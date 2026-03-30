"""Unit tests for the confirmation handler."""

from unittest.mock import MagicMock, patch

import pytest

from assistant.actions.calendar.intent import CalendarIntent
from assistant.confirmation.handler import ConfirmationHandler


def _intent(**kwargs) -> CalendarIntent:
    defaults = dict(title="Standup", date="2026-04-01", start_time="09:00", end_time="09:30")
    defaults.update(kwargs)
    return CalendarIntent(**defaults)


def test_level_0_always_returns_true():
    handler = ConfirmationHandler(0)
    assert handler.check("create_event", _intent()) is True


def test_level_1_ok_button_returns_true(monkeypatch):
    handler = ConfirmationHandler(1)
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "button returned:Create"
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: mock_result)
    assert handler.check("create_event", _intent()) is True


def test_level_1_cancel_returns_false(monkeypatch):
    handler = ConfirmationHandler(1)
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: mock_result)
    assert handler.check("create_event", _intent()) is False


def test_dialog_script_contains_title(monkeypatch):
    handler = ConfirmationHandler(1)
    captured = {}

    def fake_run(args, **kwargs):
        captured["script"] = args
        result = MagicMock()
        result.returncode = 0
        result.stdout = "button returned:Create"
        return result

    monkeypatch.setattr("subprocess.run", fake_run)
    handler.check("create_event", _intent(title="Important Meeting"))
    assert any("Important Meeting" in str(a) for a in captured["script"])
