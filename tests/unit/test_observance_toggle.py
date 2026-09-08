"""The observance on/off flag (Gil, 2026-09-05).

`observance.enabled` (config, default on) with the MACALENDAR_OBSERVANCE env
override stands down BOTH gates at once — the engine's AI-creation gate and
the recurring-series skip. The dataset replay harness sets the env to 0: the
dataset's ground truth has no concept of Shabbat, and a Friday replay was
penalising the engine for correctly refusing to book "tomorrow" (cycle 2).
"""
from __future__ import annotations

import datetime
from types import SimpleNamespace


def test_env_zero_disables(monkeypatch):
    monkeypatch.setenv("MACALENDAR_OBSERVANCE", "0")
    from assistant import observance
    assert observance.is_enabled() is False


def test_enabled_is_the_default(monkeypatch):
    monkeypatch.delenv("MACALENDAR_OBSERVANCE", raising=False)
    from assistant import observance
    assert observance.is_enabled() is True


def test_disabled_stands_down_the_engine_gate(monkeypatch):
    monkeypatch.setenv("MACALENDAR_OBSERVANCE", "0")
    from assistant.engine.decompose_validate import validate
    # 2026-09-05 is Shabbat and "gym" is neither leyning, a meal nor davening —
    # with the flag on this would be refused.
    intent = SimpleNamespace(recurrence="", date="2026-09-05",
                             start_time="10:00", title="gym")
    assert validate._observance_verdict(intent, None) is None


def test_disabled_stands_down_the_series_skip(monkeypatch):
    monkeypatch.setenv("MACALENDAR_OBSERVANCE", "0")
    from assistant import db as db_mod
    assert db_mod._skip_for_observance(datetime.date(2026, 9, 5),
                                       "10:00", "gym") is False
