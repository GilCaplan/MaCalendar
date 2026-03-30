"""Unit tests for the ActionRegistry."""

import json

import pytest

from assistant.actions import ActionRegistry, register, registry
from tests.conftest import DummyAction, DummyIntent


def test_register_and_get_roundtrip(isolated_registry, dummy_action_cls):
    isolated_registry.register(dummy_action_cls)
    result = isolated_registry.get("dummy_action")
    assert result is dummy_action_cls


def test_decorator_registers(isolated_registry):
    @isolated_registry.register
    class TempAction(DummyAction):
        action_name = "temp_action"

    assert isolated_registry.get("temp_action") is TempAction


def test_duplicate_registration_raises(isolated_registry, dummy_action_cls):
    isolated_registry.register(dummy_action_cls)
    with pytest.raises(ValueError, match="already registered"):
        isolated_registry.register(dummy_action_cls)


def test_get_unknown_action_returns_none(isolated_registry):
    assert isolated_registry.get("nonexistent") is None


def test_all_names_returns_registered(isolated_registry, dummy_action_cls):
    isolated_registry.register(dummy_action_cls)

    class AnotherAction(DummyAction):
        action_name = "another"

    isolated_registry.register(AnotherAction)
    names = isolated_registry.all_names()
    assert "dummy_action" in names
    assert "another" in names


def test_build_system_prompt_contains_description(isolated_registry, dummy_action_cls):
    isolated_registry.register(dummy_action_cls)
    prompt = isolated_registry.build_system_prompt("2026-04-01", "UTC")
    assert "dummy_action" in prompt
    assert "A dummy action for testing." in prompt


def test_build_system_prompt_contains_parameters_schema(isolated_registry, dummy_action_cls):
    isolated_registry.register(dummy_action_cls)
    prompt = isolated_registry.build_system_prompt("2026-04-01", "UTC")
    assert "message" in prompt


def test_build_ollama_schema_includes_unknown(isolated_registry):
    schema = isolated_registry.build_ollama_schema()
    assert "unknown" in schema["properties"]["action"]["enum"]


def test_build_ollama_schema_includes_registered(isolated_registry, dummy_action_cls):
    isolated_registry.register(dummy_action_cls)
    schema = isolated_registry.build_ollama_schema()
    assert "dummy_action" in schema["properties"]["action"]["enum"]


def test_build_ollama_schema_empty_registry(isolated_registry):
    schema = isolated_registry.build_ollama_schema()
    assert schema["properties"]["action"]["enum"] == ["unknown"]


def test_reset_clears_actions(isolated_registry, dummy_action_cls):
    isolated_registry.register(dummy_action_cls)
    isolated_registry._reset()
    assert isolated_registry.all_names() == []
