"""Microsoft Graph API client for calendar operations."""

from typing import List

import requests

from assistant.actions.calendar.auth import MSALAuth
from assistant.exceptions import AuthExpiredError, GraphAPIError

BASE_URL = "https://graph.microsoft.com/v1.0"


class GraphClient:
    """HTTP client for Microsoft Graph /me/events endpoint."""

    def __init__(self, auth: MSALAuth) -> None:
        self.auth = auth
        self._session = requests.Session()

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.auth.get_token()}",
            "Content-Type": "application/json",
        }

    def create_event(self, payload: dict) -> dict:
        """
        POST /me/events — create a calendar event.

        Returns the created event dict (includes 'id', 'webLink', etc.).
        """
        resp = self._session.post(
            f"{BASE_URL}/me/events",
            headers=self._headers(),
            json=payload,
            timeout=30,
        )
        self._raise_for_status(resp)
        return resp.json()

    def list_events(self, start: str, end: str) -> List[dict]:
        """
        GET /me/calendarView — list events in a time range.

        Args:
            start, end: ISO 8601 datetime strings.
        """
        resp = self._session.get(
            f"{BASE_URL}/me/calendarView",
            headers=self._headers(),
            params={
                "startDateTime": start,
                "endDateTime": end,
                "$orderby": "start/dateTime",
                "$top": "50",
            },
            timeout=30,
        )
        self._raise_for_status(resp)
        return resp.json().get("value", [])

    def _raise_for_status(self, resp: requests.Response) -> None:
        if resp.status_code == 401:
            raise AuthExpiredError("Graph API returned 401 — token may be expired.")
        if not resp.ok:
            try:
                detail = resp.json().get("error", {}).get("message", resp.text)
            except Exception:
                detail = resp.text
            raise GraphAPIError(f"Graph API {resp.status_code}: {detail}")
