"""Flask REST API — exposes calendar, todos, voice, and config endpoints.

Start with:
    python -m assistant.api           # localhost:8080
    python -m assistant.api --lan     # 0.0.0.0:8080  (iPhone access over LAN)
"""

from __future__ import annotations

import datetime
import logging
import os
import re
import sqlite3
from typing import Any

import yaml
from flask import Flask, jsonify, request

from assistant.config import AppConfig, ConfigError, load_config as _load_config_file


def load_config(path: str = "config.yaml") -> AppConfig:
    """config.yaml is local-only (gitignored); fall back to the example, then defaults (CI)."""
    try:
        return _load_config_file(path)
    except ConfigError:
        try:
            return _load_config_file("config.example.yaml")
        except ConfigError:
            return AppConfig()
from assistant.db import get_db
from assistant.exceptions import AssistantError, TargetNotFound

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

_stt = None

# ---------------------------------------------------------------------------
# iOS background verification store
# {token: {"correction": dict|None, "ready": bool, "expires": float}}
# ---------------------------------------------------------------------------
import threading as _threading
import time as _time
_verify_store: dict = {}
_verify_lock = _threading.Lock()


def build_stt(cfg):
    """STT provider per config.stt_engine (shared with the Mac pipeline)."""
    if cfg.stt_engine == "mlx":
        from assistant.stt.mlx_whisper_stt import MlxWhisperSTT
        return MlxWhisperSTT(cfg.mlx_whisper)
    if cfg.stt_engine == "google":
        from assistant.stt.google_stt import GoogleSTT
        return GoogleSTT(cfg.google_stt)
    from assistant.stt.whisper_stt import WhisperSTT
    return WhisperSTT(cfg.whisper)


def _get_stt():
    global _stt
    if _stt is None:
        cfg = load_config()
        _stt = build_stt(cfg)
    return _stt


def warm_up_components() -> None:
    """Load Whisper, spaCy and the LLM model up front (in a daemon thread) so
    the first phone command doesn't pay 10–20 s of cold starts."""
    def _go() -> None:
        import time as _t
        from assistant.engine import generate as _gen, load_config as _engine_cfg
        t0 = _t.perf_counter()
        for name, fn in (("rule parser", _gen._get_rule_parser),
                         ("whisper", _get_stt),
                         ("llm parser", lambda: _gen._get_parser(_engine_cfg()))):
            try:
                fn()
            except Exception as e:
                logger.warning("Warm-up of %s failed: %s", name, e)
        try:
            rp = _gen._get_rule_parser()
            if rp is not None:
                rp.analyze("meeting tomorrow at 3pm")  # forces spaCy + datetime models
        except Exception:
            pass
        logger.info("Warm-up finished in %.1fs", _t.perf_counter() - t0)
    _threading.Thread(target=_go, daemon=True, name="warm-up").start()


def _llm_reachable(cfg) -> bool:
    if cfg.llm_engine != "ollama":
        return True
    try:
        import requests as _rq
        return _rq.get(f"{cfg.ollama.base_url}/api/tags", timeout=1.5).ok
    except Exception:
        return False


def start_pending_retry_loop(run_transcript, interval: float = 30.0) -> None:
    """Daemon: whenever the LLM is reachable, re-run queued commands (max 5 tries each)."""
    def _loop() -> None:
        from assistant.intent.memory import get_memory
        while True:
            _time.sleep(interval)
            try:
                mem = get_memory()
                rows = mem.pending()
                if not rows:
                    continue
                cfg = load_config()
                if not _llm_reachable(cfg):
                    continue
                for row in rows:
                    if row["attempts"] >= 5:
                        mem.resolve_pending(row["id"], "failed", "gave up after 5 attempts")
                        continue
                    logger.info("📱 Retrying queued command #%s: %s", row["id"], row["transcript"])
                    result = run_transcript(row["transcript"])
                    if result.get("parse") == "error":
                        mem.bump_pending(row["id"])
                    else:
                        mem.resolve_pending(row["id"], "done", result.get("message", ""))
            except Exception as e:
                logger.warning("📱 Pending retry loop error: %s", e)
    _threading.Thread(target=_loop, daemon=True, name="pending-retry").start()


