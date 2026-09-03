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


# Words that can (but very often do not) join two independent requests. Their
# absence is a free proof the input is one item — the LLM is never consulted.
_COMPOUND_HINT = re.compile(r"\b(and|then|also|plus|after that)\b|,|;", re.I)

_SEGMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["event", "task", "review"]},
                    "text": {"type": "string"},
                },
                "required": ["kind", "text"],
            },
        },
    },
    "required": ["items"],
}

_SEGMENT_SYSTEM = """You split ONE voice command to a calendar assistant into its independent requests, if it contains more than one.

Rules, in order of importance:
1. When in doubt, DO NOT SPLIT. Return the whole command as one item. A wrong
   merge is recoverable; a wrong split is not.
2. Never split people joined by "and": "meeting with Tal and Ravid" is ONE
   event with two guests.
3. Never split a thing and its description: "fish and chips" is one dish,
   "buy a gift for mom and dad" is one errand.
4. Split only when two independent requests are joined: "book gym at 7 and
   remind me to buy milk" is two.
5. Copy the speaker's own words into each item's text — never rephrase,
   summarise or invent words.
6. kind: "event" books or changes something on the calendar, "task" is a
   to-do, "review" asks what is scheduled.

Return JSON: {"items": [{"kind": ..., "text": ...}, ...]}"""


def _llm_segments(state: EngineState, cfg) -> "list[Item] | None":
    """One schema-constrained call, only when the words even suggest compounding
    — and biased to under-split (see module docstring). None = keep one item."""
    from assistant.engine import llm as _llm

    text = state.text
    if len(text.split()) < 6 or not _COMPOUND_HINT.search(text):
        return None
    system = _SEGMENT_SYSTEM
    if state.mistakes:
        # A loop-back from step 6 carries what went wrong last time — the
        # retried attempt must not repeat it.
        system += "\n\nOn a previous attempt at THIS command you made these " \
                  "mistakes — do not repeat them:\n- " + "\n- ".join(state.mistakes)
    try:
        out, ms = _llm.call_json(cfg, system, f"The command: {text}", _SEGMENT_SCHEMA)
        state.llm_ms += ms
    except Exception:
        # Segmentation must never lose the command: one item is always a
        # legitimate reading, and if the model is truly offline step 5 will
        # say so through the pending queue.
        return None
    raw_items = out.get("items") or []
    parts = [(str(d.get("kind", "")).strip(), str(d.get("text", "")).strip())
             for d in raw_items if isinstance(d, dict)]
    parts = [(k if k in ("event", "task", "review") else _kind_of(t), t)
             for k, t in parts if t]
    if len(parts) <= 1:
        return None
    # Under-split bias, enforced: a "split" that produced a fragment (a lone
    # word with no verb or time) is the model imagining structure — refuse it.
    if any(len(t.split()) < 2 for _, t in parts):
        return None
    return [Item(id=f"item_{i + 1}", kind=k, text=t)
            for i, (k, t) in enumerate(parts)]


def run(state: EngineState, cfg) -> EngineState:
    from assistant.trace import LLM, RULE

    segments, how = _deterministic_segments(state.text, cfg)

    # The delimiters must not survive into titles — an event called "[gym]"
    # helps nobody. The working transcript becomes the joined segments.
    if how:
        state.text = " ".join(segments)

    state.items = [
        Item(id=f"item_{i + 1}", kind=_kind_of(seg), text=seg)
        for i, seg in enumerate(segments)
    ]

    if how:
        if state.trace:
            state.trace.step(RULE, "Split into commands",
                             f"{len(segments)} {how}: "
                             + " · ".join(s[:40] for s in segments))
        return state

    llm_items = _llm_segments(state, cfg)
    if llm_items:
        state.items = llm_items
        if state.trace:
            state.trace.step(LLM, "Split into commands",
                             f"{len(llm_items)} items: "
                             + " · ".join(it.text[:40] for it in llm_items))
        return state

    if state.trace:
        state.trace.step(RULE, "Segmented", f"1 item ({state.items[0].kind})")
    return state
