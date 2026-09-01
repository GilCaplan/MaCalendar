"""Placing training sessions on real dates, around Shabbat and the chagim.

`observance.py` says what a day permits. This module decides what actually goes
on it — and the split is deliberate. Observance is not negotiable and is
computed; training policy is a set of preferences that can be argued with, and
lives here:

  * a minor fast (Tzom Gedalia, 17 Tammuz) is a full rest day, not a late-night
    run — the session moves rather than being squeezed past nightfall;
  * motzei Shabbat / motzei chag is a last resort, spent only when a chag would
    otherwise cost a session outright;
  * two hard sessions never land on consecutive days if a legal alternative
    exists;
  * one run per day, and lower-body strength is kept off the day before a
    long run.

# Why placement is deterministic

An LLM may propose a week's shape (see `actions/workout_routine`), but every
date it proposes is re-placed here against `observance.availability()`. A model
that has confidently scheduled a tempo run on Yom Kippur is not a hypothetical
— it is the default behaviour of any model that has not been told the Hebrew
date. Proposals are advisory; placement is not.
"""

from __future__ import annotations

import dataclasses
import datetime
from typing import Dict, List, Optional, Sequence, Tuple

from assistant import observance as ob

# Sessions that carry real intensity. Two of these on consecutive days is the
# thing the relocation search works hardest to avoid.
#
# The long run is deliberately NOT here. Every long run in this block is run at
# easy aerobic pace (6:00-6:30/km, HR under 155), and counting it as hard makes
# the 48-hour rule cascade: a long run displaced onto a Tuesday pushes
# Wednesday's threshold to Thursday, which pushes Friday's speed session into
# the following week. "48 hours between hard days" means threshold, speed and
# time trials.
HARD_KINDS = {"threshold", "speed", "tt"}
RUN_KINDS = {"long", "easy", "threshold", "speed", "tt"}
STRENGTH_KINDS = {"gym", "calisthenics"}

# Fallback session lengths, in minutes, when a spec doesn't carry one.
_DEFAULT_MINUTES = {
    "long": 100, "easy": 45, "threshold": 60, "speed": 60, "tt": 60,
    "gym": 60, "calisthenics": 45, "rest": 0,
}

# How far the search will move a session from where it was wanted.
_MAX_SHIFT_DAYS = 3
_SEARCH_OFFSETS = [1, -1, 2, -2, 3, -3]


@dataclasses.dataclass
class SessionSpec:
    """One session, before it knows what date it will survive on."""

    kind: str
    title: str
    preferred_date: datetime.date
    detail: str = ""
    discipline: str = ""                 # derived from kind when blank
    distance_km: Optional[float] = None
    duration_minutes: Optional[int] = None
    preferred_time: Optional[datetime.time] = None
    template_id: Optional[str] = None
    # Squats, deadlifts, lunges. Only lower-body work is kept off the day
    # before a long run — pressing and pulling the day before does no harm,
    # and blocking it would cost a strength session every week for nothing.
    lower_body: bool = False
    # A session the plan considers immovable (a goal-race time trial, say).
    # Pinned sessions are still validated; if the date is genuinely unavailable
    # the result reports a warning rather than silently relocating it.
    pinned: bool = False

    def __post_init__(self) -> None:
        if not self.discipline:
            self.discipline = (
                "run" if self.kind in RUN_KINDS
                else "rest" if self.kind == "rest"
                else "strength"
            )
        if self.duration_minutes is None:
            self.duration_minutes = _DEFAULT_MINUTES.get(self.kind, 60)


@dataclasses.dataclass
class PlacedSession:
    """A spec that has found a legal home."""

    spec: SessionSpec
    date: datetime.date
    start_time: Optional[datetime.time]
    end_time: Optional[datetime.time]
    window_label: str
    observance_note: str
    moved_from: Optional[datetime.date] = None

    def as_plan_item(self) -> dict:
        return {
            "date": self.date.isoformat(),
            "start_time": self.start_time.strftime("%H:%M") if self.start_time else "",
            "end_time": self.end_time.strftime("%H:%M") if self.end_time else "",
            "kind": self.spec.kind,
            "discipline": self.spec.discipline,
            "title": self.spec.title,
            "detail": self.spec.detail,
            "distance_km": self.spec.distance_km,
            "template_id": self.spec.template_id,
            "window_label": self.window_label,
            "observance_note": self.observance_note,
        }


