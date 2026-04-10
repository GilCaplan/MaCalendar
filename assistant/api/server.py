"""Flask REST API — exposes calendar, todos, voice, and config endpoints.

Start with:
    python -m assistant.api           # localhost:8080
    python -m assistant.api --lan     # 0.0.0.0:8080  (iPhone access over LAN)
"""

from __future__ import annotations

import datetime
import logging
import os
from functools import wraps
from typing import Any

import yaml
from flask import Flask, jsonify, request

from assistant.actions import ActionRegistry
from assistant.config import load_config
from assistant.db import get_db
from assistant.exceptions import AssistantError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

_registry: ActionRegistry | None = None
_parser = None
_rule_parser = None
_stt = None

# ---------------------------------------------------------------------------
# iOS background verification store
# {token: {"correction": dict|None, "ready": bool, "expires": float}}
# ---------------------------------------------------------------------------
import threading as _threading
import time as _time
_verify_store: dict = {}
_verify_lock = _threading.Lock()


def _get_registry() -> ActionRegistry:
    global _registry
    if _registry is None:
        import assistant.actions.calendar  # noqa: F401  triggers @register
        import assistant.actions.todo      # noqa: F401
        import assistant.actions.clarify   # noqa: F401
        _registry = ActionRegistry()
    return _registry


def _get_parser():
    global _parser
    if _parser is None:
        from assistant.intent.parser import IntentParser
        cfg = load_config()
        _parser = IntentParser(cfg, _get_registry())
    return _parser


def _get_rule_parser():
    global _rule_parser
    if _rule_parser is None:
        from assistant.intent.rule_parser import (
            RuleBasedParser,
            _RULE_PARSER_AVAILABLE,
        )
        if _RULE_PARSER_AVAILABLE:
            _rule_parser = RuleBasedParser(_get_registry())
    return _rule_parser


def _run_server_verify(token: str, transcript: str, rule_result) -> None:
    """Background worker: runs LLM verification and stores result for iOS polling.

    The iOS app polls GET /voice/verify/<token> every ~5 s after receiving a
    rule-path voice response. This function populates the store so the poll
    can return the correction (if any) or {"ok": true}.

    Three-tier outcome — matches pipeline.py logic:
      • ok=true            → {"ok": true}  — iOS takes no action
      • severity="minor"  → {"ok": false, "severity": "minor", "patch": {...},
                             "speech": "...", "refresh": "events"|"todos"}
      • severity="major"  → {"ok": false, "severity": "major",
                             "action": "...", "parameters": {...},
                             "speech": "...", "refresh": "..."}
    iOS re-executes major corrections via the normal REST endpoints
    (create/patch/delete) and plays the speech string locally.
    """
    try:
        parser = _get_parser()
        correction = parser.verify_fast_path_async(transcript, rule_result)

        result: dict
        if correction is None:
            result = {"ok": True}
        else:
            severity = correction.get("severity", "major")
            # Determine which entity type to refresh
            action = correction.get("action", "")
            refresh = "events" if "event" in action else "todos" if "todo" in action else ""
            result = {**correction, "ok": False, "refresh": refresh}

        logger.info("📱 Server verify token=%s result=%s", token[:8], result)
    except Exception as exc:
        logger.warning("📱 Server verify failed: %s", exc)
        result = {"ok": True}  # assume correct on error — don't confuse the user

    with _verify_lock:
        if token in _verify_store:
            _verify_store[token]["correction"] = result
            _verify_store[token]["ready"] = True

    # Purge expired tokens (housekeeping)
    now = _time.time()
    with _verify_lock:
        expired = [t for t, v in _verify_store.items() if v["expires"] < now]
        for t in expired:
            del _verify_store[t]


def _get_stt():
    global _stt
    if _stt is None:
        from assistant.stt.whisper_stt import WhisperSTT
        cfg = load_config()
        _stt = WhisperSTT(cfg.whisper)
    return _stt


