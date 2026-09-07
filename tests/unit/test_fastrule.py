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
