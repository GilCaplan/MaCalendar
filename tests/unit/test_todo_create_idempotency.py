"""Creating a task twice must not make two tasks — including for callers that
send no idempotency key at all.

`client_token` (2026-09-06) made tokened creates idempotent, and the partial
unique index enforces it. But the index is `WHERE client_token != ''`, so a
token-less POST was still an unconditional insert — and the caller that had
been duplicating "buy groceries" turned out to send no token: it was the unit
suite's own HUD revert click reaching the live server (see
`test_no_live_api_writes.py`). Between them, 45 copies of one task.

These cover the second net: an open task, spelled the same, in the same list,
created moments ago, is read as a replay of that create rather than a new ask.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MACALENDAR_DB", str(tmp_path / "todo_idempotency.db"))
    import assistant.db as _db
    monkeypatch.setattr(_db, "_db_instance", None)
    from assistant.api.server import create_app
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def _open_titles(client, title="buy groceries"):
    rows = client.get("/todos?list=all&include_completed=true").get_json()
    return [r for r in rows if r["title"] == title and not r["completed"]]


# ---------------------------------------------------------------------------
# The hole: no token at all
# ---------------------------------------------------------------------------

def test_a_tokenless_repeat_returns_the_same_task(client):
    """The exact shape the HUD's revert POST sent, nine times over one evening."""
    body = {"title": "buy groceries", "list_name": "today"}
    first = client.post("/todos", json=body)
    assert first.status_code == 201
    first_id = first.get_json()["id"]

    replay = client.post("/todos", json=body)
    assert replay.status_code == 200, "a token-less replay created a second task"
    assert replay.get_json() == {"id": first_id, "duplicate": True,
                                 "reason": "recent-identical"}
    assert len(_open_titles(client)) == 1


def test_nine_tokenless_replays_still_leave_one_task(client):
    """The live count, reproduced: nine POSTs, one row."""
    body = {"title": "buy groceries", "list_name": "today"}
    ids = {client.post("/todos", json=body).get_json()["id"] for _ in range(9)}
    assert len(ids) == 1
    assert len(_open_titles(client)) == 1


@pytest.mark.parametrize("spelling", ["buy groceries", "Buy Groceries",
                                      "  buy   groceries  "])
def test_the_fingerprint_ignores_case_and_spacing(client, spelling):
    client.post("/todos", json={"title": "buy groceries"})
    assert client.post("/todos", json={"title": spelling}).status_code == 200
    assert len(_open_titles(client)) == 1


# ---------------------------------------------------------------------------
# ...without swallowing a real second ask
# ---------------------------------------------------------------------------

def test_a_different_task_is_never_folded_in(client):
    client.post("/todos", json={"title": "buy groceries"})
    assert client.post("/todos", json={"title": "buy challah"}).status_code == 201
    assert len(_open_titles(client)) == 1
    assert len(_open_titles(client, "buy challah")) == 1


def test_the_same_title_in_another_list_is_its_own_task(client):
    client.post("/todos", json={"title": "buy groceries", "list_name": "today"})
    second = client.post("/todos", json={"title": "buy groceries",
                                         "list_name": "general"})
    assert second.status_code == 201


def test_re_adding_a_task_you_ticked_off_works(client):
    """Completing is the signal that the task is done with — asking again is a
    new ask, however soon it comes."""
    first = client.post("/todos", json={"title": "buy groceries"}).get_json()["id"]
    client.patch(f"/todos/{first}/toggle")
    again = client.post("/todos", json={"title": "buy groceries"})
    assert again.status_code == 201
    assert again.get_json()["id"] != first


def test_the_window_is_configurable_and_zero_turns_it_off(client, monkeypatch):
    from assistant.api import server as _server
    cfg = _server.load_config()
    monkeypatch.setattr(cfg.todo, "duplicate_window_seconds", 0)
    monkeypatch.setattr(_server, "load_config", lambda *a, **k: cfg)
    client.post("/todos", json={"title": "buy groceries"})
    assert client.post("/todos", json={"title": "buy groceries"}).status_code == 201


def test_an_explicit_token_still_wins(client):
    """Two genuinely different asks that happen to say the same thing are told
    apart by their tokens — the precise key beats the fingerprint."""
    a = client.post("/todos", json={"title": "buy groceries", "client_token": "ask-a"})
    b = client.post("/todos", json={"title": "buy groceries", "client_token": "ask-b"})
    assert a.status_code == 201 and b.status_code == 201
    assert a.get_json()["id"] != b.get_json()["id"]


# ---------------------------------------------------------------------------
# The db helper on its own
# ---------------------------------------------------------------------------

def test_find_recent_open_todo_honours_the_window(client, monkeypatch):
    import assistant.db as _db
    db = _db.get_db()
    db.create_todo(title="buy groceries", list_name="today")
    assert db.find_recent_open_todo("buy groceries", "today", 120) is not None
    assert db.find_recent_open_todo("buy groceries", "today", 0) is None
    assert db.find_recent_open_todo("buy groceries", "general", 120) is None
    assert db.find_recent_open_todo("", "today", 120) is None
