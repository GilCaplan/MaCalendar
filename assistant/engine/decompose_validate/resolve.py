"""Resolvers: an item's spoken time -> concrete values. Pure, and per ITEM.

    resolve(item.time, anchor, said) -> {date, start_time, end_time,
                                         recurrence, recur_days, rounded}

WHY EVERY FUNCTION HERE TAKES ONE ITEM'S OWN TIME
-------------------------------------------------
The stage this replaces read the WHOLE transcript, produced a flat list of
dates, and pinned them to events by index (`ev_idx`, `n_events`,
`orig_event_dates`). That is the bug class: `relative_dates` returns two dates
for three events on "add gym on tuesday … and add yoga on tuesday … and add my
conference on the 20th of November", because the bare-ordinal branch correctly
refuses to claim a month-named ordinal — and the conference lands in September.
It also caused `a987aba`.

Segmentation already decided which words belong to which item. So a resolver
takes ONE item's time and nothing else, there is no list to index into, and
"which event does this date belong to" is never asked. That is the fix; the
rest of this module is just doing the arithmetic carefully.

RELATIONSHIP TO THE GOLD
------------------------
`datasets/normalization.py` is a CLOSED LOOKUP TABLE — every filler, written out
by hand. This is a GENERAL PARSER over arbitrary strings. They are deliberately
different implementations of the same conventions, which is what lets the board
catch a bug here. Copying the table would make gold and code move together and
the board would measure nothing.
"""
from __future__ import annotations

import datetime as dt
import re

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday",
            "saturday", "sunday")
_WD = {name: i for i, name in enumerate(WEEKDAYS)}
_MONTHS = {m.lower(): i for i, m in enumerate(
    ("January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"), start=1)}
_NUMBER = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4,
           "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
           "a couple of": 2, "a dozen": 12, "half a dozen": 6, "twelve": 12}

#: Words that make a bare 7 or 8 o'clock mean the evening. Same list the
#: convention is stated with; see `_bare_hour`.
_EVENING = re.compile(r"\b(tonight|this evening|evening|dinner|supper|drinks|pm)\b", re.I)


# ---------------------------------------------------------------------------
# DATE
# ---------------------------------------------------------------------------

def _coming(anchor: dt.date, name: str) -> dt.date:
    """The soonest `name`, today counting as today."""
    return anchor + dt.timedelta(days=(_WD[name] - anchor.weekday()) % 7)


def _next_calendar_week(anchor: dt.date, name: str) -> dt.date:
    """"next tuesday" = that weekday in the NEXT calendar week, which on some
    anchors is the same day "this tuesday" would give. Both readings agreeing
    is not a bug — it is what the words mean on a Sunday."""
    return anchor + dt.timedelta(days=(7 - anchor.weekday()) + _WD[name])


