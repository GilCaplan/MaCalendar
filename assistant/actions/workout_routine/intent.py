"""Intent model for the auto-generate-workout-routine action."""

from __future__ import annotations

from pydantic import field_validator

from assistant.actions.base import BaseIntent


class GenerateWorkoutRoutineIntent(BaseIntent):
    """Free-text goal describing the routine the user wants generated,
    e.g. 'give me a 3-day push pull legs hypertrophy split'."""

    goal: str

    @field_validator("goal")
    @classmethod
    def require_goal(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("goal cannot be empty")
        return v
