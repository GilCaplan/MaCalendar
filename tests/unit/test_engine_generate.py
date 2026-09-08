"""Step 5 — the generate stage's deterministic fallbacks.

The LLM paths live in tests/integration (Ollama guard); what's pinned here
is the honest-failure ladder: a task-kind item never parses to nothing
(task_fallback, run 12), and an event-kind item whose words literally ask
for an event/reminder with a grounded when becomes a default-titled event
instead of dying unknown (event_fallback, cycle 5) — while everything less
grounded stays unknown, because a guessed event is worse than none.
"""

from __future__ import annotations

import pytest

import assistant.engine.fastrule.objects as generate
from assistant.engine import load_config
from assistant.engine.state import EngineState, Item


@pytest.fixture
def cfg():
    return load_config()


@pytest.fixture
def dead_llm(monkeypatch):
    """Both the per-item parse and the event-kind retry come back empty."""
    monkeypatch.setattr(generate, "_parse_item", lambda item, state, cfg: [])
    class _P:
        def parse(self, text):
            return []
    monkeypatch.setattr(generate, "_get_parser", lambda cfg: _P())


def _run(text, kind, cfg):
    st = EngineState(raw_text=text, text=text)
    st.items = [Item(id="item_1", kind=kind, text=text)]
    return generate.run(st, cfg).items[0]


# --- event_fallback: the grounded default-title event (cycle 5) ----------

def test_literal_event_ask_with_time_becomes_default_event(dead_llm, cfg):
    it = _run("Set reminder for three o'clock", "event", cfg)
    assert it.action == "create_event"
    assert it.intent.title == "Reminder"
    assert it.intent.start_time == "15:00"


def test_literal_event_ask_with_date_becomes_default_event(dead_llm, cfg):
    it = _run("please set event on Tuesday", "event", cfg)
    assert it.action == "create_event"
    assert it.intent.title == "Event"
    assert it.intent.date is not None


def test_no_literal_ask_stays_unknown(dead_llm, cfg):
    # An event-kind item with a when but no event/reminder word: defaulting a
    # title here would be invention, not grounding.
    it = _run("something on Tuesday maybe", "event", cfg)
    assert it.action is None


def test_no_grounded_when_stays_unknown(dead_llm, cfg):
    # The ask is literal but names no date and no time - a time is never
    # guessed (hypothesis #2's risk clause).
    it = _run("can you set an event for me", "event", cfg)
    assert it.action is None


def test_task_kind_never_takes_the_event_fallback(dead_llm, cfg):
    # "reminder" in a task-kind item's words must not turn it into an event;
    # the task fallback owns task-kind items.
    it = _run("set a reminder note for three o'clock", "task", cfg)
    assert it.action == "create_todo"


# --- task_fallback: pinned (run 12) --------------------------------------

def test_task_kind_item_never_parses_to_nothing(dead_llm, cfg):
    it = _run("submit the Haxaga grades", "task", cfg)
    assert it.action == "create_todo"
    assert it.intent.titles == ["submit the Haxaga grades"]


# --- fast-path generic-target veto (cycle 6) ------------------------------

class _StubRR:
    def __init__(self, intents):
        self.confidence = 0.95
        self.intents = intents
        self.missing_slots = []


class _StubParser:
    def __init__(self, intents):
        self._rr = _StubRR(intents)

    def analyze(self, text, current_view=None):
        return self._rr


def _fast(monkeypatch, cfg, text, intents):
    from types import SimpleNamespace
    monkeypatch.setattr(generate, "_get_rule_parser",
                        lambda: _StubParser(intents))
    st = EngineState(raw_text=text, text=text)
    return generate.fast_propose(st, cfg), st


def test_mutation_on_a_bare_ask_noun_routes_deep(monkeypatch, cfg):
    from types import SimpleNamespace
    ok, st = _fast(monkeypatch, cfg, "set reminder at 3 pm",
                   [("update_todo", SimpleNamespace(match_title="reminder"))])
    assert ok is False          # the deep track (event_fallback) owns this


def test_mutation_on_a_real_target_still_fast(monkeypatch, cfg):
    from types import SimpleNamespace
    ok, st = _fast(monkeypatch, cfg, "move the gym meeting",
                   [("update_event", SimpleNamespace(match_title="gym meeting"))])
    assert ok is True and st.parse_path == "fast"


def test_creations_never_vetoed(monkeypatch, cfg):
    from types import SimpleNamespace
    ok, st = _fast(monkeypatch, cfg, "reminder tomorrow 9am take pills",
                   [("create_event", SimpleNamespace(title="take pills"))])
    assert ok is True


# --- invention guard (cycle 7) --------------------------------------------

def test_fabricated_title_is_dropped():
    from types import SimpleNamespace
    st = EngineState(raw_text="x", text="x")
    item = Item(id="item_1", kind="event",
                text="new scenario, time or calendar to new list")
    got = [("create_event", SimpleNamespace(title="New Event"))]
    assert generate._guard_inventions(got, item, st) == []
    assert any("invention_guard" in str(f) for f in st.fixes)


def test_paraphrased_title_survives_via_stems():
    from types import SimpleNamespace
    st = EngineState(raw_text="x", text="x")
    item = Item(id="item_1", kind="event", text="meet Dana tomorrow at noon")
    got = [("create_event", SimpleNamespace(title="Meeting with Dana"))]
    assert generate._guard_inventions(got, item, st) == got


def test_grounded_title_untouched():
    from types import SimpleNamespace
    st = EngineState(raw_text="x", text="x")
    item = Item(id="item_1", kind="event", text="dentist on Wednesday at noon")
    got = [("create_event", SimpleNamespace(title="Dentist"))]
    assert generate._guard_inventions(got, item, st) == got


def test_non_event_actions_never_guarded():
    from types import SimpleNamespace
    st = EngineState(raw_text="x", text="x")
    item = Item(id="item_1", kind="task", text="whatever garble")
    got = [("create_todo", SimpleNamespace(titles=["Unrelated Words"]))]
    assert generate._guard_inventions(got, item, st) == got


def test_the_deep_track_does_not_undo_a_refusal(monkeypatch, cfg):
    """The engine audit's headline: the per-item path re-implemented the
    commit test with BOTH gate layers omitted, so an item the front door had
    vetoed was re-committed here. A generic target must survive the deep
    track as an honest "I couldn't find it", not a guess."""
    from assistant.engine import run_transcript
    out = run_transcript("remove my reminder", source="test")
    assert out["actions"] == [], out
