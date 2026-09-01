"""Put training sessions on the calendar from a free-text request.

Handles both "add an easy 8k on Thursday morning" and "give me four more weeks
building to a 10k" — the difference is only how many sessions come back from
the LLM, so one action covers both.

# The model proposes, the scheduler disposes

The LLM is given the observance calendar for the window it is planning into,
which gets it close. It is not trusted with the result. Every date it returns
is re-placed by `workout_plan.schedule()` against `observance.availability()`,
and the confirmation the user hears reports whatever had to move and why. A
model asked for "a run on Monday" during Sukkot will cheerfully answer with
chol hamoed or with yom tov and cannot tell you which it picked; the rules
engine can, so the rules engine decides.

Sessions land as a `workout_plan` plus real calendar events, exactly like the
seeded block, so a phone-dictated run is indistinguishable from a planned one.
"""

from __future__ import annotations

import datetime
from typing import ClassVar, List, Optional, Type

from pydantic import BaseModel, Field, ValidationError

from assistant import observance as ob
from assistant import workout_plan as wp
from assistant.actions import register
from assistant.actions.base import BaseAction, BaseIntent
from assistant.actions.schedule_workout.intent import ScheduleWorkoutIntent
from assistant.exceptions import ParseError

# How far ahead the planner is allowed to reach when the request doesn't say.
_DEFAULT_HORIZON_DAYS = 56


class _GenSession(BaseModel):
    date: str
    kind: str                       # long|easy|threshold|speed|tt|gym|calisthenics|rest
    title: str
    detail: str = ""
    distance_km: Optional[float] = None
    duration_minutes: Optional[int] = None
    lower_body: bool = False


class _GenPlan(BaseModel):
    plan_name: str
    sessions: List[_GenSession] = Field(default_factory=list)


_SCHEMA_PROMPT = """You are an experienced running and strength coach building a training \
schedule. Turn the user's request into dated sessions. Respond with ONLY a JSON object, no \
prose and no markdown fences, matching EXACTLY this shape:

{
  "plan_name": "<short name for this block, or a short label for a single session>",
  "sessions": [
    {
      "date": "YYYY-MM-DD",
      "kind": "long|easy|threshold|speed|tt|gym|calisthenics|rest",
      "title": "<short title, e.g. 'Easy 8 km' or 'Threshold 3 x 10 min'>",
      "detail": "<the session itself: distances, paces, reps, recoveries>",
      "distance_km": <number or null — total including warm-up and cool-down>,
      "duration_minutes": <number or null>,
      "lower_body": <true only for a squat/deadlift/lunge-focused strength session>
    }
  ]
}

Rules:
  - "kind" must be one of the listed values. Runs are long/easy/threshold/speed/tt; strength \
is gym or calisthenics.
  - Give every running session a distance_km, including warm-up and cool-down.
  - Keep 48 hours between hard sessions (threshold, speed, tt). Long runs are easy-paced and \
do not count as hard.
  - If the request implies several weeks, include 2-3 strength sessions per week on a \
lower / push / pull rotation, and progress the running volume gradually (no more than ~10% \
a week).
  - If the user asks for a single session, return exactly one.
  - Return ONLY the JSON object described above."""


class SchedulingError(ParseError):
    """The LLM's proposed schedule could not be validated or placed."""


