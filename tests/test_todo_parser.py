"""
Todo feature integration tests — mirrors tests/test_ollama_parser.py pattern.

These tests run through the full pipeline after the transcribe step:
  parsed_intents → execute action → verify DB state

Two modes:
  1. With Ollama: `python tests/test_todo_parser.py`        (requires `ollama serve`)
  2. Direct exec:  `python tests/test_todo_parser.py --direct` (no LLM needed, uses pre-built intents)
"""

import datetime
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import assistant.actions.calendar  # noqa: F401
import assistant.actions.todo      # noqa: F401

from assistant.actions import registry
from assistant.config import load_config
from assistant.db import CalendarDB

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TMP_DB_PATH = None
_db_instance: CalendarDB = None


def _get_db() -> CalendarDB:
    global _db_instance
    return _db_instance


def clear_todos():
    db = _get_db()
    with db._conn() as conn:
        conn.execute("DELETE FROM todos")
        conn.execute("DELETE FROM sqlite_sequence WHERE name='todos'")
    todos = db.get_todos(include_completed=True)
    assert len(todos) == 0, "Failed to clear todos"


def run_test_direct(intents_list: list, expected_count: int, test_name: str, seed_todos: list = None):
    """Execute a list of (action_name, IntentObject) directly (no LLM)."""
    print(f"\n==============================================")
    print(f"🎬 Test: {test_name}")

    clear_todos()

    # Seed DB
    db = _get_db()
    if seed_todos:
        for seed in seed_todos:
            db.create_todo(**seed)

    config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config.yaml"))
    config = load_config(config_path)

    results = []
    for action_name, intent in intents_list:
        action_cls = registry.get(action_name)
        result = action_cls().execute(intent, config)
        print(f"   ✅ {action_name}: {result}")
        results.append(result)

    todos = db.get_todos(include_completed=True)
    pending = [t for t in todos if not t["completed"]]
    print(f"📊 DB todos: {len(todos)} total, {len(pending)} pending")
    for t in todos:
        done = "✓" if t["completed"] else "○"
        print(f"   [{done}] [{t['list']}] {t['title']} (priority: {t['priority']})")

    assert len(pending) == expected_count, (
        f"❌ {test_name}: Expected {expected_count} pending, got {len(pending)}"
    )
    print(f"🟢 Passed {test_name}!")
    return todos, results


def run_test_llm(parser, expected_count: int, test_name: str, transcript: str, seed_todos: list = None):
    """Parse a transcript via LLM → execute → verify."""
    print(f"\n==============================================")
    print(f"🎬 LLM Test: {test_name}")
    print(f"Transcript: '{transcript}'")

    clear_todos()

    db = _get_db()
    if seed_todos:
        for seed in seed_todos:
            db.create_todo(**seed)

    config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config.yaml"))
    config = load_config(config_path)

    print("⏳ Parsing via LLM...")
    actions_tuples = parser.parse(transcript)
    valid = [(n, i) for n, i in actions_tuples if n != "unknown"]
    print(f"🔍 Parsed {len(valid)} valid actions:")
    for n, i in valid:
        print(f"   -> {n}: {i}")

    for action_name, intent in valid:
        action_cls = registry.get(action_name)
        result = action_cls().execute(intent, config)
        print(f"   ✅ {action_name}: {result}")

    todos = db.get_todos(include_completed=True)
    pending = [t for t in todos if not t["completed"]]
    print(f"📊 DB todos: {len(todos)} total, {len(pending)} pending")
    for t in todos:
        done = "✓" if t["completed"] else "○"
        print(f"   [{done}] [{t['list']}] {t['title']}")

    assert len(pending) == expected_count, (
        f"❌ {test_name}: Expected {expected_count} pending, got {len(pending)}"
    )
    print(f"🟢 Passed {test_name}!")
    return todos


# ---------------------------------------------------------------------------
# Direct tests (no LLM required)
# ---------------------------------------------------------------------------

