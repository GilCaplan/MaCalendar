"""Regression suite built from real voice transcripts logged in
DOCUMENTATION/NLU_TRACKING.md — the app's own self-recorded history of every
voice command that has actually been spoken to it, including real STT noise
(mumbling, self-corrections, trailing filler words, mis-transcribed words).

Only transcripts that were logged as "SUCCESS — rule fast-path" AND that were
*not* subsequently flagged wrong by the background LLM verifier in
DOCUMENTATION/SCENARIO_BUG.md are used as positive regression cases here — those
are the ones we have positive evidence the rule parser got right. Entries that
were flagged wrong stay tracked in SCENARIO_BUG.md rather than being asserted
here as "correct".

We don't assert exact resolved dates/times: "tomorrow" et al. are relative to
whenever the test runs, not to whenever the transcript was originally spoken, so
only action selection (and fast-path firing where the log shows it fired) is
checked. This protects the rule parser's classification behavior against
regressions without being fragile to date drift.
"""
from __future__ import annotations

import datetime

import pytest

from assistant.intent.rule_parser import RULE_THRESHOLD, RuleBasedParser
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


# Real transcripts, real STT noise, confirmed-correct action selection.
# (transcript, expected action_names in order, expect_fast_path_fires)
HISTORICAL_FAST_PATH_CASES = [
    (
        "set event tomorrow at 4.30 pm for one hour with yotem regarding his bugroot",
        ["create_event"], True,
    ),
    (
        "can you set a meeting for next week on the 14th on tuesday at 2pm to do a "
        "meeting with manachem to do a run of simulation with him",
        ["create_event"], True,
    ),
    (
        # Garbled STT tail ("with it time") — still routed as a schedule query.
        "reading tomorrow at six p.m. with it time",
        ["query_schedule"], True,
    ),
    ("set tomorrow a meeting with nurit at 5pm", ["create_event"], True),
    ("set a meeting for me tomorrow at 4pm", ["create_event"], True),
    (
        "please set a meeting for me tomorrow at 4pm with re for defense on homework",
        ["create_event"], True,
    ),
    (
        # Mid-sentence self-correction ("sorry, i mean edo") shouldn't confuse routing.
        "set a meeting for me tomorrow at 5.30 p.m. with pelic sorry, i mean edo",
        ["create_event"], True,
    ),
    (
        # Trailing filler/noise after the command.
        "set meeting on thursday for three o'clock. thank you. is this why you made it?",
        ["create_event"], True,
    ),
    (
        # Truncated trailing "to" — STT cut off mid-word.
        "set a meeting on thursday for 11 a.m. to",
        ["create_event"], True,
    ),
    (
        "add on the 19 at 9 a.m. exam for eurovision course online",
        ["create_event"], True,
    ),
]


@pytest.mark.parametrize("transcript,expected_actions,expect_fires", HISTORICAL_FAST_PATH_CASES)
def test_historical_fast_path_case(parser, transcript, expected_actions, expect_fires):
    context_memory.reset()
    result = parser.analyze(transcript, current_view="month")
    action_names = [name for name, _ in result.intents]
    assert action_names == expected_actions, (
        f"Historical transcript {transcript!r} used to route to {expected_actions}, "
        f"now routes to {action_names}"
    )
    fires = result.confidence >= RULE_THRESHOLD and not result.missing_slots
    assert fires == expect_fires, (
        f"Historical transcript {transcript!r} used to "
        f"{'fast-path' if expect_fires else 'defer to LLM'}, now "
        f"{'fast-paths' if fires else 'defers'} (confidence={result.confidence:.2f}, "
        f"missing={result.missing_slots})"
    )


def test_historical_tomorrow_case_resolves_to_real_tomorrow(parser):
    """'Set a meeting for me tomorrow at 4pm' — date must track the real clock,
    not whatever 'tomorrow' resolved to when the transcript was first logged.
    """
    context_memory.reset()
    result = parser.analyze("set a meeting for me tomorrow at 4pm", current_view="month")
    _, intent = result.intents[0]
    assert intent.date == _tomorrow()
    assert intent.start_time == "16:00"


# ---------------------------------------------------------------------------
# Cases the background LLM verifier flagged as wrong (SCENARIO_BUG.md) — kept
# here as documentation of known imperfections, not asserted as correct. If one
# of these starts passing after a rule-parser improvement, promote it to
# HISTORICAL_FAST_PATH_CASES above and delete the matching SCENARIO_BUG.md entry
# (per that file's own maintenance instructions).
# ---------------------------------------------------------------------------

KNOWN_IMPERFECT_CASES = [
    # Rule parser said create_todo; background LLM judged it should be create_event.
    "on this coming thursday, please send an event for me at 1pm to go to tellmond "
    "to visit my friend tal with naor",
    # Rule parser said update_event; background LLM judged it should be create_todo.
    "a certain meeting on wednesday at 5.15pm to meet with rina for magsha meme "
    "bagru progress update",
    # Rule parser said create_event; background LLM judged it should be create_todo.
    "set a meeting tomorrow on tuesday at 6pm with ofir",
    "create a meeting tomorrow at 2pm on wednesday meeting with adin for the project",
]


@pytest.mark.parametrize("transcript", KNOWN_IMPERFECT_CASES)
def test_known_imperfect_case_still_parses_without_crashing(parser, transcript):
    """These are ambiguous even for a human reading the transcript cold — the bar
    here is just 'doesn't crash', not 'picks the LLM-preferred action'. Tracked in
    SCENARIO_BUG.md for anyone improving the rule parser's action-routing heuristics.
    """
    context_memory.reset()
    parser.analyze(transcript, current_view="month")
