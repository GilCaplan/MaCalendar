"""Turn the HWU-64 sample into a synthetic command-memory retrieval pool.

`fetch_hwu64_sample.py` collects real utterances; this script runs each one
through the REAL current parser — against fully scratch databases, never
`~/.assistant_tools/` — and records the parser's own answer, exactly the way
a real command becomes a real memory row. That's the point: the pool holds
what THIS system does with outside phrasing, not an imported "correct" label.

No feedback is set (stays at the default 'none'). We have no human judgement
on whether the parse was right, and faking 'approved' would be exactly the
kind of unreviewed-but-trusted data CLAUDE.md already warns degrades the
personalisation layer. 'none' is still retrievable — only 'rejected' and
`source='test'` are excluded — same as an untouched real command would be.

Self-check (`verify_fast_path`) is off for this build only: it's a second LLM
call per command that exists to catch bad answers before a person sees them,
and doesn't affect whether a row is retrievable. Skipping it turns a ~6-25s
call into ~4-12s, which matters across 3000 of them.

Resumable: re-running skips any (scenario, intent, text) already present in
the output db, so an interrupted overnight build picks back up rather than
starting over. Progress is logged every 25 rows.

    python -m scripts.fetch_hwu64_sample                              # writes dataset/history_<N>.json
    python -m scripts.build_memory_scaling_pool                       # replay history_3000.json (build/resume)
    python -m scripts.build_memory_scaling_pool --limit 60             # smoke test
    python -m scripts.build_memory_scaling_pool --slice-tiers          # write output/dummy_<N>.db per history
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import sqlite3
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

EXP_DIR = ROOT / "DOCUMENTATION" / "experiments" / "memory_scaling"
FIXTURE = EXP_DIR / "hwu64_sample.json"
DATASET_DIR = EXP_DIR / "dataset"     # self-contained history_<N>.json inputs — see fetch_hwu64_sample.py
OUTPUT_DIR = EXP_DIR / "output"       # dummy_<N>.db — what replaying history_<N>.json produces
POOL_DB = EXP_DIR / "pool_full.db"    # working copy the build accumulates into; not itself a deliverable
LOG = EXP_DIR / "build.log"
TIERS = [60, 300, 1000, 3000]

# --- isolate BEFORE importing the app, same pattern as scripts/audit_assistant.py
_TMP = tempfile.mkdtemp(prefix="macal_scaling_")
os.environ["MACALENDAR_NO_WARMUP"] = "1"
os.environ["MACALENDAR_DB"] = os.path.join(_TMP, "calendar.db")
os.environ["MACALENDAR_MEMORY_DB"] = str(POOL_DB)   # the pool itself IS the memory db
os.environ["MACALENDAR_VOCAB"] = os.path.join(_TMP, "vocab.json")          # intentionally empty —
os.environ["MACALENDAR_CATEGORIES"] = os.path.join(_TMP, "categories.json")  # not this user's vocabulary
os.environ["MACALENDAR_TRACE_BUS"] = os.path.join(_TMP, "trace_bus.jsonl")


def _log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def _ensure_pool_schema() -> None:
    """The memory db's own schema, plus one column this experiment adds."""
    from assistant.intent.memory import CommandMemory
    CommandMemory(str(POOL_DB))  # runs _SCHEMA + _migrate
    with sqlite3.connect(POOL_DB) as c:
        existing = {r[1] for r in c.execute("PRAGMA table_info(examples)")}
        if "tier_rank" not in existing:
            c.execute("ALTER TABLE examples ADD COLUMN tier_rank INTEGER")


def _already_built() -> set[str]:
    if not POOL_DB.exists():
        return set()
    with sqlite3.connect(POOL_DB) as c:
        try:
            rows = c.execute(
                "SELECT transcript FROM examples WHERE tier_rank IS NOT NULL").fetchall()
        except sqlite3.OperationalError:
            return set()
    return {t for (t,) in rows}


