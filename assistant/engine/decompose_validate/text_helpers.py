"""Read-only readings of the TRANSCRIPT, shared across the engine.

These are not rules and they change nothing — each answers one question about the
words ("does this text name a weekday?", "is this end bound inclusive?") and
several stages ask. They lived in `validate.py` because that is where they were
first needed; they are here because they belong to no single stage.

RETIRED FROM `validate.py` (Gil, 2026-09-08) along with the rest of it. The
original is in `retired/decompose-validate-v1/`.

`bare_hour_pm` is worth a note: it is the same CONVENTION `resolve.py` applies
(1-6 pm, 7-8 pm with evening words), stated a second time for callers that hold a
transcript rather than an item. The duplication is deliberate where it is measured
-- the gold restates it too, for the same reason -- but if the convention ever
changes, both move.
"""
from __future__ import annotations

import datetime as _dt
import re

_RECUR_WORDS = [
    (r"\bevery\s*day\b|\bdaily\b", "daily"),
    (r"\bevery\s+\w+day\b|\bweekly\b|\b(?:mon|tues|wednes|thurs|fri|satur|sun)days\b", "weekly"),
    (r"\bevery\s+month\b|\bmonthly\b", "monthly"),
]

# Cadences the data model cannot express. recurrence is one of daily, weekly
# or monthly, so each of these gets rounded to something else and produces a
# confidently wrong series. Saying so beats approximating silently.


# Cadences the data model cannot express. recurrence is one of daily, weekly
# or monthly, so each of these gets rounded to something else and produces a
# confidently wrong series. Saying so beats approximating silently.
_UNSUPPORTED_CADENCE = [
    (r"\bevery\s+other\b|\bfortnight|\bbi-?weekly\b|\balternate\s+\w+days?\b",
     "every other week"),
    (r"\b(twice|three times|3 times|two times)\s+(a|per)\s+(week|day|month)\b",
     "more than once a period"),
    (r"\bevery\s+(weekday|week\s?day)\b", "weekdays only"),
    (r"\bevery\s+\w+day\s+and\s+\w+day\b", "two days a week"),
]

# "until" names the boundary you stop at; "through"/"including" keep the day.
# English is genuinely ambiguous — this is the project's reading, applied
# everywhere rather than guessed per sentence.


# "until" names the boundary you stop at; "through"/"including" keep the day.
# English is genuinely ambiguous — this is the project's reading, applied
# everywhere rather than guessed per sentence.
_INCLUSIVE_END = r"\b(through|thru|including|inclusive|up to and including|end of)\b"


_EXCLUSIVE_END = r"\b(until|till|til|up to|up until|before)\b"


_EVENING_WORDS = re.compile(
    r"\b(dinner|drinks?|beer|pub|bar|party|pregame|pizza|kems|movie|cinema|"
    r"show|concert|tonight|evening|night|maariv|mincha)\b", re.I)

# Words that name no particular thing; a calendar full of "meeting" cannot be
# read back. Step 6 consumes this via is_placeholder_title().


# Words that name no particular thing; a calendar full of "meeting" cannot be
# read back. Step 6 consumes this via is_placeholder_title().
_CONTENTLESS_TITLES = {
    "event", "events", "meeting", "meetings", "set meeting", "appointment",
    "activity", "session", "thing", "item", "task", "reminder",
}


_EMPTY_NOUNS = {"event", "events", "activity", "thing", "item"}


_WEEKDAY_WORDS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4,
    "saturday": 5, "sunday": 6,
    "mon": 0, "tue": 1, "tues": 1, "wed": 2, "thu": 3, "thur": 3, "thurs": 3,
    "fri": 4, "sat": 5, "sun": 6,
}


def end_is_exclusive(text: str) -> bool:
    """Does this sentence's end-date word exclude the day it names?"""
    t = text.lower()
    if re.search(_INCLUSIVE_END, t):
        return False
    return bool(re.search(_EXCLUSIVE_END, t))


def named_weekdays(text: str) -> set:
    return {n for w, n in _WEEKDAY_WORDS.items() if re.search(rf"\b{w}s?\b", text)}


def unsupported_cadence(text: str) -> "str | None":
    for pat, label in _UNSUPPORTED_CADENCE:
        if re.search(pat, text):
            return label
    return None


def at_times(text: str) -> set:
    """Times introduced by "at" — i.e. when something STARTS."""
    out: set = set()
    t = text.lower().replace(".", ":")
    for m in re.finditer(r"\bat\s+(?:around\s+|about\s+|roughly\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm|a:m|p:m)?\b", t):
        h, mm, ap = int(m.group(1)), m.group(2) or "00", (m.group(3) or "").replace(":", "")
        if h > 24:
            continue
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
        out.add(f"{h % 24:02d}:{mm}")
        if not ap and h <= 12:                      # bare hour: both readings
            out.add(f"{(h + 12) % 24:02d}:{mm}")
    return out


def spoken_times(text: str) -> set:
    """All clock times a command mentions, as HH:MM (both readings for bare hours)."""
    out: set = set()
    t = text.lower().replace(".", ":")
    for m in re.finditer(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a:m|p:m)?\b", t):
        h, mm, ap = int(m.group(1)), m.group(2) or "00", (m.group(3) or "").replace(":", "")
        if h > 24:
            continue
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
        out.add(f"{h % 24:02d}:{mm}")
        if not ap and h <= 12:
            out.add(f"{(h + 12) % 24:02d}:{mm}")
    for m in re.finditer(r"\b(\d{2})(\d{2})\b", t):          # 1930, 0915
        h, mm = int(m.group(1)), m.group(2)
        if h < 24 and int(mm) < 60:
            out.add(f"{h:02d}:{mm}")
    if "noon" in t:
        out.add("12:00")
    if "midnight" in t:
        out.add("00:00")
    return out


def is_placeholder_title(title: str, cfg) -> bool:
    """Would this title be useless in a calendar? ("meeting", "event with X")"""
    t = (title or "").strip().lower().strip(" .-")
    if not t:
        return True
    configured = {k.lower() for k in getattr(cfg.nlu, "event_keywords", [])}
    if t in _CONTENTLESS_TITLES | configured:
        return True
    first, _, rest = t.partition(" ")
    return bool(rest) and first in _EMPTY_NOUNS and \
        rest.split(" ", 1)[0] in ("with", "for", "to", "on", "at", "about", "re")


def bare_hour_pm(transcript: str, hhmm: str) -> "str | None":
    """'Kems tomorrow at 8' → 20:00. A bare hour 1–8 is far more often PM in
    calendar speech; 7–8 only when evening words are present."""
    m = re.match(r"(\d{2}):(\d{2})", hhmm or "")
    if not m:
        return None
    h = int(m.group(1))
    if not (1 <= h <= 8):
        return None
    tl = transcript.lower()
    if re.search(rf"\b{h}(?::\d{{2}})?\s*(?:am|a\.m\.)\b", tl) or \
            re.search(rf"\b0?{h}:\d{{2}}\b(?!\s*pm)", tl) and re.search(rf"\b(?:0{h}|{h + 12}):", tl):
        return None
    if re.search(rf"\b{h}(?::\d{{2}})?\s*(?:pm|p\.m\.)\b", tl):
        return None
    if not re.search(rf"\b(?:at\s+)?{h}(?::\d{{2}})?\b", tl):
        return None
    if h <= 6 or _EVENING_WORDS.search(tl):
        return f"{h + 12:02d}:{m.group(2)}"
    return None


# ---------------------------------------------------------------------------
# The observance gate (new — the one rule that REFUSES rather than repairs)
# ---------------------------------------------------------------------------
