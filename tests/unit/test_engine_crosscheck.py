"""Step 6 — extraction, deterministic diff, blame routing, loop-back, and the
background patch tiers. The LLM is faked throughout; the live gate is
scripts/engine_stage_check.py --stage crosscheck.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import assistant.engine as engine
import assistant.engine.llmjudge.llmjudge as crosscheck
import assistant.engine.generate.generate as generate
import assistant.engine.llm as engine_llm
from assistant.engine.state import EngineState, ExecutedAction, Item


@pytest.fixture
def cfg():
    return engine.load_config()


def _state_with(items, text="x"):
    st = EngineState(raw_text=text, text=text)
    st.items = items
    return st


def _event_item(id, title, text=""):
    return Item(id=id, kind="event", text=text or title, action="create_event",
                intent=SimpleNamespace(title=title))


def _task_item(id, title, text=""):
    return Item(id=id, kind="task", text=text or title, action="create_todo",
                intent=SimpleNamespace(title=title))


# --- extraction + diff ------------------------------------------------------

def test_all_asks_covered_means_no_findings(cfg, monkeypatch):
    monkeypatch.setattr(engine_llm, "call_json", lambda *a, **k: ({"asks": [
        {"kind": "event", "words": "gym on tuesday at 7am"},
        {"kind": "task", "words": "buy milk"},
    ]}, 4))
    st = _state_with([_event_item("item_1", "gym"),
                      _task_item("item_2", "buy milk")],
                     text="book gym on tuesday at 7am and remind me to buy milk")
    crosscheck.run(st, cfg)
    assert st.findings == []


def test_a_missing_ask_is_found_and_blamed_on_segment(cfg, monkeypatch):
    monkeypatch.setattr(engine_llm, "call_json", lambda *a, **k: ({"asks": [
        {"kind": "event", "words": "gym on tuesday at 7am"},
        {"kind": "task", "words": "buy milk"},
    ]}, 4))
    st = _state_with([_event_item("item_1", "gym")],
                     text="book gym on tuesday at 7am and remind me to buy milk")
    crosscheck.run(st, cfg)
    assert [f.type for f in st.findings] == ["missing"]
    assert st.findings[0].blamed_stage == "segment"
    assert any("buy milk" in m for m in st.mistakes)


def test_an_extra_production_is_found(cfg, monkeypatch):
    monkeypatch.setattr(engine_llm, "call_json", lambda *a, **k: ({"asks": [
        {"kind": "task", "words": "buy milk"},
    ]}, 4))
    st = _state_with([_task_item("item_1", "buy milk"),
                      _task_item("item_2", "buy groceries")],
                     text="add buy milk to my list")
    crosscheck.run(st, cfg)
    assert [f.type for f in st.findings] == ["extra"]
    assert st.findings[0].item_id == "item_2"


def test_no_model_means_no_findings_not_a_failure(cfg, monkeypatch):
    def _down(*a, **k):
        raise RuntimeError("offline")
    monkeypatch.setattr(engine_llm, "call_json", _down)
    st = _state_with([_event_item("item_1", "gym")], text="book gym")
    crosscheck.run(st, cfg)
    assert st.findings == []


def test_a_blocked_item_is_not_an_extra(cfg, monkeypatch):
    """A refusal already explained must not be double-reported as noise."""
    monkeypatch.setattr(engine_llm, "call_json", lambda *a, **k: ({"asks": []}, 4))
    it = _event_item("item_1", "gym session")
    it.blocked = "that lands on Shabbat"
    st = _state_with([it], text="gym saturday")
    crosscheck.run(st, cfg)
    assert st.findings == []


# --- foreground loop-back ---------------------------------------------------

def test_loop_back_reruns_segment_with_the_mistake(cfg, monkeypatch):
    """First pass merges two asks into one item; the cross-check notices the
    missing task; the re-run (with the mistake in the prompt) splits properly
    and the second check is clean.

    The input is one segment's deterministic clause tier declines (an event
    chain sharing a leading date), so the merge this scenario needs is the
    LLM tier's to make. With a plainly-coordinated command the parse now
    splits it correctly first time and there is no loop-back to observe.

    PINNED TO `old_seg` (2026-09-08). The loop-back can only be observed with a
    segmenter that can CHANGE ITS MIND on a re-run. FastSeg is deterministic and
    LLMSeg is off by default, so re-running segmentation on unchanged text
    returns the same items and there is nothing for the second pass to fix —
    the same reason `state.asked_fastrule` exists. This test covers the
    loop-back MECHANISM, so it runs against the implementation that has an LLM
    tier; `assistant/engine/segmentation/ARCHITECTURE.md` records that the
    mechanism is inert while LLMSeg is off.
    """
    import assistant.engine.segmentation as _seg
    monkeypatch.setattr(_seg, "IMPLEMENTATION", "old_seg")
    text = "tomorrow gym at 7 am and a meeting with Tal at 11"

    calls = {"n": 0}

    def scripted_llm(cfg_, system, user, schema=None):
        calls["n"] += 1
        if "split ONE voice command" in system:      # segment
            if "do not repeat them" in system:       # the retry, mistake attached
                return {"items": [
                    {"kind": "event", "text": "book gym on tuesday at 7am"},
                    {"kind": "task", "text": "remind me to buy milk"},
                ]}, 2
            return {"items": [{"kind": "event", "text": text}]}, 2
        # extraction: always the true two asks
        return {"asks": [
            {"kind": "event", "words": "gym on tuesday at 7am"},
            {"kind": "task", "words": "buy milk"},
        ]}, 2

    monkeypatch.setattr(engine_llm, "call_json", scripted_llm)
    monkeypatch.setattr(generate, "_get_rule_parser", lambda: None)

    parser = MagicMock()

    def parse(seg_text):
        if "milk" in seg_text and "gym" not in seg_text:
            return [("create_todo", SimpleNamespace(title="buy milk", due_date=None))]
        return [("create_event", SimpleNamespace(
            title="gym", date=None, start_time="07:00", end_time=None,
            recurrence=None, recur_until=None, description=""))]

    parser.parse.side_effect = parse
    parser.last_llm_ms = 1
    parser.last_examples_used = 0
    parser.last_raw_response = ""
    monkeypatch.setattr(generate, "_get_parser", lambda c: parser)

    registry = MagicMock()

    def _get(name):
        cls = MagicMock()
        cls.return_value.execute.return_value = f"did {name}"
        return cls

    registry.get.side_effect = _get
    monkeypatch.setattr(generate, "get_registry", lambda: registry)

    out = engine.run_transcript(text, source="test")
    assert out["parse"] == "deep"
    assert sorted(out["actions"]) == ["create_event", "create_todo"]
    assert not any("not sure I caught every part" in m for m in [out["message"]])
    titles = [s["title"] for s in out["trace"]]
    assert "Looping back" in titles


def test_loop_budget_is_finite_and_admitted(cfg, monkeypatch):
    """A check that keeps failing stops after MAX_REENTRIES and says so.

    The scripted segment never splits, so the input must be one the
    deterministic clause tier also declines — otherwise the parse splits it
    and the never-resolving disagreement this test needs never happens."""
    def scripted_llm(cfg_, system, user, schema=None):
        if "split ONE voice command" in system:
            return {"items": []}, 1                    # never splits
        return {"asks": [{"kind": "task", "words": "buy milk"},
                         {"kind": "event", "words": "gym at 7"}]}, 1

    monkeypatch.setattr(engine_llm, "call_json", scripted_llm)
    monkeypatch.setattr(generate, "_get_rule_parser", lambda: None)
    parser = MagicMock()
    parser.parse.return_value = [("create_event", SimpleNamespace(
        title="gym", date=None, start_time=None, end_time=None,
        recurrence=None, recur_until=None, description=""))]
    parser.last_llm_ms = 1
    parser.last_examples_used = 0
    parser.last_raw_response = ""
    monkeypatch.setattr(generate, "_get_parser", lambda c: parser)
    registry = MagicMock()
    registry.get.side_effect = lambda name: MagicMock(
        **{"return_value.execute.return_value": "did it"})
    monkeypatch.setattr(generate, "get_registry", lambda: registry)

    out = engine.run_transcript("tomorrow gym at 7 am and a meeting with Tal at 11",
                                source="test")
    assert "not sure I caught every part" in out["message"]


# --- background patch tiers -------------------------------------------------

def test_placeholder_title_is_renamed_in_background(cfg, monkeypatch):
    from assistant.db import get_db
    db = get_db()
    row_id = db.create_event_from_dict({
        "title": "meeting", "date": "2026-11-03",
        "start_time": "15:00", "end_time": "16:00"})

    monkeypatch.setattr(engine_llm, "call_json",
                        lambda *a, **k: ({"asks": [
                            {"kind": "event", "words": "meeting with Ravid at Kems"}]}, 2))
    parser = MagicMock()
    parser.fix_title_async.return_value = "Meeting with Ravid at Kems"
    monkeypatch.setattr(generate, "_get_parser", lambda c: parser)

    st = _state_with([_event_item("item_1", "meeting",
                                  text="meeting with Ravid at Kems at 3pm")],
                     text="meeting with Ravid at Kems at 3pm")
    st.executed = [ExecutedAction(item_id="item_1", action="create_event",
                                  message="", ok=True,
                                  record=("event", row_id, "create_event", 0))]
    correction = engine._background_verify(st, cfg)
    assert db.get_event(row_id)["title"] == "Meeting with Ravid at Kems"
    assert correction and correction["severity"] == "minor"
    try:
        db.delete_event(row_id)
    except Exception:
        pass


def test_extra_row_is_advisory_by_default(cfg, monkeypatch):
    from assistant.db import get_db
    db = get_db()
    keep = db.create_todo(title="buy milk", list_name="today", priority="none",
                          due_date="", notes="")
    extra = db.create_todo(title="buy groceries", list_name="today", priority="none",
                           due_date="", notes="")
    monkeypatch.setattr(engine_llm, "call_json", lambda *a, **k: ({"asks": [
        {"kind": "task", "words": "buy milk"}]}, 2))

    st = _state_with([_task_item("item_1", "buy milk"),
                      _task_item("item_2", "buy groceries")],
                     text="add buy milk to my list")
    st.executed = [
        ExecutedAction("item_1", "create_todo", "", True, ("todo", keep, "create_todo", 0)),
        ExecutedAction("item_2", "create_todo", "", True, ("todo", extra, "create_todo", 1)),
    ]
    assert cfg.self_check_apply is False       # the measured-caution default
    correction = engine._background_verify(st, cfg)
    assert db.get_todo(extra) is not None      # advisory: said, not done
    assert correction["severity"] == "major"
    assert "Worth a look" in correction["speech"]
    for tid in (keep, extra):
        try:
            db.delete_todo(tid)
        except Exception:
            pass


def test_extra_row_is_removed_when_apply_is_on(cfg, monkeypatch):
    from assistant.db import get_db
    db = get_db()
    keep = db.create_todo(title="buy milk", list_name="today", priority="none",
                          due_date="", notes="")
    extra = db.create_todo(title="buy groceries", list_name="today", priority="none",
                           due_date="", notes="")
    monkeypatch.setattr(engine_llm, "call_json", lambda *a, **k: ({"asks": [
        {"kind": "task", "words": "buy milk"}]}, 2))
    monkeypatch.setattr(cfg, "self_check_apply", True)

    st = _state_with([_task_item("item_1", "buy milk"),
                      _task_item("item_2", "buy groceries")],
                     text="add buy milk to my list")
    st.executed = [
        ExecutedAction("item_1", "create_todo", "", True, ("todo", keep, "create_todo", 0)),
        ExecutedAction("item_2", "create_todo", "", True, ("todo", extra, "create_todo", 1)),
    ]
    correction = engine._background_verify(st, cfg)
    assert db.get_todo(extra) is None
    assert correction["severity"] == "major"
    # The removal carries one-tap revert: a ready-to-POST /todos body that
    # re-creates exactly what was undone.
    assert correction.get("revert"), "a destructive patch must offer a revert"
    spec = correction["revert"][0]
    assert spec["kind"] == "todo"
    assert spec["body"]["title"] == "buy groceries"
    assert spec["body"]["list_name"] == "today"
    try:
        db.delete_todo(keep)
    except Exception:
        pass


def test_revert_spec_shapes_a_post_ready_body():
    """The spec is exactly what POST /events / POST /todos accept, so a client
    reverts by re-creating — no new endpoint, no db.py bypass."""
    ev = {"title": "Gym", "date": "2026-11-03", "start_time": "07:00",
          "end_time": "08:00", "location": "", "attendees": "Noa",
          "recurrence": "", "color": "#0078d4", "id": 5, "source": "voice"}
    assert engine._revert_spec("event", ev) == {"kind": "event", "body": {
        "title": "Gym", "date": "2026-11-03", "start_time": "07:00",
        "end_time": "08:00", "attendees": "Noa", "color": "#0078d4"}}
    # a row missing a field a create needs can't be re-created — no false offer
    assert engine._revert_spec("event", {"title": "x"}) is None
    assert engine._revert_spec("event", None) is None

    td = {"title": "buy milk", "list": "today", "priority": "high",
          "due_date": "", "notes": "", "tags": ["Groceries"], "quantity": 3}
    spec = engine._revert_spec("todo", td)
    assert spec["kind"] == "todo"
    assert spec["body"]["list_name"] == "today"       # the `list` column → POST `list_name`
    assert spec["body"]["tags"] == ["Groceries"]
    assert spec["body"]["quantity"] == 3


def test_the_loop_stops_when_a_rerun_cannot_change_anything(cfg, monkeypatch):
    """A re-run starts from the same transcript and runs the same stages, so
    if it would begin from the SAME items with the SAME complaint it produces
    the same answer. Looping again only spends the budget.

    Real usage (2026-09-08): "Let an event to go out for a run now" — one ask,
    ONE item, segment never in doubt — looped three times to the identical
    result, its own trace saying "unchanged since the last attempt" each
    round, and apologised after 30 seconds.
    """
    def scripted_llm(cfg_, system, user, schema=None):
        if "split ONE voice command" in system:
            return {"items": []}, 1                    # segment never splits
        return {"asks": [{"kind": "event", "words": "gym at 7"},
                         {"kind": "task", "words": "buy milk"}]}, 1

    monkeypatch.setattr(engine_llm, "call_json", scripted_llm)
    monkeypatch.setattr(generate, "_get_rule_parser", lambda: None)
    parser = MagicMock()
    parser.parse.return_value = [("create_event", SimpleNamespace(
        title="gym", date=None, start_time=None, end_time=None,
        recurrence=None, recur_until=None, description=""))]
    parser.last_llm_ms = 1
    parser.last_examples_used = 0
    parser.last_raw_response = ""
    monkeypatch.setattr(generate, "_get_parser", lambda c: parser)
    registry = MagicMock()
    registry.get.side_effect = lambda name: MagicMock(
        **{"return_value.execute.return_value": "did it"})
    monkeypatch.setattr(generate, "get_registry", lambda: registry)

    out = engine.run_transcript("tomorrow gym at 7 am and a meeting with Tal at 11",
                                source="test")
    loops = [s for s in out["trace"] if s["title"] == "Looping back"]
    assert len(loops) < crosscheck.MAX_REENTRIES, (
        f"burned every retry on an unchanging parse: {[s['detail'] for s in loops]}")
    # and it still admits it could not finish the job
    assert "not sure I caught every part" in out["message"]
