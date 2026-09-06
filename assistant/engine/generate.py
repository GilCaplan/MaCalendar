"""Step 5 — turn items into concrete intents (and own the fast-track proposal).

Contract (see DOCUMENTATION/ENGINE.md):
  fast_propose(state, cfg) -> bool
      The whole-input rule-parser proposal. On confidence ≥ RULE_THRESHOLD
      with no missing slots it fills state.items with one Item per intent,
      sets state.parse_path="fast" and state.rule_confidence, and returns
      True — the orchestrator then commits instantly and runs the deep track
      in the background. Always records the score it saw.
  run(state, cfg) -> state
      Deep track, per item:
      reads   item.text, item.slots, state.text
      writes  item.action, item.intent (an item whose text parses into
              several intents is expanded into sub-items, one intent each —
              per-item attribution is what keeps feedback from corrupting a
              neighbour, the row-75 lesson), state.llm_ms, trace (RULE/LLM)

All text→intent conversion lives here and nowhere else. The rule parser is
consulted first per item (free, ~50ms); the LLM fills gaps from the rule
parser's partial analysis or parses from scratch. Prompts are grounded on the
item's own words — never another item's.
"""

from __future__ import annotations

import logging
import re

from assistant.engine.state import EngineState, Item

logger = logging.getLogger(__name__)

_parser = None
_rule_parser = None
_RULE_PARSER_MISSING = object()   # spaCy absent: checked once, then skipped


def get_registry():
    """The action registry, with every action module imported (they
    self-register via @register on import)."""
    import assistant.actions.calendar          # noqa: F401
    import assistant.actions.todo              # noqa: F401
    import assistant.actions.clarify           # noqa: F401
    import assistant.actions.workout_routine   # noqa: F401
    import assistant.actions.schedule_workout  # noqa: F401
    from assistant.actions import ActionRegistry
    return ActionRegistry()


def _get_parser(cfg):
    global _parser
    if _parser is None:
        from assistant.intent.parser import IntentParser
        _parser = IntentParser(cfg, get_registry())
    return _parser


def _get_rule_parser():
    global _rule_parser
    if _rule_parser is _RULE_PARSER_MISSING:
        return None
    if _rule_parser is None:
        from assistant.intent.rule_parser import (
            RuleBasedParser, _RULE_PARSER_AVAILABLE,
        )
        if not _RULE_PARSER_AVAILABLE:
            _rule_parser = _RULE_PARSER_MISSING
            return None
        _rule_parser = RuleBasedParser(get_registry())
    return _rule_parser


def reset_parsers() -> None:
    """Tests swap config; cached parsers must not outlive it."""
    global _parser, _rule_parser
    _parser = None
    _rule_parser = None


# A joiner that all but announces a second request. Deliberately much narrower
# than segment's _COMPOUND_HINT: a plain "and" joins guests and groceries far
# more often than requests, but ". Also," / ", and then" / " — and" almost
# never appear inside ONE ask. Cycle 3 of the dataset loop: every observed
# fast-path mangle ("…at 9am, and then Remind me…" committing a todo literally
# titled "then") was a confident SINGLE-intent parse of text carrying one of
# these.
#: A mutation whose match_title is just the ask-noun targets nothing (cycle 6).
_GENERIC_TARGET_RE = re.compile(
    r"^(?:my |the |a |an )?(?:reminder|alert|event|appointment|task|todo)s?$",
    re.I)

_STRONG_COMPOUND_RE = re.compile(
    r"\band\s+(?:then|also)\b"          # "and then", "and also"
    r"|[.;!?]\s+(?:also|then|plus|and)\b"   # a sentence break, then a joiner
    r"|\s[—–]\s*and\b"                  # " — and"
    r"|,\s*then\b",                     # ", then"
    re.I)


