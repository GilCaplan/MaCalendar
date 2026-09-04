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


def _brain_version() -> str:
    from assistant.trace import BRAIN_VERSION
    return BRAIN_VERSION

# Step 0, half one: one command at a time. Flask serves requests on threads,
# and two commands interleaving would race the anaphora context ("the one I
# just made") and the per-run trace. Waiting here is the intake queue — FIFO,
# invisible, and the wait shows up honestly in the trace's total.
_run_lock = threading.Lock()


def coalesce(texts: "list[str]", max_tokens: int = 300) -> "list[str]":
    """Step 0, half two: queued inputs are combined into ("…")and("…") batches
    up to a token budget (≈4 chars/token), so several short queued commands
    cost one parse instead of several; overflow runs in later batches. The
    wrapper is deterministic for step 2 to split — logic stays independent."""
    batches: list[str] = []
    current: list[str] = []
    used = 0
    for text in texts:
        t = (text or "").strip()
        if not t:
            continue
        cost = max(1, len(t) // 4)
        if current and used + cost > max_tokens:
            batches.append(_wrap(current))
            current, used = [], 0
        current.append(t)
        used += cost
    if current:
        batches.append(_wrap(current))
    return batches


def _wrap(parts: "list[str]") -> str:
    if len(parts) == 1:
        return parts[0]
    return "and".join(f'("{p}")' for p in parts)


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
    from assistant.trace import Trace

    cfg = load_config()
    trace = trace or Trace(source=source)
    if trace_run:
        from assistant import trace_bus as _tb
        trace.on_step(lambda st: _tb.publish_step(trace_run, st.to_dict()))

    with _run_lock:
        return _run_locked(text, trace, source, current_view, trace_run,
                           supports_edit, cfg)


def _run_locked(text, trace, source, current_view, trace_run,
                supports_edit, cfg) -> dict:
    from assistant.trace import DONE

    state = EngineState(raw_text=text, source=source, current_view=current_view,
                        supports_edit=supports_edit, trace=trace)

    # -- step 1: transcript repair ------------------------------------------
    _transcript.run(state, cfg)
    if state.ignored:
        # Not parsed, not executed, and above all not remembered: a false
        # start in the history teaches the model that junk is normal.
        logger.info("Ignoring a transcript with nothing in it: %r", text[:40])
        return {"message": "", "actions": [], "refresh": "", "parse": "ignored",
                "corrections": [], "trace": trace.to_list(), "memory_id": None,
                "brain": _brain_version()}
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
                "uncertain_words": state.needs_edit, "brain": _brain_version()}

    # -- fast track ---------------------------------------------------------
    try:
        fast = cfg.engine.fast_track and _generate.fast_propose(state, cfg)
        if fast:
            _validate.run_objects(state, cfg)
            _commit(state, cfg)
            _label.run(state, cfg)
            # The deep track runs BEHIND the instant answer: extraction-based
            # cross-check against what was just committed, patches through the
            # verify-token contract the clients already speak.
            _start_background_verify(state, cfg)
        else:
            # -- deep track, foreground -------------------------------------
            _deep_parse(state, cfg)
            # Step 6 runs BEFORE anything is written: findings loop execution
            # back to the blamed stage (fresh intents each time, so the
            # field rules cannot double-apply), at most MAX_REENTRIES total.
            reentries = 0
            while reentries < _crosscheck.MAX_REENTRIES:
                _crosscheck.run(state, cfg)
                loop_to = _loop_target(state)
                if loop_to is None:
                    break
                reentries += 1
                state.retries[loop_to] = state.retries.get(loop_to, 0) + 1
                if state.trace:
                    from assistant.trace import VERIFY
                    state.trace.step(VERIFY, "Looping back",
                                     f"re-running from {loop_to} "
                                     f"({reentries}/{_crosscheck.MAX_REENTRIES})")
                _deep_parse(state, cfg)
            else:
                # Budget spent with a MISSING ask still open — flag it.
                # (Advisory extras alone don't merit alarming the speaker.)
                if any(f.type == "missing" for f in state.findings):
                    state.messages.append(
                        "I'm not sure I caught every part of that — worth a glance.")
            _commit(state, cfg)
            _label.run(state, cfg)
    except AssistantError as e:
        return _parse_error_response(state, cfg, e)

    # -- bookkeeping: reply, memory, logs, trace bus ------------------------
    # A loop-back re-runs generate, and a per-item failure message from each
    # attempt survives on the state — saying "I couldn't read this part"
    # three times is one apology and two bugs. Consecutive duplicates fold.
    deduped: list = []
    for m in state.messages:
        if m and (not deduped or m != deduped[-1]):
            deduped.append(m)
    response_msg = " ".join(deduped)
    action_names = [ex.action for ex in state.executed if ex.ok]
    logger.info("%s Response: %s | refresh=%s | parse=%s",
                "🖥️" if source == "mac" else "📱",
                response_msg, state.refresh or "none", state.parse_path)

    _log_nlu(state, action_names)
    if state.parse_path == "fast":
        # The fast path has ANSWERED, but a background review still runs — so
        # this is not "Done", it is "answered, reviewing". Saying Done here read
        # as finished when it was not.
        trace.step(DONE, "Fast answer",
                   f"rules answered in {trace.total_ms / 1000:.1f} s · reviewing in the background",
                   path=state.parse_path)
    else:
        trace.step(DONE, "Done",
                   f"deep path · {trace.total_ms / 1000:.1f} s total",
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
        "brain": _brain_version(),
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
                # is not. But a parse that matches nothing is the one signature
                # of a misread that only execution can reveal — the rules'
                # "Walk Mark's dog" → complete_todo 'walk mark stalk', and the
                # LLM's "night shift tomorrow 8pm–6am" → update_event on an
                # event that never existed (run 9) — so a single-action command
                # earns one second opinion before the not-found stands,
                # whichever track produced it. Ownership of this recheck moves
                # into step 6 when it absorbs the last of the old bolt-ons.
                replacement = None
                if len(state.items) == 1 and not state.messages:
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


def _deep_parse(state: EngineState, cfg) -> None:
    """Steps 2→5 + the field rules — the deep track's parse half, re-runnable:
    items are rebuilt from scratch each time (fresh intents, so no field rule
    can apply twice), and any loop-back mistakes are already on the state for
    the stages' prompts."""
    state.items = []
    _segment.run(state, cfg)
    _decompose.run(state, cfg)
    _validate.run(state, cfg)
    _generate.run(state, cfg)
    _validate.run_objects(state, cfg)


def _loop_target(state: EngineState) -> "str | None":
    """The earliest stage the findings blame, or None when there is nothing
    to loop for. Only MISSING findings earn a loop: a re-run can recover an
    ask that was merged away, but it cannot un-produce an extra (segment is
    under-split-biased, so an "extra" is far more often the matcher's
    artefact than real over-production — run 8 measured 39 loop storms, most
    of them exactly that). Extras stay advisory findings. Only stages whose
    re-run rebuilds intents are loopable — re-running the field rules on the
    SAME objects would double-apply them."""
    for f in state.findings:
        if f.type == "missing" and f.blamed_stage in ("segment", "generate"):
            return "segment"   # a segment re-run rebuilds everything after it
    return None


# ---------------------------------------------------------------------------
# Fast track's background verify — the deep track running behind the answer
# ---------------------------------------------------------------------------

def _verify_store():
    """The token store the clients poll (GET /voice/verify/<token>). It lives
    with the HTTP layer; both sides import lazily so neither owns the other at
    import time."""
    from assistant.api.server import _verify_store as store, _verify_lock as lock
    return store, lock


def _start_background_verify(state: EngineState, cfg) -> None:
    """Issue a verify token and run the cross-check behind the instant answer.

    Patch tiers, applied here when the check disagrees:
      • additive (a missing ask): parsed and committed, minor severity —
        "I also added …".
      • title (a placeholder like "meeting"): renamed in place, minor.
      • destructive (an extra row): honoured only when `self_check_apply`
        says so — the old always-on verifier measurably proposed far more
        than it fixed, so removal ships ADVISORY: said, not done.
    """
    reconcile = getattr(cfg.engine, "reconcile", "always")
    if reconcile == "uncertain" and state.rule_confidence >= 0.95:
        return
    import uuid

    token = str(uuid.uuid4())
    store, lock = _verify_store()
    import time as _t
    with lock:
        store[token] = {"ready": False, "correction": None, "expires": _t.time() + 120}
    state.verify_token = token

    def _work() -> None:
        try:
            correction = _background_verify(state, cfg)
        except Exception as e:
            logger.debug("Background verify failed: %s", e)
            correction = None
        with lock:
            if token in store:
                store[token]["ready"] = True
                store[token]["correction"] = correction or {"ok": True}

    threading.Thread(target=_work, daemon=True, name="crosscheck-bg").start()


def _background_verify(state: EngineState, cfg) -> "dict | None":
    """The check itself, on the worker thread. Returns the correction payload
    for the verify endpoint (None = agreed)."""
    from assistant.engine.validate import is_placeholder_title

    speech: list[str] = []
    refresh: set = set()
    severity = "minor"

    # A placeholder title ("meeting") is renamed before anything else — 22 of
    # 37 flagged titles in a week were the bare word "meeting".
    for ex in state.executed:
        if not (ex.ok and ex.record and ex.record[0] == "event"
                and ex.record[2] == "create_event"):
            continue
        from assistant.db import get_db
        ev = get_db().get_event(ex.record[1])
        if ev and is_placeholder_title(ev["title"], cfg):
            try:
                better = _generate._get_parser(cfg).fix_title_async(
                    state.text, ev["title"])
            except Exception:
                better = None
            if better and better.strip().lower() != ev["title"].strip().lower():
                get_db().update_event(ex.record[1], title=better.strip())
                speech.append(f"I named it “{better.strip()}”.")
                refresh.add("events")

    _crosscheck.run(state, cfg)
    for f in state.findings:
        if f.type == "missing":
            # Run 8's lesson, same as the old verifier's: the check PROPOSES
            # far more than it should apply — four commands were broken by
            # confident duplicate adds ("add eggs" vs the row "buy eggs").
            # Additive lands only under self_check_apply; advisory otherwise.
            if getattr(cfg, "self_check_apply", False):
                made = _commit_missing_ask(state, cfg, f)
                if made:
                    speech.append(made)
                    refresh.update(("events", "todos"))
            else:
                severity = "major"
                speech.append(f"Worth a look: {f.detail}.")
        elif f.type == "extra":
            if getattr(cfg, "self_check_apply", False):
                undone = _remove_extra(state, f)
                if undone:
                    severity = "major"
                    speech.append(undone)
                    refresh.update(("events", "todos"))
            else:
                severity = "major"
                speech.append(f"Worth a look: {f.detail}.")

    if not speech:
        return None
    both = "both" if len(refresh) > 1 else (refresh.pop() if refresh else "")
    return {"ok": False, "severity": severity, "patch": {},
            "speech": " ".join(speech), "refresh": both}


def _commit_missing_ask(state: EngineState, cfg, finding) -> "str | None":
    """An ask the fast parse dropped: parse just its words and commit it."""
    import re as _re
    m = _re.search(r"“(.+?)”", finding.detail)
    if not m:
        return None
    words = m.group(1)
    from assistant.engine.state import Item
    sub = EngineState(raw_text=words, text=words, source=state.source,
                      current_view=state.current_view, mode="background")
    sub.items = [Item(id="item_1", kind="other", text=words)]
    try:
        _generate.run(sub, cfg)
        _validate.run_objects(sub, cfg)
        _commit(sub, cfg)
    except Exception:
        return None
    done = [m2 for m2 in sub.messages if m2]
    if any(ex.ok for ex in sub.executed):
        return "I first missed part of that — " + " ".join(done)
    return None


def _remove_extra(state: EngineState, finding) -> "str | None":
    """Delete a committed row the words never asked for (self_check_apply on)."""
    from assistant.db import get_db
    for ex in state.executed:
        if ex.item_id == finding.item_id and ex.ok and ex.record:
            kind, row_id = ex.record[0], ex.record[1]
            try:
                if kind == "event":
                    get_db().delete_event(row_id)
                    return "I removed an event I created by mistake."
                get_db().delete_todo(row_id)
                return "I removed a task I created by mistake."
            except Exception:
                return None
    return None


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
            "uncertain_words": _transcript.uncertain_words(state.text),
            "brain": _brain_version()}
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
    """NLU_TRACKING.md — appended after every action, success and failure.

    Except test traffic: the file is the record of real usage, and the audit's
    89 synthetic commands per run would drown it — the same lesson the trace
    bus taught (its History filters "test" for the same reason)."""
    if state.source == "test":
        return
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
            "brain": _brain_version(),
        }
        if trace_run:
            trace_bus.publish_result(trace_run, payload)
        else:
            trace_bus.publish(state.trace.source if state.trace else state.source,
                              resp["trace"], payload)
    except Exception:
        pass
