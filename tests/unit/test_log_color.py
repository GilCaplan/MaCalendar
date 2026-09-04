"""The server log's colour bands — so a skim reads command→response→error."""
from __future__ import annotations

import logging

from assistant.api.log_color import ColorFormatter, category


def _rec(msg, level=logging.INFO):
    return logging.LogRecord("assistant.api.server", level, __file__, 1, msg, (), None)


def test_a_command_arriving_is_cyan_in():
    assert category(_rec("📱 Text command: what do I have today")) == "in"
    assert category(_rec("📱 Transcript: gym tomorrow")) == "in"


def test_a_response_is_green_out():
    assert category(_rec("📱 Response: Created event 'gym' | refresh=events | parse=fast")) == "out"


def test_a_failure_is_red_error():
    assert category(_rec("📱 Parse error: model offline")) == "error"
    assert category(_rec("No action class for: frobnicate")) == "error"
    assert category(_rec("boom", level=logging.ERROR)) == "error"


def test_learning_is_magenta_and_warnings_yellow():
    assert category(_rec("Learned from a retry: 'x' -> 'y'")) == "learn"
    assert category(_rec("Warm-up finished in 2.1s")) == "warn"
    assert category(_rec("slow", level=logging.WARNING)) == "warn"


def test_the_processing_middle_stays_plain():
    assert category(_rec("📱 Rule fast-path: confidence=0.95 actions=['create_event']")) is None
    assert category(_rec("📱 Parsed actions: ['create_event']")) is None


def test_the_formatter_wraps_only_categorised_lines():
    f = ColorFormatter()
    out = f.format(_rec("📱 Response: done | parse=fast"))
    assert out.startswith("\033[32m") and out.endswith("\033[0m")
    plain = f.format(_rec("📱 Rule fast-path: confidence=0.95"))
    assert "\033[" not in plain
