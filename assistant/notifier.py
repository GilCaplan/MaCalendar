"""Best-effort pre-event notification banners on the Mac.

Policy vs. delivery: `assistant/notify.py` decides WHEN a reminder should
fire (`notify_at`) and why it must not (`notify_suppressed_reason`); this
module only delivers. The API process runs one daemon thread (started from
`create_app`, right next to the pending-retry loop and gated by the same
`MACALENDAR_NO_WARMUP` check) that wakes every `interval` seconds, re-reads
the config — so a notifications edit takes effect on the API's `--reload`
restart without touching this loop — and considers today's and tomorrow's
events, a horizon that covers any lead up to 24 hours.

Delivery is strictly local: `osascript` banners and, optionally, `say`.
No sockets — the offline rule (`tests/unit/test_offline.py`) applies to
this module verbatim. The re-fire guard is the DB's `reminder_log` table
(UNIQUE on event_id + fires_at): the API restarts on every source edit
under `--reload`, so an in-memory fired-set would re-fire constantly.

The phone is the reliable ringer; this thread is a convenience while the
Mac stack happens to be up. Nothing may raise out of the loop.
"""
from __future__ import annotations

import datetime
import logging
import subprocess
import threading
import time
from typing import Optional

from assistant.notify import notify_verdict

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def _applescript(s: str) -> str:
    """Escape for interpolation inside an AppleScript double-quoted string.

    The command runs argv-style (no shell involved), so backslash and the
    double quote are the only metacharacters; newlines become spaces so a
    multi-line description can never break the literal."""
    return (str(s).replace("\\", "\\\\").replace('"', '\\"')
            .replace("\n", " ").replace("\r", " "))


def _event_start(event: dict) -> "Optional[datetime.datetime]":
    """The event's start as a naive local datetime, or None if unparseable
    (same parse notify_verdict uses, so the two never disagree)."""
    try:
        return datetime.datetime.combine(
            datetime.date.fromisoformat(event["date"]),
            datetime.time(*[int(x) for x in str(event["start_time"]).split(":")[:2]]))
    except (KeyError, ValueError, TypeError):
        return None


def _body(event: dict, minutes: int, late: bool) -> str:
    """Banner body: 'in 15 min · 18:30 · Clinic' (pieces present only when
    the event has them); a caught-up late banner is prefixed so it reads as
    what it is."""
    parts = [f"in {minutes} min"]
    if event.get("start_time"):
        parts.append(str(event["start_time"])[:5])
    if event.get("location"):
        parts.append(str(event["location"]))
    body = " · ".join(parts)
    return f"starting soon — {body}" if late else body


def _deliver(title: str, body: str, cfg, tts_voice: str, minutes: int) -> None:
    """Local-only delivery: an osascript banner, optionally spoken. Failures
    are logged, never raised — a banner is a nicety, not a duty."""
    script = (f'display notification "{_applescript(body)}" '
              f'with title "{_applescript(title)}"')
    if getattr(cfg, "sound", False):
        script += ' sound name "Glass"'
    try:
        subprocess.run(["osascript", "-e", script],
                       capture_output=True, timeout=10)
    except Exception as exc:
        logger.warning("notifier: osascript banner failed: %s", exc)
    if getattr(cfg, "speak", False):
        try:
            # argv-style and prefixed, so a title can never read as a flag.
            subprocess.run(
                ["say", "-v", tts_voice,
                 f"Heads up — {title} in {minutes} minutes."],
                capture_output=True, timeout=60)
        except Exception as exc:
            logger.warning("notifier: say failed: %s", exc)


def _publish_trace(action: str, event: dict, reason: "Optional[str]" = None) -> None:
    """One finished bus run in the shape the HUD already renders: a single
    TraceStep-shaped step (stage/title/detail/ms/at_ms/ok, extras under
    "data") plus a result message. Suppression is announced, never silent —
    the notify policy's own rule."""
    try:
        from assistant import trace_bus
        name = event.get("title") or ""
        data: dict = {"action": action, "event_id": event.get("id")}
        if reason:
            data["reason"] = reason
        step = {"stage": "notify",
                "title": "Reminder fired" if action == "fired" else "Reminder suppressed",
                "detail": name, "ms": 0, "at_ms": 0, "ok": True, "data": data}
        msg = (f'Reminder fired for "{name}"' if action == "fired"
               else f'Reminder for "{name}" suppressed ({reason})')
        trace_bus.publish("mac", [step], {"message": msg})
    except Exception:                            # pragma: no cover - best effort
        pass


