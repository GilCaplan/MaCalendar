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

from assistant.actions import ActionRegistry
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
        import assistant.actions.calendar         # noqa: F401  triggers @register
        import assistant.actions.todo             # noqa: F401
        import assistant.actions.clarify          # noqa: F401
        import assistant.actions.workout_routine  # noqa: F401
        _registry = ActionRegistry()
    return _registry


def _get_parser():
    global _parser
    if _parser is None:
        from assistant.intent.parser import IntentParser
        cfg = load_config()
        _parser = IntentParser(cfg, _get_registry())
        if cfg.llm_engine == "ollama" and cfg.ollama.warm_up:
            _threading.Thread(target=_parser.warm_up, daemon=True).start()
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


def _run_server_verify(token: str, transcript: str, rule_result, executed=None,
                       records=None, memory_id=None) -> None:
    """Background self-check for a voice command (any parse path).

    The LLM re-reasons over the transcript, what was executed, and the user's
    similar past commands. Unlike the original iOS design (which handed the
    correction to the phone to re-execute), corrections are applied HERE on
    the Mac — minor patches via db.update_*, major ones as delete + re-run —
    and the phone only polls GET /voice/verify/<token> to learn what happened
    (speech to say, what to refresh).

      • {"ok": true}
      • {"ok": false, "severity": "minor"|"major", "applied": bool,
         "speech": "...", "refresh": "events"|"todos"|""}
    """
    result: dict = {"ok": True}
    try:
        parser = _get_parser()
        if executed:
            correction = parser.verify_actions_async(transcript, executed)
        else:
            correction = parser.verify_fast_path_async(transcript, rule_result)

        if correction is not None:
            severity = correction.get("severity", "major")
            speech = correction.get("speech", "")
            applied = False
            refresh = ""
            db = get_db()
            recs = list(records or [])
            try:
                if not load_config().self_check_apply:
                    raise ValueError("self-check is advisory (config self_check_apply=false)")
                if severity == "minor":
                    import re as _re
                    patch = {k: v for k, v in (correction.get("patch") or {}).items() if v not in (None, "")}
                    # Be conservative: the verifier over-proposes. Only accept a time if that
                    # clock time is actually spoken in the command; never accept a date change
                    # (the parser + sanity pass own dates); accept a title only when the
                    # current title is a placeholder.
                    spoken = _spoken_times(transcript)
                    for k in ("start_time", "end_time", "new_start_time", "new_end_time"):
                        if k in patch and _hhmm(patch[k]) not in spoken:
                            patch.pop(k)
                    for k in ("date", "new_date", "recur_until", "match_date"):
                        patch.pop(k, None)
                    if "title" in patch or "new_title" in patch:
                        cur = ""
                        for rtype, rid, _a in recs:
                            if rtype == "event":
                                ev = db.get_event(rid); cur = (ev or {}).get("title", "")
                        if cur.strip().lower() not in {"meeting", "set meeting", "event", "appointment", "activity", "task", ""}:
                            patch.pop("title", None); patch.pop("new_title", None)
                    patch = {k: v for k, v in patch.items() if k not in ("description", "location", "attendees", "list_name", "new_list", "priority", "new_priority")}
                    # never let a malformed date/time through (e.g. an echoed placeholder)
                    for k in ("date", "new_date", "recur_until"):
                        if k in patch and not _re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(patch[k])):
                            patch.pop(k)
                    for k in ("start_time", "end_time"):
                        if k in patch and not _re.fullmatch(r"\d{1,2}:\d{2}", str(patch[k])):
                            patch.pop(k)
                    if not patch:
                        raise ValueError("patch had no valid fields")
                    for rtype, rid, _act in recs:
                        if rtype == "event":
                            db.update_event(rid, **patch); refresh = "events"; applied = True
                        elif rtype == "todo":
                            db.update_todo(rid, **{k: v for k, v in patch.items() if k in ("title", "list_name")})
                            refresh = "todos"; applied = True
                else:
                    action = correction.get("action", "")
                    params = correction.get("parameters") or {}
                    action_cls = _get_registry().get(action)
                    executed_names = [n for n, _ in (executed or [])]
                    if action == "create_event" and "create_todo" in executed_names and not _spoken_times(transcript):
                        raise ValueError("refusing task→event flip without a spoken time")
                    if action in executed_names:
                        raise ValueError("major correction proposes the same action")
                    if action_cls is not None and action.startswith(("create_",)):
                        for rtype, rid, act in recs:
                            if act.startswith("create_"):
                                (db.delete_event if rtype == "event" else db.delete_todo)(rid)
                        intent = action_cls.intent_model(**params)
                        action_cls().execute(intent, load_config())
                        refresh = "events" if "event" in action else "todos" if "todo" in action else ""
                        applied = True
                        if memory_id is not None:
                            from assistant.intent.memory import get_memory
                            get_memory().set_feedback(memory_id, "corrected",
                                                      [{"action": action, "parameters": params}],
                                                      notes="llm self-check")
            except Exception as exc:
                logger.warning("📱 Self-check correction not applied: %s", exc)
            result = {"ok": False, "severity": severity, "applied": applied,
                      "speech": speech if applied else "", "refresh": refresh}
            # NLU bug corpus — the server path never wrote here before
            try:
                from assistant.pipeline import Pipeline as _Pipeline
                _Pipeline._append_scenario_bug(
                    transcript, issue_type=f"self_check/{severity}",
                    details=f"executed={executed and [n for n, _ in executed]} correction={correction} applied={applied}",
                )
            except Exception:
                pass
        logger.info("📱 Self-check token=%s result=%s", token[:8], result)
    except Exception as exc:
        logger.warning("📱 Self-check failed: %s", exc)
        result = {"ok": True}  # assume correct on error — don't confuse the user

    with _verify_lock:
        if token in _verify_store:
            _verify_store[token]["correction"] = result
            _verify_store[token]["ready"] = True

    # Purge expired tokens (housekeeping)
    now = _time.time()
    with _verify_lock:
        for t in [t for t, e in _verify_store.items() if e["expires"] < now]:
            _verify_store.pop(t, None)


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


