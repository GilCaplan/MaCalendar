"""Pipeline — orchestrates the full voice-command flow."""

from __future__ import annotations

import datetime
import logging
import os
import queue
import re
import threading
import time
from typing import Callable, List, Optional

import numpy as _np

from assistant.actions import ActionRegistry
from assistant.audio.capture import AudioCapture
from assistant.config import AppConfig
from assistant.exceptions import AssistantError, AudioCaptureError
from assistant.intent.parser import IntentParser
from assistant.tts.speaker import Speaker

logger = logging.getLogger(__name__)

# Status strings consumed by CalendarWindow via status_queue
STATUS_IDLE = "idle"
STATUS_LISTENING = "listening"
STATUS_PROCESSING = "processing"
STATUS_DONE = "done"
STATUS_ERROR = "error"
# Recording finished, waiting on Redo / Add more / Send (mirrors the iPhone's
# review bar). Skipped when a stop word ended the recording — saying "execute"
# means go, not "go in three seconds".
STATUS_REVIEW = "review"
# The engine's transcript gate wants the speaker to check a doubted word
# before anything executes; the message is a JSON payload for the dialog.
STATUS_EDIT = "edit_transcript"
# The engine's confirm gate: the words were a question about creating
# something, so the parse is offered rather than run. Message is a JSON
# payload for the Add / No box (DEVQA Q9).
STATUS_CONFIRM = "confirm_create"

# Two button presses within this window while listening = cancel recording
_DOUBLE_TAP_SEC = 0.4


