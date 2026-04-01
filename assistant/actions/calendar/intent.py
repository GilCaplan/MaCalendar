from typing import List, Optional, Any
import json
from pydantic import field_validator, model_validator

from assistant.actions.base import BaseIntent


class CalendarIntent(BaseIntent):
    title: str
    date: str                        # ISO 8601 date, e.g. "2026-04-01"
    start_time: str                  # 24-hour "HH:MM"
    end_time: str                    # 24-hour "HH:MM"
    attendees: List[str] = []        # names or email addresses
    location: Optional[str] = None
    description: Optional[str] = None
    recurrence: Optional[str] = None         # 'daily', 'weekly', 'monthly'
    recur_until: Optional[str] = None        # ISO 8601 date, e.g. "2026-12-31"

    @field_validator("title", mode="before")
    @classmethod
    def title_required(cls, v: Any) -> str:
        if not v or not str(v).strip():
            raise ValueError("Event title cannot be empty")
        return str(v).strip()

    @model_validator(mode="after")
    def fix_end_time(self) -> "CalendarIntent":
        """Default end_time to start_time + 1 hour when the LLM omits it."""
        if not self.end_time and self.start_time:
            try:
                h, m = map(int, self.start_time.split(":"))
                end_min = h * 60 + m + 60
                self.end_time = f"{min(end_min // 60, 23):02d}:{end_min % 60:02d}"
            except Exception:
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
    """Intent for updating an existing event — match by title + date, then patch fields."""
    match_title: str                 # title to search for (fuzzy match)
    match_date: Optional[str] = None # narrow by date if provided
    new_title: Optional[str] = None
    new_date: Optional[str] = None
    new_start_time: Optional[str] = None
    new_end_time: Optional[str] = None
    new_location: Optional[str] = None
    new_description: Optional[str] = None


class DeleteEventIntent(BaseIntent):
    """Intent for deleting an existing event — match by title + optional date."""
    match_title: str
    match_date: Optional[str] = None  # narrow by date if provided


class QueryScheduleIntent(BaseIntent):
    """Intent for querying and reading out the user's schedule."""
    scope: str = "today"        # "today" | "tomorrow" | "week"
    query_type: str = "full"    # "full" | "first" | "next" | "count"
