"""PATCH refuses to silently overwrite a newer edit (events and tasks).

Both devices write to the same database, so "edit an event on your phone while
disconnected, edit the same event on the Mac, reconnect" used to end with the
phone's queued change quietly winning and the Mac's edit gone. A client can now
quote the `updated_at` it was working from and be told when it is stale.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MACALENDAR_DB", str(tmp_path / "cal.db"))
    import assistant.db as _db
    _db._db = None
    from assistant.api.server import create_app
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def _event(client) -> dict:
    r = client.post("/events", json={"title": "Lunch", "date": "2026-09-01",
                                     "start_time": "13:00", "end_time": "14:00"})
    assert r.status_code == 201, r.get_data(as_text=True)
    return client.get(f"/events/{r.get_json()['id']}").get_json()


def test_an_edit_from_the_version_you_saw_is_applied(client):
    event = _event(client)
    r = client.patch(f"/events/{event['id']}",
                     json={"title": "Lunch with Shaul", "base_updated_at": event["updated_at"]})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert client.get(f"/events/{event['id']}").get_json()["title"] == "Lunch with Shaul"


def test_an_edit_from_a_stale_version_is_refused(client):
    event = _event(client)
    # someone edits it on the Mac in the meantime
    client.patch(f"/events/{event['id']}", json={"title": "Lunch (moved)"})

    r = client.patch(f"/events/{event['id']}",
                     json={"title": "Lunch with Shaul", "base_updated_at": event["updated_at"]})

    assert r.status_code == 409
    assert r.get_json()["current"]["title"] == "Lunch (moved)"
    # and the Mac's version survived
    assert client.get(f"/events/{event['id']}").get_json()["title"] == "Lunch (moved)"


def test_an_edit_without_a_base_version_still_works(client):
    """Existing callers (the Mac's own UI, the voice pipeline) don't send one."""
    event = _event(client)
    r = client.patch(f"/events/{event['id']}", json={"title": "Renamed"})
    assert r.status_code == 200
    assert client.get(f"/events/{event['id']}").get_json()["title"] == "Renamed"


def test_base_updated_at_is_not_written_as_a_field(client):
    event = _event(client)
    client.patch(f"/events/{event['id']}",
                 json={"title": "Kept", "base_updated_at": event["updated_at"]})
    fresh = client.get(f"/events/{event['id']}").get_json()
    assert "base_updated_at" not in fresh
    assert fresh["title"] == "Kept"


# ---------------------------------------------------------------------------
# Tasks get the same protection
# ---------------------------------------------------------------------------

def _todo(client) -> dict:
    r = client.post("/todos", json={"title": "Buy challah"})
    assert r.status_code in (200, 201), r.get_data(as_text=True)
    todo_id = r.get_json()["id"]
    return next(t for t in client.get("/todos").get_json() if t["id"] == todo_id)


def test_a_task_edit_from_the_version_you_saw_is_applied(client):
    todo = _todo(client)
    r = client.patch(f"/todos/{todo['id']}",
                     json={"title": "Buy challah and wine", "base_updated_at": todo["updated_at"]})
    assert r.status_code == 200, r.get_data(as_text=True)


def test_a_task_edit_from_a_stale_version_is_refused(client):
    todo = _todo(client)
    client.patch(f"/todos/{todo['id']}", json={"title": "Buy challah (Dad is bringing it)"})

    r = client.patch(f"/todos/{todo['id']}",
                     json={"title": "Buy challah and wine", "base_updated_at": todo["updated_at"]})

    assert r.status_code == 409
    assert r.get_json()["current"]["title"] == "Buy challah (Dad is bringing it)"
