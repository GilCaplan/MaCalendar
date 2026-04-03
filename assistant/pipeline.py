"""Pipeline — orchestrates the full voice-command flow."""

from __future__ import annotations

import datetime
import logging
import os
import queue
import re
import threading
import time
from typing import Callable, List, Optional, Tuple

from assistant.actions import ActionRegistry
from assistant.audio.capture import AudioCapture
from assistant.config import AppConfig
from assistant.confirmation.handler import ConfirmationHandler
from assistant.exceptions import (
    AssistantError,
    AudioCaptureError,
    AuthExpiredError,
    LLMTimeoutError,
    LLMUnavailableError,
    OllamaTimeoutError,
    OllamaUnavailableError,
    ParseError,
)
from assistant.intent.parser import IntentParser, UnknownIntent
from assistant.intent.rule_parser import (
    RULE_THRESHOLD,
    RuleBasedParser,
    RuleParserSkip,
    _RULE_PARSER_AVAILABLE,
)
from assistant.tts.speaker import Speaker

logger = logging.getLogger(__name__)

# Status strings consumed by CalendarWindow via status_queue
STATUS_IDLE = "idle"
STATUS_LISTENING = "listening"
STATUS_PROCESSING = "processing"
STATUS_DONE = "done"
STATUS_ERROR = "error"


def _build_stt(config: AppConfig):
    if config.stt_engine == "whisper":
        from assistant.stt.whisper_stt import WhisperSTT
        return WhisperSTT(config.whisper)
    else:
        from assistant.stt.google_stt import GoogleSTT
        return GoogleSTT(config.google_stt)


