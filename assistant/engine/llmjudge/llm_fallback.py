"""The model half of reading an item — and the three guards that make it safe.

PORTED FROM `fastrule/objects.py`, 2026-09-09 (Gil): *"before we start breaking
FastRule code, port what's relevant to the LLMJudge folder."* Step 0 of
`PLAN.md` §1.0. A MOVE with an import redirect, verbatim, **no behaviour
change** — FastRule still calls these at the same branch point.

WHY THE PORT CAME FIRST, and is not merely tidiness. Trim FastRule first and
these ~150 lines exist only in git history when the port happens, at which
point "port" quietly becomes "rewrite from memory". `_guard_inventions` is the
one that would be lost first, and it exists because a model once fabricated an
event onto the calendar (cycle 7) — nothing about its new home makes that risk
smaller.

WHAT IS **NOT** HERE, deliberately. `_parse_item` stays in `objects.py`: it is
the per-item BRANCH POINT (rules-vs-model), not a liftable unit, and splitting
it would be a behaviour change wearing a port's clothes. Phase B replaces it
with a `DEFER(INCAPACITY)` consumer; that is the shape §1.2 describes, and it
is not this step's business.

THE THREE GUARDS, none of which may be dropped on the way:

    _guard_inventions   a model-fabricated event never reaches the calendar.
                        Rule-parser output deliberately never routes through
                        it — rules are grounded by construction.
    _grounded_title     every content word of an LLM title must have been
                        spoken.
    _honour_refusal     a REFUSAL may be RESOLVED by the model, never
                        overturned. The one rule this codebase has already
                        broken once.
"""
from __future__ import annotations

import re

from assistant.engine.state import EngineState, Item


def _llm_trace(state: EngineState, parser, cfg, title: str) -> None:
    from assistant.trace import LLM
    state.llm_ms += parser.last_llm_ms
    if state.trace:
        state.trace.step(LLM, title,
                         f"{cfg.llm_engine}:{getattr(cfg, cfg.llm_engine).model} · "
                         f"{parser.last_examples_used} history example(s) used",
                         raw=(parser.last_raw_response or "")[:1500] or None,
                         examples=parser.last_examples_used)


def _honour_refusal(got, res, item: Item, state: EngineState):
    """FastRule REFUSED this reading — the LLM may resolve the objection, but
    a bare re-read must not overturn it.

    The distinction that matters: for a generic-target veto ("delete this
    event" names nothing), the LLM legitimately fixes it by RESOLVING the
    reference to a real title — anaphora memory is exactly that job. What it
    must not do is hand back the same empty target and have it executed,
    which is what happened before the audit found this path. Empty slots
    surfacing as "I couldn't find…" is the right answer; guessing is not.
    """
    from assistant.trace import RULE

    if not got:
        return got
    if not (res.reason or "").startswith("generic-target"):
        return got          # the other refusals stand as parsed
    from assistant.engine.llmjudge.gatekeeper import _GENERIC_TARGET_RE
    # `_friendly` stays in `fastrule.objects` — it has eight other callers
    # there. Imported lazily, like the trace constant above, so neither module
    # resolves the other at import time and no cycle is possible. When phase B
    # dismantles `objects.py` this import fails loudly, which is the point:
    # a tripwire beats a silent loss.
    from assistant.engine.fastrule.objects import _friendly
    kept = []
    for name, intent in got:
        if name.startswith(("update_", "delete_", "complete_")):
            target = str(getattr(intent, "match_title", "") or "").strip()
            if not target or _GENERIC_TARGET_RE.match(target):
                # unresolved: the model gave back the same bare noun
                state.messages.append(
                    "I wasn't sure which one you meant, so I left it alone.")
                if state.trace:
                    state.trace.step(RULE, f"Held back {_friendly(item.id)}",
                                     f"“{target or 'no target'}” names nothing "
                                     "specific — refusing rather than guessing",
                                     ok=False)
                continue
        kept.append((name, intent))
    return kept


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
