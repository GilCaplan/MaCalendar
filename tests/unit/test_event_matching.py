"""Unit tests for `_find_event` in assistant/actions/calendar/action.py — the
token-based fuzzy matcher that every voice update_event/delete_event command
depends on to find which event the user means. Previously untested despite
being one of the trickiest pieces of logic in the app: stop-word filtering,
generic-title fallback ("the event at 6pm"), anaphora resolution, and
date-mismatch recovery all live here.

Uses a real temp-file CalendarDB (not mocks) since the matcher queries the DB
directly via `db._conn()`.
"""
from __future__ import annotations

import datetime

import pytest

from assistant.actions.calendar.action import _find_event
from assistant.db import CalendarDB
from assistant.intent.context import context_memory


@pytest.fixture
def db(tmp_path) -> CalendarDB:
    return CalendarDB(path=str(tmp_path / "matching_test.db"))


def _add_event(db, title, date, start_time, end_time="10:00") -> int:
    return db.create_event_from_dict({
        "title": title, "date": date, "start_time": start_time, "end_time": end_time,
    })


# ---------------------------------------------------------------------------
# Basic fuzzy title matching
# ---------------------------------------------------------------------------

def test_exact_title_match(db):
    _add_event(db, "Dentist appointment", "2026-04-14", "09:00")
    result = _find_event(db, match_title="Dentist appointment", match_date=None)
    assert result["title"] == "Dentist appointment"


def test_partial_title_match_via_token_overlap(db):
    _add_event(db, "Meeting with Rina about progress", "2026-04-08", "17:15")
    result = _find_event(db, match_title="rina", match_date=None)
    assert result["title"] == "Meeting with Rina about progress"


def test_best_scoring_event_wins_among_multiple_candidates(db):
    _add_event(db, "Meeting with Adin", "2026-04-15", "14:00")
    _add_event(db, "Meeting with Ofir", "2026-04-15", "16:00")
    result = _find_event(db, match_title="meeting with ofir", match_date=None)
    assert result["title"] == "Meeting with Ofir"


def test_no_match_returns_none(db):
    _add_event(db, "Dentist appointment", "2026-04-14", "09:00")
    result = _find_event(db, match_title="quantum physics symposium", match_date=None)
    assert result is None


# ---------------------------------------------------------------------------
# Generic-title fallback: "the event at 6pm" shouldn't try to fuzzy-match
# the word "event" against real titles — it should look up by time instead.
# ---------------------------------------------------------------------------

def test_generic_title_with_time_falls_back_to_time_lookup(db):
    _add_event(db, "Team standup", "2026-04-14", "18:00")
    result = _find_event(db, match_title="event", match_date="2026-04-14", match_start_time="18:00")
    assert result["title"] == "Team standup"


def test_generic_title_alone_with_no_date_or_time_finds_nothing_useful(db):
    """'the meeting' with zero other context can't disambiguate among several —
    scored fuzzy matching still applies since there's no date/time to fall back to.
    """
    _add_event(db, "Standup", "2026-04-14", "09:00")
    result = _find_event(db, match_title="meeting", match_date=None)
    # "meeting" doesn't overlap with "Standup" at all — no match.
    assert result is None


# ---------------------------------------------------------------------------
# Date mismatch recovery — LLM/rule parser got the date wrong
# ---------------------------------------------------------------------------

def test_wrong_date_falls_back_to_closest_event_by_title(db):
    """If no event exists on the given date, search all events (by title match)
    instead of returning nothing.
    """
    _add_event(db, "Dentist appointment", "2026-04-14", "09:00")
    result = _find_event(db, match_title="dentist", match_date="2026-05-01")
    assert result["title"] == "Dentist appointment"


def test_wrong_date_with_no_title_match_returns_none(db):
    _add_event(db, "Dentist appointment", "2026-04-14", "09:00")
    result = _find_event(db, match_title="quantum physics", match_date="2026-05-01")
    assert result is None


# ---------------------------------------------------------------------------
# Empty title — pure date/time lookup
# ---------------------------------------------------------------------------

def test_empty_title_with_date_returns_first_event_that_day(db):
    _add_event(db, "First", "2026-04-14", "09:00")
    _add_event(db, "Second", "2026-04-14", "15:00")
    result = _find_event(db, match_title="", match_date="2026-04-14")
    assert result["title"] == "First"


def test_empty_title_and_no_date_returns_none(db):
    _add_event(db, "Dentist appointment", "2026-04-14", "09:00")
    result = _find_event(db, match_title="", match_date=None)
    assert result is None


# ---------------------------------------------------------------------------
# Anaphora resolution ("delete it", "cancel that")
# ---------------------------------------------------------------------------

def test_anaphor_resolves_via_context_memory(db):
    context_memory.reset()
    event_id = _add_event(db, "Dentist appointment", "2026-04-14", "09:00")
    context_memory.update_event(event_id, "Dentist appointment", "2026-04-14")

    result = _find_event(db, match_title="it", match_date=None)
    assert result["id"] == event_id
    context_memory.reset()


def test_anaphor_with_no_memory_returns_none(db):
    context_memory.reset()
    _add_event(db, "Dentist appointment", "2026-04-14", "09:00")
    result = _find_event(db, match_title="it", match_date=None)
    assert result is None


def test_anaphor_with_explicit_date_prefers_filter_over_memory(db):
    """'the event on Thursday at 6' — even with memory pointing elsewhere,
    an explicit date/time filter takes priority.
    """
    context_memory.reset()
    other_id = _add_event(db, "Old event", "2026-04-01", "10:00")
    context_memory.update_event(other_id, "Old event", "2026-04-01")

    thursday_event_id = _add_event(db, "Thursday thing", "2026-04-16", "18:00")
    result = _find_event(db, match_title="it", match_date="2026-04-16", match_start_time="18:00")
    assert result["id"] == thursday_event_id
    context_memory.reset()


# ---------------------------------------------------------------------------
# Start-time boost — a time match should outweigh a weak title overlap
# ---------------------------------------------------------------------------

def test_start_time_match_boosts_over_title_only_overlap(db):
    _add_event(db, "Team meeting notes", "2026-04-14", "10:00")
    _add_event(db, "Quick sync", "2026-04-14", "13:00")
    # "meeting at 1pm" — weak title overlap with the first event, but the second
    # event's start_time (13:00) should win via the time-match boost.
    result = _find_event(
        db, match_title="meeting", match_date="2026-04-14", match_start_time="13:00"
    )
    assert result["title"] == "Quick sync"