def _roll_to_day(anchor: dt.date, day: int, month: "int | None" = None) -> "dt.date | None":
    """The soonest future date with this day-of-month (and month, if named).

    A named MONTH is honoured exactly — "the 20th of November" is November,
    even when that is next year. Only a BARE ordinal rolls month by month,
    which is the distinction the old code's guard was protecting and the
    reason it returned fewer dates than events.
    """
    if month is not None:
        for year in (anchor.year, anchor.year + 1):
            try:
                cand = dt.date(year, month, day)
            except ValueError:
                continue
            if cand >= anchor:
                return cand
        return None
    cur = anchor
    for _ in range(13):
        try:
            cand = cur.replace(day=day)
        except ValueError:
            cand = None
        if cand and cand >= anchor:
            return cand
        cur = (cur.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
    return None


def resolve_date(said: str, anchor: dt.date) -> "str | None":
    """One item's time words -> an ISO date, or None if they name no day.

    Ordered most specific first. A month-named ordinal must be tried before the
    bare one, or "the 20th of November" is read as "the 20th" and the month is
    lost — which is exactly the live bug.
    """
    t = (said or "").lower()
    if not t.strip():
        return None

    # "the 20th of November" / "November the 20th" / "November 20"
    m = (re.search(r"\bthe\s+(\d{1,2})(?:st|nd|rd|th)?\s+of\s+([a-z]+)", t)
         or re.search(r"\b([a-z]+)\s+the\s+(\d{1,2})(?:st|nd|rd|th)?\b", t)
         or re.search(r"\b([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?\b", t))
    if m:
        a, b = m.group(1), m.group(2)
        day, month = (int(a), _MONTHS.get(b)) if a.isdigit() else (
            int(b) if b.isdigit() else None, _MONTHS.get(a))
        if month and day:
            got = _roll_to_day(anchor, day, month)
            if got:
                return got.isoformat()

    if re.search(r"\bday after tomorrow\b", t):
        return (anchor + dt.timedelta(days=2)).isoformat()

    # OFFSETS BEFORE BARE WORDS. "a week from today" contains "today", and a
    # bare-today branch placed first swallowed it and returned the anchor —
    # every "a week from today" resolved to today. The longer phrase wins.
    # "in three weeks", "two weeks from now", "a week from today"
    # NOT followed by "before" -- "the 21st a day before" is a LEAD TIME on the
    # 21st, not "in a day". Read as an offset it produced tomorrow and threw
    # away the 21st entirely.
    # The lookahead sits DIRECTLY on the unit. Placed after the optional
    # `\s*` it never fired, because that had already eaten the space and the
    # lookahead saw "before" with no whitespace in front of it.
    m = re.search(r"\b(?:in\s+)?(\w+)\s+(day|week|month)s?\b(?!\s+before)\s*"
                  r"(?:from\s+(?:now|today))?", t)
    if m and (m.group(1).isdigit() or m.group(1) in _NUMBER):
        n = int(m.group(1)) if m.group(1).isdigit() else _NUMBER[m.group(1)]
        unit = m.group(2)
        if unit == "day":
            return (anchor + dt.timedelta(days=n)).isoformat()
        if unit == "week":
            return (anchor + dt.timedelta(weeks=n)).isoformat()
        month0 = anchor.month - 1 + n
        year, month = anchor.year + month0 // 12, month0 % 12 + 1
        day = min(anchor.day, [31, 29 if year % 4 == 0 else 28, 31, 30, 31, 30,
                               31, 31, 30, 31, 30, 31][month - 1])
        return dt.date(year, month, day).isoformat()

    if re.search(r"\btomorrow\b", t):
        return (anchor + dt.timedelta(days=1)).isoformat()
    if re.search(r"\b(today|tonight|this (?:morning|afternoon|evening))\b", t):
        return anchor.isoformat()

    for name in WEEKDAYS:
        if re.search(rf"\b{name}\b", t):
            if re.search(rf"\bnext\s+{name}\b", t):
                return _next_calendar_week(anchor, name).isoformat()
            return _coming(anchor, name).isoformat()

    if re.search(r"\bchristmas\b", t):
        year = anchor.year + (1 if (anchor.month, anchor.day) > (12, 25) else 0)
        return dt.date(year, 12, 25).isoformat()
    if re.search(r"\bnew year'?s eve\b", t):
        year = anchor.year + (1 if (anchor.month, anchor.day) > (12, 31) else 0)
        return dt.date(year, 12, 31).isoformat()

    m = re.search(r"\bthe\s+(\d{1,2})(?:st|nd|rd|th)\b", t)
    if m:
        got = _roll_to_day(anchor, int(m.group(1)))
        if got:
            return got.isoformat()
    return None


# ---------------------------------------------------------------------------
# CLOCK
# ---------------------------------------------------------------------------

_WORD_CLOCK = {"noon": (12, 0), "midday": (12, 0), "midnight": (0, 0)}

#: Coarse parts of the day, which imply a WINDOW rather than an instant.
#: "late afternoon" is 5-7pm (Gil, 2026-09-08). Only settled ones are here —
#: "early evening" and "around lunchtime" have no ruling yet, so they resolve
#: to nothing rather than to a number nobody chose.
PART_OF_DAY = {"late afternoon": ("17:00", "19:00")}
_MINUTE_WORD = {"half past": 30, "quarter past": 15, "quarter to": -15}

#: SPOKEN CLOCK TIMES. Whisper writes what was said, and "ten thirty" is said
#: far more often than "10:30" — every one of the resolver's 31 missing clock
#: times was this one form. Listed longest-first so "twenty five" is read before
#: "twenty" leaves the "five" behind as a stray word.
_SPOKEN_HOUR = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
                "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
                "twelve": 12}
