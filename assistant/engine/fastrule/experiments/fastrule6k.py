"""FS1 — score FastRule against its own 6,000-row dataset (all six metrics).

    python -m assistant.engine.fastrule.experiments.fastrule6k                # train 4,800: full board + mining
    python -m assistant.engine.fastrule.experiments.fastrule6k --split test   # test 1,200: AGGREGATES ONLY

Ground truth is by construction (assistant/engine/fastrule/datasets/DATASET.md). Scoring per
row, against `expect`:
  • commit/abstain + counts + action  — the selective-classifier core;
  • ATOMICITY DETECTION — the first direct gate supervision: a compound
    reason (strong-compound / clause-coordination / mixed-mode) is FastRule
    saying "not atomic"; scored as a binary classifier against expect.atomic;
  • title slot — committed creates' first title vs expect.slots.title
    (normalized containment either way);
  • LABELS (metric 6) — the real classify()/tagging functions run on the
    committed titles against the dataset's frozen category fixture
    (MACALENDAR_CATEGORIES points there; personal config never enters).

LEAKAGE GUARD, enforced here: --split test prints aggregates only — no row
text, no per-family lines, no misses. Test mistakes are never mined
(assistant/engine/TRAIN_TEST_SPLIT_CONVENTION.md; ITERATION_PROTOCOL.md).
"""
from __future__ import annotations

import argparse
import collections
import datetime as _dt
import json
import os
import pathlib
import sys
import tempfile

# Lane scripts run BESIDE live engine measurements by design (Gil: FastRule
# iteration never waits on the deep track). The BLAS single-thread pin is the
# guard that makes two model-loading processes safe together — structural
# here, not left to the caller.
for _blas in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_blas, "1")

ROOT = pathlib.Path(__file__).resolve().parents[1]
_FIXTURE = ROOT / "datasets" / "banks" / "categories_fixture.json"

# isolate BEFORE importing assistant; categories -> the dataset's fixture
_T = tempfile.mkdtemp(prefix="fr6k_")
for _v, _n in (("DB", "c.db"), ("MEMORY_DB", "m.db"), ("VOCAB", "v.json"),
               ("TRACE_BUS", "t.jsonl"), ("LOCATION", "l.json")):
    os.environ[f"MACALENDAR_{_v}"] = os.path.join(_T, _n)
os.environ["MACALENDAR_CATEGORIES"] = str(_FIXTURE)
os.environ["MACALENDAR_NO_WARMUP"] = "1"

# deterministic clock: date phrases resolve against a fixed Wednesday morning
_CLOCK = _dt.datetime(2026, 9, 9, 10, 0, 0)

_COMPOUND_REASONS = ("strong-compound", "clause-coordination", "mixed-mode-compound")


def _norm(s: str) -> str:
    return " ".join("".join(c for c in (s or "").lower() if c.isalnum() or c.isspace()).split())


