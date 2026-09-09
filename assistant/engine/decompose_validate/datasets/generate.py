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
import collections
import hashlib
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

#: The ORIGINAL families' banks, read-only. Editing this file would reshuffle
#: FastRule's own 7,200-row split (see engine/TRAIN_TEST_SPLIT_CONVENTION.md) and
#: would change which filler every existing row here draws.
_BANKS = os.path.join(_ROOT, "assistant", "engine", "fastrule", "datasets", "banks")

#: This stage's OWN banks: the grown filler pools and the new families.
_GROWN = os.path.join(_HERE, "banks")

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

#: Additional anchors, used by the GROWN families only. The original five are
#: untouched on purpose: widening the list would change which anchor each
#: existing row gets (`ANCHORS[n % len(ANCHORS)]`), and the 795 rows the resolver
#: was measured on would silently become different rows.
#:
#: Chosen for the arithmetic they break, not for variety — a leap day, a year
#: end and start, a 31st, two month ends, and the five weekdays the original
#: anchors do not cover at all (they are Tue/Sun/Wed/Sun/Thu, so a Monday,
#: Friday or Saturday anchor never occurred).
GROWN_ANCHORS = ANCHORS + [
    dt.date(2028, 2, 29),   # leap day
    dt.date(2026, 12, 31),  # year end
    dt.date(2027, 1, 1),    # year start
    dt.date(2026, 10, 31),  # a 31st
    dt.date(2026, 11, 30),  # month end of a 30-day month
    dt.date(2027, 3, 1),    # month start
    dt.date(2026, 9, 11),   # Friday
    dt.date(2026, 9, 12),   # Saturday
    dt.date(2026, 9, 14),   # Monday
    dt.date(2026, 9, 16),   # Wednesday
    dt.date(2026, 9, 17),   # Thursday
]

#: Fraction of the GROWN families held out. The original families cannot be
#: held out at any fraction -- the resolver was tuned until it scored 100% on
#: them, so they measure memorisation and nothing else.
TEST_FRAC = 0.4

#: Renders per grown family. The original families keep 3; these get more
#: because the point of the growth is coverage and the board costs nothing to
#: run (0 model calls, 0.000 s/row).
GROWN_PER_FAMILY = 40

_SLOT = re.compile(r"\{(\w+)\}")

#: WHICH END OF THE RANGE a date filler names. The gold used to file every date
#: slot as the START, so "every tuesday and thursday until the 21st" was born
#: with date=2026-09-21 -- a MONDAY, neither of the days it names. The
#: preposition in front of the filler is what distinguishes them.
_ROLE = re.compile(r"\b(until|till|up to|through|thru|including|starting|"
                   r"beginning|begins)\b\s*$", re.I)
_EXCLUSIVE = ("until", "till", "up to")


def _role_of(time_str: str, raw: str) -> str:
    """"start" | "until" | "through" | "plain" for one date filler."""
    i = time_str.lower().find((raw or "").lower())
    if i < 0:
        return "plain"
    m = _ROLE.search(time_str[:i])
    if not m:
        return "plain"
    w = m.group(1).lower()
    return ("until" if w in _EXCLUSIVE
            else "through" if w in ("through", "thru", "including") else "start")


_WEEKDAY_NUM = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                "friday": 4, "saturday": 5, "sunday": 6}


def _norm_for(slot: str, value: str, anchor: dt.date, transcript: str = ""):
    """The normalized meaning of ONE filled slot, or N.AMBIGUOUS / None."""
    base = slot.rstrip("23")
    if base in ("date", "query_range"):
        return N.resolve_date(value, anchor)
    if base == "time":
        return N.resolve_time(value, transcript)   # `transcript` is the item's own
                                                   # words here; see _gold_item
    if base == "time_range":
        return N.TIME_RANGES.get(value.strip().lower())
    if base == "recurrence":
        return N.RECURRENCES.get(value.strip().lower())
    if base == "lead_time":
        return N.LEAD_TIMES.get(value.strip().lower())
    if base == "qty":
        return N.QUANTITIES.get(value.strip().lower())
    if base == "event_duration":
        return N.DURATIONS.get(value.strip().lower())
    return None


