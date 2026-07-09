"""Bounded undo/redo stack for direct UI actions (create/edit/delete/drag on
events via mouse/dialog). Independent of the voice-pipeline's own
background-verification undo+redo in pipeline.py, which reverses a
fast-path voice action after an LLM judges it wrong."""

from __future__ import annotations

from typing import Callable, List, NamedTuple, Optional

MAX_DEPTH = 20


class ActionRecord(NamedTuple):
    description: str
    undo_fn: Callable[[], None]
    redo_fn: Callable[[], None]


class UndoManager:
    def __init__(self) -> None:
        self._undo_stack: List[ActionRecord] = []
        self._redo_stack: List[ActionRecord] = []

    def push(self, description: str, undo_fn: Callable[[], None], redo_fn: Callable[[], None]) -> None:
        self._undo_stack.append(ActionRecord(description, undo_fn, redo_fn))
        if len(self._undo_stack) > MAX_DEPTH:
            self._undo_stack.pop(0)
        # A fresh action invalidates whatever redo history was there —
        # standard undo/redo semantics (matches every other app's Cmd+Z/⇧⌘Z).
        self._redo_stack.clear()

    def undo(self) -> Optional[str]:
        """Pop and run the most recent action's undo function, moving it to
        the redo stack. Returns its description, or None if empty."""
        if not self._undo_stack:
            return None
        record = self._undo_stack.pop()
        record.undo_fn()
        self._redo_stack.append(record)
        return record.description

    def redo(self) -> Optional[str]:
        """Pop and run the most recently undone action's redo function,
        moving it back to the undo stack. Returns its description, or None
        if there's nothing to redo."""
        if not self._redo_stack:
            return None
        record = self._redo_stack.pop()
        record.redo_fn()
        self._undo_stack.append(record)
        return record.description

    def clear(self) -> None:
        self._undo_stack.clear()
        self._redo_stack.clear()

    def __bool__(self) -> bool:
        return bool(self._undo_stack)
