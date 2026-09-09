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
    # Coarse ranges. A "week" or "weekend" is not ONE date, and picking a day
    # would be inventing precision the speaker did not give.
    "next week":                AMBIGUOUS,
    "this weekend":             AMBIGUOUS,
    "next month":               AMBIGUOUS,
    "the end of the month":     AMBIGUOUS,
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
_EVENING_WORDS = ("tonight", "this evening", "evening", "dinner", "supper",
                  "drinks", "pm")


def resolve_time(filler: str, transcript: str = ""):
    """-> "HH:MM" | AMBIGUOUS | None. Needs the sentence for a bare hour."""
    key = filler.strip().lower()
    if key in PART_OF_DAY_WINDOW:
        return PART_OF_DAY_WINDOW[key][0]      # the start; the end via window()
    if key in TIMES:
        return TIMES[key]
    if key not in BARE_HOURS:
        return None
    h, m = BARE_HOURS[key]
    tl = (transcript or "").lower()
    if h <= 6:
        return f"{h + 12:02d}:{m:02d}"
    if 7 <= h <= 8 and any(w in tl for w in _EVENING_WORDS):
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
}

#: Recurrences whose cadence was ROUNDED to fit daily|weekly|monthly. The reply
#: must say so — never a silent change.
ROUNDED = {"every other week", "every other tuesday", "every weekday",
           "every weekend"}

# ---------------------------------------------------------------------------
# LEAD TIME -> minutes before start
# ---------------------------------------------------------------------------

LEAD_TIMES = {
    "5 minutes before": 5, "10 minutes before": 10, "15 minutes before": 15,
    "30 minutes before": 30, "half an hour before": 30,
    "an hour before": 60, "two hours before": 120,
    "a day before": 1440, "a week before": 10080,
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

TIME_RANGES = {
    "from 10am to 11:30am": ("10:00", "11:30"),
    "from 3 to 4pm": ("15:00", "16:00"),
    "from noon to 1": ("12:00", "13:00"),
    "from 6 to 8": AMBIGUOUS, "between 2 and 4": AMBIGUOUS,
    "from 9 to 2:30": AMBIGUOUS, "between 5 and 6:30": AMBIGUOUS,
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
            "time_ranges": split(TIME_RANGES),
            "lead_times": {"known": len(LEAD_TIMES), "ambiguous": 0}}