_SPOKEN_MINUTE = {"o'clock": 0, "oclock": 0, "twenty five": 25, "twenty-five": 25,
                  "thirty five": 35, "thirty-five": 35, "forty five": 45,
                  "forty-five": 45, "fifty five": 55, "fifty-five": 55,
                  "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40,
                  "fifty": 50, "ten": 10, "five": 5}

_SPOKEN_CLOCK = re.compile(
    r"\b(" + "|".join(_SPOKEN_HOUR) + r")\s+(" +
    "|".join(re.escape(m) for m in _SPOKEN_MINUTE) + r")\b")


def _bare_hour(h: int, minute: int, said: str) -> str:
    """THE BARE-HOUR CONVENTION: 1-6 is PM; 7-8 is PM only with evening words.

    A bare hour in calendar speech is far more often the afternoon — "gym at 5"
    is not 5am. 7 and 8 are the boundary, so they need the sentence to say so.
    """
    if h <= 6:
        return f"{h + 12:02d}:{minute:02d}"
    if 7 <= h <= 8 and _EVENING.search(said or ""):
        return f"{h + 12:02d}:{minute:02d}"
    return f"{h:02d}:{minute:02d}"


def resolve_clock(said: str, context: str = "") -> "str | None":
    """One item's time words -> "HH:MM", or None if they name no clock time."""
    t = (said or "").lower()
    ctx = f"{t} {context or ''}"

    for phrase, (start, _end) in PART_OF_DAY.items():
        if phrase in t:
            return start

    for word, (h, mi) in _WORD_CLOCK.items():
        if re.search(rf"\b{word}\b", t):
            return f"{h:02d}:{mi:02d}"

    # SPOKEN BEFORE THE DIGIT BRANCHES, and the compound form before the bare
    # one, so "ten thirty" is not read as a bare ten with a loose "thirty".
    m = _SPOKEN_CLOCK.search(t)
    if m:
        return _bare_hour(_SPOKEN_HOUR[m.group(1)], _SPOKEN_MINUTE[m.group(2)], ctx)

    # A BARE worded hour needs an explicit "at". "one" and "five" are ordinary
    # words — "the one I just made", "five apples" — and reading either as a
    # clock would INVENT a time nobody said, which the board counts as harm.
    m = re.search(rf"\bat\s+({'|'.join(_SPOKEN_HOUR)})\b", t)
    if m:
        return _bare_hour(_SPOKEN_HOUR[m.group(1)], 0, ctx)

    for phrase, delta in _MINUTE_WORD.items():
        m = re.search(rf"\b{phrase}\s+(\w+)\b", t)
        if m:
            word = m.group(1)
            h = int(word) if word.isdigit() else _NUMBER.get(word)
            if h is None:
                continue
            if delta < 0:
                h, minute = h - 1, 60 + delta
            else:
                minute = delta
            return _bare_hour(h, minute, ctx)

    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)\b", t)
    if m:
        h, minute = int(m.group(1)), int(m.group(2) or 0)
        ap = m.group(3)[0]
        if ap == "p" and h < 12:
            h += 12
        if ap == "a" and h == 12:
            h = 0
        return f"{h:02d}:{minute:02d}"

    m = re.search(r"\b(\d{1,2}):(\d{2})\b", t)
    if m:
        h, minute = int(m.group(1)), int(m.group(2))
        return f"{h:02d}:{minute:02d}" if h >= 9 else _bare_hour(h, minute, ctx)

    m = re.search(r"\bat\s+(\d{1,2})\b(?!\s*:)", t) or re.search(r"\b(\d{1,2})\s*o'?clock\b", t)
    if m:
        return _bare_hour(int(m.group(1)), 0, ctx)
    return None