def _hhmm(v) -> str:
    import re as _re
    m = _re.match(r"^\s*(\d{1,2}):(\d{2})", str(v))
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else ""


def _at_times(text: str) -> set[str]:
    """Times introduced by "at" — i.e. when something starts.

    "dinner with Danny at 8 pm" states a start. The model sometimes reads such a
    time as the END and invents an earlier start, booking 18:00–20:00 for an
    8 pm dinner. Knowing which times were spoken as "at X" lets that be undone.
    """
    import re as _re
    out: set[str] = set()
    t = text.lower().replace(".", ":")
    for m in _re.finditer(r"\bat\s+(?:around\s+|about\s+|roughly\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm|a:m|p:m)?\b", t):
        h, mm, ap = int(m.group(1)), m.group(2) or "00", (m.group(3) or "").replace(":", "")
        if h > 24:
            continue
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
        out.add(f"{h % 24:02d}:{mm}")
        if not ap and h <= 12:                      # bare hour: both readings
            out.add(f"{(h + 12) % 24:02d}:{mm}")
    return out


def _spoken_times(text: str) -> set[str]:
    """All clock times a command mentions, as HH:MM (both 12h readings for bare hours)."""
    import re as _re
    out: set[str] = set()
    t = text.lower().replace(".", ":")
    for m in _re.finditer(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a:m|p:m)?\b", t):
        h, mm, ap = int(m.group(1)), m.group(2) or "00", (m.group(3) or "").replace(":", "")
        if h > 24:
            continue
        if ap == "pm" and h < 12: h += 12
        if ap == "am" and h == 12: h = 0
        out.add(f"{h % 24:02d}:{mm}")
        if not ap and h <= 12:
            out.add(f"{(h + 12) % 24:02d}:{mm}")
    for m in _re.finditer(r"\b(\d{2})(\d{2})\b", t):          # 1930, 0915
        h, mm = int(m.group(1)), m.group(2)
        if h < 24 and int(mm) < 60:
            out.add(f"{h:02d}:{mm}")
    if "noon" in t: out.add("12:00")
    if "midnight" in t: out.add("00:00")
    return out


