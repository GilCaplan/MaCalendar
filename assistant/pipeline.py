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
    TargetNotFound,
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
# Recording finished, waiting on Redo / Add more / Send (mirrors the iPhone's
# review bar). Skipped when a stop word ended the recording — saying "execute"
# means go, not "go in three seconds".
STATUS_REVIEW = "review"

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
        self._parser = IntentParser(config, registry)
        self._rule_parser: Optional[RuleBasedParser] = (
            RuleBasedParser(registry) if _RULE_PARSER_AVAILABLE else None
        )
        self._confirmer = ConfirmationHandler(config.confirmation_level)
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
        self._last_listen_press: float = 0.0  # monotonic time of last press during STATUS_LISTENING

        self.on_auth_expired: Optional[Callable[[], None]] = None
        # Set by the UI when the active view changes; used to inject parse context
        self.current_view: str = "month"

        # Warm up the spaCy / recognizer models in the background so the first
        # voice command doesn't block while 80 MB of model data loads.
        if _RULE_PARSER_AVAILABLE:
            from assistant.intent.rule_parser import _ensure_nlp, _ensure_dt
            threading.Thread(
                target=lambda: (_ensure_nlp(), _ensure_dt()),
                daemon=True,
                name="nlp-warmup",
            ).start()

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
        from assistant.trace import STT, VOCAB, ERROR
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

        self._process_transcript(transcript, trace, t_start,
                                 raw_transcript=_raw_transcript, corrections=_corrections)

    def _process_transcript(self, transcript: str, trace, t_start: float, *,
                            raw_transcript: str = "", corrections: list | None = None) -> bool:
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
        }
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


    def _background_fix_title(self, transcript: str, event_id: int, keyword: str) -> None:
        """Daemon thread: ask the LLM for a proper title and patch the event if improved.

        Called whenever the fast-path created an event whose title is a generic
        keyword (e.g. 'meeting'). The LLM reads the full transcript context and
        returns a better title; we patch silently if the record is still unchanged.
        """
        from assistant.db import get_db
        try:
            better_title = self._parser.fix_title_async(transcript, keyword)
            if not better_title:
                return
            db = get_db()
            current = db.get_event(event_id)
            if current is None:
                return  # already deleted
            if current.get("title", "").lower() != keyword.lower():
                return  # user already edited it — respect their change
            db.update_event(event_id, title=better_title)
            logger.info("🖥️ Keyword title fix: %r → %r (event_id=%d)", keyword, better_title, event_id)
            self._trace_late_step("verify", "Better title", f"“{keyword}” → “{better_title}”")
            self._set_status("refresh", "")
        except Exception as exc:
            logger.debug("🖥️ Background title fix failed: %s", exc)

    def _background_verify(self, transcript: str, rule_result, snapshot: dict) -> None:
        """Daemon thread: the LLM reviews what the fast path just did.

        Two stages, deliberately separate, because they are different questions
        and the model is good at one and bad at the other:

          1. CLASSIFY — "is this right, or does it need changing?" A yes/no
             judgement. Measured on commands the rules get confidently wrong,
             this caught every one.
          2. AUTHOR — "then what should it be?" Only reached when stage 1 says
             change it. The verifier's own answer to this is not used: asked
             inline it proposed create_todo for "Walk Mark's dog today at
             2:30PM", which has a time and is an event. The full parser is
             asked instead, and if the parser lands on what already ran, stage
             1 was a false alarm and nothing is touched.

        Applied as three tiers:

        Tier 1 — ok:    Rule parser was right. Nothing changes.
        Tier 2 — minor: PATCH the existing record with corrected fields.
                        Speaks a brief correction only when audibly meaningful.
        Tier 3 — major: Wrong action/entity. Undo the fast-path record (if it
                        was a create), then re-execute the authored intent.

        Before applying any correction, checks if the user already modified the
        record (manual edit, another voice command, etc.). If so, skips the
        correction — the user's change acts as implicit feedback.

        Every outcome publishes a trace step, including agreement. A check that
        happens invisibly is one the user cannot trust or overrule: the panel
        has to be able to say "I looked at this and left it alone".
        """
        from assistant.db import get_db

        logger.debug("🖥️ Background verify starting for: %r", transcript)

        # Short-circuit: if the rule parser picked create_event and the transcript
        # contains a strong calendar signal word AND an explicit time, the rule
        # parser is almost certainly right — skip the LLM verification entirely to
        # avoid false-positive "meeting → create_todo" misclassifications.
        _STRONG_CALENDAR_WORDS = frozenset({
            "meeting", "appointment", "call", "session", "interview",
            "sync", "standup", "stand-up", "lecture", "class",
        })
        _rule_actions = list(rule_result.raw_slots.keys())
        if len(_rule_actions) == 1 and _rule_actions[0] == "create_event":
            _slots = rule_result.raw_slots["create_event"]
            _words = set(re.findall(r"\w+", transcript.lower()))
            if (_words & _STRONG_CALENDAR_WORDS) and _slots.get("start_time"):
                logger.debug(
                    "🖥️ Background verify: skipping — calendar signal + time is unambiguous"
                )
                return

        action_names = [name for name, _ in snapshot.get("actions", [])]
        _ran = ", ".join(n.replace("_", " ") for n in action_names) or "the command"

        # --- Stage 1: classify — leave it, or change it? --------------------
        self._trace_late_step("verify", "Self-check",
                              f"Re-reading {_ran} with the LLM…")
        correction = self._parser.verify_fast_path_async(transcript, rule_result)
        if correction is None:
            # Tier 1. Said out loud in the trace rather than silently: this is
            # the common case, and it is the evidence that the check ran.
            self._trace_late_step("verify", "Self-check",
                                  f"Checked {_ran} — correct, left alone")
            return

        severity = correction.get("severity", "major")
        speech = correction.get("speech", "")
        self._trace_late_step(
            "verify", "Self-check",
            f"Flagged as {severity}" + (f": {speech}" if speech else "") + " — working out the fix",
            ok=False)

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
            self._trace_late_step("verify", "Self-check",
                                  "You had already edited this — left your version alone")
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
                self._trace_late_step("verify", "Self-check",
                                      "Nothing concrete to change — kept the original")
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
                self._trace_late_step(
                    "verify", "Self-check",
                    speech or "Corrected " + ", ".join(f"{k} → {v}" for k, v in patch.items()))
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

        # The verifier is a good detector and an unreliable author. Measured on
        # parses the rules get confidently wrong, it spotted every one — and
        # then proposed create_todo for "Walk Mark's dog today at 2:30PM",
        # which has a time and is plainly an event, and wanted to redo a
        # correct complete_todo as update_todo. The full parser gets both
        # right. So the verdict is used only as the trigger, and the parser
        # writes the replacement.
        #
        # This is also the last safety gate before an undo: if the parser
        # agrees with what already ran, the verdict was a false alarm and the
        # record must be left alone. Without it a wrong "major" deletes an
        # event the user correctly asked for.
        try:
            reparsed = self._parser.parse(transcript)
        except Exception as exc:
            logger.info("🖥️ Correction re-parse failed (%s) — leaving the record alone", exc)
            self._trace_late_step("verify", "Self-check",
                                  f"Couldn't work out a fix ({exc}) — kept the original", ok=False)
            return
        replacement = [(n, i) for n, i in (reparsed or [])
                       if n != "unknown" and not isinstance(i, UnknownIntent)]
        if not replacement:
            logger.info("🖥️ Correction re-parse produced nothing — leaving the record alone")
            self._trace_late_step("verify", "Self-check",
                                  "No better reading found — kept the original", ok=False)
            return
        if [n for n, _ in replacement] == action_names:
            logger.info(
                "🖥️ Background verify: parser agrees with %s — treating the verdict as a "
                "false alarm and keeping the record", action_names)
            self._trace_late_step("verify", "Self-check",
                                  f"Second opinion agrees with {_ran} — false alarm, kept it")
            return
        if len(replacement) > 1:
            logger.info("🖥️ Correction re-parse returned %d actions — too ambiguous to "
                        "undo and redo automatically", len(replacement))
            self._trace_late_step("verify", "Self-check",
                                  "Fix was ambiguous — kept the original rather than guess",
                                  ok=False)
            return

        corrected_action, intent = replacement[0]
        corrected_params = intent.model_dump() if hasattr(intent, "model_dump") else {}
        logger.info("🖥️ Correction authored by the parser: %s → %s",
                    action_names, corrected_action)

        action_cls = self.registry.get(corrected_action)
        if action_cls is None:
            logger.warning("🖥️ Correction action %r not in registry", corrected_action)
            return

        # `intent` came back validated from the parser, so there is nothing to
        # re-validate — but an empty title still has to be recovered before it
        # reaches the calendar: prefer the rule parser's title, then a keyword.
        if corrected_action == "create_event" and not getattr(intent, "title", ""):
            _rule_title = rule_result.raw_slots.get("create_event", {}).get("title") or ""
            if _rule_title:
                intent.title = _rule_title
                logger.info("🖥️ Filled empty correction title from rule parser: %r", _rule_title)
            else:
                # Keyword fallback: first calendar-type noun in transcript
                _CAL_TITLE_WORDS = (
                    "appointment", "meeting", "session", "call", "sync",
                    "interview", "lecture", "class", "standup",
                )
                _transcript_lower = transcript.lower()
                for _kw in _CAL_TITLE_WORDS:
                    if _kw in _transcript_lower:
                        intent.title = _kw.capitalize()
                        logger.info(
                            "🖥️ Filled empty correction title from keyword fallback: %r",
                            intent.title,
                        )
                        break

        if corrected_action == "create_event" and not getattr(intent, "title", ""):
            logger.warning("🖥️ Correction has no usable title — skipping undo+redo")
            self._append_scenario_bug(
                transcript,
                issue_type="correction_failed",
                details=f"Re-parse gave action={corrected_action!r} with no title",
                extra={"Corrected params": corrected_params},
            )
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

        # Re-execute with validated corrected intent
        try:
            result_text = action_cls().execute(intent, self.config)
            logger.info("🖥️ Background verify: major correction executed → %s", result_text)
            self._trace_late_step("verify", "Self-check",
                                  f"Redid it as {corrected_action.replace('_', ' ')}: {result_text}")
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

    def _trace_begin(self):
        """Start a trace whose steps stream to the HUD as they happen."""
        from assistant import trace_bus
        from assistant.trace import Trace
        trace = Trace(source="mac")
        self._trace_run = trace_bus.publish_begin("Mac")
        trace.on_step(lambda st: trace_bus.publish_step(self._trace_run, st.to_dict()))
        return trace

    def _queue_pending(transcript: str, reason: str) -> "int | None":
        """Park a command the LLM couldn't take, so it can be retried later.

        The API server does this for phone commands; without it a command
        spoken to the Mac while Ollama was down was simply lost.
        """
        try:
            from assistant.intent.memory import get_memory
            return get_memory().add_pending(transcript, reason, source="mac")
        except Exception as exc:
            logger.warning("🖥️ Could not queue pending command: %s", exc)
            return None

    @staticmethod
    def _uncertain_words(transcript: str) -> list:
        """Words the vocabulary isn't sure it heard right (same helper the phone uses)."""
        try:
            from assistant.stt.vocab import get_vocab
            return get_vocab().suggestions(transcript)
        except Exception:
            return []

    def _trace_late_step(self, stage: str, title: str, detail: str = "", ok: bool = True) -> None:
        """Append a step after the run finished (background self-check)."""
        if self._trace_run is None:
            return
        from assistant import trace_bus
        trace_bus.publish_step(self._trace_run, {"stage": stage, "title": title,
                                                 "detail": detail, "ms": 0, "at_ms": 0, "ok": ok})

    def _retry_after_no_match(self, transcript, trace, *, eligible: bool,
                              failed_action: str, message: str):
        """Re-parse with the LLM after a fast-path action matched nothing.

        Returns a replacement action list, or None to keep the original
        "I couldn't find ..." answer.

        Only the rule fast path is retried, and only when it produced exactly
        one action that has executed nothing. Both conditions matter:

        - Re-parsing an LLM result with the same LLM just asks the same
          question twice.
        - The retry re-parses the whole transcript, so if an earlier action in
          the list had already succeeded, running the new list would repeat it.
          Two identical events is a worse outcome than one honest "not found".

        A retry that comes back with the same action is discarded: the LLM
        agreeing that this is a complete_todo means the task genuinely is not
        there, and saying so is the right answer.
        """
        from assistant.trace import RULE, LLM

        if not eligible or self._parser is None:
            return None

        trace.step(RULE, "Rule parser matched nothing",
                   f"{failed_action.replace('_', ' ')} found no target — asking the LLM instead",
                   ok=False)
        self._set_status(STATUS_PROCESSING, "💭 Rethinking with AI…")
        try:
            retried = self._parser.parse(transcript)
        except (LLMUnavailableError, OllamaUnavailableError, ParseError) as e:
            logger.info("🖥️ No-match retry unavailable (%s) — keeping the rule answer", e)
            trace.step(LLM, f"LLM ({self.config.llm_engine})",
                       f"Unavailable ({e}) — keeping the original answer", ok=False)
            return None

        replacement = [(n, i) for n, i in (retried or [])
                       if n != "unknown" and not isinstance(i, UnknownIntent)]
        if not replacement:
            trace.step(LLM, f"LLM ({self.config.llm_engine})",
                       "Nothing recognisable either — keeping the original answer", ok=False)
            return None
        if len(replacement) == 1 and replacement[0][0] == failed_action:
            trace.step(LLM, f"LLM ({self.config.llm_engine})",
                       f"Agrees it is {failed_action.replace('_', ' ')} — the target really is missing",
                       ok=False)
            return None

        trace.step(LLM, f"LLM ({self.config.llm_engine})",
                   "Re-read it as " + ", ".join(n.replace("_", " ") for n, _ in replacement))
        logger.info("🖥️ No-match retry: %s → %s", failed_action, [n for n, _ in replacement])
        return replacement

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

