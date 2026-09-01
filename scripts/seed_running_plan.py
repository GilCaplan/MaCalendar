"""Seed a training block into the calendar, observance-checked.

    python -m scripts.seed_running_plan                  # preview, writes nothing
    python -m scripts.seed_running_plan --commit         # write it
    python -m scripts.seed_running_plan --replace        # drop an existing block first

Writes to the REAL calendar DB at ~/.assistant_tools/calendar.db (or wherever
MACALENDAR_DB points). It is a preview by default for that reason: seeding
sixty-odd events is easy to do twice and tedious to undo by hand. `--replace`
is the supported way to re-seed — it removes the previous plan's events through
the `workout_plan_items.event_id` links rather than leaving duplicates behind.
"""

from __future__ import annotations

import argparse
import datetime
import sys
from collections import defaultdict

from assistant import observance as ob
from assistant import workout_plan as wp
from assistant.config import load_config
from assistant.db import CalendarDB
from assistant.programs import autumn_5k


def _settings_from_config() -> ob.ObservanceSettings:
    """Honour config.yaml's `observance:` block, falling back to the defaults."""
    try:
        cfg = load_config()
    except Exception:
        return ob.DEFAULT_SETTINGS
    o = getattr(cfg, "observance", None)
    if o is None:
        return ob.DEFAULT_SETTINGS
    hh, _, mm = o.latest_evening.partition(":")
    return ob.ObservanceSettings(
        latitude=o.latitude, longitude=o.longitude, timezone=o.timezone,
        city=o.city, tzeit_depression=o.tzeit_depression,
        candle_lighting_minutes=o.candle_lighting_minutes,
        erev_buffer_minutes=o.erev_buffer_minutes,
        motzei_buffer_minutes=o.motzei_buffer_minutes,
        earliest_hour=o.earliest_hour,
        latest_evening=datetime.time(int(hh), int(mm or 0)),
    )


def _policy_from_config() -> wp.SchedulePolicy:
    try:
        o = load_config().observance
        return wp.SchedulePolicy(
            minor_fast_is_rest_day=o.minor_fast_is_rest_day,
            allow_motzei_fallback=o.allow_motzei_fallback,
        )
    except Exception:
        return wp.SchedulePolicy()


def _print_schedule(result: wp.ScheduleResult) -> None:
    """A week-by-week preview, in the Sunday-to-Saturday week that applies here."""
    by_week: dict = defaultdict(list)
    for p in result.placed:
        # Sunday starts the week: shift so Sunday == 0.
        week_start = p.date - datetime.timedelta(days=(p.date.weekday() + 1) % 7)
        by_week[week_start].append(p)

    for week_start in sorted(by_week):
        sessions = by_week[week_start]
        km = sum(p.spec.distance_km or 0 for p in sessions)
        runs = sum(1 for p in sessions if p.spec.discipline == "run")
        strength = sum(1 for p in sessions if p.spec.discipline == "strength")
        end = week_start + datetime.timedelta(days=6)
        print(f"\n  {week_start:%-d %b} – {end:%-d %b}"
              f"   {runs} runs · {km:.0f} km · {strength} strength")
        print("  " + "-" * 74)
        for p in sorted(sessions, key=lambda p: (p.date, p.start_time or datetime.time(0))):
            when = f"{p.start_time:%H:%M}" if p.start_time else "  –  "
            dist = f"{p.spec.distance_km:>5.1f} km" if p.spec.distance_km else "        "
            note = f"  {p.observance_note}" if p.observance_note else ""
            moved = f"  ← moved from {p.moved_from:%a %-d %b}" if p.moved_from else ""
            print(f"  {p.date:%a %d %b}  {when}  {p.spec.title:<30}{dist}{note}{moved}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--commit", action="store_true",
                    help="actually write the plan and its calendar events")
    ap.add_argument("--replace", action="store_true",
                    help="delete an existing plan of the same name (and its events) first")
    ap.add_argument("--include-rest", action="store_true",
                    help="also create calendar events for rest days")
    args = ap.parse_args(argv)

    settings = _settings_from_config()
    policy = _policy_from_config()

    specs = autumn_5k.build()
    result = wp.schedule(specs, settings=settings, policy=policy)

    print(f"\n{autumn_5k.PLAN_NAME} — {autumn_5k.PLAN_GOAL}")
    print(f"Observance computed for {settings.city} "
          f"({settings.latitude:.4f}, {settings.longitude:.4f})")
    _print_schedule(result)

    total_km = sum(p.spec.distance_km or 0 for p in result.placed)
    runs = sum(1 for p in result.placed if p.spec.discipline == "run")
    strength = sum(1 for p in result.placed if p.spec.discipline == "strength")
    print(f"\n  TOTAL: {runs} runs · {total_km:.0f} km · {strength} strength sessions")

    if result.moves:
        print("\n  Moved by the observance rules:")
        for m in result.moves:
            print(f"    • {m}")
    if result.warnings:
        print("\n  COULD NOT PLACE:")
        for w in result.warnings:
            print(f"    • {w}")

    if not args.commit:
        print("\n  Preview only — nothing written. Re-run with --commit to write it.\n")
        return 0

    db = CalendarDB()

    if args.replace:
        for existing in db.get_workout_plans():
            if existing["name"] == autumn_5k.PLAN_NAME:
                removed = db.delete_workout_plan(existing["id"])
                print(f"\n  Replaced previous plan — removed {removed} calendar events.")

    plan_id = db.create_workout_plan({
        "name": autumn_5k.PLAN_NAME,
        "goal": autumn_5k.PLAN_GOAL,
        "start_date": autumn_5k.PLAN_START.isoformat(),
        "end_date": autumn_5k.PLAN_END.isoformat(),
        "items": result.items(),
    })
    written = wp.materialise(db, plan_id, include_rest=args.include_rest)
    print(f"\n  Wrote plan {plan_id} — {written} calendar events.")
    print("  Restart the Mac app to see them (it does not reload).\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