@register
class ScheduleWorkoutAction(BaseAction):
    action_name: ClassVar[str] = "schedule_workout"
    description: ClassVar[str] = (
        "Put running or gym sessions on the CALENDAR on specific dates, working around Shabbat "
        "and the chagim. "
        "Triggers on: 'add an easy 8k on Thursday', 'schedule a threshold run Wednesday "
        "morning', 'put my long run on Friday', 'plan four more weeks of running', 'add two "
        "gym sessions a week for the next month', 'schedule my training through October'. "
        "Use this when the user wants training ON THEIR CALENDAR on dates. Do NOT use it for "
        "generating a gym routine's exercises and sets with no dates attached — that is "
        "generate_workout_routine."
    )
    intent_model: ClassVar[Type[BaseIntent]] = ScheduleWorkoutIntent
    parameters_schema: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "request": {
                "type": "string",
                "description": (
                    "The user's free-text training request, verbatim or lightly cleaned up, "
                    "e.g. 'easy 8k on Thursday morning' or 'four more weeks building to a 10k'."
                ),
            },
        },
        "required": ["request"],
    }

    def execute(self, intent: ScheduleWorkoutIntent, config) -> str:  # type: ignore[override]
        from assistant.actions import registry as global_registry
        from assistant.db import get_db
        from assistant.intent.parser import IntentParser

        settings = observance_settings(config)
        policy = schedule_policy(config)

        today = datetime.date.today()
        horizon = today + datetime.timedelta(days=_DEFAULT_HORIZON_DAYS)

        parser = IntentParser(config, global_registry)
        generated = self._generate(parser, intent.request, today, horizon, settings)

        specs = self._to_specs(generated, today, horizon)
        if not specs:
            raise SchedulingError("I couldn't work out which sessions to schedule.")

        result = wp.schedule(specs, settings=settings, policy=policy)
        if not result.placed:
            raise SchedulingError(
                "I couldn't find a legal day for that — "
                + (result.warnings[0] if result.warnings else "the days around it are blocked.")
            )

        db = get_db()
        dates = [p.date for p in result.placed]
        plan_id = db.create_workout_plan({
            "name": generated.plan_name or "Training",
            "goal": intent.request,
            "start_date": min(dates).isoformat(),
            "end_date": max(dates).isoformat(),
            "items": result.items(),
        })
        written = wp.materialise(db, plan_id)

        return self._confirmation(result, written)

    # ------------------------------------------------------------------
    # LLM call
    # ------------------------------------------------------------------

    @staticmethod
    def _generate(
        parser: "IntentParser",
        request: str,
        today: datetime.date,
        horizon: datetime.date,
        settings: ob.ObservanceSettings,
    ) -> _GenPlan:
        """Ask for a schedule, having first told the model which days are out.

        The blocked-day list is what stops the model proposing Yom Kippur and
        forcing a relocation the user then has to be told about. It is a
        convenience, not a guarantee — `wp.schedule()` re-checks regardless.
        """
        blocked = ob.blocked_days(today, horizon, settings)
        lines = []
        for av in blocked:
            if av.status == "blocked":
                lines.append(f"  {av.date} ({av.date:%a}) — {av.reason}: no training at all")
            elif av.status == "daytime_only":
                lines.append(f"  {av.date} ({av.date:%a}) — {av.reason}: morning only, "
                             f"must finish by {av.windows[0].end:%H:%M}")
            elif av.status == "evening_only":
                lines.append(f"  {av.date} ({av.date:%a}) — {av.reason}: evening only, "
                             f"after {av.windows[0].start:%H:%M}")

        calendar_note = (
            "Days that are restricted or unavailable in this window:\n" + "\n".join(lines)
            if lines else "No restricted days in this window."
        )

        user_prompt = (
            f"Today is {today:%A %d %B %Y}. Schedule nothing before today and nothing "
            f"after {horizon:%d %B %Y}.\n\n"
            f"{calendar_note}\n\n"
            f"User's request: {request!r}\n\nProduce the JSON schedule now."
        )
        data = parser.call_llm_json(_SCHEMA_PROMPT, user_prompt)
        try:
            return _GenPlan.model_validate(data)
        except ValidationError as e:
            raise SchedulingError(f"Could not build a valid schedule: {e}") from e

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _to_specs(
        generated: _GenPlan, today: datetime.date, horizon: datetime.date
    ) -> List[wp.SessionSpec]:
        """Convert to specs, dropping anything nonsensical rather than trusting it."""
        valid_kinds = wp.RUN_KINDS | wp.STRENGTH_KINDS | {"rest"}
        specs: List[wp.SessionSpec] = []
        for s in generated.sessions:
            try:
                date = datetime.date.fromisoformat(s.date)
            except (ValueError, TypeError):
                continue
            if date < today or date > horizon:
                continue
            kind = (s.kind or "").strip().lower()
            if kind not in valid_kinds:
                continue
            title = (s.title or "").strip()
            if not title:
                continue
            km = s.distance_km if (s.distance_km or 0) > 0 else None
            minutes = s.duration_minutes if (s.duration_minutes or 0) > 0 else None
            specs.append(wp.SessionSpec(
                kind=kind, title=title, preferred_date=date,
                detail=(s.detail or "").strip(), distance_km=km,
                duration_minutes=minutes, lower_body=bool(s.lower_body),
            ))
        return specs

    # ------------------------------------------------------------------
    # Confirmation
    # ------------------------------------------------------------------

    @staticmethod
    def _confirmation(result: wp.ScheduleResult, written: int) -> str:
        sessions = [p for p in result.placed if p.spec.kind != "rest"]
        if len(sessions) == 1:
            p = sessions[0]
            when = f"{p.date:%A %d %B}"
            time = f" at {p.start_time:%H:%M}" if p.start_time else ""
            message = f"Added {p.spec.title} on {when}{time}."
        else:
            message = f"Scheduled {len(sessions)} sessions — {written} on your calendar."

        # What the rules changed is the part worth saying out loud.
        if result.moves:
            if len(result.moves) == 1:
                message += f" I moved one: {result.moves[0]}."
            else:
                message += f" I moved {len(result.moves)} around the chagim."
        if result.warnings:
            message += f" I couldn't place {len(result.warnings)}."
        return message


# ---------------------------------------------------------------------------
# Config plumbing — shared with scripts/seed_running_plan.py
# ---------------------------------------------------------------------------

def observance_settings(config) -> ob.ObservanceSettings:
    """Build observance settings from config, falling back to the defaults."""
    o = getattr(config, "observance", None)
    if o is None:
        return ob.DEFAULT_SETTINGS
    hh, _, mm = (o.latest_evening or "22:30").partition(":")
    try:
        latest = datetime.time(int(hh), int(mm or 0))
    except ValueError:
        latest = datetime.time(22, 30)
    return ob.ObservanceSettings(
        latitude=o.latitude, longitude=o.longitude, timezone=o.timezone,
        city=o.city, tzeit_depression=o.tzeit_depression,
        candle_lighting_minutes=o.candle_lighting_minutes,
        erev_buffer_minutes=o.erev_buffer_minutes,
        motzei_buffer_minutes=o.motzei_buffer_minutes,
        earliest_hour=o.earliest_hour, latest_evening=latest,
    )


def schedule_policy(config) -> wp.SchedulePolicy:
    o = getattr(config, "observance", None)
    if o is None:
        return wp.SchedulePolicy()
    return wp.SchedulePolicy(
        minor_fast_is_rest_day=o.minor_fast_is_rest_day,
        allow_motzei_fallback=o.allow_motzei_fallback,
    )
