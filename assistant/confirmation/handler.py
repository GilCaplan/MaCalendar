"""Confirmation dialogs via native macOS osascript."""

from __future__ import annotations

import re
import subprocess
from typing import Optional

from assistant.actions.base import BaseIntent
from assistant.actions.calendar.intent import CalendarIntent, DeleteEventIntent, UpdateEventIntent


class ConfirmationHandler:
    """
    Shows native macOS confirmation dialogs before actions are executed.

    Confirmation levels:
        0 — fully autonomous, no dialogs
        1 — simple yes/no
        2 — full event details shown
        3 — field-by-field review with optional inline editing
    """

    def __init__(self, level: int) -> None:
        self.level = level

    def check(self, action_name: str, intent: BaseIntent) -> bool:
        """Return True if the action should proceed, False if cancelled."""
        if self.level == 0:
            return True

        if isinstance(intent, DeleteEventIntent):
            return self._confirm_delete(intent)

        if isinstance(intent, UpdateEventIntent):
            return self._confirm_update(intent)

        if isinstance(intent, CalendarIntent):
            return self._confirm_calendar(intent)

        return self._confirm_generic(action_name, intent)

    # ------------------------------------------------------------------
    # Create confirmation
    # ------------------------------------------------------------------

    def _confirm_calendar(self, intent: CalendarIntent) -> bool:
        recur_text = f" (Repeats {intent.recurrence})" if getattr(intent, "recurrence", None) else ""
        if self.level == 1:
            msg = (
                f"Create event: '{intent.title}'{recur_text}\\n"
                f"Date: {intent.date}\\n"
                f"Time: {intent.start_time} – {intent.end_time}"
            )
            return self._osascript_confirm(msg, confirm_button="Create")

        if self.level == 2:
            lines = [
                f"Title: {intent.title}",
                f"Date: {intent.date}",
                f"Time: {intent.start_time} – {intent.end_time}",
            ]
            if getattr(intent, "recurrence", None):
                r_end = f" until {intent.recur_until}" if getattr(intent, "recur_until", None) else ""
                lines.append(f"Repeats: {intent.recurrence}{r_end}")
            if intent.attendees:
                lines.append(f"Attendees: {', '.join(intent.attendees)}")
            if intent.location:
                lines.append(f"Location: {intent.location}")
            msg = "Create this event?\\n\\n" + "\\n".join(lines)
            return self._osascript_confirm(msg, confirm_button="Create")

        if self.level == 3:
            return self._confirm_calendar_step_by_step(intent)

        return True

    def _confirm_calendar_step_by_step(self, intent: CalendarIntent) -> bool:
        """Let the user review and optionally edit each field."""
        fields = [
            ("Event title", "title"),
            ("Date (YYYY-MM-DD)", "date"),
            ("Start time (HH:MM)", "start_time"),
            ("End time (HH:MM)", "end_time"),
        ]
        for label, attr in fields:
            current = str(getattr(intent, attr))
            new_val = self._osascript_editable_field(label, current)
            if new_val is None:
                return False
            setattr(intent, attr, new_val)
        return True

    # ------------------------------------------------------------------
    # Update confirmation
    # ------------------------------------------------------------------

    def _confirm_update(self, intent: UpdateEventIntent) -> bool:
        lines = [f"Find event matching: '{intent.match_title}'"]
        if intent.match_date:
            lines.append(f"On date: {intent.match_date}")
        lines.append("")
        lines.append("Apply changes:")
        if intent.new_title:      lines.append(f"  Title → {intent.new_title}")
        if intent.new_date:       lines.append(f"  Date → {intent.new_date}")
        if intent.new_start_time: lines.append(f"  Start → {intent.new_start_time}")
        if intent.new_end_time:   lines.append(f"  End → {intent.new_end_time}")
        if intent.new_location:   lines.append(f"  Location → {intent.new_location}")
        if intent.new_description: lines.append(f"  Notes → {intent.new_description}")
        msg = "Update this event?\\n\\n" + "\\n".join(lines)
        return self._osascript_confirm(msg, confirm_button="Update")

    # ------------------------------------------------------------------
    # Delete confirmation — always shown regardless of level (safety)
    # ------------------------------------------------------------------

    def _confirm_delete(self, intent: DeleteEventIntent) -> bool:
        """Always confirm deletes — even at level 0 a delete is shown."""
        lines = [
            f"⚠️ Delete event matching: '{intent.match_title}'",
        ]
        if intent.match_date:
            lines.append(f"On: {intent.match_date}")
        lines.append("")
        lines.append("This cannot be undone.")
        msg = "\\n".join(lines)
        return self._osascript_confirm(msg, confirm_button="Delete")

    # ------------------------------------------------------------------
    # Generic fallback
    # ------------------------------------------------------------------

    def _confirm_generic(self, action_name: str, intent: BaseIntent) -> bool:
        msg = f"Run action: {action_name}?"
        return self._osascript_confirm(msg, confirm_button="Proceed")

    # ------------------------------------------------------------------
    # osascript helpers
    # ------------------------------------------------------------------

    def _osascript_confirm(self, message: str, confirm_button: str = "OK") -> bool:
        script = (
            f'display dialog "{message}" '
            f'buttons ["Cancel", "{confirm_button}"] '
            f'default button "{confirm_button}"'
        )
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0 and confirm_button in result.stdout

    def _osascript_editable_field(self, label: str, default: str) -> Optional[str]:
        safe_default = default.replace('"', "'")
        script = (
            f'display dialog "{label}:" '
            f'default answer "{safe_default}" '
            f'buttons ["Cancel", "OK"] default button "OK"'
        )
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        match = re.search(r"text returned:(.*)", result.stdout)
        return match.group(1).strip() if match else default
