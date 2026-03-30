"""ICS file importer and macOS Calendar scanner.

Public API
----------
parse_ics(path) -> list[dict]
    Parse a .ics / .ical file; return a list of event dicts matching the
    schema used by CalendarDB.create_event_from_dict().

scan_macos_calendar() -> list[dict]
    Read events directly from the macOS Calendar SQLite store
    (~/.local/share/... or ~/Library/Calendars). Returns the same dict
    schema.  Falls back to an empty list if the DB cannot be opened.

import_events(db, events) -> tuple[int, int]
    Bulk-insert a list of event dicts into *db*, skipping duplicates
    (same title + date + start_time).  Returns (inserted, skipped).
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from typing import Generator, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MACOS_CALENDAR_DB = os.path.expanduser(
    "~/Library/Calendars/Calendar Cache"
)

# Fallback search root when the primary path doesn't exist
_FALLBACK_CALENDAR_ROOT = os.path.expanduser("~/Library/Calendars")


def _normalize_dt(
    value: str, tzid: Optional[str] = None
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Parse an iCal DATE or DATETIME value.

    Returns (date_str, start_time_str, end_time_str) where the last two
    may be None for all-day events.  We convert everything to local naive
    time using a simple UTC offset approach (no heavy pytz dependency).
    """
    value = value.strip()

    # All-day: YYYYMMDD
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})", value)
    if m:
        date_str = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        return date_str, None, None

    # Date-time: YYYYMMDDTHHMMSS[Z]
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})(Z?)", value)
    if m:
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hour, minute, second = int(m.group(4)), int(m.group(5)), int(m.group(6))
        utc = m.group(7) == "Z"
        dt = datetime.datetime(year, month, day, hour, minute, second)
        if utc:
            # Convert UTC → local naive
            ts = dt.replace(tzinfo=datetime.timezone.utc).timestamp()
            dt = datetime.datetime.fromtimestamp(ts)
        date_str = dt.strftime("%Y-%m-%d")
        time_str = dt.strftime("%H:%M")
        return date_str, time_str, None

    return None, None, None


# ---------------------------------------------------------------------------
# ICS parser  (no external deps — stdlib only)
# ---------------------------------------------------------------------------

def parse_ics(path: str) -> List[dict]:
    """Parse an ICS/iCal file and return a list of event dicts.

    Handles CRLF and LF line endings, folded lines (RFC 5545 §3.1), and
    the most common VEVENT properties.
    """
    with open(path, "rb") as fh:
        raw = fh.read()

    # Unfold RFC 5545 folded lines (CRLF / CR / LF + SPACE|TAB)
    text = raw.decode("utf-8", errors="replace")
    text = re.sub(r"\r\n[ \t]|\r[ \t]|\n[ \t]", "", text)
    lines = re.split(r"\r\n|\r|\n", text)

    events: List[dict] = []
    current: Optional[dict] = None

    for line in lines:
        if line.upper() == "BEGIN:VEVENT":
            current = {}
        elif line.upper() == "END:VEVENT":
            if current is not None:
                ev = _build_event_dict(current)
                if ev:
                    events.append(ev)
            current = None
        elif current is not None and ":" in line:
            # Split on first ":"
            key_part, _, wren = line.partition(":")
            # key_part may contain params: DTSTART;TZID=America/New_York
            key = key_part.split(";")[0].upper()
            params_raw = key_part[len(key):]  # everything after key name
            current[key] = (wren.strip(), params_raw)

    return events


def _build_event_dict(raw: dict) -> Optional[dict]:
    """Convert a raw VEVENT property map to a CalendarDB-compatible dict."""

    def get(key: str) -> Tuple[str, str]:
        return raw.get(key, ("", ""))

    title = get("SUMMARY")[0].replace("\\n", "\n").replace("\\,", ",")
    if not title:
        return None

    description = get("DESCRIPTION")[0].replace("\\n", "\n").replace("\\,", ",")
    location = get("LOCATION")[0].replace("\\,", ",")

    # DTSTART
    dtstart_val, dtstart_params = get("DTSTART")
    tzid = None
    m = re.search(r"TZID=([^;:]+)", dtstart_params)
    if m:
        tzid = m.group(1)

    date_str, start_time, _ = _normalize_dt(dtstart_val, tzid)
    if not date_str:
        return None  # Can't parse date — skip

    # DTEND
    dtend_val = get("DTEND")[0]
    _, end_time, _ = _normalize_dt(dtend_val, tzid)

    # All-day event: use 00:00 – 23:59
    if not start_time:
        start_time = "00:00"
    if not end_time:
        end_time = "23:59"

    return {
        "title": title,
        "date": date_str,
        "start_time": start_time,
        "end_time": end_time,
        "location": location,
        "description": description,
        "attendees": "",
        "color": "#0078d4",
    }


