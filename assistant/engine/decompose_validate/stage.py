"""The decompose_validate STAGE: X2 (items) -> X3 (complete, checked, flagged).

One box in the chain, two functions kept separate inside it (Gil): **decompose
RESOLVES** — each item's spoken time becomes concrete values — and **validate
CHECKS** those values back against the words, repairing what it can prove and
flagging what it cannot. Neither one splits; that is segmentation's job.

    run(state, cfg)          the text pass — what the chain calls
    run_objects(state, cfg)  the OBJECT pass (legacy, see below)

## What is wired, and what is not yet

`resolve.py` + `checks.py` are the implementation this stage was rebuilt around,
measured on its own dataset (`datasets/`, `eval_metrics/`, ARCHITECTURE.md).
`run()` calls them and writes the result into `item.slots`, which is the field
already designated for structured values — so X3 carries resolved values without
reshaping `EngineState`, whose contracts are frozen.

**The legacy pair still runs, and still feeds FastRule.** `decompose.py` does
item splitting and text repair that the new pair deliberately does not do, and
`run_objects` — invoked from the tail of the FastRule stage, because its rules
need `item.intent` to exist — is still where the OLD date resolution lives.
Making FastRule read `slots` instead of re-parsing the string, and then deleting
`run_objects`, is the remaining swap. Until it happens, the values below are
carried and traced but are not what the calendar rows are built from.
"""
from __future__ import annotations

import datetime as dt

from assistant.engine.decompose_validate import checks as _checks
from assistant.engine.decompose_validate import decompose as _decompose
from assistant.engine.decompose_validate import resolve as _resolve
from assistant.engine.decompose_validate import validate as _validate

#: The value fields this stage fills, written into `item.slots`.
VALUE_FIELDS = ("date", "start_time", "end_time", "recurrence", "recur_days",
                "recur_until", "quantity", "reminder_minutes")


def _as_dict(item) -> dict:
    """An Item -> the plain shape `resolve`/`checks` work in.

    They take dicts on purpose: both are pure and unit-testable without building
    an EngineState, and neither can reach into a field it has no business in.
    """
    out = {"kind": getattr(item, "kind", ""),
           "text": getattr(item, "text", "") or "",
           "time": getattr(item, "time", None)}
    for f in VALUE_FIELDS:
        out[f] = (item.slots or {}).get(f)
    return out


def resolve_values(state, anchor: "dt.date | None" = None):
    """Fill each item's values, then check them against the words.

    Returns (fixes, flags) for the trace. Values land in `item.slots`; flags land
    in `slots["flags"]` and NEVER in `item.blocked` — a flag notifies, it does not
    refuse (Gil, 2026-09-08).
    """
    anchor = anchor or dt.date.today()
    items = list(getattr(state, "items", []) or [])
    if not items:
        return [], []

    said = getattr(state, "text", "") or getattr(state, "raw_text", "") or ""
    dicts = []
    for item in items:
        d = _as_dict(item)
        # The item's OWN words as context, never the transcript: a neighbour's
        # "4pm" must not decide this item's bare hour.
        own = f"{d['time'] or ''} {d['text']}".strip()
        v = _resolve.resolve(d["time"] or "", anchor, own, action=d["text"])
        d.update({k: v.get(k) for k in
                  ("date", "start_time", "end_time", "recurrence",
                   "recur_days", "recur_until")})
        d["quantity"] = _resolve.resolve_quantity(d["text"])
        d["reminder_minutes"] = (_resolve.resolve_lead_time(d["time"] or "")
                                 or _resolve.resolve_lead_time(d["text"]))
        dicts.append(d)

    checked, fixes, flags = _checks.run(dicts, said, anchor)

    by_rule = {}
    for flag in flags:
        by_rule.setdefault(flag.rule, []).append(flag.why)
    for item, d in zip(items, checked):
        if item.slots is None:
            item.slots = {}
        for f in VALUE_FIELDS:
            if d.get(f) is not None:
                item.slots[f] = d[f]
    if flags:
        # Attached to the FIRST item rather than duplicated across all of them:
        # a flag is about a value, and the reply mentions it once.
        items[0].slots.setdefault("flags", []).extend(
            f"{flag.rule}: {flag.why}" for flag in flags)
    return fixes, flags


def run(state, cfg):
    """X2 -> X3. Legacy split/repair, then resolve values and check them."""
    _decompose.run(state, cfg)
    _validate.run(state, cfg)
    try:
        resolve_values(state)
    except Exception as exc:
        # A value pass must never take the command down — the legacy path still
        # produces the rows, so a failure here costs the slots and nothing else.
        # But it is RECORDED, not swallowed: a silent except is how a broken
        # resolver looks exactly like a resolver with nothing to say.
        if state.items:
            if state.items[0].slots is None:
                state.items[0].slots = {}
            state.items[0].slots.setdefault("flags", []).append(
                f"resolve_values failed: {type(exc).__name__}: {exc}")
    return state


def run_objects(state, cfg):
    """The object pass — this stage's rules, run after objects exist."""
    return _validate.run_objects(state, cfg)