@dataclasses.dataclass
class SchedulePolicy:
    """The arguable half — training preferences, not halacha."""

    minor_fast_is_rest_day: bool = True
    allow_motzei_fallback: bool = True
    avoid_back_to_back_hard: bool = True
    # No LOWER-BODY strength the day before a long run: heavy legs on Thursday
    # is how a Friday long run turns into a bad Friday long run. Upper-body
    # work on that day is left alone.
    protect_day_before_long: bool = True
    default_morning: datetime.time = datetime.time(6, 30)
    default_evening: datetime.time = datetime.time(18, 30)


@dataclasses.dataclass
class ScheduleResult:
    placed: List[PlacedSession]
    # Human-readable notes: what moved, what could not be placed, and why.
    moves: List[str] = dataclasses.field(default_factory=list)
    warnings: List[str] = dataclasses.field(default_factory=list)

    def items(self) -> List[dict]:
        return [p.as_plan_item() for p in self.placed]


# ---------------------------------------------------------------------------
# Day-level legality
# ---------------------------------------------------------------------------

def _is_rest_by_policy(
    date: datetime.date, policy: SchedulePolicy, settings: ob.ObservanceSettings
) -> Tuple[bool, str]:
    """Training policy on top of observance: (must rest?, why).

    Observance already blocks the daylight of a fast. What policy adds is
    refusing the evening *after* one — halachically fine, but running on legs
    that have just come off a fast is how people get hurt.
    """
    if policy.minor_fast_is_rest_day and ob.is_fast_day(date):
        return True, ob.fast_day_name(date)
    return False, ""


def _usable_windows(
    date: datetime.date,
    policy: SchedulePolicy,
    settings: ob.ObservanceSettings,
    allow_fallback: bool = True,
) -> List[ob.TimeWindow]:
    """Windows on *date* this policy is willing to use, best first.

    `allow_fallback` is what keeps motzei Shabbat a genuine last resort. The
    scheduler runs its whole search once with it off — so every ordinary day
    within reach is considered first — and only then runs it again with it on.
    Without that two-pass structure a session preferred on Shabbat would take
    Saturday night rather than moving to the Sunday, which is the opposite of
    the intent.
    """
    rest, _ = _is_rest_by_policy(date, policy, settings)
    if rest:
        return []
    av = ob.availability(date, settings)
    ordinary = [w for w in av.windows if not w.fallback]
    if ordinary:
        return ordinary
    if allow_fallback and policy.allow_motzei_fallback:
        return [w for w in av.windows if w.fallback]
    return []


