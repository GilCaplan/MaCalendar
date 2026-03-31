"""Pipeline — orchestrates the full voice-command flow."""

from __future__ import annotations

import logging
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
        # 1. Listen
        self._phase = STATUS_LISTENING
        listen_hint = "🔗 Listening to add on… (say 'done' or press mic to stop)" if combine else "🎙 Listening… (say 'done' or press mic to stop)"
        self._set_status(STATUS_LISTENING, listen_hint)

        def stream_checker(audio_buffer) -> None:
            if self._phase != STATUS_LISTENING:
                return
            try:
                partial = self._stt.transcribe(audio_buffer).lower()
                import re
                if re.search(r'\b(execute|done|stop|end)\b', partial):
                    logger.info("Early termination text detected implicitly in stream: %s", partial)
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
                logger.warning("Audio capture blocked: already in progress.")
                self._set_status(STATUS_IDLE, "")
            else:
                self._tts.speak("Microphone error. Please check your audio settings.")
                logger.error("Audio capture error: %s", e)
                self._set_status(STATUS_ERROR, "⚠️ Microphone error")
            return

        # 2. Transcribe
        self._phase = STATUS_PROCESSING
        self._set_status(STATUS_PROCESSING, "⏳ Transcribing…")
        try:
            transcript = self._stt.transcribe(audio)
        except AssistantError as e:
            self._tts.speak("I couldn't understand that. Please try again.")
            logger.error("STT error: %s", e)
            self._set_status(STATUS_ERROR, "⚠️ Transcription failed")
            return

        if not transcript or len(transcript.strip()) < 3:
            self._tts.speak("I didn't catch that.")
            self._set_status(STATUS_IDLE, "")
            return

        # Strip stop keywords from the tail of the transcript
        transcript = _strip_stop_keyword(transcript)

        # Combine mode: prepend previous transcript so the LLM sees one unified request
        if combine and self._last_transcript:
            transcript = self._last_transcript + ", " + transcript
            logger.info("Combined transcript: %s", transcript)

        # Save clean transcript for potential future combine session
        self._last_transcript = transcript

        # Inject view context so the LLM biases routing appropriately
        if self.current_view == "todo":
            transcript = "[TASKS VIEW] " + transcript

        logger.info("Transcript (cleaned): %s", transcript)
        snippet = transcript[:60] + ("…" if len(transcript) > 60 else "")
        self._set_status(STATUS_PROCESSING, f'💭 "{snippet}"')

        # 3. Parse intent(s)
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
            logger.error("Parse error: %s", e)
            self._set_status(STATUS_ERROR, "⚠️ Couldn't parse request")
            return

        # Filter unknowns
        valid = [(name, intent) for name, intent in action_list
                 if name != "unknown" and not isinstance(intent, UnknownIntent)]

        if not valid:
            self._tts.speak("I'm not sure what you'd like me to do.")
            self._set_status(STATUS_IDLE, "")
            return

        # 4. Confirm + execute each action
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
                logger.warning("Unknown action '%s'", action_name)
                continue

            try:
                self._set_status(STATUS_PROCESSING, f"⚙️ Executing {action_name.replace('_', ' ')}…")
                result_text = action_cls().execute(intent, self.config)
                results.append(result_text)
                logger.info("Action '%s' complete: %s", action_name, result_text)
            except AuthExpiredError as e:
                self._tts.speak("Microsoft login expired. Use Re-authenticate in the menu.")
                logger.error("Auth expired: %s", e)
                self._set_status(STATUS_ERROR, "⚠️ Auth expired")
                if self.on_auth_expired:
                    self.on_auth_expired()
                return
            except AssistantError as e:
                self._tts.speak("Something went wrong. Check the logs for details.")
                logger.error("Action error: %s", e)
                self._set_status(STATUS_ERROR, "⚠️ Action failed")
                return

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
            time.sleep(2)

        self._phase = STATUS_IDLE
        self._set_status(STATUS_IDLE, "")

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
