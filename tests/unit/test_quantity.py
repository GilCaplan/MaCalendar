"""Five of something is one task, not five tasks.

"I need to buy some groceries, which includes pasta times 5" produced this,
from the LLM path, on a real phone:

    create_todo(titles=['buy pasta', 'buy pasta', 'buy pasta',
                        'buy pasta', 'buy pasta'])

Neither parse path had any way to say "five of these", so the only available
representation of a count was repetition. The list then showed five identical
rows, and ticking one told you nothing about which.

The risk in fixing it is the opposite error — reading a count that was never a
count. "call 911" must not become one task to call, nine hundred and eleven
times. So the tests below are as much about what is left alone.
"""
from __future__ import annotations

import pytest

from assistant.actions.todo.intent import CreateTodoIntent
from assistant.intent.quantity import collapse_repeats, split_quantity


@pytest.mark.parametrize("said, title, qty", [
    # The forms that started this.
    ("buy pasta times 5",   "buy pasta",  5),
    ("buy pasta times five", "buy pasta", 5),
    ("pasta x5",            "pasta",      5),
    ("pasta X 5",           "pasta",      5),
    ("pasta ×5",            "pasta",      5),
    ("5x pasta",            "pasta",      5),
    ("x5 pasta",            "pasta",      5),
    # A count after a buying verb is a count of the thing.
    ("buy 5 apples",        "buy apples", 5),
    ("get 3 bottles of water", "get bottles of water", 3),
    ("buy a dozen eggs",    "buy eggs",  12),
    # Punctuation the count leaves behind is cleaned up.
    ("buy pasta, x5",       "buy pasta",  5),
    ("buy pasta - times 3", "buy pasta",  3),
])
def test_a_count_becomes_a_quantity(said, title, qty):
    assert split_quantity(said) == (title, qty)


@pytest.mark.parametrize("said", [
    "call 911",                  # not 911 phone calls
    "pay invoice 42",            # an identifier, not a count
    "buy an apple",              # one of a thing is the default
    "meeting at 5",              # a time
    "read chapter 7",            # not a buying verb
    "book table for 4",          # covered by neither rule, and shouldn't be
    "buy milk",                  # nothing to read
    "renew passport 2026",       # four digits is never a count
    "call 5 people",             # 'call' is not a buying verb
])
def test_a_number_that_is_not_a_count_is_left_alone(said):
    """A false positive silently changes what was asked for, so the rules only
    fire on an explicit multiplier or a count after a verb that implies buying."""
    assert split_quantity(said) == (said, 1)


def test_three_digit_numbers_are_never_counts():
    """The cap is what keeps house numbers and years out."""
    assert split_quantity("buy 250 stamps") == ("buy 250 stamps", 1)


def test_repeated_titles_fold_into_one_with_a_count():
    """The exact shape the LLM produced for 'pasta times 5'."""
    titles, quantities = collapse_repeats(["buy pasta"] * 5)
    assert titles == ["buy pasta"]
    assert quantities == [5]


def test_folding_keeps_the_order_things_were_first_said():
    titles, quantities = collapse_repeats(["milk", "bread", "milk"])
    assert titles == ["milk", "bread"]
    assert quantities == [2, 1]


def test_folding_is_case_insensitive_but_keeps_the_first_spelling():
    titles, quantities = collapse_repeats(["Buy Pasta", "buy pasta"])
    assert titles == ["Buy Pasta"]
    assert quantities == [2]


def test_counts_inside_repeated_titles_add_up():
    titles, quantities = collapse_repeats(["pasta x2", "pasta x3"])
    assert titles == ["pasta"]
    assert quantities == [5]


def test_distinct_items_are_not_folded():
    titles, quantities = collapse_repeats(["buy milk", "buy bread"])
    assert titles == ["buy milk", "buy bread"]
    assert quantities == [1, 1]


# --------------------------------------------------------------------------
# The intent is where the fix has to land — both parse paths build one
# --------------------------------------------------------------------------

def test_the_intent_folds_the_llms_five_copies():
    intent = CreateTodoIntent(titles=["buy pasta"] * 5)
    assert intent.titles == ["buy pasta"]
    assert intent.quantity_for(0) == 5


def test_the_intent_reads_a_count_out_of_a_single_title():
    intent = CreateTodoIntent(titles=["buy pasta x5"])
    assert intent.titles == ["buy pasta"]
    assert intent.quantity_for(0) == 5


def test_an_ordinary_list_is_untouched():
    intent = CreateTodoIntent(titles=["buy chicken", "buy rice"])
    assert intent.titles == ["buy chicken", "buy rice"]
    assert [intent.quantity_for(i) for i in range(2)] == [1, 1]


def test_quantity_for_defaults_to_one_when_asked_out_of_range():
    """Callers index by position; a mismatch must not raise mid-write."""
    assert CreateTodoIntent(titles=["x"]).quantity_for(99) == 1


def test_the_quantity_reaches_the_database(tmp_path, monkeypatch):
    monkeypatch.setenv("MACALENDAR_DB", str(tmp_path / "c.db"))
    from assistant.db import CalendarDB
    db = CalendarDB(str(tmp_path / "c.db"))
    todo_id = db.create_todo(title="buy pasta", quantity=5)
    assert db.get_todo(todo_id)["quantity"] == 5


def test_an_existing_task_defaults_to_one(tmp_path):
    """Every row created before the column existed reads back as 1, not null."""
    from assistant.db import CalendarDB
    db = CalendarDB(str(tmp_path / "c.db"))
    todo_id = db.create_todo(title="buy milk")
    assert db.get_todo(todo_id)["quantity"] == 1


def test_quantity_can_be_edited_and_never_goes_below_one(tmp_path):
    from assistant.db import CalendarDB
    db = CalendarDB(str(tmp_path / "c.db"))
    todo_id = db.create_todo(title="buy pasta", quantity=5)
    db.update_todo(todo_id, quantity=2)
    assert db.get_todo(todo_id)["quantity"] == 2
    db.update_todo(todo_id, quantity=0)
    assert db.get_todo(todo_id)["quantity"] == 1


# --------------------------------------------------------------------------
# End to end: the exact shape that reached the phone
# --------------------------------------------------------------------------

def test_the_command_that_started_this_makes_one_task(sample_config):
    """'…which includes pasta times 5' → one task, quantity 5, not five rows.

    Runs against the scratch database conftest points every store at — the
    real one refuses to open from a test at all.
    """
    import assistant.db as dbmod

    from assistant.actions.todo.action import CreateTodoAction
    from assistant.actions.todo.intent import CreateTodoIntent

    db = dbmod.get_db()
    before = {r["id"] for r in db.get_todos(list_name="today")}

    intent = CreateTodoIntent(titles=["buy pasta"] * 5, list_name="today")
    speech = CreateTodoAction().execute(intent, sample_config)

    made = [r for r in db.get_todos(list_name="today") if r["id"] not in before]
    assert len(made) == 1, f"expected one task, got {[r['title'] for r in made]}"
    assert made[0]["title"] == "buy pasta"
    assert made[0]["quantity"] == 5
    # And it is said back as five, so the mistake is visible if it recurs.
    assert "5" in speech