def _build_stt(config: AppConfig):
    if config.stt_engine == "mlx":
        from assistant.stt.mlx_whisper_stt import MlxWhisperSTT
        return MlxWhisperSTT(config.mlx_whisper)
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
        # Kept only for health_check(); this process does not parse any more.
        self._parser = IntentParser(config, registry)
        # Confirmation dialogs ran between parse and execute, both of which now
        # happen in the API process — which cannot put a window on this screen.
        # Rather than drop the setting silently, say so: a user who set this to
        # 2 expects to be asked before anything is written, and finding out by
        # noticing events appearing unannounced is not acceptable.
        if config.confirmation_level > 0:
            logger.warning(
                "🖥️ confirmation_level=%d is not in effect: parsing and execution now "
                "happen in the assistant API process, which cannot show a dialog here. "
                "Commands run without confirmation. Set confirmation_level: 0 to silence "
                "this, or file the dry-run endpoint work if you want the prompts back.",
                config.confirmation_level,
            )
        self._tts = Speaker(config.tts)

        self.status_queue: queue.Queue[str] = queue.Queue()
        # Stage-by-stage "thinking" trace — the same timeline the iPhone renders
        # from /voice's `trace`. It goes out over assistant.trace_bus rather than
        # staying in this process: the panel that draws it is its own app now
        # (assistant.thinking_hud), so that it can float over whatever you are
        # actually looking at, and show the phone's commands with the calendar
        # app closed. `_trace_run` is the id tying one run's lines together.
        self._trace_run: str | None = None
        self._busy = threading.Event()
        self._trigger_lock = threading.Lock()
        self._phase = STATUS_IDLE  # tracks current stage for button re-press logic
        # Pending session mode: None = no queue, "new" = fresh session, "combine" = append to last transcript
        self._queued: Optional[str] = None
        self._last_transcript: str = ""  # retained for combine mode
        self._recording_cancelled = threading.Event()  # set to discard current recording
        self._review_event = threading.Event()        # UI answered the review bar
        self._review_choice: Optional[str] = None     # "send" | "redo" | "add" | "cancel"
        # The engine's transcript gate: when the vocabulary doubts a word, the
        # brain answers needs_edit and this pair carries the dialog's verdict
        # back to the worker thread (same pattern as the review bar).
        self._edit_event = threading.Event()
        self._edit_text: Optional[str] = None
        # The engine's confirm gate (DEVQA Q9), same pattern again: the brain
        # answers confirm_create with a ready-to-POST proposal, the box's
        # Add / No verdict comes back to the worker thread through this pair.
        self._confirm_event = threading.Event()
        self._confirm_choice: Optional[bool] = None
        self._last_listen_press: float = 0.0  # monotonic time of last press during STATUS_LISTENING

        self.on_auth_expired: Optional[Callable[[], None]] = None
        # Set by the UI when the active view changes; used to inject parse context
        self.current_view: str = "month"


    def trigger(self) -> None:
        """Called by HotkeyListener or mic button.

        While idle → start a new session.
        While listening:
          1st press → stop recording and auto-queue a new session.
          2nd press within 400ms → cancel recording entirely (no processing).
        While processing, cycles through:
          1st press → queue a new independent session
          2nd press → switch to combine mode (new audio appended to previous transcript)
          3rd press → cancel the queued session
        """
        with self._trigger_lock:
            if self._busy.is_set():
                if self._phase == STATUS_REVIEW:
                    # Mic press while the Redo / Add more / Send bar is up means
                    # "send it" — same as tapping the mic on the phone.
                    self.review_choice("send")
                elif self._phase == STATUS_LISTENING:
                    now = time.monotonic()
                    if now - self._last_listen_press < _DOUBLE_TAP_SEC:
                        # Double-tap: cancel recording, discard audio, go idle
                        self._recording_cancelled.set()
                        self._audio.stop()
                        self._queued = None
                        self._set_status(STATUS_IDLE, "❌ Recording cancelled")
                    else:
                        # Single press: stop + auto-queue a fresh session
                        self._last_listen_press = now
                        self._audio.stop()
                        if self._queued is None:
                            self._queued = "new"
                            self._set_status(STATUS_LISTENING, "⏸ Got it — recording again after processing")
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

    def review_choice(self, choice: str) -> None:
        """Answer the Redo / Add more / Send bar (called from the UI thread)."""
        self._review_choice = choice
        self._review_event.set()

    def stop_recording(self) -> None:
        """Stop the current recording immediately (button re-press or external call)."""
        self._audio.stop()

    def retry_pending(self, pending_id: int) -> bool:
        """Re-run a command that was parked because the LLM was unreachable.

        The phone has had this via POST /pending/<id>/retry; this is the same
        thing for the Mac's own queue. Returns False if the assistant is busy
        or the id is unknown.
        """
        from assistant.intent.memory import get_memory
        row = get_memory().get_pending(pending_id)
        if row is None:
            return False
        with self._trigger_lock:
            if self._busy.is_set():
                self._set_status(STATUS_PROCESSING, "Busy — try the retry again in a moment")
                return False
            self._busy.set()

        def _work() -> None:
            try:
                trace = self._trace_begin()
                trace.step("memory", "Retrying", row["transcript"])
                self._phase = STATUS_PROCESSING
                self._set_status(STATUS_PROCESSING, "🔁 Retrying queued command…")
                if self._process_transcript(row["transcript"], trace, time.perf_counter()):
                    get_memory().resolve_pending(pending_id, "done")
                else:
                    get_memory().bump_pending(pending_id)   # still stuck — leave it queued
            except Exception as exc:
                logger.error("🖥️ Pending retry failed: %s", exc)
                self._set_status(STATUS_ERROR, "⚠️ Retry failed")
            finally:
                self._phase = STATUS_IDLE
                self._busy.clear()

        threading.Thread(target=_work, daemon=True).start()
        return True

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
            # (but not if the session was cancelled via double-tap)
            with self._trigger_lock:
                if self._recording_cancelled.is_set():
                    self._recording_cancelled.clear()
                    self._queued = None
                    return
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
        from assistant.trace import STT, ERROR
        trace = self._trace_begin()

        # 1. Listen
        self._recording_cancelled.clear()
        self._phase = STATUS_LISTENING
        listen_hint = "🔗 Listening to add on… (say 'done' or tap twice to cancel)" if combine else "🎙 Listening… (tap to stop & re-record, tap twice to cancel)"
        self._set_status(STATUS_LISTENING, listen_hint)
        trace.step(STT, "Listening",
                   "Adding on to the last command…" if combine
                   else "Recording — say a stop word or tap the mic to finish.")

        # Stream-checker: transcribe growing buffer every 2.5 s to detect stop words.
        # Cache the last result so we can reuse it and skip the final full transcription.
        _last_partial: List[str] = ["", 0.0]  # [transcript, timestamp]
        _stopped_early = [False]               # True when a stop word ended it
        _stream_stop_re = _build_stop_re(self.config.audio.stop_phrases)

        def stream_checker(audio_buffer) -> None:
            if self._phase != STATUS_LISTENING:
                return
            try:
                partial = self._stt.transcribe(audio_buffer).lower()
                _last_partial[0] = partial
                _last_partial[1] = time.perf_counter()
                if _stream_stop_re.search(partial):
                    logger.info("🖥️ Early termination detected in stream: %s", partial)
                    _stopped_early[0] = True
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
            trace.step(ERROR, "Microphone error", msg, ok=False)
            self._trace_result()
            return

        t_recorded = time.perf_counter()
        logger.info("🖥️ ⏱ Recording: %.2fs", t_recorded - t_start)

        # Double-tap cancel: discard audio and abort without processing
        if self._recording_cancelled.is_set():
            self._recording_cancelled.clear()
            self._set_status(STATUS_IDLE, "")
            trace.step(ERROR, "Cancelled", "Recording discarded — you tapped twice.", ok=False)
            self._trace_result()
            return

        # 2. Transcribe, then (unless a stop word ended it) offer Redo / Add more
        #    / Send — the same bar the iPhone shows. Transcribing first means the
        #    bar can show what was actually heard, and that a spoken stop word is
        #    detected reliably even for utterances shorter than one stream-checker
        #    interval.
        while True:
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
                    trace.step(ERROR, "Transcription failed", str(e), ok=False)
                    self._trace_result()
                    return
                logger.info("🖥️ ⏱ Transcription: %.2fs", time.perf_counter() - t_recorded)

            if not transcript or len(transcript.strip()) < 3:
                self._tts.speak("I didn't catch that.")
                self._set_status(STATUS_IDLE, "")
                trace.step(ERROR, "Nothing heard", "The recording was silent.", ok=False)
                self._trace_result()
                return

            # A spoken stop word ("execute", "finish", …) is an explicit "go now":
            # strip it and send without the review pause.
            said_stop_word = bool(_stream_stop_re.search(transcript)) or _stopped_early[0]
            transcript = _strip_stop_keyword(transcript, self.config.audio.stop_phrases)

            if combine or said_stop_word or not self.config.audio.review_before_send:
                break

            choice = self._await_review(transcript)
            if choice == "send":
                break
            if choice == "cancel":
                self._set_status(STATUS_IDLE, "❌ Cancelled")
                trace.step(ERROR, "Cancelled", "You discarded the recording.", ok=False)
                self._trace_result()
                return

            # Redo replaces the audio, Add more appends to it; either way we
            # transcribe again from the top of this loop.
            self._phase = STATUS_LISTENING
            self._set_status(STATUS_LISTENING,
                             "🎙 Listening again…" if choice == "redo" else "🎙 Go on…")
            _last_partial[0], _last_partial[1] = "", 0.0
            _stopped_early[0] = False
            try:
                more = self._audio.record_until_silence(
                    streaming_callback=stream_checker, streaming_interval_sec=2.5)
            except AudioCaptureError as e:
                logger.error("🖥️ Audio capture error on %s: %s", choice, e)
                self._set_status(STATUS_ERROR, "⚠️ Microphone error")
                trace.step(ERROR, "Microphone error", str(e), ok=False)
                self._trace_result()
                return
            audio = more if choice == "redo" else _np.concatenate([audio, more])
            t_recorded = time.perf_counter()

        _raw_transcript = transcript
        trace.step(STT, "Heard", transcript)

        # Vocabulary auto-correct used to happen here, against source="mac".
        # It now runs inside _run_transcript for both surfaces, so that a name
        # the phone learns is a name the Mac hears too, and the "Vocabulary"
        # step in the panel comes from the same code either way. Applying it
        # here as well would correct an already-corrected transcript and report
        # every fix twice.
        _corrections: list = []

        # Combine mode: send the previous command and this one as one request.
        #
        # Joined with brackets rather than a comma. A comma made them a single
        # run-on sentence the LLM had to untangle — the expensive path, and the
        # one it is worst at. Bracketed, the server splits them and parses each
        # on its own, where a short command usually settles on the rules for no
        # LLM call at all. The review then runs once for the pair instead of
        # twice, which is the actual saving.
        if combine and self._last_transcript:
            transcript = f"[{self._last_transcript}] [{transcript}]"
            logger.info("🖥️ Combined transcript: %s", transcript)

        # Save clean transcript for potential future combine session
        self._last_transcript = transcript

        # Inject view context so the LLM biases routing appropriately
        if self.current_view == "todo":
            transcript = "[TASKS VIEW] " + transcript

        logger.info("🖥️ Transcript (cleaned): %s", transcript)
        snippet = transcript[:60] + ("…" if len(transcript) > 60 else "")
        self._set_status(STATUS_PROCESSING, f'💭 "{snippet}"')

        self._process_transcript(transcript, trace, t_start,
                                 raw_transcript=_raw_transcript, corrections=_corrections)

    def _process_transcript(self, transcript: str, trace, t_start: float, *,
                            raw_transcript: str = "", corrections: list | None = None,
                            edited_from: str = "") -> bool:
        """Hand the transcript to the brain and render the answer.

        The Mac used to parse and execute here, in this process, with its own
        copy of the sequence the API server runs for the phone. Keeping two
        implementations of one behaviour cost real bugs: the phone had a sanity
        pass that turned an LLM's past date into the next occurrence and the
        Mac did not, so the same sentence produced a different event depending
        on which microphone heard it. Worse, a fix applied to one was simply
        absent from the other — twice in one afternoon.

        So there is one brain now, and it is the API server. Both surfaces post
        here; `source` is the only thing that differs, and it only labels the
        trace, the vocabulary corrections and the command memory.

        The transcript goes over unmodified — vocabulary correction and view
        context happen server-side, so both surfaces get them identically.
        Steps stream back into the run this process already opened, so the HUD
        draws one timeline rather than two.

        Returns True when at least one action executed.
        """
        import json as _json
        import urllib.error
        import urllib.request

        from assistant.trace import ERROR

        if corrections:
            # Already-applied corrections only reach here from the pending
            # queue, whose transcript was corrected when it was parked.
            logger.debug("🖥️ %d correction(s) carried from the pending queue", len(corrections))

        port = getattr(self.config.api, "port", 8080)
        payload = {
            "transcript": transcript,
            "source": "mac",
            "current_view": self.current_view,
            # This client can show the "check the transcription" dialog, so the
            # engine's gate may answer needs_edit here.
            "supports_edit": True,
            # …and the Add / No box, so an interrogative create may come back
            # as a proposal rather than being executed or dropped.
            "supports_confirm": True,
        }
        if edited_from:
            payload["edited_from"] = edited_from
        if self._trace_run:
            payload["trace_run"] = self._trace_run

        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/voice/text",
            data=_json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        key = getattr(self.config.api, "key", None)
        if key:
            req.add_header("X-API-Key", key)

        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                data = _json.loads(r.read().decode())
        except (urllib.error.URLError, OSError, ValueError) as e:
            # The launcher starts both processes, so this means the API died or
            # never came up. Say so plainly rather than failing silently — the
            # GUI cannot do the work itself any more, and pretending otherwise
            # is how you get two implementations again.
            logger.error("🖥️ Cannot reach the assistant API on port %d: %s", port, e)
            msg = ("I can't reach the assistant service. "
                   "Restart it with Launch Calendar.command.")
            self._tts.speak(msg)
            self._set_status(STATUS_ERROR, "⚠️ Assistant service unreachable")
            trace.step(ERROR, "Service unreachable", f"port {port}: {e}", ok=False)
            self._trace_result(transcript=transcript, message=msg)
            self._phase = STATUS_IDLE
            return False

        message = data.get("message") or ""
        actions = data.get("actions") or []
        pending_id = data.get("pending_id")

        if data.get("parse") == "needs_edit":
            # The vocabulary doubts a word and the setting says ask first.
            # Nothing has executed; the dialog's answer decides what does.
            shown = data.get("transcript") or transcript
            edited = self._await_transcript_edit(shown, data.get("needs_edit") or [])
            if edited is None:
                self._set_status(STATUS_IDLE, "❌ Cancelled")
                trace.step(ERROR, "Cancelled", "You discarded the doubted transcript.", ok=False)
                self._trace_result(transcript=shown, message="Cancelled — nothing was done.")
                self._phase = STATUS_IDLE
                return False
            return self._process_transcript(edited, trace, t_start,
                                            raw_transcript=raw_transcript or shown,
                                            edited_from=shown)

        if data.get("parse") == "confirm_create" and data.get("confirm_token"):
            # A question about creating something. Nothing has run; the box's
            # answer decides, and the server does the creating so the Mac and
            # the phone commit through exactly the same path.
            said = self._await_create_confirm(message, data.get("proposal") or [])
            outcome = self._answer_create_confirm(data["confirm_token"], said, port, key)
            if outcome.get("refresh"):
                self._set_status("refresh", "")
            reply = outcome.get("message") or ""
            if reply:
                self._tts.speak_sync(reply)
            self._trace_result(transcript=transcript, message=reply)
            self._phase = STATUS_IDLE
            self._set_status(STATUS_IDLE, "")
            return bool(outcome.get("created"))

        if data.get("parse") == "error" and not actions:
            self._tts.speak(message or "I couldn't understand that request.")
            self._set_status(STATUS_ERROR, "⚠️ Couldn't parse request")
            self._trace_result(transcript=transcript, message=message,
                               pending_id=pending_id,
                               uncertain_words=data.get("uncertain_words") or [])
            self._phase = STATUS_IDLE
            return False

        # A view-switching action (e.g. show me my tasks) still has to move the
        # window, which only this process can do.
        view_switch = next(
            (getattr(self.registry.get(n), "view_switch", None) for n in actions
             if getattr(self.registry.get(n), "view_switch", None)),
            None,
        )
        if view_switch:
            self._set_status("view", view_switch)
        if data.get("refresh"):
            self._set_status("refresh", "")

        if message:
            self._tts.speak_sync(message)

        logger.info("🖥️ ⏱ Total pipeline: %.2fs", time.perf_counter() - t_start)
        self._trace_result(transcript=transcript, message=message,
                           pending_id=pending_id,
                           uncertain_words=data.get("uncertain_words") or [])
        self._phase = STATUS_IDLE
        self._set_status(STATUS_IDLE, "")
        return bool(actions)


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
                for key, wren in extra.items():
                    lines.append(f"\n**{key}:** `{wren}`\n")
            lines.append("\n---\n\n")

            with open(path, "a", encoding="utf-8") as f:
                f.writelines(lines)

            logger.debug("🖥️ Scenario bug appended (%s): %s", issue_type, details[:80])
        except Exception as exc:
            logger.warning("🖥️ Could not append scenario bug: %s", exc)

    @staticmethod
    def _append_nlu_log(
        transcript: str,
        parse_method: str,
        fast_path_used: bool,
        actions: "list[str]",
        result_messages: "list[str]",
        success: bool = True,
        failure_reason: str = "",
        source: str = "mac",
    ) -> None:
        """Append an entry to DOCUMENTATION/NLU_TRACKING.md.

        Covers successes and failures so the file is a complete picture of all
        NLU attempts. Failed entries are also written to SCENARIO_BUG.md via
        the existing _append_scenario_bug path — this just adds the NLU label.

        Args:
            transcript:      The cleaned user transcript.
            parse_method:    "rule", "hybrid", "llm", or "separator".
            fast_path_used:  True when the rule parser ran without any LLM call.
            actions:         Action names that were attempted.
            result_messages: Confirmation strings (empty list on failure).
            success:         False for parse errors, unknown intents, action failures.
            failure_reason:  Short description of what went wrong (failure only).
        """
        try:
            repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            path = os.path.join(repo_root, "DOCUMENTATION", "NLU_TRACKING.md")
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if success:
                status_label = "✅ rule fast-path" if fast_path_used else f"🤖 {parse_method}"
            else:
                status_label = f"❌ failed ({parse_method})"

            source_label = "🖥️ Mac" if source == "mac" else "📱 iOS"
            lines = [
                f"## [{ts}] {'SUCCESS' if success else 'FAILED'} — {source_label}\n",
                f"**Transcript:** `{transcript}`\n\n",
                f"**Parse:** {status_label}",
            ]
            if actions:
                lines.append(f" | **Actions:** {', '.join(actions)}")
            lines.append("\n\n")
            if result_messages:
                for msg in result_messages:
                    lines.append(f"- {msg}\n")
            if failure_reason:
                lines.append(f"**Reason:** {failure_reason}\n")
            lines.append("\n---\n\n")

            with open(path, "a", encoding="utf-8") as f:
                f.writelines(lines)
        except Exception as exc:
            logger.warning("🖥️ Could not append NLU log: %s", exc)

    def _await_review(self, transcript: str) -> str:
        """Block on the Redo / Add more / Send bar; auto-sends when it times out.

        Returns "send" | "redo" | "add" | "cancel".
        """
        seconds = max(1, int(getattr(self.config.audio, "review_seconds", 3)))
        self._phase = STATUS_REVIEW
        self._review_choice = None
        self._review_event.clear()
        snippet = transcript[:60] + ("…" if len(transcript) > 60 else "")
        self._set_status(STATUS_REVIEW, f"{seconds}|{snippet}")
        answered = self._review_event.wait(timeout=seconds)
        choice = self._review_choice if answered else "send"
        self._review_choice = None
        return choice or "send"

    def _await_transcript_edit(self, transcript: str, doubted: list) -> "str | None":
        """Block on the "check the transcription" dialog. Returns the text to
        run (possibly untouched — that is a confirmation the server counts),
        or None for cancel. A dialog left unanswered cancels: executing a
        doubted transcript minutes later would surprise more than it helps."""
        import json as _json
        self._edit_text = None
        self._edit_event.clear()
        words = [d.get("heard") if isinstance(d, dict) else str(d) for d in doubted]
        self._set_status(STATUS_EDIT, _json.dumps(
            {"transcript": transcript, "words": [w for w in words if w]}))
        answered = self._edit_event.wait(timeout=180)
        text = (self._edit_text or "").strip() if answered else None
        self._edit_text = None
        return text if text else None

    def submit_transcript_edit(self, text: "str | None") -> None:
        """Called by the UI thread with the dialog's verdict (None = cancel)."""
        self._edit_text = text
        self._edit_event.set()

    def _await_create_confirm(self, prompt: str, proposal: list) -> bool:
        """Block on the Add / No box for a confirm_create proposal.

        Returns True only for an explicit Add. An unanswered box declines: a
        proposal that quietly books itself minutes later is precisely what the
        gate exists to prevent (Gil, DEVQA Q9)."""
        import json as _json
        self._confirm_choice = None
        self._confirm_event.clear()
        self._set_status(STATUS_CONFIRM, _json.dumps(
            {"prompt": prompt,
             "items": [s.get("summary", "") for s in proposal if s.get("summary")]}))
        answered = self._confirm_event.wait(timeout=180)
        choice = bool(self._confirm_choice) if answered else False
        self._confirm_choice = None
        return choice

    def submit_create_confirm(self, accept: "bool | None") -> None:
        """Called by the UI thread with the box's verdict (None = declined)."""
        self._confirm_choice = bool(accept)
        self._confirm_event.set()

    def _answer_create_confirm(self, token: str, accept: bool,
                               port: int, key: "str | None") -> dict:
        """POST the verdict to /voice/confirm. The server owns the creating —
        the GUI must not grow a second create path (the pipeline.py rule)."""
        import json as _json
        import urllib.error
        import urllib.request

        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/voice/confirm",
            data=_json.dumps({"confirm_token": token, "accept": accept}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        if key:
            req.add_header("X-API-Key", key)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return _json.loads(r.read().decode())
        except (urllib.error.URLError, OSError, ValueError) as e:
            logger.error("🖥️ Could not answer the confirmation: %s", e)
            return {"ok": False, "accepted": accept, "created": [], "refresh": "",
                    "message": "I couldn't reach the assistant service to do that."}

    def _trace_begin(self):
        """Start a trace whose steps stream to the HUD as they happen."""
        from assistant import trace_bus
        from assistant.trace import Trace
        trace = Trace(source="mac")
        self._trace_run = trace_bus.publish_begin("Mac")
        trace.on_step(lambda st: trace_bus.publish_step(self._trace_run, st.to_dict()))
        return trace

    @staticmethod
    def _uncertain_words(transcript: str) -> list:
        """Words the vocabulary isn't sure it heard right (same helper the phone uses)."""
        try:
            from assistant.stt.vocab import get_vocab
            return get_vocab().suggestions(transcript)
        except Exception:
            return []

    def _trace_result(self, **fields) -> None:
        """Close the trace with the result card payload (may be empty)."""
        if self._trace_run is None:
            return
        from assistant import trace_bus
        trace_bus.publish_result(self._trace_run, fields)

    def _set_status(self, status: str, message: str = "") -> None:
        """Push (status, message) to the queue. Message is shown as a UI toast."""
        self.status_queue.put((status, message))


# ---------------------------------------------------------------------------
# Stop-keyword helper
# ---------------------------------------------------------------------------

# Stop-keyword handling lives with the brain now (the engine strips them as
# step 1 of every command); this client imports the same helpers for its own
# recording UX — the streaming stop-word listener and the review bar — so the
# two can never disagree about what ends a recording.
from assistant.engine.transcript import (            # noqa: E402
    build_stop_re as _build_stop_re,
    strip_stop_keyword as _strip_stop_keyword,
)
