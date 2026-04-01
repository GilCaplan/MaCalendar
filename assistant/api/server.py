"""Flask REST API — exposes calendar, todos, voice, and config endpoints.

Start with:
    python -m assistant.api           # localhost:5000
    python -m assistant.api --lan     # 0.0.0.0:5000  (iPhone access over LAN)
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
_stt = None


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
            expected = getattr(getattr(cfg, "api", None), "key", None)
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
    # Voice endpoints
    # ------------------------------------------------------------------

    def _run_transcript(transcript: str) -> dict[str, Any]:
        """Parse and execute a transcript; return the API response dict."""
        parser = _get_parser()
        cfg = load_config()

        try:
            parsed = parser.parse(transcript)
        except AssistantError as e:
            return {"message": str(e), "actions": [], "refresh": ""}

        messages: list[str] = []
        action_names: list[str] = []
        refresh_set: set[str] = set()

        for action_name, intent in parsed:
            if action_name == "unknown":
                messages.append("Sorry, I didn't understand that.")
                continue
            registry = _get_registry()
            action_cls = registry.get(action_name)
            if action_cls is None:
                continue
            try:
                result = action_cls().execute(intent, cfg)
                messages.append(result or "")
                action_names.append(action_name)
                # Determine what to refresh
                if "event" in action_name:
                    refresh_set.add("events")
                elif "todo" in action_name:
                    refresh_set.add("todos")
            except Exception as e:
                logger.exception("Action %s failed", action_name)
                messages.append(f"Error: {e}")

        if "events" in refresh_set and "todos" in refresh_set:
            refresh = "both"
        elif refresh_set:
            refresh = refresh_set.pop()
        else:
            refresh = ""

        return {
            "message": " ".join(m for m in messages if m),
            "actions": action_names,
            "refresh": refresh,
        }

    @app.post("/voice")
    def voice_audio():
        """Accept a multipart audio file, transcribe via Whisper, then execute."""
        if "audio" not in request.files:
            return jsonify({"error": "Missing 'audio' file field", "code": 400}), 400

        audio_bytes = request.files["audio"].read()
        try:
            from assistant.api.audio_utils import audio_bytes_to_numpy
            audio_np = audio_bytes_to_numpy(audio_bytes)
        except Exception as e:
            return jsonify({"error": f"Audio decode failed: {e}", "code": 422}), 422

        try:
            stt = _get_stt()
            transcript = stt.transcribe(audio_np)
        except Exception as e:
            return jsonify({"error": f"Transcription failed: {e}", "code": 500}), 500

        if not transcript.strip():
            return jsonify({"message": "I didn't catch that.", "actions": [], "refresh": ""})

        return jsonify(_run_transcript(transcript))

    @app.post("/voice/text")
    def voice_text():
        """Accept a JSON transcript and execute directly (skips STT)."""
        body = request.get_json(silent=True) or {}
        transcript = body.get("transcript", "").strip()
        if not transcript:
            return jsonify({"error": "Missing 'transcript' field", "code": 400}), 400
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
