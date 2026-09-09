"""Build the decompose_validate dataset: (X1, anchor) -> the COMPLETE items.

Reuses segmentation's template derivation rather than re-deriving it. That
matters for more than effort: the two stages then agree BY CONSTRUCTION about
where an item's boundaries are and which time belongs to it, so a
decompose_validate score can never be quietly measuring a segmentation
disagreement.

    segmentation.derive(t)  ->  per-item (action, time, tag) as TEMPLATES
    _bind(...)              ->  which filler filled each slot
    normalization.py        ->  what that filler MEANS, hand-written
    here                    ->  compose the gold item

Nothing in `assistant/engine/` is consulted for a VALUE. The resolver under test
never touches the gold.

    python -m assistant.engine.decompose_validate.datasets.generate --report
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
# datasets/ -> decompose_validate/ -> engine/ -> assistant/ -> repo root
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from assistant.engine.decompose_validate.datasets import normalization as N  # noqa: E402
from assistant.engine.segmentation.experiments import generate as SEG        # noqa: E402

_BANKS = os.path.join(_ROOT, "assistant", "engine", "fastrule", "datasets", "banks")

#: Several anchors, chosen to make the resolver's hard cases REACHABLE rather
#: than hoping they turn up: a mid-month Tuesday, a Sunday past the 15th (so
#: "the 15th" must roll a month), a month end, and December (so "the 15th" and
#: christmas must roll the YEAR).
ANCHORS = [
    dt.date(2026, 9, 8),    # Tuesday, before the 15th
    dt.date(2026, 9, 20),   # Sunday, AFTER the 15th — rolls a month
    dt.date(2026, 9, 30),   # month end
    dt.date(2026, 12, 20),  # December — rolls the year
    dt.date(2026, 2, 26),   # short month
]

_SLOT = re.compile(r"\{(\w+)\}")


def _norm_for(slot: str, value: str, anchor: dt.date, transcript: str = ""):
    """The normalized meaning of ONE filled slot, or N.AMBIGUOUS / None."""
    base = slot.rstrip("23")
    if base in ("date", "query_range"):
        return N.resolve_date(value, anchor)
    if base == "time":
        return N.resolve_time(value, transcript)
    if base == "time_range":
        return N.TIME_RANGES.get(value.strip().lower())
    if base == "recurrence":
        return N.RECURRENCES.get(value.strip().lower())
    if base == "lead_time":
        return N.LEAD_TIMES.get(value.strip().lower())
    if base == "qty":
        return N.QUANTITIES.get(value.strip().lower())
    return None


def _gold_item(spec: dict, binding: dict, anchor: dt.date, transcript: str = "") -> "dict | None":
    """One derived item + its fillers -> the COMPLETE gold item.

    Returns None when any slot this item uses is AMBIGUOUS — the row is then
    dropped whole, because a half-normalized item would teach a wrong value.
    """
    item = {"kind": spec["tag"],
            "text": SEG._fill(spec["action"], binding),
            "time": SEG._fill(spec["time"], binding),
            "date": None, "start_time": None, "end_time": None,
            "recurrence": None, "recurrence_rounded": False,
            "quantity": None, "reminder_minutes": None}

    # The DATE FLOOR (segmentation's SPEC): an item with no day of its own is
    # today. Applied here too, so the two stages cannot disagree about it.
    saw_day = False

    for slot in _SLOT.findall(spec["time"]) + _SLOT.findall(spec["action"]):
        raw = binding.get(slot)
        if raw is None:
            continue
        got = _norm_for(slot, raw, anchor, transcript)
        if got is None:
            continue
        if got is N.AMBIGUOUS:
            return None
        base = slot.rstrip("23")
        if base in ("date", "query_range"):
            iso, hint = got
            item["date"] = iso
            saw_day = True
            if hint and not item["start_time"]:
                item[f"_part_of_day"] = hint
        elif base == "time":
            item["start_time"] = got
        elif base == "time_range":
            item["start_time"], item["end_time"] = got
        elif base == "recurrence":
            cadence, weekday = got
            item["recurrence"] = cadence
            item["recurrence_rounded"] = raw.strip().lower() in N.ROUNDED
            if weekday:
                item["recurrence_weekday"] = weekday
            saw_day = True
        elif base == "lead_time":
            item["reminder_minutes"] = got
        elif base == "qty":
            item["quantity"] = got

    if not saw_day:
        item["date"] = anchor.isoformat()      # the floor
    return item


def build(per_template: int = 3, seed: int = 20260908):
    banks = json.load(open(os.path.join(_BANKS, "fillers.json")))
    templates = json.load(open(os.path.join(_BANKS, "complex_patterns.json")))
    rows, dropped = [], []

    for t in templates:
        if t["action"] == "propose":
            dropped.append((t["family"], "action=propose"))
            continue
        spec = SEG.derive(t)
        if spec is None:
            dropped.append((t["family"], "underivable"))
            continue
        rng = random.Random(f"{seed}:{t['family']}")
        made = 0
        why = ""
        for n in range(per_template * 4):
            if made >= per_template:
                break
            anchor = ANCHORS[n % len(ANCHORS)]
            binding = SEG._bind(t["template"], banks, rng)
            if not binding and _SLOT.search(t["template"]):
                why = "unknown slot"
                break
            text = SEG._fill(t["template"], binding)
            gold = [_gold_item(s, binding, anchor, text) for s in spec]
            if any(g is None for g in gold):
                why = "an ambiguous filler"
                continue
            rows.append({"id": f"dv_{t['family']}_{n}", "text": text,
                         "today": anchor.isoformat(), "gold": gold,
                         "traps": [t["nuance"]], "family": t["family"],
                         "source": "generated"})
            made += 1
        if not made:
            dropped.append((t["family"], why or "no valid render"))
    return rows, dropped


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-template", type=int, default=3)
    ap.add_argument("--out", default=os.path.join(_HERE, "generated.jsonl"))
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()

    rows, dropped = build(a.per_template)
    with open(a.out, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")

    import collections
    print(f"wrote {len(rows)} rows from {len({r['family'] for r in rows})} families")
    print(f"   anchors: {dict(collections.Counter(r['today'] for r in rows))}")
    print(f"   items:   {sum(len(r['gold']) for r in rows)}")
    print(f"   dropped {len(dropped)} families (nothing guessed)")
    print(f"   normalization coverage: {N.coverage()}")
    if a.report:
        for why, n in collections.Counter(w for _f, w in dropped).most_common():
            print(f"      {n:3d}  {why}")


if __name__ == "__main__":
    main()
