"""The six-week base block: 2 September - 17 October 2026, ending in a 5K TT.

Session content only. Not one date in here is final — every one is a *preferred*
date that `workout_plan.schedule()` re-places against `observance.availability()`,
so the block can be re-flowed if a chag moves or the start date shifts.

Two deliberate departures from the plan as originally drafted:

1. **Mon 14 Sep is Tzom Gedalia.** The draft put a 12 km long run on it. The
   preferred date is left on the Monday on purpose — the scheduler is what
   discovers the fast and moves the run to Tuesday, which is the behaviour
   worth having, and worth being able to see fail.

2. **Strength is a slot, not a prescription.** 2-3 sessions a week, each one
   just "Gym / Calisthenics" — the plan books the time and Gil decides on the
   day what to do with it. An earlier version prescribed a Lower / Push / Pull
   rotation with named lifts; it was thrown away because a plan that tells you
   which exercise to do on a Tuesday five weeks out is a plan you stop opening.

   The cost is real and worth stating: because the plan no longer knows which
   day is leg day, it cannot flag one `lower_body` and keep it off the day
   before a long run. `SchedulePolicy.protect_day_before_long` still works and
   is still tested — this program simply has nothing to tell it. Running order
   is yours to keep sensible: the day before a long run is not the day for
   heavy squats.
"""

from __future__ import annotations

import datetime
from typing import List

from assistant.workout_plan import SessionSpec

D = datetime.date


def _s(kind, title, date, detail="", km=None, minutes=None, lower=False, pinned=False):
    return SessionSpec(
        kind=kind, title=title, preferred_date=date, detail=detail,
        distance_km=km, duration_minutes=minutes, lower_body=lower, pinned=pinned,
    )


