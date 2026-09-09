#!/usr/bin/env python3
"""Score FastRule against the REAL-SPEECH dataset (dataset/realspeech/).

This deliberately owns NO metric of its own. It selects a slice of
`realspeech_1200.jsonl`, writes it to a scratch file, points
`assistant/engine/fastrule/experiments/fastrule_shape` at that file and runs
it — so the numbers printed
here are literally the FastRule product-shape board (atomic handle-rate,
correct-on-handled, date/time correctness, harm, the non-atomic diagnostic
buckets and the propose defer rate), computed by the same code that produces
them on `assistant/engine/fastrule/datasets/`. Two boards that share a scorer are comparable;
two boards that share only a vocabulary are not.

The one thing this adds is the SLICE, because a real-speech board has two
populations that must never be blended into one headline:

    --pool faithful   asks-per-utterance reproduces the measured real mix.
                      THIS is the real-usage proxy — quote this one.
    --pool stress     the multi-ask tail, oversampled for diagnosis. A
                      microscope, never a headline.
    --pool all        both, for completeness only.

    python -m scripts.realspeech_board                    # test split, faithful
    python -m scripts.realspeech_board --split train      # mining
    python -m scripts.realspeech_board --pool stress
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA = ROOT / "dataset" / "realspeech" / "realspeech_1200.jsonl"


def _shape_ok(row: dict, spec: "str | None") -> bool:
    if not spec:
        return True
    if spec.startswith("no:"):
        return spec[3:] not in row["shapes"]
    return spec in row["shapes"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--split", choices=("train", "test"), default="test")
    ap.add_argument("--pool", choices=("faithful", "stress", "all"),
                    default="faithful")
    ap.add_argument("--asks", type=int, default=None,
                    help="restrict to rows with exactly N asks (diagnostic)")
    ap.add_argument("--undisputed-dates", action="store_true",
                    help="drop rows whose ground-truth date is a relative "
                         "weekday ('next thursday'), where the engine and the "
                         "scorer hold two defensible readings and the project "
                         "has ruled neither. Legitimate on the test half: the "
                         "slice is defined by a PRE-DECLARED convention "
                         "dispute recorded by the generator, not by which "
                         "rows failed.")
    ap.add_argument("--shape", default=None,
                    help="restrict to rows where this speech shape fired, or "
                         "'no:<shape>' for rows where it did not. TRAIN-SIDE "
                         "MINING ONLY — slicing the test half by shape to "
                         "decide what to fix is exactly the leakage the "
                         "protocol forbids (ITERATION_PROTOCOL.md).")
    a = ap.parse_args()

    rows = [json.loads(l) for l in DATA.open(encoding="utf-8")]
    sel = [r for r in rows if r["split"] == a.split
           and (a.pool == "all" or r["pool"] == a.pool)
           and (a.asks is None or r["n_asks"] == a.asks)
           and _shape_ok(r, a.shape)
           and not (a.undisputed_dates
                    and "date_weekday_relative" in r["shapes"])]
    if not sel:
        raise SystemExit("no rows in that slice")
    if a.shape and a.split == "test":
        raise SystemExit(
            "--shape is train-side mining only: slicing the sealed test half "
            "by shape to decide what to fix is the leakage the protocol "
            "forbids. Re-run with --split train.")

    scratch = pathlib.Path(tempfile.mkdtemp(prefix="rs_board_")) / "slice.jsonl"
    with scratch.open("w", encoding="utf-8") as f:
        for r in sel:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # import AFTER the slice exists; fastrule_shape sets its scratch stores at
    # import time (MACALENDAR_* -> a temp dir), which is what keeps this run
    # from ever touching ~/.assistant_tools/.
    from assistant.engine.fastrule.experiments import fastrule_shape
    fastrule_shape.DATA = scratch

    print(f"dataset/realspeech · pool={a.pool} · split={a.split}"
          + (f" · {a.asks}-ask" if a.asks is not None else "")
          + (f" · shape={a.shape}" if a.shape else "")
          + (" · undisputed dates only" if a.undisputed_dates else "")
          + f" · n={len(sel)}")
    print("(metrics: assistant/engine/fastrule/experiments/fastrule_shape "
          "— same scorer as the FastRule 7,200 board)\n")
    sys.argv = ["fastrule_shape", "--split", a.split]
    return fastrule_shape.main()


if __name__ == "__main__":
    sys.exit(main())
