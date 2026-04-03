"""Ollama-based intent parser — two-pass: Ollama enforces envelope, Pydantic validates params."""

from __future__ import annotations

import datetime
import json
import logging
import re
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from assistant.intent.rule_parser import RuleParseResult

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
        # Cached prompt/schema — rebuilt only when the date rolls over
        self._schema = self.registry.build_ollama_schema()
        self._prompt_date: str = ""
        self._system_prompt: str = ""

    def _get_system_prompt(self) -> str:
        """Return cached system prompt, refreshing it if the date has changed."""
        today = datetime.date.today().isoformat()
        if today != self._prompt_date:
            try:
                tz = str(datetime.datetime.now().astimezone().tzname())
            except Exception:
                tz = "UTC"
            self._system_prompt = self.registry.build_system_prompt(today, tz)
            self._prompt_date = today
        return self._system_prompt

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
            logger.warning("🖥️ Potential prompt injection detected: %r", transcript)
            return [("unknown", UnknownIntent())]

        system_prompt = self._get_system_prompt()
        schema = self._schema

        # Route to specific provider call
        engine = self.config.llm_engine
        try:
            if engine == "ollama":
                raw_content = self._call_ollama(system_prompt, transcript, schema)
            elif engine == "openai":
                raw_content = self._call_openai(system_prompt, transcript)
            elif engine == "gemini":
                raw_content = self._call_gemini(system_prompt, transcript)
            elif engine == "claude":
                raw_content = self._call_claude(system_prompt, transcript)
            else:
                raise ParseError(f"Unsupported LLM engine: {engine}")
        except AssistantError:
            raise
        except Exception as e:
            raise ParseError(f"Error calling {engine}: {e}") from e

        return self._parse_response(raw_content)

    def parse_with_context(
        self,
        transcript: str,
        partial: "RuleParseResult",
    ) -> list[tuple[str, BaseIntent]]:
        """Called when RuleBasedParser has partial results (low confidence or missing slots).

        Prepends a pre-analysis context block to the user message so the LLM only
        has to fill gaps rather than re-parse from scratch. The system prompt and
        schema cache are left untouched.
        """
        context_hint = self._build_partial_context(partial)
        augmented = f"{context_hint}\n\nUser command: {transcript}"
        return self.parse(augmented)

    @staticmethod
    def _build_partial_context(partial: "RuleParseResult") -> str:
        lines = [
            "[RULE PARSER PRE-ANALYSIS — use this to fill gaps; do not contradict filled slots]",
            f"Normalized transcript: {partial.transcript!r}",
            f"Rule confidence: {partial.confidence:.2f}",
        ]
        for action_name, raw_slots in partial.raw_slots.items():
            lines.append(f"Identified action: {action_name}")
            filled = {k: v for k, v in raw_slots.items() if v or v == 0}
            empty = [k for k, v in raw_slots.items() if not v and v != 0]
            for slot, value in filled.items():
                lines.append(f"  Filled slot '{slot}': {value!r}")
            for slot in empty:
                lines.append(f"  Empty slot '{slot}': (needs your resolution)")
        if partial.missing_slots:
            lines.append(
                f"Required slots still missing: {', '.join(partial.missing_slots)}"
            )
        return "\n".join(lines)

    def verify_fast_path_async(
        self,
        transcript: str,
        rule_result: "RuleParseResult",
    ) -> "dict | None":
        """Send the rule-parser's interpretation to the LLM for background severity judgment.

        Returns a correction dict or None (confirmed correct).
        Safe to call from a daemon thread — exceptions are caught and logged.

        Return schema when correction needed:
            {
              "severity": "minor",            # patch a few fields on the existing record
              "patch": {"start_time": "16:00"},
              "speech": "Fixed the time to 4 PM"
            }
            or
            {
              "severity": "major",            # completely wrong — undo + redo
              "action": "create_todo",
              "parameters": {"titles": ["call mom"]},
              "speech": "I think you meant a reminder, not a calendar event"
            }
        """
        try:
            return self._run_verification(transcript, rule_result)
        except Exception as e:
            logger.debug("Fast-path verification skipped: %s", e)
            return None

    def _run_verification(
        self,
        transcript: str,
        rule_result: "RuleParseResult",
    ) -> "dict | None":
        """Build a severity-tiered verification prompt and call the active LLM backend."""
        action_summaries = []
        for action_name, raw_slots in rule_result.raw_slots.items():
            filled = {k: v for k, v in raw_slots.items() if v or v == 0}
            action_summaries.append(
                f"  action={action_name!r}, slots={json.dumps(filled, default=str)}"
            )
        actions_block = "\n".join(action_summaries) if action_summaries else "  (none)"

        verify_sys = (
            "You are a voice-command verifier. A fast rule parser already executed a command. "
            "Judge if it was correct, then respond with ONLY a JSON object — no prose.\n\n"
            "Severity rules:\n"
            '  • Correct → {"ok": true}\n'
            '  • Minor error (wrong time, date, or title but right action) →\n'
            '    {"ok": false, "severity": "minor",\n'
            '     "patch": {<only the fields that need fixing>},\n'
            '     "speech": "<under 15 words for TTS>"}\n'
            '  • Major error (wrong action, wrong entity type) →\n'
            '    {"ok": false, "severity": "major",\n'
            '     "action": "<correct_action_name>",\n'
            '     "parameters": {<full correct params>},\n'
            '     "speech": "<under 15 words for TTS>"}\n'
            "Valid action names: create_event, update_event, delete_event, query_schedule, "
            "create_todo, complete_todo, delete_todo, update_todo, query_todo.\n\n"
            "Key semantic rules for update_event:\n"
            "  • EXTEND/LENGTHEN/SHORTEN/STRETCH: 'to Xpm' is new_end_time (NOT new_start_time).\n"
            "    The event is identified by match_start_time (e.g. 'extend the 1pm event to 3pm'\n"
            "    → match_start_time='13:00', new_end_time='15:00'). This is CORRECT.\n"
            "  • MOVE/RESCHEDULE: 'to Xpm' or 'at Xpm' is new_start_time.\n"
            "  • match_title may be absent when match_start_time uniquely identifies the event —\n"
            "    this is valid, not a missing-slot error.\n"
            "  • Generic words ('event', 'appointment', 'meeting') as match_title are wrong;\n"
            "    the event should be identified by time or its actual name."
        )
        verify_user = (
            f"Voice command: {transcript!r}\n\n"
            f"Rule parser executed:\n{actions_block}\n\n"
            "Judge the severity:"
        )

        engine = self.config.llm_engine
        try:
            if engine == "ollama":
                raw = self._call_ollama_verify(verify_sys, verify_user)
            elif engine == "openai":
                raw = self._call_openai(verify_sys, verify_user)
            elif engine == "gemini":
                raw = self._call_gemini(verify_sys, verify_user)
            elif engine == "claude":
                raw = self._call_claude(verify_sys, verify_user)
            else:
                return None
        except Exception as e:
            logger.debug("Verification LLM call failed: %s", e)
            return None

        json_str = self._extract_json(raw)
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return None

        if data.get("ok") is True:
            logger.debug("🖥️ Background verify: confirmed ✓")
            return None  # silent — rule parser was right

        severity = data.get("severity", "major")
        logger.info(
            "🖥️ Background verify correction — severity=%s action=%r patch=%r",
            severity, data.get("action"), data.get("patch"),
        )
        return data  # pipeline decides what to do with minor vs major

    def _call_ollama_verify(self, sys: str, user: str) -> str:
        """Lightweight Ollama call without format schema — faster for verification."""
        conf = self.config.ollama
        payload = {
            "model": conf.model,
            "messages": [{"role": "system", "content": sys}, {"role": "user", "content": user}],
            "stream": False,
            "options": {"temperature": 0.0},  # deterministic judgment
        }
        resp = self._session.post(
            f"{conf.base_url}/api/chat", json=payload, timeout=25
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]

    # ------------------------------------------------------------------
    # Backends
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_timeout(transcript: str, base: int) -> int:
        """
        Scale timeout by estimated number of actions in the transcript.
        Counts action-separating signals (conjunctions, commas between clauses)
        to guess how many JSON objects the LLM must produce.
        Each extra action adds 15 s on top of the base.
        """
        separators = re.findall(
            r'\b(and also|and then|also|then|plus|additionally|,)\b',
            transcript.lower()
        )
        estimated_actions = 1 + len(separators)
        return base + (estimated_actions - 1) * 15

    def _call_ollama(self, sys: str, user: str, schema: dict) -> str:
        conf = self.config.ollama
        timeout = self._estimate_timeout(user, conf.timeout_seconds)
        logger.debug("Ollama timeout: %ds (estimated %d action(s))", timeout,
                     1 + len(re.findall(r'\b(and also|and then|also|then|plus|additionally|,)\b', user.lower())))
        payload = {
            "model": conf.model,
            "messages": [{"role": "system", "content": sys}, {"role": "user", "content": user}],
            "stream": False,
            "format": schema,
            "options": {"temperature": conf.temperature},
        }
        try:
            resp = self._session.post(f"{conf.base_url}/api/chat", json=payload, timeout=timeout)
            resp.raise_for_status()
            return resp.json()["message"]["content"]
        except requests.ConnectionError as e:
            raise OllamaUnavailableError(f"Ollama offline at {conf.base_url}") from e
        except requests.Timeout as e:
            raise OllamaTimeoutError("Ollama timed out") from e

    def _call_openai(self, sys: str, user: str) -> str:
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

    def _call_gemini(self, sys: str, user: str) -> str:
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

    def _call_claude(self, sys: str, user: str) -> str:
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
