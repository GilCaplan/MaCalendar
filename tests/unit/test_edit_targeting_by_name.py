"""Editing the right event when several look alike.

Two bugs made voice edits land on the wrong event — the worst failure this app
can have, because it happens silently:

  * "the meeting with Ima" came out of the parser as just "meeting", so the
    matcher scored a generic word and took the nearest meeting — Shaul's.
  * When a named event wasn't on the day given, the matcher fell back to "first
    event on that date", so "move the gym on Sunday" moved whatever else was
    there.
"""
from __future__ import annotations

import datetime as dt

import pytest

from assistant.intent.rule_parser import RuleBasedParser


@pytest.fixture(scope="module")
def parser():
    import assistant.actions.calendar  # noqa: F401
    import assistant.actions.todo      # noqa: F401
    from assistant.actions import registry
    return RuleBasedParser(registry)


def match_title(parser, transcript: str) -> str:
    return parser.analyze(transcript, current_view="month").raw_slots.get(
        "update_event", {}).get("match_title", "")


@pytest.mark.parametrize("said, expected", [
    ("change the meeting with Ima to 12",    "meeting with ima"),
    ("move the meeting with Shaul to 11",    "meeting with shaul"),
    ("move lunch with Tal to 2pm",           "lunch with tal"),
    ("rename the meeting with Tal to robotics sync", "meeting with tal"),
])
def test_the_person_stays_in_the_match_title(parser, said, expected):
    assert match_title(parser, said).lower() == expected


def test_a_title_without_a_person_is_unchanged(parser):
    assert match_title(parser, "move the gym to 7am").lower() == "gym"


# ---------------------------------------------------------------------------
# The matcher itself
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("MACALENDAR_DB", str(tmp_path / "cal.db"))
    import assistant.db as _db
    # The singleton is _db_instance; assigning _db._db just made a stray
    # attribute and left get_db() handing back the session-wide database,
    # so these read whatever other tests had written into it.
    monkeypatch.setattr(_db, "_db_instance", None)
    from assistant.actions.calendar.intent import CalendarIntent
    database = _db.get_db()
    today = dt.date.today()
    for title, offset, start in [("Meeting with Shaul", 1, "10:00"),
                                 ("Gym", 1, "18:00"),
                                 ("Meeting with Ima", 2, "10:00"),
                                 ("Gym", 3, "06:00")]:
        database.create_event(CalendarIntent(
            title=title, date=(today + dt.timedelta(days=offset)).isoformat(),
            start_time=start, end_time="23:00"))
    return database


def test_a_named_event_beats_a_nearer_one_with_a_generic_title(db):
    from assistant.actions.calendar.action import _find_event
    found = _find_event(db, "meeting with ima", None)
    assert found["title"] == "Meeting with Ima"


def test_naming_something_that_is_not_on_that_day_finds_nothing(db):
    """Rather than editing whatever else happens to be there."""
    from assistant.actions.calendar.action import _find_event
    day_with_no_gym = (dt.date.today() + dt.timedelta(days=2)).isoformat()
    assert _find_event(db, "gym", day_with_no_gym) is None


def test_a_generic_title_still_falls_back_to_the_day(db):
    from assistant.actions.calendar.action import _find_event
    day = (dt.date.today() + dt.timedelta(days=2)).isoformat()
    found = _find_event(db, "the event", day)
    assert found is not None and found["title"] == "Meeting with Ima"


def test_a_clock_time_in_the_title_is_not_a_name(db):
    """"move my 1pm meeting tomorrow" describes when, not what it is called, so
    the day still has to resolve it."""
    from assistant.actions.calendar.action import _find_event
    tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    found = _find_event(db, "my 1pm meeting", tomorrow)
    assert found is not None and found["title"] == "Meeting with Shaul"
