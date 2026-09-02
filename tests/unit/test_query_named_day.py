"""Asking about a named day must answer about that day.

"what do I have on friday" answered for *today*, confidently and via the rule
fast path, so no LLM ever saw it. Two causes stacked:

  • _SCOPE_PHRASES knows "today", "tomorrow" and "week" and nothing else, so
    "friday" matched no phrase and kept the default.
  • QueryScheduleIntent had nowhere to put a day anyway — scope was the only
    field, and its enum has three values. The LLM could not have expressed the
    right answer even when it knew it.

Found by asking the running assistant a question and reading the reply, which
is the only check that would have caught it: every layer was individually
behaving as written.
"""
from __future__ import annotations

import datetime as dt

import pytest

from assistant.actions.calendar.intent import CalendarIntent, QueryScheduleIntent


@pytest.fixture
def parser(registry_with_real_actions):
    # conftest's autouse isolated_registry empties the global registry before
    # every test, so the populated one has to come from a fixture.
    from assistant.intent.rule_parser import RuleBasedParser
    return RuleBasedParser(registry_with_real_actions)


def _slots(parser, said):
    return parser.analyze(said, current_view="month").raw_slots.get("query_schedule", {})


@pytest.mark.parametrize("said, weekday", [
    ("what do I have on friday", 4),
    ("what do I have friday", 4),
    ("what's on monday", 0),
    ("what do I have on sunday", 6),
])
def test_a_named_weekday_becomes_a_date(parser, said, weekday):
    got = _slots(parser, said).get("date")
    assert got, f"{said!r} produced no date"
    assert dt.date.fromisoformat(got).weekday() == weekday


@pytest.mark.parametrize("said, scope", [
    ("what do I have today", "today"),
    ("what do I have tomorrow", "tomorrow"),
    ("what do I have this week", "week"),
])
def test_the_relative_scopes_still_work(parser, said, scope):
    assert _slots(parser, said).get("scope") == scope


def test_a_week_query_carries_no_date(parser):
    """A week is a range, not a day — a date here would silently narrow it."""
    assert _slots(parser, "what do I have this week").get("date") is None


def test_a_named_day_beats_scope(registry_with_real_actions, sample_config,
                                 tmp_path, monkeypatch):
    """scope defaults to "today" and is always present, so date has to win.

    Takes sample_config rather than load_config(): config.yaml is gitignored,
    so calling it fails on CI for reasons that have nothing to do with dates.
    """
    monkeypatch.setenv("MACALENDAR_DB", str(tmp_path / "c.db"))
    from assistant.db import get_db

    db = get_db()
    friday = dt.date.today() + dt.timedelta(days=(4 - dt.date.today().weekday()) % 7 or 7)
    db.create_event(CalendarIntent(title="Threshold 9 km", date=friday.isoformat(),
                                   start_time="06:30", end_time="07:30"))
    db.create_event(CalendarIntent(title="Something today", date=dt.date.today().isoformat(),
                                   start_time="09:00", end_time="10:00"))

    action = registry_with_real_actions.get("query_schedule")()
    said_friday = action.execute(
        QueryScheduleIntent(scope="today", date=friday.isoformat()), sample_config)

    assert "Threshold 9 km" in said_friday
    assert "Something today" not in said_friday
