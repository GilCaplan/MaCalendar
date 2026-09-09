"""LLMJudge — the intent-level vetoes, unit-level (no LLM).

This file was created by the 2026-09-09 PORT (`llmjudge/PLAN.md` §1.0): three
tests came here from `test_fastrule.py` with the code they pin. A guard without
its test is only half ported, so they moved in the same change.

They still drive `FastRule.run()` rather than `Gatekeeper.judge()` directly,
and deliberately so: during the port FastRule is still the caller, and a test
that changed what it exercises would stop being evidence that behaviour did not
move — which is the port's one acceptance condition. When phase B turns the
veto into prompt CONTEXT (§1.1), these become the tests that say what changed.

conftest.py has already pointed every store at scratch before this import.
"""
import pytest

from assistant.engine.fastrule.fastrule import FastRule


@pytest.fixture
def fastrule(registry_with_real_actions):
    # the autouse isolated_registry empties the action registry; intents are
    # built from it, so FastRule needs the real actions restored
    return FastRule(0.80)


def test_f4a_polite_imperative_is_not_a_question(fastrule):
    """"Can you create X" wants X created — the interrogative gate must not
    read the courtesy as a question. Real questions still abstain."""
    r = fastrule.run("Can you create a new list in my podcast?")
    assert r.committed and r.intents[0][0] == "create_todo"
    r = fastrule.run("Do I need to be reminded of any meetings on Monday?")
    assert not r.committed and r.reason == "interrogative-create"


def test_f7_rename_never_commits_a_create(fastrule):
    """"rename flu shot to sales call" fast-committed create_todo at 0.95 —
    and FastRule can't know which store holds the old title anyway. Renames
    abstain; deep's matcher searches both stores."""
    r = fastrule.run("rename flu shot to sales call")
    assert not r.committed and r.reason == "rename-misroute"


def test_personalisation_is_lookup_not_training(fastrule):
    """Gil's principle: the shipped models stay generic and identical for
    every user; the personal part is the DATA they are pointed at. So a
    lookup against the user's own stores must (a) resolve what generic
    English cannot, and (b) never let a wrong parse through just because
    something was found."""
    from assistant.db import get_db
    from assistant.actions.calendar.intent import CalendarIntent

    # nothing in the stores: the rename cannot be resolved, so it defers
    r = fastrule.run("rename flu shot to sales call")
    assert not r.committed and r.reason == "rename-misroute"

    get_db().create_event(CalendarIntent(title="flu shot", date="2026-09-10",
                                         start_time="09:00", end_time="10:00"))
    # now the store is known — but the parse reads it as a CREATE, which
    # disagrees. The lookup must CONFIRM a parse, never merely permit one.
    r = fastrule.run("rename flu shot to sales call")
    assert not r.committed, "a lookup must not launder a wrong parse"


def test_the_ported_code_lives_here_now(fastrule):
    """The port itself, pinned: these names resolve from `llmjudge`, and
    FastRule's redirect is the same object rather than a second copy.

    Two copies of a guard is the exact shape of the bug this project already
    paid for — the per-item path re-implemented the commit test with the gates
    omitted and re-committed what the front door had vetoed. A copy would have
    reintroduced that shape; this asserts it is a move.
    """
    from assistant.engine.fastrule import fastrule as fr
    from assistant.engine.fastrule import objects as fo
    from assistant.engine.llmjudge import gatekeeper as gk
    from assistant.engine.llmjudge import llm_fallback as lf

    assert fr.Gatekeeper is gk.Gatekeeper
    assert fr._GENERIC_TARGET_RE is gk._GENERIC_TARGET_RE
    assert fo._guard_inventions is lf._guard_inventions
    assert fo._honour_refusal is lf._honour_refusal

    # …and the DEFER vocabulary deliberately did NOT move: it is FastRule's
    # product, with three other readers. A contract does not belong inside one
    # of its consumers.
    assert fr.REFUSAL == "refusal" and fr.reason_class("generic-target") == fr.REFUSAL
    assert not hasattr(gk, "REFUSAL"), "the reason-class contract stays in fastrule"
