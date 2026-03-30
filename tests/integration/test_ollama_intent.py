"""Integration tests against a real running Ollama instance.

Skipped automatically if Ollama is not reachable at localhost:11434.
"""

import pytest
import requests

from assistant.actions.calendar.intent import CalendarIntent
from assistant.config import OllamaConfig
from assistant.intent.parser import OllamaIntentParser, UnknownIntent


def _ollama_running() -> bool:
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _ollama_running(),
    reason="Ollama not running at localhost:11434 — skipping integration tests",
)


@pytest.fixture
def parser(registry_with_calendar):
    config = OllamaConfig(model="llama3.2:3b", temperature=0.0, timeout_seconds=60)
    return OllamaIntentParser(config, registry_with_calendar)


def test_calendar_phrase_produces_create_event(parser):
    action_name, intent = parser.parse("Schedule a team meeting tomorrow at 2pm")
    assert action_name == "create_event"
    assert isinstance(intent, CalendarIntent)
    assert intent.title  # non-empty


def test_unknown_phrase_produces_unknown(parser):
    action_name, intent = parser.parse("What is the capital of France?")
    assert action_name == "unknown"
    assert isinstance(intent, UnknownIntent)


def test_relative_date_is_resolved(parser):
    """The LLM should convert 'tomorrow' to an ISO date."""
    _, intent = parser.parse("Book a call tomorrow at 3pm")
    assert isinstance(intent, CalendarIntent)
    import re
    assert re.match(r"\d{4}-\d{2}-\d{2}", intent.date), f"Expected ISO date, got: {intent.date}"


def test_attendees_extracted(parser):
    _, intent = parser.parse("Schedule lunch with Alice and Bob on Friday at noon")
    assert isinstance(intent, CalendarIntent)
    names = [a.lower() for a in intent.attendees]
    assert "alice" in names or "bob" in names
