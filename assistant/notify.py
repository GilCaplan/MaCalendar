"""Pre-event notification policy — the single brain both clients read.

Computes, per event row, WHEN a reminder should fire (`notify_at`) and why
it won't (`notify_suppressed_reason`). The server embeds the answers in
every event payload; the phone schedules local notifications from its cache
of those payloads; the Mac notifier thread fires the same times. Neither
client re-derives policy.

Resolution chain for the lead time (first hit wins):
    event.reminder_minutes  0 → none ("I said no reminder on this one")
                            N → N minutes before start
    category lead           0 → the whole category is MUTED (Gil's rule:
                                a category can opt out of notifications)
                            N → N
    global default          0 → opt-in only (ships as 0), N → N

Quiet windows (observance): evaluated on the FIRE time, sundown-bounded via
candle_lighting/tzeit — never date-only. An event itself inside Shabbat/yom
tov gets no reminder (reason recorded, announced at creation — never
silent). A reminder that lands inside the window for an event AFTER it is
clamped to tzeit + motzei_buffer_minutes. Fasts don't suppress — a reminder
is not a booking. Fail open: no solar data ⇒ notify normally, same
philosophy as the series skip.
"""
from __future__ import annotations

import datetime
import logging
from typing import Optional

logger = logging.getLogger(__name__)

#: How many consecutive holy days a window scan will walk (2-day chag +
#: adjacent Shabbat is the realistic maximum).
_MAX_RUN = 4


# --------------------------------------------------------------------------
# Lead-time resolution
# --------------------------------------------------------------------------

def resolve_lead(event: dict, cfg) -> "tuple[Optional[int], str]":
    """(minutes, source) — minutes None means 'no reminder', and source says
    which rung of the chain decided (event_off / event / category_muted /
    category / default / default_off)."""
    ev = event.get("reminder_minutes")
    if ev is not None:
        return (None, "event_off") if int(ev) == 0 else (int(ev), "event")
    leads = getattr(cfg, "category_leads", None) or {}
    cat = event.get("category") or ""
    if cat in leads:
        n = int(leads[cat])
        return (None, "category_muted") if n == 0 else (n, "category")
    d = int(getattr(cfg, "default_lead_minutes", 0) or 0)
    return (None, "default_off") if d == 0 else (d, "default")


# --------------------------------------------------------------------------
# Quiet windows
# --------------------------------------------------------------------------

def _holy(d: datetime.date) -> bool:
    from assistant import observance as ob
    return ob.is_shabbat(d) or ob.is_yom_tov(d)


def _window_end(d: datetime.date) -> "Optional[datetime.datetime]":
    """End (tzeit of the last consecutive holy day) of the window containing
    holy day `d`; None when solar data is unavailable (fail open)."""
    from assistant import observance as ob
    last = d
    for _ in range(_MAX_RUN):
        nxt = last + datetime.timedelta(days=1)
        if not _holy(nxt):
            break
        last = nxt
    t = ob.tzeit(last)
    return datetime.datetime.combine(last, t) if t else None


def quiet_window_end(moment: datetime.datetime) -> "Optional[datetime.datetime]":
    """When `moment` falls inside a Shabbat/yom-tov window, the window's end;
    else None. Sundown-bounded: erev evenings count from candle lighting,
    the last day releases at tzeit. Any missing solar datum ⇒ None."""
    from assistant import observance as ob
    try:
        d = moment.date()
        if _holy(d):
            end = _window_end(d)
            if end is None:
                return None                       # fail open
            return end if moment < end else None
        nxt = d + datetime.timedelta(days=1)
        if _holy(nxt):
            cl = ob.candle_lighting(d)
            if cl is not None and moment.time() >= cl:
                return _window_end(nxt)
        return None
    except Exception:                              # fail open, like the series skip
        logger.warning("observance unavailable for %s; notifying normally", moment)
        return None


# --------------------------------------------------------------------------
# The verdict
# --------------------------------------------------------------------------

def notify_verdict(event: dict, cfg) -> "tuple[Optional[str], Optional[str]]":
    """(notify_at ISO local datetime | None, suppressed_reason | None)."""
    if not getattr(cfg, "enabled", True):
        return None, None
    lead, _src = resolve_lead(event, cfg)
    if lead is None or not event.get("start_time") or not event.get("date"):
        return None, None
    try:
        start = datetime.datetime.combine(
            datetime.date.fromisoformat(event["date"]),
            datetime.time(*[int(x) for x in event["start_time"].split(":")[:2]]))
    except (ValueError, TypeError):
        return None, None
    fire = start - datetime.timedelta(minutes=lead)

    if getattr(cfg, "respect_observance", True):
        from assistant import observance as ob
        if ob.is_enabled():
            start_end = quiet_window_end(start)
            if start_end is not None:
                # The event itself is inside the window (Shabbat lunch):
                # no reminder, and the reason travels with the payload.
                d = start.date()
                name = ob.yom_tov_name(d) if ob.is_yom_tov(d) else ""
                return None, (f"yom_tov:{name}" if name else "shabbat")
            fire_end = quiet_window_end(fire)
            if fire_end is not None:
                # Motzei event whose lead lands inside the window: clamp to
                # after havdala plus the configured buffer.
                buf = ob.current_settings().motzei_buffer_minutes
                fire = fire_end + datetime.timedelta(minutes=buf)
                if fire >= start:
                    return None, "clamped_past_start"
    return fire.isoformat(timespec="minutes"), None


def annotate(rows: "list[dict]", cfg=None) -> "list[dict]":
    """Add reminder_minutes/notify_at/notify_suppressed_reason to event
    payloads — the serialization hook GET /events* runs every row through."""
    if cfg is None:
        from assistant.config import load_config
        cfg = load_config().notifications
    for r in rows:
        at, why = notify_verdict(r, cfg)
        r["notify_at"] = at
        r["notify_suppressed_reason"] = why
        r.setdefault("reminder_minutes", None)
    return rows
