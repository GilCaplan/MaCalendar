"""Tests for Pipeline's background LLM verification/correction — the "slower,
more careful" pass that judges every rule fast-path result after the fact and can
silently patch (minor) or undo-and-redo (major) it. This logic had zero test
coverage before: it's daemon-thread-only code, never exercised by any existing
test, despite being the safety net for the entire fast-path architecture.

We don't construct a real Pipeline() (that pulls in a live mic, a real Whisper
model, and a real TTS engine). Instead we call the unbound instance methods
against a minimal double exposing just the attributes they touch — the same
duck-typing Python allows for any bound method call.
"""
from __future__ import annotations

import queue
from typing import Any
from unittest.mock import MagicMock

import pytest

from assistant.actions.base import BaseAction
from assistant.actions.calendar.intent import CalendarIntent
from assistant.actions.todo.intent import CreateTodoIntent
from assistant.intent.rule_parser import RuleParseResult
from assistant.pipeline import Pipeline


# ---------------------------------------------------------------------------
# Fake actions — avoid any real Microsoft Graph / DB network calls
# ---------------------------------------------------------------------------

class _FakeCreateEventAction(BaseAction):
    action_name = "create_event"
    description = "test create_event"
    intent_model = CalendarIntent
    parameters_schema = {"type": "object", "properties": {}}

    def __init__(self):
        self.calls: list = []

    def execute(self, intent: CalendarIntent, config: Any) -> str:
        self.calls.append(intent)
        return f"Created event '{intent.title}'"


class _FakeCreateTodoAction(BaseAction):
    action_name = "create_todo"
    description = "test create_todo"
    intent_model = CreateTodoIntent
    parameters_schema = {"type": "object", "properties": {}}

    def execute(self, intent: CreateTodoIntent, config: Any) -> str:
        return f"Added {intent.titles}"


@pytest.fixture
def registry_with_fakes(isolated_registry):
    isolated_registry._actions["create_event"] = _FakeCreateEventAction
    isolated_registry._actions["create_todo"] = _FakeCreateTodoAction
    return isolated_registry


# ---------------------------------------------------------------------------
# Fake Pipeline double — only the attributes _background_verify/_background_fix_title touch
# ---------------------------------------------------------------------------

class _FakePipeline:
    def __init__(self, registry, config, parser):
        self.registry = registry
        self.config = config
        self._parser = parser
        self._tts = MagicMock()
        self.status_queue: "queue.Queue" = queue.Queue()
        self.trace_queue: "queue.Queue" = queue.Queue()

    def _set_status(self, status: str, message: str = "") -> None:
        self.status_queue.put((status, message))

    _trace_late_step = Pipeline._trace_late_step
    _detect_user_change = staticmethod(Pipeline._detect_user_change)
    _background_verify = Pipeline._background_verify
    _background_fix_title = Pipeline._background_fix_title
    # Duck-typed double, not a Pipeline subclass — patch these directly so the
    # real methods never touch DOCUMENTATION/*.md during tests.
    _append_scenario_bug = staticmethod(MagicMock())
    _append_nlu_log = staticmethod(MagicMock())


@pytest.fixture(autouse=True)
def no_markdown_writes(monkeypatch):
    """Prevent tests from appending to the real DOCUMENTATION/*.md files."""
    monkeypatch.setattr(Pipeline, "_append_scenario_bug", MagicMock())
    monkeypatch.setattr(Pipeline, "_append_nlu_log", MagicMock())


@pytest.fixture
def fake_db(monkeypatch):
    db = MagicMock()
    monkeypatch.setattr("assistant.db.get_db", lambda: db)
    return db


def _rule_result(action_name: str, slots: dict, confidence: float = 0.9) -> RuleParseResult:
    return RuleParseResult(
        confidence=confidence,
        intents=[],
        missing_slots=[],
        raw_slots={action_name: slots},
        transcript="test transcript",
    )


# ---------------------------------------------------------------------------
# Tier 1 — ok: LLM confirms the fast-path was right, nothing happens
# ---------------------------------------------------------------------------

