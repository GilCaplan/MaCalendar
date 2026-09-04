"""The orchestrator: track selection, the needs_edit gate, honest refusals,
the offline queue, and the trivial filter.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import assistant.engine as engine
import assistant.engine.generate as generate
import assistant.stt.vocab as vocab_mod
from assistant.engine.state import EngineState, Item
from assistant.exceptions import OllamaUnavailableError


@pytest.fixture
def cfg():
    return engine.load_config()


def _fake_registry(monkeypatch, results):
    registry = MagicMock()

    def _get(name):
        cls = MagicMock()
        cls.return_value.execute.side_effect = results.get(name, ["done"])
        return cls

    registry.get.side_effect = _get
    monkeypatch.setattr(generate, "get_registry", lambda: registry)
    return registry


# --- trivial ---------------------------------------------------------------

def test_a_false_start_is_ignored_and_not_remembered():
    out = engine.run_transcript("execute", source="test")
    assert out["parse"] == "ignored"
    assert out["memory_id"] is None
    assert out["actions"] == []


# --- track selection -------------------------------------------------------

def test_confident_rules_take_the_fast_track(monkeypatch, cfg):
    rr = SimpleNamespace(confidence=0.97, missing_slots=[],
                         intents=[("query_schedule", SimpleNamespace())])
    rp = MagicMock()
    rp.analyze.return_value = rr
    monkeypatch.setattr(generate, "_get_rule_parser", lambda: rp)
    _fake_registry(monkeypatch, {"query_schedule": ["all clear"]})

    out = engine.run_transcript("what do I have today", source="test")
    assert out["parse"] == "fast"


def test_unconfident_rules_take_the_deep_track(monkeypatch):
    rr = SimpleNamespace(confidence=0.30, missing_slots=["start_time"], intents=[])
    rp = MagicMock()
    rp.analyze.return_value = rr
    monkeypatch.setattr(generate, "_get_rule_parser", lambda: rp)
    parser = MagicMock()
    parser.parse.return_value = [("create_event", SimpleNamespace(title="x"))]
    parser.parse_with_context.side_effect = Exception("no context parse")
    parser.last_llm_ms = 3
    parser.last_examples_used = 0
    parser.last_raw_response = ""
    monkeypatch.setattr(generate, "_get_parser", lambda cfg: parser)
    _fake_registry(monkeypatch, {"create_event": ["made it"]})

    out = engine.run_transcript("do the thing with the stuff sometime", source="test")
    assert out["parse"] == "deep"
    assert out["actions"] == ["create_event"]


# --- the needs_edit gate ---------------------------------------------------

def _doubtful_vocab(monkeypatch):
    monkeypatch.setattr(vocab_mod, "apply_vocab", lambda text, source=None: (text, []))
    fake = MagicMock()
    fake.suggestions.return_value = [{"word": "noa", "suggestion": "Noa"}]
    monkeypatch.setattr(vocab_mod, "get_vocab", lambda: fake)


def test_gate_fires_only_for_capable_clients_with_the_setting_on(monkeypatch, cfg):
    _doubtful_vocab(monkeypatch)
    monkeypatch.setattr(cfg.engine, "confirm_transcript", True)
    monkeypatch.setattr(engine, "load_config", lambda: cfg)

    out = engine.run_transcript("call noa tomorrow at nine", source="test",
                                supports_edit=True)
    assert out["parse"] == "needs_edit"
    assert out["actions"] == []
    assert out["needs_edit"]


def test_gate_never_fires_for_an_old_client(monkeypatch, cfg):
    _doubtful_vocab(monkeypatch)
    monkeypatch.setattr(cfg.engine, "confirm_transcript", True)
    monkeypatch.setattr(engine, "load_config", lambda: cfg)
    rr = SimpleNamespace(confidence=0.97, missing_slots=[],
                         intents=[("query_schedule", SimpleNamespace())])
    rp = MagicMock()
    rp.analyze.return_value = rr
    monkeypatch.setattr(generate, "_get_rule_parser", lambda: rp)
    _fake_registry(monkeypatch, {"query_schedule": ["all clear"]})

    out = engine.run_transcript("call noa tomorrow at nine", source="test",
                                supports_edit=False)
    assert out["parse"] != "needs_edit"


def test_gate_off_means_best_guess(monkeypatch, cfg):
    _doubtful_vocab(monkeypatch)
    monkeypatch.setattr(cfg.engine, "confirm_transcript", False)
    monkeypatch.setattr(engine, "load_config", lambda: cfg)
    rr = SimpleNamespace(confidence=0.97, missing_slots=[],
                         intents=[("query_schedule", SimpleNamespace())])
    rp = MagicMock()
    rp.analyze.return_value = rr
    monkeypatch.setattr(generate, "_get_rule_parser", lambda: rp)
    _fake_registry(monkeypatch, {"query_schedule": ["all clear"]})

    out = engine.run_transcript("call noa tomorrow at nine", source="test",
                                supports_edit=True)
    assert out["parse"] != "needs_edit"


# --- honest refusals -------------------------------------------------------

def test_a_blocked_item_is_reported_never_silent(monkeypatch, cfg):
    _fake_registry(monkeypatch, {})
    st = EngineState(raw_text="gym saturday", text="gym saturday")
    st.items = [Item(id="item_1", kind="event", text="gym saturday",
                     action="create_event",
                     intent=SimpleNamespace(title="gym session"),
                     blocked="that lands on Shabbat (Saturday, Sep 5)")]
    engine._commit(st, cfg)
    assert any("didn't book" in m and "Shabbat" in m for m in st.messages)
    assert st.executed == []


# --- offline queue ---------------------------------------------------------

def test_llm_offline_queues_the_command(monkeypatch):
    monkeypatch.setattr(generate, "fast_propose", lambda state, cfg: False)
    monkeypatch.setattr(generate, "run",
                        lambda state, cfg: (_ for _ in ()).throw(
                            OllamaUnavailableError("Ollama offline at localhost")))

    out = engine.run_transcript("book squash with Yuval next thursday at 8", source="test")
    assert out["parse"] == "error"
    assert "offline" in out["message"].lower() or "saved" in out["message"].lower()
    assert out.get("pending_id") is not None


# --- the gate's learning loop ----------------------------------------------

@pytest.fixture
def scratch_vocab(monkeypatch, tmp_path):
    """A private vocabulary store, so learning tests cannot touch the shared
    scratch one other tests read."""
    import assistant.stt.vocab as vocab_module
    path = str(tmp_path / "vocab.json")
    store = vocab_module.VocabStore(path=path)
    monkeypatch.setattr(vocab_module, "get_vocab", lambda: store)
    monkeypatch.setattr(vocab_module, "VOCAB_PATH", path)
    return store


def test_a_saved_edit_becomes_an_alias(scratch_vocab):
    from assistant.engine import transcript
    pairs = transcript.learn_from_edit("call noga tomorrow at nine",
                                       "call Noa tomorrow at nine")
    assert pairs == [("noga", "Noa")]
    entry = next(e for e in scratch_vocab.entries if e.word == "Noa")
    assert "noga" in [a.lower() for a in entry.aliases]


def test_an_untouched_resubmit_whitelists_after_two_confirms(scratch_vocab):
    from assistant.engine import transcript
    text = "meet Moxie at the park tomorrow"
    assert transcript.confirm_unchanged(text) == []          # first confirm
    promoted = transcript.confirm_unchanged(text)            # second
    assert promoted == ["Moxie"]
    assert any(e.word == "Moxie" for e in scratch_vocab.entries)
    # And the gate stays quiet about it from now on.
    assert not any(s["heard"] == "Moxie" for s in scratch_vocab.suggestions(text))


def test_the_endpoint_learns_and_bypasses_the_gate(scratch_vocab, monkeypatch, cfg):
    monkeypatch.setattr(cfg.engine, "confirm_transcript", True)
    monkeypatch.setattr(engine, "load_config", lambda: cfg)
    import assistant.api.server as server
    monkeypatch.setattr(server, "load_config", lambda *a, **k: cfg)
    rr = SimpleNamespace(confidence=0.97, missing_slots=[],
                         intents=[("query_schedule", SimpleNamespace())])
    rp = MagicMock()
    rp.analyze.return_value = rr
    monkeypatch.setattr(generate, "_get_rule_parser", lambda: rp)
    _fake_registry(monkeypatch, {"query_schedule": ["all clear"]})

    app = server.create_app()
    client = app.test_client()
    body = client.post("/voice/text", json={
        "transcript": "call Noa tomorrow", "source": "test",
        "edited_from": "call noga tomorrow", "supports_edit": True,
    }).get_json()
    # The edit taught the alias AND the resubmission was not re-gated.
    assert body["parse"] != "needs_edit"
    entry = next(e for e in scratch_vocab.entries if e.word == "Noa")
    assert "noga" in [a.lower() for a in entry.aliases]


# --- step 0: intake coalescing ---------------------------------------------

def test_coalesce_wraps_within_budget():
    got = engine.coalesce(["gym tomorrow at 7am", "buy milk"], max_tokens=300)
    assert got == ['("gym tomorrow at 7am")and("buy milk")']


def test_coalesce_overflow_runs_sequentially():
    texts = ["a" * 400, "b" * 400, "c" * 400]
    got = engine.coalesce(texts, max_tokens=150)
    assert got == texts                       # each too big to share a batch


def test_coalesce_single_input_is_unwrapped():
    assert engine.coalesce(["just one thing"], max_tokens=300) == ["just one thing"]


def test_the_wrapper_round_trips_through_segment(cfg):
    from assistant.engine import segment
    batch = engine.coalesce(["gym tomorrow at 7am", "buy milk"], max_tokens=300)[0]
    st = EngineState(raw_text=batch, text=batch)
    segment.run(st, cfg)
    assert [it.text for it in st.items] == ["gym tomorrow at 7am", "buy milk"]


def test_repeated_attempt_messages_fold_into_one(monkeypatch):
    """A loop-back that fails the same way each attempt must apologise once,
    not once per re-entry (found live: three identical "couldn't read"s)."""
    from assistant.exceptions import ParseError
    monkeypatch.setattr(generate, "fast_propose", lambda state, cfg: False)

    def failing_run(state, cfg):
        state.messages.append("Sorry, I couldn't read this part: “x”.")
        return state

    monkeypatch.setattr(generate, "run", failing_run)
    import assistant.engine.crosscheck as crosscheck

    def always_missing(state, cfg):
        from assistant.engine.state import CheckFinding
        state.findings = [CheckFinding(type="missing", item_id=None,
                                       detail="d", blamed_stage="segment")]
        return state

    monkeypatch.setattr(crosscheck, "run", always_missing)
    out = engine.run_transcript("add christmas thing to calendar", source="test")
    assert out["message"].count("couldn't read") == 1


def test_a_task_kind_item_never_parses_to_nothing(monkeypatch, cfg):
    from assistant.engine.state import EngineState, Item
    parser = MagicMock()
    parser.parse.return_value = [("unknown", SimpleNamespace())]
    parser.last_llm_ms = 1
    parser.last_examples_used = 0
    parser.last_raw_response = ""
    monkeypatch.setattr(generate, "_get_parser", lambda c: parser)
    monkeypatch.setattr(generate, "_get_rule_parser", lambda: None)
    st = EngineState(raw_text="x", text="x")
    st.items = [Item(id="item_1", kind="task", text="submit the Haxaga grades")]
    generate.run(st, cfg)
    assert st.items[0].action == "create_todo"
    assert st.items[0].intent.titles == ["submit the Haxaga grades"]