def _incoherent(item: dict) -> bool:
    """True when the gold contradicts itself, so the row must not be emitted."""
    start, until = item.get("date"), item.get("recur_until")
    if start and until and until < start:
        return True                       # ends before it begins
    days = item.get("recur_days") or []
    if start and days:
        wd = ("monday", "tuesday", "wednesday", "thursday", "friday",
              "saturday", "sunday")[dt.date.fromisoformat(start).weekday()]
        if wd not in days:
            return True                   # starts on a day it never names
    return False


def _gold_item(spec: dict, binding: dict, anchor: dt.date, transcript: str = "") -> "dict | None":
    """One derived item + its fillers -> the COMPLETE gold item.

    Returns None when any slot this item uses is AMBIGUOUS — the row is then
    dropped whole, because a half-normalized item would teach a wrong value.
    """
    item = {"kind": spec["tag"],
            "text": SEG._fill(spec["action"], binding),
            "time": SEG._fill(spec["time"], binding),
            "date": None, "start_time": None, "end_time": None,
            "recurrence": None, "recurrence_rounded": False, "recur_until": None,
            "quantity": None, "reminder_minutes": None}

    # The DATE FLOOR (segmentation's SPEC): an item with no day of its own is
    # today. Applied here too, so the two stages cannot disagree about it.
    saw_day = False

    for slot in _SLOT.findall(spec["time"]) + _SLOT.findall(spec["action"]):
        raw = binding.get(slot)
        if raw is None:
            continue
        # THE ITEM'S OWN WORDS, not the row's. A bare hour reads evening words
        # from the item that spoke it -- a neighbour's "4pm" must not move it.
        got = _norm_for(slot, raw, anchor,
                        f"{item['time']} {item['text']}")
        if got is None:
            # A slot that SHOULD normalize but did not is a hole in the table,
            # and emitting the item anyway would put `None` in gold — teaching
            # "no time was said" for a sentence that says one. Drop the row and
            # let --report name the filler, the same treatment as AMBIGUOUS.
            if slot.rstrip("23") in ("date", "query_range", "time", "time_range",
                                     "recurrence", "lead_time", "qty",
                                     "event_duration"):
                return None
            continue
        if got is N.AMBIGUOUS:
            return None
        base = slot.rstrip("23")
        if base in ("date", "query_range"):
            iso, hint = got
            role = _role_of(item["time"], raw)
            if role in ("until", "through"):
                d = dt.date.fromisoformat(iso)
                # until EXCLUDES the day it names, through/including keep it
                item["recur_until"] = (d - dt.timedelta(days=1)).isoformat() \
                    if role == "until" else iso
            else:
                item["date"] = iso
                saw_day = True
            if hint and not item["start_time"]:
                item["_part_of_day"] = hint
        elif base == "time":
            item["start_time"] = got
            win = N.window(raw)
            if win:                       # a coarse part of day sets its END too
                item["end_time"] = win[1]
        elif base == "time_range":
            item["start_time"], item["end_time"] = got
        elif base == "recurrence":
            cadence, weekday = got
            item["recurrence"] = cadence
            item["recurrence_rounded"] = raw.strip().lower() in N.ROUNDED
            if weekday:
                item["recurrence_weekday"] = weekday
            # A SERIES STILL NEEDS A FIRST INSTANCE. Marking saw_day without
            # setting a date left "every month at 11am" with date=None, which
            # is not a bookable event -- and taught the resolver that a
            # recurrence means no date. It starts on the first named weekday,
            # or on the anchor when the cadence names no day.
            days = weekday if isinstance(weekday, list) else ([weekday] if weekday else [])
            if item["date"]:
                pass                      # an explicit start already named it
            elif days:
                first = min(
                    anchor + dt.timedelta(days=(_WEEKDAY_NUM[d] - anchor.weekday()) % 7)
                    for d in days)
                item["date"] = first.isoformat()
                item["recur_days"] = days
            else:
                item["date"] = anchor.isoformat()
            if days:
                item["recur_days"] = days
            saw_day = True
        elif base == "lead_time":
            item["reminder_minutes"] = got
        elif base == "qty":
            item["quantity"] = got
        elif base == "event_duration":
            # A LENGTH, so it sets the END from the start. With no start there
            # is nothing to add it to, and inventing one would invent the event.
            if item["start_time"] and not item["end_time"]:
                h, mi = (int(x) for x in item["start_time"].split(":"))
                total = h * 60 + mi + got
                item["end_time"] = f"{total // 60 % 24:02d}:{total % 60:02d}"

    if not saw_day:
        item["date"] = anchor.isoformat()      # the floor
    return item


