"""Multi-action scenario tests — combinations of create/delete/update/complete for
events and todos said together in a single utterance.

These probe the space of things a real voice submission can contain: two creates,
a create + delete, cross-domain (event + todo) mixes, and same-domain chains that
are genuinely ambiguous. For each scenario we assert either:
  (a) the rule parser extracts the right intents (and, where the pipeline would
      actually execute it standalone, that fast-path fires), or
  (b) the rule parser correctly recognizes it can't be confident and defers to the
      LLM (RuleParserSkip, or confidence below RULE_THRESHOLD) — safe degradation,
      not a silent wrong answer.

Also covers a real bug found while writing this suite: `_split_intents` used each
conjunct verb's full subtree as its span, but a ROOT verb's subtree always includes
everything nested under its conjuncts too — so span[0] silently duplicated the
whole sentence. Fixed in rule_parser.py by clipping each span to the next verb's
start position. See test_multi_action_scenarios::test_split_intents_no_duplicate_span.
"""
from __future__ import annotations

import datetime

import pytest

from assistant.intent.rule_parser import RULE_THRESHOLD, RuleBasedParser, RuleParserSkip
from assistant.intent.context import context_memory


def _tomorrow() -> str:
    return (datetime.date.today() + datetime.timedelta(days=1)).isoformat()


@pytest.fixture
def parser(isolated_registry):
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

    return RuleBasedParser(isolated_registry)


def _fires(result) -> bool:
    """Whether the pipeline would take the fast-path for this analyze() result."""
    return result.confidence >= RULE_THRESHOLD and not result.missing_slots


# ---------------------------------------------------------------------------
# Split-boundary regression: the duplicate-span bug
# ---------------------------------------------------------------------------

def test_split_intents_no_duplicate_span():
    """Regression: span[0] must not be the entire sentence when there are 2+ verbs.

    Before the fix, `_split_intents("buy milk and call mom")` returned
    ['buy milk and call mom', 'call mom'] — the first span duplicated the whole
    sentence instead of being clipped to just its own verb's territory.
    """
    import assistant.intent.rule_parser as rp
    rp._ensure_nlp()
    doc = rp._NLP("buy milk and call mom")
    spans = rp._split_intents(doc)
    assert len(spans) == 2
    texts = [s.text for s in spans]
    assert "buy milk and call mom" not in texts
    # The trailing "and" (a cc token) stays attached to span[0] as a harmless
    # artifact — slot-filling extracts the object via dependency parse, not raw
    # text — but the span must stop before "call mom" starts.
    assert texts == ["buy milk and", "call mom"]


# ---------------------------------------------------------------------------
# Todo + todo (same domain, different titles)
# ---------------------------------------------------------------------------

def test_two_todos_correct_titles(parser):
    """'Buy milk and call mom' — two distinct create_todo intents, correct titles."""
    result = parser.analyze("buy milk and call mom", current_view="month")
    action_names = [name for name, _ in result.intents]
    assert action_names == ["create_todo", "create_todo"]
    titles = [intent.titles[0].lower() for _, intent in result.intents]
    assert titles == ["milk", "mom"]


# ---------------------------------------------------------------------------
# Event + todo (cross-domain create)
# ---------------------------------------------------------------------------

def test_event_and_todo_mixed_create(parser):
    """'Schedule a meeting tomorrow at 3pm and buy milk' — one event, one todo."""
    result = parser.analyze(
        "schedule a meeting tomorrow at 3pm and buy milk", current_view="month"
    )
    action_names = [name for name, _ in result.intents]
    assert action_names == ["create_event", "create_todo"]
    _, event_intent = result.intents[0]
    assert event_intent.date == _tomorrow()
    assert event_intent.start_time == "15:00"
    _, todo_intent = result.intents[1]
    assert "milk" in todo_intent.titles[0].lower()


# ---------------------------------------------------------------------------
# Event + todo (cross-domain delete)
# ---------------------------------------------------------------------------

def test_event_and_todo_mixed_delete(parser):
    """'Delete my grocery list and cancel my dentist appointment' — delete_todo + delete_event."""
    result = parser.analyze(
        "delete my grocery list and cancel my dentist appointment", current_view="month"
    )
    action_names = [name for name, _ in result.intents]
    assert action_names == ["delete_todo", "delete_event"]
    assert _fires(result)


def test_delete_todo_then_create_todo(parser):
    """'Delete my dentist appointment and add task buy flowers' — delete_event + create_todo."""
    result = parser.analyze(
        "delete my dentist appointment and add task buy flowers", current_view="month"
    )
    action_names = [name for name, _ in result.intents]
    assert action_names == ["delete_event", "create_todo"]
    assert _fires(result)


def test_complete_and_delete_todo(parser):
    """'Complete the grocery task and delete the laundry task' — complete_todo + delete_todo."""
    result = parser.analyze(
        "complete the grocery task and delete the laundry task", current_view="month"
    )
    action_names = [name for name, _ in result.intents]
    assert action_names == ["complete_todo", "delete_todo"]
    assert _fires(result)


# ---------------------------------------------------------------------------
# Ambiguous same-domain chains must NOT silently misfire — safe degradation
# ---------------------------------------------------------------------------

def test_two_deletes_same_domain_defers_to_llm(parser):
    """'Cancel my meeting today and cancel my dentist appointment tomorrow'.

    Both halves need a match_title the rule parser can't confidently resolve
    (ambiguous which noun is the title vs. filler) — must NOT fast-path fire
    with a guessed/wrong match_title; must defer to the LLM instead.
    """
    result = parser.analyze(
        "cancel my meeting today and cancel my dentist appointment tomorrow",
        current_view="month",
    )
    assert not _fires(result)


