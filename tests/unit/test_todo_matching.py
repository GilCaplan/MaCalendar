"""Unit tests for `_find_todo` in assistant/actions/todo/action.py — the fuzzy
matcher every delete_todo/update_todo/complete_todo voice command depends on to
resolve "the grocery task" to a specific row. Mirrors test_event_matching.py's
coverage of the calendar-side matcher.
"""
from __future__ import annotations

import pytest

from assistant.actions.todo.action import _find_todo
from assistant.db import CalendarDB
from assistant.intent.context import context_memory


@pytest.fixture
def db(tmp_path) -> CalendarDB:
    return CalendarDB(path=str(tmp_path / "todo_matching_test.db"))


def _add_todo(db, title, list_name="today") -> int:
    return db.create_todo(title=title, list_name=list_name, priority="none", due_date="", notes="")


def test_exact_title_match(db):
    _add_todo(db, "Buy groceries")
    result = _find_todo(db, "Buy groceries")
    assert result["title"] == "Buy groceries"


def test_partial_token_overlap_match(db):
    _add_todo(db, "Buy organic groceries for the week")
    result = _find_todo(db, "groceries")
    assert result["title"] == "Buy organic groceries for the week"


def test_substring_boost_wins_over_weaker_overlap(db):
    _add_todo(db, "Call mom about the groceries")
    _add_todo(db, "wash dishes")
    result = _find_todo(db, "wash dishes")
    assert result["title"] == "wash dishes"


def test_no_match_returns_none(db):
    _add_todo(db, "Buy groceries")
    result = _find_todo(db, "quantum physics symposium")
    assert result is None


def test_best_scoring_todo_wins_among_multiple_candidates(db):
    _add_todo(db, "Call dentist")
    _add_todo(db, "Call mom")
    result = _find_todo(db, "call mom")
    assert result["title"] == "Call mom"


def test_matches_across_completed_and_pending(db):
    """Fuzzy matching (e.g. for 'uncheck the grocery task') must consider
    completed todos too, not just pending ones.
    """
    todo_id = _add_todo(db, "Buy groceries")
    db.toggle_todo_complete(todo_id)
    result = _find_todo(db, "groceries")
    assert result["id"] == todo_id
    assert result["completed"] == 1


def test_anaphor_resolves_via_context_memory(db):
    context_memory.reset()
    todo_id = _add_todo(db, "Buy groceries")
    context_memory.update_todo(todo_id, "Buy groceries")

    result = _find_todo(db, "it")
    assert result["id"] == todo_id
    context_memory.reset()


def test_anaphor_with_no_memory_returns_none(db):
    context_memory.reset()
    _add_todo(db, "Buy groceries")
    result = _find_todo(db, "it")
    assert result is None