def stratified_split(families: list, seed: int) -> dict:
    """family -> "train" | "test", stratified by nuance.

    Mirrors `engine/TRAIN_TEST_SPLIT_CONVENTION.md`, for the same reason it gives:
    a global fraction could by chance put every `series_bound` family on one
    side, and that slice would then silently stop being measured. Ordering is a
    stable hash so the assignment does not depend on file order or
    PYTHONHASHSEED, and every bucket keeps at least one family on each side.
    """
    buckets = collections.defaultdict(list)
    for t in families:
        buckets[t.get("nuance", "?")].append(t["family"])
    out = {}
    for nuance, fams in sorted(buckets.items()):
        ordered = sorted(fams, key=lambda f: hashlib.sha256(
            f"{seed}:split:{nuance}:{f}".encode()).hexdigest())
        n_test = min(max(1, round(TEST_FRAC * len(ordered))), len(ordered) - 1) \
            if len(ordered) > 1 else 0
        for i, f in enumerate(ordered):
            out[f] = "test" if i < n_test else "train"
    return out


def _emit(templates, banks, anchors, per_template, seed, split_of, rows, dropped):
    """Render one family set. Byte-identical to the original loop for the
    original inputs — the only addition to a row is its `split`."""
    for t in templates:
        if t["action"] == "propose":
            dropped.append((t["family"], "action=propose"))
            continue
        spec = SEG.derive(t)
        if spec is None:
            dropped.append((t["family"], "underivable"))
            continue
        rng = random.Random(f"{seed}:{t['family']}")
        made, why, seen = 0, "", set()
        for n in range(per_template * 6):
            if made >= per_template:
                break
            anchor = anchors[n % len(anchors)]
            binding = SEG._bind(t["template"], banks, rng)
            if not binding and _SLOT.search(t["template"]):
                why = "unknown slot"
                break
            text = SEG._fill(t["template"], binding)
            if (text, anchor) in seen:
                continue                      # same render on the same anchor
            gold = [_gold_item(s, binding, anchor, text) for s in spec]
            if any(g is None for g in gold):
                why = "an ambiguous filler"
                continue
            if any(_incoherent(g) for g in gold):
                why = "cadence contradicts its bound"
                continue
            seen.add((text, anchor))
            rows.append({"id": f"dv_{t['family']}_{n}", "text": text,
                         "today": anchor.isoformat(), "gold": gold,
                         "traps": [t["nuance"]], "family": t["family"],
                         "source": "generated",
                         "split": split_of(t["family"])})
            made += 1
        if not made:
            dropped.append((t["family"], why or "no valid render"))


