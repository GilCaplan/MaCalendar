"""The schedule_workout action's non-LLM half.

The generation call itself needs a model and is covered by the integration
suite; what matters here is that nothing the model returns is taken on trust.
"""

import datetime

import pytest

from assistant import workout_plan as wp
from assistant.actions.schedule_workout.action import (
    ScheduleWorkoutAction,
    _GenPlan,
    _GenSession,
    observance_settings,
    schedule_policy,
)

D = datetime.date
TODAY = D(2026, 9, 1)
HORIZON = D(2026, 10, 31)


def gen(**kw):
    base = dict(date="2026-09-15", kind="easy", title="Easy 8 km")
    base.update(kw)
    return _GenSession(**base)


def to_specs(sessions):
    return ScheduleWorkoutAction._to_specs(
        _GenPlan(plan_name="X", sessions=sessions), TODAY, HORIZON
    )


# ---------------------------------------------------------------------------
# Nothing the model returns is trusted
# ---------------------------------------------------------------------------

def test_valid_session_survives():
    specs = to_specs([gen(distance_km=8.0, detail="8 km @ 6:10")])
    assert len(specs) == 1
    assert specs[0].kind == "easy"
    assert specs[0].distance_km == 8.0
    assert specs[0].preferred_date == D(2026, 9, 15)


@pytest.mark.parametrize("bad", [
    {"date": "not-a-date"},
    {"date": "2026-13-45"},
    {"date": "2026-08-01"},        # before today
    {"date": "2027-06-01"},        # past the horizon
    {"kind": "brunch"},            # not a training kind
    {"kind": ""},
    {"title": "   "},              # no title
])
def test_nonsense_is_dropped_not_scheduled(bad):
    assert to_specs([gen(**bad)]) == []


def test_kind_is_case_insensitive():
    assert to_specs([gen(kind="THRESHOLD")])[0].kind == "threshold"


def test_nonpositive_numbers_become_none():
    spec = to_specs([gen(distance_km=0, duration_minutes=-5)])[0]
    assert spec.distance_km is None
    # Falls back to the per-kind default rather than a negative duration.
    assert spec.duration_minutes > 0


def test_good_sessions_survive_alongside_bad_ones():
    specs = to_specs([gen(), gen(kind="nonsense"), gen(date="2026-09-16")])
    assert len(specs) == 2


# ---------------------------------------------------------------------------
# Placement still overrides the model
# ---------------------------------------------------------------------------

def test_a_model_proposing_yom_kippur_is_overruled():
    """The whole reason placement is not left to the LLM."""
    specs = to_specs([gen(date="2026-09-21", kind="threshold", title="Threshold")])
    result = wp.schedule(specs)
    assert result.placed[0].date != D(2026, 9, 21)


def test_a_model_proposing_chol_hamoed_is_left_alone():
    specs = to_specs([gen(date="2026-09-28", title="Easy 6 km")])
    result = wp.schedule(specs)
    assert result.placed[0].date == D(2026, 9, 28)
    assert result.moves == []


# ---------------------------------------------------------------------------
# Confirmation wording
# ---------------------------------------------------------------------------

def test_single_session_confirmation_names_the_day():
    result = wp.schedule(to_specs([gen(date="2026-09-16", title="Easy 8 km")]))
    msg = ScheduleWorkoutAction._confirmation(result, 1)
    assert "Easy 8 km" in msg and "Wednesday 16 September" in msg


def test_confirmation_reports_what_the_rules_moved():
    result = wp.schedule(to_specs([
        gen(date="2026-09-14", kind="long", title="Long 12 km"),
    ]))
    msg = ScheduleWorkoutAction._confirmation(result, 1)
    assert "moved" in msg.lower()
    assert "Tzom Gedalia" in msg


def test_confirmation_counts_a_multi_session_block():
    result = wp.schedule(to_specs([
        gen(date="2026-10-05", title="Easy 6 km"),
        gen(date="2026-10-07", kind="threshold", title="Threshold"),
        gen(date="2026-10-09", kind="long", title="Long 14 km"),
    ]))
    msg = ScheduleWorkoutAction._confirmation(result, 3)
    assert "3 sessions" in msg


# ---------------------------------------------------------------------------
# Config plumbing
# ---------------------------------------------------------------------------

def test_settings_fall_back_when_config_has_no_observance_block():
    class Bare:
        pass

    assert observance_settings(Bare()).city == "Jerusalem"
    assert schedule_policy(Bare()).minor_fast_is_rest_day is True


def test_settings_read_from_config():
    from assistant.config import AppConfig, HotkeyConfig

    cfg = AppConfig(hotkey=HotkeyConfig(modifiers=["cmd"], key="space"))
    settings = observance_settings(cfg)
    assert settings.timezone == "Asia/Jerusalem"
    assert settings.latest_evening == datetime.time(22, 30)


def test_malformed_latest_evening_does_not_raise():
    from assistant.config import AppConfig, HotkeyConfig

    cfg = AppConfig(hotkey=HotkeyConfig(modifiers=["cmd"], key="space"))
    cfg.observance.latest_evening = "half past ten"
    assert observance_settings(cfg).latest_evening == datetime.time(22, 30)
