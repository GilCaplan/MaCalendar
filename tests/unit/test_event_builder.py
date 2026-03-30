"""Unit tests for the calendar event builder."""

import pytest

from assistant.actions.calendar.event_builder import build_event_payload
from assistant.actions.calendar.intent import CalendarIntent
from assistant.exceptions import EventBuildError


def _make_intent(**kwargs) -> CalendarIntent:
    defaults = dict(
        title="Team standup",
        date="2026-04-01",
        start_time="09:00",
        end_time="09:30",
    )
    defaults.update(kwargs)
    return CalendarIntent(**defaults)


def test_basic_payload_has_required_keys():
    payload = build_event_payload(_make_intent(), "America/New_York")
    assert "subject" in payload
    assert "start" in payload
    assert "end" in payload
    assert payload["subject"] == "Team standup"


def test_timezone_applied():
    payload = build_event_payload(_make_intent(), "Europe/London")
    assert payload["start"]["timeZone"] == "Europe/London"
    assert payload["end"]["timeZone"] == "Europe/London"


def test_iso_datetime_assembled_correctly():
    payload = build_event_payload(_make_intent(date="2026-04-01", start_time="14:30", end_time="15:00"), "UTC")
    assert payload["start"]["dateTime"] == "2026-04-01T14:30:00"
    assert payload["end"]["dateTime"] == "2026-04-01T15:00:00"


def test_attendees_with_emails():
    intent = _make_intent(attendees=["alice@example.com", "bob@example.com"])
    payload = build_event_payload(intent, "UTC")
    assert len(payload["attendees"]) == 2
    addresses = [a["emailAddress"]["address"] for a in payload["attendees"]]
    assert "alice@example.com" in addresses


def test_attendees_name_only_blank_email():
    intent = _make_intent(attendees=["Alice"])
    payload = build_event_payload(intent, "UTC")
    assert payload["attendees"][0]["emailAddress"]["address"] == ""
    assert payload["attendees"][0]["emailAddress"]["name"] == "Alice"


def test_no_attendees_omits_key():
    intent = _make_intent(attendees=[])
    payload = build_event_payload(intent, "UTC")
    assert "attendees" not in payload


def test_location_included():
    intent = _make_intent(location="Conference Room A")
    payload = build_event_payload(intent, "UTC")
    assert payload["location"]["displayName"] == "Conference Room A"


def test_no_location_omits_key():
    intent = _make_intent()
    payload = build_event_payload(intent, "UTC")
    assert "location" not in payload


def test_description_included():
    intent = _make_intent(description="Discuss Q2 roadmap")
    payload = build_event_payload(intent, "UTC")
    assert payload["body"]["content"] == "Discuss Q2 roadmap"


def test_end_before_start_wraps_to_next_day():
    # e.g. 23:30 → 00:30 (overnight)
    intent = _make_intent(start_time="23:30", end_time="00:30")
    payload = build_event_payload(intent, "UTC")
    from datetime import datetime
    end_dt = datetime.fromisoformat(payload["end"]["dateTime"])
    start_dt = datetime.fromisoformat(payload["start"]["dateTime"])
    assert end_dt > start_dt


def test_invalid_date_raises_event_build_error():
    intent = _make_intent(date="not-a-date")
    with pytest.raises(EventBuildError):
        build_event_payload(intent, "UTC")
