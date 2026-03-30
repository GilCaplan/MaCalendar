"""Todo voice actions — create, complete, update, delete, and query tasks."""

from __future__ import annotations

import re
from typing import ClassVar, List, Optional, Type

from assistant.actions import register
from assistant.actions.base import BaseAction, BaseIntent
from assistant.actions.todo.intent import (
    CompleteTodoIntent,
    CreateTodoIntent,
    DeleteTodoIntent,
    QueryTodoIntent,
    UpdateTodoIntent,
)

# Global memory — remember the last created/modified todo for anaphoric reference
_last_todo_id: Optional[int] = None

_ANAPHORS = {"it", "that", "this", "the task", "that task", "the last one", "the last task"}


def _find_todo(db, match_title: str) -> Optional[dict]:
    """
    Find the best-matching todo by title.
    Resolves anaphoric pronouns via global memory.
    Uses token-based fuzzy scoring identical to the calendar _find_event pattern.
    """
    global _last_todo_id

    if match_title.lower().strip() in _ANAPHORS:
        if _last_todo_id is not None:
            return db.get_todo(_last_todo_id)
        return None

    needle_words = set(re.findall(r"\w+", match_title.lower()))
    todos = db.get_todos(include_completed=True)

    best_match = None
    best_score = 0

    for todo in todos:
        title_words = set(re.findall(r"\w+", todo["title"].lower()))
        overlap = len(needle_words & title_words)

        clean_needle = match_title.lower().replace("-", " ")
        clean_title = todo["title"].lower().replace("-", " ")
        if clean_title in clean_needle or clean_needle in clean_title:
            overlap += 10

        if overlap > best_score:
            best_score = overlap
            best_match = todo

    return best_match if best_score > 0 else None


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

@register
class CreateTodoAction(BaseAction):
    action_name: ClassVar[str] = "create_todo"
    view_switch: ClassVar[str] = "switch_todo"
    description: ClassVar[str] = (
        "Add one or more tasks/todos/reminders to the task list. "
        "Triggers on: 'add task X', 'remind me to X', 'add tasks X, Y, Z', "
        "'add to my list: X and Y', 'create a todo for X'. "
        "IMPORTANT: for multi-task phrases like 'add tasks: wash dishes, buy groceries', "
        "extract ALL tasks into the 'titles' array."
    )
    intent_model: ClassVar[Type[BaseIntent]] = CreateTodoIntent
    parameters_schema: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "titles": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "One or more task titles. Always use an array. "
                    "E.g. ['wash dishes'] or ['task A', 'task B', 'task C']."
                ),
            },
            "list_name": {
                "type": "string",
                "enum": ["today", "general"],
                "description": (
                    "Which list to add to. Default: 'today'. "
                    "Use 'general' if user says 'add to general list', 'someday', or no time context."
                ),
            },
            "priority": {
                "type": "string",
                "enum": ["none", "low", "medium", "high"],
                "description": "Optional priority. Default: 'none'.",
            },
        },
        "required": ["titles"],
    }

    def execute(self, intent: CreateTodoIntent, _config) -> str:  # type: ignore[override]
        global _last_todo_id
        from assistant.db import CalendarDB
        db = CalendarDB()

        created = []
        for title in intent.titles:
            todo_id = db.create_todo(
                title=title,
                list_name=intent.list_name,
                priority=intent.priority,
                due_date=intent.due_date or "",
            )
            _last_todo_id = todo_id
            created.append(title)

        list_label = "Today" if intent.list_name == "today" else "General"
        if len(created) == 1:
            return f"Added '{created[0]}' to {list_label}."
        return f"Added {len(created)} tasks to {list_label}."


# ---------------------------------------------------------------------------
# Complete / Uncheck
# ---------------------------------------------------------------------------

@register
class CompleteTodoAction(BaseAction):
    action_name: ClassVar[str] = "complete_todo"
    description: ClassVar[str] = (
        "Mark a task done or undo completion. "
        "Triggers on: 'mark X done', 'check off X', 'complete X', "
        "'mark X as done', 'uncheck X', 'mark X incomplete'."
    )
    intent_model: ClassVar[Type[BaseIntent]] = CompleteTodoIntent
    parameters_schema: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "match_title": {
                "type": "string",
                "description": "Title or partial title of the task to complete. Or 'it' for the last task.",
            },
            "complete": {
                "type": "boolean",
                "description": "True to mark done, False to uncheck. Default: true.",
            },
        },
        "required": ["match_title"],
    }

    def execute(self, intent: CompleteTodoIntent, _config) -> str:  # type: ignore[override]
        global _last_todo_id
        from assistant.db import CalendarDB
        db = CalendarDB()

        todo = _find_todo(db, intent.match_title)
        if todo is None:
            if intent.match_title.lower().strip() in _ANAPHORS:
                return "I don't remember the last task."
            return f"I couldn't find a task matching '{intent.match_title}'."

        _last_todo_id = todo["id"]
        if intent.complete:
            db.update_todo(todo["id"], completed=1,
                           completed_at=__import__("datetime").datetime.now().isoformat())
            return f"Marked '{todo['title']}' as done."
        else:
            db.update_todo(todo["id"], completed=0, completed_at="")
            return f"Unchecked '{todo['title']}'."


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

