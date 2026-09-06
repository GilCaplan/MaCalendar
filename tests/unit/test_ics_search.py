"""The .ics export (import's symmetric half) and the /search endpoint."""

from __future__ import annotations

import pytest

from assistant.api.server import create_app
from assistant.db import get_db
from assistant.ics_export import event_to_ics, filename_for


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def event_id():
    db = get_db()
    eid = db.create_event_from_dict({
        "title": "Dentist, checkup; molar",
        "date": "2026-10-14", "start_time": "12:00", "end_time": "12:45",
        "location": "Clinic", "description": "bring card",
        "attendees": "Dana",
    })
    yield eid
    db.delete_event(eid)


def test_ics_has_the_event_and_escapes_punctuation(event_id):
    row = get_db().get_event(event_id)
    ics = event_to_ics(row)
    assert "BEGIN:VEVENT" in ics and ics.endswith("END:VCALENDAR\r\n")
    assert "DTSTART:20261014T120000" in ics
    assert "DTEND:20261014T124500" in ics
    assert "SUMMARY:Dentist\\, checkup\\; molar" in ics
    assert "LOCATION:Clinic" in ics
    assert "With: Dana" in ics          # attendees land in the description
    assert "RRULE" not in ics           # instances are rows; never an RRULE


def test_ics_endpoint_serves_a_calendar_file(client, event_id):
    r = client.get(f"/events/{event_id}.ics")
    assert r.status_code == 200
    assert r.mimetype == "text/calendar"
    assert "attachment" in r.headers["Content-Disposition"]
    assert filename_for(get_db().get_event(event_id)).endswith(".ics")


def test_ics_404_for_missing_event(client):
    assert client.get("/events/999999.ics").status_code == 404


def test_search_finds_events_and_todos(client, event_id):
    db = get_db()
    tid = db.create_todo("buy dental floss")
    try:
        r = client.get("/search?q=dent")
        assert r.status_code == 200
        body = r.get_json()
        assert any(e["id"] == event_id for e in body["events"])
        assert any(t["title"] == "buy dental floss" for t in body["todos"])
    finally:
        db.delete_todo(tid)


def test_search_rejects_tiny_queries(client):
    assert client.get("/search?q=a").status_code == 400
