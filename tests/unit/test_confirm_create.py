"""The confirm-create gate (DEVQA Q9, Gil 2026-09-07).

"should i add yoga to my calendar tomorrow?" must neither auto-create nor be
silently dropped. Both failures were real: `should` is absent from validate's
`_QUESTION_START`, so that sentence booked yoga outright, while "what if i
booked town hall for the 3rd?" matched the rule and vanished without a word.

The gate mirrors the transcript gate exactly — the client declares it can ask
(`supports_confirm`), the engine stops before commit and hands back a
ready-to-POST proposal, and an old client that declares nothing keeps today's
behaviour.

Everything here drives the Flask TEST CLIENT, never localhost:8080 — a live
POST is served by the running assistant.api, which holds the real stores
(tests/conftest.py refuses it).
"""

from __future__ import annotations

import pytest

from assistant.engine import _confirm_proposal, _create_spec
from assistant.engine.segmentation.old_seg.segment import is_interrogative_create
from assistant.engine.state import EngineState, Item
from assistant.engine.decompose_validate import stage as _validate


# ---------------------------------------------------------------------------
# The reader: what counts as a question about creating something
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "should i add yoga to my calendar tomorrow?",
    "what if i booked town hall for the 3rd?",
    "do you think i should schedule the dentist on friday?",
    "how about we put lunch with Tal at 1?",
    "shall i add a gym session tomorrow morning",      # STT dropped the "?"
    "would it be worth blocking out thursday afternoon?",
])
def test_reads_as_a_question_about_creating(text):
    assert is_interrogative_create(text)


@pytest.mark.parametrize("text", [
    "add yoga to my calendar tomorrow",               # a plain instruction
    "can you add yoga tomorrow?",                     # a request, not a musing
    "could you book the dentist on friday?",          # ditto, politely
    "what's on my calendar friday?",                  # a query, no create verb
    "should i call my mother?",                       # a question, nothing to book
    "do i have a meeting tomorrow?",                  # a schedule question
    "",
])
def test_not_a_question_about_creating(text):
    assert not is_interrogative_create(text)


# ---------------------------------------------------------------------------
# Step 4 holds the intent instead of dropping it — but only when asked to
# ---------------------------------------------------------------------------

def _event_state(text, supports_confirm=True):
    from assistant.actions.calendar.intent import CalendarIntent
    from assistant.engine import load_config

    state = EngineState(raw_text=text, text=text, source="test",
                        supports_confirm=supports_confirm)
    state.items = [Item(id="item_1", kind="event", text=text,
                        action="create_event",
                        intent=CalendarIntent(title="Yoga", date="2099-01-02",
                                              start_time="07:00", end_time="08:00"))]
    return state, load_config()


def test_interrogative_create_is_held_not_dropped():
    state, cfg = _event_state("should i add yoga to my calendar tomorrow?")
    _validate.run_objects(state, cfg)

    assert state.items[0].intent is not None, "the parse must survive to be offered"
    assert state.items[0].slots.get("confirm_create") is True
    assert any(f.rule == "interrogative_create_asks_first" for f in state.fixes)


def test_old_client_keeps_todays_behaviour():
    """No supports_confirm ⇒ deep decides on its own, exactly as before."""
    state, cfg = _event_state("should i add yoga to my calendar tomorrow?",
                              supports_confirm=False)
    _validate.run_objects(state, cfg)

    assert not state.items[0].slots.get("confirm_create")
    assert state.items[0].intent is not None   # "should" was never in _QUESTION_START


def test_a_plain_instruction_is_untouched():
    state, cfg = _event_state("add yoga to my calendar tomorrow")
    _validate.run_objects(state, cfg)

    assert not state.items[0].slots.get("confirm_create")
    assert state.items[0].intent is not None


