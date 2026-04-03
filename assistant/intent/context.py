"""Centralized cross-session context memory for anaphora resolution.

Replaces the scattered module-level globals (_last_event_id, _last_todo_id, etc.)
previously living in calendar/action.py and todo/action.py. By centralizing here,
the RuleBasedParser can resolve anaphoric references ("it", "that") at parse time
without circular imports into action modules.
"""
from __future__ import annotations

import threading
from typing import Optional


class ContextMemory:
    """Thread-safe Borg singleton holding the most recently touched
    event and todo IDs/titles for anaphoric reference ('it', 'that').

    Uses the Borg pattern (shared state dict) so all instances are the same object.
    """

    _shared: dict = {}
    _lock: threading.Lock = threading.Lock()

    def __init__(self) -> None:
        self.__dict__ = self._shared

    # --- Event memory ---
    last_event_id: Optional[int] = None
    last_event_title: Optional[str] = None
    last_event_date: Optional[str] = None   # ISO date, for UI navigation

    # --- Todo memory ---
    last_todo_id: Optional[int] = None
    last_todo_title: Optional[str] = None

    def update_event(self, event_id: int, title: str, date: str) -> None:
        with self._lock:
            self.last_event_id = event_id
            self.last_event_title = title
            self.last_event_date = date

    def update_todo(self, todo_id: int, title: str) -> None:
        with self._lock:
            self.last_todo_id = todo_id
            self.last_todo_title = title

    def clear_event(self) -> None:
        with self._lock:
            self.last_event_id = None
            self.last_event_title = None
            self.last_event_date = None

    def clear_todo(self) -> None:
        with self._lock:
            self.last_todo_id = None
            self.last_todo_title = None

    def reset(self) -> None:
        """Clear all memory. Used in tests."""
        with self._lock:
            self.last_event_id = None
            self.last_event_title = None
            self.last_event_date = None
            self.last_todo_id = None
            self.last_todo_title = None


# Module-level singleton — import this everywhere
context_memory = ContextMemory()