def resolve_range(said: str, context: str = "") -> "tuple[str, str] | None":
    """"from 3 to 4pm" / "between 2 and 4" -> (start, end)."""
    t = (said or "").lower()
    m = re.search(r"\b(?:from|between)\s+(.+?)\s+(?:to|until|till|and)\s+(.+?)$", t)
    if not m:
        return None

    def _side(part: str, ctx: str) -> "str | None":
        """Inside a range, a BARE NUMBER is a clock time. Outside one it is not
        -- "buy 3 apples" must never become 03:00 -- which is why this lives
        here and not in resolve_clock. Without it "from 3 to 4pm" failed
        entirely: the start returned None and took the whole range with it."""
        got = resolve_clock(part, ctx)
        if got:
            return got
        bare = re.fullmatch(r"\s*(\d{1,2})(?::(\d{2}))?\s*", part)
        if bare:
            return _bare_hour(int(bare.group(1)), int(bare.group(2) or 0), ctx)
        return None
    # The END carries the am/pm for both when only it has one — "from 3 to 4pm"
    # is 15:00-16:00, not 03:00-16:00.
    end = _side(m.group(2), context)
    # The END carries the am/pm for both when only it has one -- "from 3 to 4pm"
    # is 15:00-16:00, not 03:00-16:00 -- so the end's words join the start's
    # context.
    start = _side(m.group(1), f"{context} {m.group(2)}")
    if not (start and end):
        return None
    if end <= start:                      # "from 9 to 2:30" crosses midday
        eh = int(end[:2])
        if eh < 12:
            end = f"{eh + 12:02d}{end[2:]}"
    return (start, end) if end > start else None


# ---------------------------------------------------------------------------
# RECURRENCE
# ---------------------------------------------------------------------------

def resolve_recurrence(said: str) -> "dict | None":
    """-> {cadence, days, rounded} or None.

    `cadence` is only ever daily|weekly|monthly — the product's rule. Anything
    else is ROUNDED to one of them and `rounded` says so, because the reply has
    to announce it rather than change the meaning quietly.

    `days` lets a weekly series name several weekdays ("every tuesday and
    thursday"). That is WHICH days a weekly series lands on, not a fourth
    cadence.
    """
    t = (said or "").lower()
    if not re.search(r"\b(every|each|daily|weekly|monthly|nightly)\b", t):
        return None

    days = [d for d in WEEKDAYS if re.search(rf"\b{d}\b", t)]
    rounded = False

    if re.search(r"\bevery other\b", t):
        rounded = True                     # fortnightly -> weekly, announced
    if re.search(r"\bevery weekday\b", t):
        return {"cadence": "daily", "days": [], "rounded": True}
    if re.search(r"\bevery weekend\b", t):
        return {"cadence": "weekly", "days": ["saturday"], "rounded": True}
    if re.search(r"\b(monthly|every month)\b", t):
        return {"cadence": "monthly", "days": [], "rounded": rounded}
    if re.search(r"\b(daily|nightly|every day|every morning|every evening|every night)\b", t):
        return {"cadence": "daily", "days": [], "rounded": rounded}
    return {"cadence": "weekly", "days": days, "rounded": rounded}


# ---------------------------------------------------------------------------
# From the ACTION words, not the time
# ---------------------------------------------------------------------------