def _shift_time(t: datetime.time, minutes: int) -> datetime.time:
    total = min(t.hour * 60 + t.minute + minutes, 23 * 60 + 59)
    return datetime.time(total // 60, total % 60)


def _clamp_into_window(
    window: ob.TimeWindow, preferred: Optional[datetime.time], minutes: int
) -> Tuple[datetime.time, datetime.time]:
    """Fit a session of *minutes* inside *window*, as near *preferred* as possible."""
    win_lo = window.start.hour * 60 + window.start.minute
    win_hi = window.end.hour * 60 + window.end.minute
    want = (
        preferred.hour * 60 + preferred.minute
        if preferred is not None
        else (win_lo if window.label in ("morning", "evening") else win_lo)
    )
    latest_start = max(win_lo, win_hi - minutes)
    start = min(max(want, win_lo), latest_start)
    end = min(start + minutes, win_hi)
    return (
        datetime.time(start // 60, start % 60),
        datetime.time(min(end // 60, 23), end % 60),
    )


# ---------------------------------------------------------------------------
# The scheduler
# ---------------------------------------------------------------------------

def schedule(
    specs: Sequence[SessionSpec],
    settings: ob.ObservanceSettings = ob.DEFAULT_SETTINGS,
    policy: Optional[SchedulePolicy] = None,
) -> ScheduleResult:
    """Place every spec on a legal date, moving what has to move.

    Specs are processed in preferred-date order so that earlier sessions claim
    their days first and later ones flow around them — the alternative, taking
    them in list order, lets a Friday session displace a Tuesday one.
    """
    policy = policy or SchedulePolicy()
    result = ScheduleResult(placed=[])

    # date -> disciplines already committed that day
    taken: Dict[datetime.date, List[PlacedSession]] = {}

    def hard_on(day: datetime.date) -> bool:
        return any(p.spec.kind in HARD_KINDS for p in taken.get(day, []))

    def run_on(day: datetime.date) -> bool:
        return any(p.spec.discipline == "run" for p in taken.get(day, []))

    def long_on(day: datetime.date) -> bool:
        return any(p.spec.kind == "long" for p in taken.get(day, []))

    # Long runs are looked up from the specs, not only from what has already
    # been placed. Sessions are processed in date order, so a Thursday leg day
    # is decided before Friday's long run exists — checking `taken` alone would
    # let heavy legs land the day before every long run in the block.
    wanted_long_days = {
        s.preferred_date for s in specs if s.kind == "long"
    }

    def acceptable(
        spec: SessionSpec, day: datetime.date, strict: bool, allow_fallback: bool
    ) -> bool:
        """Is *day* a home for *spec*? `strict` applies the soft preferences too."""
        if not _usable_windows(day, policy, settings, allow_fallback):
            return False
        if spec.discipline == "run" and run_on(day):
            return False
        if spec.discipline == "strength" and len(taken.get(day, [])) >= 2:
            return False
        if not strict:
            return True
        if policy.avoid_back_to_back_hard and spec.kind in HARD_KINDS:
            if hard_on(day - datetime.timedelta(days=1)) or hard_on(day + datetime.timedelta(days=1)):
                return False
        if policy.protect_day_before_long and spec.discipline == "strength" and spec.lower_body:
            tomorrow = day + datetime.timedelta(days=1)
            if long_on(tomorrow) or tomorrow in wanted_long_days:
                return False
        return True

    def find_date(spec: SessionSpec) -> Optional[datetime.date]:
        """Preferred date first, then outward — ordinary days before fallbacks.

        The outer loop is the fallback gate: everything reachable without
        spending a motzei-Shabbat window is tried before any of it is.
        """
        want = spec.preferred_date
        for allow_fallback in (False, True):
            if allow_fallback and not policy.allow_motzei_fallback:
                break
            # Strictness is the outer preference, not distance: a neighbouring
            # day that satisfies every soft rule beats the preferred day with
            # the soft rules waived. Relaxing first would keep heavy legs on
            # the day before a long run rather than shifting it 24 hours.
            for strict in (True, False):
                if acceptable(spec, want, strict, allow_fallback):
                    return want
                if spec.pinned:
                    continue
                for off in _SEARCH_OFFSETS:
                    if abs(off) > _MAX_SHIFT_DAYS:
                        continue
                    cand = want + datetime.timedelta(days=off)
                    if acceptable(spec, cand, strict, allow_fallback):
                        return cand
        return None

    ordered = sorted(specs, key=lambda s: (s.preferred_date, 0 if s.kind == "rest" else 1))

    for spec in ordered:
        want = spec.preferred_date

        # Rest days are markers, not sessions: they never move and never
        # consume a day's capacity.
        if spec.kind == "rest":
            av = ob.availability(want, settings)
            rest_reason, fast = _is_rest_by_policy(want, policy, settings)
            note = spec.detail or av.reason or (fast if rest_reason else "")
            result.placed.append(PlacedSession(
                spec=spec, date=want, start_time=None, end_time=None,
                window_label="", observance_note=note,
            ))
            continue

        target = find_date(spec)
        if target is None:
            why = ob.availability(want, settings).reason or "no legal slot within 3 days"
            result.warnings.append(
                f"{want:%a %d %b}: could not place {spec.title!r} ({why})"
            )
            continue

        windows = _usable_windows(target, policy, settings)
        window = windows[0]  # find_date already proved this is non-empty

        # A second session on a day goes to the evening rather than stacking on
        # top of the first. Two 06:30 entries would overlap in the calendar,
        # and running then lifting back-to-back is not what "run in the
        # morning, lift after work" means.
        if taken.get(target):
            wanted = policy.default_evening
        else:
            wanted = spec.preferred_time or (
                policy.default_morning if window.label in ("morning", "daytime")
                else None
            )
        start, end = _clamp_into_window(window, wanted, spec.duration_minutes or 60)

        # On a short erev window the evening does not exist, so the clamp lands
        # the second session right after the first instead.
        for prior in sorted(taken.get(target, []), key=lambda p: p.end_time or datetime.time(0, 0)):
            if prior.end_time and start < prior.end_time:
                gap = _shift_time(prior.end_time, 30)
                start, end = _clamp_into_window(window, gap, spec.duration_minutes or 60)

        av = ob.availability(target, settings)
        note = ""
        if window.fallback:
            note = f"After {av.reason or 'Shabbat'} ends"
        elif window.label == "morning":
            note = av.reason or "Erev Shabbat"

        placed = PlacedSession(
            spec=spec, date=target, start_time=start, end_time=end,
            window_label=window.label, observance_note=note,
            moved_from=want if target != want else None,
        )
        taken.setdefault(target, []).append(placed)
        result.placed.append(placed)

        if target != want:
            reason = ob.availability(want, settings).reason
            rest, fast = _is_rest_by_policy(want, policy, settings)
            if rest:
                reason = f"{fast} — full rest day"
            result.moves.append(
                f"{spec.title}: {want:%a %d %b} → {target:%a %d %b}"
                + (f" ({reason})" if reason else "")
            )

    result.placed.sort(key=lambda p: (p.date, p.start_time or datetime.time(0, 0)))
    return result


# ---------------------------------------------------------------------------
# Materialising into the calendar
# ---------------------------------------------------------------------------

# Category names the plan writes onto its events, so they pick up their own
# colours from the existing categories store rather than the default blue.
CATEGORY_RUN = "Running"
CATEGORY_STRENGTH = "Gym"

_COLORS = {CATEGORY_RUN: "#1f7a6f", CATEGORY_STRENGTH: "#a96b14"}


def materialise(db, plan_id: str, *, include_rest: bool = False) -> int:
    """Create a calendar event for every session in a stored plan.

    Idempotent by way of `workout_plan_items.event_id`: an item that already
    points at an event is updated in place rather than duplicated, which is
    what makes re-planning safe to run twice.
    """
    plan = db.get_workout_plan(plan_id)
    if plan is None:
        return 0

    written = 0
    for item in plan["items"]:
        if item["kind"] == "rest" and not include_rest:
            continue
        category = CATEGORY_RUN if item["discipline"] == "run" else CATEGORY_STRENGTH
        color = _COLORS.get(category, "#0078d4")
        description = item["detail"] or ""
        if item["observance_note"]:
            description = (description + "\n" if description else "") + item["observance_note"]

        start = item["start_time"] or "06:30"
        end = item["end_time"] or "07:30"

        if item["event_id"]:
            db.update_event(
                item["event_id"], title=item["title"], date=item["date"],
                start_time=start, end_time=end, description=description,
                color=color, category=category,
            )
        else:
            event_id = db.create_event_from_dict({
                "title": item["title"], "date": item["date"],
                "start_time": start, "end_time": end,
                "description": description, "color": color,
                "category": category,
            })
            db.set_plan_item_event(item["id"], event_id)
        written += 1
    return written