class Pipeline:
    """
    Coordinates:
        AudioCapture → STT → IntentParser → ConfirmationHandler → Action.execute()

    Runs on a worker thread; pushes status updates to status_queue for
    the calendar UI to consume on the main thread every 100ms.
    """

    def __init__(self, config: AppConfig, registry: ActionRegistry) -> None:
        self.config = config
        self.registry = registry

        self._audio = AudioCapture(config.audio)
        self._stt = _build_stt(config)
        self._parser = IntentParser(config, registry)
        self._rule_parser: Optional[RuleBasedParser] = (
            RuleBasedParser(registry) if _RULE_PARSER_AVAILABLE else None
        )
        self._confirmer = ConfirmationHandler(config.confirmation_level)
        self._tts = Speaker(config.tts)

        self.status_queue: queue.Queue[str] = queue.Queue()
        self._busy = threading.Event()
        self._trigger_lock = threading.Lock()
        self._phase = STATUS_IDLE  # tracks current stage for button re-press logic
        # Pending session mode: None = no queue, "new" = fresh session, "combine" = append to last transcript
        self._queued: Optional[str] = None
        self._last_transcript: str = ""  # retained for combine mode

        self.on_auth_expired: Optional[Callable[[], None]] = None
        # Set by the UI when the active view changes; used to inject parse context
        self.current_view: str = "month"

    def trigger(self) -> None:
        """Called by HotkeyListener or mic button.

        While idle → start a new session.
        While listening → stop recording immediately.
        While processing, cycles through:
          1st press → queue a new independent session
          2nd press → switch to combine mode (new audio appended to previous transcript)
          3rd press → cancel the queued session
        """
        with self._trigger_lock:
            if self._busy.is_set():
                if self._phase == STATUS_LISTENING:
                    self.stop_recording()
                elif self._queued is None:
                    self._queued = "new"
                    self._set_status(STATUS_PROCESSING, "🕐 Queued — tap again to combine instead")
                elif self._queued == "new":
                    self._queued = "combine"
                    self._set_status(STATUS_PROCESSING, "🔗 Will combine with previous — tap again to cancel")
                else:
                    self._queued = None
                    self._set_status(STATUS_PROCESSING, "⏸ Queued session cancelled")
                return
            # Mark busy before spawning so rapid re-triggers see it immediately
            self._busy.set()
        threading.Thread(target=self._run, daemon=True).start()

    def stop_recording(self) -> None:
        """Stop the current recording immediately (button re-press or external call)."""
        self._audio.stop()

    def health_check(self) -> dict:
        return {"ollama": self._parser.health_check()}

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run(self, combine: bool = False) -> None:
        try:
            self._run_pipeline(combine=combine)
        finally:
            self._busy.clear()
            # If a session was queued while we were busy, kick it off now
            with self._trigger_lock:
                next_mode = self._queued
                if next_mode is not None:
                    self._queued = None
                    self._busy.set()
                    threading.Thread(
                        target=self._run,
                        kwargs={"combine": next_mode == "combine"},
                        daemon=True,
                    ).start()

    def _run_pipeline(self, combine: bool = False) -> None:
        t_start = time.perf_counter()

        # 1. Listen
        self._phase = STATUS_LISTENING
        listen_hint = "🔗 Listening to add on… (say 'done' or press mic to stop)" if combine else "🎙 Listening… (say 'done' or press mic to stop)"
        self._set_status(STATUS_LISTENING, listen_hint)

        # Stream-checker: transcribe growing buffer every 2.5 s to detect stop words.
        # Cache the last result so we can reuse it and skip the final full transcription.
        _last_partial: List[str] = ["", 0.0]  # [transcript, timestamp]

        def stream_checker(audio_buffer) -> None:
            if self._phase != STATUS_LISTENING:
                return
            try:
                partial = self._stt.transcribe(audio_buffer).lower()
                _last_partial[0] = partial
                _last_partial[1] = time.perf_counter()
                if re.search(r'\b(execute|done|stop|end|go)\b', partial):
                    logger.info("🖥️ Early termination detected in stream: %s", partial)
                    self.stop_recording()
            except Exception as e:
                logger.error("Stream checker error: %s", e)

        try:
            audio = self._audio.record_until_silence(
                streaming_callback=stream_checker,
                streaming_interval_sec=2.5
            )
        except AudioCaptureError as e:
            msg = str(e)
            if "already in progress" in msg:
                logger.warning("🖥️ Audio capture blocked: already in progress.")
                self._set_status(STATUS_IDLE, "")
            else:
                self._tts.speak("Microphone error. Please check your audio settings.")
                logger.error("🖥️ Audio capture error: %s", e)
                self._set_status(STATUS_ERROR, "⚠️ Microphone error")
            return

        t_recorded = time.perf_counter()
        logger.info("🖥️ ⏱ Recording: %.2fs", t_recorded - t_start)

        # 2. Transcribe — reuse stream-checker result if it's fresh (within 3 s)
        self._phase = STATUS_PROCESSING
        partial_text, partial_ts = _last_partial
        reuse = partial_text and (t_recorded - partial_ts) < 3.0

        if reuse:
            transcript = partial_text
            logger.info("🖥️ ⏱ Transcription: reused stream-checker result (0.00s)")
        else:
            self._set_status(STATUS_PROCESSING, "⏳ Transcribing…")
            try:
                transcript = self._stt.transcribe(audio)
            except AssistantError as e:
                self._tts.speak("I couldn't understand that. Please try again.")
                logger.error("🖥️ STT error: %s", e)
                self._set_status(STATUS_ERROR, "⚠️ Transcription failed")
                return
            logger.info("🖥️ ⏱ Transcription: %.2fs", time.perf_counter() - t_recorded)

        if not transcript or len(transcript.strip()) < 3:
            self._tts.speak("I didn't catch that.")
            self._set_status(STATUS_IDLE, "")
            return

        # Strip stop keywords from the tail of the transcript
        transcript = _strip_stop_keyword(transcript)

        # Combine mode: prepend previous transcript so the LLM sees one unified request
        if combine and self._last_transcript:
            transcript = self._last_transcript + ", " + transcript
            logger.info("🖥️ Combined transcript: %s", transcript)

        # Save clean transcript for potential future combine session
        self._last_transcript = transcript

        # Inject view context so the LLM biases routing appropriately
        if self.current_view == "todo":
            transcript = "[TASKS VIEW] " + transcript

        logger.info("🖥️ Transcript (cleaned): %s", transcript)
        snippet = transcript[:60] + ("…" if len(transcript) > 60 else "")
        self._set_status(STATUS_PROCESSING, f'💭 "{snippet}"')

        # 3. Parse intent(s) — try rule-based fast-path first
        t_llm = time.perf_counter()
        action_list = None
        _fast_path_rule_result = None  # set when fast-path executes, used for background verify

        if self._rule_parser is not None:
            try:
                rule_result = self._rule_parser.analyze(transcript, current_view=self.current_view)
                if rule_result.confidence >= RULE_THRESHOLD and not rule_result.missing_slots:
                    action_list = rule_result.intents
                    _fast_path_rule_result = rule_result
                    logger.info(
                        "🖥️ Rule fast-path: confidence=%.2f actions=%s (%.3fs)",
                        rule_result.confidence,
                        [n for n, _ in action_list],
                        time.perf_counter() - t_llm,
                    )
                else:
                    logger.info(
                        "🖥️ Rule partial handoff: confidence=%.2f missing=%s",
                        rule_result.confidence, rule_result.missing_slots,
                    )
                    self._set_status(STATUS_PROCESSING, "💭 Clarifying with AI…")
                    try:
                        action_list = self._parser.parse_with_context(transcript, rule_result)
                    except (LLMUnavailableError, OllamaUnavailableError):
                        pass  # handled below
            except RuleParserSkip as e:
                logger.debug("🖥️ Rule parser skipped: %s", e)

        if action_list is None:
            self._set_status(STATUS_PROCESSING, "💭 Thinking…")
            try:
                action_list = self._parser.parse(transcript)
            except (LLMUnavailableError, OllamaUnavailableError):
                engine = self.config.llm_engine
                self._tts.speak(f"The {engine} assistant is offline. Please check your connection and try again.")
                self._set_status(STATUS_ERROR, f"⚠️ {engine.title()} offline")
                return
            except (LLMTimeoutError, OllamaTimeoutError):
                engine = self.config.llm_engine
                self._tts.speak(f"The {engine} assistant is taking too long to respond.")
                self._set_status(STATUS_ERROR, f"⚠️ {engine.title()} timeout")
                return
            except ParseError as e:
                self._tts.speak("I couldn't understand that request.")
                logger.error("🖥️ Parse error: %s", e)
                self._set_status(STATUS_ERROR, "⚠️ Couldn't parse request")
                self._append_scenario_bug(
                    transcript,
                    issue_type="parse_error",
                    details=str(e),
                )
                return

        logger.info("🖥️ ⏱ Parse total: %.2fs", time.perf_counter() - t_llm)

        # Filter unknowns
        valid = [(name, intent) for name, intent in action_list
                 if name != "unknown" and not isinstance(intent, UnknownIntent)]

        if not valid:
            self._tts.speak("I'm not sure what you'd like me to do.")
            self._set_status(STATUS_IDLE, "")
            self._append_scenario_bug(
                transcript,
                issue_type="unknown_intent",
                details="LLM returned no recognisable action (all results were UnknownIntent).",
            )
            return

        # 4. Confirm + execute each action
        t_exec = time.perf_counter()
        results: List[str] = []
        for action_name, intent in valid:
            if action_name == "clarify":
                pass  # never prompt confirmation for a clarification question
            elif not self._confirmer.check(action_name, intent):
                self._tts.speak("Cancelled.")
                self._set_status(STATUS_IDLE, "")
                return

            action_cls = self.registry.get(action_name)
            if action_cls is None:
                logger.warning("🖥️ Unknown action '%s'", action_name)
                continue

            try:
                self._set_status(STATUS_PROCESSING, f"⚙️ Executing {action_name.replace('_', ' ')}…")
                result_text = action_cls().execute(intent, self.config)
                results.append(result_text)
                logger.info("🖥️ Action '%s' complete: %s", action_name, result_text)
            except AuthExpiredError as e:
                self._tts.speak("Microsoft login expired. Use Re-authenticate in the menu.")
                logger.error("🖥️ Auth expired: %s", e)
                self._set_status(STATUS_ERROR, "⚠️ Auth expired")
                if self.on_auth_expired:
                    self.on_auth_expired()
                return
            except AssistantError as e:
                self._tts.speak("Something went wrong. Check the logs for details.")
                logger.error("🖥️ Action error: %s", e)
                self._set_status(STATUS_ERROR, "⚠️ Action failed")
                self._append_scenario_bug(
                    transcript,
                    issue_type="action_failed",
                    details=f"Action {action_name!r} raised: {e}",
                    extra={"Intent": str(intent)},
                )
                return
        logger.info("🖥️ ⏱ Execute: %.2fs", time.perf_counter() - t_exec)

        if results:
            summary = " ".join(results)
            # Clarify-only responses don't touch the calendar — go straight to idle
            is_clarify = all(name == "clarify" for name, _ in valid)
            if is_clarify:
                self._tts.speak_sync(summary)
                self._set_status(STATUS_IDLE, "")
                return
            # Check if any executed action requested a UI view switch
            view_switch = next(
                (getattr(self.registry.get(n), "view_switch", None) for n, _ in valid
                 if getattr(self.registry.get(n), "view_switch", None)),
                None,
            )
            ui_status = view_switch if view_switch else "refresh"
            self._set_status(ui_status, results[0][:80])
            self._tts.speak(summary)
            time.sleep(0.3)  # brief pause for UI toast to render before going idle

            # Background LLM verification of fast-path results (does not block user)
            if (
                _fast_path_rule_result is not None
                and self.config.verify_fast_path
                and not is_clarify
            ):
                # Snapshot what the fast-path just created/modified so we can detect
                # user-changed-in-between and undo creates for major corrections.
                from assistant.intent.context import context_memory
                verify_snapshot = {
                    "actions": [(name, type(intent).__name__) for name, intent in valid],
                    "event_id": context_memory.last_event_id,
                    "event_title": context_memory.last_event_title,
                    "event_date": context_memory.last_event_date,
                    "todo_id": context_memory.last_todo_id,
                    "todo_title": context_memory.last_todo_title,
                }
                threading.Thread(
                    target=self._background_verify,
                    args=(transcript, _fast_path_rule_result, verify_snapshot),
                    daemon=True,
                ).start()

        logger.info("🖥️ ⏱ Total pipeline: %.2fs", time.perf_counter() - t_start)
        self._phase = STATUS_IDLE
        self._set_status(STATUS_IDLE, "")

    def _background_verify(self, transcript: str, rule_result, snapshot: dict) -> None:
        """Daemon thread: LLM judges the fast-path result in three tiers.

        Tier 1 — ok:    Silent. Rule parser was right.
        Tier 2 — minor: Silently PATCH the existing record with corrected fields.
                        Speaks a brief correction only when audibly meaningful.
        Tier 3 — major: Completely wrong action/entity.
                        Undo the fast-path record (if it was a create), then
                        re-execute with the LLM-corrected intent.

        Before applying any correction, checks if the user already modified the
        record (manual edit, another voice command, etc.). If so, skips the
        correction — the user's change acts as implicit feedback.
        """
        from assistant.db import get_db

        logger.debug("🖥️ Background verify starting for: %r", transcript)
        correction = self._parser.verify_fast_path_async(transcript, rule_result)
        if correction is None:
            return  # tier 1 — confirmed correct, silent

        severity = correction.get("severity", "major")
        speech = correction.get("speech", "")
        action_names = [name for name, _ in snapshot.get("actions", [])]

        # ---------------------------------------------------------------
        # Guard: did the user already change the record?
        # ---------------------------------------------------------------
        db = get_db()
        user_changed = self._detect_user_change(db, snapshot, action_names)
        if user_changed:
            logger.info(
                "🖥️ Background verify: user already changed record — skipping correction, "
                "treating as implicit feedback that rule parser was wrong for: %r", transcript
            )
            return

        # Log the mistake scenario before applying any correction
        severity = correction.get("severity", "major")
        fast_path_summary = ", ".join(
            f"{name}({rule_result.raw_slots.get(name, {})})"
            for name, _ in snapshot.get("actions", [])
        )
        if severity == "minor":
            detail = (
                f"Rule parser was slightly off. "
                f"Fast-path: {fast_path_summary}. "
                f"LLM patch: {correction.get('patch', {})}"
            )
        else:
            detail = (
                f"Rule parser chose wrong action. "
                f"Fast-path: {fast_path_summary}. "
                f"LLM says: action={correction.get('action')} "
                f"params={correction.get('parameters', {})}"
            )
        self._append_scenario_bug(
            transcript,
            issue_type=f"fast_path_wrong/{severity}",
            details=detail,
            extra={"Speech correction": correction.get("speech", "")} if correction.get("speech") else None,
        )

        # ---------------------------------------------------------------
        # Tier 2 — minor: patch the existing record
        # ---------------------------------------------------------------
        if severity == "minor":
            patch = correction.get("patch", {})
            if not patch:
                return
            applied = False
            event_id = snapshot.get("event_id")
            todo_id = snapshot.get("todo_id")
            try:
                if event_id and any("event" in a for a in action_names):
                    db.update_event(event_id, **patch)
                    applied = True
                elif todo_id and any("todo" in a for a in action_names):
                    db.update_todo(todo_id, **patch)
                    applied = True
            except Exception as exc:
                logger.warning("🖥️ Minor patch failed: %s", exc)
                return
            if applied:
                logger.info("🖥️ Background verify: minor patch applied %s", patch)
                self._set_status("refresh", speech[:80] if speech else "")
                if speech:
                    self._tts.speak(speech)
            return

        # ---------------------------------------------------------------
        # Tier 3 — major: undo fast-path create, re-execute with LLM
        # ---------------------------------------------------------------
        corrected_action = correction.get("action")
        corrected_params = correction.get("parameters", {})
        if not corrected_action:
            return

        # Undo: only safe for creates (delete/update originals are already gone/changed)
        for action_name in action_names:
            if action_name == "create_event":
                event_id = snapshot.get("event_id")
                if event_id:
                    try:
                        db.delete_event(event_id)
                        logger.info("🖥️ Background verify: undid create_event id=%d", event_id)
                    except Exception as exc:
                        logger.warning("🖥️ Undo create_event failed: %s", exc)
                        return
            elif action_name == "create_todo":
                todo_id = snapshot.get("todo_id")
                if todo_id:
                    try:
                        db.delete_todo(todo_id)
                        logger.info("🖥️ Background verify: undid create_todo id=%d", todo_id)
                    except Exception as exc:
                        logger.warning("🖥️ Undo create_todo failed: %s", exc)
                        return

        # Re-execute with corrected intent
        action_cls = self.registry.get(corrected_action)
        if action_cls is None:
            logger.warning("🖥️ Correction action %r not in registry", corrected_action)
            return
        try:
            intent = action_cls.intent_model.model_validate(corrected_params)
            result_text = action_cls().execute(intent, self.config)
            logger.info("🖥️ Background verify: major correction executed → %s", result_text)
            combined = f"{speech} {result_text}".strip() if speech else result_text
            self._set_status("refresh", combined[:80])
            self._tts.speak(combined)
        except Exception as exc:
            logger.error("🖥️ Major correction execution failed: %s", exc)
            self._append_scenario_bug(
                transcript,
                issue_type="correction_failed",
                details=f"LLM correction action={corrected_action!r} failed to execute: {exc}",
                extra={"Corrected params": corrected_params},
            )

    @staticmethod
    def _detect_user_change(db, snapshot: dict, action_names: list[str]) -> bool:
        """Return True if the record was externally modified since the fast-path ran.

        Compares key fields (title, date, start_time) between the snapshot taken
        right after execution and the current DB state. A mismatch means the user
        (or another command) already touched the record.
        """
        event_id = snapshot.get("event_id")
        todo_id = snapshot.get("todo_id")

        if event_id and any("event" in a for a in action_names):
            current = db.get_event(event_id)
            if current is None:
                return True  # deleted — user changed it
            if snapshot.get("event_title") and current.get("title") != snapshot["event_title"]:
                return True
        if todo_id and any("todo" in a for a in action_names):
            current = db.get_todo(todo_id)
            if current is None:
                return True  # deleted — user changed it
            if snapshot.get("todo_title") and current.get("title") != snapshot["todo_title"]:
                return True
        return False

    @staticmethod
    def _append_scenario_bug(
        transcript: str,
        issue_type: str,
        details: str,
        extra: "dict | None" = None,
    ) -> None:
        """Append any failure scenario to DOCUMENTATION/SCENARIO_BUG.md.

        Args:
            transcript:  The raw user transcript that triggered the issue.
            issue_type:  Short label, e.g. "parse_error", "unknown_intent",
                         "action_failed", "fast_path_wrong", "correction_failed".
            details:     Human-readable description of what went wrong
                         (error message, mismatch description, etc.).
            extra:       Optional dict of additional key→value pairs to include.
        """
        try:
            repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            path = os.path.join(repo_root, "DOCUMENTATION", "SCENARIO_BUG.md")
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            lines = [
                f"## [{ts}] {issue_type}\n",
                f"**Transcript:** `{transcript}`\n\n",
                f"**Issue:** {details}\n",
            ]
            if extra:
                for key, val in extra.items():
                    lines.append(f"\n**{key}:** `{val}`\n")
            lines.append("\n---\n\n")

            with open(path, "a", encoding="utf-8") as f:
                f.writelines(lines)

            logger.debug("🖥️ Scenario bug appended (%s): %s", issue_type, details[:80])
        except Exception as exc:
            logger.warning("🖥️ Could not append scenario bug: %s", exc)

    def _set_status(self, status: str, message: str = "") -> None:
        """Push (status, message) to the queue. Message is shown as a UI toast."""
        self.status_queue.put((status, message))


# ---------------------------------------------------------------------------
# Stop-keyword helper
# ---------------------------------------------------------------------------

# Ordered longest-first so "set events" matches before "set event"
_STOP_PATTERNS = [
    r"\bset\s+events?\b",
    r"\bexecute\b",
    r"\bdone\b",
    r"\bstop\b",
    r"\bsubmit\b",
    r"\bconfirm\b",
    r"\bthat'?s?\s+it\b",
    r"\bok\s+go\b",
]
_STOP_RE = re.compile(
    r"[\s,.!?]*(?:" + "|".join(_STOP_PATTERNS) + r")[\s,.!?]*$",
    re.IGNORECASE,
)


def _strip_stop_keyword(transcript: str) -> str:
    """Remove trailing stop keywords from the transcript."""
    cleaned = _STOP_RE.sub("", transcript).strip()
    return cleaned if cleaned else transcript
