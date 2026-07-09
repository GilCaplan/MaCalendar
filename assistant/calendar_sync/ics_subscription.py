"""Read-only calendar subscriptions via ICS/webcal links.

Any calendar provider (Gmail, Outlook.com, iCloud, Yahoo, ...) hands out a
private "secret address" ICS/webcal URL for a calendar — subscribing to one
needs zero OAuth setup. These feeds are read-only by construction: there is
no write endpoint behind a webcal link, so events synced from one are never
editable in the app. A refresh re-fetches the whole feed, upserts by the
VEVENT UID, and removes local copies of anything no longer present upstream.
"""

from __future__ import annotations

import logging

import requests

from assistant.calendar_ui.importer import parse_ics_bytes
from assistant.db import CalendarDB, _utcnow_iso

logger = logging.getLogger(__name__)


def _normalize_url(url: str) -> str:
    """webcal:// links point at the same feed as https://."""
    if url.startswith("webcal://"):
        return "https://" + url[len("webcal://"):]
    return url


def fetch_ics(url: str) -> bytes:
    resp = requests.get(_normalize_url(url), timeout=30, headers={"User-Agent": "MACalendar/1.0"})
    resp.raise_for_status()
    return resp.content


def sync_ics_source(db: CalendarDB, source: dict) -> tuple[int, int]:
    """Refresh one ICS subscription. Returns (kept, removed).

    *source* is a `calendar_sources` row dict (kind == 'ics_url'). "kept" is
    every event currently in the feed (there's no separate added-vs-updated
    tracking — every fetched event is unconditionally upserted).
    """
    external_source = f"ics:{source['id']}"
    raw = fetch_ics(source["url"])
    events = parse_ics_bytes(raw)

    kept_ids = []
    for ev in events:
        uid = ev.get("external_id") or f"{ev['title']}|{ev['date']}|{ev['start_time']}"
        if source.get("color"):
            ev = {**ev, "color": source["color"]}
        db.upsert_external_event(external_source, uid, ev)
        kept_ids.append(uid)

    removed = db.delete_events_not_in(external_source, kept_ids)
    return len(kept_ids), removed


def sync_all_ics_sources(db: CalendarDB) -> tuple[int, int, list[str]]:
    """Refresh every enabled ICS subscription. Returns (added_or_updated, removed, errors)."""
    total_kept = 0
    total_removed = 0
    errors: list[str] = []
    for source in db.get_calendar_sources():
        if source["kind"] != "ics_url" or not source["enabled"]:
            continue
        try:
            kept, removed = sync_ics_source(db, source)
            total_kept += kept
            total_removed += removed
            db.update_calendar_source(source["id"], last_synced=_utcnow_iso())
        except Exception as e:
            logger.exception("ICS subscription refresh failed for source %s", source["id"])
            errors.append(f"{source.get('label') or source['url']}: {e}")
    return total_kept, total_removed, errors
