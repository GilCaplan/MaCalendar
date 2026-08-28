"""A spoken am/pm must survive the business-hours heuristic.

Bare hours 1–7 are read as afternoon, because "meeting at 3" almost always
means 3 PM. The guard that was meant to exempt an explicitly stated morning
time tested `\\b(am|a\\.m\\.)\\b` — but "7am" has no word boundary between the
digit and "am", and "a.m." doesn't end on one either. Both slipped through, so
"gym at 7am" was booked at 7 in the evening. Morning words got no say at all,
which put Shacharit at 7 PM.
"""
from __future__ import annotations

import pytest

from assistant.intent.rule_parser import RuleBasedParser


@pytest.fixture(scope="module")
def parser():
    import assistant.actions.calendar  # noqa: F401  — registers create_event
    import assistant.actions.todo      # noqa: F401
    from assistant.actions import registry
    return RuleBasedParser(registry)


def start_time(parser, transcript: str) -> str | None:
    return parser.analyze(transcript, current_view="month").raw_slots.get(
        "create_event", {}).get("start_time")


@pytest.mark.parametrize("said, expected", [
    ("add gym tomorrow at 7am",      "07:00"),
    ("add gym tomorrow at 7 am",     "07:00"),
    ("add gym tomorrow at 7 a.m.",   "07:00"),
    ("add gym tomorrow at 7:00 am",  "07:00"),
    ("add gym tomorrow at 7pm",      "19:00"),
    ("add gym tomorrow at 7p.m.",    "19:00"),
    ("add gym tomorrow at 12pm",     "12:00"),
    ("add gym tomorrow at 12am",     "00:00"),
])
def test_a_stated_meridiem_wins(parser, said, expected):
    assert start_time(parser, said) == expected


@pytest.mark.parametrize("said, expected", [
    ("add shacharit tomorrow at 7",  "07:00"),
    ("add breakfast tomorrow at 7",  "07:00"),
])
def test_morning_words_mean_morning(parser, said, expected):
    assert start_time(parser, said) == expected


@pytest.mark.parametrize("said, expected", [
    ("add meeting tomorrow at 3",           "15:00"),
    ("add dinner tomorrow at 7",            "19:00"),
    # the meridiem matcher must not fire on ordinary words containing a/m
    ("add meeting with Amit tomorrow at 3",  "15:00"),
    ("add exam tomorrow at 2",               "14:00"),
    ("add a meeting tomorrow at 4",          "16:00"),
])
def test_a_bare_afternoon_hour_is_still_pm(parser, said, expected):
    assert start_time(parser, said) == expected


# ---------------------------------------------------------------------------
# Time ranges
# ---------------------------------------------------------------------------

def times(parser, transcript: str) -> tuple[str | None, str | None]:
    slots = parser.analyze(transcript, current_view="month").raw_slots.get("create_event", {})
    return slots.get("start_time"), slots.get("end_time")


@pytest.mark.parametrize("said", [
    "add gym tomorrow from 9 to 10",
    "add meeting tomorrow from 2 to 3",
])
def test_a_bare_range_does_not_crash_the_parser(parser, said):
    """The recogniser returns a match with no resolution for these; dereferencing
    it raised an AttributeError that escaped the parser and killed the command
    rather than falling back to the LLM."""
    assert times(parser, said)[0] is not None


@pytest.mark.parametrize("said, start, end", [
    ("add lunch from 12 to 1 tomorrow",    "12:00", "13:00"),   # crossed noon
    ("add gym tomorrow from 9 to 10",      "09:00", "10:00"),
    ("add meeting tomorrow from 2 to 3",   "14:00", "15:00"),
    ("add gym tomorrow from 6 to 7pm",     "18:00", "19:00"),
    ("add gym tomorrow from 9am to 10am",  "09:00", "10:00"),
    ("add shift from 11pm to 2am",         "23:00", "02:00"),   # genuinely overnight
])
def test_a_range_never_ends_before_it_starts(parser, said, start, end):
    assert times(parser, said) == (start, end)
