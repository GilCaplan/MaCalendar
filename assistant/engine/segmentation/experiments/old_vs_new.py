"""The OLD segment stage vs the NEW FastSeg, on the same dataset.

Gil: "run the old implementation on the datasets we used on the new
segmentation system just to compare results from the old to new. dont try
improve it, its just to look."

THE COMPARISON HAS TO BE FAIR OR IT IS NOT WORTH RUNNING, and a naive one is
not. The old stage emits `Item(kind, text)` where `text` is the whole span
INCLUDING the time — separating action from time is the NEW contract, invented
after it. Scoring it on `time`, or on exact-row, would report a catastrophe for
a field it was never asked to produce.

So both systems are scored only on the three things they BOTH genuinely do:

    1  item count      did it cut the command into the right number of pieces
    2  item P/R/F1     are the pieces the right pieces
    3  kind / tag      event | task | review

and the gold each is compared against is the one appropriate to its contract:

    new  ->  (action, time, tag)      as labelled
    old  ->  (action + time, kind)    the span it should have produced

The date FLOOR is excluded when rebuilding the old gold: "today" is a value the
labelling adds, not a word the speaker said, so an implementation that never
emitted it must not be charged for the omission.

    python -m assistant.engine.segmentation.experiments.old_vs_new
"""
from __future__ import annotations

import glob
import os
import sys
import time

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_S = "/tmp/seg_old_vs_new"
os.makedirs(_S, exist_ok=True)
for k, v in dict(MACALENDAR_DB=f"{_S}/c.db", MACALENDAR_MEMORY_DB=f"{_S}/m.db",
                 MACALENDAR_VOCAB=f"{_S}/v.json", MACALENDAR_CATEGORIES=f"{_S}/g.json",
                 MACALENDAR_TRACE_BUS=f"{_S}/t.jsonl",
                 MACALENDAR_NO_WARMUP="1").items():
    os.environ.setdefault(k, v)

from assistant.engine.segmentation.fastseg import invariant
from assistant.engine.segmentation.experiments import score as sc          # noqa: E402
from assistant.engine.segmentation.fastseg.fastseg import fastseg                 # noqa: E402
from assistant.engine.segmentation.experiments.run_board import (  # noqa: E402
    assign_splits, stratified_sample)


def old_gold(row: "dict") -> "list[dict]":
    """The gold the OLD contract should be judged against: one span per item,
    time folded back in, minus the floor the labelling added."""
    out = []
    said = invariant.content(row["text"])
    for item in row["gold"]:
        time = " ".join(w for w in str(item["time"]).split()
                        if w.lower() != invariant.DEFAULT_TIME
                        or invariant.DEFAULT_TIME in said)
        out.append({"action": f"{item['action']} {time}".strip(),
                    "time": "", "tag": item["tag"]})
    return out


def run_old(text: str, cfg) -> "list[dict]":
    """One command through the shipped segment stage."""
    from assistant.engine.segmentation.old_seg import segment
    from assistant.engine.state import EngineState

    state = EngineState(raw_text=text, text=text, source="test")
    try:
        segment.run(state, cfg)
    except Exception:
        return []
    return [{"action": it.text, "time": "", "tag": it.kind}
            for it in (state.items or [])]


def board(name: str, rows, predict, gold_of) -> dict:
    n = len(rows)
    count_ok = tp = n_pred = n_gold = tag_ok = tag_n = 0
    over = under = 0
    elapsed = 0.0
    for row in rows:
        gold = [sc.as_item(g) for g in gold_of(row)]
        _t0 = time.perf_counter()
        raw_pred = predict(row["text"])
        elapsed += time.perf_counter() - _t0
        pred = [sc.as_item(p) for p in raw_pred]
        count_ok += len(gold) == len(pred)
        over += len(pred) > len(gold)
        under += len(pred) < len(gold)
        pairs, _mg, _mp = sc.match_items(gold, pred)
        tp += len(pairs)
        n_pred += len(pred)
        n_gold += len(gold)
        for gi, pi, _s in pairs:
            tag_n += 1
            tag_ok += gold[gi]["tag"] == pred[pi]["tag"]
    prec = tp / n_pred if n_pred else 0.0
    rec = tp / n_gold if n_gold else 0.0
    return {"name": name, "n": n, "count": count_ok / n,
            "p": prec, "r": rec,
            "f1": 2 * prec * rec / (prec + rec) if prec + rec else 0.0,
            "tag": tag_ok / tag_n if tag_n else 0.0, "tag_n": tag_n,
            "over": over, "under": under, "sec_per_row": elapsed / max(1, n)}


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0,
                    help="cap the rows; the OLD stage falls back to the LLM, so a "
                         "full pass is a model job")
    a = ap.parse_args()
    from assistant.engine import load_config

    cfg = load_config()
    rows = [r for r in assign_splits(
        sc.load_rows(sorted(glob.glob(f"{_HERE}/datasets/*.jsonl"))))
        if r["split"] == "train"]
    if a.limit:
        # TRAP-STRATIFIED, not the first N: the rows sort by id, so a plain head
        # would be one template family repeated and would say nothing about the
        # shapes the two systems actually differ on.
        rows = stratified_sample(rows, a.limit)

    print(f"{len(rows)} rows — segment-tuning TRAIN half\n")
    print("Both systems judged ONLY on what both were built to do. The old "
          "stage never\nseparated time from action, so `time` and `exact-row` "
          "are N/A for it BY DESIGN,\nnot a failure — it is not scored on them.\n")

    results = [
        board("old_seg (shipped)", rows, lambda t: run_old(t, cfg), old_gold),
        board("FastSeg (new)", rows, fastseg, lambda r: r["gold"]),
    ]

    print(f"{'':<20}{'item count':>12}{'item P':>9}{'item R':>9}{'item F1':>10}"
          f"{'tag acc':>10}{'over':>7}{'under':>7}{'sec/row':>10}")
    print("-" * 84)
    for b in results:
        print(f"{b['name']:<20}{b['count']:>12.1%}{b['p']:>9.1%}{b['r']:>9.1%}"
              f"{b['f1']:>10.1%}{b['tag']:>10.1%}{b['over']:>7}{b['under']:>7}"
              f"{b['sec_per_row']:>10.3f}")

    o, nw = results
    print(f"\n{'delta (new - old)':<20}{nw['count'] - o['count']:>+12.1%}"
          f"{nw['p'] - o['p']:>+9.1%}{nw['r'] - o['r']:>+9.1%}"
          f"{nw['f1'] - o['f1']:>+10.1%}{nw['tag'] - o['tag']:>+10.1%}")

    print(f"\n   COST is the column that changes the reading: old_seg falls back "
          f"to the\n   LLM when its deterministic pass finds nothing, so its score "
          f"is MODEL-ASSISTED.\n   FastSeg makes zero model calls "
          f"({o['sec_per_row'] / max(1e-9, nw['sec_per_row']):.0f}x faster here).")
    print("\nONLY THE NEW SYSTEM DOES THIS (no old-system number exists):")
    print("   time extraction — the old stage left the time inside the item text")


if __name__ == "__main__":
    main()
