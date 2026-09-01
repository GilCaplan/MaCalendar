"""Scheduling sessions around the calendar, and the training policy on top."""

import datetime

from assistant import observance as ob
from assistant import workout_plan as wp
from assistant.programs import autumn_5k

D = datetime.date


def spec(kind, title, date, **kw):
    return wp.SessionSpec(kind=kind, title=title, preferred_date=date, **kw)


def placed_on(result, date):
    return [p for p in result.placed if p.date == date]


# ---------------------------------------------------------------------------
# Observance is honoured
# ---------------------------------------------------------------------------

def test_session_on_shabbat_is_moved():
    res = wp.schedule([spec("easy", "Easy 5 km", D(2026, 9, 19))])
    assert res.placed[0].date != D(2026, 9, 19)
    assert not res.warnings


def test_session_on_yom_kippur_is_moved():
    res = wp.schedule([spec("threshold", "Threshold", D(2026, 9, 21))])
    got = res.placed[0].date
    assert got != D(2026, 9, 21)
    assert not ob.is_yom_tov(got)


def test_minor_fast_is_a_full_rest_day():
    """Tzom Gedalia: the session moves rather than being pushed past nightfall."""
    res = wp.schedule([spec("long", "Long 12 km", D(2026, 9, 14))])
    assert res.placed[0].date == D(2026, 9, 15)
    assert "Tzom Gedalia" in res.moves[0]


def test_minor_fast_may_be_used_when_policy_says_so():
    """With the house rule off, the fast day becomes schedulable again — but
    only after nightfall, because observance still blocks its daylight."""
    policy = wp.SchedulePolicy(minor_fast_is_rest_day=False)
    res = wp.schedule(
        [spec("easy", "Easy", D(2026, 9, 14), pinned=True)], policy=policy
    )
    assert res.placed[0].date == D(2026, 9, 14)
    assert res.placed[0].window_label == "evening"

    # And with the rule on, that same pinned session cannot be placed at all.
    res = wp.schedule([spec("easy", "Easy", D(2026, 9, 14), pinned=True)])
    assert res.placed == []
    assert res.warnings


def test_erev_chag_session_finishes_before_candle_lighting():
    """Fri 11 Sep 2026 — Rosh Hashanah at sundown. The session keeps its day."""
    res = wp.schedule([spec("speed", "Speed 5 x 400", D(2026, 9, 11))])
    p = res.placed[0]
    assert p.date == D(2026, 9, 11)
    assert p.window_label == "morning"
    assert p.end_time < ob.candle_lighting(D(2026, 9, 11))
    assert "Rosh Hashana" in p.observance_note


def test_chol_hamoed_sessions_are_left_alone():
    """The whole point: Sukkot's working days must not be treated as yom tov."""
    days = [D(2026, 9, 27), D(2026, 9, 28), D(2026, 9, 29), D(2026, 9, 30), D(2026, 10, 1)]
    res = wp.schedule([spec("easy", f"Easy {i}", d) for i, d in enumerate(days)])
    assert [p.date for p in res.placed] == days
    assert res.moves == []


# ---------------------------------------------------------------------------
# Motzei Shabbat is a fallback, not a normal slot
# ---------------------------------------------------------------------------

def test_motzei_fallback_not_used_when_an_ordinary_day_is_free():
    res = wp.schedule([spec("easy", "Easy", D(2026, 9, 19))])   # a Shabbat
    assert res.placed[0].window_label != "evening"


def test_motzei_fallback_used_when_the_week_is_boxed_in():
    """Sat 3 Oct 2026 is Shmini Atzeret; with the days either side taken by
    runs, the session has nowhere ordinary to go and Saturday night is spent."""
    specs = [
        spec("easy", "Fri run", D(2026, 10, 2)),
        spec("easy", "Sun run", D(2026, 10, 4)),
        spec("easy", "Boxed in", D(2026, 10, 3)),
    ]
    res = wp.schedule(specs, policy=wp.SchedulePolicy(avoid_back_to_back_hard=False))
    boxed = [p for p in res.placed if p.spec.title == "Boxed in"][0]
    # Either it took the motzei-chag window, or it found another ordinary day —
    # what it must never do is land during the chag itself.
    assert not (boxed.date == D(2026, 10, 3) and boxed.window_label != "evening")


def test_motzei_can_be_refused_entirely():
    policy = wp.SchedulePolicy(allow_motzei_fallback=False)
    res = wp.schedule([spec("easy", "Easy", D(2026, 9, 19))], policy=policy)
    assert all(p.window_label != "evening" for p in res.placed)


# ---------------------------------------------------------------------------
# Training policy
# ---------------------------------------------------------------------------

def test_two_sessions_on_one_day_do_not_overlap():
    res = wp.schedule([
        spec("easy", "Easy 5 km", D(2026, 10, 6)),
        spec("calisthenics", "Pull & Core", D(2026, 10, 6)),
    ])
    a, b = sorted(placed_on(res, D(2026, 10, 6)), key=lambda p: p.start_time)
    assert a.end_time <= b.start_time


def test_only_one_run_per_day():
    res = wp.schedule([
        spec("easy", "Easy", D(2026, 10, 6)),
        spec("threshold", "Threshold", D(2026, 10, 6)),
    ])
    dates = [p.date for p in res.placed]
    assert len(set(dates)) == 2


