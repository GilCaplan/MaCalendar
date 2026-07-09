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

    def update_event(self, event_id: str, payload: dict) -> dict:
        """PATCH /me/events/{id} — update an existing Outlook event."""
        resp = self._session.patch(
            f"{BASE_URL}/me/events/{event_id}",
            headers=self._headers(),
            json=payload,
            timeout=30,
        )
        self._raise_for_status(resp)
        return resp.json()

    def delete_event(self, event_id: str) -> None:
        """DELETE /me/events/{id}. A 404 (already gone) is treated as success
        so retried deletes after an unconfirmed prior success don't raise."""
        resp = self._session.delete(
            f"{BASE_URL}/me/events/{event_id}",
            headers=self._headers(),
            timeout=30,
        )
        if resp.status_code == 404:
            return
        self._raise_for_status(resp)

    def list_events(self, start: str, end: str, max_pages: int = 20) -> List[dict]:
        """
        GET /me/calendarView — list events in a time range, following
        @odata.nextLink so a busy calendar's events past the first page
        aren't silently treated as "not returned = deleted" by callers that
        reconcile against this list (see calendar_sync/outlook_sync.py).

        Args:
            start, end: ISO 8601 datetime strings.
            max_pages: safety cap (each page holds up to 100 events) so a
                pathological/huge calendar can't loop indefinitely.
        """
        events: List[dict] = []
        resp = self._session.get(
            f"{BASE_URL}/me/calendarView",
            headers=self._headers(),
            params={
                "startDateTime": start,
                "endDateTime": end,
                "$orderby": "start/dateTime",
                "$top": "100",
            },
            timeout=30,
        )
        self._raise_for_status(resp)
        body = resp.json()
        events.extend(body.get("value", []))
        next_link = body.get("@odata.nextLink")

        pages = 1
        while next_link and pages < max_pages:
            resp = self._session.get(next_link, headers=self._headers(), timeout=30)
            self._raise_for_status(resp)
            body = resp.json()
            events.extend(body.get("value", []))
            next_link = body.get("@odata.nextLink")
            pages += 1

        return events

    def _raise_for_status(self, resp: requests.Response) -> None:
        if resp.status_code == 401:
            raise AuthExpiredError("Graph API returned 401 — token may be expired.")
        if not resp.ok:
            try:
                detail = resp.json().get("error", {}).get("message", resp.text)
            except Exception:
                detail = resp.text
            raise GraphAPIError(f"Graph API {resp.status_code}: {detail}")
