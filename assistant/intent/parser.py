"""Ollama-based intent parser — two-pass: Ollama enforces envelope, Pydantic validates params."""

from __future__ import annotations

import datetime
import json
import logging
import re
import time
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
        # Diagnostics for the thinking trace
        self.last_llm_ms: int = 0
        self.last_raw_response: str = ""
        self.last_examples_used: int = 0

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

        # Personalisation: similar past commands (+ user corrections) as few-shot.
        # Appended to the USER message, not the system prompt: Ollama caches the
        # KV state of an unchanged prompt prefix, so keeping the (long) system
        # prompt byte-identical between calls skips most prompt processing.
        examples_block = self._few_shot_for(transcript)
        user_msg = f"{transcript}\n\n{examples_block}" if examples_block else transcript
        self.last_examples_used = examples_block.count("\n- ") if examples_block else 0

        # Route to specific provider call
        engine = self.config.llm_engine
        t0 = time.perf_counter()
        try:
            if engine == "ollama":
                raw_content = self._call_ollama(system_prompt, user_msg, schema)
            elif engine == "openai":
                raw_content = self._call_openai(system_prompt, user_msg)
            elif engine == "gemini":
                raw_content = self._call_gemini(system_prompt, user_msg)
            elif engine == "claude":
                raw_content = self._call_claude(system_prompt, user_msg)
            else:
                raise ParseError(f"Unsupported LLM engine: {engine}")
        except AssistantError:
            raise
        except Exception as e:
            raise ParseError(f"Error calling {engine}: {e}") from e
        finally:
            self.last_llm_ms = int((time.perf_counter() - t0) * 1000)

        self.last_raw_response = raw_content
        return self._parse_response(raw_content)

    def _few_shot_for(self, transcript: str) -> str:
        k = getattr(self.config.nlu, "memory_examples", 0)
        if not k:
            return ""
        try:
            from assistant.intent.memory import get_memory
            # Strip context prefixes so retrieval sees the user's words only
            plain = transcript.split("User command:", 1)[-1].replace("[TASKS VIEW]", "").strip()
            return get_memory().few_shot_block(plain, k=k)
        except Exception as e:  # memory must never break parsing
            logger.debug("Memory few-shot skipped: %s", e)
            return ""

    def warm_up(self) -> None:
        """Preload the Ollama model so the first real command doesn't pay the load cost."""
        if self.config.llm_engine != "ollama":
            return
        conf = self.config.ollama
        for model in dict.fromkeys([conf.model, conf.verify_model or conf.model]):
            try:
                self._session.post(
                    f"{conf.base_url}/api/generate",
                    json={"model": model, "keep_alive": conf.keep_alive, "options": {"num_ctx": conf.num_ctx}},
                    timeout=120,
                )
                logger.info("Ollama model %s warmed (keep_alive=%s)", model, conf.keep_alive)
            except Exception as e:
                logger.warning("Ollama warm-up of %s failed: %s", model, e)

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
        # "due thursday" with no clock time is a deadline, not an appointment.
        # The rule parser sometimes reads such a sentence as create_event, and
        # then this hint never fired: "book the driving test due next monday"
        # came back as a 9 AM event.
        _text = getattr(partial, "transcript", "") or ""
        _says_due = re.search(r"\bdue\b", _text, re.IGNORECASE)
        _says_a_clock_time = re.search(
            r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b|\bat\s+\d{1,2}\b|\bnoon\b|\bmidnight\b",
            _text, re.IGNORECASE)
        if any(a == "create_todo" for a in partial.raw_slots) or (_says_due and not _says_a_clock_time):
            lines.append("This is a TASK command: return create_todo action(s) only — do NOT add a create_event.")
        if getattr(partial, "dropped_spans", 0):
            lines.append(f"NOTE: the rule parser could only interpret part of the command ({partial.dropped_spans} clause(s) were skipped). "
                         "Re-read the FULL user command and return EVERY action it contains — there are probably more than listed above.")
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

    @staticmethod
    def _strip_datetime_words(title: str) -> str:
        """'Meeting Tomorrow at 4pm' → 'Meeting'; keeps names/places."""
        t = re.sub(r"\b(?:at|from|until|till|to)\s+\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)?\b", "", title, flags=re.I)
        t = re.sub(r"\b(?:today|tonight|tomorrow|yesterday|this|next|coming)\s+(?:morning|evening|night|week|weekend|"
                   r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", "", t, flags=re.I)
        t = re.sub(r"\b(?:today|tonight|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", "", t, flags=re.I)
        t = re.sub(r"\b(?:on\s+)?the\s+\d{1,2}(?:st|nd|rd|th)\b", "", t, flags=re.I)
        t = re.sub(r"\b\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm)\b", "", t, flags=re.I)
        t = re.sub(r"\s{2,}", " ", t).strip(" ,-–")
        t = re.sub(r"\s+(?:on|at|in|for|from|to|until|till|with|and)$", "", t, flags=re.I)
        return t.strip()

    def fix_title_async(self, transcript: str, keyword: str) -> "str | None":
        """Ask the LLM for a proper event title when fast-path used a keyword placeholder.

        Returns an improved title string, or None if the LLM couldn't improve on the keyword.
        Safe to call from a daemon thread — exceptions are caught and logged.
        """
        sys_prompt = (
            "You are a calendar assistant. Given a voice command transcript, "
            "produce a concise, properly-cased event title.\n"
            "Rules: 2-6 words, title case, no punctuation at end, no explanation.\n"
            "The title names the activity and who/where (e.g. 'Meeting with Ravid at Kems', 'Dentist Appointment'). "
            "NEVER include the date, weekday, or time — those are stored separately.\n"
            "Respond with ONLY a JSON object: {\"title\": \"<event title>\"}"
        )
        user_prompt = (
            f"Voice transcript: {transcript!r}\n"
            f"Current placeholder title: {keyword!r}\n"
            "What is the proper event title?"
        )
        try:
            engine = self.config.llm_engine
            if engine == "ollama":
                raw = self._call_ollama_verify(self._get_system_prompt(), "[SIDE TASK — ignore the JSON-envelope instructions above for this message]\n" + sys_prompt + "\n\n" + user_prompt)
            elif engine == "openai":
                raw = self._call_openai(sys_prompt, user_prompt)
            elif engine == "gemini":
                raw = self._call_gemini(sys_prompt, user_prompt)
            elif engine == "claude":
                raw = self._call_claude(sys_prompt, user_prompt)
            else:
                return None
            json_str = self._extract_json(raw)
            data = json.loads(json_str)
            title = data.get("title", "").strip().strip("\"'")
            if title and title.lower() != keyword.lower():
                logger.debug("fix_title_async: %r → %r", keyword, title)
                title = self._strip_datetime_words(title) or None
                if not title or title.strip().lower() == keyword.strip().lower():
                    return None
                return title
        except Exception as exc:
            logger.debug("fix_title_async failed: %s", exc)
        return None

    def call_llm_json(self, sys_prompt: str, user_prompt: str) -> dict:
        """Generic one-shot structured-output call to whichever LLM engine is configured.

        For actions that need free-form structured JSON from the LLM outside the
        normal intent-routing envelope (e.g. workout routine generation) — reuses
        the same per-provider HTTP call paths as parse()/fix_title_async(), no new
        request path. Raises ParseError on an unsupported engine, requests errors,
        or invalid JSON; caller decides how to handle validation of the parsed dict.
        """
        engine = self.config.llm_engine
        try:
            if engine == "ollama":
                raw = self._call_ollama_verify(self._get_system_prompt(), "[SIDE TASK — ignore the JSON-envelope instructions above for this message]\n" + sys_prompt + "\n\n" + user_prompt)
            elif engine == "openai":
                raw = self._call_openai(sys_prompt, user_prompt)
            elif engine == "gemini":
                raw = self._call_gemini(sys_prompt, user_prompt)
            elif engine == "claude":
                raw = self._call_claude(sys_prompt, user_prompt)
            else:
                raise ParseError(f"Unsupported LLM engine: {engine}")
        except AssistantError:
            raise
        except Exception as e:
            raise ParseError(f"Error calling {engine}: {e}") from e

        json_str = self._extract_json(raw)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ParseError(f"LLM returned invalid JSON: {e}\nRaw: {raw}") from e

    def _run_verification(
        self,
        transcript: str,
        rule_result: "RuleParseResult",
    ) -> "dict | None":
        """Build a severity-tiered verification prompt and call the active LLM backend.

        Judged against the *validated intents*, which is what actually reached
        the database — not `raw_slots`, which is the rule parser's working
        state from before CalendarIntent filled its defaults. The difference is
        not cosmetic: raw slots carry `end_time: ""` on every single
        create_event, because the end is derived later. Shown that, the
        verifier correctly observes that the event has no end time and patches
        one in — onto a record that already had the right one. That is most of
        how this feature came to propose corrections on ~96% of commands and
        fix nothing, which is why it was switched off.
        """
        action_summaries = []
        for action_name, intent in rule_result.intents:
            if hasattr(intent, "model_dump"):
                params = intent.model_dump(exclude_none=True)
                params = {k: v for k, v in params.items() if v or v == 0}
            elif isinstance(intent, dict):
                params = intent
            else:
                params = {}
            action_summaries.append(
                f"  action={action_name!r}, parameters={json.dumps(params, default=str)}"
            )
        actions_block = "\n".join(action_summaries) if action_summaries else "  (none)"
        return self._verify_block(transcript, actions_block, "A fast rule parser")

    def verify_actions_async(
        self,
        transcript: str,
        executed: "list[tuple[str, object]]",
    ) -> "dict | None":
        """Post-execution self-check for ANY parse path (rule, hybrid, llm).

        Re-reasons over the transcript, what was actually executed, and this
        user's similar past commands (memory) and returns the same three-tier
        correction dict as verify_fast_path_async, or None if it agrees.
        Safe to call from a daemon thread.
        """
        try:
            summaries = []
            for name, intent in executed:
                if hasattr(intent, "model_dump"):
                    params = intent.model_dump(exclude_none=True, exclude_defaults=True)
                elif isinstance(intent, dict):
                    params = intent
                else:
                    params = {}
                summaries.append(f"  action={name!r}, parameters={json.dumps(params, default=str)}")
            block = "\n".join(summaries) if summaries else "  (none)"
            return self._verify_block(transcript, block, "The assistant")
        except Exception as e:
            logger.debug("Post-execution verification skipped: %s", e)
            return None

    def _verify_block(self, transcript: str, actions_block: str, who: str) -> "dict | None":
        history = self._few_shot_for(transcript)

        verify_sys = (
            f"You are a voice-command verifier. {who} already executed a command. "
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
            f"Valid action names: {', '.join(self.registry.all_names())}.\n\n"
            "Default to agreement. Most commands are interpreted correctly, and a\n"
            "wrong 'correction' overwrites a record the user is already happy with.\n"
            'Return {"ok": true} unless you can name a definite error. In particular:\n'
            "  • The parameters shown are the FINAL stored values, after defaults were\n"
            "    applied. An end time the speaker never said is not missing and not\n"
            "    wrong — it was derived. Never patch a field just to fill it in.\n"
            "  • Never patch a field to a value the speaker did not state.\n"
            "  • Casing, punctuation and word order in a title are not errors.\n"
            "  • If you disagree only about style or phrasing, that is ok:true.\n"
            '  • If something is off but you cannot say what the value should be,\n'
            '    return {"ok": true} rather than a guess.\n\n'
            "Key routing rules (apply these FIRST before judging):\n"
            "  • If the command says 'set/create/schedule/book a meeting/appointment/call/session'\n"
            "    AND includes a specific time or date → it is ALWAYS create_event. Never create_todo.\n"
            "  • 'Meeting', 'appointment', 'call', 'session' with a time are calendar events, not tasks.\n"
            "  • Only classify as create_todo when the request is clearly a task/reminder with no\n"
            "    scheduled time (e.g. 'remind me to buy groceries', 'add task: call dentist').\n"
            "  • The title for create_event may be a generic word like 'meeting' or 'appointment' —\n"
            "    that is CORRECT as a title; do not flag it as wrong.\n\n"
            "Key semantic rules for update_event:\n"
            "  • EXTEND/LENGTHEN/SHORTEN/STRETCH: 'to Xpm' is new_end_time (NOT new_start_time).\n"
            "    The event is identified by match_start_time (e.g. 'extend the 1pm event to 3pm'\n"
            "    → match_start_time='13:00', new_end_time='15:00'). This is CORRECT.\n"
            "  • MOVE/RESCHEDULE: 'to Xpm' or 'at Xpm' is new_start_time.\n"
            "  • match_title may be absent when match_start_time uniquely identifies the event —\n"
            "    this is valid, not a missing-slot error.\n"
            "  • Generic words ('event', 'appointment', 'meeting') as match_title for update/delete\n"
            "    are ambiguous; the event should be identified by time or its actual name."
        )
        # The verifier instructions go in the USER turn and the system prompt is
        # the same one the parser uses: Ollama caches the KV state of an
        # unchanged prompt prefix, so alternating parse/verify calls with two
        # different system prompts would re-process ~4k tokens every time.
        verify_user = (
            "[VERIFICATION TASK — ignore the JSON-envelope instructions above for this message]\n"
            + verify_sys + "\n\n"
            + f"Voice command: {transcript!r}\n\n"
            f"Executed:\n{actions_block}\n\n"
            + (history + "\nIf the executed interpretation contradicts how this user's similar past "
               "commands were (correctly) interpreted, prefer the user's history.\n\n" if history else "")
            + "Judge the severity:"
        )
        verify_sys = self._get_system_prompt()

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

        # Severity decides between patching a field and undoing the record and
        # rebuilding it, so an absent one must never default to the destructive
        # branch. Infer it from what the verdict actually carries: a full
        # replacement action means major, a field patch means minor, and a
        # bare {"ok": false} with neither is not actionable — the model has
        # said it is unhappy without saying what to do, and acting on that is
        # guessing. Treat it as agreement.
        severity = data.get("severity")
        if severity not in ("minor", "major"):
            if data.get("action"):
                severity = "major"
            elif data.get("patch"):
                severity = "minor"
            else:
                logger.info("🖥️ Background verify: not-ok with no action or patch — ignoring")
                return None
            data["severity"] = severity

        if severity == "minor" and not data.get("patch"):
            logger.info("🖥️ Background verify: minor with an empty patch — ignoring")
            return None

        logger.info(
            "🖥️ Background verify correction — severity=%s action=%r patch=%r",
            severity, data.get("action"), data.get("patch"),
        )
        return data  # pipeline decides what to do with minor vs major

    def _call_ollama_verify(self, sys: str, user: str) -> str:
        """Verification call — uses the (optionally stronger) `verify_model`."""
        conf = self.config.ollama
        payload = {
            "model": conf.verify_model or conf.model,
            "messages": [{"role": "system", "content": sys}, {"role": "user", "content": user}],
            "stream": False,
            "keep_alive": conf.keep_alive,
            "options": {"temperature": 0.0, "num_ctx": conf.num_ctx},  # deterministic judgment
        }
        resp = self._session.post(
            f"{conf.base_url}/api/chat", json=payload, timeout=60
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
            "keep_alive": conf.keep_alive,
            "options": {"temperature": conf.temperature, "num_ctx": conf.num_ctx},
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

        # Propagate title across create_event batch items — handles "another one" anaphora
        # where the LLM returns an empty title for the second/third event.
        last_create_title: str | None = None
        for item in raw_items:
            if item.get("action") == "create_event":
                params = item.setdefault("parameters", {})
                t = params.get("title", "")
                if t and str(t).strip():
                    last_create_title = str(t).strip()
                elif last_create_title:
                    params["title"] = last_create_title

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