def test_a_question_inside_a_compound_does_not_hold_the_command():
    """A confirmation holds everything, so it only fires when the question IS
    the command — otherwise the gym booking would wait on a yoga dialog."""
    from assistant.actions.calendar.intent import CalendarIntent

    state, cfg = _event_state("should i add yoga tomorrow?")
    state.items.append(Item(
        id="item_2", kind="event", text="book gym at 7",
        action="create_event",
        intent=CalendarIntent(title="Gym", date="2099-01-02",
                              start_time="07:00", end_time="08:00")))
    _validate.run_objects(state, cfg)

    assert not state.items[0].slots.get("confirm_create")
    assert state.items[1].intent is not None, "the booking still runs"


# ---------------------------------------------------------------------------
# The proposal is a body POST /events and POST /todos already accept
# ---------------------------------------------------------------------------

def test_event_proposal_is_a_postable_body():
    from assistant.actions.calendar.intent import CalendarIntent

    item = Item(id="item_1", kind="event", text="x", action="create_event",
                intent=CalendarIntent(title="Yoga", date="2099-01-02",
                                      start_time="07:00", end_time="08:00",
                                      attendees=["Tal", "Ravid"]))
    specs = _create_spec(item)

    assert len(specs) == 1
    spec = specs[0]
    assert spec["kind"] == "event"
    assert {"title", "date", "start_time", "end_time"} <= set(spec["body"])
    # The column is a string; POST /events writes what it is handed.
    assert spec["body"]["attendees"] == "Tal, Ravid"
    assert "Yoga" in spec["summary"]


def test_todo_proposal_is_a_postable_body():
    from assistant.actions.todo.intent import CreateTodoIntent

    item = Item(id="item_1", kind="task", text="x", action="create_todo",
                intent=CreateTodoIntent(titles=["Call the vet"], due_date="2099-01-02"))
    spec = _create_spec(item)[0]

    assert spec["kind"] == "todo"
    assert spec["body"]["title"] == "Call the vet"
    assert spec["body"]["list_name"] == "today"
    assert spec["body"]["client_token"].startswith("confirm-todo-")


def test_every_task_in_a_list_is_offered():
    """A to-do intent can carry several titles; offering only the first would
    be exactly the silent drop this gate exists to prevent."""
    from assistant.actions.todo.intent import CreateTodoIntent

    item = Item(id="item_1", kind="task", text="x", action="create_todo",
                intent=CreateTodoIntent(titles=["milk", "eggs", "bread"]))
    specs = _create_spec(item)

    assert [s["body"]["title"] for s in specs] == ["milk", "eggs", "bread"]
    tokens = {s["body"]["client_token"] for s in specs}
    assert len(tokens) == 3, "one idempotency key per task, not one for all"


def test_an_unpostable_proposal_falls_back_to_creating_nothing():
    """No title ⇒ no body ⇒ no dialog offering something we cannot POST. The
    honest answer is the pre-ruling one: the question creates nothing."""
    item = Item(id="item_1", kind="event", text="x", action="create_event",
                intent=object())     # nothing a body can be built from
    item.slots["confirm_create"] = True
    state = EngineState(raw_text="x", text="x", supports_confirm=True)
    state.items = [item]

    assert _confirm_proposal(state) is None
    assert state.items[0].intent is None


# ---------------------------------------------------------------------------
# The orchestrator short-circuit and the endpoint, through the test client
# ---------------------------------------------------------------------------

@pytest.fixture
def client(registry_with_real_actions):
    from assistant.api.server import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture
