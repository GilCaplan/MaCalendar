"""Repeating events and Shabbat.

This project already knows when Shabbat is — the training planner will not put
a run on one — so a nightly "mincha maariv every day at 1900" that booked every
Saturday was inconsistent rather than merely unhelpful.

Two things make it correct rather than approximately correct:

  • The boundary is candle lighting and tzeit at the configured location, not
    midnight. Candle lighting in Jerusalem is 18:43 in September and 16:20 in
    December, so a 19:00 Friday event is outside Shabbat in one and inside it
    in the other. Skipping by date would lose every Friday in summer.
  • Meals are the exception, because they are what the day is for. Unless it
    is a fast, where a meal is the one thing that must not be booked — Yom
    Kippur is both, and the fast wins.
"""
from __future__ import annotations

import datetime as dt

import pytest

from assistant.db import _is_meal, _skip_for_observance

FRI_SEP = dt.date(2026, 9, 4)     # candle lighting 18:43
SAT_SEP = dt.date(2026, 9, 5)     # tzeit 19:37
FRI_DEC = dt.date(2026, 12, 18)   # candle lighting 16:20
WED = dt.date(2026, 9, 9)
YOM_KIPPUR = dt.date(2026, 9, 21)


# ------------------------------------------------------------------ boundaries

@pytest.mark.parametrize("date, time, skipped", [
    (FRI_SEP, "06:30", False),   # Friday morning is an ordinary morning
    (FRI_SEP, "18:00", False),   # still before candles
    (FRI_SEP, "19:00", True),    # after 18:43 — Shabbat has begun
    (FRI_DEC, "16:00", False),   # before 16:20
    (FRI_DEC, "17:00", True),    # after candles, and dark by four in December
    (SAT_SEP, "09:00", True),
    (SAT_SEP, "19:00", True),    # before tzeit 19:37
    (SAT_SEP, "20:00", False),   # after tzeit — Shabbat is out
    (WED, "19:00", False),       # an ordinary Wednesday
])
def test_the_boundary_is_candle_lighting_and_tzeit(date, time, skipped):
    assert _skip_for_observance(date, time, "Mincha Maariv") is skipped


def test_the_same_clock_time_differs_by_season():
    """19:00 on a Friday: inside Shabbat in December, outside it in September.
    This is the case a date-only rule cannot get right."""
    assert _skip_for_observance(FRI_SEP, "18:00", "Mincha") is False
    assert _skip_for_observance(FRI_DEC, "18:00", "Mincha") is True


# ----------------------------------------------------------------- exceptions

@pytest.mark.parametrize("title", [
    "Shabbat lunch", "Friday night dinner", "Kiddush", "Seudah shlishit",
    "Melave malka", "brunch with Ima",
])
def test_meals_are_allowed_on_shabbat(title):
    assert _skip_for_observance(SAT_SEP, "13:00", title) is False


@pytest.mark.parametrize("title", ["Mincha Maariv", "Gym", "Standup", "Threshold 9 km"])
def test_everything_else_is_not(title):
    assert _skip_for_observance(SAT_SEP, "13:00", title) is True


def test_a_fast_beats_the_meal_exception():
    """Yom Kippur is chag and fast at once. A meal is exactly what must not be
    booked, so the exception that normally protects it does not apply."""
    assert _skip_for_observance(YOM_KIPPUR, "13:00", "Shabbat lunch") is True
    assert _skip_for_observance(YOM_KIPPUR, "13:00", "Kiddush") is True


def test_the_evening_after_a_fast_needs_no_special_case():
    """A minor fast ends at tzeit and is not yom tov, so nothing blocks the
    evening — including the meal that breaks it."""
    tzom_gedalia = dt.date(2026, 9, 14)
    assert _skip_for_observance(tzom_gedalia, "19:30", "Mincha Maariv") is False
    assert _skip_for_observance(tzom_gedalia, "19:30", "break-fast dinner") is False


# --------------------------------------------------------------- meal wording

@pytest.mark.parametrize("title, is_meal", [
    ("Shabbat lunch", True), ("Kiddush", True), ("seudah shlishit", True),
    ("Friday night dinner", True), ("breakfast", True),
    ("Mincha Maariv", False), ("Gym", False), ("Threshold 9 km", False),
    ("meeting with Tal", False),
])
def test_what_counts_as_a_meal(title, is_meal):
    """Not the category classifier: that colours by social context, filing
    "lunch" under Social and "kiddush" under Prayer."""
    assert _is_meal(title) is is_meal


# ------------------------------------------------------------------- fallback

def test_an_unusable_time_falls_back_to_the_date(monkeypatch):
    assert _skip_for_observance(SAT_SEP, "", "Mincha Maariv") is True
    assert _skip_for_observance(SAT_SEP, "not a time", "Mincha Maariv") is True


def test_nothing_is_skipped_when_observance_cannot_be_computed(monkeypatch):
    """Degrade to booking everything. A series quietly losing days is worse
    than one landing where it should not."""
    import assistant.db as db
    monkeypatch.setattr(db, "RECURRENCE_SKIPS_OBSERVANCE", False)
    assert _skip_for_observance(SAT_SEP, "13:00", "Gym") is False


# ------------------------------------------------- deliberately on Shabbat

@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("MACALENDAR_DB", str(tmp_path / "c.db"))
    import importlib
    import assistant.db as dbmod
    importlib.reload(dbmod)
    return dbmod.CalendarDB(str(tmp_path / "c.db"))


def test_a_series_anchored_on_shabbat_keeps_its_shabbatot(db):
    """A Saturday shiur, or a monthly review that lands on the 31st, was put
    there on purpose. Skipping every later instance would leave a "weekly"
    series with one event in it — the failure mode that turned up when an
    existing month-end test lost its February."""
    root = db.create_event_from_dict({
        "title": "Shabbat shiur", "date": "2026-09-05", "start_time": "16:00",
        "end_time": "17:00", "recurrence": "weekly", "recurrence_end": "2026-10-03",
    })
    dates = sorted(e["date"] for e in db.get_series_events(root))
    assert len(dates) == 5, f"anchored series lost instances: {dates}"
    assert all(dt.date.fromisoformat(d).weekday() == 5 for d in dates)


def test_a_series_that_only_crosses_shabbat_skips_it(db):
    """The case this exists for: "every day at 1900" through a week that
    contains one."""
    root = db.create_event_from_dict({
        "title": "Mincha Maariv", "date": "2026-09-02", "start_time": "19:00",
        "end_time": "19:30", "recurrence": "daily", "recurrence_end": "2026-09-16",
    })
    days = {dt.date.fromisoformat(e["date"]).strftime("%a")
            for e in db.get_series_events(root)}
    assert "Sat" not in days
    assert "Fri" not in days, "19:00 on a Friday in September is after candle lighting"
    assert {"Sun", "Mon", "Tue", "Wed", "Thu"} <= days