def fast_propose(state: EngineState, cfg) -> bool:
    from assistant.intent.rule_parser import RULE_THRESHOLD, RuleParserSkip
    from assistant.trace import RULE

    rule_parser = _get_rule_parser()
    if rule_parser is None:
        return False
    try:
        rr = rule_parser.analyze(state.text, current_view=state.current_view)
    except RuleParserSkip as e:
        if state.trace:
            state.trace.step(RULE, "Rule parser", f"Skipped: {e}")
        return False
    except Exception as e:
        # A fast-path bug is not a reason to lose the command.
        if state.trace:
            state.trace.step(RULE, "Rule parser", f"Failed, deep track instead: {e}", ok=False)
        return False

    state.rule_confidence = float(rr.confidence)
    if (len(rr.intents) <= 1 and _STRONG_COMPOUND_RE.search(state.text)):
        # A one-request reading of two-request wording: however confident the
        # score, the parse swallowed a compound. The deep track splits first.
        if state.trace:
            state.trace.step(RULE, "Rule parser",
                             "Confident but the words announce a second request "
                             "— deep track", ok=True)
        return False
    for name, intent in rr.intents:
        # Cycle 6: "set reminder at 3 pm" fast-committed
        # update_todo(match_title="reminder") — a mutation aimed at the bare
        # ask-noun is no target at all (the same ethos as the delete
        # not-found rule). Deep handles it: event_fallback for the set-shape,
        # anaphora/not-found for real edits.
        if name.startswith(("update_", "delete_", "complete_")):
            target = str(getattr(intent, "match_title", "") or "").strip()
            if _GENERIC_TARGET_RE.match(target):
                if state.trace:
                    state.trace.step(RULE, "Rule parser",
                                     f"Confident but “{target}” is a generic noun, "
                                     "not a target — deep track", ok=True)
                return False
    if rr.confidence >= RULE_THRESHOLD and not rr.missing_slots:
        state.items = [
            Item(id=f"item_{i + 1}", kind=_kind_for(name), text=state.text,
                 action=name, intent=intent)
            for i, (name, intent) in enumerate(rr.intents)
        ]
        state.parse_path = "fast"
        if state.trace:
            state.trace.step(RULE, "Rule parser",
                             f"Confident ({rr.confidence:.2f}) — instant: "
                             + ", ".join(n for n, _ in rr.intents),
                             confidence=round(rr.confidence, 2),
                             actions=[n for n, _ in rr.intents])
        return True

    if state.trace:
        state.trace.step(RULE, "Rule parser",
                         f"Partial ({rr.confidence:.2f})"
                         + (f", missing {', '.join(rr.missing_slots)}" if rr.missing_slots else "")
                         + " — deep track",
                         confidence=round(rr.confidence, 2),
                         missing=list(rr.missing_slots) or None)
    return False


def _kind_for(action_name: str) -> str:
    if "todo" in action_name:
        return "task"
    if "event" in action_name:
        return "event"
    if "query" in action_name or "schedule" in action_name:
        return "review"
    return "other"


def _friendly(item_id: str) -> str:
    """item_1 -> "part 1", item_1-2 -> "part 1.2" — legible in the trace chain."""
    return "part " + item_id.replace("item_", "").replace("-", ".")


def _llm_trace(state: EngineState, parser, cfg, title: str) -> None:
    from assistant.trace import LLM
    state.llm_ms += parser.last_llm_ms
    if state.trace:
        state.trace.step(LLM, title,
                         f"{cfg.llm_engine}:{getattr(cfg, cfg.llm_engine).model} · "
                         f"{parser.last_examples_used} history example(s) used",
                         raw=(parser.last_raw_response or "")[:1500] or None,
                         examples=parser.last_examples_used)


