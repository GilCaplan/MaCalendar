"""SQLite-backed local calendar event storage."""

from __future__ import annotations

import calendar
import datetime
import json
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
    completed_at    TEXT    NOT NULL DEFAULT '',
    position        INTEGER NOT NULL DEFAULT 0
)
"""

_TODO_MIGRATIONS = [
    "ALTER TABLE todos ADD COLUMN priority TEXT NOT NULL DEFAULT 'none'",
    "ALTER TABLE todos ADD COLUMN due_date TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE todos ADD COLUMN notes TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE todos ADD COLUMN source_event_id INTEGER",
    "ALTER TABLE todos ADD COLUMN completed_at TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE todos ADD COLUMN position INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE todos ADD COLUMN attachments TEXT NOT NULL DEFAULT '[]'",
]

_CREATE_SUBTASKS_TABLE = """
CREATE TABLE IF NOT EXISTS subtasks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    todo_id    INTEGER NOT NULL,
    title      TEXT    NOT NULL,
    completed  INTEGER NOT NULL DEFAULT 0,
    position   INTEGER NOT NULL DEFAULT 0,
    created_at TEXT    NOT NULL
)
"""

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
    # External calendar sync bookkeeping (ICS subscriptions + two-way Outlook sync)
    "ALTER TABLE events ADD COLUMN source TEXT NOT NULL DEFAULT 'local'",
    "ALTER TABLE events ADD COLUMN external_id TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE events ADD COLUMN external_source TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE events ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE events ADD COLUMN sync_dirty INTEGER NOT NULL DEFAULT 0",
]

_CREATE_CALENDAR_SOURCES_TABLE = """
CREATE TABLE IF NOT EXISTS calendar_sources (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT    NOT NULL,             -- 'ics_url' | 'outlook'
    label       TEXT    NOT NULL DEFAULT '',
    url         TEXT    NOT NULL DEFAULT '',  -- ics_url only
    color       TEXT    NOT NULL DEFAULT '#0078d4',
    two_way     INTEGER NOT NULL DEFAULT 0,   -- outlook only — push local changes back
    last_synced TEXT    NOT NULL DEFAULT '',
    enabled     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT    NOT NULL
)
"""

_CREATE_SYNC_DELETES_TABLE = """
CREATE TABLE IF NOT EXISTS calendar_sync_deletes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    external_source TEXT    NOT NULL,
    external_id     TEXT    NOT NULL,
    created_at      TEXT    NOT NULL
)
"""


_CREATE_TIMERS_TABLE = """
CREATE TABLE IF NOT EXISTS timers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL DEFAULT 'Untitled Timer',
    hourly_rate REAL    NOT NULL DEFAULT 0.0,
    color       TEXT    NOT NULL DEFAULT '#1a6fc4',
    created_at  TEXT    NOT NULL,
    archived    INTEGER NOT NULL DEFAULT 0,
    timer_type  TEXT    NOT NULL DEFAULT 'work',
    currency    TEXT    NOT NULL DEFAULT 'ILS'
)
"""

_TIMER_MIGRATIONS = [
    "ALTER TABLE timers ADD COLUMN timer_type TEXT NOT NULL DEFAULT 'work'",
    "ALTER TABLE timers ADD COLUMN currency TEXT NOT NULL DEFAULT 'ILS'",
]

_CREATE_TIMER_SESSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS timer_sessions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    timer_id   INTEGER NOT NULL,
    title      TEXT    NOT NULL DEFAULT '',
    start_time TEXT    NOT NULL,
    end_time   TEXT,
    notes      TEXT    NOT NULL DEFAULT '',
    created_at TEXT    NOT NULL
)
"""

_CREATE_COUNTERS_TABLE = """
CREATE TABLE IF NOT EXISTS counters (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT    NOT NULL DEFAULT 'Untitled Counter',
    price_per_unit  REAL    NOT NULL DEFAULT 0.0,
    currency        TEXT    NOT NULL DEFAULT 'ILS',
    color           TEXT    NOT NULL DEFAULT '#1a6fc4',
    created_at      TEXT    NOT NULL,
    archived        INTEGER NOT NULL DEFAULT 0
)
"""

# Each tap of +/- is logged as its own row (mirrors timer_sessions) so the
# running count is always derivable — never stored redundantly — and every
# tap keeps a timestamp (for the date / time-of-day bucket) plus an optional
# label describing what that tap was for.
_CREATE_COUNTER_PRESSES_TABLE = """
CREATE TABLE IF NOT EXISTS counter_presses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    counter_id  INTEGER NOT NULL,
    delta       INTEGER NOT NULL DEFAULT 1,
    label       TEXT    NOT NULL DEFAULT '',
    pressed_at  TEXT    NOT NULL,
    created_at  TEXT    NOT NULL
)
"""

# A "cash out" closes the counter's current tally cycle: it snapshots the
# net count for that cycle (so later press edits/deletes never retroactively
# rewrite payout history — mirrors how timer session totals aren't
# recomputed after the fact) and records when/how much was paid. Cycle
# boundaries are pure time boundaries against counter_presses.pressed_at —
# cycle_started_at is the previous payout's payout_at, or the counter's own
# created_at for the first-ever payout — so no migration of counter_presses
# is ever needed.
_CREATE_COUNTER_PAYOUTS_TABLE = """
CREATE TABLE IF NOT EXISTS counter_payouts (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    counter_id        INTEGER NOT NULL,
    cycle_started_at  TEXT    NOT NULL,
    payout_at         TEXT    NOT NULL,
    count             INTEGER NOT NULL,
    amount            REAL,
    currency          TEXT    NOT NULL,
    note              TEXT    NOT NULL DEFAULT '',
    created_at        TEXT    NOT NULL
)
"""

_CREATE_COURSES_TABLE = """
CREATE TABLE IF NOT EXISTS courses (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    number     TEXT    NOT NULL DEFAULT '',
    name       TEXT    NOT NULL,
    color      TEXT    NOT NULL DEFAULT '#1a6fc4',
    partners   TEXT    NOT NULL DEFAULT '[]',
    position   INTEGER NOT NULL DEFAULT 0,
    created_at TEXT    NOT NULL
)
"""

_CREATE_ASSIGNMENTS_TABLE = """
CREATE TABLE IF NOT EXISTS assignments (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id         INTEGER NOT NULL,
    title             TEXT    NOT NULL,
    due_date          TEXT    NOT NULL DEFAULT '',
    completed         INTEGER NOT NULL DEFAULT 0,
    calendar_event_id INTEGER,
    created_at        TEXT    NOT NULL
)
"""

# ---------------------------------------------------------------------------
# Workout (Phase 1: backend-only sync target for the existing local-only iOS
# Workout feature — see MACalendar-iOS/.../Workout/WorkoutModels.swift).
#
# Unlike events/todos (server-assigned autoincrement Int id + temp-id remap
# for offline creation), these tables use client-generated UUIDs (TEXT
# PRIMARY KEY) end-to-end, matching how the iOS structs already mint their
# own `id: UUID` at creation time. The server just stores whatever id the
# client sends — no remap dance needed, conflict-free by construction.
#
# Normalized child tables (no JSON blob columns), matching this codebase's
# existing convention (see todos/subtasks, timers/timer_sessions).
# ---------------------------------------------------------------------------

