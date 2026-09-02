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

    @field_validator("recur_until", "recurrence", "date", "start_time", "end_time",
                     "location", "description", mode="before")
    @classmethod
    def coerce_null_strings(cls, v: Any) -> Any:
        """Treat the literal string 'null' or 'none' as a missing value."""
        if isinstance(v, str) and v.strip().lower() in ("null", "none", ""):
            return None
        return v

    @field_validator("recurrence", mode="after")
    @classmethod
    def recurrence_known(cls, v: Any) -> Any:
        """Only daily/weekly/monthly; LLM noise ('unknown', 'none', 'once', 'every monday') → None/weekly."""
        if v is None:
            return None
        sv = str(v).strip().lower()
        if sv in ("daily", "weekly", "monthly"):
            return sv
        if "day" in sv and "week" not in sv and "mon" not in sv:
            return "daily"
        if "week" in sv or any(d in sv for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")):
            return "weekly"
        if "month" in sv:
            return "monthly"
        return None

    @field_validator("date", "recur_until", mode="after")
    @classmethod
    def date_must_be_iso(cls, v: Any) -> Any:
        """Only ISO dates survive. Junk the LLM sometimes emits ('unknown', 'tbd',
        'this Friday', a placeholder) becomes None — the server's sanity pass then
        resolves relative dates from the transcript — rather than failing the command."""
        if v is None:
            return None
        import re as _re
        sv = str(v).strip()
        if _re.fullmatch(r"\d{4}-\d{2}-\d{2}", sv):
            return sv
        m = _re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[T ].*)?", sv)   # 2026-8-5, 2026-08-05T10:00
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        return None

    @field_validator("start_time", "end_time", mode="after")
    @classmethod
    def time_must_be_hhmm(cls, v: Any) -> Any:
        """Normalise '9 AM', '12:00 PM', '9.30pm', '0915', '230pm' → 'HH:MM'.

        The compact-with-meridiem form is what speech recognition actually
        hands back: "today at 2:30PM" is transcribed "at 230PM", and both
        '230pm' and '1130am' used to raise here. The colon is the only thing
        the older patterns had to find the minutes by, so '230pm' backtracked
        to nothing and the whole parse was thrown away.

        A meridiem is required for that third form on purpose. Bare '230' is
        genuinely ambiguous — 2:30, or 02:30 written badly — and the existing
        four-digit rule already reads '0230'. Guessing between them is how you
        get an event at the wrong time of day.
        """
        if v is None:
            return None
        import re as _re
        t = str(v).strip().lower().replace(".", ":")
        m = (_re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm|a:m|p:m)?", t)
             or _re.fullmatch(r"(\d{2})(\d{2})()", t)
             or _re.fullmatch(r"(\d{1,2})(\d{2})\s*(am|pm|a:m|p:m)", t))
        if not m:
            raise ValueError(f"time must be HH:MM, got {v!r}")
        h, mm, ap = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").replace(":", "")
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
        if h > 23 or mm > 59:
            raise ValueError(f"time out of range: {v!r}")
        return f"{h:02d}:{mm:02d}"

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
    # A specific day, when one was named. scope could only say today, tomorrow
    # or week, so "what do I have on friday" had nowhere to put "friday" and
    # fell back to the default — answering confidently about the wrong day.
    # When this is set it wins over scope.
    date: Optional[str] = None  # YYYY-MM-DD