def _parse_item(item: Item, state: EngineState, cfg) -> "list | None":
    """One item's text → intents. Rules first, LLM for the gaps."""
    from assistant.intent.rule_parser import RULE_THRESHOLD, RuleParserSkip

    parser = _get_parser(cfg)
    rule_parser = _get_rule_parser()
    if rule_parser is not None:
        try:
            rr = rule_parser.analyze(item.text, current_view=state.current_view)
            if rr.confidence >= RULE_THRESHOLD and not rr.missing_slots:
                if state.trace:
                    from assistant.trace import RULE
                    state.trace.step(RULE, f"Read {_friendly(item.id)}",
                                     f"{rr.confidence:.2f}: " + ", ".join(n for n, _ in rr.intents))
                return rr.intents
            try:
                got = parser.parse_with_context(item.text, rr)
                _llm_trace(state, parser, cfg, f"Read {_friendly(item.id)}")
                return _guard_inventions(got, item, state)
            except Exception:
                pass
        except RuleParserSkip:
            pass
        except Exception:
            pass
    got = parser.parse(item.text)
    _llm_trace(state, parser, cfg, f"Read {_friendly(item.id)}")
    return _guard_inventions(got, item, state)


#: Words too generic to ground a title on their own (cycle 7).
_TITLE_STOP = {"the", "a", "an", "and", "with", "for", "new", "my", "our"}


def _grounded_title(title: str, text: str) -> bool:
    """Every content word of an LLM event title must be spoken in the item's
    own words, prefix-stemmed so "Meeting" grounds on "meet". A title the
    words never said is a fabrication (hypothesis #5: garble input produced
    "New Event", conference room, 10:00-11:00 — none of it in the words)."""
    words = [w for w in re.findall(r"[a-z']+", title.casefold())
             if len(w) > 2 and w not in _TITLE_STOP]
    if not words:
        return True                       # bare/stopword titles judged elsewhere
    toks = set(re.findall(r"[a-z']+", text.casefold()))
    def ok(w: str) -> bool:
        stem = w[:4]
        return any(tk.startswith(stem) or w.startswith(tk[:4])
                   for tk in toks if len(tk) > 2)
    return all(ok(w) for w in words)


def _guard_inventions(got, item: Item, state: EngineState):
    """Drop LLM-fabricated events (cycle 7); rule-parser output never routes
    through here — rules are grounded by construction. An emptied list falls
    through to the event-kind retry / event_fallback / honest unknown."""
    if not got:
        return got
    kept = []
    for name, intent in got:
        if name == "create_event" and item.kind != "task":
            title = str(getattr(intent, "title", "") or "")
            if not _grounded_title(title, item.text):
                state.add_fix("generate", "invention_guard", title[:40], "",
                              note="LLM title not grounded in the item's words")
                continue
        kept.append((name, intent))
    return kept


