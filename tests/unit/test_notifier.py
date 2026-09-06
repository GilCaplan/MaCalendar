"""assistant/notifier.py — the Mac delivery loop over notify.py's policy.

Ticks are driven synchronously with a fake clock (`_tick(db, cfg, now, last)`),
subprocess is recorded rather than run, and the trace bus is pointed at a
per-test file. 2026-09-08 is a plain Tuesday (the same anchor test_notify.py
uses); 2026-12-12 is a plain Shabbat.
"""

from __future__ import annotations

import datetime
import socket
import sqlite3
import subprocess

import pytest

from assistant import notifier, trace_bus
from assistant.config import NotificationsConfig
from assistant.db import CalendarDB

NOW = datetime.datetime(2026, 9, 8, 18, 0)          # Tue evening, no observance
LAST = NOW - datetime.timedelta(seconds=30)         # a normal 30s-earlier tick


@pytest.fixture
def db(tmp_path) -> CalendarDB:
    return CalendarDB(path=str(tmp_path / "notifier_test.db"))


@pytest.fixture
def runs(monkeypatch) -> list:
    """Record every subprocess.run argv the notifier issues; run nothing."""
    calls: list = []

    def fake_run(cmd, *a, **k):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(notifier.subprocess, "run", fake_run)
    return calls


@pytest.fixture
def bus(tmp_path, monkeypatch) -> str:
    """Point the trace bus at a per-test file (BUS_PATH is read per call)."""
    path = str(tmp_path / "bus.jsonl")
    monkeypatch.setattr(trace_bus, "BUS_PATH", path)
    return path


def _seed(db: CalendarDB, title: str, date: str, start: str, end: str,
          reminder: "int | None" = None, location: str = "") -> int:
    return db.create_event_from_dict({
        "title": title, "date": date, "start_time": start, "end_time": end,
        "attendees": "", "location": location, "description": "",
        "recurrence": "", "recurrence_end": "",
        "reminder_minutes": reminder,
    })


def _osascripts(calls: list) -> list:
    return [c for c in calls if c and c[0] == "osascript"]


def _reminder_rows(db: CalendarDB) -> list:
    con = sqlite3.connect(db.path)
    try:
        return con.execute(
            "SELECT event_id, fires_at, outcome FROM reminder_log").fetchall()
    finally:
        con.close()


def _notify_traces(eid: int) -> list:
    return [e for e in trace_bus.read_history()
            if e.get("steps") and e["steps"][0].get("stage") == "notify"
            and e["steps"][0].get("data", {}).get("event_id") == eid]


# --------------------------------------------------------------------------
# Firing and the re-fire guard
# --------------------------------------------------------------------------

def test_due_reminder_fires_once_then_dedupes(db, runs, bus):
    eid = _seed(db, "Gym", "2026-09-08", "18:15", "19:15",
                reminder=15, location="Holmes Place")
    cfg = NotificationsConfig()                       # sound on, speak off

    notifier._tick(db, cfg, now=NOW, last=LAST)
    osas = _osascripts(runs)
    assert len(osas) == 1
    script = osas[0][2]
    assert 'with title "Gym"' in script
    assert "in 15 min" in script and "18:15" in script and "Holmes Place" in script
    assert 'sound name "Glass"' in script
    assert "starting soon" not in script              # on-time, not a catch-up
    assert db.reminder_logged(eid, "2026-09-08T18:00")

    # Same window replayed (the --reload-restart scenario): the reminder_log
    # row blocks a second banner.
    notifier._tick(db, cfg, now=NOW, last=LAST)
    assert len(_osascripts(runs)) == 1

    # The fire is announced on the bus, once, from the Mac.
    traces = _notify_traces(eid)
    assert len(traces) == 1
    assert traces[0]["source"] == "mac"
    assert traces[0]["steps"][0]["data"]["action"] == "fired"


def test_not_yet_due_does_not_fire(db, runs):
    _seed(db, "Gym", "2026-09-08", "19:00", "20:00", reminder=15)  # due 18:45
    notifier._tick(db, NotificationsConfig(), now=NOW, last=LAST)
    assert runs == []
    assert _reminder_rows(db) == []


def test_titles_are_applescript_escaped(db, runs):
    _seed(db, 'Meet "Rav" \\ chevruta', "2026-09-08", "18:15", "19:00",
          reminder=15)
    notifier._tick(db, NotificationsConfig(), now=NOW, last=LAST)
    script = _osascripts(runs)[0][2]
    assert '\\"Rav\\"' in script                      # quote escaped
    assert "\\\\" in script                           # backslash escaped


# --------------------------------------------------------------------------
# The late-fire policy (wake from sleep / restart)
# --------------------------------------------------------------------------

def test_late_beyond_catch_up_is_missed_silently(db, runs):
    # Due 17:00 (started 17:15); the Mac slept 16:30 → 18:00. An hour late
    # and already started: record the miss, show nothing.
    eid = _seed(db, "Daf", "2026-09-08", "17:15", "18:00", reminder=15)
    notifier._tick(db, NotificationsConfig(), now=NOW,
                   last=NOW - datetime.timedelta(minutes=90))
    assert runs == []
    assert _reminder_rows(db) == [(eid, "2026-09-08T17:00", "missed")]

    # And the miss is recorded exactly once across further ticks.
    notifier._tick(db, NotificationsConfig(), now=NOW,
                   last=NOW - datetime.timedelta(minutes=90))
    assert len(_reminder_rows(db)) == 1


