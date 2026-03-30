"""Calendar voice actions — create, update, and delete events."""

from typing import ClassVar, List, Optional, Type

from assistant.actions import register
from assistant.actions.base import BaseAction, BaseIntent
from assistant.actions.calendar.intent import CalendarIntent, DeleteEventIntent, UpdateEventIntent


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
            "match_title": {"type": "string", "description": "Title (or partial title) of the event to find. Or 'it'."},
            "match_date": {"type": "string", "description": "ISO 8601 date to narrow the search. Optional."},
            "new_title": {"type": "string", "description": "Replacement title. Omit if unchanged."},
            "new_date": {"type": "string", "description": "New ISO 8601 date. Omit if unchanged."},
            "new_start_time": {"type": "string", "description": "New start time HH:MM. Omit if unchanged."},
            "new_end_time": {"type": "string", "description": "New end time HH:MM. Omit if unchanged."},
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
            "match_title": {"type": "string", "description": "Title of the event to delete. Or 'it'."},
            "match_date": {"type": "string", "description": "ISO 8601 date to narrow the search. Optional."},
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
# Internal helper
# ---------------------------------------------------------------------------

def _find_event(db, match_title: str, match_date: Optional[str]) -> Optional[dict]:
    """
    Find the best-matching event by title and optional date.
    Implements token-based fuzzy matching to handle LLM trailing words.
    Resolves anaphoric pronouns via global memory bounds.
    """
    global _last_event_id
    import datetime as dt
    import re
    
    # Check for pronoun reference
    if match_title.lower() in _ANAPHORS:
        if _last_event_id is not None:
            with db._conn() as conn:
                row = conn.execute("SELECT * FROM events WHERE id = ?", (_last_event_id,)).fetchone()
            if row:
                return dict(row)
        return None

    # Tokenize the search needle into a set of words
    needle_words = set(re.findall(r'\w+', match_title.lower()))
    today = dt.date.today().isoformat()

    with db._conn() as conn:
        if match_date:
            rows = conn.execute(
                "SELECT * FROM events WHERE date = ? ORDER BY start_time",
                (match_date,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM events WHERE date >= ? ORDER BY date ASC, start_time ASC",
                (today,),
            ).fetchall()
            if not rows:
                rows = conn.execute(
                    "SELECT * FROM events WHERE date < ? ORDER BY date DESC, start_time DESC",
                    (today,),
                ).fetchall()

    best_match = None
    best_score = 0
    
    for row in rows:
        row_dict = dict(row)
        title_words = set(re.findall(r'\w+', row_dict["title"].lower()))
        
        # Check intersection score (how many target words exist in the event title)
        overlap = len(needle_words.intersection(title_words))
        
        # Or if the event title is a strict substring of the needle (e.g. "daily stand-up end" contains "daily standup")
        # Removing dashes for safe comparisons
        clean_needle = match_title.lower().replace("-", " ")
        clean_title = row_dict["title"].lower().replace("-", " ")
        
        if clean_title in clean_needle or clean_needle in clean_title:
            overlap += 10  # Massive score boost for substring match
            
        if overlap > best_score:
            best_score = overlap
            best_match = row_dict

    return best_match if best_score > 0 else None
