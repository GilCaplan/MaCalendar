"""Sundown must be computed for the configured place, not a hardcoded one.

`ObservanceSettings` carried a full set of defaults, and config.yaml carried
the same fields again. Nothing connected them — they merely happened to hold
equal values, because both were written by hand at the same time.

So `candle_lighting(date)`, called without an explicit settings object, used
the dataclass defaults and ignored the configuration entirely. The recurrence
skipping in db.py is exactly such a caller: changing the coordinates in
config.yaml would have moved the workout planner (which builds its own
settings) while leaving the calendar computing Shabbat for wherever the
defaults happened to point.

Nothing was visibly wrong, because the two agreed. It would have gone wrong
the first time someone edited one of them — or the moment a device reported
its own location, which is the whole reason this was found.
"""
from __future__ import annotations

import datetime as dt

import pytest

from assistant import observance as ob


@pytest.fixture
def elsewhere(monkeypatch):
    """Point the configuration at the opposite hemisphere and let it notice.

    Perth rather than somewhere far north: above about 60 degrees the sun
    never reaches 8.5 degrees below the horizon in midsummer, so the solar
    computation correctly returns nothing and the test would be asserting
    against the polar guard rather than against the configuration.
    """
    class _Ob:
        latitude, longitude = -31.95, 115.86      # Perth
        timezone, city = "Australia/Perth", "Perth"
        tzeit_depression, candle_lighting_minutes = 8.5, 18
        erev_buffer_minutes, motzei_buffer_minutes = 90, 30
        earliest_hour, latest_evening = 5, "22:30"

    class _Cfg:
        observance = _Ob()

    monkeypatch.setattr("assistant.config.load_config", lambda *a, **k: _Cfg())
    ob.reload_settings()
    yield
    monkeypatch.undo()
    ob.reload_settings()


def test_the_configured_location_is_the_one_used(elsewhere):
    assert ob.current_settings().city == "Perth"


def test_sundown_actually_moves_with_the_configuration(elsewhere):
    """The real assertion: a different place gives a different answer.

    Late June is midwinter in Perth and midsummer in the northern default, so
    the two local sunsets are hours apart. This cannot pass by accident if the
    configuration were still being ignored.
    """
    june = dt.date(2026, 6, 26)
    configured = ob.sunset(june)
    assert configured is not None
    default = ob.sunset(june, ob.DEFAULT_SETTINGS)
    assert default.hour - configured.hour >= 2, (
        f"sunset barely moved ({default} → {configured}) — configuration ignored")


def test_candle_lighting_follows_the_configured_offset(elsewhere):
    d = dt.date(2026, 9, 4)
    ss, cl = ob.sunset(d), ob.candle_lighting(d)
    gap = (dt.datetime.combine(d, ss) - dt.datetime.combine(d, cl)).seconds / 60
    assert round(gap) == ob.current_settings().candle_lighting_minutes


def test_an_unreadable_configuration_falls_back_rather_than_raising(monkeypatch):
    """A missing config.yaml must not take the calendar down."""
    def boom(*a, **k):
        raise FileNotFoundError("no config here")
    monkeypatch.setattr("assistant.config.load_config", boom)
    ob.reload_settings()
    try:
        assert ob.current_settings() is ob.DEFAULT_SETTINGS
        assert ob.candle_lighting(dt.date(2026, 9, 4)) is not None
    finally:
        monkeypatch.undo()
        ob.reload_settings()


def test_reloading_clears_the_cached_sun_times(elsewhere):
    """The solar computation is cached on its arguments, so a settings change
    that did not clear it would keep returning the previous location's answers
    for any date already asked about."""
    june = dt.date(2026, 6, 26)
    first = ob.sunset(june)
    ob.reload_settings()
    assert ob.sunset(june) == first        # same config, same answer
    assert ob._sun_times.cache_info().currsize <= 2


def test_an_explicit_settings_object_still_wins(elsewhere):
    """The workout planner passes its own; that must not be overridden."""
    d = dt.date(2026, 9, 4)
    assert ob.candle_lighting(d, ob.DEFAULT_SETTINGS) != ob.candle_lighting(d)
