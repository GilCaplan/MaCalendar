"""A retry is a correction the speaker already gave, for free.

When a command produces the wrong thing, gets deleted, and is immediately said
again in slightly different words, the second version is what the first one
meant. Nobody has to be asked; the work is already done and thrown away.

That signal is worth having because the explicit one is failing: a third of
commands get no verdict at all, which is fatigue from being asked on every
single one. This costs nothing.

The danger is the opposite of the opportunity. Similarity retrieval clusters
near-duplicates, so a wrong correction arrives with its siblings and does more
damage than no correction at all. Every guard below exists because a specific
shape of false positive turned up when this was first run over the real
history — where, with loose guards, two of the three pairs it found were
nonsense and the third pointed the wrong way.
"""
from __future__ import annotations

import json
import time

import pytest

from assistant.intent.memory import (
    CommandMemory, FEEDBACK_APPROVED, FEEDBACK_CORRECTED, FEEDBACK_REJECTED,
)

ACTIONS = [("create_event", {"title": "Dentist", "date": "2026-09-10"})]


@pytest.fixture
def memory(tmp_path):
    return CommandMemory(str(tmp_path / "m.db"))


def _say(memory, text, *, when, verdict=None, actions=ACTIONS, source="ios"):
    """Record a command at a chosen moment, since these tests are about timing."""
    eid = memory.record(transcript=text, source=source, parse_path="llm", actions=actions)
    with memory._conn() as c:
        c.execute("UPDATE examples SET ts = ? WHERE id = ?", (when, eid))
    if verdict:
        memory.set_feedback(eid, verdict)
    return eid


# ---------------------------------------------------------------------------
# The shape it exists to catch
# ---------------------------------------------------------------------------

def test_a_deleted_command_said_again_is_recognised(memory):
    now = time.time()
    _say(memory, "book the dentist for tuesday at nine", when=now, verdict=FEEDBACK_REJECTED)
    _say(memory, "book the dentist for tuesday at ten", when=now + 9)

    pairs = memory.find_reformulations()
    assert len(pairs) == 1, pairs
    assert pairs[0]["right"].endswith("at ten")


def test_the_retry_becomes_what_the_first_should_have_produced(memory):
    """It plugs into the existing weighting: this is the shape "fix this" makes."""
    now = time.time()
    wrong = _say(memory, "book the dentist for tuesday at nine", when=now,
                 verdict=FEEDBACK_REJECTED)
    _say(memory, "book the dentist for tuesday at ten", when=now + 9,
         actions=[("create_event", {"title": "Dentist", "start_time": "10:00"})])

    assert memory.learn_from_reformulations()
    row = memory.get(wrong)
    assert row["feedback"] == FEEDBACK_CORRECTED
    assert row["correction"][0]["parameters"]["start_time"] == "10:00"


def test_running_it_twice_changes_nothing(memory):
    """It runs after every command, so it must not accumulate."""
    now = time.time()
    _say(memory, "book the dentist for tuesday at nine", when=now, verdict=FEEDBACK_REJECTED)
    _say(memory, "book the dentist for tuesday at ten", when=now + 9)
    assert len(memory.learn_from_reformulations()) == 1
    assert memory.learn_from_reformulations() == []


# ---------------------------------------------------------------------------
# The false positives found in the real history, each now refused
# ---------------------------------------------------------------------------

def test_two_different_commands_in_a_row_are_not_a_correction(memory):
    """The first thing it got wrong: people say unrelated things consecutively."""
    now = time.time()
    _say(memory, "today i have an event at six o'clock a meeting", when=now,
         verdict=FEEDBACK_REJECTED)
    _say(memory, "on tuesday the fourteenth set an event at three with the team", when=now + 20)
    assert memory.find_reformulations() == []


def test_rows_written_at_the_same_instant_are_not_a_retry(memory):
    """A gap of zero means imported or batched history, not a person reacting."""
    now = time.time()
    _say(memory, "book the dentist for tuesday at nine", when=now, verdict=FEEDBACK_REJECTED)
    _say(memory, "book the dentist for tuesday at ten", when=now + 0.2)
    assert memory.find_reformulations() == []


def test_very_short_transcripts_are_ignored(memory):
    """"Execute." against "Execute a" scores 0.88 and means nothing at all."""
    now = time.time()
    _say(memory, "Execute.", when=now, verdict=FEEDBACK_REJECTED)
    _say(memory, "Execute a", when=now + 5)
    assert memory.find_reformulations() == []


def test_a_verbatim_repeat_teaches_nothing(memory):
    """Saying exactly the same thing again blames the recognition, not the words."""
    now = time.time()
    text = "book the dentist for tuesday at nine"
    _say(memory, text, when=now, verdict=FEEDBACK_REJECTED)
    _say(memory, text, when=now + 8)
    assert memory.find_reformulations() == []


