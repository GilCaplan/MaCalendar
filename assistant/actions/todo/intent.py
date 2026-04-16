"""Intent models for todo voice actions."""

from __future__ import annotations

from typing import List, Optional

from pydantic import field_validator, model_validator

from assistant.actions.base import BaseIntent


class CreateTodoIntent(BaseIntent):
    titles: List[str] = []
    list_name: str = "today"   # 'today' | 'general'
    priority: str = "none"     # 'none' | 'low' | 'medium' | 'high'
    due_date: Optional[str] = None

    @field_validator("titles", mode="before")
    @classmethod
    def coerce_titles(cls, v):
        if isinstance(v, str):
            return [t.strip() for t in v.split(",") if t.strip()]
        return v

    @model_validator(mode="after")
    def require_titles(self) -> "CreateTodoIntent":
        if not self.titles:
            raise ValueError("titles list cannot be empty")
        return self


class CompleteTodoIntent(BaseIntent):
    match_title: str
    complete: bool = True   # False = uncheck


class DeleteTodoIntent(BaseIntent):
    match_title: str


class UpdateTodoIntent(BaseIntent):
    match_title: str
    new_title: Optional[str] = None
    new_list: Optional[str] = None
    new_priority: Optional[str] = None
    new_due_date: Optional[str] = None   # ISO date string, e.g. '2026-04-01'
    new_notes: Optional[str] = None      # Replace/set the task notes


class QueryTodoIntent(BaseIntent):
    list_name: str = "all"         # 'today' | 'general' | 'all'
    include_completed: bool = False


class AddSubtaskIntent(BaseIntent):
    parent_title: str       # which parent task to add the subtask to
    subtask_title: str      # title of the new subtask


class CompleteSubtaskIntent(BaseIntent):
    parent_title: str
    subtask_title: str
    complete: bool = True   # False = uncheck


class DeleteSubtaskIntent(BaseIntent):
    parent_title: str
    subtask_title: str
