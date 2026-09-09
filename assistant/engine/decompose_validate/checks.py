"""validate — the second half of the stage. Compare, repair what is provable,
flag the rest. Never refuse.

    run(items, transcript, anchor) -> (items, [Fix], [Flag])

WHAT VALIDATE CAN DO THAT NOTHING ELSE CAN
Segmentation holds the WORDS and never resolves them. decompose holds one item's
words and produces a VALUE. **Validate is the only stage holding both the words
and the value**, so it is the only one that can check them against each other.
That is its entire reason to exist, and every rule below is an instance of it.

THE PROVABLE REPAIR
An item may arrive with values from somewhere other than `resolve.py` — the LLM
judge, FastRule's partial parse, a rewritten retry. So the repair that is always
available is: read the item's own words again, and where they NAME a value that
contradicts what the item holds, **the words win**.

Two guards keep that from being destructive:

  1. If the words name NOTHING, the existing value stands. Silence is not
     evidence, and overwriting a value the resolver merely cannot parse would
     destroy information a better producer supplied.
  2. Only the fields the words actually speak to are touched. A rule that
     rewrites everything scores perfectly against a broken item and terribly
     against a correct one, which is what board G's BROKE column exists to catch.

FIX versus FLAG
A rule FIXES only what it can prove. Where the disagreement is real but which
side is wrong is unknowable — a series whose end precedes its start could have
either end mistaken — it FLAGS instead.

**Flags never block** (Gil, 2026-09-08). A blocked item is a command that
silently did nothing; a flagged one is committed with a note the speaker can see
and act on. That is the whole change from the old `_observance_verdict`, which
refused.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import re

from assistant.engine.decompose_validate import resolve as R

#: Fields validate may repair from the words, and the resolver key each reads.
_FROM_TIME = ("date", "start_time", "end_time", "recurrence", "recur_until")

_WEEKDAY = ("monday", "tuesday", "wednesday", "thursday", "friday",
            "saturday", "sunday")

#: Phrases with no agreed value, so nothing can resolve them. The speaker said
#: something real and the engine has no ruling, which is a FLAG rather than a
#: silent drop — see ARCHITECTURE.md's open questions.
_NO_RULING = re.compile(
    r"\b(next week|next month|this weekend|the next few days|the rest of the day"
    r"|early evening|around lunchtime|first thing in the morning"
    r"|every year|annually|yearly)\b")


@dataclasses.dataclass
class Fix:
    """A repair that was applied. Lands in the trace and in board G."""
    rule: str
    field: str
    was: object
    now: object
    why: str


@dataclasses.dataclass
class Flag:
    """A doubt that was NOT repaired. Carried to commit, which notifies."""
    rule: str
    why: str
    field: str = ""


def _words(item: dict, transcript: str, anchor: dt.date) -> dict:
    """What this item's OWN words say, ignoring what it currently holds.

    THE CONTEXT IS THE ITEM, NOT THE TRANSCRIPT. The bare-hour convention reads
    evening words from the sentence, and the only sentence that can speak for an
    item is its own: in "team meeting from 3 to 4pm and budget review at quarter
    to nine" the 4pm belongs to the meeting, and letting it decide the budget
    review's hour would charge an item for a neighbour's words.

    `transcript` is still a parameter — validate is the stage that HOLDS the
    transcript, and the honoured check needs it — but it is deliberately not what
    grounds a value.
    """
    said = item.get("time") or ""
    own = f"{said} {item.get('text') or ''}".strip()
    return R.resolve(said, anchor, own, action=item.get("text") or "")


# ---------------------------------------------------------------------------
# The rules. Ordered: agreement first (it establishes values), then
# completeness, then cross-field arithmetic, then the flags.
# ---------------------------------------------------------------------------

def agree_with_words(item, said, transcript, anchor, fixes, flags):
    """Where the words NAME a value and the item disagrees, the words win."""
    for field in _FROM_TIME:
        want = said.get(field)
        if want is None:
            continue                       # silence is not evidence — guard 1
        if field == "date" and said.get("date_floored"):
            # The floor is a DEFAULT, not something the speaker said. Treating it
            # as evidence reset every unspoken date to today, which is guard 1
            # being violated by the one field that always has an answer.
            # `date_floor` below fills a MISSING date; it does not overwrite one.
            continue
        have = item.get(field)
        if str(have) != str(want):
            fixes.append(Fix("agree_with_words", field, have, want,
                             f"the words say {item.get('time')!r}"))
            item[field] = want


def agree_on_counts(item, said, transcript, anchor, fixes, flags):
    """Quantity and lead time are spoken in the ACTION, so they are read there."""
    # SEPARATELY, never concatenated. Joining time and action put the action's
    # words directly after "prior"/"before", and the lead-time reader correctly
    # refuses a lead time whose tail names something else -- so "two days prior"
    # + "call the plumber" read as a relation to the plumber and repaired nothing.
    for field, fn, sources in (
            ("quantity", R.resolve_quantity, (item.get("text") or "",)),
            ("reminder_minutes", R.resolve_lead_time,
             (item.get("time") or "", item.get("text") or ""))):
        want = next((v for v in (fn(src) for src in sources) if v is not None), None)
        source = " / ".join(x for x in sources if x)
        if want is None:
            continue
        if str(item.get(field)) != str(want):
            fixes.append(Fix("agree_on_counts", field, item.get(field), want,
                             f"the words say {source.strip()!r}"))
            item[field] = want


def date_floor(item, said, transcript, anchor, fixes, flags):
    """THE DATE FLOOR: an item with no day of its own is today.

    Unconditional, because that is how the convention is stated — not "a clock
    with no day", which is what this rule checked at first and which left an item
    with neither a day nor a clock holding no date at all, so nothing could be
    built from it.

    Deliberately NOT the reverse: a day with no clock is perfectly normal and must
    never acquire an invented time. The floor applies to the DAY only.
    """
    if not item.get("date"):
        fixes.append(Fix("date_floor", "date", None, anchor.isoformat(),
                         "a clock with no day defaults to today"))
        item["date"] = anchor.isoformat()


def series_starts_on_a_named_day(item, said, transcript, anchor, fixes, flags):
    """A weekly series must begin on a day it actually names (CLAUDE.md).

    "every tuesday and thursday" cannot open on a Wednesday. Advancing is
    provable, so this fixes rather than flags.
    """
    days = item.get("recur_days") or []
    date = item.get("date")
    if not (days and date):
        return
    try:
        d0 = dt.date.fromisoformat(date)
    except (TypeError, ValueError):
        return
    if _WEEKDAY[d0.weekday()] in days:
        return
    soonest = min(d0 + dt.timedelta(days=(_WEEKDAY.index(x) - d0.weekday()) % 7)
                  for x in days if x in _WEEKDAY)
    fixes.append(Fix("series_starts_on_a_named_day", "date", date,
                     soonest.isoformat(),
                     f"a weekly series on {sorted(days)} cannot start on a "
                     f"{_WEEKDAY[d0.weekday()]}"))
    item["date"] = soonest.isoformat()


def end_after_start(item, said, transcript, anchor, fixes, flags):
    """An end at or before the start is impossible.

    ONE repair is provable: a bare end hour read as morning when the start is
    afternoon — "from 3 to 4" where the 4 became 04:00. Adding twelve hours is
    the bare-hour convention finishing its own job. Anything else is a genuine
    contradiction whose wrong half is unknowable, so it flags.
    """
    start, end = item.get("start_time"), item.get("end_time")
    if not (start and end) or end > start:
        return
    h, mi = (int(x) for x in end.split(":"))
    if h < 12:
        bumped = f"{h + 12:02d}:{mi:02d}"
        if bumped > start:
            fixes.append(Fix("end_after_start", "end_time", end, bumped,
                             "a bare end hour before the start reads as pm"))
            item["end_time"] = bumped
            return
    flags.append(Flag("end_after_start",
                      f"ends {end} but starts {start}", "end_time"))


def until_after_start(item, said, transcript, anchor, fixes, flags):
    """A series that ends before it begins has no instances.

    NOT repairable: either the bound or the start could be the mistaken one, and
    guessing would either book a series nobody asked for or drop one they did.
    """
    date, until = item.get("date"), item.get("recur_until")
    if date and until and str(until) < str(date):
        flags.append(Flag("until_after_start",
                          f"the series ends {until} but starts {date}, so it "
                          f"has no dates at all", "recur_until"))


def until_needs_recurrence(item, said, transcript, anchor, fixes, flags):
    """An end bound with no series to bound.

    The bound is kept rather than dropped: it is something the speaker said, and
    deleting it would lose information the reply should mention.
    """
    if item.get("recur_until") and not item.get("recurrence"):
        flags.append(Flag("until_needs_recurrence",
                          f"{item['recur_until']} bounds a series, but no "
                          f"recurrence was found", "recurrence"))


def every_phrase_honoured(item, said, transcript, anchor, fixes, flags):
    """The value-level analogue of segmentation's no-loss invariant.

    Segmentation guarantees no WORD is lost; validate guarantees no word went
    UNHONOURED. A phrase the engine has no ruling for is the honest case to
    surface — the speaker named something real and nothing carries it.
    """
    m = _NO_RULING.search(f"{item.get('time') or ''} {item.get('text') or ''}".lower())
    if m:
        flags.append(Flag("every_phrase_honoured",
                          f"{m.group(0)!r} has no agreed value, so nothing "
                          f"carries it"))


def observance(item, said, transcript, anchor, fixes, flags):
    """A one-off the ASSISTANT created, landing inside Shabbat or yom tov.

    Reuses `db._skip_for_observance`, which is already sundown-bounded and already
    holds every exception — meals allowed because they are what the day is for,
    inverted on a fast, Yom Kippur resolved as a fast. Reimplementing it here
    would be a second copy to drift.

    Two deliberate limits: it only looks at ONE-OFFS (a series' own skipping is
    `db`'s job and is untouched), and if observance cannot be computed it says
    NOTHING — a quiet flag is better than a wrong one, the same rule the series
    logic follows.
    """
    if item.get("recurrence") or not item.get("date"):
        return
    try:
        from assistant import db
        when = dt.date.fromisoformat(item["date"])
        if db._skip_for_observance(when, item.get("start_time") or "",
                                  item.get("text") or "", ""):
            flags.append(Flag("observance",
                              f"{item['date']} falls inside Shabbat or yom tov "
                              f"and this is not leyning, a meal or davening",
                              "date"))
    except Exception:
        return                             # cannot compute -> say nothing


#: The pipeline. Order is load-bearing: agreement establishes the values that
#: completeness and arithmetic then reason about.
RULES = (agree_with_words, agree_on_counts, date_floor,
         series_starts_on_a_named_day, end_after_start, until_after_start,
         until_needs_recurrence, every_phrase_honoured, observance)


def run(items: list, transcript: str, anchor: dt.date):
    """The stage's validate half. Returns (items, fixes, flags).

    Items are COPIED, so a caller can compare before against after — which is
    what board G does, and the only way to see a repair that broke something.
    """
    out, fixes, flags = [], [], []
    for item in items:
        fresh = dict(item)
        said = _words(fresh, transcript, anchor)
        for rule in RULES:
            rule(fresh, said, transcript, anchor, fixes, flags)
        out.append(fresh)
    return out, fixes, flags