def _title_ok(got: str, want: str) -> bool:
    g, w = _norm(got), _norm(want)
    return bool(g and w) and (w in g or g in w)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=("train", "test"), default="train")
    ap.add_argument("--tier", choices=("simple", "complex", ""), default="")
    a = ap.parse_args()
    aggregates_only = a.split == "test"

    from freezegun import freeze_time
    # imports + the recognizer's lazy first-analyze happen OUTSIDE the frozen
    # clock (the main harness's epoch lesson: freezing during warm-up breaks
    # every later date resolution) — only the scoring loop runs frozen.
    from assistant.engine.fastrule.fastrule import FastRule
    from assistant.actions.calendar.categories import classify as _classify
    from assistant.actions.todo import tagging as _tagging
    from assistant.intent.rule_parser import RULE_THRESHOLD
    FastRule(RULE_THRESHOLD).run("book gym tomorrow at 7am")   # warm
    with freeze_time(_CLOCK):

        fixture = json.loads(_FIXTURE.read_text())
        task_tag_kw = fixture.get("task_tags", {})

        def _tags_for(title: str) -> "list[str]":
            low = (title or "").lower()
            return sorted(d["name"] for d in task_tag_kw
                          if any(k in low for k in d.get("keywords", ())))

        rows = [json.loads(l) for l in
                (ROOT / "datasets" / "fastrule_7200.jsonl").open()]
        rows = [r for r in rows if r["split"] == a.split
                and (not a.tier or r["tier"] == a.tier)]

        fr = FastRule(RULE_THRESHOLD)
        n = len(rows)
        committed = correct = 0
        # atomicity confusion: (predicted-compound?, truly-compound?)
        at_tp = at_fp = at_fn = at_tn = 0
        title_ok = title_n = 0
        cat_ok = cat_n = 0
        cat_conf: collections.Counter = collections.Counter()
        tag_tp = tag_fp = tag_fn = 0
        fam_bad: collections.Counter = collections.Counter()
        fam_all: collections.Counter = collections.Counter()
        misses: list[tuple[str, str, str]] = []

        for r in rows:
            e = r["expect"]
            fam_all[r["family"]] += 1
            try:
                res = fr.run(r["text"])
            except Exception:
                res = None
            reason = (res.reason or "") if res else "error"
            pred_compound = any(reason.startswith(c) for c in _COMPOUND_REASONS)
            truly_compound = not e.get("atomic", True)
            if pred_compound and truly_compound: at_tp += 1
            elif pred_compound: at_fp += 1
            elif truly_compound: at_fn += 1
            else: at_tn += 1

            if not (res and res.committed):
                continue    # abstain: deep's job, not an error here
            committed += 1
            ev = sum(1 for nm, _ in res.intents if nm == "create_event")
            td = sum(1 for nm, _ in res.intents if nm == "create_todo")
            names = [nm for nm, _ in res.intents]
            act = e.get("action", "")
            if act in ("create_event", "create_todo", "mixed"):
                ok = ev >= e.get("events", 0) and td >= e.get("tasks", 0) \
                     and (ev + td) >= (e.get("events", 0) + e.get("tasks", 0))
            elif act == "query":
                ok = (ev + td) == 0 and any(nm.startswith("query") for nm in names)
            else:   # delete_* / complete_todo / update_*
                ok = (ev + td) == 0 and any(nm.startswith(act.split("_")[0]) for nm in names)
            if ok:
                correct += 1
            else:
                fam_bad[r["family"]] += 1
                if not aggregates_only and len(misses) < 25:
                    misses.append((r["family"], act, r["text"][:64]))

            # slots + labels on correctly-shaped commits only
            if ok and act in ("create_event", "create_todo") and e.get("slots", {}).get("title"):
                first = next((i for nm, i in res.intents if nm.startswith("create")), None)
                got_title = ""
                if first is not None:
                    tl = getattr(first, "titles", None) or [getattr(first, "title", "")]
                    got_title = (tl[0] if tl else "") or ""
                title_n += 1
                if _title_ok(got_title, e["slots"]["title"]):
                    title_ok += 1
                if act == "create_event" and e["slots"].get("category"):
                    cat_n += 1
                    got_cat = _classify(got_title)
                    cat_conf[(e["slots"]["category"], got_cat)] += 1
                    if got_cat == e["slots"]["category"]:
                        cat_ok += 1
                if act == "create_todo" and "tags" in e["slots"]:
                    want = set(e["slots"]["tags"]); got = set(_tags_for(got_title))
                    tag_tp += len(want & got)
                    tag_fp += len(got - want)
                    tag_fn += len(want - got)

    def pct(x, d): return f"{x/d:.1%}" if d else "—"
    print(f"[{a.split}{'/'+a.tier if a.tier else ''}] rows {n} · committed {committed} "
          f"({pct(committed,n)}) · correct-on-committed {pct(correct,committed)}")
    ap_ = at_tp / (at_tp + at_fp) if at_tp + at_fp else 0
    ar_ = at_tp / (at_tp + at_fn) if at_tp + at_fn else 0
    print(f"ATOMICITY (gate supervision): precision {ap_:.1%} · recall {ar_:.1%} · "
          f"acc {pct(at_tp+at_tn, n)}  (compound-flagged {at_tp+at_fp}, truly-compound {at_tp+at_fn})")
    print(f"TITLE slot (on correct commits): {pct(title_ok, title_n)} (n={title_n})")
    print(f"LABELS · category acc {pct(cat_ok, cat_n)} (n={cat_n}) · "
          f"tags micro-P {pct(tag_tp, tag_tp+tag_fp)} R {pct(tag_tp, tag_tp+tag_fn)}")
    if aggregates_only:
        print("(test split: aggregates only — leakage guard)")
        return 0
    print("\nworst families (committed-wrong / total):")
    for fam, bad in fam_bad.most_common(10):
        print(f"  {fam:32} {bad}/{fam_all[fam]}")
    print("\nmisses (train mining):")
    for fam, act, txt in misses[:15]:
        print(f"  [{fam} · {act}] {txt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