#: WHAT MAY FOLLOW "before" and still leave it a lead time on THIS item.
#: Either a self-reference, or the item's own time continuing the sentence —
#: "remind me 15 minutes before at ten thirty" is how the speaker orders it.
#: A BARE NOUN PHRASE is the disqualifier: "an hour before sales call" measures
#: from a DIFFERENT event, and reading it as a lead time would have fired the
#: reminder an hour before the taxes instead.
_SELF_REFERENCE = frozenset((
    "it", "that", "then", "hand", "it starts", "it begins", "the start",
    "the event", "the meeting", "the appointment", "the time", "start",
))
_TAIL_CONTINUES = re.compile(
    r"^(?:at|on|in|from|until|till|through|starting|and|tomorrow|today|tonight|"
    r"next|this|every|each)\b")


def resolve_lead_time(said: str) -> "int | None":
    """"half an hour before" -> 30 minutes."""
    t = (said or "").lower()
    # HALF FIRST. "half an hour before" matched on "an hour" and returned 60 —
    # the `half` sat outside the pattern and was silently dropped, so every one
    # of these reminders fired an hour early. The fraction has to be read before
    # the unit it modifies.
    m = re.search(r"\bhalf\s+(?:an?\s+)?(hour|day|week)s?\s+before\b", t)
    if m:
        return {"hour": 30, "day": 720, "week": 5040}[m.group(1)]

    m = re.search(r"\b(?:(\d+)|(\w+))\s+(minute|hour|day|week)s?\s+before\b", t)
    if not m:
        return None
    # BEFORE WHAT. `reminder_minutes` means "nudge me N minutes before THIS
    # item's start", so it only applies when `before` points back at this item.
    # "remind me to file the taxes an hour before sales call" is an hour before
    # a DIFFERENT event, and reading it as a lead time attached the reminder to
    # the wrong thing entirely — it would have fired an hour before the taxes.
    tail = t[m.end():].strip(" ,.")
    if tail and tail not in _SELF_REFERENCE and not _TAIL_CONTINUES.match(tail):
        return None
    n = int(m.group(1)) if m.group(1) else _NUMBER.get(m.group(2))
    if n is None:
        return None
    return n * {"minute": 1, "hour": 60, "day": 1440, "week": 10080}[m.group(3)]


#: Nouns that make a number a LENGTH OF TIME rather than a count of things.
_DURATION_UNIT = (r"(?:mins?|minutes?|hrs?|hours?|days?|weeks?|months?|years?|"
                  r"seconds?|secs?)\b")


def resolve_quantity(said: str) -> "int | None":
    """"5 apples" / "a dozen eggs" -> the count."""
    t = (said or "").lower()
    for phrase in ("half a dozen", "a couple of", "a dozen"):
        if phrase in t:
            return _NUMBER[phrase]
    # A DURATION IS NOT A COUNT. "extend blood test by 30 minutes" was read as a
    # quantity of 30, which would have put "30" on the todo row next to an
    # instruction that is about the event's LENGTH. The unit noun settles it.
    m = re.search(rf"\b(\d+)\s+(?!{_DURATION_UNIT})\w+", t)
    if m:
        return int(m.group(1))
    m = re.search(rf"\b(two|three|four|five|six|seven|eight|nine|ten|twelve)\s+"
                  rf"(?!{_DURATION_UNIT})\w+", t)
    return _NUMBER.get(m.group(1)) if m else None


# ---------------------------------------------------------------------------

#: A SERIES BOUND, not a start date. "every tuesday until the 21st" names two
#: different things and the resolver used to keep only one of them — the 21st
#: became the FIRST tuesday, which was a Monday. Split before resolving.
#:
#: UNTIL EXCLUDES the day it names; THROUGH and INCLUDING keep it. English
#: supports both readings, so the project picks one and applies it everywhere
#: (CLAUDE.md) rather than guessing per sentence.
_UNTIL = re.compile(r"\b(until|till|up to|through|thru|including)\b\s*(.+)$")

