"""Observance rules for training availability.

Dates here are real and checked against the Hebrew calendar for 5787/5788, not
invented. The cases that matter most are the ones a naive implementation gets
wrong: chol hamoed must stay runnable, and an evening must be governed by the
day that follows it rather than the day it is attached to.
"""

import datetime

import pytest

from assistant import observance as ob

D = datetime.date


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def test_yom_tov_recognised():
    assert ob.is_yom_tov(D(2026, 9, 12))    # Rosh Hashana I
    assert ob.is_yom_tov(D(2026, 9, 13))    # Rosh Hashana II
    assert ob.is_yom_tov(D(2026, 9, 21))    # Yom Kippur
    assert ob.is_yom_tov(D(2026, 9, 26))    # Sukkot day 1
    assert ob.is_yom_tov(D(2026, 10, 3))    # Shmini Atzeret


def test_chol_hamoed_is_not_yom_tov():
    """The regression this module exists to prevent.

    `enumerate_holidays()` reports Sukkot as one span from 25 Sep to 2 Oct.
    Scheduling against that would cost four runs in the freest week of the
    block. Every one of these days must come back runnable.
    """
    for day in range(27, 31):                      # 27-30 Sep
        assert ob.is_chol_hamoed(D(2026, 9, day)), day
        assert not ob.is_yom_tov(D(2026, 9, day)), day
    for day in (1, 2):                             # 1-2 Oct, incl. Hoshana Rabbah
        assert ob.is_chol_hamoed(D(2026, 10, day)), day
        assert not ob.is_yom_tov(D(2026, 10, day)), day


def test_chanukah_and_purim_are_ordinary_training_days():
    assert not ob.is_yom_tov(D(2026, 12, 7))       # Chanukah
    assert not ob.is_yom_tov(D(2027, 3, 23))       # Purim
    assert ob.availability(D(2026, 12, 7)).status == "free"


def test_yom_kippur_is_both_festival_and_fast():
    """pyluach returns None from `fast_day()` for Yom Kippur — we normalise it back."""
    yk = D(2026, 9, 21)
    assert ob.is_yom_tov(yk)
    assert ob.is_fast_day(yk)
    assert ob.is_major_fast(yk)
    assert not ob.is_minor_fast(yk)
    assert ob.fast_day_name(yk) == "Yom Kippur"


def test_tisha_bav_is_a_major_fast():
    """pyluach spells it '9 of Av' and reports no festival for it.

    Daylight is blocked. The evening after nightfall is *observantly* free —
    the fast has ended — so this module reports it, and it is the scheduler's
    training policy, not halacha, that declines to put a run there.
    """
    tb = D(2027, 8, 12)
    assert ob.is_fast_day(tb)
    assert ob.is_major_fast(tb)
    assert not ob.is_minor_fast(tb)

    av = ob.availability(tb)
    assert not any(w.label in ("daytime", "morning") for w in av.windows)
    assert not av.has_ordinary_window


def test_minor_fasts():
    assert ob.is_minor_fast(D(2026, 9, 14))        # Tzom Gedalia
    assert ob.is_minor_fast(D(2027, 7, 22))        # 17 Tammuz
    assert not ob.is_minor_fast(D(2026, 9, 15))


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

def test_shabbat_daytime_always_blocked():
    for day in (5, 12, 19, 26):
        av = ob.availability(D(2026, 9, day))
        assert not any(w.label in ("daytime", "morning") for w in av.windows), day


def test_erev_shabbat_is_morning_only():
    av = ob.availability(D(2026, 9, 18))           # ordinary Friday
    assert av.status == "daytime_only"
    assert [w.label for w in av.windows] == ["morning"]
    # Must finish well before candle lighting, not merely before sunset.
    cl = ob.candle_lighting(D(2026, 9, 18))
    assert av.windows[0].end < cl


def test_erev_chag_is_morning_only():
    """Fri 11 Sep 2026: Rosh Hashanah begins at sundown, so the speed session
    has to happen in the morning rather than being lost."""
    av = ob.availability(D(2026, 9, 11))
    assert av.status == "daytime_only"
    assert "Rosh Hashana" in av.reason


def test_evening_is_governed_by_the_following_day():
    """Sat 12 Sep 2026 is Shabbat AND Rosh Hashanah I, with RH II following.

    Motzei Shabbat is normally a fallback window; here it must not exist at
    all, because the chag continues into Sunday.
    """
    assert ob.availability(D(2026, 9, 12)).is_blocked

    # Contrast: Sat 3 Oct 2026 is Shmini Atzeret, and nothing follows it.
    av = ob.availability(D(2026, 10, 3))
    assert av.status == "evening_only"
    assert av.windows[0].fallback is True


def test_motzei_shabbat_is_fallback_only():
    av = ob.availability(D(2026, 9, 19))           # ordinary Shabbat
    assert av.status == "evening_only"
    assert all(w.fallback for w in av.windows)
    assert not av.has_ordinary_window


def test_ordinary_weekday_is_free_into_the_evening():
    """The post-18-October plan runs weeknight evenings; the window must allow it."""
    av = ob.availability(D(2026, 10, 6))           # ordinary Tuesday
    assert av.status == "free"
    assert av.has_ordinary_window
    assert av.windows[0].end >= datetime.time(20, 0)


def test_chol_hamoed_week_is_fully_available():
    """Sun 27 Sep - Thu 1 Oct 2026 carry four runs; none may be blocked."""
    for day in range(27, 31):
        assert ob.availability(D(2026, 9, day)).status == "free", day
    assert ob.availability(D(2026, 10, 1)).status == "free"
    # Hoshana Rabbah is erev Shmini Atzeret — morning only, but not lost.
    assert ob.availability(D(2026, 10, 2)).status == "daytime_only"


def test_erev_yom_kippur_keeps_its_morning():
    av = ob.availability(D(2026, 9, 20))
    assert av.status == "daytime_only"
    assert "Yom Kippur" in av.reason


# ---------------------------------------------------------------------------
# Sun times
# ---------------------------------------------------------------------------

def test_sun_times_are_plausible_for_israel():
    ss = ob.sunset(D(2026, 9, 4))
    tz = ob.tzeit(D(2026, 9, 4))
    assert datetime.time(18, 30) < ss < datetime.time(19, 30)
    assert tz > ss
    # Tzeit at 8.5 deg should be ~30-45 min after sunset at this latitude.
    delta = (
        datetime.datetime.combine(D(2000, 1, 1), tz)
        - datetime.datetime.combine(D(2000, 1, 1), ss)
    ).total_seconds() / 60
    assert 25 <= delta <= 50


def test_candle_lighting_precedes_sunset():
    assert ob.candle_lighting(D(2026, 9, 18)) < ob.sunset(D(2026, 9, 18))


def test_blocked_days_lists_only_constrained_days():
    days = ob.blocked_days(D(2026, 9, 27), D(2026, 10, 1))
    assert days == []                              # all of chol hamoed is clear

    days = ob.blocked_days(D(2026, 9, 11), D(2026, 9, 14))
    got = {d.date for d in days}
    assert got == {D(2026, 9, 11), D(2026, 9, 12), D(2026, 9, 13), D(2026, 9, 14)}


@pytest.mark.parametrize("bad", [datetime.date.min, datetime.date.max])
def test_extreme_dates_degrade_rather_than_raise(bad):
    """Same guarantee hebrew_calendar makes: never propagate a date-math failure."""
    av = ob.availability(bad)
    assert av.status in ("free", "daytime_only", "evening_only", "blocked")
