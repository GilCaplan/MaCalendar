"""Unit tests for RuleBasedParser — no LLM, no DB required.

All 7 spec cases plus edge cases.
Expected dates are computed relative to real today so no datetime mocking needed.
ContextMemory is reset by the autouse fixture in conftest.py.
"""
from __future__ import annotations

import datetime

import pytest

from assistant.intent.rule_parser import (
    RULE_THRESHOLD,
    RuleBasedParser,
    RuleParserSkip,
)
from assistant.intent.context import context_memory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tomorrow() -> str:
    return (datetime.date.today() + datetime.timedelta(days=1)).isoformat()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def parser(isolated_registry):
    """RuleBasedParser with all real actions registered.

    isolated_registry clears global_registry during the test, so we re-populate
    it manually from the already-imported action classes.
    """
    from assistant.actions.calendar.action import (
        CreateEventAction, UpdateEventAction, DeleteEventAction, QueryScheduleAction
    )
    from assistant.actions.todo.action import (
        CreateTodoAction, CompleteTodoAction, DeleteTodoAction, UpdateTodoAction, QueryTodoAction
    )
    from assistant.actions.clarify import ClarifyAction

    for cls in [
        CreateEventAction, UpdateEventAction, DeleteEventAction, QueryScheduleAction,
        CreateTodoAction, CompleteTodoAction, DeleteTodoAction, UpdateTodoAction,
        QueryTodoAction, ClarifyAction,
    ]:
        isolated_registry._actions[cls.action_name] = cls

    return RuleBasedParser(isolated_registry)


# ---------------------------------------------------------------------------
# Spec test case 1: create_event fast path
# ---------------------------------------------------------------------------

def test_schedule_meeting_tomorrow_at_3pm(parser):
    """'Schedule a meeting tomorrow at 3 PM' → create_event, fast path."""
    result = parser.analyze("Schedule a meeting tomorrow at 3 PM", current_view="month")

    assert result.confidence >= RULE_THRESHOLD
    assert not result.missing_slots
    assert len(result.intents) == 1

    action_name, intent = result.intents[0]
    assert action_name == "create_event"
    assert intent.date == _tomorrow()
    assert intent.start_time == "15:00"
    assert "meeting" in intent.title.lower()


# ---------------------------------------------------------------------------
# Spec test case 2: update_event with anaphora
# ---------------------------------------------------------------------------

def test_move_it_to_friday_resolves_anaphora(parser):
    """'Move it to Friday' → update_event; match_title resolved from memory."""
    context_memory.update_event(42, "dentist", "2026-04-01")

    result = parser.analyze("Move it to Friday", current_view="month")

    # Anaphora penalty → correct partial handoff (< threshold)
    assert "update_event" in result.raw_slots
    assert result.raw_slots["update_event"].get("match_title") == "dentist"


# ---------------------------------------------------------------------------
# Spec test case 3: delete_todo
# ---------------------------------------------------------------------------

def test_delete_grocery_list(parser):
    """'Delete my grocery list' → delete_todo."""
    result = parser.analyze("Delete my grocery list", current_view="todo")

    assert "delete_todo" in result.raw_slots
    slots = result.raw_slots["delete_todo"]
    assert "grocery" in slots.get("match_title", "").lower()


# ---------------------------------------------------------------------------
# Spec test case 4: query_schedule fast path
# ---------------------------------------------------------------------------

def test_what_do_i_have_today(parser):
    """'What do I have today' → query_schedule, fast path."""
    result = parser.analyze("What do I have today", current_view="month")

    assert result.confidence >= RULE_THRESHOLD
    assert not result.missing_slots
    assert len(result.intents) == 1

    action_name, intent = result.intents[0]
    assert action_name == "query_schedule"
    assert intent.scope == "today"


# ---------------------------------------------------------------------------
# Spec test case 5: create_todo bare verb
# ---------------------------------------------------------------------------

def test_call_mom(parser):
    """'Call mom' → create_todo, fast path."""
    result = parser.analyze("Call mom", current_view="month")

    assert result.confidence >= RULE_THRESHOLD
    assert not result.missing_slots

    action_name, intent = result.intents[0]
    assert action_name == "create_todo"
    assert "mom" in intent.titles[0].lower()


# ---------------------------------------------------------------------------
# Spec test case 6: create_todo with due_date
# ---------------------------------------------------------------------------