def run_direct_tests():
    from assistant.actions.todo.intent import (
        AddSubtaskIntent,
        CompleteTodoIntent,
        CompleteSubtaskIntent,
        CreateTodoIntent,
        DeleteSubtaskIntent,
        DeleteTodoIntent,
        QueryTodoIntent,
        UpdateTodoIntent,
    )

    print("\n" + "=" * 60)
    print("DIRECT EXECUTION TESTS (no LLM required)")
    print("=" * 60)

    # SCENARIO 1: Single task creation
    run_test_direct(
        [("create_todo", CreateTodoIntent(titles=["buy groceries"]))],
        expected_count=1,
        test_name="Single Task Creation",
    )

    # SCENARIO 2: Multi-task creation (the key new feature)
    todos, results = run_test_direct(
        [("create_todo", CreateTodoIntent(
            titles=["buy groceries", "call dentist", "walk the dog"],
            list_name="today",
        ))],
        expected_count=3,
        test_name="Multi-Task Creation (3 tasks in one voice command)",
    )
    assert "3 tasks" in results[0], f"Expected '3 tasks' in result, got: {results[0]}"

    # SCENARIO 3: Create then complete via fuzzy match
    todos, results = run_test_direct(
        [
            ("create_todo", CreateTodoIntent(titles=["wash dishes"])),
            ("complete_todo", CompleteTodoIntent(match_title="wash")),  # partial match
        ],
        expected_count=0,   # completed → no pending
        test_name="Create then Complete (fuzzy title match)",
    )
    db = _get_db()
    all_todos = db.get_todos(include_completed=True)
    assert any(t["completed"] for t in all_todos), "Task should be completed"

    # SCENARIO 4: Anaphoric 'it' reference — create then delete via "it"
    todos, results = run_test_direct(
        [
            ("create_todo", CreateTodoIntent(titles=["buy milk"])),
            ("delete_todo", DeleteTodoIntent(match_title="it")),
        ],
        expected_count=0,
        test_name="Anaphoric 'it' Delete",
    )
    assert any("Deleted" in r for r in results), f"Expected 'Deleted' in results: {results}"
    print("   ✅ Anaphor 'it' deleted the last created todo")

    # SCENARIO 5: Update task title and list
    run_test_direct(
        [
            ("create_todo", CreateTodoIntent(titles=["grocery run"])),
            ("update_todo", UpdateTodoIntent(
                match_title="grocery",
                new_title="buy organic groceries",
                new_list="general",
                new_priority="high",
            )),
        ],
        expected_count=1,
        test_name="Update Task (rename + move list + priority)",
    )
    db = _get_db()
    updated = db.get_todos(include_completed=True)
    assert updated[0]["title"] == "buy organic groceries"
    assert updated[0]["list"] == "general"
    assert updated[0]["priority"] == "high"
    print("   ✅ Title, list, and priority correctly updated")

    # SCENARIO 6: Query returns correct spoken summary
    clear_todos()
    config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config.yaml"))
    config = load_config(config_path)
    db = _get_db()
    for title in ["task A", "task B", "task C"]:
        db.create_todo(title=title, list_name="today")
    query_cls = registry.get("query_todos")
    result = query_cls().execute(QueryTodoIntent(list_name="today"), config)
    assert "3 tasks" in result, f"Expected '3 tasks', got: {result}"
    assert "task A" in result and "task C" in result
    print(f"   ✅ Query result: {result}")
    print("🟢 Passed Query Summary!")

    # SCENARIO 7: Calendar sync → todos created, then cleared on sync-off
    clear_todos()
    today = datetime.date.today()
    db.create_event_from_dict({
        "title": "Morning standup",
        "date": today.isoformat(),
        "start_time": "09:00",
        "end_time": "09:30",
    })
    count = db.sync_calendar_to_todos(list_name="today")
    assert count == 1, f"Expected 1 synced todo, got {count}"
    synced = db.get_todos_by_source("calendar_sync")
    assert len(synced) == 1
    assert synced[0]["title"] == "Morning standup"
    print(f"   ✅ Calendar sync created {count} todo(s) from today's events")

    # Re-sync after completing the synced task — completion must be preserved
    db.toggle_todo_complete(synced[0]["id"])
    re_count = db.sync_calendar_to_todos(list_name="today")
    assert re_count == 1, f"Expected 1 on re-sync, got {re_count}"
    re_synced = db.get_todos_by_source("calendar_sync")
    assert len(re_synced) == 1
    assert re_synced[0]["completed"] == 1, "Re-sync should preserve completed state"
    print(f"   ✅ Re-sync preserved completed state of synced todo")

    # Sync off → clears synced todos, manual todos unaffected
    db.create_todo("manual task", list_name="today")
    deleted = db.delete_todos_by_source("calendar_sync")
    assert deleted == 1
    remaining = db.get_todos(include_completed=False)
    assert len(remaining) == 1 and remaining[0]["source"] == "manual"
    print(f"   ✅ Sync-off cleared calendar todos, manual tasks preserved")
    print("🟢 Passed Calendar Sync + Off!")

    # SCENARIO 8: Completed tasks don't appear in pending query
    clear_todos()
    id_x = db.create_todo("task X")
    db.create_todo("task Y")
    db.toggle_todo_complete(id_x)
    all_todos = db.get_todos(include_completed=True)
    pending = [t for t in all_todos if not t["completed"]]
    assert len(pending) == 1 and pending[0]["title"] == "task Y"
    print(f"\n==============================================")
    print("🎬 Test: Completed Tasks Hidden from Pending")
    print(f"   ✅ 2 tasks, 1 completed → 1 pending")
    print("🟢 Passed Completed Tasks Hidden from Pending!")

    # SCENARIO 9: Create with priority + due date
    next_week = (datetime.date.today() + datetime.timedelta(days=7)).isoformat()
    todos, results = run_test_direct(
        [("create_todo", CreateTodoIntent(
            titles=["submit report"],
            priority="high",
            due_date=next_week,
            list_name="today",
        ))],
        expected_count=1,
        test_name="Create Task with Priority + Due Date",
    )
    db = _get_db()
    created = db.get_todos(include_completed=True)
    assert created[0]["priority"] == "high", f"Expected high priority, got {created[0]['priority']}"
    assert created[0]["due_date"] == next_week, f"Expected due {next_week}, got {created[0]['due_date']}"
    assert "high priority" in results[0], f"Expected priority in response: {results[0]}"
    print("   ✅ Priority and due_date stored and confirmed in response")

    # SCENARIO 10: Update notes via voice
    _, results = run_test_direct(
        [
            ("create_todo", CreateTodoIntent(titles=["review PR"])),
            ("update_todo", UpdateTodoIntent(
                match_title="review PR",
                new_notes="Check tests and coverage before merging.",
            )),
        ],
        expected_count=1,
        test_name="Update Task Notes",
    )
    db = _get_db()
    updated = db.get_todos(include_completed=True)
    assert updated[0]["notes"] == "Check tests and coverage before merging.", (
        f"Unexpected notes: {updated[0]['notes']}"
    )
    assert "notes updated" in results[1], f"Expected 'notes updated' in response: {results[1]}"
    print("   ✅ Notes correctly stored and confirmed in response")

    # SCENARIO 11: Add subtask → complete subtask → delete subtask
    run_test_direct(
        [("create_todo", CreateTodoIntent(titles=["Modern Vision HW"]))],
        expected_count=1,
        test_name="Setup parent task for subtask tests",
    )
    db = _get_db()
    parent = db.get_todos(include_completed=True)[0]

    # Add subtask
    config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config.yaml"))
    config = load_config(config_path)
    add_cls = registry.get("add_subtask")
    add_result = add_cls().execute(
        AddSubtaskIntent(parent_title="Modern Vision HW", subtask_title="Read theory notes"),
        config,
    )
    print(f"   ✅ add_subtask: {add_result}")
    assert "Read theory notes" in add_result

    subtasks = db.get_subtasks(parent["id"])
    assert len(subtasks) == 1
    assert subtasks[0]["title"] == "Read theory notes"
    assert subtasks[0]["completed"] == 0

    # Complete subtask
    complete_cls = registry.get("complete_subtask")
    complete_result = complete_cls().execute(
        CompleteSubtaskIntent(parent_title="Modern Vision HW", subtask_title="Read theory"),
        config,
    )
    print(f"   ✅ complete_subtask: {complete_result}")
    assert "Completed" in complete_result
    subtasks = db.get_subtasks(parent["id"])
    assert subtasks[0]["completed"] == 1

    # Delete subtask
    delete_cls = registry.get("delete_subtask")
    delete_result = delete_cls().execute(
        DeleteSubtaskIntent(parent_title="Modern Vision HW", subtask_title="Read theory"),
        config,
    )
    print(f"   ✅ delete_subtask: {delete_result}")
    assert "Deleted" in delete_result
    subtasks = db.get_subtasks(parent["id"])
    assert len(subtasks) == 0
    print("🟢 Passed Subtask Add / Complete / Delete!")

    # SCENARIO 12: Query response includes priority for high-priority tasks
    clear_todos()
    db.create_todo("submit tax return", list_name="today", priority="high")
    db.create_todo("buy groceries", list_name="today", priority="none")
    query_cls = registry.get("query_todos")
    result = query_cls().execute(QueryTodoIntent(list_name="today"), config)
    assert "urgent" in result.lower(), f"Expected 'urgent' for high priority task in: {result}"
    assert "buy groceries" in result
    print(f"   ✅ Query includes priority hint: {result}")
    print("🟢 Passed Priority in Query Response!")

    print("\n" + "=" * 60)
    print("🎉 ALL DIRECT TESTS PASSED!")
    print("=" * 60)


