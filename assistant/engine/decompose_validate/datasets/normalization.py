"""The GOLD source of truth: every filler value, normalized by hand, once.

This is the file that makes the dataset non-circular. Segmentation's dataset
could be built from the templates because the templates NAME their slots. That
trick does not carry here: decompose_validate is judged on RESOLVED values, and
resolving is the very thing under test — deriving gold by running the resolver
would be marking its own homework.

The way out is that the filler banks are small and CLOSED: 30 dates, 20 times,
15 recurrences, 7 ranges, 8 lead times, 15 quantities. So each is normalized
here, by hand, as a function of the anchor. The generator then composes an
item's gold from these, and nothing in `assistant/engine/` is consulted.

ANCHORING (ISO-TimeML / TempEval-3). A relative expression has no value without
a reference point — "tomorrow" is only a date once you say when it was spoken.
TIMEX3 calls it the document creation time; every row here carries its own
`today`, so gold is absolute, reproducible forever, and the same text under two
anchors is two different (and both correct) rows. That is deliberate coverage,
not duplication: "the 15th" on the 8th and on the 20th resolve to different
months, and only an anchored dataset can test it.

WHERE A VALUE IS GENUINELY AMBIGUOUS it is marked `AMBIGUOUS` rather than
guessed, and the generator skips those rows. A dataset that quietly picks one
reading teaches that reading as fact.
"""
from __future__ import annotations

import datetime as dt
import re

#: Marks a filler whose normalization is a product decision we have not made.
#: Rows using it are EXCLUDED and reported, never guessed at.
AMBIGUOUS = object()

_WEEKDAY = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6}


def _coming(anchor: dt.date, name: str) -> dt.date:
    """The soonest `name`, today counting as today (the project's rule)."""
    return anchor + dt.timedelta(days=(_WEEKDAY[name] - anchor.weekday()) % 7)


def _next_week(anchor: dt.date, name: str) -> dt.date:
    """That weekday in the NEXT calendar week — `validate.relative_dates`'
    documented reading of "next tuesday", and the one the engine ships."""
    return anchor + dt.timedelta(days=(7 - anchor.weekday()) + _WEEKDAY[name])


_MONTH = {m: i for i, m in enumerate(
    ("january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"), start=1)}


