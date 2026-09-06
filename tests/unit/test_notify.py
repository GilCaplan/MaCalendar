"""assistant/notify.py — the notification policy, rung by rung.

Dates are chosen against the real (offline) pyluach/astral computations for
the default Jerusalem settings: 2026-09-11 and 2026-12-11 are Fridays
(candle lighting ~18:36 vs ~16:20 — the seasonal boundary CLAUDE.md warns
about), 2026-09-21 is Yom Kippur, 2026-09-12/2026-12-12 the Shabbatot.
"""

from __future__ import annotations

import datetime

import pytest

from assistant import notify
from assistant.config import NotificationsConfig


def _ev(**kw):
    base = dict(id=1, title="Gym", date="2026-09-08", start_time="18:30",
                end_time="19:30", category="Sports", reminder_minutes=None)
    base.update(kw)
    return base


# --- resolution chain -----------------------------------------------------

def test_event_lead_beats_category_and_default():
    cfg = NotificationsConfig(default_lead_minutes=30,
                              category_leads={"Sports": 45})
    assert notify.resolve_lead(_ev(reminder_minutes=15), cfg) == (15, "event")


def test_event_zero_means_explicitly_none():
    cfg = NotificationsConfig(default_lead_minutes=30)
    assert notify.resolve_lead(_ev(reminder_minutes=0), cfg) == (None, "event_off")


def test_category_lead_beats_default():
    cfg = NotificationsConfig(default_lead_minutes=30,
                              category_leads={"Sports": 45})
    assert notify.resolve_lead(_ev(), cfg) == (45, "category")


def test_category_zero_mutes_the_category():
    # Gil's rule: a category can opt out of notifications entirely.
    cfg = NotificationsConfig(default_lead_minutes=30,
                              category_leads={"Sports": 0})
    assert notify.resolve_lead(_ev(), cfg) == (None, "category_muted")


def test_default_zero_is_opt_in_only():
    cfg = NotificationsConfig(default_lead_minutes=0)
    assert notify.resolve_lead(_ev(), cfg) == (None, "default_off")


def test_default_applies_when_nothing_narrower_speaks():
    cfg = NotificationsConfig(default_lead_minutes=30)
    assert notify.resolve_lead(_ev(category="Errands"), cfg) == (30, "default")


# --- the verdict ----------------------------------------------------------

def test_plain_weekday_event_fires_lead_before_start():
    cfg = NotificationsConfig(default_lead_minutes=30)
    at, why = notify.notify_verdict(_ev(), cfg)     # Tue 2026-09-08
    assert at == "2026-09-08T18:00" and why is None


def test_no_start_time_no_reminder():
    cfg = NotificationsConfig(default_lead_minutes=30)
    assert notify.notify_verdict(_ev(start_time=""), cfg) == (None, None)


def test_master_switch_off_kills_everything():
    cfg = NotificationsConfig(enabled=False, default_lead_minutes=30)
    assert notify.notify_verdict(_ev(reminder_minutes=15), cfg) == (None, None)


# --- quiet windows (September vs December Friday: the seasonal boundary) --

def test_september_friday_evening_event_is_before_candles():
    # 18:00 Friday 2026-09-11: candle lighting ~18:36 in September — the
    # 17:30 fire time is a plain weekday moment.
    cfg = NotificationsConfig(default_lead_minutes=30)
    at, why = notify.notify_verdict(_ev(date="2026-09-11", start_time="18:00"), cfg)
    assert at == "2026-09-11T17:30" and why is None


def test_december_friday_same_clock_time_is_inside_shabbat():
    # Same 18:00 Friday in December: candles ~16:20 — the event itself is
    # inside the window, so the reminder is suppressed with the reason.
    cfg = NotificationsConfig(default_lead_minutes=30)
    at, why = notify.notify_verdict(_ev(date="2026-12-11", start_time="18:00"), cfg)
    assert at is None and why == "shabbat"


def test_shabbat_lunch_suppressed():
    # 2026-12-12 is a plain Shabbat (2026-09-12 would be Rosh Hashana too —
    # the first draft of this test learned that from the code being right).
    cfg = NotificationsConfig(default_lead_minutes=30)
    at, why = notify.notify_verdict(_ev(date="2026-12-12", start_time="12:00"), cfg)
    assert at is None and why == "shabbat"


def test_motzei_event_reminder_clamps_past_havdala():
    # Motzei Shabbat 2026-12-12: December tzeit ~17:2x; a 21:00 event with a
    # 300-minute lead would fire 16:00 (inside Shabbat) — clamped to
    # tzeit + motzei_buffer (30), landing after havdala but before the event.
    cfg = NotificationsConfig(category_leads={"Sports": 300})
    at, why = notify.notify_verdict(_ev(date="2026-12-12", start_time="21:00"), cfg)
    assert why is None and at is not None
    t = datetime.datetime.fromisoformat(at)
    assert t.date() == datetime.date(2026, 12, 12)
    assert datetime.time(17, 0) <= t.time() <= datetime.time(18, 30)


def test_yom_kippur_is_in_the_yom_tov_set():
    # Verify, don't assume (the plan's own instruction): YK 2026-09-21.
    cfg = NotificationsConfig(default_lead_minutes=30)
    at, why = notify.notify_verdict(_ev(date="2026-09-21", start_time="17:00"), cfg)
    assert at is None and why is not None and why.startswith("yom_tov:")


def test_respect_observance_off_ignores_shabbat():
    cfg = NotificationsConfig(default_lead_minutes=30, respect_observance=False)
    at, why = notify.notify_verdict(_ev(date="2026-09-12", start_time="12:00"), cfg)
    assert at == "2026-09-12T11:30" and why is None


def test_fail_open_when_solar_data_missing(monkeypatch):
    # No candle-lighting/tzeit data ⇒ notify normally (the series-skip
    # philosophy verbatim), never silently hold.
    from assistant import observance as ob
    monkeypatch.setattr(ob, "tzeit", lambda *a, **k: None)
    monkeypatch.setattr(ob, "candle_lighting", lambda *a, **k: None)
    cfg = NotificationsConfig(default_lead_minutes=30)
    at, why = notify.notify_verdict(_ev(date="2026-09-12", start_time="12:00"), cfg)
    assert at == "2026-09-12T11:30" and why is None


# --- annotation -----------------------------------------------------------

def test_annotate_adds_the_three_fields():
    rows = [_ev()]
    out = notify.annotate(rows, NotificationsConfig(default_lead_minutes=15))
    assert out[0]["notify_at"] == "2026-09-08T18:15"
    assert out[0]["notify_suppressed_reason"] is None
    assert "reminder_minutes" in out[0]


# --- end-to-end: the payload carries the verdict --------------------------

def test_events_endpoint_serves_notify_fields():
    from assistant.api.server import create_app
    from assistant.db import get_db
    app = create_app()
    app.config["TESTING"] = True
    db = get_db()
    eid = db.create_event_from_dict({
        "title": "Standup", "date": "2026-09-08",
        "start_time": "09:00", "end_time": "09:15",
        "reminder_minutes": 15,
    })
    try:
        with app.test_client() as c:
            row = c.get(f"/events/{eid}").get_json()
            assert row["reminder_minutes"] == 15
            assert row["notify_at"] == "2026-09-08T08:45"
            assert row["notify_suppressed_reason"] is None
            listed = c.get("/events?date=2026-09-08").get_json()
            assert all("notify_at" in e for e in listed)
    finally:
        db.delete_event(eid)
