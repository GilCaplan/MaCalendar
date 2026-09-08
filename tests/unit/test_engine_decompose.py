"""Step 3 — decomposition: several things, or one thing × N."""

from __future__ import annotations

import pytest

import assistant.engine.decompose_validate.decompose as decompose
import assistant.engine.llm as engine_llm
from assistant.engine import load_config
from assistant.engine.state import EngineState, Item


@pytest.fixture
def cfg():
    return load_config()


def _run(items, cfg) -> EngineState:
    st = EngineState(raw_text="", text="")
    st.items = items
    return decompose.run(st, cfg)


def _event(text, id="item_1"):
    return Item(id=id, kind="event", text=text)


def _task(text, id="item_1"):
    return Item(id=id, kind="task", text=text)


# --- two times = two events (row: walk dog at 9am and 2:30pm) ---------------

def test_two_adjacent_times_become_two_events(cfg):
    st = _run([_event("walk the dog at 9am and 2:30pm")], cfg)
    assert [it.id for it in st.items] == ["item_1-1", "item_1-2"]
    assert "at 9am" in st.items[0].text and "at 2:30pm" in st.items[1].text


def test_and_again_at_is_the_same_activity_twice(cfg):
    st = _run([_event("walk the dog at 9am and again at 2:30pm")], cfg)
    assert len(st.items) == 2


def test_a_time_range_is_one_event(cfg, monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("a range must not consult the LLM")
    monkeypatch.setattr(engine_llm, "call_json", _boom)
    st = _run([_event("lunch from 12:00 to 1:00 and bring the laptop")], cfg)
    assert len(st.items) == 1


def test_guests_joined_by_and_never_split(cfg, monkeypatch):
    monkeypatch.setattr(engine_llm, "call_json",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no LLM")))
    st = _run([_event("meeting with Tal and Ravid tomorrow at 3pm")], cfg)
    assert len(st.items) == 1


def test_llm_split_for_wordy_double_time(cfg, monkeypatch):
    monkeypatch.setattr(engine_llm, "call_json", lambda *a, **k: ({"parts": [
        {"text": "take Saba to physio at 10am"},
        {"text": "take Saba to physio at 4:30pm"},
    ]}, 7))
    st = _run([_event("take Saba to physio at 10am and later on at 4:30pm today")], cfg)
    assert [it.id for it in st.items] == ["item_1-1", "item_1-2"]


def test_llm_returning_one_part_keeps_the_item(cfg, monkeypatch):
    monkeypatch.setattr(engine_llm, "call_json", lambda *a, **k: ({"parts": [
        {"text": "dinner at 8pm and drinks after at 10pm"},
    ]}, 7))
    st = _run([_event("dinner at 8pm and drinks after at 10pm")], cfg)
    assert len(st.items) == 1


# --- task lists and quantities ---------------------------------------------

def test_task_list_splits_with_verb_handed_down(cfg):
    st = _run([_task("buy chicken and rice")], cfg)
    assert [it.text for it in st.items] == ["buy chicken", "buy rice"]
    assert [it.id for it in st.items] == ["item_1-1", "item_1-2"]


def test_idiom_is_one_task(cfg):
    st = _run([_task("buy fish and chips")], cfg)
    assert len(st.items) == 1


def test_quantity_is_one_task_with_units(cfg):
    st = _run([_task("buy 5 apples")], cfg)
    assert len(st.items) == 1
    assert st.items[0].slots["quantity"] == 5
    assert "5" not in st.items[0].text


def test_depth_is_bounded_to_one_split(cfg):
    """A sub-item is never split again: ids go one level deep."""
    st = _run([_task("buy chicken and rice and pasta")], cfg)
    assert all(it.id.count("-") <= 1 for it in st.items)


# --- reminder-clause stripping (cycle 8, notifications phase 3) -----------

def test_inline_reminder_clause_lands_in_slots():
    from assistant.engine.decompose_validate.decompose import _strip_reminder_clause
    from assistant.engine.state import Item
    it = Item(id="item_1", kind="event",
              text="book gym tomorrow at 6:30 and give me a heads-up half an hour before")
    _strip_reminder_clause(it)
    assert it.slots["reminder_minutes"] == 30
    assert it.text == "book gym tomorrow at 6:30"


def test_with_a_reminder_noun_form():
    from assistant.engine.decompose_validate.decompose import _strip_reminder_clause
    from assistant.engine.state import Item
    it = Item(id="item_1", kind="event",
              text="meeting with Dana Monday 9am with a 15 minute reminder")
    _strip_reminder_clause(it)
    assert it.slots["reminder_minutes"] == 15
    assert it.text == "meeting with Dana Monday 9am"


def test_leading_alert_me_hours_form():
    from assistant.engine.decompose_validate.decompose import _strip_reminder_clause
    from assistant.engine.state import Item
    it = Item(id="item_1", kind="event",
              text="Alert me 2 hours before my meeting on Tuesday with client")
    _strip_reminder_clause(it)
    assert it.slots["reminder_minutes"] == 120


def test_until_through_sentences_never_touched():
    # The whole reason the strip lives in decompose: a bare surviving
    # "before" would read as a recurrence-end marker in validate.
    from assistant.engine.decompose_validate.decompose import _strip_reminder_clause
    from assistant.engine.state import Item
    for txt in ("run daily until the end of September",
                "shiur weekly through October 3rd",
                "gym every monday until December"):
        it = Item(id="item_1", kind="event", text=txt)
        _strip_reminder_clause(it)
        assert "reminder_minutes" not in it.slots and it.text == txt


def test_bare_reminder_command_left_for_the_fallback():
    from assistant.engine.decompose_validate.decompose import _strip_reminder_clause
    from assistant.engine.state import Item
    it = Item(id="item_1", kind="event", text="remind me 30 minutes before")
    _strip_reminder_clause(it)
    assert "reminder_minutes" not in it.slots


def test_leading_courtesy_prefix_cleaned_after_strip():
    # C8 regression: "please remind me 1 hour before the meeting..." left
    # "please the meeting..." - a verbless mangle the LLM misread.
    from assistant.engine.decompose_validate.decompose import _strip_reminder_clause
    from assistant.engine.state import Item
    it = Item(id="item_1", kind="event",
              text="please remind me 1 hour before the meeting I hace tomorrow")
    _strip_reminder_clause(it)
    assert it.slots["reminder_minutes"] == 60
    assert it.text == "the meeting I hace tomorrow"