def _days_in(year: int, month: int) -> int:
    nxt = dt.date(year + month // 12, month % 12 + 1, 1)
    return (nxt - dt.date(year, month, 1)).days


def _month_ordinal(anchor: dt.date, month: int, day: int) -> dt.date:
    """A NAMED month is honoured exactly, rolling the YEAR if it has passed.

    The distinction from `_month_day` is the whole point of §8.2 and of the live
    bug in `a987aba`: "the 20th of November" is November even when that means
    next year, and only a BARE ordinal may roll month by month.
    """
    for year in (anchor.year, anchor.year + 1):
        cand = dt.date(year, month, min(day, _days_in(year, month)))
        if cand >= anchor:
            return cand
    raise ValueError((month, day))


def _add_months(anchor: dt.date, n: int) -> dt.date:
    m0 = anchor.month - 1 + n
    year, month = anchor.year + m0 // 12, m0 % 12 + 1
    return dt.date(year, month, min(anchor.day, _days_in(year, month)))


def _end_of_month(anchor: dt.date) -> dt.date:
    return dt.date(anchor.year, anchor.month, _days_in(anchor.year, anchor.month))


def _end_of_named_month(anchor: dt.date, month: int) -> dt.date:
    """The LAST day of a named month — "the end of September" names a day.

    CLAUDE.md: "until the end of September is inclusive — that phrase names the
    final day, not a boundary past it." So this is a date, not a fuzzy region,
    and it is the reason `the end of the month` stopped being AMBIGUOUS below.
    """
    for year in (anchor.year, anchor.year + 1):
        cand = dt.date(year, month, _days_in(year, month))
        if cand >= anchor:
            return cand
    raise ValueError(month)


def _month_day(anchor: dt.date, day: int) -> dt.date:
    """The soonest future day-of-month, rolling forward — 'the 15th' on the
    20th is next month's 15th."""
    cur = anchor
    for _ in range(3):
        try:
            cand = cur.replace(day=day)
        except ValueError:
            cand = None
        if cand and cand >= anchor:
            return cand
        cur = (cur.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
    raise ValueError(day)


# ---------------------------------------------------------------------------
# DATE fillers -> (date, part-of-day hint or None)
#
# The hint matters: "this evening" is BOTH a date (today) and a coarse time.
# Keeping them separate is what lets the board score the two independently
# instead of blaming the date resolver for a clock miss.
# ---------------------------------------------------------------------------

DATES = {
    "today":                    (lambda a: a,                              None),
    "tonight":                  (lambda a: a,                              "evening"),
    "this evening":             (lambda a: a,                              "evening"),
    "this afternoon":           (lambda a: a,                              "afternoon"),
    "this morning":             (lambda a: a,                              "morning"),
    "tomorrow":                 (lambda a: a + dt.timedelta(days=1),       None),
    "the day after tomorrow":   (lambda a: a + dt.timedelta(days=2),       None),
    "in two days":              (lambda a: a + dt.timedelta(days=2),       None),
    "in three days":            (lambda a: a + dt.timedelta(days=3),       None),
    "in five days":             (lambda a: a + dt.timedelta(days=5),       None),
    "in a week":                (lambda a: a + dt.timedelta(days=7),       None),
    "a week from today":        (lambda a: a + dt.timedelta(days=7),       None),
    "two weeks from now":       (lambda a: a + dt.timedelta(days=14),      None),
    "in two weeks":             (lambda a: a + dt.timedelta(days=14),      None),
    "in three weeks":           (lambda a: a + dt.timedelta(days=21),      None),
    "next monday":              (lambda a: _next_week(a, "monday"),        None),
    "next tuesday":             (lambda a: _next_week(a, "tuesday"),       None),
    "next wednesday":           (lambda a: _next_week(a, "wednesday"),     None),
    "next thursday":            (lambda a: _next_week(a, "thursday"),      None),
    "next friday":              (lambda a: _next_week(a, "friday"),        None),
    "this friday":              (lambda a: _coming(a, "friday"),           None),
    "this coming saturday":     (lambda a: _coming(a, "saturday"),         None),
    "this sunday":              (lambda a: _coming(a, "sunday"),           None),
    "the 15th":                 (lambda a: _month_day(a, 15),              None),
    "the 20th":                 (lambda a: _month_day(a, 20),              None),
    "the 21st":                 (lambda a: _month_day(a, 21),              None),
    "the 30th":                 (lambda a: _month_day(a, 30),              None),
    "the 3rd":                  (lambda a: _month_day(a, 3),               None),
    "christmas day":            (lambda a: dt.date(a.year + (a.month == 12 and a.day > 25), 12, 25), None),
    "new year's eve":           (lambda a: dt.date(a.year + (a.month == 12 and a.day > 31), 12, 31), None),
    # --- 2026-09-08 growth. Every form below was MINED from the corpora
    # (11,932 texts, sealed 300 excluded) rather than invented, so the dataset
    # exercises what people actually say. Counts are occurrences in that corpus.

    # A NAMED MONTH, honoured exactly (§8.2's defect class; "march 5th" 147x).
    "march 5th":                (lambda a: _month_ordinal(a, 3, 5),        None),
    "march 23rd":               (lambda a: _month_ordinal(a, 3, 23),       None),
    "april 1st":                (lambda a: _month_ordinal(a, 4, 1),        None),
    "april 20th":               (lambda a: _month_ordinal(a, 4, 20),       None),
    "may 2nd":                  (lambda a: _month_ordinal(a, 5, 2),        None),
    "june 10th":                (lambda a: _month_ordinal(a, 6, 10),       None),
    "july 4th":                 (lambda a: _month_ordinal(a, 7, 4),        None),
    "august 15th":              (lambda a: _month_ordinal(a, 8, 15),       None),
    "september 1st":            (lambda a: _month_ordinal(a, 9, 1),        None),
    "october 31st":             (lambda a: _month_ordinal(a, 10, 31),      None),
    "february 12th":            (lambda a: _month_ordinal(a, 2, 12),       None),
    # The "of" order, which a bare-ordinal rule must not hijack — the exact
    # case segmentation's md calls out and the one a987aba got wrong.
    "the 20th of november":     (lambda a: _month_ordinal(a, 11, 20),      None),
    "the 12th of august":       (lambda a: _month_ordinal(a, 8, 12),       None),
    "the 5th of march":         (lambda a: _month_ordinal(a, 3, 5),        None),

    # BARE ordinals roll month by month, never year by year.
    "the 1st":                  (lambda a: _month_day(a, 1),               None),
    "the 5th":                  (lambda a: _month_day(a, 5),               None),
    "the 10th":                 (lambda a: _month_day(a, 10),              None),
    "the 12th":                 (lambda a: _month_day(a, 12),              None),
    "the 22nd":                 (lambda a: _month_day(a, 22),              None),
    "the 25th":                 (lambda a: _month_day(a, 25),              None),
    "the 28th":                 (lambda a: _month_day(a, 28),              None),
    "the 31st":                 (lambda a: _month_day(a, 31),              None),

    # More weekday phrasings ("coming saturday" 151x).
    "next saturday":            (lambda a: _next_week(a, "saturday"),      None),
    "next sunday":              (lambda a: _next_week(a, "sunday"),        None),
    "this monday":              (lambda a: _coming(a, "monday"),           None),
    "this tuesday":             (lambda a: _coming(a, "tuesday"),          None),
    "this wednesday":           (lambda a: _coming(a, "wednesday"),        None),
    "this thursday":            (lambda a: _coming(a, "thursday"),         None),
    "this saturday":            (lambda a: _coming(a, "saturday"),         None),
    "this coming monday":       (lambda a: _coming(a, "monday"),           None),
    "this coming friday":       (lambda a: _coming(a, "friday"),           None),

    # Longer offsets, including the MONTH unit the set had no coverage of.
    "in four days":             (lambda a: a + dt.timedelta(days=4),       None),
    "in six days":              (lambda a: a + dt.timedelta(days=6),       None),
    "in ten days":              (lambda a: a + dt.timedelta(days=10),      None),
    "in four weeks":            (lambda a: a + dt.timedelta(days=28),      None),
    "three weeks from now":     (lambda a: a + dt.timedelta(days=21),      None),
    "in a month":               (lambda a: _add_months(a, 1),              None),
    "in two months":            (lambda a: _add_months(a, 2),              None),
    "in six months":            (lambda a: _add_months(a, 6),              None),
    "a month from today":       (lambda a: _add_months(a, 1),              None),

    # END OF A MONTH — a DATE, not a fuzzy region. See `_end_of_named_month`:
    # CLAUDE.md rules that "the end of September" names the final day, which is
    # what moved "the end of the month" out of AMBIGUOUS below (74x in corpus).
    "the end of the month":     (lambda a: _end_of_month(a),               None),
    "the end of september":     (lambda a: _end_of_named_month(a, 9),      None),
    "the end of december":      (lambda a: _end_of_named_month(a, 12),     None),
    "the end of the year":      (lambda a: dt.date(a.year, 12, 31),        None),

    "christmas eve":            (lambda a: _month_ordinal(a, 12, 24),      None),
    "new year's day":           (lambda a: _month_ordinal(a, 1, 1),        None),

    # Coarse ranges. A "week" or "weekend" is not ONE date, and picking a day
    # would be inventing precision the speaker did not give.
    "next week":                AMBIGUOUS,
    "this weekend":             AMBIGUOUS,
    "next month":               AMBIGUOUS,
    "the rest of the day":      AMBIGUOUS,
    "the next few days":        AMBIGUOUS,
}

# ---------------------------------------------------------------------------
# TIME fillers -> "HH:MM"
#
# A bare hour with no am/pm is the project's `bare_hour_pm` question and is a
# PRODUCT decision, not a fact — so those are AMBIGUOUS here and excluded,
# rather than baking one reading into the gold.
# ---------------------------------------------------------------------------

#: Times whose am/pm is EXPLICIT — a flat lookup, no context needed.
TIMES = {
    "7am": "07:00", "7:30am": "07:30", "9 in the morning": "09:00",
    "10am": "10:00", "11am": "11:00",
    "noon": "12:00", "midday": "12:00", "midnight": "00:00",
    "5 pm": "17:00", "3pm": "15:00", "6pm": "18:00", "8pm": "20:00",
    "14:00": "14:00",
    # --- 2026-09-08 growth, mined. am/pm is EXPLICIT in all of these, so they
    # are a flat lookup: no bare-hour question arises. Spelling variants are
    # separate keys on purpose -- "2pm" and "2 pm" are different fillers and
    # Whisper emits both.
    "2pm": "14:00", "2 pm": "14:00", "4pm": "16:00", "9am": "09:00",
    "10 am": "10:00", "12pm": "12:00", "12 noon": "12:00", "12am": "00:00",
    "8:30pm": "20:30", "3:45pm": "15:45", "6:30pm": "18:30", "8:15pm": "20:15",
    "7:15am": "07:15", "11:45am": "11:45",
    # 24-hour, which the set had exactly one of.
    "09:30": "09:30", "13:00": "13:00", "15:30": "15:30", "18:45": "18:45",
    "20:00": "20:00",
    # Spoken, but with the half of day SAID -- so still unambiguous.
    "seven in the morning": "07:00", "nine in the morning": "09:00",
    "eight in the evening": "20:00", "ten thirty in the morning": "10:30",
    # Coarse parts of the day. These are a PRODUCT decision, not a fact, so
    # each one is either decided by Gil or left ambiguous — never guessed.
    "first thing in the morning": AMBIGUOUS,   # undecided
    "around lunchtime": AMBIGUOUS,             # undecided
    "early evening": AMBIGUOUS,                # undecided
}

#: Coarse parts of the day that resolve to a WINDOW, not an instant — so they
#: set an end time as well as a start. Gil, 2026-09-08: "late afternoon just set
#: default as 5-7pm unless stated otherwise."
#:
#: "unless stated otherwise" is already how the rest works: an explicit clock in
#: the sentence is a different filler and wins outright. This only fills the gap
#: when the speaker gave nothing more precise.
PART_OF_DAY_WINDOW = {
    "late afternoon": ("17:00", "19:00"),
}

#: Times spoken WITHOUT am/pm, as an (hour, minute) pair. Their value depends on
#: the sentence, so they are resolved by `resolve_time` below rather than looked
#: up — which is the whole reason they are separated out.
BARE_HOURS = {
    "6:45": (6, 45), "9:15": (9, 15), "8 o'clock": (8, 0),
    "half past six": (6, 30), "quarter to nine": (8, 45),
    "ten thirty": (10, 30),
    # --- 2026-09-08 growth, mined. Whisper writes what was SAID, so the spoken
    # forms are the common case rather than the exotic one. Values are the
    # (hour, minute) the words name; the bare-hour convention then decides
    # am/pm from the sentence, which is why these are not in TIMES.
    "three thirty": (3, 30), "seven thirty": (7, 30), "nine fifteen": (9, 15),
    "eleven forty five": (11, 45),
    "two o'clock": (2, 0), "three o'clock": (3, 0), "five o'clock": (5, 0),
    # "past" and "to" are arithmetic on the hour, done here by hand so the
    # gold does not depend on the resolver getting the direction right.
    "half past ten": (10, 30), "quarter past seven": (7, 15),
    "ten past six": (6, 10), "twenty past eight": (8, 20),
    "quarter to five": (4, 45), "twenty to seven": (6, 40),
    "7:15": (7, 15), "10:45": (10, 45), "11:30": (11, 30), "12:30": (12, 30),
}

#: THE BARE-HOUR CONVENTION, written out from its stated form rather than by
#: calling `validate.bare_hour_pm`. That distinction is the point: copying the
#: implementation would make the board unable to catch the implementation
#: drifting, because gold and code would move together. Stated:
#:
#:     a bare hour 1-6 is PM;  7-8 is PM only when evening words are present;
#:     9-12 are left as spoken.
#:
#: If the CONVENTION itself is wrong, no board will say so — that is a human
#: judgement, the same status as the date floor.
#: A WORD-BOUNDED regex, not a substring list. As substrings, "pm" matched inside
#: "4pm" -- so any sentence containing an explicit pm time made every bare hour in
#: it evening. Combined with reading the whole transcript (fixed below) that let
#: ONE item's "4pm" push a NEIGHBOUR's "8 o'clock" to 20:00.
_EVENING = re.compile(r"\b(tonight|this evening|evening|dinner|supper|drinks|pm)\b")


def resolve_time(filler: str, own_words: str = ""):
    """-> "HH:MM" | AMBIGUOUS | None. Needs the ITEM'S OWN words for a bare hour.

    `own_words` is this item's time plus its action — NOT the transcript. The
    bare-hour convention says "7-8 is pm when evening words are present", and the
    only evening words that can speak for an item are its own: in "team meeting
    from 3 to 4pm and budget review at quarter to nine" the 4pm belongs to the
    meeting, and letting it decide the budget review's hour is charging an item
    for a neighbour's words — the bug class this whole stage was built to end.
    """
    key = filler.strip().lower()
    if key in PART_OF_DAY_WINDOW:
        return PART_OF_DAY_WINDOW[key][0]      # the start; the end via window()
    if key in TIMES:
        return TIMES[key]
    if key not in BARE_HOURS:
        return None
    h, m = BARE_HOURS[key]
    tl = (own_words or "").lower()
    if h <= 6:
        return f"{h + 12:02d}:{m:02d}"
    if 7 <= h <= 8 and _EVENING.search(tl):
        return f"{h + 12:02d}:{m:02d}"
    return f"{h:02d}:{m:02d}"

# ---------------------------------------------------------------------------
# RECURRENCE -> (cadence, weekday or None)
#
# The engine supports daily|weekly|monthly ONLY, and anything else is rounded
# and the rounding announced. Gold records the rounded value, because that is
# the product's stated contract, plus the weekday a weekly series must start on.
# ---------------------------------------------------------------------------

RECURRENCES = {
    "every day": ("daily", None), "daily": ("daily", None),
    "nightly": ("daily", None), "every morning": ("daily", None),
    "every evening": ("daily", None), "every night": ("daily", None),
    "every week": ("weekly", None), "weekly": ("weekly", None),
    "every monday": ("weekly", "monday"), "every tuesday": ("weekly", "tuesday"),
    "every friday": ("weekly", "friday"),
    "monthly": ("monthly", None), "every month": ("monthly", None),
    # Rounded, and the rounding is ANNOUNCED — so the gold carries a flag the
    # board can check the reply for.
    "every other week": ("weekly", None),
    "every other tuesday": ("weekly", "tuesday"),
    "every weekday": ("daily", None),
    "every weekend": ("weekly", "saturday"),
    # Gil, 2026-09-08 chose option (c): ONE weekly series naming both days,
    # rather than losing the Thursday or making two series for one sentence.
    # The CADENCE is still weekly -- `recur_days` says WHICH days it lands on,
    # so daily|weekly|monthly is unchanged.
    "every tuesday and thursday": ("weekly", ["tuesday", "thursday"]),

    # --- 2026-09-08 growth, mined.
    "every sunday": ("weekly", "sunday"),
    "every wednesday": ("weekly", "wednesday"),
    "every thursday": ("weekly", "thursday"),
    "every saturday": ("weekly", "saturday"),
    "everyday": ("daily", None), "once a week": ("weekly", None),
    "every monday and wednesday": ("weekly", ["monday", "wednesday"]),
    "every saturday and sunday": ("weekly", ["saturday", "sunday"]),
    "every monday wednesday and friday":
        ("weekly", ["monday", "wednesday", "friday"]),
    # ROUNDED — the cadence does not fit daily|weekly|monthly, so it is rounded
    # to one that does and the reply must SAY so.
    "twice a week": ("weekly", None), "twice a day": ("daily", None),
    "every other day": ("daily", None), "biweekly": ("weekly", None),
    "fortnightly": ("weekly", None), "every three weeks": ("weekly", None),
    # A YEARLY cadence cannot be rounded honestly: the nearest representable
    # value is monthly, which is 12x wrong and would fire eleven times a year
    # that nobody asked for. Rounding is only acceptable when it stays close,
    # so this is AMBIGUOUS rather than silently mangled -- and it is a real
    # product gap ("every year" 24x in the corpus), recorded in ARCHITECTURE.md.
    "every year": AMBIGUOUS, "annually": AMBIGUOUS, "yearly": AMBIGUOUS,
}

#: Recurrences whose cadence was ROUNDED to fit daily|weekly|monthly. The reply
#: must say so — never a silent change.
ROUNDED = {"every other week", "every other tuesday", "every weekday",
           "every weekend", "twice a week", "twice a day", "every other day",
           "biweekly", "fortnightly", "every three weeks"}

# ---------------------------------------------------------------------------
# LEAD TIME -> minutes before start
# ---------------------------------------------------------------------------

LEAD_TIMES = {
    "5 minutes before": 5, "10 minutes before": 10, "15 minutes before": 15,
    "30 minutes before": 30, "half an hour before": 30,
    "an hour before": 60, "two hours before": 120,
    "a day before": 1440, "a week before": 10080,
    # --- 2026-09-08 growth, mined.
    "1 hour before": 60, "2 hours before": 120, "2 days before": 2880,
    "three days before": 4320, "three weeks before": 30240,
    "fifteen minutes before": 15, "twenty minutes before": 20,
    "45 minutes before": 45,
    # SYNONYMS of "before". Same offset, different word -- the resolver knew
    # only "before", so "an hour ahead" and "two days prior" produced nothing
    # at all. Real forms, all from the corpus.
    "an hour ahead": 60, "a day ahead": 1440, "three days ahead": 4320,
    "two days prior": 2880, "10 minutes prior": 10,
    "4 hours in advance": 240, "five minutes in advance": 5,
    "20 minutes in advance": 20,
}

# ---------------------------------------------------------------------------
# DURATION -> minutes, which sets END TIME from the start
#
# New 2026-09-08. "book the gym at 5 for an hour" names an end and the set had
# no way to express it -- 23 occurrences of "for a week" alone. A duration only
# produces a value when there IS a start; with no start there is nothing to add
# it to, and inventing one would be inventing the whole event.
# ---------------------------------------------------------------------------

DURATIONS = {
    "for 15 minutes": 15, "for 30 minutes": 30, "for 45 minutes": 45,
    "for 90 minutes": 90, "for half an hour": 30, "for an hour": 60,
    "for two hours": 120, "for three hours": 180,
    # MULTI-DAY durations are a different field. "for two weeks" is a span of
    # days, and X3 has no start/end DATE pair -- only `recur_until`, which
    # belongs to a series. Marked rather than crushed into end_time, where it
    # would mean 20,160 minutes past a clock time.
    "for a day": AMBIGUOUS, "for two days": AMBIGUOUS,
    "for a week": AMBIGUOUS, "for two weeks": AMBIGUOUS,
}

# ---------------------------------------------------------------------------
# QUANTITY -> integer
# ---------------------------------------------------------------------------

QUANTITIES = {
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "eight": 8,
    "twelve": 12, "a dozen": 12, "half a dozen": 6,
    "2": 2, "3": 3, "5": 5, "10": 10,
    "a couple of": 2,
    "a few": AMBIGUOUS,          # 3? more? not a number the speaker gave
}

# ---------------------------------------------------------------------------
# TIME RANGE -> (start "HH:MM", end "HH:MM")
# ---------------------------------------------------------------------------

#: A BARE range is no longer ambiguous, and it is worth writing down why, since
#: these four were AMBIGUOUS until 2026-09-08. Two rules the project has ALREADY
#: stated settle every one of them, so this is a derivation and not a new ruling:
#:
#:   1. the bare-hour convention — 1-6 is PM, 9-12 as spoken
#:   2. `end_before_start` — a range's end must come AFTER its start
#:
#: "from 6 to 8": rule 1 makes the 6 into 18:00, and rule 2 then forces the 8 to
#: 20:00 — an 08:00 end would precede the start. "from 9 to 2:30": rule 1 leaves
#: the 9 at 09:00, rule 2 forces the 2:30 to 14:30. Neither needed a guess.
#:
#: If either convention is wrong, these are wrong with it — which is the correct
#: coupling. A gold value should follow from the stated rules, not from what the
#: resolver happens to return.
TIME_RANGES = {
    "from 10am to 11:30am": ("10:00", "11:30"),
    "from 3 to 4pm": ("15:00", "16:00"),
    "from noon to 1": ("12:00", "13:00"),
    "from 6 to 8": ("18:00", "20:00"),
    "between 2 and 4": ("14:00", "16:00"),
    "from 9 to 2:30": ("09:00", "14:30"),
    "between 5 and 6:30": ("17:00", "18:30"),
    # --- 2026-09-08 growth, mined.
    "from 4 to 6": ("16:00", "18:00"),
    "between 3 and 5": ("15:00", "17:00"),
    "from three to five": ("15:00", "17:00"),
    "between 11am and 3pm": ("11:00", "15:00"),
    "from 9 to 11": ("09:00", "11:00"),
    "between 6 and 7pm": ("18:00", "19:00"),
    "from 2 to 4pm": ("14:00", "16:00"),
    "from 8am to 10am": ("08:00", "10:00"),
    "between 1 and 2": ("13:00", "14:00"),
}


def resolve_date(filler: str, anchor: dt.date):
    """-> (iso date, part-of-day hint) | AMBIGUOUS | None if unknown."""
    entry = DATES.get(filler.strip().lower())
    if entry is None:
        return None
    if entry is AMBIGUOUS:
        return AMBIGUOUS
    fn, hint = entry
    return fn(anchor).isoformat(), hint


def window(filler: str):
    """-> (start, end) for a coarse part of the day, else None.

    Separate from `resolve_time` because these are the only fillers that imply
    a DURATION. Everything else gives a start and lets the event's default
    length apply.
    """
    return PART_OF_DAY_WINDOW.get(filler.strip().lower())


def coverage() -> dict:
    """How much of each bank is normalized — printed by the generator so the
    dataset's blind spots are visible rather than implied."""
    def split(table):
        known = sum(1 for v in table.values() if v is not AMBIGUOUS)
        return {"known": known, "ambiguous": len(table) - known}
    times = split(TIMES)
    times["known"] += len(BARE_HOURS) + len(PART_OF_DAY_WINDOW)
    return {"dates": split(DATES), "times": times,
            "recurrences": split(RECURRENCES), "quantities": split(QUANTITIES),
            "time_ranges": split(TIME_RANGES), "durations": split(DURATIONS),
            "lead_times": {"known": len(LEAD_TIMES), "ambiguous": 0}}
