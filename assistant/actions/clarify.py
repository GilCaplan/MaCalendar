"""Clarification action — returned by the LLM when the user's request is ambiguous."""

from typing import ClassVar, Type

from assistant.actions import register
from assistant.actions.base import BaseAction, BaseIntent


class ClarifyIntent(BaseIntent):
    question: str


@register
class ClarifyAction(BaseAction):
    action_name: ClassVar[str] = "clarify"
    description: ClassVar[str] = (
        "Ask the user for clarification when a key detail is missing or ambiguous. "
        "Use this when the user says something like 'next week' without specifying which day, "
        "'this month' without a date, or any request where you cannot determine a specific date or time. "
        "Do NOT guess a date — ask instead. "
        "Examples that need clarification: "
        "'schedule something next week' (no day given), "
        "'set a meeting soon' (no date or time), "
        "'remind me next month' (no specific date). "
        "Examples that do NOT need clarification: "
        "'schedule a meeting Tuesday at 2pm' (fully specified), "
        "'add a dentist appointment next Monday at 10am' (day and time given)."
    )
    intent_model: ClassVar[Type[BaseIntent]] = ClarifyIntent
    parameters_schema: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": (
                    "A short, natural clarifying question. "
                    "Examples: 'Which day next week?', 'What time?', 'Which date this month?'"
                ),
            },
        },
        "required": ["question"],
    }

    def execute(self, intent: ClarifyIntent, _config) -> str:
        return intent.question