def run(state: EngineState, cfg) -> EngineState:
    from assistant.exceptions import LLMTimeoutError, LLMUnavailableError, ParseError

    out: list = []
    for item in state.items:
        try:
            got = _parse_item(item, state, cfg)
        except (LLMUnavailableError, LLMTimeoutError):
            raise            # the orchestrator owns offline queueing
        except ParseError as e:
            # One unreadable item must not kill its neighbours (a validation
            # error on "bowling tuesday night" once took the whole command
            # down). Honest per-item failure; the rest still executes.
            logger.warning("Item %s failed to parse: %s", item.id, e)
            state.add_fix("generate", "item_parse_failed", item.text[:40], "",
                          note=str(e)[:120])
            state.messages.append(
                f"Sorry, I couldn't read this part: “{item.text[:60]}”.")
            out.append(item)
            continue
        if item.kind == "event" and got is not None and \
                not any(("event" in n or n in ("clarify", "query_schedule"))
                        for n, _ in got if n != "unknown"):
            # Segmentation judged these words an EVENT; a parse that yields
            # only todos or unknowns contradicts that judgment. Tasks have a
            # fallback — events silently died instead (the missing-event
            # signature: 72% of event+task failures). One retry, restating
            # segment's own judgment in the words.
            try:
                retried = _get_parser(cfg).parse(f"set an event: {item.text}")
                _llm_trace(state, _get_parser(cfg), cfg, f"Re-read {_friendly(item.id)} as an event")
            except Exception:
                retried = None
            if retried and any("event" in n for n, _ in retried if n != "unknown"):
                state.add_fix("generate", "event_kind_retry", "", item.text[:40],
                              note="the parse contradicted the item's event kind")
                got = retried
        if item.kind == "event" and (not got or all(n == "unknown" for n, _ in got)):
            fb = _event_fallback(item.text)
            if fb is not None:
                item.action, item.intent = "create_event", fb
                state.add_fix("generate", "event_fallback", "", item.text[:40],
                              note="literal set-an-event ask with a grounded when")
                out.append(item)
                continue
        if item.kind == "task" and (not got or all(n == "unknown" for n, _ in got)):
            # Segmentation already judged these words a to-do; a parse that
            # comes back empty for them is the model failing the words, not
            # the words failing to be a task ("submit the Haxaga grades" →
            # unknown, run 12). The item text IS the task.
            from assistant.actions.todo.intent import CreateTodoIntent
            try:
                item.action = "create_todo"
                item.intent = CreateTodoIntent(titles=[item.text.strip()])
                state.add_fix("generate", "task_fallback", "", item.text[:40],
                              note="a task-kind item never parses to nothing")
                out.append(item)
                continue
            except Exception:
                pass
        if not got:
            out.append(item)
            continue
        if len(got) == 1:
            item.action, item.intent = got[0]
            _apply_slots(item)
            out.append(item)
            continue
        for j, (name, intent) in enumerate(got, start=1):
            sub = Item(id=f"{item.id}-{j}", kind=_kind_for(name), text=item.text,
                       slots=dict(item.slots), action=name, intent=intent)
            _apply_slots(sub)
            out.append(sub)
    state.items = out
    return state


#: The literal ask that grounds a default title — the noun IS in the words.
_EVENT_ASK = re.compile(
    r"\b(?:set|make|create|add|schedule|book|put)\b[^.!?]*?\b(event|reminder|appointment)\b"
    r"|\b(event|reminder|appointment)\b[^.!?]*?\b(?:set|make|create|add|schedule|book|put)\b",
    re.I)


def _event_fallback(text: str):
    """The event twin of task_fallback (hypothesis #2, cycle 5).

    Fires only after the event-kind retry also produced nothing: when the
    words LITERALLY ask to set an event/reminder/appointment ("Set a event
    for the evening", "Set reminder for three o'clock") and the date
    recognizer grounds a when in those same words, the honest object is a
    default-titled event — noun and when are both in the transcript, so
    nothing is invented. No literal ask, or no grounded when, returns None
    and the item stays unknown; a time is never guessed.
    """
    m = _EVENT_ASK.search(text)
    if not m:
        return None
    noun = next(g for g in m.groups() if g)
    import datetime as _dt
    from assistant.intent.rule_parser import _extract_temporal
    t = _extract_temporal(text, _dt.date.today())
    if not (t.get("date") or t.get("start_time")):
        return None
    from assistant.actions.calendar.intent import CalendarIntent
    return CalendarIntent(title=noun.capitalize(), date=t.get("date"),
                          start_time=t.get("start_time"),
                          end_time=t.get("end_time"))


def _apply_slots(item: Item) -> None:
    """Structured hints from decomposition land on the intent, when it can
    carry them — a count the words stated beats one the model guessed."""
    rm = item.slots.get("reminder_minutes")
    if rm and item.action == "create_event" and hasattr(item.intent, "reminder_minutes"):
        if getattr(item.intent, "reminder_minutes", None) is None:
            item.intent.reminder_minutes = int(rm)
    q = item.slots.get("quantity")
    if q and item.action == "create_todo" and hasattr(item.intent, "quantity"):
        if getattr(item.intent, "quantity", None) in (None, 0, 1):
            item.intent.quantity = q