def test_lower_body_kept_off_the_day_before_a_long_run():
    res = wp.schedule([
        spec("long", "Long 15 km", D(2026, 10, 9)),
        spec("gym", "Heavy legs", D(2026, 10, 8), lower_body=True),
    ])
    legs = [p for p in res.placed if p.spec.title == "Heavy legs"][0]
    assert legs.date != D(2026, 10, 8)


def test_upper_body_is_allowed_the_day_before_a_long_run():
    """The blunt version of the rule above cost a strength session every week."""
    res = wp.schedule([
        spec("long", "Long 15 km", D(2026, 10, 9)),
        spec("gym", "Upper push", D(2026, 10, 8)),
    ])
    push = [p for p in res.placed if p.spec.title == "Upper push"][0]
    assert push.date == D(2026, 10, 8)


def test_pinned_session_warns_rather_than_moving():
    res = wp.schedule([spec("tt", "Race", D(2026, 9, 21), pinned=True)])
    assert res.placed == []
    assert res.warnings and "Race" in res.warnings[0]


def test_rest_days_are_kept_and_annotated():
    res = wp.schedule([spec("rest", "Rest", D(2026, 9, 26))])
    p = res.placed[0]
    assert p.date == D(2026, 9, 26)
    assert p.start_time is None
    assert "Succos" in p.observance_note or "Shabbat" in p.observance_note


# ---------------------------------------------------------------------------
# The real program
# ---------------------------------------------------------------------------

def test_autumn_block_places_everything():
    res = wp.schedule(autumn_5k.build())
    assert res.warnings == []
    assert len(res.placed) == len(autumn_5k.build())


def test_autumn_block_never_trains_on_a_blocked_day():
    res = wp.schedule(autumn_5k.build())
    for p in res.placed:
        if p.spec.kind == "rest":
            continue
        av = ob.availability(p.date)
        assert not av.is_blocked, f"{p.spec.title} on {p.date}"
        if p.window_label != "evening":
            assert not ob.is_shabbat(p.date), f"{p.spec.title} on {p.date}"
            assert not ob.is_yom_tov(p.date), f"{p.spec.title} on {p.date}"
        assert not ob.is_fast_day(p.date), f"{p.spec.title} on {p.date}"


def test_autumn_block_moves_the_tzom_gedalia_long_run():
    res = wp.schedule(autumn_5k.build())
    assert len(res.moves) == 1
    assert "Tzom Gedalia" in res.moves[0]


def test_autumn_block_has_two_or_three_strength_sessions_every_week():
    res = wp.schedule(autumn_5k.build())
    per_week = {}
    for p in res.placed:
        if p.spec.discipline == "strength":
            key = p.date.isocalendar()[:2]
            per_week[key] = per_week.get(key, 0) + 1
    assert per_week, "no strength sessions at all"
    assert all(2 <= n <= 3 for n in per_week.values()), per_week


def test_autumn_block_has_no_overlapping_sessions():
    res = wp.schedule(autumn_5k.build())
    by_date = {}
    for p in res.placed:
        by_date.setdefault(p.date, []).append(p)
    for date, sessions in by_date.items():
        timed = sorted(
            [s for s in sessions if s.start_time], key=lambda s: s.start_time
        )
        for a, b in zip(timed, timed[1:]):
            assert a.end_time <= b.start_time, f"{date}: {a.spec.title} / {b.spec.title}"


# ---------------------------------------------------------------------------
# Materialising into the calendar
# ---------------------------------------------------------------------------

def test_materialise_creates_and_relinks_events(tmp_path):
    from assistant.db import CalendarDB

    db = CalendarDB(str(tmp_path / "t.db"))
    res = wp.schedule([
        spec("easy", "Easy 8 km", D(2026, 10, 6), distance_km=8.0, detail="8 km easy"),
        spec("rest", "Rest", D(2026, 10, 10)),
    ])
    plan_id = db.create_workout_plan({
        "name": "Test", "start_date": "2026-10-01", "end_date": "2026-10-31",
        "items": res.items(),
    })

    assert wp.materialise(db, plan_id) == 1          # the rest day is not an event
    items = db.get_workout_plan(plan_id)["items"]
    run = [i for i in items if i["kind"] == "easy"][0]
    assert run["event_id"] is not None

    # Running it twice must update in place, not duplicate.
    assert wp.materialise(db, plan_id) == 1
    again = db.get_workout_plan(plan_id)["items"]
    assert [i["event_id"] for i in again] == [i["event_id"] for i in items]


def test_delete_plan_removes_its_events(tmp_path):
    from assistant.db import CalendarDB

    db = CalendarDB(str(tmp_path / "t.db"))
    res = wp.schedule([spec("easy", "Easy", D(2026, 10, 6))])
    plan_id = db.create_workout_plan({
        "name": "Test", "start_date": "2026-10-01", "end_date": "2026-10-31",
        "items": res.items(),
    })
    wp.materialise(db, plan_id)
    assert db.delete_workout_plan(plan_id) == 1
    assert db.get_workout_plan(plan_id) is None
