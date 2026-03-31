"""Calendar voice actions — create, update, and delete events."""

from typing import ClassVar, List, Optional, Type

from assistant.actions import register
from assistant.actions.base import BaseAction, BaseIntent
from assistant.actions.calendar.intent import CalendarIntent, DeleteEventIntent, QueryScheduleIntent, UpdateEventIntent


# Global memory to remember the most recently created or modified event
_last_event_id: Optional[int] = None

# Anaphoric pronouns that trigger the memory fallback
_ANAPHORS = {"it", "that", "this", "this event", "that event", "the last one", "the last event", "the event"}

# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

@register
class CreateEventAction(BaseAction):
    action_name: ClassVar[str] = "create_event"
    description: ClassVar[str] = (
        "Schedule or add a new event to the calendar. Triggers on phrases like "
        "'schedule a meeting', 'add an event', 'remind me to', 'set up a call'."
    )
    intent_model: ClassVar[Type[BaseIntent]] = CalendarIntent
    parameters_schema: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Short, clear title of the event."},
            "date": {"type": "string", "description": "ISO 8601 date, e.g. YYYY-MM-DD."},
            "start_time": {"type": "string", "description": "24-hour HH:MM formatted start time."},
            "end_time": {"type": "string", "description": "24-hour HH:MM formatted end time."},
            "attendees": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of names or emails attending.",
            },
            "location": {"type": "string", "description": "Meeting link, room, or location address."},
            "description": {"type": "string", "description": "Detailed notes or agenda."},
            "recurrence": {"type": "string", "description": "Optional: 'daily', 'weekly', or 'monthly'"},
            "recur_until": {"type": "string", "description": "Optional: ISO 8601 end date for recurrence"},
        },
        "required": ["title", "date", "start_time", "end_time"],
    }

    def execute(self, intent: CalendarIntent, _config) -> str:  # type: ignore[override]
        """
        Save the event to the local SQLite database.
        """
        global _last_event_id
        
        from assistant.db import CalendarDB
        db = CalendarDB()

        from assistant.calendar_ui.styles import BLUE
        event_id = db.create_event(intent, color=BLUE)
        
        # Cache the ID so the user can say "Delete it" in their next breath
        _last_event_id = event_id

        if intent.recurrence:
            return f"Created recurring {intent.recurrence} event '{intent.title}' starting on {intent.date}."
        return f"Created event '{intent.title}' on {intent.date} from {intent.start_time} to {intent.end_time}."


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

@register
class UpdateEventAction(BaseAction):
    action_name: ClassVar[str] = "update_event"
    description: ClassVar[str] = (
        "Modify an existing calendar event. Triggers on phrases like "
        "'move my meeting', 'reschedule', 'change the time of', 'rename', "
        "'update my appointment', 'shift the standup'. If modifying the last interacted event, title may be 'it'."
    )
    intent_model: ClassVar[Type[BaseIntent]] = UpdateEventIntent
    parameters_schema: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "match_title": {"type": "string", "description": "The event title ONLY — just the name words (e.g. 'dentist', 'standup', 'team sync'). Do NOT include 'my', 'the', 'meeting', dates, or other context words. Use 'it' to refer to the last created/modified event."},
            "match_date": {"type": "string", "description": "ISO 8601 date of the event to help narrow the search. Only provide if you are confident about the date; omit if unsure."},
            "new_title": {"type": "string", "description": "Replacement title. Omit if unchanged."},
            "new_date": {"type": "string", "description": "New ISO 8601 date. Omit if unchanged."},
            "new_start_time": {"type": "string", "description": "New start time HH:MM. Omit if unchanged."},
            "new_end_time": {"type": "string", "description": "New end time HH:MM. Omit if unchanged. Duration is preserved automatically when only start time changes."},
            "new_location": {"type": "string", "description": "New location. Omit if unchanged."},
            "new_description": {"type": "string", "description": "New notes. Omit if unchanged."},
        },
        "required": ["match_title"],
    }

    def execute(self, intent: UpdateEventIntent, _config) -> str:  # type: ignore[override]
        global _last_event_id
        from assistant.db import CalendarDB
        db = CalendarDB()

        event = _find_event(db, intent.match_title, intent.match_date)
        if event is None:
            if intent.match_title.lower() in _ANAPHORS:
                return "I can't do that. I don't remember the last event."
            return f"I couldn't find an event matching '{intent.match_title}'."

        updates: dict = {}
        if intent.new_title:      updates["title"] = intent.new_title
        if intent.new_date:       updates["date"] = intent.new_date
        if intent.new_start_time: updates["start_time"] = intent.new_start_time
        if intent.new_end_time:   updates["end_time"] = intent.new_end_time
        if intent.new_location:   updates["location"] = intent.new_location
        if intent.new_description: updates["description"] = intent.new_description

        # Preserve original duration when only the start time changes
        if "start_time" in updates and "end_time" not in updates:
            try:
                orig_sh, orig_sm = map(int, event["start_time"].split(":"))
                orig_eh, orig_em = map(int, event["end_time"].split(":"))
                duration_min = (orig_eh * 60 + orig_em) - (orig_sh * 60 + orig_sm)
                if duration_min > 0:
                    new_sh, new_sm = map(int, updates["start_time"].split(":"))
                    end_min = min(new_sh * 60 + new_sm + duration_min, 23 * 60 + 59)
                    updates["end_time"] = f"{end_min // 60:02d}:{end_min % 60:02d}"
            except Exception:
                pass

        if not updates:
            return f"No changes specified for '{event['title']}'."

        db.update_event(event["id"], **updates)
        _last_event_id = event["id"]

        display = updates.get("title", event["title"])
        return f"Updated '{display}' successfully."


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