def create_app() -> Flask:
    app = Flask(__name__)

    # ------------------------------------------------------------------
    # Optional API-key auth
    # ------------------------------------------------------------------

    def _api_key_required(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            cfg = load_config()
            expected = cfg.api.key
            if expected:
                provided = request.headers.get("X-API-Key", "")
                if provided != expected:
                    return jsonify({"error": "Unauthorized", "code": 401}), 401
            return f(*args, **kwargs)
        return decorated

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    @app.get("/health")
    def health():
        cfg = load_config()
        db = get_db()
        return jsonify({
            "status": "ok",
            "llm": cfg.llm_engine,
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

    def _run_transcript(transcript: str) -> dict[str, Any]:
        """Parse and execute a transcript; return the API response dict."""
        from assistant.intent.rule_parser import RULE_THRESHOLD, RuleParserSkip
        parser = _get_parser()
        rule_parser = _get_rule_parser()
        cfg = load_config()

        parsed = None
        parse_path = "llm"

        if rule_parser is not None:
            try:
                rule_result = rule_parser.analyze(transcript)
                if rule_result.confidence >= RULE_THRESHOLD and not rule_result.missing_slots:
                    parsed = rule_result.intents
                    parse_path = "rule"
                    logger.info(
                        "📱 Rule fast-path: confidence=%.2f actions=%s",
                        rule_result.confidence, [n for n, _ in parsed],
                    )
                else:
                    logger.info(
                        "📱 Rule partial handoff: confidence=%.2f missing=%s",
                        rule_result.confidence, rule_result.missing_slots,
                    )
                    try:
                        parsed = parser.parse_with_context(transcript, rule_result)
                        parse_path = "hybrid"
                    except AssistantError:
                        parsed = None  # fall through to full LLM below
            except RuleParserSkip as e:
                logger.debug("📱 Rule parser skipped: %s", e)

        if parsed is None:
            try:
                parsed = parser.parse(transcript)
            except AssistantError as e:
                logger.warning("📱 Parse error: %s", e)
                from assistant.pipeline import Pipeline as _Pipeline
                _threading.Thread(
                    target=_Pipeline._append_nlu_log,
                    args=(transcript, "llm", False, [], [], False, f"parse_error: {e}", "ios"),
                    daemon=True,
                ).start()
                return {"message": str(e), "actions": [], "refresh": "", "parse": "error"}

        logger.info("📱 Parsed actions: %s", [a for a, _ in parsed])

        messages: list[str] = []
        action_names: list[str] = []
        refresh_set: set[str] = set()

        for action_name, intent in parsed:
            if action_name == "unknown":
                logger.warning("📱 Unknown intent for transcript: %s", transcript)
                messages.append("Sorry, I didn't understand that.")
                continue
            registry = _get_registry()
            action_cls = registry.get(action_name)
            if action_cls is None:
                logger.warning("📱 No action class for: %s", action_name)
                continue
            try:
                result = action_cls().execute(intent, cfg)
                logger.info("📱 Action %s → %s", action_name, result)
                messages.append(result or "")
                action_names.append(action_name)
                if "event" in action_name:
                    refresh_set.add("events")
                elif "todo" in action_name:
                    refresh_set.add("todos")
            except Exception as e:
                logger.exception("📱 Action %s failed: %s", action_name, e)
                messages.append(f"Error: {e}")

        if "events" in refresh_set and "todos" in refresh_set:
            refresh = "both"
        elif refresh_set:
            refresh = refresh_set.pop()
        else:
            refresh = ""

        response_msg = " ".join(m for m in messages if m)
        logger.info("📱 Response: %s | refresh=%s | parse=%s", response_msg, refresh or "none", parse_path)

        # NLU tracking
        from assistant.pipeline import Pipeline as _Pipeline
        _success = bool(action_names)
        _failure_reason = "" if _success else ("unknown_intent" if not any(a != "unknown" for a, _ in parsed) else "action_failed")
        _threading.Thread(
            target=_Pipeline._append_nlu_log,
            args=(transcript, parse_path, parse_path == "rule",
                  action_names or [a for a, _ in parsed if a != "unknown"],
                  messages if _success else [],
                  _success, _failure_reason, "ios"),
            daemon=True,
        ).start()

        # For rule-path results: kick off background LLM verification
        # and hand the iOS app a token it can poll with GET /voice/verify/<token>
        verify_token: str | None = None
        if parse_path == "rule" and rule_result is not None:
            import uuid
            verify_token = str(uuid.uuid4())
            with _verify_lock:
                _verify_store[verify_token] = {
                    "ready": False,
                    "correction": None,
                    "expires": _time.time() + 90,   # 90 s TTL
                }
            _threading.Thread(
                target=_run_server_verify,
                args=(verify_token, transcript, rule_result),
                daemon=True,
            ).start()

        resp: dict = {
            "message": response_msg,
            "actions": action_names,
            "refresh": refresh,
            "parse": parse_path,
        }
        if verify_token:
            resp["verify_token"] = verify_token
        return resp

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

        try:
            stt = _get_stt()
            transcript = stt.transcribe(audio_np)
        except Exception as e:
            return jsonify({"error": f"Transcription failed: {e}", "code": 500}), 500

        if not transcript.strip():
            return jsonify({"message": "I didn't catch that.", "actions": [], "refresh": ""})

        logger.info("📱 Transcript: %s", transcript)
        return jsonify(_run_transcript(transcript))

    @app.post("/voice/text")
    def voice_text():
        """Accept a JSON transcript and execute directly (skips STT)."""
        body = request.get_json(silent=True) or {}
        transcript = body.get("transcript", "").strip()
        if not transcript:
            return jsonify({"error": "Missing 'transcript' field", "code": 400}), 400
        logger.info("📱 Text command: %s", transcript)
        return jsonify(_run_transcript(transcript))

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
        if db.get_event(event_id) is None:
            return jsonify({"error": "Event not found", "code": 404}), 404
        db.update_event(event_id, **data)
        if data.get("recurrence"):
            db.promote_to_series(event_id)
        return jsonify({"id": event_id})

    @app.delete("/events/<int:event_id>")
    def event_delete(event_id: int):
        db = get_db()
        if db.get_event(event_id) is None:
            return jsonify({"error": "Event not found", "code": 404}), 404
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

        if list_name == "all":
            list_name = None  # get_todos(None) returns everything

        rows = db.get_todos(list_name=list_name, include_completed=include_completed)
        return jsonify(rows)

    @app.post("/todos")
    def todo_create():
        data = request.get_json(silent=True) or {}
        title = data.get("title", "").strip()
        if not title:
            return jsonify({"error": "Missing 'title' field", "code": 400}), 400
        db = get_db()
        todo_id = db.create_todo(
            title=title,
            list_name=data.get("list_name", "today"),
            priority=data.get("priority", "none"),
            due_date=data.get("due_date", ""),
            notes=data.get("notes", ""),
        )
        return jsonify({"id": todo_id}), 201

    @app.patch("/todos/<int:todo_id>")
    def todo_update(todo_id: int):
        data = request.get_json(silent=True) or {}
        db = get_db()
        if db.get_todo(todo_id) is None:
            return jsonify({"error": "Todo not found", "code": 404}), 404
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

        for key, val in data.items():
            if key in _ALLOWED_PATCH_KEYS:
                if isinstance(val, dict) and isinstance(current.get(key), dict):
                    current[key].update(val)
                else:
                    current[key] = val

        with open(path, "w") as f:
            yaml.dump(current, f, default_flow_style=False, allow_unicode=True)

        return jsonify({"status": "ok"})

    return app
