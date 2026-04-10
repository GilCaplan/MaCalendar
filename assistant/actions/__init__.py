"""ActionRegistry — singleton that maps action names to handler classes."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Type

if TYPE_CHECKING:
    from assistant.actions.base import BaseAction


class ActionRegistry:
    """
    Borg singleton: all instances share state.
    Actions self-register via the @register decorator when their module is imported.
    """

    _shared_state: dict = {"_actions": {}}

    def __init__(self) -> None:
        self.__dict__ = self._shared_state

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, action_cls: Type[BaseAction]) -> Type[BaseAction]:
        """Register an action class. Can be used as a decorator or called directly."""
        name = action_cls.action_name
        if name in self._actions:
            raise ValueError(
                f"Action '{name}' is already registered by {self._actions[name]}."
            )
        self._actions[name] = action_cls
        return action_cls

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, action_name: str) -> Type[BaseAction] | None:
        return self._actions.get(action_name)

    def all_names(self) -> list[str]:
        return list(self._actions.keys())

    # ------------------------------------------------------------------
    # Prompt / schema construction (called by IntentParser at startup)
    # ------------------------------------------------------------------

    def build_system_prompt(self, today: str, timezone: str) -> str:
        """
        Dynamically build the Ollama system prompt from all registered actions.
        Adding a new action automatically teaches the LLM about it.
        """
        import datetime
        today_dt = datetime.date.fromisoformat(today)
        day_name = today_dt.strftime("%A")  # e.g. "Tuesday"

        # Build 14-day reference so the LLM can resolve relative dates accurately.
        # Days 0-6 are labelled "this [Day]" (or today/tomorrow), days 7-13 "next [Day]".
        this_week = []
        next_week = []
        for i in range(14):
            d = today_dt + datetime.timedelta(days=i)
            if i == 0:
                label = f"today ({day_name})"
            elif i == 1:
                label = f"tomorrow ({d.strftime('%A')})"
            elif i <= 6:
                label = f"this {d.strftime('%A')}"
            else:
                label = f"next {d.strftime('%A')}"
            entry = f"  {label} = {d.isoformat()}"
            if i <= 6:
                this_week.append(entry)
            else:
                next_week.append(entry)

        next_week_start = today_dt + datetime.timedelta(days=7)
        next_week_end = today_dt + datetime.timedelta(days=13)
        upcoming_str = (
            "This week:\n" + "\n".join(this_week) +
            f"\n\nNext week ({next_week_start.strftime('%b %d')}–{next_week_end.strftime('%b %d')}):\n" +
            "\n".join(next_week)
        )

        lines = [
            "You are a voice assistant intent parser for a calendar and task management application.",
            f"Today is {day_name}, {today}. Timezone: {timezone}.",
            "",
            "Date reference — use ONLY these to resolve relative dates:",
            upcoming_str,
            "",
            "Rules for relative dates:",
            "  - 'next [Day]' = the entry labelled 'next [Day]' above (in next week's block).",
            "  - 'next week on [Day]' = that day in the 'Next week' block above.",
            "  - 'this [Day]' = the entry labelled 'this [Day]' in this week's block.",
            "  - If the user specifies an explicit calendar date number (e.g., 'the 14th', 'April 15'), use that date directly — do not apply any additional week offset on top of it.",
            "  - Never guess — always copy the exact ISO date from the table above.",
            "",
            "Return ONLY valid JSON. The format MUST be exactly:",
            '{"actions": [{"action": "<name>", "parameters": {...}}, ...]}',
            "",
            "CRITICAL: Always use the 'actions' array, even if there is only 1 action.",
            "If the user's transcript contains multiple distinct events, times, or tasks (e.g. 'Set a meeting at 10am and another at 2pm'), extract each as a separate object in the 'actions' array.",
            "",
            'Use action="unknown" with parameters={} if no action matches.',
            "",
            "VIEW CONTEXT: If the transcript starts with '[TASKS VIEW]', the user is looking at their",
            "task list. In this context, strongly prefer todo actions (create_todo, complete_todo,",
            "delete_todo, update_todo, query_todos) for ambiguous commands like 'add groceries' or",
            "'remove milk'. Only use calendar actions if the user explicitly mentions times, dates,",
            "meetings, or events.",
            "",
            "Registered actions and what triggers them:",
        ]
        for name, cls in self._actions.items():
            lines.append(f"\n  action: \"{name}\"")
            lines.append(f"  description: {cls.description}")
            lines.append(f"  parameters schema:")
            for schema_line in json.dumps(cls.parameters_schema, indent=4).splitlines():
                lines.append(f"    {schema_line}")

        return "\n".join(lines)

    def build_ollama_schema(self) -> dict:
        """
        Top-level JSON schema passed to Ollama's structured-output feature.
        Ollama enforces only the envelope; Pydantic validates parameters (two-pass).
        """
        action_names = self.all_names() + ["unknown"]
        return {
            "type": "object",
            "properties": {
                "actions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": action_names,
                            },
                            "parameters": {
                                "type": "object",
                            },
                        },
                        "required": ["action", "parameters"],
                    }
                }
            },
            "required": ["actions"],
        }

    # ------------------------------------------------------------------
    # Test helpers
    # ------------------------------------------------------------------

    def _reset(self) -> None:
        """For test isolation only. Clears all registered actions."""
        self._actions.clear()


# Module-level singleton
registry = ActionRegistry()


def register(cls: Type[BaseAction]) -> Type[BaseAction]:
    """Convenience decorator: @register on a BaseAction subclass."""
    return registry.register(cls)
