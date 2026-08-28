"""POST /timers/<id>/sessions — logging time you forgot to start the timer for.

The Mac's Timer tab has always had "Log past time…"; the phone had no way to
add a session at all (only to view and delete them), so a forgotten timer was
simply lost time. These tests cover the endpoint that closes that gap.
"""
from __future__ import annotations

import datetime

import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MACALENDAR_DB", str(tmp_path / "cal.db"))
    import assistant.db as _db
    _db._db = None                      # drop any singleton from another test
    from assistant.api.server import create_app
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def _timer(client) -> int:
    r = client.post("/timers", json={"title": "Thesis", "hourly_rate": 60, "currency": "ILS"})
    assert r.status_code in (200, 201), r.get_json()
    return r.get_json()["id"]


def test_logs_a_finished_past_session(client):
    tid = _timer(client)
    now = datetime.datetime.now().astimezone()
    start = (now - datetime.timedelta(hours=2)).isoformat()

    r = client.post(f"/timers/{tid}/sessions",
                    json={"start_time": start, "end_time": now.isoformat(), "title": "forgot to start"})

    assert r.status_code == 201
    body = r.get_json()
    assert body["title"] == "forgot to start"
    assert body["running"] is False
    assert body["seconds"] == pytest.approx(7200, abs=2)


def test_session_shows_up_in_the_list(client):
    tid = _timer(client)
    now = datetime.datetime.now().astimezone()
    client.post(f"/timers/{tid}/sessions",
                json={"start_time": (now - datetime.timedelta(minutes=30)).isoformat(),
                      "end_time": now.isoformat()})

    sessions = client.get(f"/timers/{tid}/sessions").get_json()["sessions"]
    assert len(sessions) == 1
    assert sessions[0]["seconds"] == pytest.approx(1800, abs=2)


def test_end_time_may_be_omitted_for_a_still_running_session(client):
    tid = _timer(client)
    start = (datetime.datetime.now().astimezone() - datetime.timedelta(minutes=5)).isoformat()

    body = client.post(f"/timers/{tid}/sessions", json={"start_time": start}).get_json()

    assert body["running"] is True
    assert not body["end_time"]


def test_start_time_is_required(client):
    tid = _timer(client)
    r = client.post(f"/timers/{tid}/sessions", json={})
    assert r.status_code == 400
    assert "start_time" in r.get_json()["error"]
