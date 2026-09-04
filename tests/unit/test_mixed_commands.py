"""One sentence, several records — and they do not all take the same route.

Asked where the pages explain a command that makes both an event and a task,
the honest answer was to run one rather than reason about it. The result
corrected the page: a mixed command is answered by the rules alone, because an
event and a task are different actions with different slots and both fit at
once. Two *events* do not, because there is only one set of event slots.

That distinction is easy to lose in a refactor and impossible to notice from
the outside, so it is pinned here.
"""
from __future__ import annotations

import logging

import pytest


@pytest.fixture
def client(registry_with_real_actions, monkeypatch, tmp_path):
    # conftest swaps the global registry for a two-action dummy so unit tests
    # are not at the mercy of the real one; driving the server end to end needs
    # the real actions back, or every command parses to nothing.
    monkeypatch.setenv("MACALENDAR_NO_WARMUP", "1")
    # A database of our own. These commands really do create events and tasks,
    # and the scratch database is shared across the suite — writing "gym" into
    # it broke a test elsewhere that asserted exactly what a given day held.
    import assistant.db as dbmod
    monkeypatch.setattr(dbmod, "_db_instance", dbmod.CalendarDB(str(tmp_path / "c.db")))
    logging.disable(logging.INFO)
    from assistant.api import server
    app = server.create_app()
    app.config.update(TESTING=True)
    yield app.test_client()
    logging.disable(logging.NOTSET)


def _say(client, text):
    body = client.post("/voice/text", json={"transcript": text, "source": "test"}).get_json()
    actions = [a.get("action") if isinstance(a, dict) else a for a in (body.get("actions") or [])]
    return body, actions


def test_an_event_and_a_task_in_one_sentence_make_both(client):
    body, actions = _say(client, "book gym on tuesday at 7am and remind me to buy milk")
    assert actions == ["create_event", "create_todo"], actions
    assert "gym" in body["message"].lower() and "milk" in body["message"].lower(), (
        "both records should be named in the reply")


def test_a_mixed_command_is_answered_by_the_rules_alone(client):
    """The interesting part: it never reaches the model.

    An event and a task are different actions with different slots, so both fit
    in one pass. Two events would not — see below.
    """
    body, _ = _say(client, "book gym on tuesday at 7am and remind me to buy milk")
    assert body["parse"] == "fast", f"expected the fast track, got {body['parse']}"


def test_a_mixed_command_asks_the_client_to_refresh_both_surfaces(client):
    """A calendar that redrew and a task list that did not would be half-right."""
    body, _ = _say(client, "book gym on tuesday at 7am and remind me to buy milk")
    assert body["refresh"] == "both", body["refresh"]


import requests as _requests


def _ollama_running() -> bool:
    try:
        return _requests.get("http://localhost:11434/api/tags", timeout=3).status_code == 200
    except Exception:
        return False


@pytest.mark.skipif(not _ollama_running(),
                    reason="needs Ollama — the deep-track LLM segmentation of a shopping list")
def test_a_list_of_things_to_buy_makes_exactly_its_items(client):
    """"buy milk and buy bread" is two tasks — never one merged row, never an
    invented "buy groceries". The split is the engine's decompose stage now
    (one create per item, so feedback attaches to the right row); what is
    pinned here is the OUTCOME: exactly these rows, nothing merged."""
    _, actions = _say(client, "add buy milk and buy bread to my list")
    assert actions and set(actions) == {"create_todo"}, actions
    from assistant.db import get_db
    titles = sorted(t["title"].lower() for t in get_db().get_todos(include_completed=True))
    assert not any(" and " in t for t in titles), titles
    assert any("milk" in t for t in titles) and any("bread" in t for t in titles), titles


def test_every_record_from_one_sentence_is_written(client, tmp_path):
    """There is no half-executed command."""
    from assistant.db import get_db
    db = get_db()
    before_ev = len(db.get_events_for_month(2026, 9))
    before_td = len(db.get_todos())
    _say(client, "book gym on tuesday at 7am and remind me to buy milk")
    assert len(db.get_events_for_month(2026, 9)) > before_ev, "the event was not written"
    assert len(db.get_todos()) > before_td, "the task was not written"
