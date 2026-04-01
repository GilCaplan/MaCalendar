"""Configuration loading and validation."""

import os
from typing import List, Literal, Optional

import yaml
from pydantic import BaseModel, field_validator

from assistant.exceptions import ConfigError


class HotkeyConfig(BaseModel):
    modifiers: List[str]
    key: str

    @field_validator("modifiers")
    @classmethod
    def validate_modifiers(cls, v: List[str]) -> List[str]:
        allowed = {"cmd", "shift", "ctrl", "alt"}
        for m in v:
            if m not in allowed:
                raise ValueError(f"Unknown modifier '{m}'. Allowed: {allowed}")
        return v


class WhisperConfig(BaseModel):
    model_size: str = "base"
    compute_type: str = "int8"
    device: str = "cpu"
    language: Optional[str] = "en"
    beam_size: int = 1  # 1 = greedy decode; faster for short voice commands


class GoogleSTTConfig(BaseModel):
    api_key: Optional[str] = None


class OllamaConfig(BaseModel):
    base_url: str = "http://localhost:11434"
    model: str = "llama3.1:8b"
    temperature: float = 0.1
    timeout_seconds: int = 60


class OpenAIConfig(BaseModel):
    api_key: Optional[str] = None
    model: str = "gpt-4o"
    temperature: float = 0.1


class GeminiConfig(BaseModel):
    api_key: Optional[str] = None
    model: str = "gemini-1.5-pro"
    temperature: float = 0.1


class ClaudeConfig(BaseModel):
    api_key: Optional[str] = None
    model: str = "claude-3-5-sonnet-20240620"
    temperature: float = 0.1


class MicrosoftConfig(BaseModel):
    client_id: str
    tenant_id: str = "common"
    token_cache_path: str = "~/.assistant_tools/msal_token_cache.json"


class AudioConfig(BaseModel):
    sample_rate: int = 16000
    silence_threshold: float = 0.01
    silence_duration_sec: float = 20.0   # stop after 20s of silence
    max_recording_sec: int = 120         # hard cap


class TTSConfig(BaseModel):
    mute: bool = False
    voice: str = "Samantha"
    rate: int = 200


class TodoSyncConfig(BaseModel):
    mode: Literal["today", "general", "off"] = "off"
    auto_sync_on_open: bool = False


class TodoConfig(BaseModel):
    sync: TodoSyncConfig = TodoSyncConfig()
    show_completed: bool = False
    default_list: Literal["today", "general"] = "today"


class AppConfig(BaseModel):
    hotkey: HotkeyConfig
    stt_engine: Literal["whisper", "google"] = "whisper"
    llm_engine: Literal["ollama", "openai", "gemini", "claude"] = "ollama"
    whisper: WhisperConfig = WhisperConfig()
    google_stt: GoogleSTTConfig = GoogleSTTConfig()
    ollama: OllamaConfig = OllamaConfig()
    openai: OpenAIConfig = OpenAIConfig()
    gemini: GeminiConfig = GeminiConfig()
    claude: ClaudeConfig = ClaudeConfig()
    microsoft: Optional[MicrosoftConfig] = None
    confirmation_level: int = 1
    audio: AudioConfig = AudioConfig()
    tts: TTSConfig = TTSConfig()
    todo: TodoConfig = TodoConfig()

    @field_validator("confirmation_level")
    @classmethod
    def validate_confirmation_level(cls, v: int) -> int:
        if not 0 <= v <= 3:
            raise ValueError("confirmation_level must be between 0 and 3")
        return v


def load_config(path: str = "config.yaml") -> AppConfig:
    """Load and validate config from a YAML file.

    Supports environment variable overrides:
      ASSISTANT_OLLAMA_MODEL   → ollama.model
      ASSISTANT_STT_ENGINE     → stt_engine
      ASSISTANT_CONFIRMATION   → confirmation_level
    """
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        raise ConfigError(
            f"Config file not found: {path}\n"
            f"Copy config.example.yaml to config.yaml and fill in your values."
        )

    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in {path}: {e}") from e

    if data is None:
        raise ConfigError(f"Config file is empty: {path}")

    # Environment variable overrides
    if model := os.environ.get("ASSISTANT_OLLAMA_MODEL"):
        data.setdefault("ollama", {})["model"] = model
    if engine := os.environ.get("ASSISTANT_STT_ENGINE"):
        data["stt_engine"] = engine
    if level := os.environ.get("ASSISTANT_CONFIRMATION"):
        data["confirmation_level"] = int(level)

    try:
        return AppConfig(**data)
    except Exception as e:
        raise ConfigError(f"Configuration error: {e}") from e
