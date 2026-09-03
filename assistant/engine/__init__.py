"""The assistant engine — the brain behind every surface.

`run_transcript()` is the single entry point: the API server hands it text
(from the phone, the Mac GUI, the audit, the pending-retry loop) and gets back
the response dict every client already understands. Inside, the command runs
the 7-step deep track (`DOCUMENTATION/ENGINE.md` is the canonical contract
reference):

    0 intake      (here)            queueing + coalescing
    1 transcript  transcript.py     vocabulary repair + confidence gate
    2 segment     segment.py        split into typed items
    3 decompose   decompose.py      items that are several things, or one × N
    4 validate    validate.py       named format rules, text repair, observance
    5 generate    generate.py       items → intents (rules first, LLM for gaps)
    6 crosscheck  crosscheck.py     raw text vs. produced objects, loop-back
    7 label       label.py          category / tag read-back

The fast track is the same machinery short-circuited: when the rule parser is
confident about the whole input (generate.fast_propose), the answer is
committed instantly and the deep track's cross-check runs behind it.

Stages exchange ONLY the EngineState (state.py). Each is replaceable alone;
fixing a weak stage never means touching this orchestrator or another stage.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

from assistant.engine import (
    crosscheck as _crosscheck,
    decompose as _decompose,
    generate as _generate,
    label as _label,
    segment as _segment,
    transcript as _transcript,
    validate as _validate,
)
from assistant.engine.state import EngineState, ExecutedAction
from assistant.exceptions import AssistantError, TargetNotFound

logger = logging.getLogger(__name__)


def load_config():
    """config.yaml is local-only (gitignored); fall back to the example, then
    defaults (CI). The engine owns its config loading — it must never import
    from the API layer, which imports it."""
    from assistant.config import AppConfig, ConfigError, load_config as _load
    for path in ("config.yaml", "config.example.yaml"):
        try:
            return _load(path)
        except ConfigError:
            continue
    return AppConfig()


def _no_bg() -> bool:
    """Tests and the audit set MACALENDAR_NO_WARMUP=1: no daemon threads —
    a background model load beside a running suite segfaults the interpreter."""
    return os.environ.get("MACALENDAR_NO_WARMUP") == "1"


def run_transcript(text: str, trace: Any = None, source: str = "ios",
                   current_view: str = "month", trace_run: "str | None" = None,
                   supports_edit: bool = False) -> dict:
    """Parse and execute one transcript; return the API response dict.

    The response contract is frozen (clients depend on every key):
    message / actions / refresh / parse / transcript / original_transcript /
    corrections / trace / uncertain_words [+ memory_id, verify_token,
    pending_id, needs_edit].
    """
    from assistant.trace import Trace, DONE

    cfg = load_config()
    trace = trace or Trace(source=source)
    if trace_run:
        from assistant import trace_bus as _tb
        trace.on_step(lambda st: _tb.publish_step(trace_run, st.to_dict()))

    state = EngineState(raw_text=text, source=source, current_view=current_view,
                        supports_edit=supports_edit, trace=trace)

    # -- step 1: transcript repair ------------------------------------------
    _transcript.run(state, cfg)
    if state.ignored:
        # Not parsed, not executed, and above all not remembered: a false
        # start in the history teaches the model that junk is normal.
        logger.info("Ignoring a transcript with nothing in it: %r", text[:40])
        return {"message": "", "actions": [], "refresh": "", "parse": "ignored",
                "corrections": [], "trace": trace.to_list(), "memory_id": None}
    if state.needs_edit:
        # The gate: the client shows an editor and resubmits; nothing executes
        # on a transcript the vocabulary doubts.
        trace.step(DONE, "Checking with you",
                   "Some words look off — asking for an edit before acting.")
        return {"message": "I want to be sure I heard you right — please check "
                           "the transcription.",
                "actions": [], "refresh": "", "parse": "needs_edit",
                "needs_edit": state.needs_edit,
                "transcript": state.text, "original_transcript": state.raw_text,
                "corrections": state.corrections, "trace": trace.to_list(),
                "uncertain_words": state.needs_edit}

    # -- fast track ---------------------------------------------------------
    try:
        fast = _generate.fast_propose(state, cfg)
        if not fast:
            # -- deep track, foreground -------------------------------------
            _segment.run(state, cfg)
            _decompose.run(state, cfg)
            _validate.run(state, cfg)
            _generate.run(state, cfg)
    except AssistantError as e:
        return _parse_error_response(state, cfg, e)

    _validate.run_objects(state, cfg)
    _commit(state, cfg)
    _label.run(state, cfg)
    _crosscheck.run(state, cfg)

    # -- bookkeeping: reply, memory, logs, trace bus ------------------------
    response_msg = " ".join(m for m in state.messages if m)
    action_names = [ex.action for ex in state.executed if ex.ok]
    logger.info("%s Response: %s | refresh=%s | parse=%s",
                "🖥️" if source == "mac" else "📱",
                response_msg, state.refresh or "none", state.parse_path)

    _log_nlu(state, action_names)
    trace.step(DONE, "Done",
               f"{state.parse_path} path · {trace.total_ms / 1000:.1f} s total",
               path=state.parse_path)
    state.memory_id = _record_memory(state, cfg, response_msg)
    _mine_reformulations(state, cfg)

    resp: dict = {
        "message": response_msg,
        "actions": action_names,
        "refresh": state.refresh,
        "parse": state.parse_path,
        "transcript": state.text,
        "original_transcript": state.raw_text,
        "corrections": state.corrections,
        "trace": trace.to_list(),
        "uncertain_words": _transcript.uncertain_words(state.text),
    }
    if state.memory_id is not None:
        resp["memory_id"] = state.memory_id
    if state.verify_token:
        resp["verify_token"] = state.verify_token

    _publish(state, resp, trace_run)
    return resp


# ---------------------------------------------------------------------------
# Commit — the only place the engine touches the database, via the actions
# ---------------------------------------------------------------------------

def _commit(state: EngineState, cfg) -> None:
    from assistant.intent.context import ContextMemory
    from assistant.trace import EXECUTE

    registry = _generate.get_registry()
    ctx = ContextMemory()
    refresh_set: set = set()

    idx = 0
    for item in state.items:
        if item.blocked:
            # Refused, and the refusal explained — never silently dropped.
            title = getattr(item.intent, "title", None) or item.text[:40]
            state.messages.append(f"I didn't book '{title}': {item.blocked}.")
            if state.trace:
                state.trace.step(EXECUTE, "Held back", f"{item.id}: {item.blocked}", ok=False)
            continue
        if item.intent is None:
            continue                      # dropped by a validate rule (traced there)
        if item.action == "unknown":
            logger.warning("Unknown intent for item %s: %s", item.id, item.text[:60])
            state.messages.append("Sorry, I didn't understand that.")
            if state.trace:
                state.trace.step(EXECUTE, "Unknown intent",
                                 "The model returned no recognisable action", ok=False)
            continue
        action_cls = registry.get(item.action)
        if action_cls is None:
            logger.warning("No action class for: %s", item.action)
            if state.trace:
                state.trace.step(EXECUTE, item.action, "No such action registered", ok=False)
            continue
        pretty = item.action.replace("_", " ").title()
        try:
            ev_before, td_before = ctx.last_event_id, ctx.last_todo_id
            try:
                result = action_cls().execute(item.intent, cfg)
            except TargetNotFound as nf:
                # Empty slots surface as "I couldn't find …", which is the
                # right answer when the target cannot be identified. Guessing
                # is not. But a CONFIDENT parse that matches nothing is the one
                # signature of the rules being wrong that only execution can
                # reveal ("Walk Mark's dog" → complete_todo 'walk mark stalk'),
                # so a fast-track single action earns one LLM second opinion
                # before the not-found stands. Ownership of this recheck moves
                # into step 6 when it is built.
                replacement = None
                if state.parse_path == "fast" and len(state.items) == 1 \
                        and not state.messages:
                    replacement = _recheck_not_found(state, cfg, item)
                if replacement is None:
                    state.messages.append(nf.message)
                    state.executed.append(ExecutedAction(
                        item_id=item.id, action=item.action, message=nf.message, ok=False))
                    if state.trace:
                        state.trace.step(EXECUTE, pretty, nf.message, ok=False)
                    continue
                item.action, item.intent = replacement
                action_cls = registry.get(item.action)
                if action_cls is None:
                    state.messages.append(nf.message)
                    continue
                pretty = item.action.replace("_", " ").title()
                result = action_cls().execute(item.intent, cfg)
            record = None
            if ctx.last_event_id != ev_before and ctx.last_event_id is not None:
                record = ("event", ctx.last_event_id, item.action, idx)
            elif ctx.last_todo_id != td_before and ctx.last_todo_id is not None:
                record = ("todo", ctx.last_todo_id, item.action, idx)
            state.messages.append(result or "")
            state.executed.append(ExecutedAction(
                item_id=item.id, action=item.action, message=result or "",
                ok=True, record=record))
            if state.trace:
                state.trace.step(EXECUTE, pretty, result or "done")
            if "event" in item.action:
                refresh_set.add("events")
            elif "todo" in item.action:
                refresh_set.add("todos")
            idx += 1
        except Exception as e:
            logger.exception("Action %s failed: %s", item.action, e)
            state.messages.append(f"Error: {e}")
            state.executed.append(ExecutedAction(
                item_id=item.id, action=item.action, message=str(e), ok=False))
            if state.trace:
                state.trace.step(EXECUTE, pretty, f"Failed: {e}", ok=False)

    if "events" in refresh_set and "todos" in refresh_set:
        state.refresh = "both"
    elif refresh_set:
        state.refresh = refresh_set.pop()


def _recheck_not_found(state: EngineState, cfg, item) -> "tuple | None":
    """One LLM second opinion on a confident parse whose target is missing.
    Returns (action, intent) to run instead, or None to let the not-found
    stand — including when the LLM agrees the target really is absent."""
    from assistant.trace import LLM, RULE

    if state.trace:
        state.trace.step(RULE, "Nothing matched — rechecking",
                         f"{(item.action or '').replace('_', ' ')} found no target "
                         "— asking the LLM instead")
    try:
        retried = _generate._get_parser(cfg).parse(state.text) or []
    except Exception as e:
        if state.trace:
            state.trace.step(LLM, "LLM", f"Unavailable ({e}) — keeping the answer", ok=False)
        return None
    candidates = [(n, i) for n, i in retried if n != "unknown"]
    if len(candidates) == 1 and candidates[0][0] != item.action:
        if state.trace:
            state.trace.step(LLM, "LLM",
                             f"Re-read it as {candidates[0][0].replace('_', ' ')}")
        return candidates[0]
    if candidates and state.trace:
        state.trace.step(LLM, "LLM", "Agrees — the target really is missing", ok=False)
    return None


# ---------------------------------------------------------------------------
# Failure, memory, logging, publishing
# ---------------------------------------------------------------------------

def _parse_error_response(state: EngineState, cfg, e: AssistantError) -> dict:
    from assistant.trace import ERROR

    logger.warning("Parse error: %s", e)
    state.parse_path = "error"
    msg = str(e)
    pending_id = None
    retryable = any(w in msg.lower() for w in ("offline", "timed out", "timeout", "connection"))
    if retryable:
        try:
            from assistant.intent.memory import get_memory
            pending_id = get_memory().add_pending(state.text, msg, source=state.source)
        except Exception as pe:
            logger.warning("Could not queue command: %s", pe)
    if "offline" in msg.lower():
        msg = ("The AI model on your Mac (Ollama) is offline. I saved this command and "
               "will run it automatically when the model is back — or tap Retry.")
    elif retryable:
        msg = "The model took too long. I saved this command — tap Retry to try again."
    if state.trace:
        state.trace.step(ERROR, "Parse failed", str(e)
                         + (" — queued for retry" if pending_id else ""), ok=False)
    _log_nlu(state, [], failure=f"parse_error: {e}")
    state.memory_id = _record_memory(state, cfg, msg, success=False)
    resp = {"message": msg, "actions": [], "refresh": "", "parse": "error",
            "transcript": state.text, "original_transcript": state.raw_text,
            "corrections": state.corrections,
            "trace": state.trace.to_list() if state.trace else [],
            "uncertain_words": _transcript.uncertain_words(state.text)}
    if pending_id:
        resp["pending_id"] = pending_id
        state.pending_id = pending_id
    return resp


def _record_memory(state: EngineState, cfg, result_msg: str,
                   success: "bool | None" = None) -> "int | None":
    if not getattr(cfg.nlu, "memory_enabled", True):
        return None
    if success is None:
        success = any(ex.ok for ex in state.executed)
    try:
        from assistant.intent.memory import get_memory
        return get_memory().record(
            transcript=state.text, raw_transcript=state.raw_text, source=state.source,
            parse_path=state.parse_path,
            actions=[(it.action, it.intent) for it in state.items
                     if it.intent is not None and it.action and it.action != "unknown"],
            result=result_msg, success=success, llm_ms=state.llm_ms,
            total_ms=state.trace.total_ms if state.trace else 0,
            records=[ex.record for ex in state.executed if ex.record],
            confidence=state.rule_confidence,
        )
    except Exception as e:
        logger.warning("Memory record failed: %s", e)
        return None


def _log_nlu(state: EngineState, action_names: list, failure: str = "") -> None:
    """NLU_TRACKING.md — appended after every action, success and failure."""
    try:
        from assistant.pipeline import Pipeline
        success = bool(action_names)
        reason = failure or ("" if success else (
            "unknown_intent" if not any(it.action and it.action != "unknown"
                                        for it in state.items if it.intent is not None)
            else "action_failed"))
        threading.Thread(
            target=Pipeline._append_nlu_log,
            args=(state.text, state.parse_path, state.parse_path == "fast",
                  action_names or [it.action for it in state.items
                                   if it.action and it.action != "unknown"],
                  state.messages if success else [],
                  success, reason, state.source),
            daemon=True,
        ).start()
    except Exception:
        pass


def _mine_reformulations(state: EngineState, cfg) -> None:
    """A retry is a correction the speaker already gave, by doing it again.
    Daemon thread; nothing waits on it; idempotent."""
    if _no_bg() or state.source == "test" or not getattr(cfg.nlu, "memory_enabled", True):
        return

    def _was_a_retry(wrong: str, right: str) -> bool:
        parser = _generate._get_parser(cfg)
        answer = parser.call_llm_json(
            "You judge whether a second voice command was a RETRY of the first — "
            "the speaker being misheard or misunderstood, and saying it again — "
            "or a SEPARATE thing they also wanted. Answer only with JSON: "
            '{"retry": true} or {"retry": false}. '
            "Say false unless it is clearly the same request restated.",
            f"FIRST (was deleted): {wrong}\nSECOND: {right}",
        )
        return bool(answer.get("retry") is True)

    def _mine() -> None:
        try:
            from assistant.intent.memory import get_memory
            for pair in get_memory().learn_from_reformulations(verify=_was_a_retry):
                logger.info("Learned from a retry: %r -> %r (%.0fs apart)",
                            pair["wrong"][:48], pair["right"][:48], pair["gap_sec"])
        except Exception as exc:
            logger.debug("Reformulation pass failed: %s", exc)

    threading.Thread(target=_mine, daemon=True, name="reformulations").start()


def _publish(state: EngineState, resp: dict, trace_run: "str | None") -> None:
    """Let the HUD (a separate process) see this run: stream into the caller's
    open bus run when there is one, else publish the whole thing."""
    try:
        from assistant import trace_bus
        payload = {
            "transcript": state.text,
            "message": resp["message"],
            "actions": resp["actions"],
            "corrections": state.corrections,
            "memory_id": state.memory_id,
        }
        if trace_run:
            trace_bus.publish_result(trace_run, payload)
        else:
            trace_bus.publish(state.trace.source if state.trace else state.source,
                              resp["trace"], payload)
    except Exception:
        pass