def confirming_engine(monkeypatch):
    """Stub steps 2-5 so the gate is exercised without a model: the words are
    a question about creating something, and the parse is a create."""
    from assistant.actions.calendar.intent import CalendarIntent
    from assistant.engine.fastrule import objects as _generate

    def fake_deep(state, cfg):
        state.items = [Item(id="item_1", kind="event", text=state.text,
                            action="create_event",
                            intent=CalendarIntent(title="Yoga", date="2099-01-02",
                                                  start_time="07:00",
                                                  end_time="08:00"))]
        _validate.run_objects(state, cfg)

    # the orchestrator is object-based (Q7): the deep parse lives on the
    # Engine singleton itself — the stage-list wrapper was removed
    # 2026-09-08 and its two methods re-homed onto Engine
    import assistant.engine as _e
    monkeypatch.setattr(_e._engine, "parse", fake_deep)
    monkeypatch.setattr(_generate, "fast_propose", lambda state, cfg: False)
    monkeypatch.setattr("assistant.engine._crosscheck.run",
                        lambda state, cfg: state)
    return fake_deep


def _ask(client, **extra):
    body = {"transcript": "should i add yoga to my calendar tomorrow?",
            "source": "test", "supports_confirm": True}
    body.update(extra)
    return client.post("/voice/text", json=body).get_json()


def test_the_question_comes_back_as_a_proposal(client, confirming_engine):
    data = _ask(client)

    assert data["parse"] == "confirm_create"
    assert data["actions"] == []
    assert data["confirm_token"]
    assert len(data["proposal"]) == 1
    assert data["proposal"][0]["kind"] == "event"
    assert "Yoga" in data["message"]


def test_without_supports_confirm_nothing_is_held(client, confirming_engine):
    data = _ask(client, supports_confirm=False)

    assert data["parse"] != "confirm_create"
    assert "confirm_token" not in data
    assert data["actions"] == ["create_event"], "it executed, as it did before"


def _yoga_rows(client, date: str):
    """Count through the API, so what the test sees is what a client sees.
    The date is read off the created row: step 4 pins "tomorrow" to a real
    date, which is exactly what the proposal is supposed to carry."""
    return [e for e in client.get(f"/events?date={date}").get_json()
            if e["title"] == "Yoga"]


def test_yes_creates_it_once_even_on_a_double_tap(client, confirming_engine):
    data = _ask(client)
    token = data["confirm_token"]
    day = data["proposal"][0]["body"]["date"]
    before = len(_yoga_rows(client, day))

    first = client.post("/voice/confirm",
                        json={"confirm_token": token, "accept": True}).get_json()
    second = client.post("/voice/confirm",
                         json={"confirm_token": token, "accept": True}).get_json()

    assert first["accepted"] is True and first["created"], first
    assert first["refresh"] == "events"
    assert second["duplicate"] is True
    assert second["created"] == first["created"], "the same row, not a second one"
    assert len(_yoga_rows(client, day)) == before + 1


def test_no_creates_nothing_and_files_the_verdict(client, confirming_engine):
    from assistant.intent.memory import FEEDBACK_REJECTED, get_memory

    data = _ask(client)
    day = data["proposal"][0]["body"]["date"]
    before = len(_yoga_rows(client, day))

    answer = client.post("/voice/confirm",
                         json={"confirm_token": data["confirm_token"],
                               "accept": False}).get_json()

    assert answer["accepted"] is False
    assert answer["created"] == []
    assert len(_yoga_rows(client, day)) == before
    if data.get("memory_id") is not None:
        assert get_memory().get(data["memory_id"])["feedback"] == FEEDBACK_REJECTED


def test_an_expired_token_says_so(client, confirming_engine, monkeypatch):
    import assistant.api.server as server

    token = _ask(client)["confirm_token"]
    # Age it past the TTL rather than sleeping through it.
    with server._confirm_lock:
        server._confirm_store[token]["expires"] = 0.0

    r = client.post("/voice/confirm", json={"confirm_token": token, "accept": True})

    assert r.status_code == 404
    assert "expired" in r.get_json()["error"].lower()


def test_an_unknown_token_is_a_404(client):
    r = client.post("/voice/confirm",
                    json={"confirm_token": "no-such-token", "accept": True})
    assert r.status_code == 404


def test_a_missing_token_is_a_400(client):
    r = client.post("/voice/confirm", json={"accept": True})
    assert r.status_code == 400
