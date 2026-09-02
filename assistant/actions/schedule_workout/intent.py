"""Intent model for the schedule-workout action."""

from __future__ import annotations

from pydantic import field_validator

from assistant.actions.base import BaseIntent


class ScheduleWorkoutIntent(BaseIntent):
    """Free-text description of the training to put on the calendar, e.g.
    'add an easy 8k on Thursday morning' or 'four more weeks of running
    after the time trial, building to a 10k'."""

    request: str

    @field_validator("request")
    @classmethod
    def require_request(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("request cannot be empty")
        return v
