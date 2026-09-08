"""Full six-board comparison of two segment systems on identical rows.

A two-metric summary hides which WAY a system is failing, which is the whole
reason `score.py` has six boards. This runs the complete board for each system
over the SAME rows and prints every metric side by side with a delta, so a gain
on one board that is paid for on another cannot be reported as a win.

Model answers are replayed from `runs/prompt_lab_cache.jsonl`, so this makes NO
model calls and can be re-run freely.

    python -m segment_tuning.compare_boards --variant v4-full
    python -m segment_tuning.compare_boards --variant boundaries --source handwritten
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_S = "/tmp/seg_compare"
os.makedirs(_S, exist_ok=True)
for k, v in dict(MACALENDAR_DB=f"{_S}/c.db", MACALENDAR_MEMORY_DB=f"{_S}/m.db",
                 MACALENDAR_VOCAB=f"{_S}/v.json", MACALENDAR_CATEGORIES=f"{_S}/g.json",
                 MACALENDAR_TRACE_BUS=f"{_S}/t.jsonl",
                 MACALENDAR_NO_WARMUP="1").items():
    os.environ.setdefault(k, v)

from segment_tuning import llmseg, score as sc               # noqa: E402
from segment_tuning.fastseg import fastseg                   # noqa: E402
from segment_tuning.prompt_lab import _cache_load, interpret  # noqa: E402
from segment_tuning.run_board import assign_splits, stratified_sample  # noqa: E402

#: (label, path into the result dict, formatter). Every board is represented —
#: omitting one is how a regression gets reported as a win.
_ROWS = [
    ("A  exact-set (actions)",        ("boundaries", "exact_set"),   "pct_rows"),
    ("A  exact-row (all 3 fields)",   ("boundaries", "exact_row"),   "pct_rows"),
    ("A  right item count (the cut)", ("boundaries", "count_right"), "pct_rows"),
    ("A  item precision",             ("boundaries", "precision"),   "pct"),
    ("A  item recall",                ("boundaries", "recall"),      "pct"),
    ("A  item F1",                    ("boundaries", "f1"),          "pct"),
    ("A  rows OVER-split",            ("boundaries", "over_rows"),   "int"),
    ("A  rows UNDER-split",           ("boundaries", "under_rows"),  "int"),
    ("A2 items all 3 right",          ("action_time", "soft3"),      "int"),
    ("A2 items >= 2 of 3",            ("action_time", "soft2"),      "int"),
    ("A2 rows >= 2 of 3",             ("action_time", "soft_rows"),  "pct_rows"),
    ("B  NO-INVENTION items (=0)",    ("action_time", "invention_items"), "int"),
    ("B  NO-LOSS items (=0)",         ("action_time", "loss_items"), "int"),
    ("B  time accuracy",              ("action_time", "time_exact"), "over_matched"),
    ("B  time on a SPOKEN time",      ("action_time", "time_spoken_ok"), "spoken"),
    ("B  time on the 'today' default", ("action_time", "time_default_ok"), "default"),
    ("B  NO-LOSS rows",               ("action_time", "loss_rows"),  "int"),
    ("C  tag accuracy",               ("tag", "correct"),            "over_tag_n"),
    ("E  model calls / row",           ("cost", "calls_per_row"),    "raw"),
    ("E  seconds / row",               ("cost", "seconds_per_row"),  "raw"),
]


def _get(res, path):
    cur = res
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def fmt(res, path, kind):
    v = _get(res, path)
    if v is None:
        return "—", None
    n_rows = res.get("n_rows") or 1
    matched = _get(res, ("action_time", "matched")) or 1
    tag_n = _get(res, ("tag", "n")) or 1
    if kind == "pct_rows":
        return (f"{v / n_rows:.1%}", v / n_rows) if isinstance(v, int) else (f"{v:.1%}", v)
    if kind == "pct":
        return f"{v:.1%}", v
    if kind == "int":
        return f"{v}", float(v)
    if kind == "over_matched":
        return f"{v / matched:.1%}", v / matched
    if kind == "over_tag_n":
        return f"{v / tag_n:.1%}", v / tag_n
    if kind == "spoken":
        n = _get(res, ("action_time", "time_spoken_n")) or 1
        return f"{v / n:.1%}", v / n
    if kind == "default":
        n = _get(res, ("action_time", "time_default_n")) or 1
        return f"{v / n:.1%}", v / n
    return (f"{v:.2f}", float(v)) if isinstance(v, (int, float)) else (str(v), None)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="v4-full")
    ap.add_argument("--sample", type=int, default=600)
    ap.add_argument("--source", choices=("generated", "handwritten"))
    a = ap.parse_args()

    pool = [r for r in assign_splits(
        sc.load_rows(sorted(glob.glob(f"{_HERE}/data/*.jsonl"))))
        if r["split"] == "train"]
    rows = stratified_sample(pool, a.sample)
    cache = _cache_load()
    rows = [r for r in rows if (a.variant, r["text"]) in cache]
    if a.source:
        rows = [r for r in rows if r.get("source", "handwritten") == a.source]
    if not rows:
        raise SystemExit(f"no cached {a.variant} answers"
                         + (f" for source={a.source}" if a.source else ""))

    def fs(text):
        return {"items": fastseg(text), "calls": 0, "seconds": 0.010}

    def seg(text):
        prop = fastseg(text)
        items = interpret(a.variant, cache[(a.variant, text)], text, prop)
        final, why = llmseg.accept(text, prop, items if items is not None else prop)
        return {"items": final, "calls": 1, "seconds": 6.3, "tier": why.split(":")[0]}

    left = sc.score_rows(rows, fs, samples=0)
    right = sc.score_rows(rows, seg, samples=0)

    hw = sum(1 for r in rows if r.get("source", "handwritten") == "handwritten")
    print(f"\n{'=' * 78}")
    print(f"FastSeg alone   vs   FastSeg + LLMSeg ({a.variant})")
    print(f"{len(rows)} identical rows · TRAIN half · hand-written {hw} "
          f"({hw / len(rows):.0%})"
          + (f" · {a.source} only" if a.source else ""))
    print(f"95% CI on a ~50% rate: +/-{1.96 * (0.25 / len(rows)) ** 0.5:.1%}")
    print("=" * 78)
    print(f"{'metric':<32}{'FastSeg':>12}{'+LLMSeg':>12}{'delta':>12}   verdict")
    print("-" * 78)
    for label, path, kind in _ROWS:
        ls, lv = fmt(left, path, kind)
        rs, rv = fmt(right, path, kind)
        delta = verdict = ""
        if lv is not None and rv is not None:
            d = rv - lv
            lower_is_better = any(k in label for k in
                                  ("OVER-split", "UNDER-split", "NO-INVENTION",
                                   "NO-LOSS", "calls", "seconds"))
            if kind in ("int",) or "calls" in label or "seconds" in label:
                delta = f"{d:+.2f}" if abs(d) < 10 and d != int(d) else f"{int(d):+d}"
            else:
                delta = f"{d:+.1%}"
            if abs(d) > 1e-9:
                good = (d < 0) if lower_is_better else (d > 0)
                verdict = "better" if good else "WORSE"
        print(f"{label:<32}{ls:>12}{rs:>12}{delta:>12}   {verdict}")

    print("\n   NOTE: over- and under-split are never summed and do not cost the "
          "same.\n   An over-split makes garbage immediately; an under-split gets two "
          "more\n   chances downstream. Trading under for over is not a win.")

    print("\nF  composition")
    for k, v in (_get(left, ("composition", "counts")) or {}).items():
        print(f"   {k} ask: {v} rows")
    tiers = _get(right, ("cost", "tiers")) or {}
    if tiers:
        print("\nE  what the ACCEPT guard decided")
        for k, v in sorted(tiers.items(), key=lambda kv: -kv[1]):
            print(f"   {k:<12} {v}")


if __name__ == "__main__":
    main()
