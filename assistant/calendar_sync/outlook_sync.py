"""Two-way sync with Outlook/Office 365 via Microsoft Graph.

Pull: fetch events from Graph's `/me/calendarView` (which already expands
recurring events into individual occurrences — see GraphClient.list_events)
and upsert them locally, tagged `external_source='outlook'`.

Push: only events that *originated* from Outlook (i.e. already carry an
`external_id`) are ever pushed back — creating a plain local event never
silently leaks it to a real Outlook account. Edits to those events are
PATCHed when `sync_dirty`; deletes are drained from the tombstone queue that
`CalendarDB.delete_event()` populates.

Conflict policy: last-write-wins, resolved entirely during `pull()` by
comparing the local `updated_at` (stamped in UTC by `CalendarDB.update_event`)
against Graph's `lastModifiedDateTime` — if the local edit is newer, the
remote copy is not applied and the row is preserved dirty for the next push.
This is a personal, single-writer-per-side calendar; a full 3-way merge
would be over-engineering.

Scope (v1): only `series_id IS NULL` events are push-eligible. Local
recurrence patterns are not translated into Graph's recurrence model.
"""

from __future__ import annotations

import datetime
import logging
import re

from assistant.actions.calendar.auth import MSALAuth
from assistant.actions.calendar.graph_client import GraphClient
from assistant.actions.calendar.handler import get_local_timezone
from assistant.calendar_sync.ics_subscription import sync_all_ics_sources
from assistant.config import AppConfig
from assistant.db import CalendarDB, _utcnow_iso
from assistant.exceptions import AuthExpiredError, GraphAPIError

logger = logging.getLogger(__name__)

EXTERNAL_SOURCE = "outlook"
_PULL_WINDOW_PAST_DAYS = 30
_PULL_WINDOW_FUTURE_DAYS = 180


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HTML_BLOCK_BREAK_RE = re.compile(r"(?i)<(br|/p|/div|/li)\s*/?>")


def _html_to_text(html_content: str) -> str:
    """Best-effort HTML → plain text for Graph event bodies.

    Graph defaults `body.contentType` to "html" — dumping that verbatim into
    a plain QTextEdit/Text field renders raw markup. No HTML-parsing
    dependency is worth adding just for this, so this converts common block
    breaks to newlines, strips remaining tags, and unescapes entities.
    """
    import html as _html_module

    text = _HTML_BLOCK_BREAK_RE.sub("\n", html_content)
    text = _HTML_TAG_RE.sub("", text)
    return _html_module.unescape(text).strip()


def _graph_event_to_dict(ev: dict) -> dict:
    start = (ev.get("start") or {}).get("dateTime", "")
    end = (ev.get("end") or {}).get("dateTime", "")
    body = ev.get("body") or {}
    description = body.get("content", "")
    if body.get("contentType") == "html" and description:
        description = _html_to_text(description)

    if ev.get("isAllDay"):
        # Graph represents all-day events as midnight-to-midnight with an
        # *exclusive* end date (the day after the last day) — use the
        # 00:00-23:59 convention the ICS importer already uses for all-day
        # events, keyed off the start date only.
        date = start[:10] if len(start) >= 10 else ""
        start_time, end_time = "00:00", "23:59"
    else:
        date = start[:10] if len(start) >= 10 else ""
        start_time = start[11:16] if len(start) >= 16 else "00:00"
        end_time = end[11:16] if len(end) >= 16 else "23:59"

    return {
        "title": ev.get("subject") or "(No title)",
        "date": date,
        "start_time": start_time,
        "end_time": end_time,
        "location": (ev.get("location") or {}).get("displayName", ""),
        "description": description,
        "color": "#0078d4",
    }


def _local_event_to_payload(event: dict, timezone: str) -> dict:
    payload = {
        "subject": event["title"],
        "start": {"dateTime": f"{event['date']}T{event['start_time']}:00", "timeZone": timezone},
        "end": {"dateTime": f"{event['date']}T{event['end_time']}:00", "timeZone": timezone},
    }
    if event.get("location"):
        payload["location"] = {"displayName": event["location"]}
    if event.get("description"):
        payload["body"] = {"contentType": "text", "content": event["description"]}
    return payload


_ISO_TS_RE = re.compile(
    r"^(?P<base>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})"
    r"(?:\.(?P<frac>\d+))?"
    r"(?P<offset>Z|[+-]\d{2}:\d{2})?$"
)


