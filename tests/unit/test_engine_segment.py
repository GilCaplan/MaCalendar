"""Step 2 — segmentation. The pipeline's single point of failure, so the
traps live here: names joined by "and", idioms, verb lists, batched input.

The LLM is faked throughout (unit tests need no model); the live behaviour is
gated on scripts/engine_stage_check.py --stage segment.
"""

from __future__ import annotations

import pytest

import assistant.engine.llm as engine_llm
import assistant.engine.segment as segment
from assistant.engine import load_config
from assistant.engine.state import EngineState


@pytest.fixture
def cfg():
    return load_config()


def _seg(text: str, cfg) -> EngineState:
    st = EngineState(raw_text=text, text=text)
    return segment.run(st, cfg)


# --- deterministic splits: free, and never wrong ---------------------------

def test_bracket_batch_splits(cfg):
    st = _seg("[gym tomorrow at 7am] [lunch with Tal at noon]", cfg)
    assert [it.text for it in st.items] == ["gym tomorrow at 7am", "lunch with Tal at noon"]
    assert "[" not in st.text            # brackets must not reach a title


def test_coalescing_wrapper_splits(cfg):
    st = _seg('("gym tomorrow at 7am")and("buy milk")', cfg)
    assert len(st.items) == 2
    assert st.items[1].text == "buy milk"


def test_single_item_ids_and_kinds(cfg):
    st = _seg("what do I have this week", cfg)
    assert [it.id for it in st.items] == ["item_1"]
    assert st.items[0].kind == "review"


def test_task_phrasing_is_read_as_task(cfg):
    st = _seg("remind me to call Noa about the trip", cfg)
    assert st.items[0].kind == "task"


# --- the LLM path: consulted only when the words suggest compounding -------

def test_no_compound_hint_means_no_llm_call(cfg, monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("LLM must not be consulted for a simple command")
    monkeypatch.setattr(engine_llm, "call_json", _boom)
    st = _seg("book the dentist tomorrow morning at nine thirty", cfg)
    assert len(st.items) == 1


def test_llm_split_of_two_independent_requests(cfg, monkeypatch):
    monkeypatch.setattr(engine_llm, "call_json", lambda *a, **k: ({"items": [
        {"kind": "event", "text": "book gym tomorrow at 7am"},
        {"kind": "task", "text": "remind me to buy milk"},
    ]}, 5))
    st = _seg("book gym tomorrow at 7am and remind me to buy milk", cfg)
    assert [(it.kind, it.text) for it in st.items] == [
        ("event", "book gym tomorrow at 7am"), ("task", "remind me to buy milk")]
    assert st.llm_ms == 5


def test_a_fragment_split_is_refused(cfg, monkeypatch):
    """A 'split' that produced a lone word is the model imagining structure —
    under-split bias says one item beats two broken ones."""
    monkeypatch.setattr(engine_llm, "call_json", lambda *a, **k: ({"items": [
        {"kind": "event", "text": "meeting with Tal and Ravid at Kems tomorrow"},
        {"kind": "event", "text": "Ravid"},
    ]}, 5))
    st = _seg("meeting with Tal and Ravid at Kems tomorrow evening", cfg)
    assert len(st.items) == 1


def test_llm_answering_one_item_keeps_one_item(cfg, monkeypatch):
    monkeypatch.setattr(engine_llm, "call_json", lambda *a, **k: ({"items": [
        {"kind": "event", "text": "meeting with Tal and Ravid at Kems tomorrow evening"},
    ]}, 5))
    st = _seg("meeting with Tal and Ravid at Kems tomorrow evening", cfg)
    assert len(st.items) == 1


def test_llm_failure_never_loses_the_command(cfg, monkeypatch):
    def _offline(*a, **k):
        raise RuntimeError("ollama offline")
    monkeypatch.setattr(engine_llm, "call_json", _offline)
    st = _seg("book gym tomorrow at 7am and remind me to buy milk", cfg)
    assert len(st.items) == 1            # one item is always a legitimate reading


def test_loop_back_mistakes_reach_the_prompt(cfg, monkeypatch):
    seen = {}

    def _capture(cfg_, system, user, schema=None):
        seen["system"] = system
        return {"items": []}, 1

    monkeypatch.setattr(engine_llm, "call_json", _capture)
    st = EngineState(raw_text="x", text="book gym at 7 and remind me to buy milk")
    st.mistakes = ["you merged two independent requests"]
    segment.run(st, cfg)
    assert "merged two independent requests" in seen["system"]