_CREATE_WORKOUT_EXERCISES_TABLE = """
CREATE TABLE IF NOT EXISTS workout_exercises (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""

_CREATE_WORKOUT_TEMPLATES_TABLE = """
CREATE TABLE IF NOT EXISTS workout_templates (
    id                              TEXT PRIMARY KEY,
    name                            TEXT    NOT NULL,
    default_rest_between_sets       INTEGER NOT NULL DEFAULT 90,
    default_rest_between_exercises  INTEGER NOT NULL DEFAULT 120,
    created_at                      TEXT    NOT NULL,
    status                          TEXT    NOT NULL DEFAULT 'saved'
    -- status: 'saved' | 'draft' — 'draft' = pending review after
    -- GenerateWorkoutRoutineAction auto-generation; excluded from normal
    -- template list queries unless explicitly requested.
)
"""

_CREATE_WORKOUT_TEMPLATE_BLOCKS_TABLE = """
CREATE TABLE IF NOT EXISTS workout_template_blocks (
    id                          TEXT PRIMARY KEY,
    template_id                 TEXT    NOT NULL,
    order_index                 INTEGER NOT NULL DEFAULT 0,
    kind                        TEXT    NOT NULL,   -- 'single' | 'superset'
    -- .single
    exercise_id                 TEXT,
    rest_between_sets_override  INTEGER,
    -- .superset
    exercise_id_a               TEXT,
    exercise_id_b               TEXT,
    rest_after_round            INTEGER
)
"""

_CREATE_WORKOUT_TEMPLATE_SETS_TABLE = """
CREATE TABLE IF NOT EXISTS workout_template_sets (
    id             TEXT PRIMARY KEY,
    block_id       TEXT    NOT NULL,
    side           TEXT    NOT NULL DEFAULT 'single',  -- 'single' | 'a' | 'b'
    set_index      INTEGER NOT NULL DEFAULT 0,
    type           TEXT    NOT NULL,                   -- 'reps' | 'time'
    target_reps    INTEGER,
    weight_kg      REAL,
    target_seconds INTEGER,
    note           TEXT    NOT NULL DEFAULT ''
)
"""

_CREATE_WORKOUT_SESSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS workout_sessions (
    id          TEXT PRIMARY KEY,
    template_id TEXT,             -- NULL = ad-hoc session
    started_at  TEXT NOT NULL,
    ended_at    TEXT,              -- NULL = in progress (should be finished before sync in practice)
    notes       TEXT NOT NULL DEFAULT ''
)
"""

_CREATE_WORKOUT_SET_LOGS_TABLE = """
CREATE TABLE IF NOT EXISTS workout_set_logs (
    id               TEXT PRIMARY KEY,
    session_id       TEXT    NOT NULL,
    exercise_id      TEXT    NOT NULL,
    set_index        INTEGER NOT NULL DEFAULT 0,
    type             TEXT    NOT NULL,     -- 'reps' | 'time'
    actual_reps      INTEGER,
    actual_seconds   INTEGER,
    actual_weight_kg REAL,
    completed_at     TEXT,
    skipped          INTEGER NOT NULL DEFAULT 0
)
"""

_CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_events_date      ON events(date);
CREATE INDEX IF NOT EXISTS idx_events_series    ON events(series_id);
CREATE INDEX IF NOT EXISTS idx_todos_list       ON todos(list, completed);
CREATE INDEX IF NOT EXISTS idx_subtasks_todo    ON subtasks(todo_id, position);
CREATE INDEX IF NOT EXISTS idx_timer_sessions   ON timer_sessions(timer_id);
CREATE INDEX IF NOT EXISTS idx_counter_presses  ON counter_presses(counter_id);
CREATE INDEX IF NOT EXISTS idx_counter_payouts  ON counter_payouts(counter_id);
CREATE INDEX IF NOT EXISTS idx_assignments_course ON assignments(course_id);
CREATE INDEX IF NOT EXISTS idx_events_external    ON events(external_source, external_id);
CREATE INDEX IF NOT EXISTS idx_workout_templates_status  ON workout_templates(status, created_at);
CREATE INDEX IF NOT EXISTS idx_workout_blocks_template   ON workout_template_blocks(template_id, order_index);
CREATE INDEX IF NOT EXISTS idx_workout_sets_block        ON workout_template_sets(block_id, set_index);
CREATE INDEX IF NOT EXISTS idx_workout_sessions_started  ON workout_sessions(started_at);
CREATE INDEX IF NOT EXISTS idx_workout_set_logs_session  ON workout_set_logs(session_id);
"""


def _utcnow_iso() -> str:
    """UTC timestamp for sync bookkeeping — comparable against Graph API timestamps."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _next_date(d: datetime.date, recurrence: str, anchor_day: int | None = None) -> datetime.date:
    """Advance d by one recurrence period.

    For monthly recurrence, `anchor_day` (the original series day-of-month, e.g.
    31 for a "31st of every month" series) is used instead of `d.day` so a
    short-month clamp doesn't permanently stick — Jan 31 -> Feb 28 -> Mar 31,
    not Mar 28. Without an anchor, falls back to `d.day` (chains from the
    previous instance), which is what causes the drift.
    """
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
        day = anchor_day if anchor_day is not None else d.day
        # Clamp day to the last valid day of the target month
        max_day = calendar.monthrange(year, month)[1]
        return datetime.date(year, month, min(day, max_day))
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
            conn.execute(_CREATE_SUBTASKS_TABLE)
            conn.execute(_CREATE_TIMERS_TABLE)
            self._migrate_timers(conn)
            conn.execute(_CREATE_TIMER_SESSIONS_TABLE)
            conn.execute(_CREATE_COUNTERS_TABLE)
            conn.execute(_CREATE_COUNTER_PRESSES_TABLE)
            conn.execute(_CREATE_COUNTER_PAYOUTS_TABLE)
            conn.execute(_CREATE_COURSES_TABLE)
            conn.execute(_CREATE_ASSIGNMENTS_TABLE)
            conn.execute(_CREATE_CALENDAR_SOURCES_TABLE)
            conn.execute(_CREATE_SYNC_DELETES_TABLE)
            conn.execute(_CREATE_WORKOUT_EXERCISES_TABLE)
            conn.execute(_CREATE_WORKOUT_TEMPLATES_TABLE)
            conn.execute(_CREATE_WORKOUT_TEMPLATE_BLOCKS_TABLE)
            conn.execute(_CREATE_WORKOUT_TEMPLATE_SETS_TABLE)
            conn.execute(_CREATE_WORKOUT_SESSIONS_TABLE)
            conn.execute(_CREATE_WORKOUT_SET_LOGS_TABLE)
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

    def _migrate_timers(self, conn: sqlite3.Connection) -> None:
        """Apply any missing timers schema migrations safely."""
        existing = {r[1] for r in conn.execute("PRAGMA table_info(timers)")}
        for stmt in _TIMER_MIGRATIONS:
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
        anchor_day = current.day  # original day-of-month; see _next_date docstring
        count = 0
        max_instances = 500  # hard safety cap

        while count < max_instances:
            current = _next_date(current, recurrence, anchor_day=anchor_day)
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

    def _is_externally_locked(self, conn: sqlite3.Connection, event_id: int) -> bool:
        """True if *event_id* must not be edited/deleted locally right now.

        ICS-subscribed events are always locked — there is no write path
        behind a webcal/ICS link. Outlook-sourced events are locked unless
        two-way sync is currently on: editing one while it's off would mark
        the row dirty with no push ever happening, silently and permanently
        diverging it from the real Outlook event (see `pull()`'s dirty-row
        preservation logic in calendar_sync/outlook_sync.py).
        """
        row = conn.execute("SELECT source FROM events WHERE id = ?", (event_id,)).fetchone()
        if not row:
            return False
        source = row["source"]
        if source == "ics":
            return True
        if source == "outlook":
            two_way = conn.execute(
                "SELECT two_way FROM calendar_sources WHERE kind = 'outlook' LIMIT 1"
            ).fetchone()
            return not (two_way and two_way["two_way"])
        return False

    def is_event_locked(self, event: dict) -> bool:
        """UI-facing check: can *event* (a dict, e.g. from get_event()) be
        edited/deleted right now? See `_is_externally_locked` for policy."""
        source = event.get("source")
        if source == "ics":
            return True
        if source == "outlook":
            with self._conn() as conn:
                row = conn.execute(
                    "SELECT two_way FROM calendar_sources WHERE kind = 'outlook' LIMIT 1"
                ).fetchone()
            return not (row and row["two_way"])
        return False

    def update_event(self, event_id: int, **fields) -> None:
        allowed = {"title", "date", "start_time", "end_time", "attendees",
                   "location", "description", "color", "recurrence", "recurrence_end"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [_utcnow_iso(), event_id]
        with self._conn() as conn:
            if self._is_externally_locked(conn, event_id):
                return
            # updated_at is stamped in UTC (comparable against Graph's
            # lastModifiedDateTime for last-write-wins conflict resolution).
            # sync_dirty is only ever set here for outlook-sourced rows — the
            # periodic sync worker clears it once the push succeeds. Reaching
            # here at all already implies two-way is on (see the lock check
            # above), so this is never dirtied for a row nothing will push.
            conn.execute(
                f"UPDATE events SET {set_clause}, updated_at = ?, "
                f"sync_dirty = CASE WHEN source = 'outlook' THEN 1 ELSE sync_dirty END "
                f"WHERE id = ?",
                values,
            )

    def promote_to_series(self, event_id: int) -> None:
        """Promote a standalone event that already has recurrence set into a full series.

        Called when the user adds recurrence to a previously non-recurring event via the
        edit dialog.  The event becomes the series root and all future instances are
        generated.  No-op if the event already belongs to a series or has no recurrence.
        """
        event = self.get_event(event_id)
        if not event or not event.get("recurrence") or event.get("series_id"):
            return

        recurrence = event["recurrence"]
        recur_until = event.get("recurrence_end", "")
        attendees_str = event.get("attendees", "")

        class _FakeIntent:
            title = event["title"]
            date = event["date"]
            start_time = event["start_time"]
            end_time = event["end_time"]
            attendees = [a for a in attendees_str.split(", ") if a]
            location = event.get("location", "")
            description = event.get("description", "")

        with self._conn() as conn:
            self._create_series_instances(
                conn, event_id, _FakeIntent(), recurrence, recur_until,
                event.get("color", "#0078d4"),
            )

    def update_series(self, series_id: int, start_from_instance_id: int, **fields) -> None:
        """
        Update this instance and all future instances in the series.
        Series-wide properties (title, times, recurrence, recurrence_end, etc.) are
        propagated to ALL instances (past and future) so that any instance always
        reflects the current series definition.  Future instances are then re-generated
        whenever the schedule changes.
        """
        instance = self.get_event(start_from_instance_id)
        if not instance:
            return

        recurrence = fields.get("recurrence", instance.get("recurrence", ""))
        recur_until = fields.get("recurrence_end", instance.get("recurrence_end", ""))

        # Fields that are series-wide and should be propagated to ALL instances
        # (including past ones) so every instance always reflects the current series state.
        # recurrence + recurrence_end are included so past instances show the right until date.
        common = {
            "title", "start_time", "end_time", "attendees",
            "location", "description", "color",
            "recurrence", "recurrence_end",
        }
        updates = {k: v for k, v in fields.items() if k in common}

        with self._conn() as conn:
            if updates:
                set_clause = ", ".join(f"{k} = ?" for k in updates)
                values = list(updates.values()) + [series_id, series_id]
                conn.execute(
                    f"UPDATE events SET {set_clause} WHERE series_id = ? OR id = ?",
                    values,
                )

            # Re-generate future instances whenever the series has any recurrence
            # (keeps things simple: title/time changes also re-sync future slots).
            old_recur = instance.get("recurrence", "")
            old_until = instance.get("recurrence_end", "")
            if recurrence != old_recur or recur_until != old_until or recurrence:
                # Delete all future instances after the edited one
                conn.execute(
                    "DELETE FROM events WHERE (series_id = ? OR id = ?) AND date > ?",
                    (series_id, series_id, instance["date"]),
                )

                # Re-generate from the edited instance's date forward
                if recurrence:
                    attendees_str = fields.get("attendees", instance.get("attendees", ""))
                    attendees_list = [a for a in attendees_str.split(", ") if a]

                    class _FakeIntent:
                        title = fields.get("title", instance["title"])
                        date = instance["date"]
                        start_time = fields.get("start_time", instance["start_time"])
                        end_time = fields.get("end_time", instance["end_time"])
                        attendees = attendees_list
                        location = fields.get("location", instance["location"])
                        description = fields.get("description", instance["description"])

                    self._create_series_instances(
                        conn, series_id, _FakeIntent(), recurrence, recur_until,
                        fields.get("color", instance["color"])
                    )

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_event(self, event_id: int) -> None:
        """Delete a single event instance.

        If the deleted instance is the series root (series_id == id), the series is
        re-rooted to the next chronological instance so remaining instances keep a
        valid series_id reference and can still be edited/extended as a group.
        """
        with self._conn() as conn:
            if self._is_externally_locked(conn, event_id):
                return

            # Reaching here means this isn't an ICS event and, if it's an
            # Outlook event, two-way sync is on — queue a tombstone so the
            # periodic sync worker deletes it on the Outlook side too. The
            # row (and its external_id) won't exist to retry from once the
            # DELETE below runs.
            synced = conn.execute(
                "SELECT external_source, external_id FROM events "
                "WHERE id = ? AND external_source = 'outlook' AND external_id != ''",
                (event_id,),
            ).fetchone()
            if synced:
                conn.execute(
                    "INSERT INTO calendar_sync_deletes (external_source, external_id, created_at) "
                    "VALUES (?, ?, ?)",
                    (synced["external_source"], synced["external_id"], _utcnow_iso()),
                )

            # Check whether this event is the series root
            row = conn.execute(
                "SELECT id FROM events WHERE id = ? AND series_id = id",
                (event_id,),
            ).fetchone()
            if row:
                # Find the earliest remaining instance to become the new root
                next_row = conn.execute(
                    "SELECT id FROM events WHERE series_id = ? AND id != ? ORDER BY date, start_time LIMIT 1",
                    (event_id, event_id),
                ).fetchone()
                if next_row:
                    new_root = next_row["id"]
                    # Point all sibling instances at the new root
                    conn.execute(
                        "UPDATE events SET series_id = ? WHERE series_id = ?",
                        (new_root, event_id),
                    )
                    # Make the new root self-referential
                    conn.execute(
                        "UPDATE events SET series_id = ? WHERE id = ?",
                        (new_root, new_root),
                    )

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
        """Delete this event and all future instances in the series.

        If the root instance falls within the deleted range, re-roots the series
        to the latest remaining instance so past instances stay properly linked.
        """
        with self._conn() as conn:
            # Check if the root is being deleted
            root_row = conn.execute(
                "SELECT id FROM events WHERE id = ? AND id = series_id AND date >= ?",
                (series_id, from_date),
            ).fetchone()
            if root_row:
                # Find the latest past instance to become new root
                prev_row = conn.execute(
                    "SELECT id FROM events WHERE (series_id = ? OR id = ?) AND date < ? "
                    "ORDER BY date DESC, start_time DESC LIMIT 1",
                    (series_id, series_id, from_date),
                ).fetchone()
                if prev_row:
                    new_root = prev_row["id"]
                    conn.execute(
                        "UPDATE events SET series_id = ? WHERE series_id = ? AND date < ?",
                        (new_root, series_id, from_date),
                    )
                    conn.execute(
                        "UPDATE events SET series_id = ? WHERE id = ?",
                        (new_root, new_root),
                    )

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
            max_pos = conn.execute(
                "SELECT COALESCE(MAX(position), -1) FROM todos WHERE list = ?",
                (list_name,),
            ).fetchone()[0]
            cur = conn.execute(
                """
                INSERT INTO todos
                    (title, list, completed, priority, due_date, notes,
                     source, source_event_id, created_at, completed_at, position)
                VALUES (?, ?, 0, ?, ?, ?, ?, ?, ?, '', ?)
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
                    max_pos + 1,
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
        query += " ORDER BY completed ASC, position ASC, created_at ASC"
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
        allowed = {"title", "list", "completed", "priority", "due_date", "notes", "completed_at", "attachments"}
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

    def delete_completed_todos(self, list_name: Optional[str] = None) -> int:
        """Delete all completed todos, optionally filtered by list. Returns count deleted."""
        with self._conn() as conn:
            if list_name:
                cur = conn.execute(
                    "DELETE FROM todos WHERE completed = 1 AND list = ?", (list_name,)
                )
            else:
                cur = conn.execute("DELETE FROM todos WHERE completed = 1")
            return cur.rowcount

    def reorder_todos(self, list_name: str, ids: List[int]) -> None:
        """Update position of todos in list_name to match the given id order."""
        with self._conn() as conn:
            for pos, todo_id in enumerate(ids):
                conn.execute(
                    "UPDATE todos SET position = ? WHERE id = ? AND list = ?",
                    (pos, todo_id, list_name),
                )

    # ------------------------------------------------------------------
    # Subtasks: CRUD
    # ------------------------------------------------------------------

    def get_subtasks(self, todo_id: int) -> List[dict]:
        """Return all subtasks for a todo, ordered by position then created_at."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM subtasks WHERE todo_id = ? ORDER BY position ASC, created_at ASC",
                (todo_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def create_subtask(self, todo_id: int, title: str) -> int:
        """Insert a new subtask. Returns the new row id."""
        with self._conn() as conn:
            max_pos = conn.execute(
                "SELECT COALESCE(MAX(position), -1) FROM subtasks WHERE todo_id = ?",
                (todo_id,),
            ).fetchone()[0]
            cur = conn.execute(
                "INSERT INTO subtasks (todo_id, title, completed, position, created_at) VALUES (?, ?, 0, ?, ?)",
                (todo_id, title, max_pos + 1, datetime.datetime.now().isoformat()),
            )
            return cur.lastrowid

    def update_subtask(self, subtask_id: int, **fields) -> None:
        allowed = {"title", "completed", "position"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [subtask_id]
        with self._conn() as conn:
            conn.execute(f"UPDATE subtasks SET {set_clause} WHERE id = ?", values)

    def delete_subtask(self, subtask_id: int) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM subtasks WHERE id = ?", (subtask_id,))

    def delete_subtasks_for_todo(self, todo_id: int) -> None:
        """Delete all subtasks belonging to a todo. Call before delete_todo()."""
        with self._conn() as conn:
            conn.execute("DELETE FROM subtasks WHERE todo_id = ?", (todo_id,))

    def reorder_subtasks(self, todo_id: int, ids: List[int]) -> None:
        """Update position of subtasks to match the given id order."""
        with self._conn() as conn:
            for pos, subtask_id in enumerate(ids):
                conn.execute(
                    "UPDATE subtasks SET position = ? WHERE id = ? AND todo_id = ?",
                    (pos, subtask_id, todo_id),
                )

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

    # ------------------------------------------------------------------
    # Timers
    # ------------------------------------------------------------------

    def create_timer(
        self,
        title: str = "Untitled Timer",
        hourly_rate: float = 0.0,
        color: str = "#1a6fc4",
        timer_type: str = "work",
        currency: str = "ILS",
    ) -> int:
        """Create a new timer project. Returns new row id."""
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO timers (title, hourly_rate, color, created_at, timer_type, currency) VALUES (?, ?, ?, ?, ?, ?)",
                (title, hourly_rate, color, datetime.datetime.now().isoformat(), timer_type, currency),
            )
            return cur.lastrowid

    def get_timers(self, include_archived: bool = False) -> List[dict]:
        """Return all timer projects as dicts, newest first."""
        with self._conn() as conn:
            where = "" if include_archived else "WHERE archived = 0"
            rows = conn.execute(
                f"SELECT * FROM timers {where} ORDER BY created_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    def update_timer(self, timer_id: int, **kwargs) -> None:
        """Update allowed fields on a timer."""
        allowed = {"title", "hourly_rate", "color", "archived", "timer_type", "currency"}
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return
        sets = ", ".join(f"{k} = ?" for k in fields)
        with self._conn() as conn:
            conn.execute(
                f"UPDATE timers SET {sets} WHERE id = ?",
                (*fields.values(), timer_id),
            )

    def delete_timer(self, timer_id: int) -> None:
        """Delete a timer and all its sessions."""
        with self._conn() as conn:
            conn.execute("DELETE FROM timer_sessions WHERE timer_id = ?", (timer_id,))
            conn.execute("DELETE FROM timers WHERE id = ?", (timer_id,))

    # ------------------------------------------------------------------
    # Timer Sessions
    # ------------------------------------------------------------------

    def create_timer_session(self, timer_id: int, title: str = "", start_time: Optional[str] = None) -> int:
        """Start a new session for a timer. Returns new row id."""
        now = datetime.datetime.now().astimezone().isoformat()
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO timer_sessions (timer_id, title, start_time, end_time, notes, created_at) VALUES (?, ?, ?, NULL, '', ?)",
                (timer_id, title, start_time or now, now),
            )
            return cur.lastrowid

    def get_timer_sessions(self, timer_id: int) -> List[dict]:
        """Return all sessions for a timer, oldest first."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM timer_sessions WHERE timer_id = ? ORDER BY start_time ASC",
                (timer_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_running_session(self, timer_id: int) -> Optional[dict]:
        """Return the currently running (open) session for a timer, or None."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM timer_sessions WHERE timer_id = ? AND end_time IS NULL LIMIT 1",
                (timer_id,),
            ).fetchone()
            return dict(row) if row else None

    def update_timer_session(self, session_id: int, **kwargs) -> None:
        """Update allowed fields on a timer session."""
        allowed = {"title", "start_time", "end_time", "notes"}
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return
        sets = ", ".join(f"{k} = ?" for k in fields)
        with self._conn() as conn:
            conn.execute(
                f"UPDATE timer_sessions SET {sets} WHERE id = ?",
                (*fields.values(), session_id),
            )

    def stop_timer_session(self, session_id: int, end_time: Optional[str] = None) -> None:
        """Close an open session by setting end_time."""
        with self._conn() as conn:
            conn.execute(
                "UPDATE timer_sessions SET end_time = ? WHERE id = ?",
                (end_time or datetime.datetime.now().astimezone().isoformat(), session_id),
            )

    def delete_timer_session(self, session_id: int) -> None:
        """Delete a single timer session."""
        with self._conn() as conn:
            conn.execute("DELETE FROM timer_sessions WHERE id = ?", (session_id,))

    def split_timer_session(self, session_id: int, split_at: Optional[str] = None) -> int:
        """
        Split a session at split_at (ISO datetime string) or its midpoint.
        Closes the original session at split_at and creates a new one.
        Returns the id of the new session.
        """
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM timer_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if not row:
                raise ValueError(f"Session {session_id} not found")
            session = dict(row)

        start = datetime.datetime.fromisoformat(session["start_time"])
        if start.tzinfo is None:
            start = start.astimezone()
        end_raw = session.get("end_time")
        end = datetime.datetime.fromisoformat(end_raw) if end_raw else datetime.datetime.now()
        if end.tzinfo is None:
            end = end.astimezone()

        if split_at:
            mid = datetime.datetime.fromisoformat(split_at)
        else:
            mid = start + (end - start) / 2

        self.update_timer_session(session_id, end_time=mid.isoformat())
        return self.create_timer_session(
            session["timer_id"],
            title=session["title"],
            start_time=mid.isoformat(),
        )

    # ------------------------------------------------------------------
    # Counters
    # ------------------------------------------------------------------

    def create_counter(
        self,
        title: str = "Untitled Counter",
        price_per_unit: float = 0.0,
        currency: str = "ILS",
        color: str = "#1a6fc4",
    ) -> int:
        """Create a new tally counter. Returns new row id."""
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO counters (title, price_per_unit, currency, color, created_at) VALUES (?, ?, ?, ?, ?)",
                (title, price_per_unit, currency, color, datetime.datetime.now().isoformat()),
            )
            return cur.lastrowid

    def get_counters(self, include_archived: bool = False) -> List[dict]:
        """Return all counters as dicts, newest first."""
        with self._conn() as conn:
            where = "" if include_archived else "WHERE archived = 0"
            rows = conn.execute(
                f"SELECT * FROM counters {where} ORDER BY created_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    def update_counter(self, counter_id: int, **kwargs) -> None:
        """Update allowed fields on a counter."""
        allowed = {"title", "price_per_unit", "currency", "color", "archived"}
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return
        sets = ", ".join(f"{k} = ?" for k in fields)
        with self._conn() as conn:
            conn.execute(
                f"UPDATE counters SET {sets} WHERE id = ?",
                (*fields.values(), counter_id),
            )

    def delete_counter(self, counter_id: int) -> None:
        """Delete a counter and all its presses and payout history."""
        with self._conn() as conn:
            conn.execute("DELETE FROM counter_presses WHERE counter_id = ?", (counter_id,))
            conn.execute("DELETE FROM counter_payouts WHERE counter_id = ?", (counter_id,))
            conn.execute("DELETE FROM counters WHERE id = ?", (counter_id,))

    # ------------------------------------------------------------------
    # Counter Presses
    # ------------------------------------------------------------------

    def create_counter_press(
        self,
        counter_id: int,
        delta: int = 1,
        label: str = "",
        pressed_at: Optional[str] = None,
    ) -> int:
        """Log a single +/- tap on a counter. Returns new row id."""
        now = datetime.datetime.now().astimezone().isoformat()
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO counter_presses (counter_id, delta, label, pressed_at, created_at) VALUES (?, ?, ?, ?, ?)",
                (counter_id, delta, label, pressed_at or now, now),
            )
            return cur.lastrowid

    def get_counter_presses(self, counter_id: int) -> List[dict]:
        """Return all presses for a counter, oldest first."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM counter_presses WHERE counter_id = ? ORDER BY pressed_at ASC",
                (counter_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def update_counter_press(self, press_id: int, **kwargs) -> None:
        """Update allowed fields on a counter press."""
        allowed = {"delta", "label", "pressed_at"}
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return
        sets = ", ".join(f"{k} = ?" for k in fields)
        with self._conn() as conn:
            conn.execute(
                f"UPDATE counter_presses SET {sets} WHERE id = ?",
                (*fields.values(), press_id),
            )

    def delete_counter_press(self, press_id: int) -> None:
        """Delete a single counter press."""
        with self._conn() as conn:
            conn.execute("DELETE FROM counter_presses WHERE id = ?", (press_id,))

    # ------------------------------------------------------------------
    # Counter Payouts ("cash out" a counter's current tally cycle)
    # ------------------------------------------------------------------

    def create_counter_payout(
        self,
        counter_id: int,
        cycle_started_at: str,
        payout_at: str,
        count: int,
        amount: Optional[float],
        currency: str,
        note: str = "",
    ) -> int:
        """Log a payout that closes out a counter's current tally cycle.

        `count` is a snapshot of the net delta-sum for that cycle at the
        moment of payout — it is never recomputed later, so subsequent edits
        or deletions of presses don't retroactively rewrite payout history.
        Returns the new row id.
        """
        now = datetime.datetime.now().astimezone().isoformat()
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO counter_payouts "
                "(counter_id, cycle_started_at, payout_at, count, amount, currency, note, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (counter_id, cycle_started_at, payout_at, count, amount, currency, note, now),
            )
            return cur.lastrowid

    def get_counter_payouts(self, counter_id: int) -> List[dict]:
        """Return all payouts for a counter, newest first."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM counter_payouts WHERE counter_id = ? ORDER BY payout_at DESC",
                (counter_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def update_counter_payout(self, payout_id: int, **kwargs) -> None:
        """Update allowed fields on a counter payout.

        `count` and `cycle_started_at` are immutable snapshots and are not
        in the allowed set — only the human-editable fields (when it was
        paid, how much, and any note) can change after the fact.
        """
        allowed = {"payout_at", "amount", "note"}
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return
        sets = ", ".join(f"{k} = ?" for k in fields)
        with self._conn() as conn:
            conn.execute(
                f"UPDATE counter_payouts SET {sets} WHERE id = ?",
                (*fields.values(), payout_id),
            )

    def delete_counter_payout(self, payout_id: int) -> None:
        """Delete a single payout record. Does not touch the underlying press log."""
        with self._conn() as conn:
            conn.execute("DELETE FROM counter_payouts WHERE id = ?", (payout_id,))

    def get_counter_cycle_start(self, counter_id: int) -> Optional[str]:
        """Return the start of the counter's current (open) tally cycle.

        This is the most recent payout's `payout_at` for that counter, or
        None if it has never been cashed out — in which case the current
        cycle spans the counter's entire press history.
        """
        with self._conn() as conn:
            row = conn.execute(
                "SELECT payout_at FROM counter_payouts WHERE counter_id = ? "
                "ORDER BY payout_at DESC LIMIT 1",
                (counter_id,),
            ).fetchone()
            return row["payout_at"] if row else None

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

    # ------------------------------------------------------------------
    # Courses
    # ------------------------------------------------------------------

    def get_courses(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, number, name, color, partners, position FROM courses ORDER BY position, id"
            ).fetchall()
        return [
            {
                "id": r[0], "number": r[1], "name": r[2], "color": r[3],
                "partners": json.loads(r[4]) if r[4] else [],
                "position": r[5],
            }
            for r in rows
        ]

    def create_course(self, number: str, name: str, color: str, partners: list) -> int:
        now = datetime.datetime.now().isoformat()
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO courses (number, name, color, partners, created_at) VALUES (?,?,?,?,?)",
                (number, name, color, json.dumps(partners, ensure_ascii=False), now),
            )
            return cur.lastrowid

    def update_course(self, course_id: int, **fields) -> None:
        allowed = {"number", "name", "color", "partners", "position"}
        updates = {}
        for k, v in fields.items():
            if k not in allowed:
                continue
            updates[k] = json.dumps(v, ensure_ascii=False) if k == "partners" else v
        if not updates:
            return
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        with self._conn() as conn:
            conn.execute(
                f"UPDATE courses SET {set_clause} WHERE id = ?",
                (*updates.values(), course_id),
            )

    def delete_course(self, course_id: int) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM assignments WHERE course_id = ?", (course_id,))
            conn.execute("DELETE FROM courses WHERE id = ?", (course_id,))

    # ------------------------------------------------------------------
    # Assignments
    # ------------------------------------------------------------------

    def get_assignments(self, course_id: int) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, course_id, title, due_date, completed, calendar_event_id "
                "FROM assignments WHERE course_id = ? ORDER BY completed, due_date, id",
                (course_id,),
            ).fetchall()
        return [
            {"id": r[0], "course_id": r[1], "title": r[2],
             "due_date": r[3], "completed": r[4], "calendar_event_id": r[5]}
            for r in rows
        ]

    def create_assignment(self, course_id: int, title: str, due_date: str = "") -> int:
        now = datetime.datetime.now().isoformat()
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO assignments (course_id, title, due_date, created_at) VALUES (?,?,?,?)",
                (course_id, title, due_date, now),
            )
            return cur.lastrowid

    def toggle_assignment(self, assignment_id: int) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT completed FROM assignments WHERE id = ?", (assignment_id,)
            ).fetchone()
            if row is None:
                return False
            new_val = 0 if row[0] else 1
            conn.execute("UPDATE assignments SET completed = ? WHERE id = ?", (new_val, assignment_id))
        return bool(new_val)

    def update_assignment(self, assignment_id: int, **fields) -> None:
        allowed = {"title", "due_date", "completed", "calendar_event_id"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        with self._conn() as conn:
            conn.execute(
                f"UPDATE assignments SET {set_clause} WHERE id = ?",
                (*updates.values(), assignment_id),
            )

    def delete_assignment(self, assignment_id: int) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM assignments WHERE id = ?", (assignment_id,))

    def delete_completed_assignments(self, course_id: Optional[int] = None) -> int:
        """Delete all completed assignments, optionally filtered by course. Returns count deleted."""
        with self._conn() as conn:
            if course_id is not None:
                cur = conn.execute(
                    "DELETE FROM assignments WHERE completed = 1 AND course_id = ?", (course_id,)
                )
            else:
                cur = conn.execute("DELETE FROM assignments WHERE completed = 1")
            return cur.rowcount

    def set_assignment_calendar_event(self, assignment_id: int, event_id: int) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE assignments SET calendar_event_id = ? WHERE id = ?",
                (event_id, assignment_id),
            )

    # ------------------------------------------------------------------
    # Workout: Exercises
    # ------------------------------------------------------------------

    def create_workout_exercise(self, id: str, name: str, created_at: Optional[str] = None) -> str:
        """Insert a new exercise with a client-generated UUID. Idempotent on id
        (INSERT OR IGNORE) so a retried offline-sync POST is safe to resend."""
        now = created_at or datetime.datetime.now().isoformat()
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO workout_exercises (id, name, created_at) VALUES (?, ?, ?)",
                (id, name, now),
            )
        return id

    def get_workout_exercises(self) -> List[dict]:
        """Return all exercises, alphabetical (used for search-or-create autocomplete)."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM workout_exercises ORDER BY name COLLATE NOCASE ASC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_workout_exercise(self, exercise_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM workout_exercises WHERE id = ?", (exercise_id,)
            ).fetchone()
        return dict(row) if row else None

    def find_workout_exercise_by_name(self, name: str) -> Optional[dict]:
        """Case-insensitive exact name match — used to reuse an existing exercise
        instead of creating a duplicate."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM workout_exercises WHERE name = ? COLLATE NOCASE LIMIT 1",
                (name,),
            ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Workout: Templates (+ nested blocks/sets)
    # ------------------------------------------------------------------

    def _insert_workout_template_blocks(self, conn: sqlite3.Connection, template_id: str, blocks: list) -> None:
        """Insert a template's blocks and their nested sets. Caller owns the transaction."""
        for idx, block in enumerate(blocks):
            conn.execute(
                """
                INSERT INTO workout_template_blocks
                    (id, template_id, order_index, kind, exercise_id, rest_between_sets_override,
                     exercise_id_a, exercise_id_b, rest_after_round)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    block["id"], template_id, idx, block["kind"],
                    block.get("exercise_id"), block.get("rest_between_sets_override"),
                    block.get("exercise_id_a"), block.get("exercise_id_b"),
                    block.get("rest_after_round"),
                ),
            )
            for side, sets_key in (("single", "sets"), ("a", "sets_a"), ("b", "sets_b")):
                for set_idx, s in enumerate(block.get(sets_key) or []):
                    conn.execute(
                        """
                        INSERT INTO workout_template_sets
                            (id, block_id, side, set_index, type, target_reps, weight_kg,
                             target_seconds, note)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            s["id"], block["id"], side, set_idx, s["type"],
                            s.get("target_reps"), s.get("weight_kg"), s.get("target_seconds"),
                            s.get("note") or "",
                        ),
                    )

    def _delete_workout_template_children(self, conn: sqlite3.Connection, template_id: str) -> None:
        block_ids = [
            r[0] for r in conn.execute(
                "SELECT id FROM workout_template_blocks WHERE template_id = ?", (template_id,)
            ).fetchall()
        ]
        for block_id in block_ids:
            conn.execute("DELETE FROM workout_template_sets WHERE block_id = ?", (block_id,))
        conn.execute("DELETE FROM workout_template_blocks WHERE template_id = ?", (template_id,))

    def _hydrate_workout_template(self, conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
        template = dict(row)
        block_rows = conn.execute(
            "SELECT * FROM workout_template_blocks WHERE template_id = ? ORDER BY order_index ASC",
            (template["id"],),
        ).fetchall()
        blocks = []
        for b in block_rows:
            b = dict(b)
            set_rows = conn.execute(
                "SELECT * FROM workout_template_sets WHERE block_id = ? ORDER BY set_index ASC",
                (b["id"],),
            ).fetchall()
            sets, sets_a, sets_b = [], [], []
            for s in set_rows:
                s = dict(s)
                side = s.pop("side")
                s.pop("block_id", None)
                s.pop("set_index", None)
                (sets_a if side == "a" else sets_b if side == "b" else sets).append(s)
            blocks.append({
                "id": b["id"],
                "kind": b["kind"],
                "exercise_id": b["exercise_id"],
                "sets": sets,
                "rest_between_sets_override": b["rest_between_sets_override"],
                "exercise_id_a": b["exercise_id_a"],
                "exercise_id_b": b["exercise_id_b"],
                "sets_a": sets_a,
                "sets_b": sets_b,
                "rest_after_round": b["rest_after_round"],
            })
        template["blocks"] = blocks
        return template

    def create_workout_template(self, template: dict) -> str:
        """Insert a full nested template (id, name, blocks[+sets], ...) transactionally.
        `template["id"]` is the client-generated UUID."""
        template_id = template["id"]
        now = template.get("created_at") or datetime.datetime.now().isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO workout_templates
                    (id, name, default_rest_between_sets, default_rest_between_exercises,
                     created_at, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    template_id, template["name"],
                    template.get("default_rest_between_sets", 90),
                    template.get("default_rest_between_exercises", 120),
                    now, template.get("status", "saved"),
                ),
            )
            self._insert_workout_template_blocks(conn, template_id, template.get("blocks") or [])
        return template_id

    def get_workout_templates(self, include_drafts: bool = False) -> List[dict]:
        """Return templates newest-first. Drafts (status='draft', pending review after
        AI generation) are excluded unless include_drafts=True."""
        where = "" if include_drafts else "WHERE status != 'draft'"
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM workout_templates {where} ORDER BY created_at DESC"
            ).fetchall()
            return [self._hydrate_workout_template(conn, r) for r in rows]

    def get_workout_template(self, template_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM workout_templates WHERE id = ?", (template_id,)
            ).fetchone()
            if row is None:
                return None
            return self._hydrate_workout_template(conn, row)

    def replace_workout_template(self, template_id: str, template: dict) -> None:
        """Replace-whole-template semantics: update scalar fields, delete+recreate
        all blocks/sets. Simpler than diffing a nested structure and matches how
        the client always has the full current template in memory anyway."""
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE workout_templates
                SET name = ?, default_rest_between_sets = ?, default_rest_between_exercises = ?,
                    status = ?
                WHERE id = ?
                """,
                (
                    template.get("name"),
                    template.get("default_rest_between_sets", 90),
                    template.get("default_rest_between_exercises", 120),
                    template.get("status", "saved"),
                    template_id,
                ),
            )
            self._delete_workout_template_children(conn, template_id)
            self._insert_workout_template_blocks(conn, template_id, template.get("blocks") or [])

    def delete_workout_template(self, template_id: str) -> None:
        with self._conn() as conn:
            self._delete_workout_template_children(conn, template_id)
            conn.execute("DELETE FROM workout_templates WHERE id = ?", (template_id,))

    def approve_workout_template(self, template_id: str) -> None:
        """Flip a draft (from AI generation) to 'saved' — the client called /approve
        after the user reviewed it. No-op if already saved or not found."""
        with self._conn() as conn:
            conn.execute(
                "UPDATE workout_templates SET status = 'saved' WHERE id = ?", (template_id,)
            )

    # ------------------------------------------------------------------
    # Workout: Sessions (+ nested set logs)
    # ------------------------------------------------------------------

    def _insert_workout_set_logs(self, conn: sqlite3.Connection, session_id: str, set_logs: list) -> None:
        for log in set_logs:
            conn.execute(
                """
                INSERT INTO workout_set_logs
                    (id, session_id, exercise_id, set_index, type, actual_reps, actual_seconds,
                     actual_weight_kg, completed_at, skipped)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log["id"], session_id, log["exercise_id"], log.get("set_index", 0),
                    log["type"], log.get("actual_reps"), log.get("actual_seconds"),
                    log.get("actual_weight_kg"), log.get("completed_at"),
                    int(bool(log.get("skipped", False))),
                ),
            )

    def _hydrate_workout_session(self, conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
        session = dict(row)
        log_rows = conn.execute(
            "SELECT * FROM workout_set_logs WHERE session_id = ? ORDER BY rowid ASC",
            (session["id"],),
        ).fetchall()
        set_logs = []
        for r in log_rows:
            log = dict(r)
            log.pop("session_id", None)
            log["skipped"] = bool(log["skipped"])
            set_logs.append(log)
        session["set_logs"] = set_logs
        return session

    def create_workout_session(self, session: dict) -> str:
        """Insert a full nested session (id, startedAt, ..., setLogs[]) transactionally.
        Sessions are normally posted once already-finished on the client."""
        session_id = session["id"]
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO workout_sessions (id, template_id, started_at, ended_at, notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    session_id, session.get("template_id"), session["started_at"],
                    session.get("ended_at"), session.get("notes") or "",
                ),
            )
            self._insert_workout_set_logs(conn, session_id, session.get("set_logs") or [])
        return session_id

    def get_workout_sessions(
        self,
        limit: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[dict]:
        """Return sessions most-recent-first, optionally filtered by started_at range
        and/or capped with limit."""
        query = "SELECT * FROM workout_sessions"
        conditions: List[str] = []
        params: List = []
        if start_date:
            conditions.append("started_at >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("started_at <= ?")
            params.append(end_date)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY started_at DESC"
        if limit:
            query += " LIMIT ?"
            params.append(int(limit))
        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._hydrate_workout_session(conn, r) for r in rows]

    def get_workout_session(self, session_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM workout_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if row is None:
                return None
            return self._hydrate_workout_session(conn, row)

    def update_workout_session(self, session_id: str, **fields) -> None:
        """Patch allowed scalar fields; if 'set_logs' is present, delete+recreate
        the child rows (post-hoc edits to logged sets)."""
        allowed = {"template_id", "started_at", "ended_at", "notes"}
        set_logs = fields.pop("set_logs", None)
        updates = {k: v for k, v in fields.items() if k in allowed}
        with self._conn() as conn:
            if updates:
                set_clause = ", ".join(f"{k} = ?" for k in updates)
                conn.execute(
                    f"UPDATE workout_sessions SET {set_clause} WHERE id = ?",
                    (*updates.values(), session_id),
                )
            if set_logs is not None:
                conn.execute("DELETE FROM workout_set_logs WHERE session_id = ?", (session_id,))
                self._insert_workout_set_logs(conn, session_id, set_logs)

    def delete_workout_session(self, session_id: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM workout_set_logs WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM workout_sessions WHERE id = ?", (session_id,))

    # ------------------------------------------------------------------
    # Connected calendars (ICS subscriptions + Outlook two-way sync)
    # ------------------------------------------------------------------

    def get_calendar_sources(self) -> List[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM calendar_sources ORDER BY created_at"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_calendar_source(self, source_id: int) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM calendar_sources WHERE id = ?", (source_id,)
            ).fetchone()
        return dict(row) if row else None

    def get_calendar_source_by_kind(self, kind: str) -> Optional[dict]:
        """There's only ever one 'outlook' source (a single account) —
        this avoids callers fetching the whole table just to find it."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM calendar_sources WHERE kind = ? LIMIT 1", (kind,)
            ).fetchone()
        return dict(row) if row else None

    def create_calendar_source(
        self, kind: str, label: str = "", url: str = "",
        color: str = "#0078d4", two_way: bool = False,
    ) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO calendar_sources "
                "(kind, label, url, color, two_way, last_synced, enabled, created_at) "
                "VALUES (?, ?, ?, ?, ?, '', 1, ?)",
                (kind, label, url, color, int(two_way), _utcnow_iso()),
            )
            return cur.lastrowid

    def update_calendar_source(self, source_id: int, **fields) -> None:
        allowed = {"label", "url", "color", "two_way", "last_synced", "enabled"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        with self._conn() as conn:
            conn.execute(
                f"UPDATE calendar_sources SET {set_clause} WHERE id = ?",
                (*updates.values(), source_id),
            )

    def delete_calendar_source(self, source_id: int) -> None:
        """Remove a connected source and any local events it produced.

        Outlook events (external_source='outlook') are left in place — that
        connection is a single shared account, not a deletable per-source
        feed, and disconnecting Outlook is handled separately (it just stops
        the sync worker from touching those rows again).
        """
        with self._conn() as conn:
            source = conn.execute(
                "SELECT kind, id FROM calendar_sources WHERE id = ?", (source_id,)
            ).fetchone()
            if source and source["kind"] == "ics_url":
                conn.execute(
                    "DELETE FROM events WHERE external_source = ?",
                    (f"ics:{source_id}",),
                )
            conn.execute("DELETE FROM calendar_sources WHERE id = ?", (source_id,))

    def get_events_by_external_source(self, external_source: str) -> List[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE external_source = ?", (external_source,)
            ).fetchall()
        return [dict(r) for r in rows]

    def upsert_external_event(self, external_source: str, external_id: str, data: dict) -> int:
        """Insert or update a read-only/synced event keyed by (external_source, external_id).

        Used by both ICS subscription refresh and Outlook pull. Returns the
        local row id. UPDATE and INSERT share the same field dict so a
        column added to one path can't silently be forgotten on the other
        (this previously happened to `attendees`, which was only ever set on
        first insert and never refreshed on subsequent syncs).
        """
        fields = {
            "title": data["title"],
            "date": data["date"],
            "start_time": data["start_time"],
            "end_time": data["end_time"],
            "attendees": data.get("attendees", ""),
            "location": data.get("location", ""),
            "description": data.get("description", ""),
            "color": data.get("color", "#0078d4"),
        }
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id FROM events WHERE external_source = ? AND external_id = ?",
                (external_source, external_id),
            ).fetchone()
            if row:
                event_id = row["id"]
                set_clause = ", ".join(f"{k} = ?" for k in fields)
                conn.execute(
                    f"UPDATE events SET {set_clause}, updated_at = ? WHERE id = ?",
                    (*fields.values(), _utcnow_iso(), event_id),
                )
                return event_id

            columns = list(fields) + [
                "created_at", "updated_at", "source", "external_id", "external_source"
            ]
            placeholders = ", ".join("?" for _ in columns)
            cur = conn.execute(
                f"INSERT INTO events ({', '.join(columns)}) VALUES ({placeholders})",
                (
                    *fields.values(),
                    _utcnow_iso(), _utcnow_iso(),
                    "outlook" if external_source == "outlook" else "ics",
                    external_id, external_source,
                ),
            )
            return cur.lastrowid

    def delete_events_not_in(self, external_source: str, keep_external_ids: List[str]) -> int:
        """Remove previously-synced events whose external_id no longer appears upstream.

        Only ever touches rows already tagged with *external_source* — never
        local/manual events. Returns the number removed.
        """
        with self._conn() as conn:
            if keep_external_ids:
                placeholders = ", ".join("?" for _ in keep_external_ids)
                cur = conn.execute(
                    f"DELETE FROM events WHERE external_source = ? "
                    f"AND external_id NOT IN ({placeholders})",
                    (external_source, *keep_external_ids),
                )
            else:
                cur = conn.execute(
                    "DELETE FROM events WHERE external_source = ?", (external_source,)
                )
            return cur.rowcount

    def get_dirty_outlook_events(self) -> List[dict]:
        """Non-recurring local events pending push to Outlook (created or edited)."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE source = 'outlook' "
                "AND sync_dirty = 1 AND series_id IS NULL"
            ).fetchall()
        return [dict(r) for r in rows]

    def clear_sync_dirty(self, event_id: int) -> None:
        with self._conn() as conn:
            conn.execute("UPDATE events SET sync_dirty = 0 WHERE id = ?", (event_id,))

    def set_event_external_id(self, event_id: int, external_source: str, external_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE events SET source = ?, external_source = ?, external_id = ?, "
                "sync_dirty = 0 WHERE id = ?",
                ("outlook" if external_source == "outlook" else "ics",
                 external_source, external_id, event_id),
            )

    def pop_sync_deletes(self) -> List[dict]:
        """Return and clear all queued tombstones for the sync worker to push."""
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM calendar_sync_deletes").fetchall()
            conn.execute("DELETE FROM calendar_sync_deletes")
        return [dict(r) for r in rows]

    def requeue_sync_delete(self, external_source: str, external_id: str) -> None:
        """Re-enqueue a tombstone whose push attempt failed, for the next sync cycle."""
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO calendar_sync_deletes (external_source, external_id, created_at) "
                "VALUES (?, ?, ?)",
                (external_source, external_id, _utcnow_iso()),
            )


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