def test_late_within_catch_up_fires_as_starting_soon(db, runs):
    # Due 17:55, now 18:00 — 5 min late (> the 30s interval), inside the
    # 10-min catch-up, and the 18:10 event hasn't started: fire, marked.
    eid = _seed(db, "Standup", "2026-09-08", "18:10", "18:25", reminder=15)
    notifier._tick(db, NotificationsConfig(), now=NOW,
                   last=NOW - datetime.timedelta(minutes=60))
    osas = _osascripts(runs)
    assert len(osas) == 1
    assert "starting soon — " in osas[0][2]
    assert "in 10 min" in osas[0][2]                  # minutes to start, not lead
    assert _reminder_rows(db) == [(eid, "2026-09-08T17:55", "fired")]


def test_late_within_catch_up_but_started_is_missed(db, runs):
    # Due 17:57 for an 17:58 start (1-min lead), now 18:00: only 3 min late,
    # but the event has begun — a banner now is noise, not a heads-up.
    eid = _seed(db, "Call", "2026-09-08", "17:58", "18:20", reminder=1)
    notifier._tick(db, NotificationsConfig(), now=NOW,
                   last=NOW - datetime.timedelta(minutes=60))
    assert runs == []
    assert _reminder_rows(db) == [(eid, "2026-09-08T17:57", "missed")]


# --------------------------------------------------------------------------
# Config switches
# --------------------------------------------------------------------------

def test_disabled_config_does_nothing(db, runs):
    _seed(db, "Gym", "2026-09-08", "18:15", "19:15", reminder=15)
    notifier._tick(db, NotificationsConfig(enabled=False), now=NOW, last=LAST)
    assert runs == []
    assert _reminder_rows(db) == []


def test_sound_off_drops_the_sound_clause(db, runs):
    _seed(db, "Gym", "2026-09-08", "18:15", "19:15", reminder=15)
    notifier._tick(db, NotificationsConfig(sound=False), now=NOW, last=LAST)
    assert "sound name" not in _osascripts(runs)[0][2]


def test_speak_adds_a_say_call_with_the_tts_voice(db, runs):
    _seed(db, "Gym", "2026-09-08", "18:15", "19:15", reminder=15)
    notifier._tick(db, NotificationsConfig(speak=True), now=NOW, last=LAST,
                   tts_voice="Samantha")
    says = [c for c in runs if c[0] == "say"]
    assert len(says) == 1
    assert says[0][1:3] == ["-v", "Samantha"]
    assert says[0][3] == "Heads up — Gym in 15 minutes."
    assert len(_osascripts(runs)) == 1                # the banner still shows


# --------------------------------------------------------------------------
# Suppression bookkeeping (the policy's "announced, never silent")
# --------------------------------------------------------------------------

def test_suppressed_event_logged_and_traced_once(db, runs, bus):
    # Shabbat lunch tomorrow (2026-12-12 is a plain Shabbat): the verdict is
    # (None, "shabbat"). No banner ever; one suppressed row keyed on the
    # event's start; one bus entry.
    eid = _seed(db, "Shabbat lunch", "2026-12-12", "12:00", "14:00")
    cfg = NotificationsConfig(default_lead_minutes=30)
    friday = datetime.datetime(2026, 12, 11, 9, 0)

    notifier._tick(db, cfg, now=friday, last=friday - datetime.timedelta(seconds=30))
    notifier._tick(db, cfg, now=friday + datetime.timedelta(seconds=30), last=friday)

    assert runs == []
    assert _reminder_rows(db) == [(eid, "2026-12-12T12:00", "suppressed")]
    traces = _notify_traces(eid)
    assert len(traces) == 1
    step = traces[0]["steps"][0]
    assert step["data"]["action"] == "suppressed"
    assert step["data"]["reason"] == "shabbat"
    assert traces[0]["source"] == "mac"


def test_event_without_reminder_is_ignored_entirely(db, runs, bus):
    # default_lead 0 = opt-in only: verdict (None, None) — not suppressed,
    # not fired, no bookkeeping at all.
    eid = _seed(db, "Errand", "2026-09-08", "18:15", "19:00")
    notifier._tick(db, NotificationsConfig(), now=NOW, last=LAST)
    assert runs == []
    assert _reminder_rows(db) == []
    assert _notify_traces(eid) == []


# --------------------------------------------------------------------------
# Offline and process rules
# --------------------------------------------------------------------------

def test_a_tick_opens_no_sockets(db, runs, bus, monkeypatch):
    """The offline rule applies here verbatim: osascript + say + sqlite only."""
    class NoSockets:
        def __init__(self, *a, **k):
            raise AssertionError("notifier opened a socket")

    monkeypatch.setattr(socket, "socket", NoSockets)
    _seed(db, "Gym", "2026-09-08", "18:15", "19:15", reminder=15)
    notifier._tick(db, NotificationsConfig(speak=True), now=NOW, last=LAST)
    assert len(_osascripts(runs)) == 1                # delivered, socket-free


def test_create_app_under_no_warmup_does_not_start_the_thread(monkeypatch):
    """conftest sets MACALENDAR_NO_WARMUP=1; create_app must build routes
    only. server.py imports start_notifier_loop lazily inside the not-_no_bg
    branch, so patching the module attribute intercepts any call."""
    import os
    assert os.environ.get("MACALENDAR_NO_WARMUP") == "1"
    calls: list = []
    monkeypatch.setattr(notifier, "start_notifier_loop",
                        lambda *a, **k: calls.append(a))
    from assistant.api.server import create_app
    create_app()
    assert calls == []


def test_start_notifier_loop_spawns_a_daemon_thread():
    import threading
    before = {t.ident for t in threading.enumerate()}
    notifier.start_notifier_loop(interval=10 ** 6)    # sleeps first; inert here
    spawned = [t for t in threading.enumerate()
               if t.ident not in before and t.name == "notifier"]
    assert len(spawned) == 1 and spawned[0].daemon
