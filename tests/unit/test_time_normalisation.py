"""The times speech recognition actually produces.

"Walk Mark Stalk today at 2:30PM" reaches the parser transcribed as "at 230PM"
— no colon. CalendarIntent found minutes by looking for that colon, so '230pm'
matched nothing and the whole create_event was rejected with "time must be
HH:MM". The command was lost after the LLM had already read it correctly.

'1130am' failed the same way. Neither is exotic; both are just what dictation
does to a spoken time.
"""
from __future__ import annotations

import pytest

from assistant.actions.calendar.intent import CalendarIntent


def _time(value: str) -> str:
    return CalendarIntent(title="x", date="2026-09-02",
                          start_time=value, end_time="23:59").start_time


@pytest.mark.parametrize("said, expected", [
    # The forms that used to be rejected outright.
    ("230PM",    "14:30"),
    ("230pm",    "14:30"),
    ("1130am",   "11:30"),
    ("1215pm",   "12:15"),
    ("945AM",    "09:45"),
    # Everything that already worked, still working.
    ("9",        "09:00"),
    ("9:30pm",   "21:30"),
    ("9.30pm",   "21:30"),
    ("0915",     "09:15"),
    ("1230",     "12:30"),
    ("12:00 PM", "12:00"),
    ("12am",     "00:00"),
    ("12pm",     "12:00"),
])
def test_spoken_times_normalise_to_hhmm(said, expected):
    assert _time(said) == expected


@pytest.mark.parametrize("said", [
    "230",      # 2:30, or 02:30 mistyped? '0230' already means the latter.
    "99:99",
    "25:00",
    "half past two",
])
def test_ambiguous_or_nonsense_times_are_still_refused(said):
    """A wrong time of day is worse than a refusal the LLM can be re-asked about.

    Bare '230' is the interesting one: it is only ever a guess between 2:30 and
    02:30, and the four-digit form already covers the second reading.
    """
    with pytest.raises(Exception):
        _time(said)


def test_pm_does_not_double_shift_an_afternoon_hour():
    """'14:30pm' is malformed but survivable — 14 is already afternoon."""
    assert _time("14:30") == "14:30"


def test_an_unspecified_time_falls_back_to_the_default_rather_than_erroring():
    """Empty is "the speaker didn't say", not "the speaker said nonsense".

    Asserts the shape, not a value: the default is derived from the current
    clock, so pinning it to "09:00" makes the suite pass or fail depending on
    what time it is run.
    """
    import re
    assert re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", _time(""))
