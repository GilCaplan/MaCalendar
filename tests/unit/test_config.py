"""Unit tests for config loading and validation."""

import os
import textwrap

import pytest
import yaml

from assistant.config import AppConfig, load_config
from assistant.exceptions import ConfigError


def _write_config(tmp_path, content: str) -> str:
    p = tmp_path / "config.yaml"
    p.write_text(textwrap.dedent(content))
    return str(p)


VALID_YAML = """
hotkey:
  modifiers: ["cmd", "shift"]
  key: "space"
microsoft:
  client_id: "abc-123"
"""


def test_valid_config_loads(tmp_path):
    path = _write_config(tmp_path, VALID_YAML)
    config = load_config(path)
    assert config.hotkey.key == "space"
    assert config.microsoft.client_id == "abc-123"
    assert config.confirmation_level == 1  # default


def test_defaults_applied(tmp_path):
    path = _write_config(tmp_path, VALID_YAML)
    config = load_config(path)
    assert config.stt_engine == "whisper"
    assert config.whisper.model_size == "base"
    assert config.audio.sample_rate == 16000
    assert config.tts.voice == "Samantha"


def test_missing_required_field_raises(tmp_path):
    # hotkey is required
    path = _write_config(tmp_path, "confirmation_level: 1\n")
    with pytest.raises(ConfigError):
        load_config(path)


def test_invalid_yaml_raises(tmp_path):
    path = _write_config(tmp_path, "hotkey: {bad yaml: [unclosed")
    with pytest.raises(ConfigError):
        load_config(path)


def test_missing_file_raises():
    with pytest.raises(ConfigError, match="not found"):
        load_config("/nonexistent/path/config.yaml")


def test_invalid_modifier_raises(tmp_path):
    content = VALID_YAML + "  # extra\n"
    # Override modifier
    data = yaml.safe_load(textwrap.dedent(VALID_YAML))
    data["hotkey"]["modifiers"] = ["superkey"]
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(data))
    with pytest.raises(ConfigError):
        load_config(str(path))


def test_confirmation_level_out_of_range_raises(tmp_path):
    data = yaml.safe_load(textwrap.dedent(VALID_YAML))
    data["confirmation_level"] = 5
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(data))
    with pytest.raises(ConfigError):
        load_config(str(path))


def test_env_var_overrides_ollama_model(tmp_path, monkeypatch):
    path = _write_config(tmp_path, VALID_YAML)
    monkeypatch.setenv("ASSISTANT_OLLAMA_MODEL", "mistral:7b")
    config = load_config(path)
    assert config.ollama.model == "mistral:7b"


def test_env_var_overrides_stt_engine(tmp_path, monkeypatch):
    path = _write_config(tmp_path, VALID_YAML)
    monkeypatch.setenv("ASSISTANT_STT_ENGINE", "google")
    config = load_config(path)
    assert config.stt_engine == "google"
