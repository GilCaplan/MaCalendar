"""Unit tests for the Ollama intent parser."""

import json
from unittest.mock import MagicMock, patch

import pytest

from assistant.exceptions import OllamaUnavailableError, ParseError
from assistant.intent.parser import IntentParser, UnknownIntent
from tests.conftest import DummyAction, DummyIntent


def _make_parser(isolated_registry, sample_config):
    isolated_registry.register(DummyAction)
    return IntentParser(sample_config, isolated_registry)


def _mock_post(monkeypatch, content: str):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.ok = True
    mock_resp.json.return_value = {"message": {"content": content}}
    mock_resp.raise_for_status = MagicMock()
    monkeypatch.setattr("requests.Session.post", lambda *a, **kw: mock_resp)
    return mock_resp


def test_valid_response_returns_intent(monkeypatch, isolated_registry, sample_config):
    parser = _make_parser(isolated_registry, sample_config)
    _mock_post(monkeypatch, json.dumps({"action": "dummy_action", "parameters": {"message": "hi"}}))
    results = parser.parse("do the dummy thing")
    action_name, intent = results[0]
    assert action_name == "dummy_action"
    assert isinstance(intent, DummyIntent)
    assert intent.message == "hi"


def test_unknown_action_returns_unknown_intent(monkeypatch, isolated_registry, sample_config):
    parser = _make_parser(isolated_registry, sample_config)
    _mock_post(monkeypatch, json.dumps({"action": "unknown", "parameters": {}}))
    results = parser.parse("what is the weather?")
    action_name, intent = results[0]
    assert action_name == "unknown"
    assert isinstance(intent, UnknownIntent)


def test_malformed_json_raises_parse_error(monkeypatch, isolated_registry, sample_config):
    parser = _make_parser(isolated_registry, sample_config)
    _mock_post(monkeypatch, "this is not json at all")
    with pytest.raises(ParseError):
        parser.parse("something")


def test_missing_required_param_raises_parse_error(monkeypatch, isolated_registry, sample_config):
    # DummyIntent has 'message' with a default, so let's use CalendarIntent instead
    from assistant.actions.calendar.action import CreateEventAction
    isolated_registry.register(CreateEventAction)
    parser = IntentParser(sample_config, isolated_registry)
    # Missing required fields: date, start_time, end_time
    _mock_post(monkeypatch, json.dumps({"action": "create_event", "parameters": {"title": "X"}}))
    with pytest.raises(ParseError):
        parser.parse("schedule something")


def test_connection_error_raises_ollama_unavailable(monkeypatch, isolated_registry, sample_config):
    import requests
    parser = _make_parser(isolated_registry, sample_config)
    monkeypatch.setattr(
        "requests.Session.post",
        lambda *a, **kw: (_ for _ in ()).throw(requests.ConnectionError("refused")),
    )
    with pytest.raises(OllamaUnavailableError):
        parser.parse("anything")


def test_json_in_markdown_block_is_extracted(monkeypatch, isolated_registry, sample_config):
    parser = _make_parser(isolated_registry, sample_config)
    wrapped = "```json\n" + json.dumps({"action": "dummy_action", "parameters": {"message": "test"}}) + "\n```"
    _mock_post(monkeypatch, wrapped)
    results = parser.parse("do dummy")
    action_name, intent = results[0]
    assert action_name == "dummy_action"


def test_system_prompt_contains_all_action_names(isolated_registry):
    isolated_registry.register(DummyAction)

    class AnotherAction(DummyAction):
        action_name = "another_action"
        description = "Another action."

    isolated_registry.register(AnotherAction)
    prompt = isolated_registry.build_system_prompt("2026-04-01", "UTC")
    assert "dummy_action" in prompt
    assert "another_action" in prompt


def test_health_check_returns_false_when_ollama_down(monkeypatch, isolated_registry, sample_config):
    import requests
    parser = _make_parser(isolated_registry, sample_config)
    monkeypatch.setattr(
        "requests.Session.get",
        lambda *a, **kw: (_ for _ in ()).throw(requests.ConnectionError()),
    )
    assert parser.health_check() is False