@register
class DeleteTodoAction(BaseAction):
    action_name: ClassVar[str] = "delete_todo"
    description: ClassVar[str] = (
        "Remove a task from the list. "
        "Triggers on: 'delete task X', 'remove X from my list', 'delete it'."
    )
    intent_model: ClassVar[Type[BaseIntent]] = DeleteTodoIntent
    parameters_schema: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "match_title": {
                "type": "string",
                "description": "Title or partial title of the task to delete. Or 'it'.",
            },
        },
        "required": ["match_title"],
    }

    def execute(self, intent: DeleteTodoIntent, _config) -> str:  # type: ignore[override]
        global _last_todo_id
        from assistant.db import CalendarDB
        db = CalendarDB()

        todo = _find_todo(db, intent.match_title)
        if todo is None:
            if intent.match_title.lower().strip() in _ANAPHORS:
                return "I don't remember the last task."
            return f"I couldn't find a task matching '{intent.match_title}'."

        db.delete_todo(todo["id"])
        if _last_todo_id == todo["id"]:
            _last_todo_id = None
        return f"Deleted '{todo['title']}'."


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

@register
class UpdateTodoAction(BaseAction):
    action_name: ClassVar[str] = "update_todo"
    description: ClassVar[str] = (
        "Edit an existing task's title, list, or priority. "
        "Triggers on: 'rename task X to Y', 'move X to general list', 'set X priority to high'."
    )
    intent_model: ClassVar[Type[BaseIntent]] = UpdateTodoIntent
    parameters_schema: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "match_title": {
                "type": "string",
                "description": "Title or partial title to find. Or 'it'.",
            },
            "new_title": {
                "type": "string",
                "description": "Replacement title. Omit if unchanged.",
            },
            "new_list": {
                "type": "string",
                "enum": ["today", "general"],
                "description": "Move to a different list. Omit if unchanged.",
            },
            "new_priority": {
                "type": "string",
                "enum": ["none", "low", "medium", "high"],
                "description": "New priority. Omit if unchanged.",
            },
        },
        "required": ["match_title"],
    }

    def execute(self, intent: UpdateTodoIntent, _config) -> str:  # type: ignore[override]
        global _last_todo_id
        from assistant.db import CalendarDB
        db = CalendarDB()

        todo = _find_todo(db, intent.match_title)
        if todo is None:
            if intent.match_title.lower().strip() in _ANAPHORS:
                return "I don't remember the last task."
            return f"I couldn't find a task matching '{intent.match_title}'."

        updates: dict = {}
        if intent.new_title:    updates["title"] = intent.new_title
        if intent.new_list:     updates["list"] = intent.new_list
        if intent.new_priority: updates["priority"] = intent.new_priority

        if not updates:
            return f"No changes specified for '{todo['title']}'."

        db.update_todo(todo["id"], **updates)
        _last_todo_id = todo["id"]
        display = updates.get("title", todo["title"])
        return f"Updated '{display}'."


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------

@register
class QueryTodoAction(BaseAction):
    action_name: ClassVar[str] = "query_todos"
    view_switch: ClassVar[str] = "switch_todo"
    description: ClassVar[str] = (
        "Read out the user's task list. "
        "Triggers on: 'what tasks do I have', 'what's on my list', "
        "'read my todos', 'how many tasks today', 'show my tasks'."
    )
    intent_model: ClassVar[Type[BaseIntent]] = QueryTodoIntent
    parameters_schema: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "list_name": {
                "type": "string",
                "enum": ["today", "general", "all"],
                "description": "Which list to query. Default: 'all'.",
            },
            "include_completed": {
                "type": "boolean",
                "description": "Include completed tasks. Default: false.",
            },
        },
        "required": [],
    }

    def execute(self, intent: QueryTodoIntent, _config) -> str:  # type: ignore[override]
        from assistant.db import CalendarDB
        db = CalendarDB()

        list_name = None if intent.list_name == "all" else intent.list_name
        todos = db.get_todos(list_name=list_name, include_completed=intent.include_completed)

        label = {"today": "Today", "general": "General", "all": "your lists"}.get(
            intent.list_name, "your lists"
        )

        pending = [t for t in todos if not t["completed"]]
        n = len(pending)

        if n == 0:
            return f"No pending tasks in {label}."

        titles = [t["title"] for t in pending]
        if n == 1:
            return f"You have one task in {label}: {titles[0]}."
        if n == 2:
            return f"You have 2 tasks in {label}: {titles[0]} and {titles[1]}."
        return f"You have {n} tasks in {label}: {', '.join(titles[:-1])}, and {titles[-1]}."