def test_tier1_ok_is_silent(registry_with_fakes, sample_config, fake_db):
    parser = MagicMock()
    parser.verify_fast_path_async.return_value = None  # tier 1
    pipeline = _FakePipeline(registry_with_fakes, sample_config, parser)

    rule_result = _rule_result("create_todo", {"titles": ["milk"]})
    snapshot = {"actions": [("create_todo", None)], "todo_id": 7, "todo_title": "milk"}

    pipeline._background_verify("buy some obscure thing", rule_result, snapshot)

    fake_db.update_event.assert_not_called()
    fake_db.update_todo.assert_not_called()
    fake_db.delete_event.assert_not_called()
    fake_db.delete_todo.assert_not_called()
    pipeline._tts.speak.assert_not_called()


# ---------------------------------------------------------------------------
# Short-circuit: strong calendar word + explicit time skips verification entirely
# ---------------------------------------------------------------------------

def test_strong_calendar_signal_skips_verification(registry_with_fakes, sample_config, fake_db):
    parser = MagicMock()
    pipeline = _FakePipeline(registry_with_fakes, sample_config, parser)

    rule_result = _rule_result(
        "create_event", {"title": "meeting", "start_time": "15:00"}
    )
    snapshot = {"actions": [("create_event", None)], "event_id": 1, "event_title": "meeting"}

    pipeline._background_verify("schedule a meeting tomorrow at 3pm", rule_result, snapshot)

    parser.verify_fast_path_async.assert_not_called()


# ---------------------------------------------------------------------------
# Tier 2 — minor: silently patch the existing record
# ---------------------------------------------------------------------------

def test_tier2_minor_patches_event(registry_with_fakes, sample_config, fake_db):
    parser = MagicMock()
    parser.verify_fast_path_async.return_value = {
        "severity": "minor",
        "patch": {"title": "Dentist appointment"},
        "speech": "Fixed the title.",
    }
    pipeline = _FakePipeline(registry_with_fakes, sample_config, parser)
    fake_db.get_event.return_value = {"title": "appointment", "date": "2026-04-14"}

    rule_result = _rule_result(
        "create_event", {"title": "appointment", "date": "2026-04-14"}
    )
    snapshot = {
        "actions": [("create_event", None)],
        "event_id": 42,
        "event_title": "appointment",
        "event_date": "2026-04-14",
    }

    pipeline._background_verify("set an appointment tomorrow at 9am", rule_result, snapshot)

    fake_db.update_event.assert_called_once_with(42, title="Dentist appointment")
    pipeline._tts.speak.assert_called_once_with("Fixed the title.")
    fake_db.delete_event.assert_not_called()


def test_tier2_minor_skips_when_user_already_changed_record(registry_with_fakes, sample_config, fake_db):
    """If the user already edited the record before the background verify ran,
    their change is implicit feedback — the correction must not overwrite it.
    """
    parser = MagicMock()
    parser.verify_fast_path_async.return_value = {
        "severity": "minor",
        "patch": {"title": "Dentist appointment"},
        "speech": "Fixed the title.",
    }
    pipeline = _FakePipeline(registry_with_fakes, sample_config, parser)
    # User already retitled it manually — current DB state no longer matches the snapshot.
    fake_db.get_event.return_value = {"title": "User's own title", "date": "2026-04-14"}

    rule_result = _rule_result(
        "create_event", {"title": "appointment", "date": "2026-04-14"}
    )
    snapshot = {
        "actions": [("create_event", None)],
        "event_id": 42,
        "event_title": "appointment",
        "event_date": "2026-04-14",
    }

    pipeline._background_verify("set an appointment tomorrow at 9am", rule_result, snapshot)

    fake_db.update_event.assert_not_called()
    pipeline._tts.speak.assert_not_called()


# ---------------------------------------------------------------------------
# Tier 3 — major: undo the fast-path create, re-execute with the LLM correction
# ---------------------------------------------------------------------------

def test_tier3_major_undoes_and_reexecutes(registry_with_fakes, sample_config, fake_db):
    parser = MagicMock()
    parser.verify_fast_path_async.return_value = {
        "severity": "major",
        "action": "create_todo",
        "parameters": {"titles": ["magsha meme bagru progress update with rina"]},
        "speech": "Actually made that a todo instead.",
    }
    pipeline = _FakePipeline(registry_with_fakes, sample_config, parser)
    fake_db.get_event.return_value = {"title": "rina", "date": "2026-04-08"}

    rule_result = _rule_result(
        "update_event", {"match_title": "rina", "new_start_time": "17:15"}
    )
    snapshot = {
        "actions": [("update_event", None)],
        "event_id": 99,
        "event_title": "rina",
        "event_date": "2026-04-08",
    }

    pipeline._background_verify(
        "a certain meeting on wednesday at 5.15pm to meet with rina for progress update",
        rule_result, snapshot,
    )

    # update_event isn't a create, so nothing gets undone via delete_event —
    # but the corrected create_todo must still execute.
    fake_db.delete_event.assert_not_called()
    pipeline._tts.speak.assert_called_once()
    assert "Actually made that a todo instead." in pipeline._tts.speak.call_args[0][0]


