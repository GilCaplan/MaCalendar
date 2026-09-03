"""Is the routing threshold in the right place?

The rule parser scores its own confidence, and everything above 0.85 is
answered without consulting the model. That number was chosen by hand and has
never been checked against what actually happened afterwards — because the
score was computed, used for the decision, and thrown away. It is recorded now,
and this reads it back.

The question is not "is the score accurate" in the abstract. It is the one
question the threshold exists to answer:

    of the commands the rules were confident about, how many were right?

If commands scoring just above the line are wrong more often than the line
implies, the threshold is too low and the model should be seeing them. If they
are almost never wrong, the threshold is too high and work is being sent to the
model for nothing — at roughly eight seconds a time.

    python -m scripts.calibration

Read-only. It reports "not enough yet" rather than a confident-looking number
when the data cannot support one, which is the failure mode that matters: a
calibration curve drawn from a dozen commands is worse than no curve, because
it looks like evidence.
"""
from __future__ import annotations

import argparse
import collections
import os
import sqlite3
import sys

DB = os.environ.get("MACALENDAR_MEMORY_DB",
                    os.path.expanduser("~/.assistant_tools/nlu_memory.db"))

#: Below this many judged commands in a bucket, the ratio is noise wearing a
#: percentage sign. Three is not "enough" — it is the floor below which the
#: number is not printed at all.
MIN_PER_BUCKET = 3
#: A verdict only counts if a person gave one. "nothing threw an exception" is
#: not evidence that the command was understood.
JUDGED = {"approved": True, "corrected": False, "rejected": False}


def load(path: str) -> list[dict]:
    if not os.path.exists(path):
        sys.exit(f"no memory database at {path}")
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    cols = {r[1] for r in c.execute("PRAGMA table_info(examples)")}
    if "confidence" not in cols:
        sys.exit("this database predates the confidence column — nothing to read yet")
    return [dict(r) for r in c.execute(
        "SELECT confidence, feedback, parse_path, transcript FROM examples "
        "WHERE COALESCE(source,'') != 'test' ORDER BY ts")]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=DB)
    args = ap.parse_args()

    rows = load(args.db)
    judged = [r for r in rows if r["feedback"] in JUDGED]
    scored = [r for r in judged if r["confidence"] is not None and r["confidence"] >= 0]

    print(f"{len(rows)} real commands · {len(judged)} with a human verdict "
          f"· {len(scored)} of those also carry a confidence\n")

    if not scored:
        print("Nothing to calibrate yet.\n")
        print("  The confidence column was added on 2026-09-03; commands recorded")
        print("  before that have none, and it is only written on the rule path.")
        print("  Come back after a week of ordinary use — at ~10 commands a day")
        print("  that is roughly 70 commands, of which the rules answer about")
        print(f"  half. The first bucket becomes readable at {MIN_PER_BUCKET} judged commands.")
        return 0

    # Bucket by distinct score rather than by even-width bins. The score is a
    # product of a handful of hand-picked multipliers, so it takes only a few
    # distinct values — even bins would spread three real values across ten
    # mostly-empty buckets and invent structure that is not there.
    by_score: dict[float, list[dict]] = collections.defaultdict(list)
    for r in scored:
        by_score[round(float(r["confidence"]), 2)].append(r)

    print(f"{'score':>7}{'n':>5}{'right':>7}{'ratio':>8}   {'':<4}")
    print("-" * 44)
    for score in sorted(by_score, reverse=True):
        group = by_score[score]
        right = sum(1 for r in group if JUDGED[r["feedback"]])
        side = "answered by rules" if score >= 0.85 else "sent to the model"
        if len(group) < MIN_PER_BUCKET:
            print(f"{score:>7.2f}{len(group):>5}{right:>7}{'—':>8}   too few to read · {side}")
        else:
            print(f"{score:>7.2f}{len(group):>5}{right:>7}{right/len(group):>7.0%}   {side}")

    above = [r for r in scored if r["confidence"] >= 0.85]
    below = [r for r in scored if r["confidence"] < 0.85]
    print()
    for label, group in (("at or above 0.85", above), ("below 0.85", below)):
        if len(group) < MIN_PER_BUCKET:
            print(f"  {label:<18} {len(group):>3} judged — not enough to say anything")
            continue
        right = sum(1 for r in group if JUDGED[r["feedback"]])
        print(f"  {label:<18} {len(group):>3} judged · {right/len(group):.0%} right")

    if len(above) >= MIN_PER_BUCKET:
        rate = sum(1 for r in above if JUDGED[r["feedback"]]) / len(above)
        print()
        if rate < 0.85:
            print(f"  The confident side is right {rate:.0%} of the time, which is less often")
            print("  than 0.85 claims. That argues for raising the threshold, or for")
            print("  finding what the score is missing on the commands it gets wrong.")
        elif rate > 0.97:
            print(f"  The confident side is right {rate:.0%} of the time. If the other side")
            print("  is not much worse, the threshold is buying latency and little else.")
        else:
            print(f"  {rate:.0%} on the confident side is roughly what 0.85 claims.")

    print("\n  A verdict here means you approved, corrected or deleted the result.")
    print("  Commands you never judged are excluded — success only means nothing threw.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
