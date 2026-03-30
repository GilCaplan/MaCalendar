"""Convert a CalendarIntent into a Microsoft Graph API event payload."""

import datetime

from assistant.actions.calendar.intent import CalendarIntent
from assistant.exceptions import EventBuildError


def build_event_payload(intent: CalendarIntent, timezone: str) -> dict:
    """
    Build the JSON payload for POST /me/events.

    Args:
        intent: Validated CalendarIntent from the LLM.
        timezone: IANA timezone string, e.g. "America/New_York".

    Returns:
        dict ready to be sent as JSON to Microsoft Graph.
    """
    try:
        start_dt = datetime.datetime.fromisoformat(f"{intent.date}T{intent.start_time}:00")
        end_dt = datetime.datetime.fromisoformat(f"{intent.date}T{intent.end_time}:00")
    except ValueError as e:
        raise EventBuildError(f"Invalid date/time in intent: {e}") from e

    if end_dt <= start_dt:
        # Assume it wraps to the next day (e.g. cross-midnight event)
        end_dt += datetime.timedelta(days=1)

    payload: dict = {
        "subject": intent.title,
        "start": {
            "dateTime": start_dt.isoformat(),
            "timeZone": timezone,
        },
        "end": {
            "dateTime": end_dt.isoformat(),
            "timeZone": timezone,
        },
    }

    if intent.attendees:
        payload["attendees"] = [
            {
                "emailAddress": {
                    "name": attendee,
                    # Email is left blank if only a name was given.
                    # Graph accepts this but won't send invite emails without an address.
                    "address": attendee if "@" in attendee else "",
                },
                "type": "required",
            }
            for attendee in intent.attendees
        ]

    if intent.location:
        payload["location"] = {"displayName": intent.location}

    if intent.description:
        payload["body"] = {"contentType": "text", "content": intent.description}

    return payload
