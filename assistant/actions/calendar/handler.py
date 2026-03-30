"""High-level calendar handler — orchestrates auth, building, and API call."""

import datetime

from assistant.actions.calendar.auth import MSALAuth
from assistant.actions.calendar.event_builder import build_event_payload
from assistant.actions.calendar.graph_client import GraphClient
from assistant.actions.calendar.intent import CalendarIntent
from assistant.config import AppConfig


def get_local_timezone() -> str:
    """Return the local IANA timezone string."""
    try:
        import zoneinfo
        return str(datetime.datetime.now().astimezone().tzinfo)
    except Exception:
        return "UTC"


class CalendarHandler:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._auth = MSALAuth(config.microsoft)
        self._client = GraphClient(self._auth)

    def create_event(self, intent: CalendarIntent) -> dict:
        """Build payload and create the event. Returns the raw Graph API response."""
        tz = get_local_timezone()
        payload = build_event_payload(intent, tz)
        return self._client.create_event(payload)

    @property
    def auth(self) -> MSALAuth:
        return self._auth