# ---------------------------------------------------------------------------
# LLM-based tests (requires Ollama)
# ---------------------------------------------------------------------------

def run_llm_tests():
    from assistant.actions import ActionRegistry
    from assistant.intent.parser import IntentParser

    print("\n" + "=" * 60)
    print("LLM TESTS (requires Ollama)")
    print("=" * 60)

    reg = ActionRegistry()
    config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config.yaml"))
    config = load_config(config_path)
    parser = IntentParser(config, reg)

    print("Checking Ollama at", config.ollama.base_url)
    if not parser.health_check():
        print("❌ Ollama offline. Skipping LLM tests.\n")
        return

    print("✅ Ollama online. Running LLM todo tests...\n")

    # LLM SCENARIO 1: Single task via natural phrase
    run_test_llm(
        parser, expected_count=1,
        test_name="LLM: Single Task via Natural Phrase",
        transcript="Add task: call my dentist to schedule a cleaning.",
    )

    # LLM SCENARIO 2: Multi-task
    todos = run_test_llm(
        parser, expected_count=3,
        test_name="LLM: Multi-Task from Voice",
        transcript="Add tasks: buy milk, do laundry, and call mom.",
    )
    titles = [t["title"].lower() for t in todos if not t["completed"]]
    assert any("milk" in t for t in titles), f"'milk' not found in {titles}"
    assert any("laundry" in t for t in titles), f"'laundry' not found in {titles}"

    # LLM SCENARIO 3: Complete a task
    run_test_llm(
        parser, expected_count=0,
        test_name="LLM: Mark Task Done",
        transcript="Mark 'call dentist' as done.",
        seed_todos=[{"title": "call dentist", "list_name": "today"}],
    )

    # LLM SCENARIO 4: Query
    db = _get_db()
    clear_todos()
    db.create_todo("write report", list_name="today")
    db.create_todo("review PR", list_name="today")
    run_test_llm(
        parser, expected_count=2,
        test_name="LLM: Query Today's Tasks",
        transcript="What tasks do I have today?",
    )

    # LLM SCENARIO 5: General list task
    run_test_llm(
        parser, expected_count=1,
        test_name="LLM: Add to General List",
        transcript="Add 'learn Spanish' to my general list someday.",
    )
    db = _get_db()
    general = db.get_todos(list_name="general")
    assert len(general) >= 1, "Task not in general list"

    print("\n🎉 ALL LLM TESTS PASSED!")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    global _db_instance, _TMP_DB_PATH

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--direct", action="store_true",
                        help="Run only direct tests (no LLM required)")
    args = parser.parse_args()

    # Use a temporary DB so we don't touch the real one
    import tempfile
    tmpdir = tempfile.mkdtemp()
    _TMP_DB_PATH = os.path.join(tmpdir, "test_todos.db")

    # Patch DB path
    import assistant.db as db_mod
    original_path = db_mod.DB_PATH
    db_mod.DB_PATH = _TMP_DB_PATH

    _db_instance = CalendarDB(path=_TMP_DB_PATH)

    try:
        run_direct_tests()
        if not args.direct:
            run_llm_tests()
    finally:
        db_mod.DB_PATH = original_path

    print("\n✅ Test run complete.")


if __name__ == "__main__":
    main()