# ---------------------------------------------------------------------------
# macOS Calendar scanner
# ---------------------------------------------------------------------------

def scan_macos_calendar() -> List[dict]:
    """Read events from the macOS Calendar local SQLite database.

    macOS Calendar stores a *Calendar Cache* SQLite file under
    ~/Library/Calendars/.  The schema varies slightly across OS versions;
    we handle the two most common schemas:

      - macOS 12+ (Monterey/Ventura/Sonoma): CalendarStore table
      - Older layout: individual .ics blobs inside calendar package dirs

    Falls back to ICS scanning of ~/Library/Calendars/**/*.ics if the
    primary SQLite path is unavailable.
    """
    # ── Try the primary SQLite cache ──────────────────────────────────────
    db_path = _MACOS_CALENDAR_DB
    if os.path.isfile(db_path):
        events = _read_calendar_cache_db(db_path)
        if events is not None:
            return events

    # ── Fallback: walk ~/Library/Calendars for .ics files ─────────────────
    return _scan_ics_tree(_FALLBACK_CALENDAR_ROOT)


def _read_calendar_cache_db(path: str) -> Optional[List[dict]]:
    """Attempt to read CalendarItem rows from the macOS Calendar Cache DB."""
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
    except Exception:
        return None

    events: List[dict] = []
    try:
        # Try the modern schema (Monterey+). Table and column names vary;
        # we try a few known layouts.
        rows = None
        for attempt in (
            # macOS ≥ 13 layout
            """
            SELECT
                ci.summary      AS title,
                ci.startDate    AS start_epoch,
                ci.endDate      AS end_epoch,
                ci.location     AS location,
                ci.notes        AS description
            FROM CalendarItem ci
            WHERE ci.summary IS NOT NULL AND ci.summary != ''
            ORDER BY ci.startDate
            """,
            # Older layout (CalendarMD prefix)
            """
            SELECT
                summary         AS title,
                startDate       AS start_epoch,
                endDate         AS end_epoch,
                location        AS location,
                notes           AS description
            FROM Event
            WHERE summary IS NOT NULL AND summary != ''
            ORDER BY startDate
            """,
        ):
            try:
                rows = conn.execute(attempt).fetchall()
                break
            except sqlite3.OperationalError:
                continue

        if rows is None:
            return None

        ref = datetime.datetime(2001, 1, 1)  # Apple epoch
        for row in rows:
            try:
                title = str(row["title"]).strip()
                if not title:
                    continue
                start_dt = ref + datetime.timedelta(seconds=float(row["start_epoch"] or 0))
                end_dt = ref + datetime.timedelta(seconds=float(row["end_epoch"] or 0))
                events.append({
                    "title": title,
                    "date": start_dt.strftime("%Y-%m-%d"),
                    "start_time": start_dt.strftime("%H:%M"),
                    "end_time": end_dt.strftime("%H:%M"),
                    "location": str(row["location"] or ""),
                    "description": str(row["description"] or ""),
                    "attendees": "",
                    "color": "#0078d4",
                })
            except Exception:
                continue

    except Exception:
        return None
    finally:
        conn.close()

    return events


def _scan_ics_tree(root: str) -> List[dict]:
    """Recursively find and parse all .ics files under *root*."""
    events: List[dict] = []
    if not os.path.isdir(root):
        return events
    for dirpath, _dirs, files in os.walk(root):
        for fname in files:
            if fname.lower().endswith((".ics", ".ical")):
                try:
                    events.extend(parse_ics(os.path.join(dirpath, fname)))
                except Exception:
                    pass
    return events


# ---------------------------------------------------------------------------
# Bulk importer (deduplication)
# ---------------------------------------------------------------------------

def import_events(db, events: List[dict]) -> Tuple[int, int]:
    """Insert *events* into *db*, skipping duplicates.

    Duplicate detection: exact match on (title, date, start_time).

    Returns
    -------
    (inserted, skipped) counts.
    """
    # Build in-memory set of existing keys
    existing: set = set()
    try:
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(db.path)
        rows = conn.execute("SELECT title, date, start_time FROM events").fetchall()
        conn.close()
        existing = {(r[0], r[1], r[2]) for r in rows}
    except Exception:
        pass

    inserted = 0
    skipped = 0
    for ev in events:
        key = (ev.get("title", ""), ev.get("date", ""), ev.get("start_time", ""))
        if key in existing:
            skipped += 1
            continue
        try:
            db.create_event_from_dict(ev)
            existing.add(key)
            inserted += 1
        except Exception:
            skipped += 1

    return inserted, skipped
