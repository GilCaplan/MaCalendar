"""Replay the verification dataset through engine-v2 and diff against the
old brain's recorded behavior.

    python -m scripts.engine_dataset_compare --limit 150          # pilot
    python -m scripts.engine_dataset_compare --limit 150 --source \
        <main>/DOCUMENTATION/experiments/memory_scaling/output/dummy_3000.db

The source db is the OLD system's behavior on 3000 real HWU-64 utterances —
not human ground truth. What this reports is therefore AGREEMENT and DRIFT
(which prompts flipped pass/fail on the dataset's own count-correctness
claim), plus a triage list of disagreements: old right / new right / both
wrong is a judgment for a human (or a later judge model), not this script.

Mechanics agreed with the dataset's owner (session macalendar-ee):
- every join is keyed on COALESCE(NULLIF(raw_transcript,''), transcript) —
  the verbatim input — because the pipeline may rewrite a transcript before
  recording it, and a stored-form join leaves such rows unmatchable;
- metrics are IMPORTED from the main checkout's scripts/score_dataset_run.py
  (never reimplemented); ~half need hwu64_sample.json provenance;
- parse-path slices are per-system descriptive stats only — the engine's
  fast/deep and the pool's rule/hybrid/llm are disjoint namespaces;
- pool_full.db is never read; only the verified dummy_<N> exports.

Replay is ISOLATED per row (fresh calendar state each time), which matches
the scorer's determinism caveat: sequence-dependent effects (context memory)
are out of scope here.

TRAIN/HELD-OUT DISCIPLINE (user decision 2026-09-04): tier ordering
interleaves complexity, so contiguous rank slices are naturally stratified.
DEV = ranks 1-600 — the only rows whose failures may be inspected, triaged,
or mined for prompt examples (the 150-row pilot that already fed rounds 4-5
sits inside it, which is what makes this honest). HELD-OUT = ranks 601-3000 —
measured, never mined; its scores are the generalisation claim. Use
--min-rank/--max-rank for cheap dev-cycle re-runs; quote the two slices
separately, always.

SUBSET ≠ HISTORY (user caution, 2026-09-04): rank slices here select REPLAY
INPUTS only — the engine runs each row against an EMPTY scratch memory, so
timestamps play no role and no history-matching is needed for the agreement
comparison. But a subset used AS a command-memory history (any k>0
retrieval experiment) is a different animal: prompts and timestamps must
come as a matched set, which is exactly what the verified tier exports
(dummy_60/300/1000, each mirroring its history_N.json with its own ts
values) exist for. For memory experiments use those tier dbs whole — never
an ad-hoc rank slice of dummy_3000, whose ts/recency semantics belong to
the full tier.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import sqlite3
import sys
import tempfile
import time

WORKTREE = pathlib.Path(__file__).resolve().parents[1]
MAIN = pathlib.Path("/Users/USER/Desktop/Personal_Projects/MACalendar")
# The dataset is first-class now: dataset/ in the tree (inputs committed,
# baseline dbs gitignored+local). Falls back to the dataset owner's original
# location in the main checkout until the merge migrates it (see dataset/DATASET.md).
_LOCAL = WORKTREE / "dataset"
EXP = MAIN / "DOCUMENTATION" / "experiments" / "memory_scaling"
DATASET_INPUTS = _LOCAL / "inputs" if (_LOCAL / "inputs").exists() else EXP / "dataset"
DATASET_FIXTURE = (_LOCAL / "inputs" / "hwu64_sample.json") if (_LOCAL / "inputs" / "hwu64_sample.json").exists() else EXP / "hwu64_sample.json"
DATASET_BASELINE = _LOCAL / "baseline" if (_LOCAL / "baseline").exists() else EXP / "output"

# --- isolate BEFORE importing anything from assistant ----------------------
_TMP = tempfile.mkdtemp(prefix="engine_compare_")
ENGINE_DB = os.path.join(_TMP, "engine_run.db")
os.environ["MACALENDAR_DB"] = os.path.join(_TMP, "calendar.db")
os.environ["MACALENDAR_MEMORY_DB"] = ENGINE_DB
os.environ["MACALENDAR_TRACE_BUS"] = os.path.join(_TMP, "trace_bus.jsonl")
os.environ["MACALENDAR_NO_WARMUP"] = "1"
import shutil as _sh
for _var, _real, _name in (
        ("MACALENDAR_VOCAB", os.path.expanduser("~/.assistant_tools/vocab.json"), "vocab.json"),
        ("MACALENDAR_CATEGORIES", os.path.expanduser("~/.assistant_tools/categories.json"), "categories.json")):
    _copy = os.path.join(_TMP, _name)
    if os.path.exists(_real):
        _sh.copyfile(_real, _copy)
    os.environ[_var] = _copy
os.chdir(WORKTREE)

RAW_KEY = "COALESCE(NULLIF(raw_transcript, ''), transcript)"


def _load_scorer():
    """Import the main checkout's scorer BY FILE PATH — both checkouts have a
    scripts/ tree, and a name import would resolve to the wrong one."""
    path = MAIN / "scripts" / "score_dataset_run.py"
    spec = importlib.util.spec_from_file_location("score_dataset_run_main", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _source_rows(source: pathlib.Path, limit: int,
                 min_rank: int = 0, max_rank: int = 0) -> list[tuple[str, int]]:
    where = "tier_rank IS NOT NULL"
    if min_rank:
        where += f" AND tier_rank >= {int(min_rank)}"
    if max_rank:
        where += f" AND tier_rank <= {int(max_rank)}"
    with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as c:
        return c.execute(
            f"SELECT {RAW_KEY}, tier_rank FROM examples WHERE {where} "
            "ORDER BY tier_rank"
            + (f" LIMIT {int(limit)}" if limit else "")
        ).fetchall()


def _reset_calendar() -> None:
    from assistant.db import get_db
    db = get_db()
    assert db.path.startswith(_TMP), "refusing to reset a non-scratch DB"
    with db._conn() as conn:
        for table in ("events", "todos", "subtasks"):
            try:
                conn.execute(f"DELETE FROM {table}")
            except sqlite3.OperationalError:
                pass


def _stamp_ranks(pairs: list[tuple[str, int]]) -> int:
    """tier_rank is experiment-only; the engine's memory schema doesn't have
    it. Add it and stamp each replayed row by its verbatim text."""
    with sqlite3.connect(ENGINE_DB) as c:
        try:
            c.execute("ALTER TABLE examples ADD COLUMN tier_rank INTEGER")
        except sqlite3.OperationalError:
            pass
        stamped = 0
        for text, rank in pairs:
            cur = c.execute(
                f"UPDATE examples SET tier_rank = ? WHERE {RAW_KEY} = ?",
                (rank, text))
            stamped += 1 if cur.rowcount else 0
    return stamped


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=pathlib.Path,
                    default=DATASET_BASELINE / "dummy_3000.db")
    ap.add_argument("--fixture", type=pathlib.Path, default=DATASET_FIXTURE)
    ap.add_argument("--limit", type=int, default=150)
    ap.add_argument("--min-rank", type=int, default=0)
    ap.add_argument("--max-rank", type=int, default=0)
    ap.add_argument("--out-dir", type=pathlib.Path,
                    default=WORKTREE / "DOCUMENTATION" / "experiments" / "engine_compare")
    args = ap.parse_args()

    scorer = _load_scorer()
    prov = scorer.load_provenance(args.fixture)
    rows = _source_rows(args.source, args.limit, args.min_rank, args.max_rank)
    print(f"Replaying {len(rows)} rows from {args.source.name} through engine-v2 "
          f"(scratch: {_TMP})")

    from assistant.api.server import create_app
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()

    t0 = time.perf_counter()
    for i, (text, rank) in enumerate(rows, 1):
        _reset_calendar()
        resp = client.post("/voice/text",
                           json={"transcript": text, "source": "test"}).get_json()
        mark = "·" if (resp.get("actions") or resp.get("parse") == "ignored") else "!"
        if i % 10 == 0 or mark == "!":
            print(f"  {mark} {i}/{len(rows)}  [{resp.get('parse', '?'):9}] {text[:64]}")

    stamped = _stamp_ranks(rows)
    print(f"Replayed in {time.perf_counter() - t0:.0f}s; {stamped}/{len(rows)} rows "
          f"stamped with tier ranks")

    engine_scored = scorer.score_db(pathlib.Path(ENGINE_DB), prov)
    old_scored = scorer.score_db(args.source, prov)
    comparison = scorer.compare(old_scored, engine_scored)

    # Shared-prompt-only rates: the source spans the full tier, the engine run
    # only the pilot slice — quoting full-tier vs slice rates side by side
    # would be a lie of framing.
    shared = {r["transcript"] for r in engine_scored["per_prompt"]}
    def _rate(scored):
        rs = [r for r in scored["per_prompt"]
              if r["transcript"] in shared and r["count_ok"] is not None]
        return (sum(r["count_ok"] for r in rs) / len(rs)) if rs else None, len(rs)
    old_rate, n_old = _rate(old_scored)
    new_rate, n_new = _rate(engine_scored)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    scorer.write_report(engine_scored, comparison, args.out_dir / "engine_run.score.md")
    def _slice_rate(scored, lo, hi):
        rs = [r for r in scored["per_prompt"]
              if r["transcript"] in shared and r["count_ok"] is not None
              and lo <= (r.get("tier_rank") or 0) <= hi]
        return (round(sum(r["count_ok"] for r in rs) / len(rs), 3) if rs else None, len(rs))

    def _slice_deltas(key):
        groups = {}
        for r in engine_scored["per_prompt"]:
            g = r.get(key)
            if g is None:
                continue
            groups.setdefault(g, [None, None])
        old_by = {r["transcript"]: r for r in old_scored["per_prompt"]}
        for r in engine_scored["per_prompt"]:
            g, t = r.get(key), r["transcript"]
            if g is None or t not in shared or r["count_ok"] is None:
                continue
            o = old_by.get(t)
            if not o or o["count_ok"] is None:
                continue
            d = groups[g]
            d[0] = (d[0] or [0, 0]); d[1] = (d[1] or [0, 0])
            d[0][0] += o["count_ok"]; d[0][1] += 1
            d[1][0] += r["count_ok"]; d[1][1] += 1
        out = {}
        for g, (o, n) in groups.items():
            if not o or not n or not o[1]:
                continue
            out[g] = {"n": n[1], "old": round(o[0]/o[1], 3), "new": round(n[0]/n[1], 3),
                      "delta": round(n[0]/n[1] - o[0]/o[1], 3)}
        return out

    triage = {
        "by_complexity": _slice_deltas("complexity"),
        "by_compound_kind": _slice_deltas("compound_kind"),
        "split_policy": "DEV=ranks 1-600 (tunable); HELD-OUT=601-3000 (measure only, never mine)",
        "dev_rate_old_vs_new": [_slice_rate(old_scored, 1, 600), _slice_rate(engine_scored, 1, 600)],
        "heldout_rate_old_vs_new": [_slice_rate(old_scored, 601, 3000), _slice_rate(engine_scored, 601, 3000)],
        "shared_prompts": len(shared),
        "count_ok_shared_old": old_rate, "count_ok_shared_new": new_rate,
        "flipped_better (old fail → engine pass)": comparison["flipped_better"],
        "flipped_worse (old pass → engine fail)": comparison["flipped_worse"],
        "note": "old-system rows are behavior, not ground truth; each flip needs "
                "triage (old right / new right / both wrong) by a human or a "
                "judge model that is not the system under test",
    }
    (args.out_dir / "triage.json").write_text(json.dumps(triage, indent=2))
    (args.out_dir / "engine_run.db").unlink(missing_ok=True)
    _sh.copyfile(ENGINE_DB, args.out_dir / "engine_run.db")

    print(f"\nAGREEMENT (shared {len(shared)} prompts, count-correctness only):")
    print(f"  old brain : {old_rate:.0%} ({n_old} scored)" if old_rate is not None else "  old brain : –")
    print(f"  engine-v2 : {new_rate:.0%} ({n_new} scored)" if new_rate is not None else "  engine-v2 : –")
    print(f"  flipped better: {len(comparison['flipped_better'])} · "
          f"flipped worse: {len(comparison['flipped_worse'])} · "
          f"unchanged pass/fail: {comparison['n_unchanged_pass']}/{comparison['n_unchanged_fail']}")
    print(f"Reports: {args.out_dir}/engine_run.score.md · triage.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
