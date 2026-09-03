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