def test_a_retry_that_also_failed_teaches_nothing(memory):
    now = time.time()
    _say(memory, "book the dentist for tuesday at nine", when=now, verdict=FEEDBACK_REJECTED)
    _say(memory, "book the dentist for tuesday at ten", when=now + 9,
         verdict=FEEDBACK_REJECTED)
    assert memory.find_reformulations() == []


def test_a_command_that_was_never_rejected_is_not_a_failure(memory):
    """Two similar commands are only a retry if the first one was wrong."""
    now = time.time()
    _say(memory, "book the dentist for tuesday at nine", when=now, verdict=FEEDBACK_APPROVED)
    _say(memory, "book the dentist for tuesday at ten", when=now + 9)
    assert memory.find_reformulations() == []


def test_a_retry_on_the_other_device_is_not_the_same_attempt(memory):
    now = time.time()
    _say(memory, "book the dentist for tuesday at nine", when=now,
         verdict=FEEDBACK_REJECTED, source="ios")
    _say(memory, "book the dentist for tuesday at ten", when=now + 9, source="mac")
    assert memory.find_reformulations() == []


def test_a_retry_much_later_is_a_new_command(memory):
    now = time.time()
    _say(memory, "book the dentist for tuesday at nine", when=now, verdict=FEEDBACK_REJECTED)
    _say(memory, "book the dentist for tuesday at ten", when=now + 3600)
    assert memory.find_reformulations() == []


def test_a_retry_that_produced_nothing_is_not_the_answer(memory):
    """If the second attempt created no record, it is not what the first meant."""
    now = time.time()
    _say(memory, "book the dentist for tuesday at nine", when=now, verdict=FEEDBACK_REJECTED)
    _say(memory, "book the dentist for tuesday at ten", when=now + 9, actions=[])
    assert memory.find_reformulations() == []


def test_dry_run_reports_without_writing(memory):
    now = time.time()
    wrong = _say(memory, "book the dentist for tuesday at nine", when=now,
                 verdict=FEEDBACK_REJECTED)
    _say(memory, "book the dentist for tuesday at ten", when=now + 9)
    assert len(memory.learn_from_reformulations(dry_run=True)) == 1
    assert memory.get(wrong)["feedback"] == FEEDBACK_REJECTED


# ---------------------------------------------------------------------------
# The second opinion
# ---------------------------------------------------------------------------

def _pair(memory):
    now = time.time()
    wrong = _say(memory, "book the dentist for tuesday at nine", when=now,
                 verdict=FEEDBACK_REJECTED)
    _say(memory, "book the dentist for tuesday at ten", when=now + 9)
    return wrong


def test_a_reviewer_can_refuse_a_pair_the_rules_accepted(memory):
    """The rules are structural — timing, similarity, who spoke. They cannot
    tell a correction from two things the speaker genuinely wanted."""
    wrong = _pair(memory)
    assert memory.learn_from_reformulations(verify=lambda a, b: False) == []
    assert memory.get(wrong)["feedback"] == FEEDBACK_REJECTED


def test_a_reviewer_that_agrees_lets_it_through(memory):
    wrong = _pair(memory)
    assert len(memory.learn_from_reformulations(verify=lambda a, b: True)) == 1
    assert memory.get(wrong)["feedback"] == FEEDBACK_CORRECTED


def test_a_reviewer_that_cannot_answer_blocks_rather_than_approves(memory):
    """The model may be unreachable. Silence must not read as consent — a wrong
    correction is pasted into future prompts, so a false yes costs much more
    than a false no."""
    def unavailable(a, b):
        raise RuntimeError("model is not running")

    wrong = _pair(memory)
    assert memory.learn_from_reformulations(verify=unavailable) == []
    assert memory.get(wrong)["feedback"] == FEEDBACK_REJECTED


def test_the_reviewer_is_shown_both_commands(memory):
    seen = []
    _pair(memory)
    memory.learn_from_reformulations(verify=lambda a, b: seen.append((a, b)) or True)
    assert seen == [("book the dentist for tuesday at nine",
                     "book the dentist for tuesday at ten")]


# ---------------------------------------------------------------------------
# Nothing worth learning from should have been recorded in the first place
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("said", ["", "Execute.", "execute", "Execute a...", "No.",
                                  "ok", "um", "I need a b-"])
def test_a_false_start_is_never_treated_as_a_command(said):
    """Four of these reached the parser and were remembered as real commands.

    They are worse than harmless: the memory feeds the model worked examples,
    so a run of junk teaches it that junk is how this person speaks.
    """
    from assistant.engine.ingest.repair import is_trivial_transcript
    assert is_trivial_transcript(said), f"{said!r} should be ignored outright"


@pytest.mark.parametrize("said", ["gym tomorrow", "buy milk", "lunch at noon",
                                  "what do I have today", "delete the meeting"])
def test_a_real_command_is_not_mistaken_for_a_false_start(said):
    from assistant.engine.ingest.repair import is_trivial_transcript
    assert not is_trivial_transcript(said), f"{said!r} is a real command"