def _parse_iso(ts: str) -> datetime.datetime | None:
    """Parse an ISO-8601 timestamp from either side of the sync (local
    `_utcnow_iso()` uses a "+00:00" offset with 6-digit microseconds; Graph's
    `lastModifiedDateTime` uses a "Z" suffix with up to 7 fractional digits).
    Comparing these as raw strings is not reliable — the differing suffix
    format can make a chronologically newer timestamp sort as "smaller" once
    the two happen to share the same whole-second prefix. Normalize both to
    real `datetime` objects (UTC if no offset given) before comparing.
    """
    if not ts:
        return None
    m = _ISO_TS_RE.match(ts)
    if not m:
        return None
    frac = (m.group("frac") or "").ljust(6, "0")[:6]  # pad/truncate to microseconds
    offset = m.group("offset") or "+00:00"
    if offset == "Z":
        offset = "+00:00"
    try:
        return datetime.datetime.fromisoformat(f"{m.group('base')}.{frac}{offset}")
    except ValueError:
        return None


def pull(db: CalendarDB, client: GraphClient) -> int:
    """Fetch Outlook events into the local DB. Returns the number upserted."""
    now = datetime.datetime.now(datetime.timezone.utc)
    start = (now - datetime.timedelta(days=_PULL_WINDOW_PAST_DAYS)).isoformat()
    end = (now + datetime.timedelta(days=_PULL_WINDOW_FUTURE_DAYS)).isoformat()

    graph_events = client.list_events(start, end)
    local_by_external_id = {
        row["external_id"]: row for row in db.get_events_by_external_source(EXTERNAL_SOURCE)
    }

    kept_ids: list[str] = []
    for ev in graph_events:
        graph_id = ev.get("id")
        if not graph_id:
            continue
        if ev.get("isCancelled"):
            # Treat a cancelled occurrence the same as one Graph no longer
            # returns at all — don't keep it, so delete_events_not_in()
            # below removes any local copy (and doesn't resurrect one a
            # user already deleted locally).
            continue
        kept_ids.append(graph_id)

        local = local_by_external_id.get(graph_id)
        if local and local.get("sync_dirty"):
            remote_modified = _parse_iso(ev.get("lastModifiedDateTime", ""))
            local_modified = _parse_iso(local.get("updated_at", ""))
            if remote_modified and local_modified and local_modified >= remote_modified:
                continue  # local edit is newer — keep it, it'll push next cycle

        db.upsert_external_event(EXTERNAL_SOURCE, graph_id, _graph_event_to_dict(ev))

    # Never silently drop a locally-dirty row just because it fell outside
    # this pull's window or a transient Graph response gap.
    for row in local_by_external_id.values():
        if row.get("sync_dirty") and row["external_id"] not in kept_ids:
            kept_ids.append(row["external_id"])

    db.delete_events_not_in(EXTERNAL_SOURCE, kept_ids)
    return len(kept_ids)


def push_dirty(db: CalendarDB, client: GraphClient) -> int:
    """PATCH locally-edited, Outlook-originated events back to Graph."""
    tz = get_local_timezone()
    pushed = 0
    for event in db.get_dirty_outlook_events():
        if not event.get("external_id"):
            continue  # never auto-create plain local events on Outlook
        try:
            client.update_event(event["external_id"], _local_event_to_payload(event, tz))
            db.clear_sync_dirty(event["id"])
            pushed += 1
        except (AuthExpiredError, GraphAPIError):
            logger.warning("Failed to push event %s to Outlook — will retry next cycle", event["id"])
    return pushed


def push_deletes(db: CalendarDB, client: GraphClient) -> int:
    """Drain the tombstone queue, deleting on Graph what was deleted locally."""
    pushed = 0
    for tombstone in db.pop_sync_deletes():
        if tombstone["external_source"] != EXTERNAL_SOURCE:
            continue
        try:
            client.delete_event(tombstone["external_id"])
            pushed += 1
        except (AuthExpiredError, GraphAPIError):
            db.requeue_sync_delete(tombstone["external_source"], tombstone["external_id"])
    return pushed


def run_full_sync(db: CalendarDB, config: AppConfig) -> dict:
    """Refresh every connected calendar source. Used by the periodic timer
    and the manual 'Sync Now' button alike."""
    results: dict = {
        "ics_synced": 0, "ics_removed": 0,
        "outlook_pulled": 0, "outlook_pushed": 0,
        "errors": [],
    }

    kept, removed, ics_errors = sync_all_ics_sources(db)
    results["ics_synced"] = kept
    results["ics_removed"] = removed
    results["errors"].extend(ics_errors)

    outlook_source = db.get_calendar_source_by_kind("outlook")
    if outlook_source is None or not outlook_source["enabled"] or config.microsoft is None:
        return results

    try:
        auth = MSALAuth(config.microsoft)
        client = GraphClient(auth)
        results["outlook_pulled"] = pull(db, client)
        if outlook_source.get("two_way"):
            results["outlook_pushed"] = push_dirty(db, client) + push_deletes(db, client)
        db.update_calendar_source(outlook_source["id"], last_synced=_utcnow_iso())
    except AuthExpiredError as e:
        results["errors"].append(f"Outlook: {e}")
    except Exception as e:
        logger.exception("Outlook sync failed")
        results["errors"].append(f"Outlook sync: {e}")

    return results