# --------------------------------------------------------------------------
# One tick — the clock arrives as arguments so tests drive it synchronously
# --------------------------------------------------------------------------

def _consider(db, cfg, event: dict, now: datetime.datetime,
              last: datetime.datetime, *, tts_voice: str,
              interval: float) -> None:
    at_iso, reason = notify_verdict(event, cfg)

    if reason is not None:
        # Suppressed (Shabbat / yom tov / clamped past start). There is no
        # fire time, so the ONCE-per-event key is the event's own start;
        # log_reminder's UNIQUE row is the dedupe across ticks and restarts.
        start = _event_start(event)
        if start is None:
            return
        key = start.isoformat(timespec="minutes")
        if db.log_reminder(event["id"], key, "suppressed"):
            _publish_trace("suppressed", event, reason=reason)
        return

    if not at_iso:
        return                                  # no reminder configured
    at = datetime.datetime.fromisoformat(at_iso)
    if not (last < at <= now):
        return                                  # not due in this window
    start = _event_start(event)
    if start is None:
        return

    late = (now - at).total_seconds() > interval
    if late:
        # A wake from sleep or an API restart, not a normal tick. Catch up
        # only while the banner is still useful: recent enough, and the
        # event has not already started. Otherwise record the miss —
        # silently, but through log_reminder so it is recorded exactly once.
        catch_up = int(getattr(cfg, "catch_up_minutes", 0) or 0)
        if (now - at) > datetime.timedelta(minutes=catch_up) or now >= start:
            if db.log_reminder(event["id"], at_iso, "missed"):
                logger.debug("notifier: missed reminder for event %s (due %s)",
                             event.get("id"), at_iso)
            return

    if not db.log_reminder(event["id"], at_iso, "fired"):
        return                                  # already delivered (e.g. pre-restart)

    minutes = max(0, int(round((start - now).total_seconds() / 60)))
    _deliver(event.get("title") or "Event", _body(event, minutes, late),
             cfg, tts_voice, minutes)
    _publish_trace("fired", event)


def _tick(db, cfg, now: datetime.datetime, last: datetime.datetime, *,
          tts_voice: str = "Samantha", interval: float = 30.0) -> None:
    """One pass over today's and tomorrow's events: fire what came due in
    (last, now], catch up or record what a sleep/restart missed, and log
    each suppressed reminder once. Never raises."""
    if not getattr(cfg, "enabled", True):
        return
    try:
        events = (db.get_events_for_day(now.date())
                  + db.get_events_for_day(now.date() + datetime.timedelta(days=1)))
    except Exception as exc:
        logger.warning("notifier: could not read events: %s", exc)
        return
    for event in events:
        try:
            _consider(db, cfg, event, now, last,
                      tts_voice=tts_voice, interval=interval)
        except Exception as exc:
            logger.warning("notifier: event %s failed: %s", event.get("id"), exc)


# --------------------------------------------------------------------------
# The daemon
# --------------------------------------------------------------------------

def start_notifier_loop(interval: float = 30.0) -> None:
    """Daemon: deliver due pre-event reminders as macOS banners.

    Mirrors start_pending_retry_loop: sleep first, re-read config every tick
    (an edit lands on the API's --reload restart), catch-all so nothing
    escapes. `last` starts a day back so reminders that came due while the
    API was down (a --reload restart, a closed lid) are reconsidered exactly
    once — reminder_log skips what already fired, and the catch-up policy
    fires or records `missed` for what did not.
    """
    def _loop() -> None:
        from assistant.config import load_config
        from assistant.db import get_db
        last = datetime.datetime.now() - datetime.timedelta(days=1)
        while True:
            time.sleep(interval)
            now = datetime.datetime.now()
            try:
                cfg = load_config()
                ncfg = cfg.notifications
                if not ncfg.enabled:
                    last = now
                    continue
                _tick(get_db(), ncfg, now, last,
                      tts_voice=cfg.tts.voice, interval=interval)
                last = now
            except Exception as exc:
                # Keep `last` where it was: when the fault clears, the wider
                # window replays what this tick should have handled, and the
                # reminder_log keeps the replay from double-firing.
                logger.warning("notifier: tick failed: %s", exc)
    threading.Thread(target=_loop, daemon=True, name="notifier").start()