def test_tier3_major_undoes_create_event_before_redo(registry_with_fakes, sample_config, fake_db):
    parser = MagicMock()
    parser.verify_fast_path_async.return_value = {
        "severity": "major",
        "action": "create_todo",
        "parameters": {"titles": ["visit my friend tal with naor"]},
        "speech": "",
    }
    pipeline = _FakePipeline(registry_with_fakes, sample_config, parser)
    fake_db.get_event.return_value = {"title": "event", "date": "2026-04-16"}

    rule_result = _rule_result(
        "create_event", {"title": "event", "date": "2026-04-16", "start_time": "13:00"}
    )
    snapshot = {
        "actions": [("create_event", None)],
        "event_id": 7,
        "event_title": "event",
        "event_date": "2026-04-16",
    }

    pipeline._background_verify(
        "please send an event for me at 1pm to go visit my friend tal with naor",
        rule_result, snapshot,
    )

    fake_db.delete_event.assert_called_once_with(7)


def test_tier3_invalid_correction_params_does_not_undo(registry_with_fakes, sample_config, fake_db):
    """If the LLM's correction has invalid, unrecoverable params (create_todo with
    no titles — unlike create_event, there's no keyword/rule-parser fallback for
    an empty todo title list), the original fast-path record must survive —
    validate the correction BEFORE destroying anything.
    """
    parser = MagicMock()
    parser.verify_fast_path_async.return_value = {
        "severity": "major",
        "action": "create_todo",
        "parameters": {"titles": []},  # invalid — CreateTodoIntent requires titles
        "speech": "",
    }
    pipeline = _FakePipeline(registry_with_fakes, sample_config, parser)
    fake_db.get_event.return_value = {"title": "appointment", "date": "2026-04-14"}

    rule_result = _rule_result(
        "create_event", {"title": "appointment", "date": "2026-04-14"}
    )
    snapshot = {
        "actions": [("create_event", None)],
        "event_id": 5,
        "event_title": "appointment",
        "event_date": "2026-04-14",
    }

    pipeline._background_verify(
        "set an appointment for tomorrow morning at 910am", rule_result, snapshot,
    )

    fake_db.delete_event.assert_not_called()


# ---------------------------------------------------------------------------
# Background title fix (keyword placeholder titles, e.g. "meeting")
# ---------------------------------------------------------------------------

def test_background_fix_title_patches_when_unchanged(registry_with_fakes, sample_config, fake_db):
    parser = MagicMock()
    parser.fix_title_async.return_value = "Meeting with Adin for Project"
    pipeline = _FakePipeline(registry_with_fakes, sample_config, parser)
    fake_db.get_event.return_value = {"title": "meeting"}

    pipeline._background_fix_title(
        "set a meeting tomorrow at 2 o'clock meeting with adin for project", 12, "meeting"
    )

    fake_db.update_event.assert_called_once_with(12, title="Meeting with Adin for Project")


def test_background_fix_title_skips_when_user_already_edited(registry_with_fakes, sample_config, fake_db):
    parser = MagicMock()
    parser.fix_title_async.return_value = "Meeting with Adin for Project"
    pipeline = _FakePipeline(registry_with_fakes, sample_config, parser)
    # User already retitled it before the background fix ran.
    fake_db.get_event.return_value = {"title": "Adin 1:1"}

    pipeline._background_fix_title(
        "set a meeting tomorrow at 2 o'clock meeting with adin for project", 12, "meeting"
    )

    fake_db.update_event.assert_not_called()


def test_background_fix_title_skips_when_event_deleted(registry_with_fakes, sample_config, fake_db):
    parser = MagicMock()
    parser.fix_title_async.return_value = "Meeting with Adin"
    pipeline = _FakePipeline(registry_with_fakes, sample_config, parser)
    fake_db.get_event.return_value = None  # deleted before the fix ran

    pipeline._background_fix_title("some transcript", 12, "meeting")

    fake_db.update_event.assert_not_called()
