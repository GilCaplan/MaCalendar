"""Ollama-based intent parser — two-pass: Ollama enforces envelope, Pydantic validates params."""

from __future__ import annotations

import datetime
import json
import logging
import re

import requests

from assistant.actions import ActionRegistry
from assistant.actions.base import BaseIntent
from assistant.config import AppConfig
from assistant.exceptions import (
    AssistantError,
    LLMTimeoutError,
    LLMUnavailableError,
    OllamaTimeoutError,
    OllamaUnavailableError,
    ParseError,
)

logger = logging.getLogger(__name__)


# --- Intent Metadata ---

class UnknownIntent(BaseIntent):
    """Placeholder for cases where the LLM's response couldn't be parsed."""
    pass


class IntentParser:
    """
    Sends the user's transcript to the configured LLM backend (Ollama, OpenAI, Gemini, or Claude).
    Enforces a strict JSON envelope: {"action": "...", "parameters": {...}}
    and then validates parameters against the action's Pydantic model.
    """

    def __init__(self, config: AppConfig, registry: ActionRegistry) -> None:
        self.config = config
        self.registry = registry
        self._session = requests.Session()
        self._session.headers["Content-Type"] = "application/json"

    def parse(self, transcript: str) -> list[tuple[str, BaseIntent]]:
        """
        Parse a transcript into a list of (action_name, intent) tuples.
        """
        # --- Prompt Injection Defense ---
        forbidden = [
            "ignore previous", "ignore all", "instead do", "instead, do",
            "forget your", "system prompt", "you are now", "new instructions"
        ]
        lowered = transcript.lower()
        if any(f in lowered for f in forbidden):
            logger.warning("Potential prompt injection detected: %r", transcript)
            return [("unknown", UnknownIntent())]

        today = datetime.date.today().isoformat()
        try:
            tz = str(datetime.datetime.now().astimezone().tzname())
        except Exception:
            tz = "UTC"

        system_prompt = self.registry.build_system_prompt(today, tz)
        schema = self.registry.build_ollama_schema() # Reusing schema structure

        # Route to specific provider call
        engine = self.config.llm_engine
        try:
            if engine == "ollama":
                raw_content = self._call_ollama(system_prompt, transcript, schema)
            elif engine == "openai":
                raw_content = self._call_openai(system_prompt, transcript, schema)
            elif engine == "gemini":
                raw_content = self._call_gemini(system_prompt, transcript, schema)
            elif engine == "claude":
                raw_content = self._call_claude(system_prompt, transcript, schema)
            else:
                raise ParseError(f"Unsupported LLM engine: {engine}")
        except AssistantError:
            raise
        except Exception as e:
            raise ParseError(f"Error calling {engine}: {e}") from e

        return self._parse_response(raw_content)

    # ------------------------------------------------------------------
    # Backends
    # ------------------------------------------------------------------

    def _call_ollama(self, sys: str, user: str, schema: dict) -> str:
        conf = self.config.ollama
        payload = {
            "model": conf.model,
            "messages": [{"role": "system", "content": sys}, {"role": "user", "content": user}],
            "stream": False,
            "format": schema,
            "options": {"temperature": conf.temperature},
        }
        try:
            resp = self._session.post(f"{conf.base_url}/api/chat", json=payload, timeout=conf.timeout_seconds)
            resp.raise_for_status()
            return resp.json()["message"]["content"]
        except requests.ConnectionError as e:
            raise OllamaUnavailableError(f"Ollama offline at {conf.base_url}") from e
        except requests.Timeout as e:
            raise OllamaTimeoutError("Ollama timed out") from e

    def _call_openai(self, sys: str, user: str, schema: dict) -> str:
        conf = self.config.openai
        if not conf.api_key:
            raise ParseError("OpenAI API key missing in config.yaml")
        
        headers = {"Authorization": f"Bearer {conf.api_key}"}
        payload = {
            "model": conf.model,
            "messages": [{"role": "system", "content": sys}, {"role": "user", "content": user}],
            "temperature": conf.temperature,
            "response_format": {"type": "json_object"}
        }
        try:
            resp = self._session.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers, timeout=60)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except requests.ConnectionError as e:
            raise LLMUnavailableError("OpenAI API is unreachable") from e
        except requests.Timeout as e:
            raise LLMTimeoutError("OpenAI request timed out") from e

    def _call_gemini(self, sys: str, user: str, schema: dict) -> str:
        conf = self.config.gemini
        if not conf.api_key:
            raise ParseError("Gemini API key missing in config.yaml")
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{conf.model}:generateContent?key={conf.api_key}"
        payload = {
            "contents": [{"parts": [{"text": f"System Instruction: {sys}\nUser Prompt: {user}\nRespond in JSON matching the requested schema."}]}],
            "generationConfig": {"temperature": conf.temperature, "responseMimeType": "application/json"}
        }
        try:
            resp = self._session.post(url, json=payload, timeout=60)
            resp.raise_for_status()
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        except requests.ConnectionError as e:
            raise LLMUnavailableError("Gemini API is unreachable") from e
        except requests.Timeout as e:
            raise LLMTimeoutError("Gemini request timed out") from e

    def _call_claude(self, sys: str, user: str, schema: dict) -> str:
        conf = self.config.claude
        if not conf.api_key:
            raise ParseError("Claude API key (Anthropic) missing in config.yaml")
        
        headers = {
            "x-api-key": conf.api_key,
            "anthropic-version": "2023-06-01"
        }
        payload = {
            "model": conf.model,
            "system": sys,
            "messages": [{"role": "user", "content": user + "\n\nProvide the JSON response only."}],
            "max_tokens": 1024,
            "temperature": conf.temperature,
        }
        try:
            resp = self._session.post("https://api.anthropic.com/v1/messages", json=payload, headers=headers, timeout=60)
            resp.raise_for_status()
            return resp.json()["content"][0]["text"]
        except requests.ConnectionError as e:
            raise LLMUnavailableError("Claude API is unreachable") from e
        except requests.Timeout as e:
            raise LLMTimeoutError("Claude request timed out") from e

    # ------------------------------------------------------------------
    # Parsing Helpers
    # ------------------------------------------------------------------

    def _parse_response(self, content: str) -> list[tuple[str, BaseIntent]]:
        json_str = self._extract_json(content)
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ParseError(f"LLM returned invalid JSON: {e}\nRaw: {content}") from e

        if "actions" in data and isinstance(data["actions"], list):
            raw_items = data["actions"]
        else:
            raw_items = [data]

        results: list[tuple[str, BaseIntent]] = []
        for item in raw_items:
            action_name = item.get("action", "unknown")
            parameters = item.get("parameters", {})
            if action_name == "unknown":
                results.append(("unknown", UnknownIntent()))
                continue

            action_cls = self.registry.get(action_name)
            if not action_cls:
                results.append(("unknown", UnknownIntent()))
                continue

            try:
                intent = action_cls.intent_model.model_validate(parameters)
                results.append((action_name, intent))
            except Exception as e:
                raise ParseError(f"Validation failed for '{action_name}': {e}") from e

        return results if results else [("unknown", UnknownIntent())]

    @staticmethod
    def _extract_json(text: str) -> str:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        return match.group(1) if match else text.strip()

    def health_check(self) -> bool:
        if self.config.llm_engine == "ollama":
            try:
                resp = self._session.get(f"{self.config.ollama.base_url}/api/tags", timeout=5)
                return resp.status_code == 200
            except Exception:
                return False
        return True # Assume cloud models are healthy if internet exists
