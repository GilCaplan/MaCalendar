"""Step 2 — segment the transcript into independent items.

Contract (see DOCUMENTATION/ENGINE.md):
  reads   state.text
  writes  state.items (fresh list of Item: id, kind, text only),
          trace steps (RULE)

Deterministic delimiters first — they are free and cannot be wrong:

  • bracket batching:   "[gym tomorrow] [lunch with Tal]"   (queued phone commands)
  • intake coalescing:  ("gym tomorrow")and("lunch with Tal")  (step 0's wrapper)
  • the configured event separator (config.audio.event_separator)

Only when none of those split anything may the LLM be consulted, and the bias
is to UNDER-split: a wrongly merged item gets two more chances (step 3 can
decompose it, step 6 notices the missing item), where a wrong split of
"meeting with Tal and Ravid" creates two garbage items immediately.

Kind here is a first reading ("review" for schedule questions, "task" for
to-do phrasing, "event" for the rest); step 5 settles the actual action.
"""

from __future__ import annotations

import re

from assistant.engine.state import EngineState, Item

# ("…")and("…") — the step-0 coalescing wrapper. Parentheses+quotes because a
# bare "and" very much can occur inside one command.
_COALESCE_RE = re.compile(r"\(\s*[\"“]([^\"“”]+)[\"”]\s*\)")
_BRACKET_RE = re.compile(r"\[([^\[\]]+)\]")

# A schedule question, not an instruction to create anything.
_REVIEW_RE = re.compile(
    r"^(?:what(?:'s| is| do| have)?|show me|do i have|when is|when's|how many|"
    r"list|tell me)\b|(?:\bmy (?:schedule|day|week|agenda)\b)", re.I)

# To-do phrasing. Only used as a first reading; step 5 decides the action.
_TASK_RE = re.compile(
    r"^(?:add|put)\s+.*\b(?:to|on)\s+(?:my\s+)?(?:to-?do|task|shopping)|"
    r"^(?:remind me to|i need to|remember to|buy|get|pick up)\b|"
    r"\b(?:to-?do list|task list)\b", re.I)


def _kind_of(text: str) -> str:
    t = text.strip()
    if _REVIEW_RE.search(t):
        return "review"
    if _TASK_RE.search(t):
        return "task"
    return "event"


def _deterministic_segments(text: str, cfg) -> "tuple[list[str], str | None]":
    """Split on delimiters that cannot occur inside a command. Returns
    (segments, how) — how is None when nothing split."""
    hits = _COALESCE_RE.findall(text)
    if len(hits) > 1:
        return [s.strip() for s in hits if s.strip()], "coalesced"
    hits = _BRACKET_RE.findall(text)
    if len(hits) > 1:
        return [s.strip() for s in hits if s.strip()], "batched"
    separator = (cfg.audio.event_separator or "").strip()
    if separator:
        parts = [s.strip() for s in
                 re.split(re.escape(separator), text, flags=re.IGNORECASE)
                 if s.strip()]
        if len(parts) > 1:
            return parts, "separator"
    return [text.strip()], None


def run(state: EngineState, cfg) -> EngineState:
    from assistant.trace import RULE

    segments, how = _deterministic_segments(state.text, cfg)

    # The delimiters must not survive into titles — an event called "[gym]"
    # helps nobody. The working transcript becomes the joined segments.
    if how:
        state.text = " ".join(segments)

    state.items = [
        Item(id=f"item_{i + 1}", kind=_kind_of(seg), text=seg)
        for i, seg in enumerate(segments)
    ]

    if state.trace:
        if how:
            state.trace.step(RULE, "Split into commands",
                             f"{len(segments)} {how}: "
                             + " · ".join(s[:40] for s in segments))
        else:
            state.trace.step(RULE, "Segmented",
                             f"1 item ({state.items[0].kind})")
    return state