def _fix_title_bg(transcript: str, event_id: int, keyword: str) -> None:
    try:
        new_title = _get_parser().fix_title_async(transcript, keyword)
        if new_title and new_title.strip().lower() != keyword.strip().lower():
            get_db().update_event(event_id, title=new_title.strip())
            logger.info("📱 Title fixed for event %s: %r → %r", event_id, keyword, new_title)
    except Exception as e:
        logger.debug("📱 Title fix skipped: %s", e)


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
        t0 = _t.perf_counter()
        for name, fn in (("rule parser", _get_rule_parser), ("whisper", _get_stt),
                         ("llm parser", _get_parser)):
            try:
                fn()
            except Exception as e:
                logger.warning("Warm-up of %s failed: %s", name, e)
        try:
            rp = _get_rule_parser()
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
    if not _no_bg:
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

    def _run_transcript(transcript: str, trace: "Trace | None" = None) -> dict[str, Any]:
        """Parse and execute a transcript; return the API response dict.

        Builds a stage-by-stage ``trace`` (the "thinking log" shown on the
        phone) and records the command in the personalisation memory.
        """
        from assistant.intent.rule_parser import RULE_THRESHOLD, RuleParserSkip
        from assistant.intent.context import ContextMemory
        from assistant.pipeline import _strip_stop_keyword
        from assistant.stt.vocab import apply_vocab
        from assistant.trace import (
            Trace, VOCAB, RULE, MEMORY, LLM, VALIDATE, EXECUTE, DONE, ERROR,
        )
        trace = trace or Trace(source="ios")
        parser = _get_parser()
        rule_parser = _get_rule_parser()
        cfg = load_config()

        raw_transcript = transcript
        # Parity with the Mac pipeline: drop trailing "execute"/"done"/… stop words
        transcript = _strip_stop_keyword(transcript, cfg.audio.stop_phrases)
        # Personal vocabulary auto-correct
        transcript, vocab_fixes = apply_vocab(transcript, source="ios")
        corrections = [c.to_dict() for c in vocab_fixes]
        trace.step(VOCAB, "Vocabulary",
                   ("Fixed " + ", ".join(f"{c.original}→{c.replacement}" for c in vocab_fixes))
                   if vocab_fixes else "No corrections needed",
                   transcript=transcript, corrections=corrections or None)

        parsed = None
        parse_path = "llm"
        rule_result = None
        llm_ms = 0

        def _llm_step(title: str) -> None:
            nonlocal llm_ms
            llm_ms += parser.last_llm_ms
            trace.step(LLM, title,
                       f"{cfg.llm_engine}:{getattr(cfg, cfg.llm_engine).model} · "
                       f"{parser.last_examples_used} history example(s) used",
                       raw=(parser.last_raw_response or "")[:1500] or None,
                       examples=parser.last_examples_used)

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
                    trace.step(RULE, "Rule parser",
                               f"Confident ({rule_result.confidence:.2f}) — no LLM needed: "
                               + ", ".join(n for n, _ in parsed),
                               confidence=round(rule_result.confidence, 2),
                               actions=[n for n, _ in parsed])
                else:
                    logger.info(
                        "📱 Rule partial handoff: confidence=%.2f missing=%s",
                        rule_result.confidence, rule_result.missing_slots,
                    )
                    trace.step(RULE, "Rule parser",
                               f"Partial ({rule_result.confidence:.2f})"
                               + (f", missing {', '.join(rule_result.missing_slots)}" if rule_result.missing_slots else "")
                               + " — asking the LLM to fill gaps",
                               confidence=round(rule_result.confidence, 2),
                               missing=list(rule_result.missing_slots) or None)
                    try:
                        parsed = parser.parse_with_context(transcript, rule_result)
                        parse_path = "hybrid"
                        _llm_step("LLM (hybrid)")
                    except AssistantError as e:
                        trace.step(LLM, "LLM (hybrid)", f"Failed: {e} — retrying full parse", ok=False)
                        parsed = None  # fall through to full LLM below
            except RuleParserSkip as e:
                logger.debug("📱 Rule parser skipped: %s", e)
                trace.step(RULE, "Rule parser", f"Skipped: {e}")
            except Exception as e:
                # Any other rule-parser failure is a bug in the fast path, not a
                # reason to lose the command: hand it to the LLM instead.
                logger.warning("📱 Rule parser error (falling back to the LLM): %s", e)
                trace.step(RULE, "Rule parser", f"Failed, using the LLM: {e}", ok=False)

        if parsed is None:
            try:
                parsed = parser.parse(transcript)
                _llm_step("LLM parse")
            except AssistantError as e:
                logger.warning("📱 Parse error: %s", e)
                from assistant.pipeline import Pipeline as _Pipeline
                _threading.Thread(
                    target=_Pipeline._append_nlu_log,
                    args=(transcript, "llm", False, [], [], False, f"parse_error: {e}", "ios"),
                    daemon=True,
                ).start()
                msg = str(e)
                pending_id = None
                retryable = any(w in msg.lower() for w in ("offline", "timed out", "timeout", "connection"))
                if retryable:
                    try:
                        from assistant.intent.memory import get_memory
                        pending_id = get_memory().add_pending(transcript, msg, source="ios")
                    except Exception as pe:
                        logger.warning("📱 Could not queue command: %s", pe)
                if "offline" in msg.lower():
                    msg = ("The AI model on your Mac (Ollama) is offline. I saved this command and "
                           "will run it automatically when the model is back — or tap Retry.")
                elif retryable:
                    msg = "The model took too long. I saved this command — tap Retry to try again."
                trace.step(ERROR, "Parse failed", str(e)
                           + (" — queued for retry" if pending_id else ""), ok=False)
                _record_memory(cfg, raw_transcript, transcript, "llm", [], msg, False, llm_ms, trace, [])
                resp = {"message": msg, "actions": [], "refresh": "", "parse": "error",
                        "transcript": transcript, "original_transcript": raw_transcript,
                        "corrections": corrections, "trace": trace.to_list(),
                        "uncertain_words": _uncertain(transcript)}
                if pending_id:
                    resp["pending_id"] = pending_id
                return resp

        parsed, fixes = _normalise_intents(parsed, transcript,
                                           rule_actions=list(rule_result.raw_slots) if rule_result is not None else [])
        if fixes:
            trace.step(VALIDATE, "Sanity fixes", "; ".join(fixes))
        logger.info("📱 Parsed actions: %s", [a for a, _ in parsed])
        trace.step(VALIDATE, "Validated",
                   ", ".join(f"{n}({', '.join(f'{k}={v}' for k, v in _intent_summary(i).items())})"
                             for n, i in parsed) or "no actions",
                   actions=[{"action": n, "parameters": _intent_summary(i)} for n, i in parsed])

        messages: list[str] = []
        action_names: list[str] = []
        refresh_set: set[str] = set()
        records: list[tuple[str, int, str]] = []
        ctx = ContextMemory()

        for action_name, intent in parsed:
            if action_name == "unknown":
                logger.warning("📱 Unknown intent for transcript: %s", transcript)
                messages.append("Sorry, I didn't understand that.")
                trace.step(EXECUTE, "Unknown intent", "The model returned no recognisable action", ok=False)
                continue
            registry = _get_registry()
            action_cls = registry.get(action_name)
            if action_cls is None:
                logger.warning("📱 No action class for: %s", action_name)
                trace.step(EXECUTE, action_name, "No such action registered", ok=False)
                continue
            try:
                ev_before, td_before = ctx.last_event_id, ctx.last_todo_id
                result = action_cls().execute(intent, cfg)
                logger.info("📱 Action %s → %s", action_name, result)
                messages.append(result or "")
                action_names.append(action_name)
                if ctx.last_event_id != ev_before and ctx.last_event_id is not None:
                    records.append(("event", ctx.last_event_id, action_name))
                if ctx.last_todo_id != td_before and ctx.last_todo_id is not None:
                    records.append(("todo", ctx.last_todo_id, action_name))
                trace.step(EXECUTE, action_name.replace("_", " ").title(), result or "done")
                if "event" in action_name:
                    refresh_set.add("events")
                elif "todo" in action_name:
                    refresh_set.add("todos")
            except Exception as e:
                logger.exception("📱 Action %s failed: %s", action_name, e)
                messages.append(f"Error: {e}")
                trace.step(EXECUTE, action_name.replace("_", " ").title(), f"Failed: {e}", ok=False)

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
        # Rule fast-path parity with the Mac: a placeholder title ("meeting",
        # "set meeting", …) gets a proper title from the LLM in the background.
        if parse_path == "rule":
            keywords = {k.lower() for k in cfg.nlu.event_keywords} | {"event", "set meeting", "meeting", "appointment"}
            for rtype, rid, act in records:
                if rtype == "event" and act == "create_event":
                    ev = get_db().get_event(rid)
                    if ev and ev["title"].strip().lower() in keywords:
                        _threading.Thread(target=_fix_title_bg, args=(transcript, rid, ev["title"]), daemon=True).start()

        trace.step(DONE, "Done", f"{parse_path} path · {trace.total_ms} ms total", path=parse_path)
        memory_id = _record_memory(cfg, raw_transcript, transcript, parse_path,
                                   [(n, i) for n, i in parsed if n != "unknown"],
                                   response_msg, _success, llm_ms, trace, records)

        # Background self-check (any parse path): LLM re-reasons over the
        # transcript + what ran + the user's history, and fixes itself if needed.
        verify_token: str | None = None
        checkable = [(n, i) for n, i in parsed if n in action_names and n not in ("clarify", "query_schedule", "query_todos")]
        if _success and checkable and cfg.verify_fast_path:
            import uuid
            verify_token = str(uuid.uuid4())
            with _verify_lock:
                _verify_store[verify_token] = {
                    "ready": False,
                    "correction": None,
                    "expires": _time.time() + 120,
                }
            _threading.Thread(
                target=_run_server_verify,
                args=(verify_token, transcript, rule_result, checkable, records, memory_id),
                daemon=True,
            ).start()

        resp: dict = {
            "message": response_msg,
            "actions": action_names,
            "refresh": refresh,
            "parse": parse_path,
            "transcript": transcript,
            "original_transcript": raw_transcript,
            "corrections": corrections,
            "trace": trace.to_list(),
            "uncertain_words": _uncertain(transcript),
        }
        if memory_id is not None:
            resp["memory_id"] = memory_id
        if verify_token:
            resp["verify_token"] = verify_token

        # Let the Mac's own window show what the phone just did. The GUI is a
        # separate process, so it can't see this Trace directly.
        try:
            from assistant import trace_bus
            trace_bus.publish(trace.source, resp["trace"], {
                "transcript": transcript,
                "message": response_msg,
                "actions": action_names,
                "corrections": corrections,
                "memory_id": memory_id,
            })
        except Exception:
            pass
        return resp

    def _uncertain(transcript: str) -> list:
        try:
            from assistant.stt.vocab import get_vocab
            return get_vocab().suggestions(transcript)
        except Exception:
            return []

    _RECUR_WORDS = [(r"\bevery\s*day\b|\bdaily\b", "daily"), (r"\bevery\s+\w+day\b|\bweekly\b|\b(?:mon|tues|wednes|thurs|fri|satur|sun)days\b", "weekly"),
                    (r"\bevery\s+month\b|\bmonthly\b", "monthly")]
    _JUNK_TITLES = {"task", "tasks", "todo", "event", "events", "reminder", "list", "item", "items"}

    _WD = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
           "mon": 0, "tue": 1, "tues": 1, "wed": 2, "thu": 3, "thur": 3, "thurs": 3, "fri": 4, "sat": 5, "sun": 6}

    def _relative_dates(transcript: str) -> list:
        """Deterministic reading of relative-date phrases, in order of appearance.
        Returns ISO dates. 'thursday' = coming Thursday (today if today is Thursday),
        'next thursday' = the one after that when today is Thursday, else the coming one
        in *next* week; 'tomorrow', 'today/tonight', 'the 19th' handled too."""
        import datetime as _dt, re as _re
        today = _dt.date.today(); out = []
        t = transcript.lower()
        pat = _re.compile(r"\b(day after tomorrow|tomorrow|today|tonight|this evening|this morning|"
                          r"(?:next|this|coming)\s+(?:week\s+(?:on\s+)?)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)s?|"
                          r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)s?|"
                          r"(?:on\s+)?the\s+(\d{1,2})(?:st|nd|rd|th)\b)")
        # "the 12th of August" / "August the 12th" name a month explicitly — the
        # bare-ordinal branch below must not claim those and resolve them to the
        # next 12th of *any* month, overriding what was said.
        _MONTHS = ("january|february|march|april|may|june|july|august|september|"
                   "october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec")
        for m in pat.finditer(t):
            full = m.group(1)
            if full == "day after tomorrow":
                out.append((today + _dt.timedelta(days=2)).isoformat())
            elif full == "tomorrow":
                out.append((today + _dt.timedelta(days=1)).isoformat())
            elif full in ("today", "tonight", "this evening", "this morning"):
                out.append(today.isoformat())
            elif m.group(2):                                   # next/this <weekday>
                wd = _WD[m.group(2)]; days = (wd - today.weekday()) % 7
                if full.startswith("next"):
                    days = (7 - today.weekday()) + wd     # that weekday in NEXT calendar week
                out.append((today + _dt.timedelta(days=days)).isoformat())
            elif m.group(3):                                   # bare weekday → coming one (today if today)
                wd = _WD[m.group(3)]; days = (wd - today.weekday()) % 7
                out.append((today + _dt.timedelta(days=days)).isoformat())
            elif m.group(4):                                   # the 19th → this month if not past, else next
                around = t[max(0, m.start() - 18):m.end() + 18]
                if _re.search(rf"\b(?:{_MONTHS})\b", around):
                    continue                                   # a month was named — leave it to the parser
                n = int(m.group(4)); d0 = today
                for _ in range(3):
                    try:
                        cand = d0.replace(day=n)
                    except ValueError:
                        cand = None
                    if cand and cand >= today:
                        out.append(cand.isoformat()); break
                    d0 = (d0.replace(day=1) + _dt.timedelta(days=32)).replace(day=1)
        return out

    _EVENING_WORDS = re.compile(r"\b(dinner|drinks?|beer|pub|bar|party|pregame|pizza|kems|movie|cinema|show|concert|tonight|evening|night|maariv|mincha)\b", re.I)

    def _bare_hour_pm(transcript: str, hhmm: str) -> str | None:
        """'Kems tomorrow at 8' → 20:00. A bare hour (no am/pm) between 1 and 8 is far
        more often PM in calendar speech; 7–8 only when evening words are present."""
        m = re.match(r"(\d{2}):(\d{2})", hhmm or "")
        if not m:
            return None
        h = int(m.group(1))
        if not (1 <= h <= 8):
            return None
        tl = transcript.lower()
        # was this hour spoken with am/pm or as 24h?  then leave it
        if re.search(rf"\b{h}(?::\d{{2}})?\s*(?:am|a\.m\.)\b", tl) or re.search(rf"\b0?{h}:\d{{2}}\b(?!\s*pm)", tl) and re.search(rf"\b(?:0{h}|{h+12}):", tl):
            return None
        if re.search(rf"\b{h}(?::\d{{2}})?\s*(?:pm|p\.m\.)\b", tl):
            return None
        if not re.search(rf"\b(?:at\s+)?{h}(?::\d{{2}})?\b", tl):
            return None
        if h <= 6 or _EVENING_WORDS.search(tl):
            return f"{h + 12:02d}:{m.group(2)}"
        return None

    def _normalise_intents(parsed, transcript: str, rule_actions=()):
        """Cheap deterministic guards on top of whatever parser produced the intents:
        • create_event dated in the past → next occurrence (LLMs pick yesterday's weekday)
        • recurrence words in the transcript but none on the intent → set it
        • hybrid junk: an extra create_event with a generic title and no real time
        Returns (parsed, list_of_human_readable_fixes)."""
        import datetime as _dt, re as _re
        today = _dt.date.today(); fixes = []; out = []
        tl = transcript.lower()
        recur = next((v for pat, v in _RECUR_WORDS if _re.search(pat, tl)), None)
        n_events = sum(1 for n, _ in parsed if n == "create_event")
        rel = _relative_dates(transcript)
        ev_idx = 0
        for name, intent in parsed:
            if name in ("update_event", "delete_event"):
                # "the event I just made / the last one" → anaphor, never a title guess.
                if _re.search(r"\b(just (made|created|added|set|scheduled)|last (event|one)|the one i just|you just)\b", tl) \
                        and not getattr(intent, "match_date", None) and not getattr(intent, "match_start_time", None):
                    if (getattr(intent, "match_title", "") or "").lower() != "it":
                        fixes.append(f"match_title '{intent.match_title}'→'it' (refers to the last event)")
                        intent.match_title = "it"
                # A day named in the sentence but no match_date → pin the search to that day
                # (the first date phrase is the event being referred to; a second one is the move-to date).
                elif rel and not getattr(intent, "match_date", None):
                    fixes.append(f"match_date →{rel[0]} (said in the sentence)")
                    intent.match_date = rel[0]
                    if name == "update_event" and len(rel) > 1 and not getattr(intent, "new_date", None):
                        intent.new_date = rel[1]
                out.append((name, intent)); continue
            if name == "create_event":
                d = getattr(intent, "date", None)
                # Deterministic relative dates beat the model's guess: one phrase → all
                # events; N phrases for N events → positional.
                if rel and not recur:
                    if len(set(rel)) == 1:
                        want = rel[0]                      # "tomorrow … tomorrow" → every event
                    else:
                        want = rel[ev_idx] if ev_idx < len(rel) and len(rel) == n_events else None
                    if want and d != want:
                        fixes.append(f"date {d}→{want} ('{transcript[:30]}…' says so)"); intent.date = want; d = want
                ev_idx += 1
                if d:
                    try:
                        dd = _dt.date.fromisoformat(d)
                        if dd < today:
                            # Roll a past date forward without throwing away what was
                            # actually said. Within a week back it's a weekday that has
                            # just gone ("Monday" said on Wednesday) → same weekday next
                            # week. Further back the speaker named a calendar day, so
                            # keep that day and month and move to next year.
                            # (This used to advance one day at a time, which always
                            # landed on today: "August 12 2026" became today's date.)
                            if (today - dd).days <= 7:
                                bump = dd
                                while bump < today:
                                    bump += _dt.timedelta(days=7)
                            else:
                                try:
                                    bump = dd.replace(year=dd.year + 1)
                                except ValueError:              # 29 Feb → 28 Feb
                                    bump = dd.replace(year=dd.year + 1, day=28)
                            intent.date = bump.isoformat(); fixes.append(f"date {d}→{intent.date} (was in the past)")
                    except ValueError:
                        pass
                if recur and not getattr(intent, "recurrence", None):
                    intent.recurrence = recur; fixes.append(f"recurrence={recur}")
                # A time the speaker introduced with "at" is when the thing
                # STARTS. The model sometimes files it as the end and invents an
                # earlier start — "dinner with Danny at 8 pm" came out 18:00–20:00.
                _at = _at_times(transcript)
                _s, _e = getattr(intent, "start_time", None), getattr(intent, "end_time", None)
                if _e and _e in _at and _s and _s not in _at:
                    try:
                        _hh, _mm = map(int, _e.split(":"))
                        intent.start_time = _e
                        intent.end_time = f"{(_hh + 1) % 24:02d}:{_mm:02d}"
                        fixes.append(f"start {_s}→{_e} ('at {_e}' is when it starts)")
                    except ValueError:
                        pass

                pm = _bare_hour_pm(transcript, getattr(intent, "start_time", None) or "")
                if pm and not re.search(r"\b(?:morning|breakfast|shacharit|am)\b", tl):
                    old_s, old_e = intent.start_time, getattr(intent, "end_time", None)
                    intent.start_time = pm
                    if old_e:
                        try:
                            hh, mm = map(int, old_e.split(":")); intent.end_time = f"{(hh + 12) % 24:02d}:{mm:02d}"
                        except Exception:
                            pass
                    fixes.append(f"bare hour {old_s}→{pm} (PM)")
                if "create_todo" in rule_actions and "create_event" not in rule_actions and not _spoken_times(transcript):
                    fixes.append(f"dropped event '{getattr(intent, 'title', '')}' — rule parser saw a task and no clock time was spoken"); continue
                t = (getattr(intent, "title", "") or "").strip().lower()
                if n_events > 0 and t in _JUNK_TITLES and any(n2 == "create_todo" for n2, _ in parsed):
                    fixes.append(f"dropped junk event '{t}'"); continue
            out.append((name, intent))
        return out, fixes

    def _intent_summary(intent) -> dict:
        try:
            return intent.model_dump(exclude_none=True, exclude_defaults=True)
        except Exception:
            return {}

    def _record_memory(cfg, raw, transcript, parse_path, actions, result, success,
                       llm_ms, trace, records) -> int | None:
        if not getattr(cfg.nlu, "memory_enabled", True):
            return None
        try:
            from assistant.intent.memory import get_memory
            return get_memory().record(
                transcript=transcript, raw_transcript=raw, source="ios",
                parse_path=parse_path, actions=actions, result=result,
                success=success, llm_ms=llm_ms, total_ms=trace.total_ms, records=records,
            )
        except Exception as e:
            logger.warning("📱 Memory record failed: %s", e)
            return None

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
        return jsonify(_run_transcript(transcript, trace))

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
                result = _run_transcript(transcript, trace)
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
        logger.info("📱 Text command: %s", transcript)
        return jsonify(_run_transcript(transcript))

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
        entry = get_vocab().add_word(word, aliases)
        return jsonify(entry.to_dict()), 201

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
        if "tags" in data:
            tags = data.get("tags") or []
        else:
            # Client didn't say — fall back to the server-side "tag mode".
            auto_tag = load_config().todo.auto_tag
            tags = [auto_tag] if auto_tag else []
        todo_id = db.create_todo(
            title=title,
            list_name=data.get("list_name", "today"),
            priority=data.get("priority", "none"),
            due_date=data.get("due_date", ""),
            notes=data.get("notes", ""),
            tags=tags,
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

    app._normalise_intents = _normalise_intents   # exposed for tests
    return app
