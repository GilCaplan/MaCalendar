"""Print the FULL metric board for a loop run (Gil's rule: every cycle close
reports every metric, never a highlights-only summary).

    python -m scripts.run_board 12          # run 12 vs its predecessor + baseline
"""
from __future__ import annotations

import csv
import pathlib
import sys

LOG = pathlib.Path(__file__).resolve().parents[1] / "dataset" / "loop_log.csv"

ROWS = [
    ("count-correct raw", "overall_pct"), ("product-adjusted", "adj_pct"),
    ("simple", "simple_pct"), ("medium", "medium_pct"), ("complex", "complex_pct"),
    ("event+event", "event_event_pct"), ("task+task", "task_task_pct"),
    ("event+task", "event_task_pct"),
    ("e+t event-half missing", "et_event_missing"),
    ("e+t task-half missing", "et_task_missing"),
    ("date-collapse %", "ee_date_collapse_pct"), ("garbage titles %", "garbage_pct"),
    ("precision", "precision_pct"), ("recall", "recall_pct"), ("F1", "f1_pct"),
    ("field quality", "fieldq_pct"), ("when-correct", "when_ok_pct"),
    ("difficulty-weighted", "wtd_fieldq_pct"),
    ("deep correct %", "deep_pct"), ("fast correct %", "fast_pct"),
    ("n deep", "n_deep"), ("n fast", "n_fast"),
    ("p50 ms", "p50_ms"), ("p95 ms", "p95_ms"),
]


def main() -> int:
    run = sys.argv[1] if len(sys.argv) > 1 else None
    rows = list(csv.DictReader(open(LOG)))
    if run is None:
        run = rows[-1]["run"]
    tgt = next(r for r in rows if r["run"] == run)
    prev = next((r for r in reversed(rows) if int(r["run"]) < int(run)
                 and r["slice"] == tgt["slice"]), {})
    base = next((r for r in rows if r["label"] == "epoch-baseline"), {})
    print(f"run {run} ({tgt['label']}, {tgt['slice']}, commit {tgt['commit']})")
    print(f"{'metric':<26}{'baseline':>10}{'prev':>10}{'this run':>10}")
    for name, key in ROWS:
        print(f"{name:<26}{base.get(key,'') or '–':>10}"
              f"{prev.get(key,'') or '–':>10}{tgt.get(key,'') or '–':>10}")
    print(f"\nsummary: {tgt['summary']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