def build(limit: int | None) -> None:
    EXP_DIR.mkdir(parents=True, exist_ok=True)
    hist_path = DATASET_DIR / f"history_{max(TIERS)}.json"
    if not hist_path.exists():
        raise SystemExit(f"no {hist_path} — run scripts.fetch_hwu64_sample first")
    rows = json.loads(hist_path.read_text())["rows"]  # already ordered by seq/ts
    if limit:
        rows = rows[:limit]

    _ensure_pool_schema()
    done = _already_built()
    _log(f"pool build: {len(rows)} target rows, {len(done)} already present, resuming")

    # verify_fast_path off for this build only — real config.yaml untouched.
    # server.py does `from assistant.config import load_config`, so every call
    # site resolves the name through server's own module globals; patching
    # assistant.config.load_config after the fact would miss all of them.
    import assistant.api.server as srv
    _real_load_config = srv.load_config

    def _load_config_no_verify(path: str = "config.yaml"):
        cfg = _real_load_config(path)
        cfg.verify_fast_path = False
        return cfg

    srv.load_config = _load_config_no_verify
    app = srv.create_app()
    app.config["TESTING"] = True
    client = app.test_client()

    built = skipped = failed = 0
    t0 = time.time()
    for row in rows:
        if row["text"] in done:
            skipped += 1
            continue
        try:
            resp = client.post("/voice/text", json={"transcript": row["text"], "source": "mac"})
            if resp.status_code != 200:
                failed += 1
                _log(f"  ! HTTP {resp.status_code} on {row['text'][:60]!r}")
                continue
        except Exception as e:
            failed += 1
            _log(f"  ! {type(e).__name__}: {e} on {row['text'][:60]!r}")
            continue
        # stamp the history's timestamp + sequence position onto the row
        # memory.record() just inserted (it used time.time() at insert time).
        # Guarded by matching the transcript back — a request that produced no
        # example row at all (rather than a different one) must not mis-tag
        # whatever the last row happened to be.
        with sqlite3.connect(POOL_DB) as c:
            last = c.execute(
                "SELECT id, transcript FROM examples ORDER BY id DESC LIMIT 1").fetchone()
            if last and last[1] == row["text"]:
                c.execute("UPDATE examples SET ts=?, tier_rank=? WHERE id=?",
                          (row["ts"], row["seq"], last[0]))
            else:
                _log(f"  ! could not confirm the inserted row for {row['text'][:60]!r} — "
                     f"left unstamped, will retry on resume")
        built += 1
        if built % 25 == 0:
            rate = (built + skipped) / max(1, time.time() - t0)
            remaining = len(rows) - built - skipped - failed
            eta_min = remaining / max(rate, 1e-6) / 60
            _log(f"  {built} built, {skipped} skipped, {failed} failed / {len(rows)} "
                 f"— ETA {eta_min:.0f} min")

    _log(f"done: {built} built, {skipped} skipped, {failed} failed, "
         f"{time.time()-t0:.0f}s elapsed")


def slice_tiers() -> None:
    """For each history_<N>.json in dataset/, export the matching dummy_<N>.db.

    dummy_<N>.db = the result of replaying history_<N>.json's rows, in order,
    through the real assistant. It's cut from the accumulated POOL_DB rather
    than rebuilt from scratch per history (they're nested by construction —
    history_300 starts with every row of history_60 — so this avoids redoing
    live parser calls that were already made), but verified against the
    dataset file it's supposed to correspond to before being trusted.
    """
    if not POOL_DB.exists():
        raise SystemExit(f"no pool at {POOL_DB} yet")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for n in TIERS:
        hist_path = DATASET_DIR / f"history_{n}.json"
        if not hist_path.exists():
            print(f"skip {n}: no {hist_path.name} — run fetch_hwu64_sample first")
            continue
        history = json.loads(hist_path.read_text())

        out = OUTPUT_DIR / f"dummy_{n}.db"
        shutil.copyfile(POOL_DB, out)
        with sqlite3.connect(out) as c:
            c.execute("DELETE FROM examples WHERE tier_rank IS NULL OR tier_rank > ?", (n,))
            c.execute("DELETE FROM example_records WHERE example_id NOT IN (SELECT id FROM examples)")
            got = [r[0] for r in c.execute(
                "SELECT transcript FROM examples ORDER BY tier_rank").fetchall()]

        want = [r["text"] for r in history["rows"]]
        if got != want:
            out.unlink()
            missing = len(want) - len(got)
            print(f"REFUSING to write dummy_{n}.db: only {len(got)}/{len(want)} of "
                  f"history_{n}.json's rows have been built yet (build is still running, "
                  f"or hasn't reached row {n - missing} — re-run --slice-tiers once it has)")
            continue
        print(f"{out.name}: {len(got)} rows, matches history_{n}.json exactly")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="build only the first N rows (smoke test)")
    ap.add_argument("--slice-tiers", action="store_true", help="(re)export nested tier dbs, no building")
    args = ap.parse_args()
    if args.slice_tiers:
        slice_tiers()
    else:
        build(args.limit)