def create_app() -> Flask:
    app = Flask(__name__)
    _no_bg = os.environ.get("MACALENDAR_NO_WARMUP") == "1"   # tests
    # Under --reload, Werkzeug runs this module twice: once in the watcher that
    # does nothing but restart the child, and once in the child that serves. The
    # watcher has no use for 5.8 GB of llama, a Whisper model and spaCy, and
    # loading them there doubles both memory and startup. WERKZEUG_RUN_MAIN is
    # set only in the child; it is absent entirely when the reloader is off, so
    # the normal path is unaffected.
    _is_reload_watcher = (
        os.environ.get("WERKZEUG_RUN_MAIN") is None
        and os.environ.get("MACALENDAR_RELOADING") == "1"
    )
    if not _no_bg and not _is_reload_watcher:
        warm_up_components()

    # ------------------------------------------------------------------
    # Optional API-key auth — enforced via before_request so every route is
    # covered automatically (a per-route @decorator is easy to forget on a
    # new endpoint; this can't be skipped by accident). /health stays open
    # so external monitoring doesn't need the key.
    # ------------------------------------------------------------------

    @app.before_request
    def _enforce_api_key():
        if request.path == "/health":
            return None
        cfg = load_config()
        expected = cfg.api.key
        if expected:
            provided = request.headers.get("X-API-Key", "")
            if provided != expected:
                return jsonify({"error": "Unauthorized", "code": 401}), 401
        return None

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    @app.get("/health")
    def health():
        cfg = load_config()
        db = get_db()
        llm_status = "ok"
        if cfg.llm_engine == "ollama":
            try:
                import requests as _rq
                r = _rq.get(f"{cfg.ollama.base_url}/api/tags", timeout=1.5)
                names = [m.get("name", "") for m in r.json().get("models", [])]
                llm_status = "ok" if any(n.startswith(cfg.ollama.model.split(":")[0]) for n in names) \
                    else f"model {cfg.ollama.model} not pulled"
            except Exception:
                llm_status = "offline"
        return jsonify({
            "status": "ok",
            "llm": f"{cfg.llm_engine} ({getattr(cfg, cfg.llm_engine).model}) — {llm_status}",
            "llm_engine": cfg.llm_engine,
            "llm_status": llm_status,
            "db": db.path,
        })

    # ------------------------------------------------------------------
    # Background verification polling (iOS)
    # ------------------------------------------------------------------

    @app.get("/voice/verify/<token>")
    def voice_verify(token: str):
        """Poll for background LLM verification of a rule-path voice command.

        iOS calls this once ~5 s after receiving a voice response with a
        'verify_token'. Returns immediately with {"pending": true} if not ready yet.

        When ready, returns {"ok": true} or a correction object:
          • minor: {"ok": false, "severity": "minor", "patch": {...}, "speech": "...", "refresh": "..."}
          • major: {"ok": false, "severity": "major", "action": "...", "parameters": {...},
                    "speech": "...", "refresh": "..."}

        iOS re-executes major corrections via the normal REST endpoints
        and plays the speech string via AVSpeechSynthesizer.
        The token is consumed on first ready response.
        """
        with _verify_lock:
            entry = _verify_store.get(token)
        if entry is None:
            return jsonify({"error": "Unknown or expired token", "code": 404}), 404
        if not entry["ready"]:
            return jsonify({"pending": True})
        # Consume the token
        with _verify_lock:
            _verify_store.pop(token, None)
        return jsonify(entry["correction"])

    # ------------------------------------------------------------------
    # Voice endpoints
    # ------------------------------------------------------------------

    def _run_transcript(transcript: str, trace: "Trace | None" = None,
                        source: str = "ios", current_view: str = "month",
                        trace_run: str | None = None,
                        supports_edit: bool = False) -> dict[str, Any]:
        """The brain lives in assistant.engine now — the 7-step deep track
        (DOCUMENTATION/ENGINE.md). This wrapper exists so every voice route
        and the pending-retry loop share one entry point."""
        from assistant.engine import run_transcript as _engine_run
        return _engine_run(transcript, trace=trace, source=source,
                           current_view=current_view, trace_run=trace_run,
                           supports_edit=supports_edit)

    if not _no_bg:
        start_pending_retry_loop(_run_transcript)

    @app.post("/voice")
    def voice_audio():
        """Accept a multipart audio file, transcribe via Whisper, then execute."""
        if "audio" not in request.files:
            return jsonify({"error": "Missing 'audio' file field", "code": 400}), 400

        audio_bytes = request.files["audio"].read()
        logger.info("📱 Audio received: %.1f KB", len(audio_bytes) / 1024)
        try:
            from assistant.api.audio_utils import audio_bytes_to_numpy
            audio_np = audio_bytes_to_numpy(audio_bytes)
        except Exception as e:
            logger.error("📱 Audio decode failed: %s", e)
            return jsonify({"error": f"Audio decode failed: {e}", "code": 422}), 422

        from assistant.trace import Trace, STT
        trace = Trace(source="ios")
        try:
            stt = _get_stt()
            transcript = stt.transcribe(audio_np)
        except Exception as e:
            return jsonify({"error": f"Transcription failed: {e}", "code": 500}), 500

        if not transcript.strip():
            return jsonify({"message": "I didn't catch that.", "actions": [], "refresh": "",
                            "parse": "error", "trace": trace.to_list()})

        logger.info("📱 Transcript: %s", transcript)
        trace.step(STT, "Heard", transcript, transcript=transcript)
        return jsonify(_run_transcript(transcript, trace, source="ios"))

    @app.post("/voice/stream")
    def voice_audio_stream():
        """Same as POST /voice but streams the thinking trace live as NDJSON.

        Each line is a JSON object: {"type": "step", ...TraceStep} while the
        request is processed, then a final {"type": "result", ...response}.
        The iOS app renders the steps as a timeline as they arrive.
        """
        from flask import Response, stream_with_context
        import json as _json
        import queue as _queue
        from assistant.trace import Trace, STT, ERROR

        if "audio" in request.files:
            audio_bytes = request.files["audio"].read()
            text_cmd = None
        else:
            body = request.get_json(silent=True) or {}
            text_cmd = (body.get("transcript") or "").strip()
            audio_bytes = b""
            if not text_cmd:
                return jsonify({"error": "Missing 'audio' file or 'transcript'", "code": 400}), 400

        q: "_queue.Queue[dict | None]" = _queue.Queue()
        trace = Trace(source="ios")
        trace.on_step(lambda st: q.put({"type": "step", **st.to_dict()}))

        def work() -> None:
            try:
                if text_cmd is not None:
                    transcript = text_cmd
                    trace.step(STT, "Typed", transcript, transcript=transcript)
                else:
                    logger.info("📱 Audio received (stream): %.1f KB", len(audio_bytes) / 1024)
                    from assistant.api.audio_utils import audio_bytes_to_numpy
                    audio_np = audio_bytes_to_numpy(audio_bytes)
                    q.put({"type": "step", "stage": STT, "title": "Listening",
                           "detail": "Transcribing with Whisper…", "ms": 0, "at_ms": 0, "ok": True})
                    transcript = _get_stt().transcribe(audio_np)
                    if not transcript.strip():
                        trace.step(ERROR, "Nothing heard", "The recording was silent", ok=False)
                        q.put({"type": "result", "message": "I didn't catch that.", "actions": [],
                               "refresh": "", "parse": "error", "trace": trace.to_list()})
                        return
                    logger.info("📱 Transcript: %s", transcript)
                    trace.step(STT, "Heard", transcript, transcript=transcript)
                result = _run_transcript(transcript, trace, source="ios")
                q.put({"type": "result", **result})
            except Exception as e:  # never leave the stream hanging
                logger.exception("📱 Stream pipeline failed: %s", e)
                trace.step(ERROR, "Failed", str(e), ok=False)
                q.put({"type": "result", "message": f"Error: {e}", "actions": [], "refresh": "",
                       "parse": "error", "trace": trace.to_list()})
            finally:
                q.put(None)

        _threading.Thread(target=work, daemon=True).start()

        def gen():
            while True:
                item = q.get()
                if item is None:
                    break
                yield _json.dumps(item, ensure_ascii=False) + "\n"

        return Response(stream_with_context(gen()), mimetype="application/x-ndjson",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.post("/voice/text")
    def voice_text():
        """Accept a JSON transcript and execute directly (skips STT)."""
        body = request.get_json(silent=True) or {}
        transcript = body.get("transcript", "").strip()
        if not transcript:
            return jsonify({"error": "Missing 'transcript' field", "code": 400}), 400
        # `source` is the only thing that differs between the two surfaces: it
        # labels the trace, the vocabulary corrections and the command memory.
        # The Mac GUI posts here too — this route is the brain for both.
        # Unidentified means synthetic. Both real clients say who they are —
        # the GUI posts "mac", the iOS app posts "ios" — so anything that does
        # not is a curl, a script or a smoke check, and belongs in the history
        # only when you ask for it.
        #
        # This defaulted to "ios", which is how an afternoon of my own testing
        # ended up indistinguishable from commands actually given to the phone.
        # Defaulting the other way makes forgetting to label a test harmless
        # and forgetting to label a real client obvious.
        src = (body.get("source") or "test").strip().lower()
        if src not in ("ios", "mac", "test"):
            src = "test"
        view = (body.get("current_view") or "month").strip().lower()
        logger.info("%s Text command: %s", "🖥️" if src == "mac" else "📱", transcript)
        run = (body.get("trace_run") or "").strip() or None
        # A client that can show the "edit the transcription" round-trip says
        # so; older clients never see a needs_edit response.
        edit_ok = bool(body.get("supports_edit"))
        return jsonify(_run_transcript(transcript, source=src, current_view=view,
                                       trace_run=run, supports_edit=edit_ok))

    # ------------------------------------------------------------------
    # Personal vocabulary (STT auto-correct)
    # ------------------------------------------------------------------

    @app.get("/vocab")
    def vocab_get():
        from assistant.stt.vocab import get_vocab
        return jsonify(get_vocab().to_dict())

    @app.post("/vocab")
    def vocab_add():
        from assistant.stt.vocab import get_vocab
        body = request.get_json(silent=True) or {}
        word = str(body.get("word", "")).strip()
        if not word:
            return jsonify({"error": "Missing 'word'", "code": 400}), 400
        aliases = [str(a) for a in body.get("aliases", []) if str(a).strip()]
        entry = get_vocab().add_word(
            word, aliases,
            label=str(body.get("label", "") or ""),
            expands_to=str(body.get("expands_to", "") or ""),
        )
        return jsonify(entry.to_dict()), 201

    @app.patch("/vocab/<path:word>")
    def vocab_update(word: str):
        """Edit a word the settings screens are showing.

        Only the fields present in the body are changed; an empty string
        clears one. That distinction is what lets a screen offer "remove this
        label" without a second endpoint, and stops a client that predates a
        field from wiping it by omission.
        """
        from assistant.stt.vocab import get_vocab
        body = request.get_json(silent=True) or {}
        fields = {}
        for key in ("label", "expands_to"):
            if key in body:
                fields[key] = str(body.get(key) or "")
        if "aliases" in body:
            fields["aliases"] = [str(a).strip() for a in body.get("aliases") or []
                                 if str(a).strip()]
        if not fields:
            return jsonify({"error": "Nothing to change", "code": 400}), 400
        entry = get_vocab().update_word(word, **fields)
        if entry is None:
            return jsonify({"error": f"No such word: {word}", "code": 404}), 404
        return jsonify(entry.to_dict())

    @app.post("/vocab/alias")
    def vocab_alias():
        """Teach a correction: {"wrong": "Kyira", "right": "Kyra"}."""
        from assistant.stt.vocab import get_vocab
        body = request.get_json(silent=True) or {}
        wrong = str(body.get("wrong", "")).strip()
        right = str(body.get("right", "")).strip()
        if not wrong or not right:
            return jsonify({"error": "Need 'wrong' and 'right'", "code": 400}), 400
        entry = get_vocab().add_alias(wrong, right)
        return jsonify(entry.to_dict())

    @app.delete("/vocab/<path:word>")
    def vocab_delete(word: str):
        from assistant.stt.vocab import get_vocab
        alias = request.args.get("alias")
        store = get_vocab()
        ok = store.remove_alias(word, alias) if alias else store.remove_word(word)
        if not ok:
            return jsonify({"error": "Not found", "code": 404}), 404
        return jsonify({"ok": True})

    @app.patch("/vocab/settings")
    def vocab_settings():
        from assistant.stt.vocab import get_vocab
        body = request.get_json(silent=True) or {}
        store = get_vocab()
        store.update_settings(
            auto_correct=body.get("auto_correct"),
            learn_aliases=body.get("learn_aliases"),
            threshold=body.get("threshold"),
        )
        return jsonify(store.to_dict())

    @app.get("/changes")
    def changes_token():
        """A cheap "has anything changed?" token for the phone to poll.

        Refetching every list on a timer is expensive, so the phone did it only
        every 30 s — meaning something added on the Mac could sit invisible on
        the phone for half a minute. This returns a few bytes derived from the
        database file, so the phone can ask every couple of seconds and only do
        real work when the answer changes. The Mac's own window has always
        watched the same mtime (CalendarWindow._auto_refresh_if_db_changed);
        this is that signal, shared.

        The database runs in rollback-journal mode, so every commit touches the
        main file — mtime and size together move on any write.
        """
        import os as _os
        path = get_db().path
        try:
            st = _os.stat(path)
            token = f"{st.st_mtime:.6f}-{st.st_size}"
        except OSError:
            token = "0"
        return jsonify({"token": token})

    @app.get("/vocab/onboarding")
    def vocab_onboarding_get():
        from assistant.stt.vocab import get_vocab
        from assistant.stt import vocab_onboarding
        return jsonify(vocab_onboarding.payload(get_vocab()))

    @app.post("/vocab/onboarding")
    def vocab_onboarding_post():
        """{"answers": {"people": ["Kyra"], ...}, "presets": ["tefillah"], "done": true}"""
        from assistant.stt.vocab import get_vocab
        from assistant.stt import vocab_onboarding
        body = request.get_json(silent=True) or {}
        return jsonify(vocab_onboarding.apply(
            get_vocab(), body.get("answers"), body.get("presets"), bool(body.get("done", True))))

    @app.post("/vocab/import")
    def vocab_import():
        """Mine vocabulary candidates. Body: {"text": "..."} (WhatsApp export / notes)
        or {"source": "calendar"} or {"names": ["Rocky Caplan", ...]} (phone contacts).
        Returns candidates only — nothing is added."""
        from assistant.stt.vocab import get_vocab
        from assistant.stt import vocab_import
        body = request.get_json(silent=True) or {}
        known = {e.word for e in get_vocab().entries}
        if body.get("names"):
            cands = vocab_import.from_names([str(n) for n in body["names"]], known)
        elif body.get("source") == "calendar":
            cands = vocab_import.from_calendar(known)
        else:
            text = str(body.get("text", ""))
            if len(text) > 5_000_000:
                return jsonify({"error": "Text too large", "code": 413}), 413
            cands = vocab_import.extract(text, known)
        return jsonify({"candidates": cands})

    @app.post("/vocab/bulk")
    def vocab_bulk():
        """Add many words at once: {"words": ["Kyra", ...]}"""
        from assistant.stt.vocab import get_vocab
        body = request.get_json(silent=True) or {}
        store = get_vocab()
        added = 0
        for w in body.get("words", []):
            w = str(w).strip()
            if w and store._find(w) is None:
                store.add_word(w); added += 1
        return jsonify({"added": added, "total": len(store.entries)})

    @app.post("/vocab/preview")
    def vocab_preview():
        """Dry-run: what would the corrector do to this text? (no learning)"""
        from assistant.stt.vocab import get_vocab
        body = request.get_json(silent=True) or {}
        text = str(body.get("text", ""))
        fixed, fixes = get_vocab().correct(text, learn=False)
        return jsonify({"original": text, "corrected": fixed,
                        "corrections": [c.to_dict() for c in fixes]})

    # ------------------------------------------------------------------
    # Pending commands (failed because the LLM was offline/slow)
    # ------------------------------------------------------------------

    @app.get("/pending")
    def pending_list():
        from assistant.intent.memory import get_memory
        return jsonify({"pending": get_memory().pending(include_done=request.args.get("all") == "1")})

    @app.post("/pending/<int:pending_id>/retry")
    def pending_retry(pending_id: int):
        from assistant.intent.memory import get_memory
        mem = get_memory()
        row = mem.get_pending(pending_id)
        if row is None:
            return jsonify({"error": "Not found", "code": 404}), 404
        result = _run_transcript(row["transcript"])
        if result.get("parse") == "error":
            mem.bump_pending(pending_id)
        else:
            mem.resolve_pending(pending_id, "done", result.get("message", ""))
        result["pending_id"] = pending_id
        return jsonify(result)

    @app.delete("/pending/<int:pending_id>")
    def pending_dismiss(pending_id: int):
        from assistant.intent.memory import get_memory
        get_memory().resolve_pending(pending_id, "dismissed")
        return jsonify({"ok": True})

    # ------------------------------------------------------------------
    # Command memory (RAG personalisation + feedback)
    # ------------------------------------------------------------------

    @app.get("/memory")
    def memory_list():
        from assistant.intent.memory import get_memory
        limit = int(request.args.get("limit", 50))
        return jsonify({"examples": get_memory().recent(limit), "stats": get_memory().stats()})

    @app.get("/memory/unreviewed")
    def memory_unreviewed():
        """Commands with no feedback yet (for the phone's review screen)."""
        from assistant.intent.memory import get_memory
        limit = int(request.args.get("limit", 30))
        mem = get_memory(); db = get_db()
        rows = [r for r in mem.recent(200) if r["feedback"] == "none" and r["success"] and r["actions"]][:limit]
        # Attach what actually landed in the calendar (date/time/title) so the
        # review screen can show the real date even when the stored example
        # parameters carry none.
        for r in rows:
            resolved = []
            for rec in mem.records_for(r["id"]):
                try:
                    if rec["record_type"] == "event":
                        ev = db.get_event(int(rec["record_id"]))
                        if ev:
                            resolved.append({"type": "event", "id": ev["id"], "action": rec["action"], "title": ev["title"],
                                             "date": ev["date"], "start_time": ev["start_time"], "end_time": ev.get("end_time", "")})
                    else:
                        td = db.get_todo(int(rec["record_id"]))
                        if td:
                            resolved.append({"type": "todo", "id": td["id"], "action": rec["action"], "title": td["title"],
                                             "date": td.get("due_date", ""), "start_time": "", "end_time": ""})
                except Exception:
                    pass
            r["resolved"] = resolved
        return jsonify({"examples": rows, "count": len(rows)})

    @app.post("/memory/unreviewed/skip")
    def memory_skip_unreviewed():
        """Dismiss the whole review backlog (e.g. stale seeded history)."""
        from assistant.intent.memory import get_memory
        return jsonify({"skipped": get_memory().skip_unreviewed()})

    @app.get("/memory/similar")
    def memory_similar():
        from assistant.intent.memory import get_memory
        q = request.args.get("q", "")
        return jsonify(get_memory().retrieve(q, k=int(request.args.get("k", 4))))

    @app.post("/memory/<int:example_id>/feedback")
    def memory_feedback(example_id: int):
        """{"feedback": "approved"|"corrected"|"rejected", "correction": [...]?, "notes": "..."}"""
        from assistant.intent.memory import get_memory
        body = request.get_json(silent=True) or {}
        try:
            ok = get_memory().set_feedback(example_id, body.get("feedback", "approved"),
                                          body.get("correction"), body.get("notes", ""))
        except ValueError as e:
            return jsonify({"error": str(e), "code": 400}), 400
        if not ok:
            return jsonify({"error": "Not found", "code": 404}), 404
        return jsonify(get_memory().get(example_id))

    @app.delete("/memory/<int:example_id>")
    def memory_delete(example_id: int):
        from assistant.intent.memory import get_memory
        if not get_memory().delete(example_id):
            return jsonify({"error": "Not found", "code": 404}), 404
        return jsonify({"ok": True})

    # ------------------------------------------------------------------
    # Timers & counters (shared with the Mac Timer tab; same DB tables)
    # ------------------------------------------------------------------

    def _dt(iso: str) -> datetime.datetime:
        try:
            d = datetime.datetime.fromisoformat(iso)
        except Exception:
            return datetime.datetime.now().astimezone()
        return d if d.tzinfo else d.astimezone()

    def _secs(start: str, end: str | None) -> float:
        e = _dt(end) if end else datetime.datetime.now().astimezone()
        return max(0.0, (e - _dt(start)).total_seconds())

    def _session_out(sess: dict) -> dict:
        out = dict(sess)
        out["seconds"] = round(_secs(sess["start_time"], sess.get("end_time")), 1)
        out["running"] = sess.get("end_time") in (None, "")
        return out

    def _enforce_max(db, timer: dict, running: dict | None) -> dict | None:
        """Mirror the Mac's auto-stop: a running session past max_session_minutes is closed at the limit."""
        limit = int(timer.get("max_session_minutes") or 0)
        if running and limit > 0:
            cutoff = _dt(running["start_time"]) + datetime.timedelta(minutes=limit)
            if datetime.datetime.now().astimezone() >= cutoff:
                db.stop_timer_session(running["id"], cutoff.isoformat())
                return None
        return running

    def _timer_out(db, t: dict) -> dict:
        sessions = db.get_timer_sessions(t["id"])
        running = _enforce_max(db, t, next((x for x in sessions if not x.get("end_time")), None))
        today = datetime.date.today().isoformat()
        total = sum(_secs(x["start_time"], x.get("end_time")) for x in sessions)
        today_s = sum(_secs(x["start_time"], x.get("end_time")) for x in sessions if x["start_time"][:10] == today)
        out = dict(t)
        out["running"] = _session_out(running) if running else None
        out["total_seconds"] = round(total, 1)
        out["today_seconds"] = round(today_s, 1)
        out["session_count"] = len(sessions)
        out["earnings"] = round(total / 3600 * float(t.get("hourly_rate") or 0), 2)
        return out

    @app.get("/timers")
    def timers_list():
        db = get_db()
        inc = request.args.get("archived") == "1"
        return jsonify({"timers": [_timer_out(db, t) for t in db.get_timers(include_archived=inc)]})

    @app.post("/timers")
    def timers_create():
        b = request.get_json(silent=True) or {}
        db = get_db()
        tid = db.create_timer(title=str(b.get("title") or "Untitled Timer"), hourly_rate=float(b.get("hourly_rate") or 0),
                              color=str(b.get("color") or "#1a6fc4"), timer_type=str(b.get("timer_type") or "work"),
                              currency=str(b.get("currency") or "ILS"), max_session_minutes=int(b.get("max_session_minutes") or 0))
        t = next(x for x in db.get_timers(include_archived=True) if x["id"] == tid)
        return jsonify(_timer_out(db, t)), 201

    @app.patch("/timers/<int:tid>")
    def timers_update(tid: int):
        b = request.get_json(silent=True) or {}
        db = get_db()
        db.update_timer(tid, **{k: v for k, v in b.items()})
        t = next((x for x in db.get_timers(include_archived=True) if x["id"] == tid), None)
        if not t:
            return jsonify({"error": "Not found", "code": 404}), 404
        return jsonify(_timer_out(db, t))

    @app.delete("/timers/<int:tid>")
    def timers_delete(tid: int):
        get_db().delete_timer(tid)
        return jsonify({"ok": True})

    @app.post("/timers/<int:tid>/start")
    def timers_start(tid: int):
        b = request.get_json(silent=True) or {}
        db = get_db()
        run = db.get_running_session(tid)
        if run:
            return jsonify(_session_out(run))
        sid = db.create_timer_session(tid, title=str(b.get("title") or ""))
        return jsonify(_session_out(next(x for x in db.get_timer_sessions(tid) if x["id"] == sid))), 201

    @app.post("/timers/<int:tid>/stop")
    def timers_stop(tid: int):
        db = get_db()
        run = db.get_running_session(tid)
        if not run:
            return jsonify({"error": "Not running", "code": 409}), 409
        db.stop_timer_session(run["id"])
        return jsonify(_session_out(next(x for x in db.get_timer_sessions(tid) if x["id"] == run["id"])))

    @app.get("/timers/<int:tid>/sessions")
    def timers_sessions(tid: int):
        return jsonify({"sessions": [_session_out(x) for x in reversed(get_db().get_timer_sessions(tid))]})

    @app.post("/timers/<int:tid>/sessions")
    def timers_session_create(tid: int):
        """Log a session that already happened ("I forgot to start the timer").

        The Mac's Timer tab has had this as "Log past time…" since the feature
        landed; this is the same thing for the phone. `start_time` is required,
        `end_time` optional (omit it to create a session that is still running).
        """
        b = request.get_json(silent=True) or {}
        start = str(b.get("start_time") or "").strip()
        if not start:
            return jsonify({"error": "start_time is required", "code": 400}), 400
        db = get_db()
        sid = db.create_timer_session(tid, title=str(b.get("title") or ""), start_time=start)
        end = str(b.get("end_time") or "").strip()
        if end:
            db.update_timer_session(sid, end_time=end)
        session = next((x for x in db.get_timer_sessions(tid) if x["id"] == sid), None)
        if session is None:
            return jsonify({"error": "Not found", "code": 404}), 404
        return jsonify(_session_out(session)), 201

    @app.patch("/timer_sessions/<int:sid>")
    def timer_session_update(sid: int):
        b = request.get_json(silent=True) or {}
        get_db().update_timer_session(sid, **b)
        return jsonify({"ok": True})

    @app.delete("/timer_sessions/<int:sid>")
    def timer_session_delete(sid: int):
        get_db().delete_timer_session(sid)
        return jsonify({"ok": True})

    def _counter_out(db, c: dict) -> dict:
        presses = db.get_counter_presses(c["id"])
        cycle = db.get_counter_cycle_start(c["id"])
        in_cycle = [p for p in presses if not cycle or p["pressed_at"] > cycle]
        today = datetime.date.today().isoformat()
        out = dict(c)
        out["count"] = sum(int(p["delta"]) for p in in_cycle)
        out["total_count"] = sum(int(p["delta"]) for p in presses)
        out["today_count"] = sum(int(p["delta"]) for p in presses if p["pressed_at"][:10] == today)
        out["cycle_started_at"] = cycle
        out["payout"] = round(out["count"] * float(c.get("price_per_unit") or 0), 2)
        return out

    @app.get("/counters")
    def counters_list():
        db = get_db()
        inc = request.args.get("archived") == "1"
        return jsonify({"counters": [_counter_out(db, c) for c in db.get_counters(include_archived=inc)]})

    @app.post("/counters")
    def counters_create():
        b = request.get_json(silent=True) or {}
        db = get_db()
        cid = db.create_counter(title=str(b.get("title") or "Untitled Counter"), price_per_unit=float(b.get("price_per_unit") or 0),
                                currency=str(b.get("currency") or "ILS"), color=str(b.get("color") or "#1a6fc4"))
        return jsonify(_counter_out(db, next(x for x in db.get_counters(include_archived=True) if x["id"] == cid))), 201

    @app.patch("/counters/<int:cid>")
    def counters_update(cid: int):
        b = request.get_json(silent=True) or {}
        db = get_db()
        db.update_counter(cid, **b)
        c = next((x for x in db.get_counters(include_archived=True) if x["id"] == cid), None)
        if not c:
            return jsonify({"error": "Not found", "code": 404}), 404
        return jsonify(_counter_out(db, c))

    @app.delete("/counters/<int:cid>")
    def counters_delete(cid: int):
        get_db().delete_counter(cid)
        return jsonify({"ok": True})

    @app.post("/counters/<int:cid>/press")
    def counters_press(cid: int):
        b = request.get_json(silent=True) or {}
        db = get_db()
        db.create_counter_press(cid, delta=int(b.get("delta") or 1), label=str(b.get("label") or ""))
        return jsonify(_counter_out(db, next(x for x in db.get_counters(include_archived=True) if x["id"] == cid)))

    @app.get("/counters/<int:cid>/presses")
    def counters_presses(cid: int):
        return jsonify({"presses": list(reversed(get_db().get_counter_presses(cid)))})

    @app.delete("/counter_presses/<int:pid>")
    def counter_press_delete(pid: int):
        get_db().delete_counter_press(pid)
        return jsonify({"ok": True})

    @app.post("/counters/<int:cid>/cashout")
    def counters_cashout(cid: int):
        b = request.get_json(silent=True) or {}
        db = get_db()
        c = next((x for x in db.get_counters(include_archived=True) if x["id"] == cid), None)
        if not c:
            return jsonify({"error": "Not found", "code": 404}), 404
        info = _counter_out(db, c)
        now = datetime.datetime.now().astimezone().isoformat()
        cycle_start = info["cycle_started_at"] or (db.get_counter_presses(cid) or [{"pressed_at": c["created_at"]}])[0]["pressed_at"]
        amount = b.get("amount")
        amount = float(amount) if amount is not None else info["payout"]
        db.create_counter_payout(cid, cycle_start, now, info["count"], amount, c["currency"], note=str(b.get("note") or ""))
        return jsonify(_counter_out(db, c)), 201

    @app.get("/counters/<int:cid>/payouts")
    def counters_payouts(cid: int):
        return jsonify({"payouts": get_db().get_counter_payouts(cid)})

    # ------------------------------------------------------------------
    # Event categories (colours)
    # ------------------------------------------------------------------

    @app.get("/categories")
    def categories_list():
        from assistant.actions.calendar import categories as _cat
        return jsonify({"categories": _cat.all_categories()})

    @app.post("/categories")
    def categories_upsert():
        """{"name": "Volunteering", "color": "#…", "alt": "#…", "keywords": [...], "add_keywords": [...]}"""
        from assistant.actions.calendar import categories as _cat
        body = request.get_json(silent=True) or {}
        try:
            return jsonify(_cat.upsert(str(body.get("name", "")), body.get("color"), body.get("alt"),
                                       body.get("keywords"), body.get("add_keywords")))
        except ValueError as e:
            return jsonify({"error": str(e), "code": 400}), 400

    @app.delete("/categories/<path:name>")
    def categories_delete(name: str):
        from assistant.actions.calendar import categories as _cat
        if not _cat.remove(name):
            return jsonify({"error": "Not found (Personal cannot be removed)", "code": 404}), 404
        return jsonify({"ok": True})

    @app.post("/categories/classify")
    def categories_classify():
        from assistant.actions.calendar import categories as _cat
        b = request.get_json(silent=True) or {}
        cat = _cat.classify(b.get("title", ""), b.get("attendees"), b.get("location", ""), b.get("description", ""))
        color, alt = _cat.color_for(cat)
        return jsonify({"category": cat, "color": color, "alt": alt})

    @app.post("/categories/recolor")
    def categories_recolor():
        """Apply categories/colours to existing events. ?force=1 re-does everything."""
        n = get_db().recategorise_all(force=request.args.get("force") == "1")
        return jsonify({"updated": n})

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    @app.get("/events")
    def events_list():
        db = get_db()
        year = request.args.get("year")
        month = request.args.get("month")
        date_str = request.args.get("date")
        week_start_str = request.args.get("week_start")

        try:
            if date_str:
                rows = db.get_events_for_day(datetime.date.fromisoformat(date_str))
            elif week_start_str:
                rows = db.get_events_for_week(datetime.date.fromisoformat(week_start_str))
            elif year and month:
                rows = db.get_events_for_month(int(year), int(month))
            else:
                # Default: today
                rows = db.get_events_for_day(datetime.date.today())
        except ValueError as e:
            return jsonify({"error": str(e), "code": 400}), 400

        return jsonify(rows)

    @app.get("/events/<int:event_id>")
    def event_get(event_id: int):
        db = get_db()
        row = db.get_event(event_id)
        if row is None:
            return jsonify({"error": "Event not found", "code": 404}), 404
        return jsonify(row)

    @app.post("/events")
    def event_create():
        data = request.get_json(silent=True) or {}
        required = {"title", "date", "start_time", "end_time"}
        missing = required - data.keys()
        if missing:
            return jsonify({"error": f"Missing fields: {missing}", "code": 400}), 400
        db = get_db()
        event_id = db.create_event_from_dict(data)
        return jsonify({"id": event_id}), 201

    @app.patch("/events/<int:event_id>")
    def event_update(event_id: int):
        data = request.get_json(silent=True) or {}
        db = get_db()
        event = db.get_event(event_id)
        if event is None:
            return jsonify({"error": "Event not found", "code": 404}), 404
        if db.is_event_locked(event):
            return jsonify({"error": "Event is read-only (synced source)", "code": 403}), 403

        # Optional optimistic-concurrency check. A client that edited the event
        # while disconnected sends the `updated_at` it was working from; if the
        # event has moved on since (someone changed it on the Mac meanwhile),
        # refuse rather than silently overwriting their work, and hand back what
        # the event looks like now so the client can say so.
        base = str(data.pop("base_updated_at", "") or "")
        if base and str(event.get("updated_at") or "") not in ("", base):
            return jsonify({"error": "Event changed on the Mac since you edited it",
                            "code": 409, "current": event}), 409

        db.update_event(event_id, **data)
        if data.get("recurrence"):
            db.promote_to_series(event_id)
        return jsonify({"id": event_id})

    @app.delete("/events/<int:event_id>")
    def event_delete(event_id: int):
        db = get_db()
        event = db.get_event(event_id)
        if event is None:
            return jsonify({"error": "Event not found", "code": 404}), 404
        if db.is_event_locked(event):
            return jsonify({"error": "Event is read-only (synced source)", "code": 403}), 403
        db.delete_event(event_id)
        return jsonify({"deleted": event_id})

    # ------------------------------------------------------------------
    # Todos
    # ------------------------------------------------------------------

    @app.get("/todos")
    def todos_list():
        db = get_db()
        list_name = request.args.get("list")  # today | general | all | None
        include_completed = request.args.get("include_completed", "false").lower() == "true"
        tag = request.args.get("tag") or None  # tag name | "__untagged__" | None

        if list_name == "all":
            list_name = None  # get_todos(None) returns everything

        rows = db.get_todos(list_name=list_name, include_completed=include_completed, tag=tag)
        return jsonify(rows)

    @app.post("/todos")
    def todo_create():
        data = request.get_json(silent=True) or {}
        title = data.get("title", "").strip()
        if not title:
            return jsonify({"error": "Missing 'title' field", "code": 400}), 400
        db = get_db()
        # A count typed into the title works the same as one spoken: "pasta x5"
        # is one task for five, not a task literally called "pasta x5".
        from assistant.intent.quantity import split_quantity
        title, parsed_qty = split_quantity(title)
        try:
            quantity = max(1, int(data.get("quantity") or parsed_qty))
        except (TypeError, ValueError):
            quantity = parsed_qty
        tags = data.get("tags") or []
        if not tags:
            # Client didn't say — server-side "tag mode", else infer from the
            # title, the same order of precedence voice creation uses.
            todo_cfg = load_config().todo
            if todo_cfg.auto_tag:
                tags = [todo_cfg.auto_tag]
            elif getattr(todo_cfg, "auto_tag_infer", True):
                from assistant.actions.todo.tagging import suggest_tags
                tags = suggest_tags(title, [r["name"] for r in db.get_tags()])
        todo_id = db.create_todo(
            title=title,
            list_name=data.get("list_name", "today"),
            priority=data.get("priority", "none"),
            due_date=data.get("due_date", ""),
            notes=data.get("notes", ""),
            tags=tags,
            quantity=quantity,
        )
        return jsonify({"id": todo_id}), 201

    @app.patch("/todos/<int:todo_id>")
    def todo_update(todo_id: int):
        data = request.get_json(silent=True) or {}
        db = get_db()
        todo = db.get_todo(todo_id)
        if todo is None:
            return jsonify({"error": "Todo not found", "code": 404}), 404

        # Same optimistic-concurrency check as events: a client that edited this
        # while disconnected quotes the version it worked from, and is told when
        # the task has moved on rather than overwriting the newer change.
        base = str(data.pop("base_updated_at", "") or "")
        if base and str(todo.get("updated_at") or "") not in ("", base):
            return jsonify({"error": "Task changed on the Mac since you edited it",
                            "code": 409, "current": todo}), 409

        db.update_todo(todo_id, **data)
        return jsonify({"id": todo_id})

    @app.patch("/todos/<int:todo_id>/toggle")
    def todo_toggle(todo_id: int):
        db = get_db()
        if db.get_todo(todo_id) is None:
            return jsonify({"error": "Todo not found", "code": 404}), 404
        new_state = db.toggle_todo_complete(todo_id)
        return jsonify({"id": todo_id, "completed": int(new_state)})

    @app.delete("/todos/<int:todo_id>")
    def todo_delete(todo_id: int):
        db = get_db()
        if db.get_todo(todo_id) is None:
            return jsonify({"error": "Todo not found", "code": 404}), 404
        db.delete_todo(todo_id)
        return jsonify({"deleted": todo_id})

    @app.post("/todos/sync")
    def todos_sync():
        data = request.get_json(silent=True) or {}
        list_name = data.get("list_name", "today")
        db = get_db()
        count = db.sync_calendar_to_todos(list_name=list_name)
        return jsonify({"synced": count, "list": list_name})

    @app.post("/todos/reorder")
    def todos_reorder():
        data = request.get_json(silent=True) or {}
        list_name = data.get("list")
        ids = data.get("ids", [])
        if not list_name or not isinstance(ids, list):
            return jsonify({"error": "Missing 'list' or 'ids'", "code": 400}), 400
        db = get_db()
        db.reorder_todos(list_name, [int(i) for i in ids])
        return jsonify({"ok": True})

    @app.delete("/todos/completed")
    def todos_clear_completed():
        list_name = request.args.get("list")  # optional filter
        db = get_db()
        count = db.delete_completed_todos(list_name=list_name or None)
        return jsonify({"deleted": count})

    # ------------------------------------------------------------------
    # Todo tags
    # ------------------------------------------------------------------

    @app.get("/tags")
    def tags_list():
        return jsonify(get_db().get_tags())

    @app.post("/tags")
    def tag_create():
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Missing 'name' field", "code": 400}), 400
        row = get_db().create_tag(name, color=data.get("color", ""))
        return jsonify(row), 201

    @app.delete("/tags/<path:name>")
    def tag_delete(name: str):
        get_db().delete_tag(name)
        return jsonify({"deleted": name})

    # ------------------------------------------------------------------
    # Courses
    # ------------------------------------------------------------------

    @app.get("/courses")
    def courses_list():
        return jsonify(get_db().get_courses())

    @app.post("/courses")
    def course_create():
        data = request.get_json(silent=True) or {}
        name = data.get("name", "").strip()
        if not name:
            return jsonify({"error": "Missing 'name'"}), 400
        course_id = get_db().create_course(
            number=data.get("number", ""),
            name=name,
            color=data.get("color", "#1a6fc4"),
            partners=data.get("partners", []),
        )
        return jsonify({"id": course_id}), 201

    @app.patch("/courses/<int:course_id>")
    def course_update(course_id: int):
        data = request.get_json(silent=True) or {}
        get_db().update_course(course_id, **data)
        return jsonify({"id": course_id})

    @app.delete("/courses/<int:course_id>")
    def course_delete(course_id: int):
        get_db().delete_course(course_id)
        return jsonify({"deleted": course_id})

    # ------------------------------------------------------------------
    # Assignments
    # ------------------------------------------------------------------

    @app.get("/assignments")
    def assignments_list_all():
        """Return all assignments across every course."""
        db = get_db()
        courses = db.get_courses()
        result = []
        for c in courses:
            result.extend(db.get_assignments(c["id"]))
        return jsonify(result)

    @app.get("/courses/<int:course_id>/assignments")
    def assignments_list(course_id: int):
        return jsonify(get_db().get_assignments(course_id))

    @app.post("/assignments")
    def assignment_create():
        data = request.get_json(silent=True) or {}
        course_id = data.get("course_id")
        title     = data.get("title", "").strip()
        if not course_id or not title:
            return jsonify({"error": "Missing 'course_id' or 'title'"}), 400
        asgn_id = get_db().create_assignment(
            course_id=int(course_id),
            title=title,
            due_date=data.get("due_date", ""),
        )
        return jsonify({"id": asgn_id}), 201

    @app.patch("/assignments/<int:asgn_id>")
    def assignment_update(asgn_id: int):
        data = request.get_json(silent=True) or {}
        get_db().update_assignment(asgn_id, **data)
        return jsonify({"id": asgn_id})

    @app.patch("/assignments/<int:asgn_id>/toggle")
    def assignment_toggle(asgn_id: int):
        new_state = get_db().toggle_assignment(asgn_id)
        return jsonify({"id": asgn_id, "completed": int(new_state)})

    @app.delete("/assignments/<int:asgn_id>")
    def assignment_delete(asgn_id: int):
        get_db().delete_assignment(asgn_id)
        return jsonify({"deleted": asgn_id})

    @app.delete("/assignments/completed")
    def assignments_clear_completed():
        course_id = request.args.get("course_id", type=int)  # optional filter
        count = get_db().delete_completed_assignments(course_id=course_id)
        return jsonify({"deleted": count})

    # ------------------------------------------------------------------
    # Workout
    #
    # Client-generated UUID primary keys end-to-end (unlike events/todos'
    # autoincrement-Int + temp-id-remap scheme) — the client always sends
    # its own `id`, the server just stores it. JSON keys are snake_case,
    # matching the SQL columns 1:1 (same convention as /events and /todos;
    # the iOS API layer translates snake_case -> camelCase via CodingKeys,
    # see API/Models.swift).
    # ------------------------------------------------------------------

    @app.get("/workout/exercises")
    def workout_exercises_list():
        return jsonify(get_db().get_workout_exercises())

    @app.post("/workout/exercises")
    def workout_exercise_create():
        data = request.get_json(silent=True) or {}
        exercise_id = data.get("id")
        name = (data.get("name") or "").strip()
        if not exercise_id or not name:
            return jsonify({"error": "Missing 'id' or 'name'", "code": 400}), 400
        get_db().create_workout_exercise(id=exercise_id, name=name, created_at=data.get("created_at"))
        return jsonify({"id": exercise_id}), 201

    @app.get("/workout/templates")
    def workout_templates_list():
        include_drafts = request.args.get("include_drafts", "false").lower() == "true"
        return jsonify(get_db().get_workout_templates(include_drafts=include_drafts))

    @app.post("/workout/templates")
    def workout_template_create():
        data = request.get_json(silent=True) or {}
        template_id = data.get("id")
        name = (data.get("name") or "").strip()
        if not template_id or not name:
            return jsonify({"error": "Missing 'id' or 'name'", "code": 400}), 400
        db = get_db()
        if db.get_workout_template(template_id) is not None:
            return jsonify({"error": "Template already exists", "code": 409}), 409
        try:
            db.create_workout_template(data)
        except (sqlite3.IntegrityError, KeyError) as e:
            return jsonify({"error": f"Invalid template: {e}", "code": 400}), 400
        return jsonify({"id": template_id}), 201

    @app.patch("/workout/templates/<template_id>")
    def workout_template_update(template_id: str):
        data = request.get_json(silent=True) or {}
        db = get_db()
        if db.get_workout_template(template_id) is None:
            return jsonify({"error": "Template not found", "code": 404}), 404
        try:
            db.replace_workout_template(template_id, data)
        except (sqlite3.IntegrityError, KeyError) as e:
            return jsonify({"error": f"Invalid template: {e}", "code": 400}), 400
        return jsonify({"id": template_id})

    @app.delete("/workout/templates/<template_id>")
    def workout_template_delete(template_id: str):
        db = get_db()
        if db.get_workout_template(template_id) is None:
            return jsonify({"error": "Template not found", "code": 404}), 404
        db.delete_workout_template(template_id)
        return jsonify({"deleted": template_id})

    @app.patch("/workout/templates/<template_id>/approve")
    def workout_template_approve(template_id: str):
        db = get_db()
        if db.get_workout_template(template_id) is None:
            return jsonify({"error": "Template not found", "code": 404}), 404
        db.approve_workout_template(template_id)
        return jsonify({"id": template_id, "status": "saved"})

    @app.get("/workout/sessions")
    def workout_sessions_list():
        limit = request.args.get("limit", type=int)
        start_date = request.args.get("start_date")
        end_date = request.args.get("end_date")
        rows = get_db().get_workout_sessions(limit=limit, start_date=start_date, end_date=end_date)
        return jsonify(rows)

    @app.post("/workout/sessions")
    def workout_session_create():
        data = request.get_json(silent=True) or {}
        session_id = data.get("id")
        started_at = data.get("started_at")
        if not session_id or not started_at:
            return jsonify({"error": "Missing 'id' or 'started_at'", "code": 400}), 400
        db = get_db()
        if db.get_workout_session(session_id) is not None:
            return jsonify({"error": "Session already exists", "code": 409}), 409
        try:
            db.create_workout_session(data)
        except (sqlite3.IntegrityError, KeyError) as e:
            return jsonify({"error": f"Invalid session: {e}", "code": 400}), 400
        return jsonify({"id": session_id}), 201

    @app.patch("/workout/sessions/<session_id>")
    def workout_session_update(session_id: str):
        data = request.get_json(silent=True) or {}
        db = get_db()
        if db.get_workout_session(session_id) is None:
            return jsonify({"error": "Session not found", "code": 404}), 404
        db.update_workout_session(session_id, **data)
        return jsonify({"id": session_id})

    @app.delete("/workout/sessions/<session_id>")
    def workout_session_delete(session_id: str):
        db = get_db()
        if db.get_workout_session(session_id) is None:
            return jsonify({"error": "Session not found", "code": 404}), 404
        db.delete_workout_session(session_id)
        return jsonify({"deleted": session_id})

    # ------------------------------------------------------------------
    # Workout: Plans + the observance calendar behind them
    # ------------------------------------------------------------------

    @app.get("/workout/plans")
    def workout_plans_list():
        status = request.args.get("status", "")
        return jsonify(get_db().get_workout_plans(status=status or None))

    @app.get("/workout/plans/<plan_id>")
    def workout_plan_get(plan_id: str):
        plan = get_db().get_workout_plan(plan_id)
        if plan is None:
            return jsonify({"error": "Plan not found", "code": 404}), 404
        return jsonify(plan)

    @app.delete("/workout/plans/<plan_id>")
    def workout_plan_delete(plan_id: str):
        db = get_db()
        if db.get_workout_plan(plan_id) is None:
            return jsonify({"error": "Plan not found", "code": 404}), 404
        keep = request.args.get("keep_events", "").lower() in ("1", "true", "yes")
        removed = db.delete_workout_plan(plan_id, delete_events=not keep)
        return jsonify({"deleted": plan_id, "events_removed": removed})

    @app.get("/workout/plan-items")
    def workout_plan_items_list():
        """Scheduled sessions in a date range — what the phone's day view asks for."""
        return jsonify(get_db().get_workout_plan_items(
            start_date=request.args.get("start_date", ""),
            end_date=request.args.get("end_date", ""),
            plan_id=request.args.get("plan_id", ""),
        ))

    @app.patch("/workout/plan-items/<item_id>")
    def workout_plan_item_update(item_id: str):
        db = get_db()
        if db.get_workout_plan_item(item_id) is None:
            return jsonify({"error": "Plan item not found", "code": 404}), 404
        db.update_workout_plan_item(item_id, **(request.get_json(silent=True) or {}))
        return jsonify(db.get_workout_plan_item(item_id))

    @app.get("/observance/location")
    def observance_location_get():
        """Where sundown is currently computed for, and where that came from."""
        from assistant import observance as ob
        here = ob.get_location()
        settings = ob.current_settings()
        return jsonify({
            "in_use": {"latitude": settings.latitude, "longitude": settings.longitude,
                       "timezone": settings.timezone, "city": settings.city},
            "source": "device" if here else "config",
            "reported": here,
        })

    @app.post("/observance/location")
    def observance_location_set():
        """A device reporting where it is.

        Sundown moves by hours between places, so a repeating event that skips
        Shabbat is wrong the moment you travel — the boundary it is avoiding is
        computed for somewhere you are not. The device that knows its position
        says so, and everything downstream follows without being told.
        """
        from assistant import observance as ob
        body = request.get_json(silent=True) or {}
        try:
            settings = ob.set_location(
                latitude=body["latitude"], longitude=body["longitude"],
                timezone=body.get("timezone") or "",
                city=body.get("city", ""),
                source=(body.get("source") or "device"),
            )
        except (KeyError, TypeError):
            return jsonify({"error": "latitude, longitude and timezone are required",
                            "code": 400}), 400
        except ValueError as exc:
            return jsonify({"error": str(exc), "code": 400}), 400
        logger.info("📍 Location set to %s (%.4f, %.4f)",
                    settings.city or "an unnamed place", settings.latitude, settings.longitude)
        return jsonify({"latitude": settings.latitude, "longitude": settings.longitude,
                        "timezone": settings.timezone, "city": settings.city})

    @app.delete("/observance/location")
    def observance_location_clear():
        """Forget the reported position and go back to the configured place."""
        from assistant import observance as ob
        settings = ob.clear_location()
        return jsonify({"latitude": settings.latitude, "longitude": settings.longitude,
                        "timezone": settings.timezone, "city": settings.city,
                        "source": "config"})

    @app.get("/observance")
    def observance_range():
        """Training availability per day: what is blocked, and which windows remain.

        Lets a client show *why* a day is unavailable without reimplementing
        the Hebrew calendar — the phone renders what the Mac decided.
        """
        from assistant import observance as ob
        from assistant.actions.schedule_workout.action import observance_settings

        try:
            start = datetime.date.fromisoformat(request.args["start_date"])
            end = datetime.date.fromisoformat(request.args["end_date"])
        except (KeyError, ValueError):
            return jsonify({
                "error": "start_date and end_date are required (YYYY-MM-DD)",
                "code": 400,
            }), 400
        if end < start:
            return jsonify({"error": "end_date precedes start_date", "code": 400}), 400
        if (end - start).days > 400:
            return jsonify({"error": "range must be 400 days or fewer", "code": 400}), 400

        settings = observance_settings(load_config())
        out = []
        cur = start
        while cur <= end:
            av = ob.availability(cur, settings)
            out.append({
                "date": cur.isoformat(),
                "status": av.status,
                "reason": av.reason,
                "holiday": av.holiday_name,
                "is_chol_hamoed": ob.is_chol_hamoed(cur),
                "is_fast_day": ob.is_fast_day(cur),
                "windows": [
                    {
                        "start": w.start.strftime("%H:%M"),
                        "end": w.end.strftime("%H:%M"),
                        "label": w.label,
                        "fallback": w.fallback,
                    }
                    for w in av.windows
                ],
            })
            cur += datetime.timedelta(days=1)
        return jsonify(out)

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    _CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config.yaml")
    _ALLOWED_PATCH_KEYS = {"llm_engine", "tts", "confirmation_level"}

    @app.get("/config")
    def config_get():
        cfg = load_config()
        return jsonify({
            "llm_engine": cfg.llm_engine,
            "tts": cfg.tts.model_dump(),
            "confirmation_level": cfg.confirmation_level,
            "todo": cfg.todo.model_dump(),
        })

    @app.patch("/config")
    def config_patch():
        data = request.get_json(silent=True) or {}
        path = os.path.normpath(_CONFIG_PATH)
        with open(path) as f:
            current = yaml.safe_load(f) or {}

        for key, wren in data.items():
            if key in _ALLOWED_PATCH_KEYS:
                if isinstance(wren, dict) and isinstance(current.get(key), dict):
                    current[key].update(wren)
                else:
                    current[key] = wren

        with open(path, "w") as f:
            yaml.dump(current, f, default_flow_style=False, allow_unicode=True)

        return jsonify({"status": "ok"})

    # ------------------------------------------------------------------
    # Hebrew calendar / holidays
    # ------------------------------------------------------------------

    @app.get("/holidays")
    def holidays_list():
        from assistant.hebrew_calendar import enumerate_holidays

        start_str = request.args.get("start")
        end_str = request.args.get("end")
        israel = request.args.get("israel", "1") not in ("0", "false", "False")

        try:
            if start_str and end_str:
                start = datetime.date.fromisoformat(start_str)
                end = datetime.date.fromisoformat(end_str)
            else:
                today = datetime.date.today()
                start = today.replace(day=1)
                end = today + datetime.timedelta(days=60)
        except ValueError as e:
            return jsonify({"error": str(e), "code": 400}), 400

        holidays = enumerate_holidays(start, end, israel=israel)
        return jsonify([
            {
                "name_en": h.name_en,
                "name_he": h.name_he,
                "category": h.category,
                "gregorian_erev_start": h.gregorian_erev_start.isoformat(),
                "gregorian_end": h.gregorian_end.isoformat(),
            }
            for h in holidays
        ])

    # ------------------------------------------------------------------
    # Connected calendars (ICS subscriptions + Outlook two-way sync)
    # ------------------------------------------------------------------
    # Note: this is a view/manage surface for sources — the Outlook OAuth
    # device-code flow itself is a Mac-only UI (Connected Calendars dialog),
    # since it requires an interactive browser sign-in.

    @app.get("/calendar_sources")
    def calendar_sources_list():
        return jsonify(get_db().get_calendar_sources())

    @app.post("/calendar_sources")
    def calendar_source_create():
        data = request.get_json(silent=True) or {}
        kind = data.get("kind", "")
        if kind not in ("ics_url", "outlook"):
            return jsonify({"error": "kind must be 'ics_url' or 'outlook'", "code": 400}), 400
        if kind == "ics_url" and not data.get("url", "").strip():
            return jsonify({"error": "Missing 'url'", "code": 400}), 400
        source_id = get_db().create_calendar_source(
            kind=kind,
            label=data.get("label", ""),
            url=data.get("url", ""),
            color=data.get("color", "#0078d4"),
            two_way=bool(data.get("two_way", False)),
        )
        return jsonify({"id": source_id}), 201

    @app.patch("/calendar_sources/<int:source_id>")
    def calendar_source_update(source_id: int):
        data = request.get_json(silent=True) or {}
        get_db().update_calendar_source(source_id, **data)
        return jsonify({"id": source_id})

    @app.delete("/calendar_sources/<int:source_id>")
    def calendar_source_delete(source_id: int):
        get_db().delete_calendar_source(source_id)
        return jsonify({"deleted": source_id})

    return app