def build(per_template: int = 3, seed: int = 20260908):
    """The whole dataset: original families (train only) + grown families (split).

    Two family sets, two filler banks, two anchor lists — deliberately, and the
    reason is the leakage rule. The ORIGINAL families were fitted against until
    the board read 100%, so no slice of them can measure generalisation; they are
    train by construction, not by assignment. Everything held out comes from
    families the resolver has never seen.
    """
    base_banks = json.load(open(os.path.join(_BANKS, "fillers.json")))
    base_templates = json.load(open(os.path.join(_BANKS, "complex_patterns.json")))
    grown_banks = dict(base_banks)
    grown_banks.update({k: v for k, v in
                        json.load(open(os.path.join(_GROWN, "grown_fillers.json"))).items()
                        if not k.startswith("_")})
    grown_templates = json.load(open(os.path.join(_GROWN, "grown_patterns.json")))

    base_families = {t["family"] for t in base_templates}
    grown_families = {t["family"] for t in grown_templates}
    clash = base_families & grown_families
    if clash:
        raise ValueError(f"a grown family reuses an original name: {sorted(clash)}")

    assigned = stratified_split(grown_templates, seed)

    rows, dropped = [], []
    _emit(base_templates, base_banks, ANCHORS, per_template, seed,
          lambda f: "train", rows, dropped)
    _emit(grown_templates, grown_banks, GROWN_ANCHORS, GROWN_PER_FAMILY, seed,
          assigned.get, rows, dropped)

    # --- the guards. Each of these has to hold or the split is not a split.
    per_family = collections.defaultdict(set)
    for r in rows:
        per_family[r["family"]].add(r["split"])
    leaked = sorted(f for f, sp in per_family.items() if len(sp) > 1)
    if leaked:
        raise ValueError(f"families in BOTH splits: {leaked}")

    original_test = sorted(f for f, sp in per_family.items()
                           if f in base_families and sp != {"train"})
    if original_test:
        raise ValueError(f"an original family reached test: {original_test}")
    return rows, dropped


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-template", type=int, default=3)
    ap.add_argument("--out", default=os.path.join(_HERE, "generated.jsonl"))
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--accept-gold-change", action="store_true",
                    help="permit rows to keep their text while their GOLD moves. "
                         "Only for a deliberate correction to normalization.py — "
                         "it is otherwise the signature of an accident.")
    a = ap.parse_args()

    rows, dropped = build(a.per_template)

    # TRAIN-INVARIANCE. The original rows' text, anchor and gold must be what
    # they were before the growth, or the 100% board stops being comparable and
    # the growth has quietly moved the goalposts. A `split` field was added to
    # every row, so the check is on content, not on the whole line.
    old = {}
    if os.path.exists(a.out):
        for line in open(a.out):
            r = json.loads(line)
            old[r["id"]] = json.dumps([r["text"], r["today"], r["gold"]],
                                      sort_keys=True)
    changed = [r["id"] for r in rows
               if r["id"] in old and json.dumps(
                   [r["text"], r["today"], r["gold"]], sort_keys=True) != old[r["id"]]]
    missing = sorted(set(old) - {r["id"] for r in rows})

    by_split = collections.Counter(r["split"] for r in rows)
    fam_split = {}
    for r in rows:
        fam_split[r["family"]] = r["split"]
    fam_counts = collections.Counter(fam_split.values())
    print(f"wrote {len(rows)} rows from {len(fam_split)} families")
    print(f"   train  {by_split['train']:5d} rows   {fam_counts['train']:4d} families")
    print(f"   test   {by_split['test']:5d} rows   {fam_counts['test']:4d} families"
          f"   ({100 * by_split['test'] / max(1, len(rows)):.1f}% of rows)")
    print(f"   items:   {sum(len(r['gold']) for r in rows)}")
    print(f"   leaked families: 0 (asserted in build)")
    # A DRIFT GUARD between runs, not a proof about the pre-growth set: it
    # compares against whatever generated.jsonl currently holds, so once written
    # it is comparing the file to itself. The one-time pre-growth comparison
    # (717 identical, 78 replaced) is recorded in ARCHITECTURE.md instead.
    #
    # A replaced row is NOT a failure and must not print like one. Improving a
    # gold value changes which renders are emittable: de-ambiguating "the end of
    # the month" let renders through that every {date} family used to skip, so
    # those families accept a different three. Same families, same constructions,
    # different fillers. What WOULD be a failure is a row whose text and anchor
    # are unchanged but whose GOLD moved — that is `changed`, and it is fatal.
    if changed and not a.accept_gold_change:
        raise ValueError(
            f"{len(changed)} rows kept their text but changed gold, e.g. "
            f"{changed[:5]}. If that is deliberate (a correction to "
            f"normalization.py), re-run with --accept-gold-change; if not, it is "
            f"an accident and the gold has drifted under the resolver.")
    if changed:
        print(f"   ACCEPTED: {len(changed)} rows kept their text and their gold "
              f"moved — a deliberate gold correction")

    if not a.no_write:
        with open(a.out, "w") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")

    if old:
        print(f"   drift guard: {len(old) - len(missing)} rows identical to the "
              f"previous run, {len(missing)} replaced, 0 with moved gold")
    print(f"   normalization coverage: {N.coverage()}")

    if a.report:
        print("\n   by nuance (the stratification buckets)")
        buckets = collections.defaultdict(collections.Counter)
        for r in rows:
            buckets[r["traps"][0]][r["split"]] += 1
        for nuance in sorted(buckets):
            c = buckets[nuance]
            print(f"      {nuance:24s} train {c['train']:5d}   test {c['test']:5d}")
        print("\n   by anchor")
        for anc, n in sorted(collections.Counter(r["today"] for r in rows).items()):
            print(f"      {anc}  {n:5d}")
        print(f"\n   dropped {len(dropped)} families (nothing guessed)")
        for why, n in collections.Counter(w for _f, w in dropped).most_common():
            print(f"      {n:3d}  {why}")


if __name__ == "__main__":
    main()