@register
class DeleteEventAction(BaseAction):
    action_name: ClassVar[str] = "delete_event"
    description: ClassVar[str] = (
        "Remove a calendar event. Triggers on phrases like "
        "'cancel my meeting', 'delete the appointment', 'delete it'."
    )
    intent_model: ClassVar[Type[BaseIntent]] = DeleteEventIntent
    parameters_schema: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "match_title": {"type": "string", "description": "The event title ONLY — just the name words (e.g. 'dentist', 'standup'). Do NOT include 'my', 'the', 'meeting', dates, or surrounding context. Use 'it' to refer to the last event."},
            "match_date": {"type": "string", "description": "ISO 8601 date of the event to help narrow the search. Only provide if you are confident about the date; omit if unsure."},
        },
        "required": ["match_title"],
    }

    def execute(self, intent: DeleteEventIntent, _config) -> str:  # type: ignore[override]
        global _last_event_id
        from assistant.db import CalendarDB
        db = CalendarDB()

        event = _find_event(db, intent.match_title, intent.match_date)
        if event is None:
            if intent.match_title.lower() in _ANAPHORS:
                return "I can't do that. I don't remember the last event."
            return f"I couldn't find an event matching '{intent.match_title}'."

        db.delete_event(event["id"])
        _last_event_id = None
        return f"Deleted '{event['title']}' from your calendar."


# ---------------------------------------------------------------------------
# Query Schedule
# ---------------------------------------------------------------------------

@register
class QueryScheduleAction(BaseAction):
    action_name: ClassVar[str] = "query_schedule"
    view_switch: ClassVar[str] = "switch_today"
    description: ClassVar[str] = (
        "Query and read out the user's schedule. Triggers on phrases like "
        "'what does my day look like', 'what's on my schedule', 'when is my first meeting', "
        "'how many events do I have today', 'read my schedule', 'what's next'."
    )
    intent_model: ClassVar[Type[BaseIntent]] = QueryScheduleIntent
    parameters_schema: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "scope": {
                "type": "string",
                "enum": ["today", "tomorrow", "week"],
                "description": "Time range to query. Default: 'today'.",
            },
            "query_type": {
                "type": "string",
                "enum": ["full", "first", "next", "count"],
                "description": (
                    "'full' = read all events, 'first' = first event only, "
                    "'next' = next upcoming event, 'count' = how many events."
                ),
            },
        },
        "required": [],
    }

    def execute(self, intent: QueryScheduleIntent, _config) -> str:  # type: ignore[override]
        import datetime as dt
        from assistant.db import CalendarDB
        db = CalendarDB()

        today = dt.date.today()
        if intent.scope == "tomorrow":
            target_date = today + dt.timedelta(days=1)
            day_label = "tomorrow"
        elif intent.scope == "week":
            day_label = "this week"
        else:
            target_date = today
            day_label = "today"

        if intent.scope == "week":
            week_start = today - dt.timedelta(days=today.weekday())
            events = db.get_events_for_week(week_start)
        else:
            events = db.get_events_for_day(target_date)

        events = sorted(events, key=lambda e: e.get("start_time", ""))
        n = len(events)

        if intent.query_type == "count":
            if n == 0:
                return f"You have no events {day_label}."
            return f"You have {n} event{'s' if n != 1 else ''} {day_label}."

        if n == 0:
            return f"Your schedule is clear {day_label}. Nothing planned."

        if intent.query_type == "first":
            ev = events[0]
            return f"Your first event {day_label} is {ev['title']} at {_fmt_time(ev.get('start_time', ''))}."

        if intent.query_type == "next":
            now_time = dt.datetime.now().strftime("%H:%M")
            upcoming = [e for e in events if e.get("start_time", "") >= now_time]
            if not upcoming:
                return f"No more events for {day_label}."
            ev = upcoming[0]
            return f"Your next event is {ev['title']} at {_fmt_time(ev.get('start_time', ''))}."

        # "full" — read the whole schedule
        if n == 1:
            ev = events[0]
            return (
                f"You have one event {day_label}: "
                f"{ev['title']} at {_fmt_time(ev.get('start_time', ''))}."
            )

        parts = [
            f"{ev['title']} at {_fmt_time(ev.get('start_time', ''))}"
            for ev in events
        ]
        # Oxford-style list
        if len(parts) == 2:
            schedule = f"{parts[0]} and {parts[1]}"
        else:
            schedule = ", ".join(parts[:-1]) + f", and {parts[-1]}"
        return f"You have {n} events {day_label}: {schedule}."


