"""Deleting the event that was actually named.

"cancel the meeting with Ima" left the parser with no slots at all, so the
assistant answered "I couldn't find…" instead of deleting anything: noun
chunking hands back a bare "meeting", and delete throws away bare calendar words
because they name no particular event. The person is what identifies the event
here, so the title has to keep it.

Deleting is destructive, so the other half of the deal matters just as much: a
title that still names nobody in particular must leave the slots empty rather
than let a delete run on criteria that could match somebody else's event.
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


def delete_slots(parser, transcript: str) -> dict:
    return parser.analyze(transcript, current_view="month").raw_slots.get(
        "delete_event", {})


def match_title(parser, transcript: str) -> str:
    return delete_slots(parser, transcript).get("match_title", "")


@pytest.mark.parametrize("said, expected", [
    ("cancel the meeting with Ima",    "meeting with ima"),
    ("delete the meeting with Shaul",  "meeting with shaul"),
    ("cancel lunch with Tal tomorrow", "lunch with tal"),
    ("delete the meeting with Ima and Tal", "meeting with ima and tal"),
])
def test_the_person_stays_in_the_delete_title(parser, said, expected):
    assert match_title(parser, said).lower() == expected


@pytest.mark.parametrize("said, expected", [
    ("cancel the technion lecture",  "technion lecture"),
    ("delete the gym on thursday",   "gym"),
    ("cancel my dentist appointment", "dentist appointment"),
])
def test_a_title_that_names_itself_is_kept_as_it_was(parser, said, expected):
    assert match_title(parser, said).lower() == expected


def test_a_day_still_comes_through_alongside_the_title(parser):
    slots = delete_slots(parser, "delete the gym on thursday")
    assert slots.get("match_date")


@pytest.mark.parametrize("said", [
    "cancel the meeting",
    "cancel the lecture",
    "cancel the meeting with the dentist",
    "cancel the meeting with my mom",
])
def test_a_title_naming_nobody_is_refused_rather_than_guessed(parser, said):
    """A needle this broad could delete any meeting, so nothing is deleted."""
    assert not match_title(parser, said)


def test_a_time_alone_can_still_pick_the_event(parser):
    """"delete the event at 6pm" identifies one event without naming it."""
    slots = delete_slots(parser, "delete the event at 6pm")
    assert slots.get("match_start_time") == "18:00"
    assert not slots.get("match_title")


# ---------------------------------------------------------------------------
# End to end: what the parser produces has to find the right row
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("MACALENDAR_DB", str(tmp_path / "cal.db"))
    import assistant.db as _db
    # The singleton is _db_instance; assigning _db._db just made a stray
    # attribute and left get_db() handing back the session-wide database.
    monkeypatch.setattr(_db, "_db_instance", None)
    from assistant.actions.calendar.intent import CalendarIntent
    database = _db.get_db()
    today = dt.date.today()
    for title, offset, start in [("Meeting with Shaul", 1, "10:00"),
                                 ("Meeting with Ima", 2, "10:00"),
                                 ("Gym", 3, "06:00")]:
        database.create_event(CalendarIntent(
            title=title, date=(today + dt.timedelta(days=offset)).isoformat(),
            start_time=start, end_time="23:00"))
    return database


def test_the_parsed_title_finds_the_named_meeting(parser, db):
    from assistant.actions.calendar.action import _find_event
    slots = delete_slots(parser, "cancel the meeting with Ima")
    found = _find_event(db, slots.get("match_title", ""),
                        slots.get("match_date"), slots.get("match_start_time"))
    assert found is not None and found["title"] == "Meeting with Ima"


def test_a_nameless_delete_finds_nothing_to_delete(parser, db):
    from assistant.actions.calendar.action import _find_event
    slots = delete_slots(parser, "cancel the meeting")
    assert _find_event(db, slots.get("match_title", ""),
                       slots.get("match_date"),
                       slots.get("match_start_time")) is None
