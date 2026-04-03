import datetime
import json
from typing import Any, List, Optional

from pydantic import field_validator, model_validator

from assistant.actions.base import BaseIntent


class CalendarIntent(BaseIntent):
    title: str
    date: Optional[str] = None            # ISO 8601 date, e.g. "2026-04-01"
    start_time: Optional[str] = None      # 24-hour "HH:MM"
    end_time: Optional[str] = None        # 24-hour "HH:MM"
    attendees: List[str] = []             # names or email addresses
    location: Optional[str] = None
    description: Optional[str] = None
    recurrence: Optional[str] = None      # 'daily', 'weekly', 'monthly'
    recur_until: Optional[str] = None     # ISO 8601 date, e.g. "2026-12-31"

    @field_validator("title", mode="before")
    @classmethod
    def title_required(cls, v: Any) -> str:
        if not v or not str(v).strip():
            raise ValueError("Event title cannot be empty")
        return str(v).strip()

    @model_validator(mode="after")
    def fill_defaults(self) -> "CalendarIntent":
        """Fill in missing date and time fields with sensible defaults."""
        # 1. Date defaults to today
        if not self.date:
            self.date = datetime.date.today().isoformat()

        # 2. Start time defaults to current hour if missing
        if not self.start_time:
            now = datetime.datetime.now()
            self.start_time = f"{now.hour:02d}:00"

        # 3. End time defaults to start_time + 1 hour
        if not self.end_time:
            try:
                h, m = map(int, self.start_time.split(":"))
                end_min = h * 60 + m + 60
                # Cap at end of day
                if end_min >= 24 * 60:
                    self.end_time = "23:59"
                else:
                    self.end_time = f"{end_min // 60:02d}:{end_min % 60:02d}"
            except Exception:
                # If start_time was mangled, just mirror it
                self.end_time = self.start_time
        return self

    @field_validator("attendees", mode="before")
    @classmethod
    def parse_attendees(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass
            return [str(x).strip() for x in v.split(",") if x.strip()]
        return v


class UpdateEventIntent(BaseIntent):
    """Intent for updating an existing event — match by title and/or date/time, then patch fields."""
    match_title: Optional[str] = None    # event name; may be omitted when time uniquely identifies it
    match_date: Optional[str] = None     # narrow by date if provided
    match_start_time: Optional[str] = None  # narrow by time if provided
    new_title: Optional[str] = None
    new_date: Optional[str] = None
    new_start_time: Optional[str] = None
    new_end_time: Optional[str] = None
    new_location: Optional[str] = None
    new_description: Optional[str] = None

    @model_validator(mode="after")
    def require_title_or_time(self) -> "UpdateEventIntent":
        if not self.match_title and not self.match_start_time:
            raise ValueError("Either match_title or match_start_time must be provided")
        return self


class DeleteEventIntent(BaseIntent):
    """Intent for deleting an existing event — match by title and/or date/time."""
    match_title: Optional[str] = None    # event name; may be omitted when time uniquely identifies it
    match_date: Optional[str] = None     # narrow by date if provided
    match_start_time: Optional[str] = None  # narrow by time if provided

    @model_validator(mode="after")
    def require_title_or_time(self) -> "DeleteEventIntent":
        if not self.match_title and not self.match_start_time:
            raise ValueError("Either match_title or match_start_time must be provided")
        return self


class QueryScheduleIntent(BaseIntent):
    """Intent for querying and reading out the user's schedule."""
    scope: str = "today"        # "today" | "tomorrow" | "week"
    query_type: str = "full"    # "full" | "first" | "next" | "count"
