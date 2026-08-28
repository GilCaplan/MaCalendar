"""Shared pytest fixtures."""

from __future__ import annotations

# Point every personal store at a throwaway directory BEFORE importing anything
# from `assistant`. The calendar DB, command memory, vocabulary and event
# categories all live in ~/.assistant_tools, and their paths are read at import
# time (they're default arguments and module constants), so a fixture would run
# too late. Without this the integration tests replayed "buy milk" and
# "asdkjhaskjdh unrelated gibberish" straight into the user's real command
# memory and vocabulary, where they became few-shot examples the assistant
# learns from.
import os as _os
import tempfile as _tempfile

_SCRATCH = _tempfile.mkdtemp(prefix="macalendar-tests-")
for _var, _name in (("MACALENDAR_DB", "calendar.db"),
                    ("MACALENDAR_MEMORY_DB", "nlu_memory.db"),
                    ("MACALENDAR_VOCAB", "vocab.json"),
                    ("MACALENDAR_CATEGORIES", "categories.json")):
    _os.environ.setdefault(_var, _os.path.join(_SCRATCH, _name))

import json
import os
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest

from assistant.actions import ActionRegistry, registry as global_registry
from assistant.actions.base import BaseAction, BaseIntent
from assistant.actions.calendar.intent import CalendarIntent
from assistant.config import (
    AppConfig,
    AudioConfig,
    GoogleSTTConfig,
    HotkeyConfig,
    MicrosoftConfig,
    OllamaConfig,
    TTSConfig,
    WhisperConfig,
)


# ---------------------------------------------------------------------------
# Context memory reset — clears anaphora state between tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_context_memory():
    """Clear ContextMemory before each test to prevent anaphora state leaking."""
    from assistant.intent.context import context_memory
    context_memory.reset()
    yield
    context_memory.reset()


# ---------------------------------------------------------------------------
# Registry isolation — MUST run before each test to prevent pollution
# ---------------------------------------------------------------------------

# Every real action, captured once at import — before any test empties the
# shared registry. `@register` fires on a module's FIRST import only, so a
# fixture that re-imports the module registers nothing the second time round.
import assistant.actions.calendar   # noqa: E402,F401
import assistant.actions.todo       # noqa: E402,F401
import assistant.actions.clarify    # noqa: E402,F401

_REAL_ACTIONS = dict(global_registry._actions)


@pytest.fixture(autouse=True)
def isolated_registry():
    """Reset the global ActionRegistry before each test."""
    original = dict(global_registry._actions)
    global_registry._actions.clear()
    yield global_registry
    global_registry._actions.clear()
    global_registry._actions.update(original)


@pytest.fixture
def registry_with_calendar(isolated_registry):
    """Registry with the real calendar action registered."""
    import assistant.actions.calendar  # noqa: F401 — triggers @register
    isolated_registry._actions.update(_REAL_ACTIONS)
    return isolated_registry


@pytest.fixture
def registry_with_real_actions(isolated_registry):
    """Every real action, for tests that drive the API server end to end."""
    isolated_registry._actions.update(_REAL_ACTIONS)
    return isolated_registry


# ---------------------------------------------------------------------------
# Config fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_config() -> AppConfig:
    return AppConfig(
        hotkey=HotkeyConfig(modifiers=["cmd", "shift"], key="space"),
        stt_engine="whisper",
        whisper=WhisperConfig(model_size="tiny", compute_type="int8", device="cpu"),
        google_stt=GoogleSTTConfig(),
        ollama=OllamaConfig(
            base_url="http://localhost:11434",
            model="llama3.2:3b",
            temperature=0.1,
            timeout_seconds=5,
        ),
        microsoft=MicrosoftConfig(
            client_id="test-client-id",
            tenant_id="common",
            token_cache_path="/tmp/test_token_cache.json",
        ),
        confirmation_level=0,
        audio=AudioConfig(
            sample_rate=16000,
            silence_threshold=0.01,
            silence_duration_sec=1.0,
            max_recording_sec=5,
        ),
        tts=TTSConfig(voice="Samantha", rate=200),
    )


# ---------------------------------------------------------------------------
# Intent fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_calendar_intent() -> CalendarIntent:
    return CalendarIntent(
        title="Team standup",
        date="2026-04-01",
        start_time="09:00",
        end_time="09:30",
        attendees=["Alice", "Bob"],
    )


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_ollama_response():
    """
    Factory: returns a mock requests.Response for Ollama /api/chat.

    Usage:
        mock_response = mock_ollama_response("create_event", {"title": "X", ...})
    """
    def _make(action: str, parameters: dict) -> MagicMock:
        mock = MagicMock()
        mock.status_code = 200
        mock.ok = True
        mock.json.return_value = {
            "message": {
                "content": json.dumps({"action": action, "parameters": parameters})
            }
        }
        mock.raise_for_status = MagicMock()
        return mock

    return _make


@pytest.fixture
def mock_graph_token(monkeypatch):
    """Patch MSAL so get_token() returns a fake token without network calls."""
    monkeypatch.setattr(
        "assistant.actions.calendar.auth.MSALAuth.get_token",
        lambda self: "fake-bearer-token",
    )


@pytest.fixture
def silent_audio() -> np.ndarray:
    """5 seconds of silent audio at 16kHz."""
    return np.zeros(16000 * 5, dtype=np.float32)


@pytest.fixture
def speech_audio() -> np.ndarray:
    """Simulate 1 second of 'speech' (non-silent) followed by silence."""
    speech = np.random.uniform(-0.5, 0.5, 16000).astype(np.float32)
    silence = np.zeros(16000 * 2, dtype=np.float32)
    return np.concatenate([speech, silence])


# ---------------------------------------------------------------------------
# Dummy action for registry tests
# ---------------------------------------------------------------------------

class DummyIntent(BaseIntent):
    message: str = "hello"


class DummyAction(BaseAction):
    action_name = "dummy_action"
    description = "A dummy action for testing."
    intent_model = DummyIntent
    parameters_schema = {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
    }

    def execute(self, intent: DummyIntent, config: Any) -> str:
        return f"Dummy executed: {intent.message}"


@pytest.fixture
def dummy_action_cls():
    return DummyAction