def test_buy_milk_tomorrow(parser):
    """'Buy milk tomorrow' → create_todo with due_date."""
    result = parser.analyze("Buy milk tomorrow", current_view="month")

    assert result.confidence >= RULE_THRESHOLD
    assert not result.missing_slots

    action_name, intent = result.intents[0]
    assert action_name == "create_todo"
    assert intent.due_date == _tomorrow()
    assert "milk" in intent.titles[0].lower()


# ---------------------------------------------------------------------------
# Spec test case 7: update_event with time range
# ---------------------------------------------------------------------------

def test_reschedule_meeting_with_time_range(parser):
    """'Reschedule my meeting with John from 3 pm to 5 pm' → update_event."""
    result = parser.analyze(
        "Reschedule my meeting with John from 3 pm to 5 pm",
        current_view="month",
    )

    assert "update_event" in result.raw_slots
    slots = result.raw_slots["update_event"]
    assert slots.get("new_start_time") == "15:00"
    assert slots.get("new_end_time") == "17:00"


# ---------------------------------------------------------------------------
# Complexity gate
# ---------------------------------------------------------------------------

def test_complexity_gate_long_sentence(parser):
    """More than 12 content words (stop/filler words excluded) → RuleParserSkip."""
    # 13+ distinct semantic words: schedule, meeting, John, remind, buy, milk,
    # call, dentist, add, gym, session, tomorrow, noon
    long = (
        "I want to schedule a meeting with John and also remind me to buy milk "
        "and then call the dentist and furthermore please add a gym session tomorrow at noon"
    )
    with pytest.raises(RuleParserSkip):
        parser.analyze(long)


# ---------------------------------------------------------------------------
# Query scope variants
# ---------------------------------------------------------------------------

def test_query_schedule_week(parser):
    """'What's on my schedule this week' → query_schedule scope=week."""
    result = parser.analyze("What's on my schedule this week", current_view="month")

    assert result.confidence >= RULE_THRESHOLD
    _, intent = result.intents[0]
    assert intent.scope == "week"


def test_query_schedule_tomorrow(parser):
    """'What do I have tomorrow' → query_schedule scope=tomorrow."""
    result = parser.analyze("What do I have tomorrow", current_view="month")

    assert result.confidence >= RULE_THRESHOLD
    _, intent = result.intents[0]
    assert intent.scope == "tomorrow"


# ---------------------------------------------------------------------------
# Multi-intent split
# ---------------------------------------------------------------------------

def test_multi_intent_buy_and_call(parser):
    """'Buy milk and call mom' → two create_todo intents."""
    result = parser.analyze("Buy milk and call mom", current_view="month")

    action_names = [name for name, _ in result.intents]
    assert action_names.count("create_todo") == 2


# ---------------------------------------------------------------------------
# STT shorthand expansion
# ---------------------------------------------------------------------------

def test_stt_expansion_tmrw(parser):
    """'Schedule mtg tmrw at 3 PM' expands shorthands correctly."""
    result = parser.analyze("Schedule mtg tmrw at 3 PM", current_view="month")

    assert "create_event" in result.raw_slots
    assert result.raw_slots["create_event"].get("date") == _tomorrow()


# ---------------------------------------------------------------------------
# [TASKS VIEW] prefix stripped
# ---------------------------------------------------------------------------

def test_tasks_view_prefix_stripped(parser):
    """Pipeline's [TASKS VIEW] prefix is removed before parsing."""
    result = parser.analyze("[TASKS VIEW] what tasks do I have today", current_view="todo")

    assert result.confidence >= RULE_THRESHOLD
    action_name = list(result.raw_slots.keys())[0]
    assert action_name in ("query_todos", "query_schedule")


# ---------------------------------------------------------------------------
# Anaphor with no memory → partial result (not a skip)
# ---------------------------------------------------------------------------

def test_anaphora_no_memory_returns_partial(parser):
    """'Move it to Friday' with empty memory → update_event, match_title unresolved."""
    # No memory seeded — context_memory reset by autouse fixture
    result = parser.analyze("Move it to Friday", current_view="month")

    assert "update_event" in result.raw_slots
    # match_title stays as "it" because there's nothing to resolve
    match = result.raw_slots["update_event"].get("match_title", "").lower()
    assert match in ("it", "")


# ---------------------------------------------------------------------------
# parse() raises RuleParserSkip on low-confidence / missing slots
# ---------------------------------------------------------------------------

