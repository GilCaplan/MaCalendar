"""The prompt is DOWNSTREAM of the spec — this proves it still agrees.

Five defects were found in the V3 prompt by hand, all of the same kind: the
gold conventions moved and the prompt did not follow. Each one graded the model
WRONG FOR OBEYING ITS INSTRUCTIONS, which makes every measurement taken against
it worthless as evidence about the model.

Hand-auditing found them once. This finds them every time, the way
`test_artifact_claims.py` keeps the published pages honest about the code:

  1. every example parses, and every tag is one of the three
  2. every example satisfies the no-loss / no-invention invariant
  3. the DATE FLOOR holds — an item with a clock and no day says "today at X"
  4. the time keeps the preposition it was spoken with
  5. FastSeg, run on the example, agrees with what the prompt claims — or the
     disagreement is printed, because a prompt that teaches something FastSeg
     contradicts means one of the two is wrong and BOTH cannot be shipped

    python -m segment_tuning.check_prompt
"""
from __future__ import annotations

import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_S = "/tmp/seg_check_prompt"
os.makedirs(_S, exist_ok=True)
for k, v in dict(MACALENDAR_DB=f"{_S}/c.db", MACALENDAR_MEMORY_DB=f"{_S}/m.db",
                 MACALENDAR_VOCAB=f"{_S}/v.json", MACALENDAR_CATEGORIES=f"{_S}/g.json",
                 MACALENDAR_TRACE_BUS=f"{_S}/t.jsonl",
                 MACALENDAR_NO_WARMUP="1").items():
    os.environ.setdefault(k, v)

from segment_tuning import invariant, llmseg                # noqa: E402
from segment_tuning.fastseg import fastseg, find_time_refs  # noqa: E402

_DAY = re.compile(
    r"\b(today|tomorrow|tonight|yesterday|monday|tuesday|wednesday|thursday|"
    r"friday|saturday|sunday|next|this|last|every|each|daily|weekly|monthly|"
    r"jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|christmas|weekend|"
    r"week|month|morning|afternoon|evening|the \d)", re.I)


def examples() -> "list[tuple[str, list]]":
    """Pull (command, items) pairs straight out of the shipped prompt text."""
    out, pending = [], None
    for line in llmseg._EXAMPLES.splitlines():
        line = line.strip()
        if line.startswith('"') and line.endswith('"'):
            pending = line[1:-1]
        elif line.startswith("{") and pending is not None:
            blob = json.loads(line)
            out.append((pending, [{"action": v[0], "time": v[1], "tag": v[2]}
                                  for v in blob.values()]))
            pending = None
    return out


def main() -> int:
    rows = examples()
    print(f"{len(rows)} examples in the shipped prompt\n")
    bad = 0

    for text, items in rows:
        problems = []

        for it in items:
            if it["tag"] not in llmseg.TAGS:
                problems.append(f"tag {it['tag']!r} is not one of {llmseg.TAGS}")

        problems += invariant.violations(text, items)

        for i, it in enumerate(items, 1):
            t = it["time"]
            has_clock = bool(re.search(r"\d|noon|midnight", t))
            has_day = bool(_DAY.search(t))
            if has_clock and not has_day:
                problems.append(
                    f"item {i} time {t!r} has a clock but no day — the DATE "
                    f"FLOOR requires 'today {t}'")
            if re.search(r"\b\d{4}-\d{2}-\d{2}\b", t):
                problems.append(f"item {i} time {t!r} is RESOLVED, not captured")

        # The preposition the speaker used must survive into `time`.
        for i, it in enumerate(items, 1):
            for ref in find_time_refs(text):
                core = ref.text.split()[-1]
                if core in it["time"] and ref.text not in it["time"]:
                    if re.match(r"^(at|on|for|by|from|until|through)\b", ref.text):
                        problems.append(
                            f"item {i} time {it['time']!r} dropped the "
                            f"preposition from {ref.text!r}")

        if problems:
            bad += 1
            print(f"  FAIL  {text!r}")
            for p in dict.fromkeys(problems):
                print(f"          {p}")
        else:
            print(f"  ok    {text!r}")

    # Disagreements with FastSeg are reported, not failed: the prompt may
    # legitimately teach something FastSeg cannot yet do (that is the point of
    # having a model). But an unexplained disagreement is worth seeing.
    print("\nWhere FastSeg disagrees with the prompt (not necessarily a bug):")
    for text, items in rows:
        got = fastseg(text)
        want = [(i["action"], i["time"], i["tag"]) for i in items]
        mine = [(i["action"], i["time"], i["tag"]) for i in got]
        if want != mine:
            print(f"  {text!r}")
            print(f"     prompt : {want}")
            print(f"     fastseg: {mine}")

    print(f"\n{'FAILED' if bad else 'PASSED'} — {bad} of {len(rows)} examples "
          f"contradict the spec")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
