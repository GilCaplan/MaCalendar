"""FastRule — the selective classifier's gates, unit-level (no LLM).

conftest.py has already pointed every store at scratch before this import.
"""
import pytest

from assistant.engine.fastrule import FastRule


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


def test_f4b_marking_a_date_never_completes_a_task(fastrule):
    """"mark 13 october as my birthday" marks a DAY; it fast-committed
    complete_todo at 0.95 (would tick off an unrelated task). Now it must
    never commit a complete_* — abstaining to deep is the accepted outcome."""
    r = fastrule.run("mark 13 october of this year as my birthday")
    assert not any(n.startswith("complete_") for n, _ in r.intents)
    assert not r.committed
    r = fastrule.run("mark groceries as done")
    assert r.committed and r.intents[0][0] == "complete_todo"


def test_f5_plain_and_clause_coordination_abstains(fastrule):
    """F5: a plain "and" joining two asks (no cue words) must defer — the
    regex gate only knows announced joiners. Names and lists never trip it."""
    r = fastrule.run("book the gym for tomorrow at 6 and remind me to buy milk")
    assert not r.committed and r.reason == "clause-coordination"
    r = fastrule.run("schedule meeting with Tal and Sam tomorrow at 3pm")
    assert r.reason != "clause-coordination"  # NP-coordination: one event,
    # two guests - whatever else the parser decides, the F5 gate stays out


def test_f7_rename_never_commits_a_create(fastrule):
    """"rename flu shot to sales call" fast-committed create_todo at 0.95 —
    and FastRule can't know which store holds the old title anyway. Renames
    abstain; deep's matcher searches both stores."""
    r = fastrule.run("rename flu shot to sales call")
    assert not r.committed and r.reason == "rename-misroute"


def test_f7_priority_setting_is_an_update(fastrule):
    """"set X as high priority" read as create at 1.00 — it's a structured
    update: match_title + priority, phrase-delimited."""
    r = fastrule.run("set pick up the dry cleaning as high priority")
    assert r.committed and r.intents[0][0] == "update_todo"
    it = r.intents[0][1]
    assert getattr(it, "new_priority", None) == "high"
    assert "dry cleaning" in (getattr(it, "match_title", "") or "")
    # the rename extractor must not read "as high priority" as a new name
    assert not getattr(it, "new_title", None)


def test_f10_mutation_phrases_delimit_multiword_titles(fastrule):
    """Noun-chunking drops multi-word titles in mutations; the phrase itself
    delimits them. Generic targets still abstain (the veto judges captures)."""
    assert fastrule.run("delete wedding rehearsal from my calendar").committed
    assert fastrule.run("reschedule haircut to this weekend").committed
    assert fastrule.run("mark walk the dog complete").intents[0][0] == "complete_todo"
    assert not fastrule.run("delete this event").committed
