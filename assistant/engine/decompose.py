"""Step 3 — decompose items that are really several things, or one thing × N.

Contract (see DOCUMENTATION/ENGINE.md):
  reads   state.items
  writes  state.items (may replace an item with sub-items id "item_N-M",
          may fill item.slots: quantity, reminder_minutes), trace steps (RULE)

Bounded: one decomposition pass over the step-2 items — an item is split at
most once (ids go one level deep, "item_1-2", never "item_1-2-3").

Deterministic reuse, no LLM here yet:
  • task lists ride assistant/intent/list_split.py — "buy chicken and rice"
    is two tasks, the verb handed down, idioms and prepositions respected;
  • counts ride assistant/intent/quantity.py — "buy 5 apples" is ONE task of
    (apples, 5), never five rows (ticking one of five identical rows tells
    you nothing);
  • an event with two spoken times joined by "and" is two events ("walk the
    dog at 9am and 2:30pm") — recognised only in that narrow shape, because
    "with Tal and Ravid" must never split.
"""

from __future__ import annotations

import re

from assistant.engine.state import EngineState, Item

_TIME = r"\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)?"
# "… at 9am and 2:30pm", "… at 9 and at 14:30", "… at 9 and again at 2:30" —
# a list of times for one activity, adjacent in the sentence. Wordier phrasings
# fall through to the LLM pass below.
_TIME_LIST_RE = re.compile(
    rf"\bat\s+({_TIME})(?:\s*,\s*(?:and\s+)?|\s+and\s+(?:again\s+|then\s+)?)(?:at\s+)?({_TIME})\b",
    re.IGNORECASE)

_DECOMPOSE_SCHEMA = {
    "type": "object",
    "properties": {
        "parts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
    },
    "required": ["parts"],
}

_DECOMPOSE_SYSTEM = """One spoken request books the SAME activity at more than one time \
("walk the dog at 9am and again at 2:30pm" = two walks). Rewrite it as one \
complete request per occurrence, each with exactly one time, copying the \
speaker's own words. If it is really a single occurrence — or you are not \
sure — return it unchanged as one part. Never invent words, times or \
activities. Return JSON: {"parts": [{"text": ...}, ...]}"""


# An actual clock-time mention: "at 9", "2:30", "7pm" — NOT a bare number,
# which is far more often a date ("the 19th").
_TIME_MENTION_RE = re.compile(
    r"\b(?:at|around|about)\s+\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)?"
    r"|\b\d{1,2}:\d{2}\b"
    r"|\b\d{1,2}\s*(?:am|pm|a\.m\.|p\.m\.)\b", re.IGNORECASE)


def _llm_split_times(item: Item, state, cfg) -> "list[Item] | None":
    """The wordier shapes the regex refuses. Self-skipping: only an event item
    whose words carry two or more clock-time mentions is worth a call."""
    from assistant.engine import llm as _llm

    mentions = _TIME_MENTION_RE.findall(item.text)
    if len(mentions) < 2:
        return None
    if " and " not in item.text.lower():
        return None
    # "from 6 to 8" is a RANGE — two mentions, one event. Only more mentions
    # than the range accounts for makes this worth a look.
    if re.search(rf"\bfrom\s+{_TIME}\s*(?:to|until|till)\s+\d", item.text,
                 re.IGNORECASE) and len(mentions) <= 2:
        return None
    system = _DECOMPOSE_SYSTEM
    if state.mistakes:
        system += "\n\nOn a previous attempt at THIS command you made these " \
                  "mistakes — do not repeat them:\n- " + "\n- ".join(state.mistakes)
    try:
        out, ms = _llm.call_json(cfg, system, f"The request: {item.text}", _DECOMPOSE_SCHEMA)
        state.llm_ms += ms
    except Exception:
        return None
    parts = [str(d.get("text", "")).strip() for d in (out.get("parts") or [])
             if isinstance(d, dict) and str(d.get("text", "")).strip()]
    if len(parts) < 2 or any(len(p.split()) < 2 for p in parts):
        return None
    return [Item(id=f"{item.id}-{j}", kind=item.kind, text=p, slots=dict(item.slots))
            for j, p in enumerate(parts, start=1)]


def _split_times(item: Item) -> "list[Item] | None":
    m = _TIME_LIST_RE.search(item.text)
    if not m:
        return None
    t1, t2 = m.group(1).strip(), m.group(2).strip()
    subs = []
    for j, t in enumerate((t1, t2), start=1):
        text = item.text[:m.start()] + f"at {t}" + item.text[m.end():]
        subs.append(Item(id=f"{item.id}-{j}", kind=item.kind, text=text.strip(),
                         slots=dict(item.slots)))
    return subs


def _split_tasks(item: Item) -> "list[Item] | None":
    """The list splitter, with the same discipline segment's clause tier has:
    every piece must be an ASK.

    `list_split` is pure string work, so it cuts at commas and "and" without
    being able to tell a request from the words around one. That was invisible
    while most to-dos were mis-kinded as events and never reached here; fixing
    the kind decision routed them all in at once and the tears surfaced —
    "wash the car, done and dusted" became "wash done" + "wash dusted",
    "pack and label the boxes" left a task called "pack", and a tag question
    ("does that seem right") became an item of its own.

    The whole split is refused rather than the bad piece dropped: those words
    are still part of the command, and a merged item is recoverable where
    deleted words are not.
    """
    from assistant.intent.asks import every_part_is_an_ask
    from assistant.intent.list_split import ACTION_VERBS, split_items

    parts = [p.strip() for p in split_items(item.text) if p.strip()]
    if len(parts) <= 1:
        return None
    if not every_part_is_an_ask(parts, ACTION_VERBS):
        return None
    return [Item(id=f"{item.id}-{j}", kind="task", text=p,
                 slots=dict(item.slots))
            for j, p in enumerate(parts, start=1)]


def _extract_quantity(item: Item) -> None:
    from assistant.intent.quantity import split_quantity
    clean, count = split_quantity(item.text)
    if count > 1:
        item.slots["quantity"] = count
        item.text = clean


def _strip_reminder_clause(item) -> None:
    """Pull a spoken lead time out of the item text into slots (cycle 8).

    The clause pattern and the minute arithmetic live in
    assistant/intent/lead_time.py — FastRule needs the same reader, and one
    copy cannot drift from the other."""
    from assistant.intent import lead_time

    rest, minutes = lead_time.split(item.text)
    if minutes is None:
        return
    item.slots["reminder_minutes"] = minutes
    item.text = rest


def run(state: EngineState, cfg) -> EngineState:
    from assistant.trace import RULE

    out: list = []
    split_notes: list[str] = []
    for item in state.items:
        if item.kind == "event":
            _strip_reminder_clause(item)
        subs = None
        if item.kind == "event":
            subs = _split_times(item) or _llm_split_times(item, state, cfg)
            if subs:
                split_notes.append(f"{item.id}: {len(subs)} times → {len(subs)} events")
        elif item.kind == "task":
            subs = _split_tasks(item)
            if subs:
                split_notes.append(f"{item.id}: {len(subs)} tasks")
        for it in (subs or [item]):
            if it.kind == "task":
                _extract_quantity(it)
                if it.slots.get("quantity"):
                    split_notes.append(f"{it.id}: ×{it.slots['quantity']}")
            out.append(it)
    state.items = out

    if state.trace and split_notes:
        state.trace.step(RULE, "Decomposed", "; ".join(split_notes))
    return state
