"""Integration tests for the Flask API server — the "built-in API" the iOS app
(and any external test harness) uses to submit a transcript and get it parsed +
executed without going through a mic at all: `POST /voice/text`.

Real SQLite DB (temp file, real schema/migrations — same CalendarDB class
production uses), real ActionRegistry, real RuleBasedParser. The only things
mocked are `load_config` (avoid requiring a real config.yaml on disk),
`get_db` (point at an isolated temp DB instead of ~/.assistant_tools/calendar.db),
and Pipeline._append_nlu_log/_append_scenario_bug (server.py's _run_transcript
spawns these unconditionally in a background thread on every call — without
mocking them, every test run appends real entries to the git-tracked
DOCUMENTATION/*.md files). No network calls happen for rule-fast-path
transcripts — the background LLM verify thread it spawns fails closed (catches
its own exceptions, defaults to "ok") when Ollama isn't reachable, so it can't
fail these tests.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import assistant.api.server as server_module
from assistant.db import CalendarDB
from assistant.pipeline import Pipeline


@pytest.fixture(autouse=True)
def no_markdown_writes(monkeypatch):
    """Prevent tests from appending to the real DOCUMENTATION/*.md files.

    server.py's _run_transcript fires these as background threads on every
    call (success or failure) — without this, every test run pollutes the
    git-tracked NLU tracking / scenario bug logs with synthetic test transcripts.
    """
    monkeypatch.setattr(Pipeline, "_append_nlu_log", MagicMock())
    monkeypatch.setattr(Pipeline, "_append_scenario_bug", MagicMock())


def _register_real_actions(isolated_registry) -> None:
    """Populate the (test-cleared) shared ActionRegistry state with the real
    action classes. ActionRegistry uses a Borg shared-state pattern, so any
    ActionRegistry() instance (including the one server.py's _get_registry()
    constructs internally) sees these. Explicit registration, not
    `import assistant.actions.calendar` — that module is only ever imported
    once per process, so its @register decorators won't re-fire on a later
    test after conftest's autouse isolated_registry fixture has cleared state.
    """
    from assistant.actions.calendar.action import (
        CreateEventAction, UpdateEventAction, DeleteEventAction, QueryScheduleAction
    )
    from assistant.actions.todo.action import (
        CreateTodoAction, CompleteTodoAction, DeleteTodoAction, UpdateTodoAction,
        QueryTodoAction, AddSubtaskAction, CompleteSubtaskAction, DeleteSubtaskAction,
    )
    from assistant.actions.clarify import ClarifyAction

    for cls in [
        CreateEventAction, UpdateEventAction, DeleteEventAction, QueryScheduleAction,
        CreateTodoAction, CompleteTodoAction, DeleteTodoAction, UpdateTodoAction,
        QueryTodoAction, AddSubtaskAction, CompleteSubtaskAction, DeleteSubtaskAction,
        ClarifyAction,
    ]:
        isolated_registry._actions[cls.action_name] = cls


@pytest.fixture
def app_client(tmp_path, monkeypatch, sample_config, isolated_registry):
    """Flask test client wired to an isolated temp DB and a mocked config."""
    _register_real_actions(isolated_registry)

    db = CalendarDB(path=str(tmp_path / "test_calendar.db"))
    # Two separate bindings need patching: server.py's REST routes call its own
    # top-level `from assistant.db import get_db` import, while every Action's
    # execute() does its own deferred `from assistant.db import get_db` re-import
    # at call time — that resolves against assistant.db.get_db directly, a
    # different binding than server_module.get_db. Miss either one and requests
    # silently read/write the real ~/.assistant_tools/calendar.db instead.
    import assistant.db as db_module
    monkeypatch.setattr(db_module, "get_db", lambda: db)
    monkeypatch.setattr(server_module, "get_db", lambda: db)
    monkeypatch.setattr(server_module, "load_config", lambda *a, **kw: sample_config)

    # Reset module-level lazy singletons so each test gets a clean registry/parser
    # built against the mocked config, rather than reusing state from a prior test.
    monkeypatch.setattr(server_module, "_registry", None)
    monkeypatch.setattr(server_module, "_parser", None)
    monkeypatch.setattr(server_module, "_rule_parser", None)
    monkeypatch.setattr(server_module, "_stt", None)

    app = server_module.create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client, db


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def test_health_endpoint(app_client):
    client, db = app_client
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["db"] == db.path


# ---------------------------------------------------------------------------
# /voice/text — the text-only "skip STT" entry point
# ---------------------------------------------------------------------------

def test_voice_text_missing_transcript_returns_400(app_client):
    client, _ = app_client
    resp = client.post("/voice/text", json={})
    assert resp.status_code == 400


def test_voice_text_create_todo_rule_fast_path(app_client):
    client, db = app_client
    resp = client.post("/voice/text", json={"transcript": "buy milk"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert "create_todo" in data["actions"]
    assert data["parse"] == "rule"
    assert data["refresh"] == "todos"

    todos = db.get_todos(list_name=None, include_completed=True)
    assert any("milk" in t["title"].lower() for t in todos)


def test_voice_text_create_event_rule_fast_path(app_client):
    client, db = app_client
    resp = client.post("/voice/text", json={"transcript": "schedule a meeting tomorrow at 3pm"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert "create_event" in data["actions"]
    assert data["parse"] == "rule"
    assert data["refresh"] == "events"
    # A verify_token is issued for rule-path results (iOS polls it for corrections).
    assert "verify_token" in data


def test_voice_text_cross_domain_multi_action(app_client):
    """'Delete my grocery list and cancel my dentist appointment' — both actions
    executed and both refresh flags set (regression coverage for the multi-action
    combinatorial work in test_multi_action_scenarios.py, now through the real API).
    """
    client, db = app_client
    # Seed records to delete
    db.create_todo(title="grocery list", list_name="today", priority="none", due_date="", notes="")
    db.create_event_from_dict({
        "title": "dentist appointment", "date": "2026-01-01",
        "start_time": "09:00", "end_time": "10:00",
    })

    resp = client.post("/voice/text", json={
        "transcript": "delete my grocery list and cancel my dentist appointment"
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert set(data["actions"]) == {"delete_todo", "delete_event"}
    assert data["refresh"] == "both"


def test_voice_text_unknown_action_returns_message(app_client):
    """A transcript with no matching command shouldn't 500 — just report it couldn't parse."""
    client, _ = app_client
    resp = client.post("/voice/text", json={"transcript": "asdkjhaskjdh unrelated gibberish"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["actions"] == []


# ---------------------------------------------------------------------------
# Background verify token polling
# ---------------------------------------------------------------------------

def test_voice_verify_unknown_token_returns_404(app_client):
    client, _ = app_client
    resp = client.get("/voice/verify/not-a-real-token")
    assert resp.status_code == 404


def test_voice_verify_pending_before_ready(app_client):
    """Immediately after a rule-path response, the verify token exists but the
    background thread almost certainly hasn't finished — poll returns pending.
    """
    client, _ = app_client
    resp = client.post("/voice/text", json={"transcript": "buy milk"})
    token = resp.get_json().get("verify_token")
    assert token is not None
    poll = client.get(f"/voice/verify/{token}")
    assert poll.status_code == 200
    # Either still pending, or (rarely, if the background thread already failed
    # closed due to Ollama being unreachable) already resolved to ok=true.
    body = poll.get_json()
    assert body.get("pending") is True or body.get("ok") is True


# ---------------------------------------------------------------------------
# REST CRUD — events
# ---------------------------------------------------------------------------

def test_events_crud_roundtrip(app_client):
    client, _ = app_client

    create = client.post("/events", json={
        "title": "Standup", "date": "2026-05-01", "start_time": "09:00", "end_time": "09:30",
    })
    assert create.status_code == 201
    event_id = create.get_json()["id"]

    get_resp = client.get(f"/events/{event_id}")
    assert get_resp.status_code == 200
    assert get_resp.get_json()["title"] == "Standup"

    patch = client.patch(f"/events/{event_id}", json={"title": "Renamed Standup"})
    assert patch.status_code == 200
    assert client.get(f"/events/{event_id}").get_json()["title"] == "Renamed Standup"

    delete = client.delete(f"/events/{event_id}")
    assert delete.status_code == 200
    assert client.get(f"/events/{event_id}").status_code == 404


def test_event_create_missing_fields_returns_400(app_client):
    client, _ = app_client
    resp = client.post("/events", json={"title": "Incomplete"})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# REST CRUD — todos
# ---------------------------------------------------------------------------

def test_todos_crud_roundtrip(app_client):
    client, _ = app_client

    create = client.post("/todos", json={"title": "Buy flowers"})
    assert create.status_code == 201
    todo_id = create.get_json()["id"]

    listed = client.get("/todos?list=all").get_json()
    assert any(t["id"] == todo_id for t in listed)

    patch = client.patch(f"/todos/{todo_id}", json={"title": "Buy roses"})
    assert patch.status_code == 200
    listed = client.get("/todos?list=all").get_json()
    assert any(t["id"] == todo_id and t["title"] == "Buy roses" for t in listed)

    delete = client.delete(f"/todos/{todo_id}")
    assert delete.status_code == 200
    listed = client.get("/todos?list=all").get_json()
    assert not any(t["id"] == todo_id for t in listed)


def test_todo_create_missing_title_returns_400(app_client):
    client, _ = app_client
    resp = client.post("/todos", json={})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# API-key auth
# ---------------------------------------------------------------------------

def test_api_key_enforced_when_configured(tmp_path, monkeypatch, sample_config):
    from assistant.config import ApiConfig
    import assistant.db as db_module

    guarded_config = sample_config.model_copy(update={"api": ApiConfig(key="secret123")})
    db = CalendarDB(path=str(tmp_path / "test_calendar_auth.db"))
    monkeypatch.setattr(db_module, "get_db", lambda: db)
    monkeypatch.setattr(server_module, "get_db", lambda: db)
    monkeypatch.setattr(server_module, "load_config", lambda *a, **kw: guarded_config)
    monkeypatch.setattr(server_module, "_registry", None)
    monkeypatch.setattr(server_module, "_parser", None)
    monkeypatch.setattr(server_module, "_rule_parser", None)
    monkeypatch.setattr(server_module, "_stt", None)

    app = server_module.create_app()
    with app.test_client() as client:
        no_key = client.get("/events")
        assert no_key.status_code == 401

        with_key = client.get("/events", headers={"X-API-Key": "secret123"})
        assert with_key.status_code == 200

        wrong_key = client.get("/events", headers={"X-API-Key": "wrong"})
        assert wrong_key.status_code == 401