def test_three_way_todo_chain_defers_to_llm(parser):
    """'Add task call mom and add task buy milk' — 3-verb spaCy conjunct chain
    (spaCy attaches 'buy' as a sibling conjunct of 'add', not nested under the
    second 'add'), so the rule parser may over-split into 3 pieces. This must
    stay below the fast-path threshold rather than silently creating 3 todos
    for a 2-todo request.
    """
    result = parser.analyze(
        "add task call mom and add task buy milk", current_view="month"
    )
    assert not _fires(result)


# ---------------------------------------------------------------------------
# Fixed bug: bare "schedule <noun>" (no article) mistagged as NOUN by spaCy,
# which broke the verb-conjunct multi-intent split. _split_intents now falls
# back to lexicon-based split-point detection (INTENT_MAP verb lemmas at
# sentence-initial position or right after "and"/"or") when spaCy's VERB-conjunct
# search finds fewer than 2 verbs. See _lexicon_split_points in rule_parser.py.
# ---------------------------------------------------------------------------

def test_bare_schedule_two_events(parser):
    """'Schedule meeting ... and schedule lunch ...' (no articles) — both events
    captured via the lexicon-based split fallback.
    """
    result = parser.analyze(
        "schedule meeting tomorrow at 3pm and schedule lunch tomorrow at noon",
        current_view="month",
    )
    action_names = [name for name, _ in result.intents]
    assert action_names.count("create_event") == 2


def test_bare_schedule_then_delete(parser):
    """'Schedule gym ... and delete yesterday's meeting' — cross-domain
    create+delete, no articles, both actions captured.
    """
    result = parser.analyze(
        "schedule gym tomorrow at 7am and delete yesterday's meeting",
        current_view="month",
    )
    action_names = [name for name, _ in result.intents]
    assert "create_event" in action_names
    assert "delete_event" in action_names


# ---------------------------------------------------------------------------
# STT homophone fallback ("by"/"bye" ROOT -> "buy") — see rule_parser.py Pass 5
# in _route_intent. Restricted to ROOT position so legitimate prepositional
# "by" (e.g. "meeting by 3pm") is never affected.
# ---------------------------------------------------------------------------

def test_by_homophone_at_root_routes_to_create_todo(parser):
    """'by milk' (Whisper's common mishearing of 'buy milk') still routes to
    create_todo because 'by' lands as the span's ROOT — a preposition can't
    legitimately be a sentence's ROOT, so that position is itself the signal.
    """
    result = parser.analyze("by milk", current_view="month")
    action_names = [name for name, _ in result.intents]
    assert action_names == ["create_todo"]


def test_by_as_legitimate_preposition_unaffected(parser):
    """'meeting by 3pm today' — 'by' is a genuine preposition (not ROOT) here;
    the homophone fallback must not fire and corrupt this into a todo. This
    transcript alone doesn't map to any INTENT_MAP verb (no other action word),
    so a clean RuleParserSkip is the correct, safe outcome — a wrongly-fired
    create_todo would be the regression this test guards against.
    """
    try:
        result = parser.analyze("meeting by 3pm today", current_view="month")
        action_names = [name for name, _ in result.intents]
    except RuleParserSkip:
        action_names = []
    assert "create_todo" not in action_names


def test_stop_by_the_store_unaffected(parser):
    """'stop by the store' — 'by' is a prep attached to 'stop' (ROOT), not ROOT
    itself; must not be reinterpreted as 'buy'.
    """
    try:
        result = parser.analyze("stop by the store", current_view="month")
        action_names = [name for name, _ in result.intents]
    except RuleParserSkip:
        action_names = []
    assert "create_todo" not in action_names


# ---------------------------------------------------------------------------
# Workarounds for the known bug confirmed to work (with article / different verb)
# ---------------------------------------------------------------------------

def test_schedule_with_article_two_events_works(parser):
    """'Schedule a meeting ... and set a lunch ...' — using an article avoids the
    bare-noun mistagging bug and both events are captured.
    """
    result = parser.analyze(
        "schedule a meeting tomorrow at 3pm and set a lunch tomorrow at noon",
        current_view="month",
    )
    action_names = [name for name, _ in result.intents]
    assert action_names.count("create_event") == 2
    assert _fires(result)


def test_create_event_verb_two_events_works(parser):
    """'Create event ... and create event ...' — 'create' is reliably tagged VERB."""
    result = parser.analyze(
        "create event dentist tomorrow at 2pm and create event lunch tomorrow at noon",
        current_view="month",
    )
    action_names = [name for name, _ in result.intents]
    assert action_names.count("create_event") == 2
    assert _fires(result)


# ---------------------------------------------------------------------------
# Single-utterance create+delete+update across the whole action surface —
# sanity sweep that nothing throws unexpectedly for a broad set of phrasings.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("transcript", [
    "buy milk and call mom",
    "schedule a meeting tomorrow at 3pm and buy milk",
    "delete my grocery list and cancel my dentist appointment",
    "delete my dentist appointment and add task buy flowers",
    "complete the grocery task and delete the laundry task",
    "cancel my meeting today and cancel my dentist appointment tomorrow",
    "add task call mom and add task buy milk",
    "schedule a meeting tomorrow at 3pm and set a lunch tomorrow at noon",
    "create event dentist tomorrow at 2pm and create event lunch tomorrow at noon",
])
def test_multi_action_never_raises_unexpectedly(parser, transcript):
    """Every combo either analyzes cleanly or raises RuleParserSkip — never an
    unhandled exception that would crash the pipeline mid-command.
    """
    context_memory.reset()
    try:
        parser.analyze(transcript, current_view="month")
    except RuleParserSkip:
        pass  # explicit, expected hand-off to the LLM