def _fmt_time(time_str: str) -> str:
    """Convert '14:30' → '2:30 PM'."""
    try:
        h, m = map(int, time_str.split(":"))
        period = "AM" if h < 12 else "PM"
        h12 = h % 12 or 12
        return f"{h12}:{m:02d} {period}" if m else f"{h12} {period}"
    except Exception:
        return time_str


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

_STOP_WORDS = {
    "a", "an", "the", "my", "i", "of", "to", "in", "on", "at", "for",
    "it", "is", "be", "was", "and", "or", "that", "this",
}


def _find_event(db, match_title: str, match_date: Optional[str]) -> Optional[dict]:
    """
    Find the best-matching event by title and optional date.
    Implements token-based fuzzy matching with stop-word filtering.
    Resolves anaphoric pronouns via global memory.
    """
    global _last_event_id
    import datetime as dt
    import re

    # Anaphor resolution
    if match_title.lower() in _ANAPHORS:
        if _last_event_id is not None:
            with db._conn() as conn:
                row = conn.execute("SELECT * FROM events WHERE id = ?", (_last_event_id,)).fetchone()
            if row:
                return dict(row)
        return None

    today = dt.date.today().isoformat()

    # Strip stop words from the needle so common calendar words don't pollute scores.
    # Keep at least the full needle if stripping leaves nothing.
    raw_needle_words = set(re.findall(r'\w+', match_title.lower()))
    needle_words = raw_needle_words - _STOP_WORDS
    if not needle_words:
        needle_words = raw_needle_words

    def _score(row_dict: dict) -> int:
        title_words = set(re.findall(r'\w+', row_dict["title"].lower()))
        overlap = len(needle_words.intersection(title_words))

        # Substring boost: normalise dashes/underscores before comparing
        clean_needle = re.sub(r'[-_]', '', match_title.lower())
        clean_title  = re.sub(r'[-_]', '', row_dict["title"].lower())
        if clean_title in clean_needle or clean_needle in clean_title:
            overlap += 10

        return overlap

    with db._conn() as conn:
        if match_date:
            rows = conn.execute(
                "SELECT * FROM events WHERE date = ? ORDER BY start_time",
                (match_date,),
            ).fetchall()
            rows = [dict(r) for r in rows]
            # If the LLM gave a wrong date, fall back to all events
            if not rows:
                rows = conn.execute(
                    "SELECT * FROM events ORDER BY ABS(julianday(date) - julianday(?)), start_time",
                    (today,),
                ).fetchall()
                rows = [dict(r) for r in rows]
        else:
            # Search ALL events ordered by proximity to today so upcoming events
            # win ties over distant past/future ones.
            rows = conn.execute(
                "SELECT * FROM events ORDER BY ABS(julianday(date) - julianday(?)), start_time",
                (today,),
            ).fetchall()
            rows = [dict(r) for r in rows]

    best_match = None
    best_score = 0
    for row_dict in rows:
        s = _score(row_dict)
        if s > best_score:
            best_score = s
            best_match = row_dict

    return best_match if best_score > 0 else None
