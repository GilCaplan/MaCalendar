"""Score the resolvers against the dataset.

    python -m assistant.engine.decompose_validate.eval_metrics.run_board
    python -m assistant.engine.decompose_validate.eval_metrics.run_board --split test

Feeds each gold item's (text, time) in and scores only the VALUES that come
back, so a segmentation disagreement can never be charged to this stage.

THE DEFAULT IS THE SAFE PATH. `--split train` is the default and prints
everything; `--split test` prints AGGREGATES ONLY and refuses to show a row,
because `engine/TRAIN_TEST_SPLIT_CONVENTION.md` requires that reading a test-set
failure be impossible by accident:

    "the moment a human (or an agent) reads a test-set failure and reacts to
     it, the test set has been folded into training"

There is deliberately no flag that unlocks test row detail. If a test aggregate
disappoints, the response is to find the analogous failure in TRAIN.
"""
import argparse
import datetime as dt
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, _ROOT)
from assistant.engine.decompose_validate import checks as C               # noqa: E402
from assistant.engine.decompose_validate import resolve as R              # noqa: E402
from assistant.engine.decompose_validate.datasets import perturb as P      # noqa: E402
from assistant.engine.decompose_validate.eval_metrics import score as S    # noqa: E402

_DATA = os.path.join(_ROOT, "assistant", "engine", "decompose_validate",
                     "datasets", "generated.jsonl")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=("train", "test"), default="train")
    ap.add_argument("--samples", type=int, default=6,
                    help="example rows to print; forced to 0 for test")
    ap.add_argument("--stage", choices=("decompose", "both"), default="both",
                    help="'decompose' scores resolve.py alone; 'both' runs "
                         "validate over its output too")
    ap.add_argument("--perturb", action="store_true",
                    help="INJECT defects into the gold and let validate repair "
                         "them — this is what makes board G measurable")
    a = ap.parse_args()

    every = [json.loads(l) for l in open(_DATA)]
    rows = [r for r in every if r.get("split", "train") == a.split]
    if not rows:
        sys.exit(f"no rows with split={a.split}")

    by = {(r["text"], r["today"]): r for r in rows}

    def decompose(row, anchor):
        """resolve.py's answer for every item in the row."""
        out = []
        for g in row["gold"]:
            # The item's OWN words as context, not the row's — the same rule the
            # gold now follows, so a neighbour's "4pm" cannot move this item's
            # bare hour.
            v = R.resolve(g["time"], anchor, f"{g['time']} {g['text']}",
                          action=g["text"])
            out.append({"kind": g["kind"], "text": g["text"], "time": g["time"],
                        "date": v["date"], "start_time": v["start_time"],
                        "end_time": v["end_time"], "recurrence": v["recurrence"],
                        "recur_days": v.get("recur_days") or [],
                        "recur_until": v.get("recur_until"),
                        "quantity": R.resolve_quantity(g["text"]),
                        # lead time is a TIME slot, so it lives in `time`
                        "reminder_minutes": R.resolve_lead_time(g["time"]) or
                                            R.resolve_lead_time(g["text"])})
        return out

    def predict(text, today):
        anchor = dt.date.fromisoformat(today)
        row = by[(text, today)]

        # PERTURBED: start from the gold with a defect injected, so what is being
        # measured is validate's repair rather than decompose's arithmetic.
        # CLEAN: start from decompose's own output, which is the harder question —
        # does validate damage work that was already right?
        before = ([dict(x) for x in P.perturb_row(row)[0]] if a.perturb
                  else decompose(row, anchor))
        if a.stage == "decompose":
            return before

        after, fixes, flags = C.run(before, text, anchor)
        return {"items": after, "before": before,
                "fixes": len(fixes), "flags": len(flags)}

    samples = 0 if a.split == "test" else a.samples
    res = S.score_rows(rows, predict, samples=samples)
    board = S.format_board(res)
    if a.split == "test":
        # Truncate at the appendix rather than trusting `samples=0`: a future
        # board that prints a row somewhere else must not silently leak it.
        cut = board.find("APPENDIX")
        if cut > 0:
            board = board[:cut].rstrip()
        print(f"SEALED HALF — aggregates only, {len(rows)} rows. "
              f"Row detail is not available by design.\n")
    print(board)


if __name__ == "__main__":
    main()