#: THE FIRST INSTANCE, said explicitly. "every other tuesday starting this
#: coming saturday" begins on the SATURDAY -- the cadence says how often, this
#: clause says from when, and the two are different dates. Bare "from" is
#: deliberately absent: "two weeks from now" would split on it and lose the
#: offset.
_START = re.compile(r"\b(?:starting|start(?:s|ing)? on|beginning|begins)\b\s*(.+)$")
_EXCLUSIVE = ("until", "till", "up to")


def resolve_until(said: str, anchor: dt.date) -> "str | None":
    """The END of a series, or None. Applies the until/through convention."""
    m = _UNTIL.search((said or "").lower())
    if not m:
        return None
    bound = resolve_date(m.group(2), anchor)
    if not bound:
        return None
    d = dt.date.fromisoformat(bound)
    if m.group(1) in _EXCLUSIVE:
        d -= dt.timedelta(days=1)
    return d.isoformat()


def resolve(said: str, anchor: dt.date, context: str = "") -> dict:
    """One item's `time` -> every value it implies. The stage's workhorse."""
    # The bound is resolved from the tail and REMOVED before the start date, so
    # a series' end can never be mistaken for its beginning.
    t = (said or "").lower()
    mu, ms = _UNTIL.search(t), _START.search(t)
    cut = min([x.start() for x in (mu, ms) if x] or [len(t)])
    head = t[:cut]

    # An explicit start clause outranks everything. Then a NON-WEEKDAY date
    # phrase in the head ("every weekday in five days"). Only if neither exists
    # does the cadence's own weekday decide, below -- resolve_date returns
    # weekdays in MONDAY ORDER, so "tuesday and thursday" said on a Wednesday
    # came back as next Tuesday, five days late and past the first instance.
    explicit = resolve_date(ms.group(1), anchor) if ms else None
    bare = re.sub(rf"\b({'|'.join(WEEKDAYS)})\b", " ", head)
    other = resolve_date(bare, anchor)

    out = {"date": explicit or other or resolve_date(head, anchor),
           "start_time": None,
           "end_time": None, "recurrence": None, "recur_days": [],
           "recurrence_rounded": False,
           "recur_until": resolve_until(said, anchor)}

    rng = resolve_range(said, context)
    if rng:
        out["start_time"], out["end_time"] = rng
    else:
        out["start_time"] = resolve_clock(said, context)
        for phrase, (_s, end) in PART_OF_DAY.items():
            if phrase in (said or "").lower():
                out["end_time"] = end      # a window carries its own end

    # HEAD, not `said`. resolve_recurrence over the whole string read the
    # BOUND's weekday as one of the series' days: "weekly until next wednesday"
    # became a Wednesday series starting on the wednesday of the bound. The
    # cadence is always in the head; the tail only ever names an end.
    rec = resolve_recurrence(head)
    if rec:
        out["recurrence"] = rec["cadence"]
        out["recur_days"] = rec["days"]
        out["recurrence_rounded"] = rec["rounded"]
        if rec["days"] and not (explicit or other):
            # THE SOONEST NAMED DAY, not the first one said. "every tuesday and
            # thursday" spoken on a Wednesday starts THURSDAY -- taking days[0]
            # put it five days late and skipped the first instance.
            out["date"] = min(_coming(anchor, d) for d in rec["days"]).isoformat()
        elif rec["days"] and out["date"]:
            # A SERIES STARTS ON A DAY IT NAMES (CLAUDE.md). "every monday
            # tonight" resolved the start from "tonight" and opened a Monday
            # series on a Sunday. Advance to the soonest named day instead of
            # replacing the date, so an explicit start still decides the WEEK.
            d0 = dt.date.fromisoformat(out["date"])
            if WEEKDAYS[d0.weekday()] not in rec["days"]:
                out["date"] = min(_coming(d0, d) for d in rec["days"]).isoformat()

    # THE DATE FLOOR — segmentation's rule, applied identically here so the two
    # stages cannot disagree about it: the day defaults to today, the clock is
    # never invented.
    if not out["date"]:
        out["date"] = anchor.isoformat()
    return out