def test_parse_raises_skip_for_low_confidence(parser):
    """parse() raises RuleParserSkip when confidence < RULE_THRESHOLD or missing slots."""
    # Ambiguous command — no time and no clear target
    try:
        result = parser.analyze("move something", current_view="month")
        if result.confidence < RULE_THRESHOLD or result.missing_slots:
            with pytest.raises(RuleParserSkip):
                parser.parse("move something", current_view="month")
    except RuleParserSkip:
        pass  # complexity gate or no-match → also a valid skip


# ---------------------------------------------------------------------------
# Full create_event fast path via public parse()
# ---------------------------------------------------------------------------

def test_parse_high_confidence_returns_intents(parser):
    """parse() returns intent list directly when fast-path fires."""
    intents = parser.parse("schedule standup tomorrow at 9 AM", current_view="month")
    assert intents[0][0] == "create_event"
    _, intent = intents[0]
    assert intent.start_time == "09:00"
    assert intent.date == _tomorrow()


# ---------------------------------------------------------------------------
# create_event end_time auto-fill
# ---------------------------------------------------------------------------

def test_create_event_end_time_autofilled(parser):
    """When no end time is given, CalendarIntent auto-fills end = start + 1h."""
    result = parser.analyze("Schedule dentist tomorrow at 2 PM", current_view="month")

    assert result.confidence >= RULE_THRESHOLD
    _, intent = result.intents[0]
    assert intent.end_time == "15:00"  # 14:00 + 1h


# ---------------------------------------------------------------------------
# delete_event vs delete_todo disambiguation
# ---------------------------------------------------------------------------

def test_cancel_calendar_event(parser):
    """'Cancel my dentist appointment' → delete_event (calendar signal)."""
    result = parser.analyze("Cancel my dentist appointment", current_view="month")

    assert "delete_event" in result.raw_slots


def test_delete_todo_item(parser):
    """'Delete my grocery task' → delete_todo (todo signal)."""
    result = parser.analyze("Delete my grocery task", current_view="month")

    assert "delete_todo" in result.raw_slots


# ---------------------------------------------------------------------------
# Regression: Bug 2026-04-03 — generic calendar word must not become match_title
# ---------------------------------------------------------------------------

def test_delete_event_by_time_not_generic_title(parser):
    """'can you delete the event at 6pm today' → delete_event with match_start_time=18:00.

    The word 'event' is a generic placeholder and must NOT be used as match_title.
    The time (18:00) and date (today) should be extracted instead.
    """
    today = datetime.date.today().isoformat()
    result = parser.analyze("can you delete the event at 6pm today", current_view="month")

    assert "delete_event" in result.raw_slots
    slots = result.raw_slots["delete_event"]
    # "event" must not be used as match_title
    assert slots.get("match_title", "").lower() != "event"
    # Time and date should be filled
    assert slots.get("match_start_time") == "18:00"
    assert slots.get("match_date") == today
    # Fast path should fire (no missing required slots)
    assert not result.missing_slots
    assert result.confidence >= RULE_THRESHOLD


def test_extend_event_by_start_time(parser):
    """'extend the 1pm event to 3pm' → update_event, match_start_time=13:00, new_end_time=15:00."""
    result = parser.analyze("extend the 1pm event to 3pm", current_view="month")

    assert "update_event" in result.raw_slots
    slots = result.raw_slots["update_event"]
    # Identified by start time, not by generic title "event"
    assert slots.get("match_start_time") == "13:00"
    assert slots.get("match_title", "").lower() != "event"
    # End time changed, start time NOT changed
    assert slots.get("new_end_time") == "15:00"
    assert "new_start_time" not in slots
    # Fast path fires
    assert not result.missing_slots
    assert result.confidence >= RULE_THRESHOLD


def test_lengthen_named_event(parser):
    """'lengthen team sync to 10am' → update_event; 'to 10am' → new_end_time, NOT new_start_time."""
    result = parser.analyze("lengthen team sync to 10am", current_view="month")

    assert "update_event" in result.raw_slots
    slots = result.raw_slots["update_event"]
    # The key semantic: "to 10am" is the new end time, not a reschedule target
    assert slots.get("new_end_time") == "10:00"
    assert "new_start_time" not in slots


def test_delete_event_relative_clause_skips_to_llm(parser):
    """'delete the event you create today on friday' — relative clause → RuleParserSkip.

    Sentences with a relative clause ('you create') are too ambiguous for the
    rule parser and must be routed to the LLM.
    """
    with pytest.raises(RuleParserSkip):
        parser.analyze("delete the event you create today on friday", current_view="month")
