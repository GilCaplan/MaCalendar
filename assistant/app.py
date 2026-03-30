"""macOS menu-bar application (rumps)."""

from __future__ import annotations

import logging
import subprocess
import os

import rumps

from assistant.pipeline import (
    Pipeline,
    STATUS_DONE,
    STATUS_ERROR,
    STATUS_IDLE,
    STATUS_LISTENING,
    STATUS_PROCESSING,
)

logger = logging.getLogger(__name__)

_STATUS_ICONS = {
    STATUS_IDLE: "🎙",
    STATUS_LISTENING: "🔴",
    STATUS_PROCESSING: "⚙️",
    STATUS_DONE: "✅",
    STATUS_ERROR: "⚠️",
}


class AssistantApp(rumps.App):
    """
    Lives in the macOS menu bar.
    - Icon changes to reflect pipeline status.
    - @rumps.timer polls pipeline.status_queue every 100ms (thread-safe).
    """

    def __init__(self, pipeline: Pipeline, config_path: str) -> None:
        super().__init__(_STATUS_ICONS[STATUS_IDLE], quit_button="Quit")
        self._pipeline = pipeline
        self._config_path = config_path

        self.menu = [
            rumps.MenuItem("Status: Idle", callback=None),
            None,  # separator
            rumps.MenuItem("Re-authenticate", callback=self._reauthenticate),
            rumps.MenuItem("Open Settings", callback=self._open_settings),
        ]

    @rumps.timer(0.1)
    def _poll_status(self, _sender) -> None:
        """Drain the pipeline's status queue on the main thread."""
        try:
            while True:
                status = self._pipeline.status_queue.get_nowait()
                icon = _STATUS_ICONS.get(status, "🎙")
                self.title = icon
                self.menu["Status: Idle"].title = f"Status: {status.capitalize()}"
        except Exception:
            pass  # queue.Empty or any other error — nothing to update

    @rumps.clicked("Re-authenticate")
    def _reauthenticate(self, _sender) -> None:
        """Trigger a fresh Microsoft OAuth flow."""
        from assistant.actions.calendar.auth import MSALAuth
        try:
            auth = MSALAuth(self._pipeline.config.microsoft)
            auth.force_reauth()
            rumps.notification(
                "Voice Assistant",
                "Authentication successful",
                "Microsoft account linked.",
            )
        except Exception as e:
            logger.error("Re-auth failed: %s", e)
            rumps.notification(
                "Voice Assistant",
                "Authentication failed",
                str(e),
            )

    @rumps.clicked("Open Settings")
    def _open_settings(self, _sender) -> None:
        """Open config.yaml in the default editor."""
        subprocess.run(["open", self._config_path])
