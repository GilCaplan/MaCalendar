"""SQLite-backed local calendar event storage."""

from __future__ import annotations

import calendar
import datetime
import os
import sqlite3
from contextlib import contextmanager
from typing import Generator, List, Optional

from assistant.actions.calendar.intent import CalendarIntent

DB_PATH = os.path.expanduser("~/.assistant_tools/calendar.db")

_CREATE_TODOS_TABLE = """
CREATE TABLE IF NOT EXISTS todos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT    NOT NULL,
    list            TEXT    NOT NULL DEFAULT 'today',
    completed       INTEGER NOT NULL DEFAULT 0,
    priority        TEXT    NOT NULL DEFAULT 'none',
    due_date        TEXT    NOT NULL DEFAULT '',
    notes           TEXT    NOT NULL DEFAULT '',
    source          TEXT    NOT NULL DEFAULT 'manual',
    source_event_id INTEGER,
    created_at      TEXT    NOT NULL,
    completed_at    TEXT    NOT NULL DEFAULT ''
)
"""

_TODO_MIGRATIONS = [
    "ALTER TABLE todos ADD COLUMN priority TEXT NOT NULL DEFAULT 'none'",
    "ALTER TABLE todos ADD COLUMN due_date TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE todos ADD COLUMN notes TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE todos ADD COLUMN source_event_id INTEGER",
    "ALTER TABLE todos ADD COLUMN completed_at TEXT NOT NULL DEFAULT ''",
]

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    title          TEXT    NOT NULL,
    date           TEXT    NOT NULL,
    start_time     TEXT    NOT NULL,
    end_time       TEXT    NOT NULL,
    attendees      TEXT    NOT NULL DEFAULT '',
    location       TEXT    NOT NULL DEFAULT '',
    description    TEXT    NOT NULL DEFAULT '',
    color          TEXT    NOT NULL DEFAULT '#0078d4',
    created_at     TEXT    NOT NULL,
    series_id      INTEGER,               -- NULL = not recurring; shared by all instances
    recurrence     TEXT    NOT NULL DEFAULT '',   -- '' | 'daily' | 'weekly' | 'monthly'
    recurrence_end TEXT    NOT NULL DEFAULT ''    -- '' or ISO date (last allowed date)
)
"""

# Columns added after initial release — migrated on first open
_MIGRATIONS = [
    "ALTER TABLE events ADD COLUMN series_id INTEGER",
    "ALTER TABLE events ADD COLUMN recurrence TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE events ADD COLUMN recurrence_end TEXT NOT NULL DEFAULT ''",
]


_CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_events_date   ON events(date);
CREATE INDEX IF NOT EXISTS idx_events_series ON events(series_id);
CREATE INDEX IF NOT EXISTS idx_todos_list    ON todos(list, completed);
"""


def _next_date(d: datetime.date, recurrence: str) -> datetime.date:
    """Advance d by one recurrence period."""
    if recurrence == "daily":
        return d + datetime.timedelta(days=1)
    if recurrence == "weekly":
        return d + datetime.timedelta(weeks=1)
    if recurrence == "monthly":
        month = d.month + 1
        year = d.year
        if month > 12:
            month = 1
            year += 1
        # Clamp day to the last valid day of the target month
        max_day = calendar.monthrange(year, month)[1]
        return datetime.date(year, month, min(d.day, max_day))
    raise ValueError(f"Unknown recurrence: {recurrence!r}")