# Built-in stop patterns (longest first so "set events" beats "set event")
_BUILTIN_STOP_PATTERNS = [
    r"\bset\s+events?\b",
    r"\bexecute\b",
    r"\bxq\b",        # STT mishearing of "execute"
    r"\bdone\b",
    r"\bstop\b",
    r"\bsubmit\b",
    r"\bconfirm\b",
    r"\bthat'?s?\s+it\b",
    r"\bok\s+go\b",
]


def _build_stop_re(extra_phrases: "list[str] | None" = None) -> "re.Pattern[str]":
    """Build a stop-keyword regex from built-ins plus any user-configured phrases.

    ``extra_phrases`` is the list from ``config.audio.stop_phrases``.
    Each phrase is converted to a word-boundary regex; multi-word phrases are
    matched literally (spaces collapse to ``\\s+``).
    """
    patterns = list(_BUILTIN_STOP_PATTERNS)
    for phrase in (extra_phrases or []):
        phrase = phrase.strip()
        if not phrase:
            continue
        # Escape and allow flexible internal whitespace
        escaped = r"\s+".join(re.escape(w) for w in phrase.split())
        patterns.append(r"\b" + escaped + r"\b")
    combined = r"[\s,.!?]*(?:" + "|".join(patterns) + r")[\s,.!?]*$"
    return re.compile(combined, re.IGNORECASE)


# Module-level default (no extra phrases); pipeline rebuilds per-call with config.
_STOP_RE = _build_stop_re()


def _strip_stop_keyword(transcript: str, extra_phrases: "list[str] | None" = None) -> str:
    """Remove trailing stop keywords from the transcript."""
    stop_re = _build_stop_re(extra_phrases) if extra_phrases else _STOP_RE
    cleaned = stop_re.sub("", transcript).strip()
    return cleaned if cleaned else transcript
