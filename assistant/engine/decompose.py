"""Step 3 — decompose items that are really several things, or one thing × N.

Contract (see DOCUMENTATION/ENGINE.md):
  reads   state.items
  writes  state.items (may replace an item with sub-items id "item_N-M",
          may fill item.slots: quantity), trace steps (RULE)

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
# "… at 9am and 2:30pm", "… at 9 and at 14:30" — a list of times for one
# activity. The times must be adjacent in the sentence; anything wordier is
# left for the LLM decomposition pass (a later, gated build).
_TIME_LIST_RE = re.compile(
    rf"\bat\s+({_TIME})(?:\s*,\s*(?:and\s+)?|\s+and\s+)(?:at\s+)?({_TIME})\b",
    re.IGNORECASE)


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
    from assistant.intent.list_split import split_items
    parts = split_items(item.text)
    if len(parts) <= 1:
        return None
    return [Item(id=f"{item.id}-{j}", kind="task", text=p.strip(),
                 slots=dict(item.slots))
            for j, p in enumerate(parts, start=1)]


def _extract_quantity(item: Item) -> None:
    from assistant.intent.quantity import split_quantity
    clean, count = split_quantity(item.text)
    if count > 1:
        item.slots["quantity"] = count
        item.text = clean


def run(state: EngineState, cfg) -> EngineState:
    from assistant.trace import RULE

    out: list = []
    split_notes: list[str] = []
    for item in state.items:
        subs = None
        if item.kind == "event":
            subs = _split_times(item)
            if subs:
                split_notes.append(f"{item.id}: two times → two events")
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