class CalendarDB:
    """Thread-safe SQLite calendar event store."""

    def __init__(self, path: str | None = None) -> None:
        self.path = path if path is not None else DB_PATH
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with self._conn() as conn:
            conn.execute(_CREATE_TABLE)
            self._migrate(conn)
            conn.execute(_CREATE_TODOS_TABLE)
            self._migrate_todos(conn)
            for stmt in _CREATE_INDEXES.strip().splitlines():
                stmt = stmt.strip()
                if stmt:
                    conn.execute(stmt)

    def _migrate(self, conn: sqlite3.Connection) -> None:
        """Apply any missing schema migrations safely."""
        existing = {r[1] for r in conn.execute("PRAGMA table_info(events)")}
        for stmt in _MIGRATIONS:
            col = stmt.split("ADD COLUMN")[1].strip().split()[0]
            if col not in existing:
                try:
                    conn.execute(stmt)
                except sqlite3.OperationalError:
                    pass  # already exists

    def _migrate_todos(self, conn: sqlite3.Connection) -> None:
        """Apply any missing todos schema migrations safely."""
        existing = {r[1] for r in conn.execute("PRAGMA table_info(todos)")}
        for stmt in _TODO_MIGRATIONS:
            col = stmt.split("ADD COLUMN")[1].strip().split()[0]
            if col not in existing:
                try:
                    conn.execute(stmt)
                except sqlite3.OperationalError:
                    pass  # already exists

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create_event(self, intent: CalendarIntent, color: str = "#0078d4") -> int:
        """Insert a single event (or first instance of a series). Returns new row id."""
        recurrence = getattr(intent, "recurrence", None) or ""
        recur_until = getattr(intent, "recur_until", None) or ""

        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO events
                    (title, date, start_time, end_time, attendees, location, description,
                     color, created_at, series_id, recurrence, recurrence_end)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    intent.title,
                    intent.date,
                    intent.start_time,
                    intent.end_time,
                    ", ".join(intent.attendees),
                    intent.location or "",
                    intent.description or "",
                    color,
                    datetime.datetime.now().isoformat(),
                    None,       # series_id set below if recurring
                    recurrence,
                    recur_until,
                ),
            )
            first_id = cur.lastrowid

            if recurrence:
                # Create all subsequent instances and link them with series_id
                self._create_series_instances(
                    conn, first_id, intent, recurrence, recur_until, color
                )

        return first_id

    def _create_series_instances(
        self,
        conn: sqlite3.Connection,
        first_id: int,
        intent: CalendarIntent,
        recurrence: str,
        recur_until: str,
        color: str,
    ) -> None:
        """Generate and insert all recurrence instances; also back-fill series_id on first row."""
        end_date = (
            datetime.date.fromisoformat(recur_until)
            if recur_until
            else datetime.date.fromisoformat(intent.date) + datetime.timedelta(days=365)
        )

        # Back-fill series_id on the first (already inserted) row
        conn.execute("UPDATE events SET series_id = ? WHERE id = ?", (first_id, first_id))

        current = datetime.date.fromisoformat(intent.date)
        count = 0
        max_instances = 500  # hard safety cap

        while count < max_instances:
            current = _next_date(current, recurrence)
            if current > end_date:
                break
            conn.execute(
                """
                INSERT INTO events
                    (title, date, start_time, end_time, attendees, location, description,
                     color, created_at, series_id, recurrence, recurrence_end)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    intent.title,
                    current.isoformat(),
                    intent.start_time,
                    intent.end_time,
                    ", ".join(intent.attendees),
                    intent.location or "",
                    intent.description or "",
                    color,
                    datetime.datetime.now().isoformat(),
                    first_id,
                    recurrence,
                    recur_until,
                ),
            )
            count += 1

    def create_event_from_dict(self, data: dict) -> int:
        """Create an event from a plain dict (used by EventDialog)."""
        recurrence = data.get("recurrence", "")
        recur_until = data.get("recurrence_end", "")

        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO events
                    (title, date, start_time, end_time, attendees, location, description,
                     color, created_at, series_id, recurrence, recurrence_end)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["title"],
                    data["date"],
                    data["start_time"],
                    data["end_time"],
                    data.get("attendees", ""),
                    data.get("location", ""),
                    data.get("description", ""),
                    data.get("color", "#0078d4"),
                    datetime.datetime.now().isoformat(),
                    None,
                    recurrence,
                    recur_until,
                ),
            )
            first_id = cur.lastrowid

            if recurrence:
                # Build a minimal intent-like object for _create_series_instances
                class _FakeIntent:
                    title = data["title"]
                    date = data["date"]
                    start_time = data["start_time"]
                    end_time = data["end_time"]
                    attendees: list = []
                    location = data.get("location", "")
                    description = data.get("description", "")

                self._create_series_instances(
                    conn, first_id, _FakeIntent(), recurrence, recur_until,
                    data.get("color", "#0078d4")
                )

        return first_id

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_events_for_month(self, year: int, month: int) -> List[dict]:
        """Return all events whose date falls in the given month."""
        prefix = f"{year:04d}-{month:02d}"
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE date LIKE ? ORDER BY date, start_time",
                (f"{prefix}%",),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_events_for_week(self, start_date: datetime.date) -> List[dict]:
        """Return events for the 7 days starting from start_date."""
        end_date = start_date + datetime.timedelta(days=6)
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE date >= ? AND date <= ? ORDER BY date, start_time",
                (start_date.isoformat(), end_date.isoformat()),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_events_for_day(self, date: datetime.date) -> List[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE date = ? ORDER BY start_time",
                (date.isoformat(),),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_event(self, event_id: int) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        return dict(row) if row else None

    def get_series_events(self, series_id: int) -> List[dict]:
        """Return all events belonging to a recurring series."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE series_id = ? OR id = ? ORDER BY date, start_time",
                (series_id, series_id),
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update_event(self, event_id: int, **fields) -> None:
        allowed = {"title", "date", "start_time", "end_time", "attendees",
                   "location", "description", "color", "recurrence", "recurrence_end"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [event_id]
        with self._conn() as conn:
            conn.execute(f"UPDATE events SET {set_clause} WHERE id = ?", values)

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_event(self, event_id: int) -> None:
        """Delete a single event instance."""
        with self._conn() as conn:
            conn.execute("DELETE FROM events WHERE id = ?", (event_id,))

    def delete_series(self, series_id: int) -> int:
        """Delete all events in a series. Returns the count deleted."""
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM events WHERE series_id = ? OR id = ?",
                (series_id, series_id),
            )
            return cur.rowcount

    def delete_series_from(self, series_id: int, from_date: str) -> int:
        """Delete this event and all future instances in the series."""
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM events WHERE (series_id = ? OR id = ?) AND date >= ?",
                (series_id, series_id, from_date),
            )
            return cur.rowcount

    # ------------------------------------------------------------------
    # Todos: Create
    # ------------------------------------------------------------------

    def create_todo(
        self,
        title: str,
        list_name: str = "today",
        priority: str = "none",
        due_date: str = "",
        notes: str = "",
        source: str = "manual",
        source_event_id: Optional[int] = None,
    ) -> int:
        """Insert a new todo item. Returns the new row id."""
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO todos
                    (title, list, completed, priority, due_date, notes,
                     source, source_event_id, created_at, completed_at)
                VALUES (?, ?, 0, ?, ?, ?, ?, ?, ?, '')
                """,
                (
                    title,
                    list_name,
                    priority,
                    due_date,
                    notes,
                    source,
                    source_event_id,
                    datetime.datetime.now().isoformat(),
                ),
            )
            return cur.lastrowid

    # ------------------------------------------------------------------
    # Todos: Read
    # ------------------------------------------------------------------

    def get_todos(
        self,
        list_name: Optional[str] = None,
        include_completed: bool = False,
    ) -> List[dict]:
        """Return todos, optionally filtered by list and/or completion state."""
        query = "SELECT * FROM todos"
        conditions: List[str] = []
        params: List = []
        if list_name is not None:
            conditions.append("list = ?")
            params.append(list_name)
        if not include_completed:
            conditions.append("completed = 0")
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY completed ASC, created_at ASC"
        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_todo(self, todo_id: int) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM todos WHERE id = ?", (todo_id,)).fetchone()
        return dict(row) if row else None

    def get_todos_by_source(
        self, source: str, source_event_id: Optional[int] = None
    ) -> List[dict]:
        if source_event_id is not None:
            with self._conn() as conn:
                rows = conn.execute(
                    "SELECT * FROM todos WHERE source = ? AND source_event_id = ?",
                    (source, source_event_id),
                ).fetchall()
        else:
            with self._conn() as conn:
                rows = conn.execute(
                    "SELECT * FROM todos WHERE source = ?", (source,)
                ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Todos: Update
    # ------------------------------------------------------------------

    def update_todo(self, todo_id: int, **fields) -> None:
        allowed = {"title", "list", "completed", "priority", "due_date", "notes", "completed_at"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [todo_id]
        with self._conn() as conn:
            conn.execute(f"UPDATE todos SET {set_clause} WHERE id = ?", values)

    def toggle_todo_complete(self, todo_id: int) -> bool:
        """Flip completed flag; update completed_at. Returns new completed state."""
        todo = self.get_todo(todo_id)
        if todo is None:
            return False
        new_state = 0 if todo["completed"] else 1
        completed_at = datetime.datetime.now().isoformat() if new_state else ""
        self.update_todo(todo_id, completed=new_state, completed_at=completed_at)
        return bool(new_state)

    # ------------------------------------------------------------------
    # Todos: Delete
    # ------------------------------------------------------------------

    def delete_todo(self, todo_id: int) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM todos WHERE id = ?", (todo_id,))

    def delete_todos_by_source(self, source: str) -> int:
        """Delete all todos with the given source. Returns count deleted."""
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM todos WHERE source = ?", (source,))
            return cur.rowcount

    # ------------------------------------------------------------------
    # Todos: Calendar Sync
    # ------------------------------------------------------------------

    def sync_calendar_to_todos(self, list_name: str = "today") -> int:
        """
        Pull calendar events into the todos table with source='calendar_sync'.
        Upserts by source_event_id so manually completed synced tasks keep
        their completion state across re-syncs.
        Returns the count of todos created or updated.
        """
        today = datetime.date.today()
        if list_name == "general":
            events = self.get_events_for_week(today)
        else:
            events = self.get_events_for_day(today)

        # Build lookup of existing synced todos: source_event_id → row
        existing: dict[int, dict] = {}
        for row in self.get_todos_by_source("calendar_sync"):
            if row["source_event_id"] is not None:
                existing[row["source_event_id"]] = row

        # Remove synced todos whose source event no longer exists
        incoming_ids = {ev["id"] for ev in events}
        for ev_id, row in existing.items():
            if ev_id not in incoming_ids:
                self.delete_todo(row["id"])

        count = 0
        for ev in events:
            if ev["id"] in existing:
                # Update title (event may have been renamed) but keep completion state
                self.update_todo(existing[ev["id"]]["id"], title=ev["title"])
            else:
                self.create_todo(
                    title=ev["title"],
                    list_name=list_name,
                    source="calendar_sync",
                    source_event_id=ev["id"],
                )
            count += 1
        return count

    # ------------------------------------------------------------------
    # Util
    # ------------------------------------------------------------------

    def clear_all(self) -> None:
        """Wipe all events from the database."""
        with self._conn() as conn:
            conn.execute("DELETE FROM events")
            conn.execute("DELETE FROM sqlite_sequence WHERE name='events'")  # reset IDs

    def clear_all_todos(self) -> None:
        """Wipe all todos from the database."""
        with self._conn() as conn:
            conn.execute("DELETE FROM todos")
            conn.execute("DELETE FROM sqlite_sequence WHERE name='todos'")  # reset IDs


# ---------------------------------------------------------------------------
# Module-level singleton — avoids re-running migrations on every action call
# ---------------------------------------------------------------------------

_db_instance: Optional[CalendarDB] = None


def get_db() -> CalendarDB:
    """Return the shared CalendarDB instance, creating it once on first call."""
    global _db_instance
    if _db_instance is None:
        _db_instance = CalendarDB()
    return _db_instance