def build() -> List[SessionSpec]:
    """Every session in the block, in preferred-date order."""
    return [
        # --- Week 0: Wed 2 - Sat 5 Sep. A short opening week. -------------
        _s("easy", "Easy 8 km", D(2026, 9, 2),
           "8 km @ 6:10–6:40 — HR under 155, no exceptions", 8.0),
        _s("gym", "Gym / Calisthenics", D(2026, 9, 2)),
        _s("gym", "Gym / Calisthenics", D(2026, 9, 3)),
        _s("threshold", "Threshold 9 km", D(2026, 9, 4),
           "2.5 km w/u · 2 × 10 min @ 4:40 (2 min jog between) · 2 km c/d", 9.0),
        _s("rest", "Rest — Shabbat", D(2026, 9, 5)),

        # --- Week 1: Sun 6 - Sat 12 Sep. Rosh Hashanah from Friday sundown.
        _s("long", "Long 11 km", D(2026, 9, 6), "11 km @ 6:10–6:30 — HR under 155", 11.0),
        _s("gym", "Gym / Calisthenics", D(2026, 9, 7)),
        _s("easy", "Easy 5 km + strides", D(2026, 9, 8), "5 km + 6 × 20 s strides", 5.0),
        _s("gym", "Gym / Calisthenics", D(2026, 9, 8)),
        _s("threshold", "Threshold 9 km", D(2026, 9, 9),
           "2 km w/u · 2 × 12 min @ 4:40 (2 min jog) · 1.5 km c/d", 9.0),
        _s("gym", "Gym / Calisthenics", D(2026, 9, 10)),
        _s("speed", "Speed 5 × 400 m", D(2026, 9, 11),
           "2 km w/u · 5 × 400 m @ 3:50 (full recovery) · 1.5 km c/d — focus on turnover", 6.0),
        _s("rest", "Rest — Shabbat & Rosh Hashanah I", D(2026, 9, 12)),

        # --- Week 2: Sun 13 - Sat 19 Sep. Chag Sunday, fast Monday. -------
        _s("rest", "Rest — Rosh Hashanah II", D(2026, 9, 13)),
        # Deliberately left on Tzom Gedalia — the scheduler moves it.
        _s("long", "Long 12 km", D(2026, 9, 14), "12 km @ 6:10–6:30", 12.0),
        _s("threshold", "Threshold 10 km", D(2026, 9, 16),
           "2 km w/u · 3 × 10 min @ 4:35 (2 min jog) · 1.5 km c/d", 10.0),
        _s("gym", "Gym / Calisthenics", D(2026, 9, 16)),
        _s("gym", "Gym / Calisthenics", D(2026, 9, 17)),
        _s("speed", "Speed 6 × 400 m", D(2026, 9, 18), "2 km w/u · 6 × 400 m @ 3:50 (full recovery) · 1.5 km c/d", 6.0),
        _s("rest", "Rest — Shabbat", D(2026, 9, 19)),

        # --- Week 3: Sun 20 - Sat 26 Sep. Yom Kippur; the deload. ---------
        _s("easy", "Easy 5 km", D(2026, 9, 20),
           "5 km — hydrate well; skip it if you'd rather bank energy for the fast", 5.0),
        _s("rest", "Rest — Yom Kippur", D(2026, 9, 21)),
        _s("rest", "Rest — post-fast", D(2026, 9, 22),
           "Rehydrate, eat properly, mobility at most."),
        _s("long", "Long 12 km", D(2026, 9, 23),
           "12 km @ 6:10–6:30 — ease into it, two days off behind you", 12.0),
        _s("gym", "Gym / Calisthenics", D(2026, 9, 23)),
        _s("gym", "Gym / Calisthenics", D(2026, 9, 24)),
        _s("threshold", "Threshold 9 km", D(2026, 9, 25),
           "2 km w/u · 2 × 12 min @ 4:35 (2 min jog) · 1.5 km c/d — before Sukkot", 9.0),
        _s("rest", "Rest — Shabbat & Sukkot day 1", D(2026, 9, 26)),

        # --- Week 4: Sun 27 Sep - Sat 3 Oct. Chol HaMoed; biggest week yet.
        _s("long", "Long 13 km", D(2026, 9, 27), "13 km @ 6:00–6:30", 13.0),
        _s("gym", "Gym / Calisthenics", D(2026, 9, 28)),
        _s("easy", "Easy 5 km + strides", D(2026, 9, 29), "5 km + 6 × 20 s strides", 5.0),
        _s("gym", "Gym / Calisthenics", D(2026, 9, 29)),
        _s("threshold", "Threshold 12 km", D(2026, 9, 30),
           "2 km w/u · 3 × 12 min @ 4:30 (2 min jog) · 2 km c/d", 12.0),
        _s("gym", "Gym / Calisthenics", D(2026, 10, 1)),
        _s("speed", "Speed 8 × 400 m", D(2026, 10, 2),
           "2 km w/u · 8 × 400 m @ 3:50 (full recovery) · 1.5 km c/d — Hoshana Rabbah; chag starts at sundown", 7.0),
        _s("rest", "Rest — Shabbat & Shemini Atzeret / Simchat Torah", D(2026, 10, 3)),

        # --- Week 5: Sun 4 - Sat 10 Oct. Calendar clear; long run to Friday.
        _s("threshold", "Threshold 30 min", D(2026, 10, 4),
           "2 km w/u · 30 min continuous @ 4:30 (one block, no breaks) · 1 km c/d", 10.0),
        _s("gym", "Gym / Calisthenics", D(2026, 10, 5)),
        _s("easy", "Easy 6 km + strides", D(2026, 10, 6), "6 km + 6 × 20 s strides", 6.0),
        _s("gym", "Gym / Calisthenics", D(2026, 10, 6)),
        _s("speed", "Speed 5 × 1000 m", D(2026, 10, 7),
           "2.5 km w/u · 5 × 1000 m @ 4:05 (2 min jog) · 2 km c/d — this is goal pace", 10.0),
        _s("gym", "Gym / Calisthenics", D(2026, 10, 8)),
        _s("long", "Long 15 km", D(2026, 10, 9),
           "15 km @ 6:00–6:30 — longest run since 5 Aug", 15.0, minutes=110),
        _s("rest", "Rest — Shabbat", D(2026, 10, 10)),

        # --- Week 6: Sun 11 - Sat 17 Oct. Benchmark week. -----------------
        _s("threshold", "Threshold 30 min", D(2026, 10, 11), "2 km w/u · 30 min continuous @ 4:25 · 2 km c/d", 11.0),
        _s("gym", "Gym / Calisthenics", D(2026, 10, 12)),
        _s("easy", "Easy 6 km", D(2026, 10, 13), "6 km — strictly easy", 6.0),
        _s("gym", "Gym / Calisthenics", D(2026, 10, 13)),
        _s("speed", "Speed 4 × 1000 m", D(2026, 10, 14),
           "2.5 km w/u · 4 × 1000 m @ 4:00 (2 min jog) · 2 km c/d — short of the usual set, on purpose", 9.0),
        _s("rest", "Rest — mobility only", D(2026, 10, 15)),
        _s("tt", "5K Time Trial", D(2026, 10, 16),
           "All out. 2 km w/u · 5 km · 2 km c/d — flat route, no watch-chasing",
           10.0, pinned=True),
        _s("rest", "Rest — Shabbat", D(2026, 10, 17)),
    ]


PLAN_NAME = "Six Weeks to Oct 18"
PLAN_GOAL = "Base block ending in a 5K time trial, Fri 16 Oct 2026"
PLAN_START = D(2026, 9, 2)
PLAN_END = D(2026, 10, 17)
