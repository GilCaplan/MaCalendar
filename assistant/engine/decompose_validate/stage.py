"""The decompose_validate STAGE: X2 (items) -> X3 (complete, checked, flagged).

One box in the chain. **decompose RESOLVES** — each item's spoken time becomes
concrete values — and **validate CHECKS** those values back against the words,
repairing what it can prove and flagging what it cannot. Neither splits; that is
segmentation's job.

    run(state, cfg)          the text pass — what the chain calls
    run_objects(state, cfg)  the object pass, from the tail of FastRule, because
                             its rules need `item.intent` to exist

## The implementation, and what happened to v1

`resolve.py` + `checks.py` are the implementation, measured on this stage's own
dataset (`datasets/`, `eval_metrics/`, ARCHITECTURE.md). They are AUTHORITATIVE:
`run_objects` writes their values onto the built intents, so the calendar rows
come from them.

`validate.py` — the ported v1 module — is **retired** (Gil, 2026-09-08). Its nine
transcript-wide date rules are deleted: they built a flat list of dates and matched
them to events BY ORDER (`ev_idx`, `n_events`, `orig_event_dates`), which is the
bug class behind `a987aba` — the list is legitimately shorter than the events, so
the wrong event got the wrong date. Nothing is pinned now; each item's own words
are resolved and "which event does this date belong to" is never asked.

What survived was never value resolution, and lives where it belongs:

    targeting.py         edits and deletes — which record the speaker meant
    object_rules.py      boundaries, title repair, reply wording, past-date roll
    observance_gate.py   the Shabbat / yom tov gate, now a FLAG not a refusal
    text_helpers.py      read-only readings of the transcript, shared engine-wide

The original is kept in `retired/decompose-validate-v1/`.
"""
from __future__ import annotations

import datetime as dt
import datetime as _dt

from assistant.engine.decompose_validate import checks as _checks
from assistant.engine.decompose_validate import decompose as _decompose
from assistant.engine.decompose_validate import object_rules as _obj
from assistant.engine.decompose_validate import observance_gate as _gate
from assistant.engine.decompose_validate import resolve as _resolve
from assistant.engine.decompose_validate import targeting as _target
from assistant.engine.decompose_validate import text_repair as _tidy
from assistant.engine.state import EngineState

import re

#: The value fields this stage fills, written into `item.slots`.
VALUE_FIELDS = ("date", "start_time", "end_time", "recurrence", "recur_days",
                "recur_until", "quantity", "reminder_minutes")


def _resolve_onto_intent(state: EngineState, item, intent, today,
                         carried_day: "str | None" = None) -> "str | None":
    """The per-item resolver + validate's checks, written onto a built intent.

    THIS REPLACES THE INDEX-PINNING RULES. `_rule_relative_date_pin` and
    `_rule_due_date_pin` read the WHOLE transcript, produced a flat list of dates
    and matched them to events BY ORDER (`ev_idx`, `n_events`,
    `orig_event_dates`). That is the bug class behind `a987aba`: when the list is
    shorter than the events -- which it legitimately is, because the bare-ordinal
    branch refuses to claim a month-named ordinal -- the wrong event gets the
    wrong date, or keeps a stale one.

    Here nothing is pinned. Each item's OWN words are resolved, so the question
    "which event does this date belong to" is never asked. Segmentation already
    answered it.

    The values come from `resolve.py` and are then checked by `checks.py` -- the
    same two modules the stage's boards score, rather than a third policy that
    could drift from them.
    """

    said = (getattr(item, "time", None) or "").strip()
    spoken = item.spoken() if hasattr(item, "spoken") else (item.text or "")
    is_todo = item.action == "create_todo"

    # WITH ONE ITEM, THE TRANSCRIPT *IS* THAT ITEM'S OWN WORDS. An item can reach
    # here carrying no words of its own — `fast_propose` builds items straight
    # from intents — and then the sentence is the only evidence there is. This is
    # not the pinning bug returning: pinning was about deciding WHICH of several
    # events a date belonged to, and with a single item that question cannot
    # arise. With two or more, there is deliberately no fallback.
    only_item = sum(1 for i in state.items if i.intent is not None) == 1
    if not (said or spoken).strip() and only_item:
        said = state.text or ""
        spoken = said

    # STRIP THE INJECTED FLOOR, once, here. FastSeg materialises the date floor as
    # the literal word "today" in `item.time` (fastseg.py's floor block) so its
    # output format matches LLMSeg's prompt -- and LLMSeg is off by default. The
    # cost lands here: a floored day becomes indistinguishable from a spoken one,
    # so a carried day cannot tell it has permission to fill the gap.
    #
    # `Item.spoken()` already works around the same injection, which is the
    # argument for containing it at ONE boundary rather than teaching every reader
    # to ignore it. The transcript is the discriminator: if the sentence never says
    # "today", no speaker did. The real fix belongs in segmentation, whose contract
    # is CAPTURE, DO NOT RESOLVE -- recorded in its ARCHITECTURE.md §8.
    words = said or spoken
    if re.search(r"\btoday\b", words, re.I) and not re.search(
            r"\btoday\b", state.text or "", re.I):
        words = re.sub(r"\s+", " ", re.sub(r"\btoday\b", " ", words, flags=re.I)).strip()

    d = {"kind": "task" if is_todo else "event",
         "text": item.text or "",
         # With no separated time (an older segmenter, or a FastRule-built item)
         # the item's spoken words are all there is -- still ITS OWN words.
         "time": words,
         "date": getattr(intent, "due_date" if is_todo else "date", None),
         "start_time": getattr(intent, "start_time", None),
         "end_time": getattr(intent, "end_time", None),
         "recurrence": getattr(intent, "recurrence", None),
         "recur_days": list(getattr(intent, "recur_days", []) or []),
         "recur_until": getattr(intent, "recur_until", None),
         "quantity": None,
         "reminder_minutes": getattr(intent, "reminder_minutes", None)}

    # A LEADING DAY CARRIES FORWARD. "set a meeting tomorrow at 1 pm, another one
    # at 4 pm" says the day ONCE; the second item's own words name none, and the
    # floor would put it today. So an item with no day of its own inherits the day
    # of the item before it.
    #
    # This is NOT the index-pinning bug returning, and the difference is the whole
    # point: pinning matched the Nth date to the Nth event, which is a GUESS that
    # breaks as soon as the counts differ. Carrying a day forward is a SCOPE rule
    # -- segmentation's documented LEADING behaviour -- and it only ever fills a
    # gap, never overrides a day the item actually named.

    # AN INJECTED "today" IS NOT A SPOKEN DAY. Segmentation materialises the date
    # floor as a literal word, so item 2 of "a meeting tomorrow at 1 pm, another
    # one at 4 pm" arrives with time="today at 4 pm" and LOOKS like it named its
    # own day — which stopped the carry and booked it today. The transcript is the
    # discriminator: if it never says "today", no speaker did.
    spoke_a_day = not _resolve.resolve(
        d["time"], today, f"{d['time']} {d['text']}", action=d["text"]
    )["date_floored"]
    if not spoke_a_day and carried_day:
        d["date"] = carried_day

    out, fixes, flags = _checks.run([d], state.text, today)
    got = out[0]

    for field in ("date", "start_time", "end_time", "recurrence", "recur_days",
                  "recur_until", "reminder_minutes"):
        if is_todo and field != "date":
            continue                       # a todo carries only a due date
        target = "due_date" if (is_todo and field == "date") else field
        if not hasattr(intent, target):
            continue
        was, now = getattr(intent, target, None), got.get(field)
        if now is None or str(was) == str(now):
            continue
        try:
            setattr(intent, target, now)
        except Exception:
            continue                       # a validator refused it; leave it be
        state.add_fix("validate", "resolve_from_own_words", str(was), str(now),
                      note=f"{item.text!r}: {said or spoken!r}")

    for flag in flags:
        # A FLAG NEVER BLOCKS (Gil, 2026-09-08): it is recorded so the reply can
        # mention it, and the item still commits.
        state.add_fix("validate", f"flag:{flag.rule}", "", "", note=flag.why)

    # Only a day the item SAID becomes the carried one. Passing an inherited day
    # on would be fine, but passing a FLOORED one would make "today" spread
    # across a command that never mentioned it.
    return got.get("date") if spoke_a_day else carried_day


def run_objects(state: EngineState, cfg) -> EngineState:
    """The object pass: this stage's values onto the intents, then the rules that
    need an intent to exist."""
    from assistant.trace import VALIDATE

    transcript = state.text
    tl = transcript.lower()
    today = _dt.date.today()
    fixes_before = len(state.fixes)

    rel = _target.relative_dates(transcript)

    pairs = [(it, it.action, it.intent) for it in state.items if it.intent is not None]
    # `n_events` is all that survives of v1's counters — `_rule_junk_event_drop`
    # needs to know how many events there are. `n_todos`, `orig_event_dates`,
    # `ev_idx` and `td_idx` went with the rules that indexed dates onto events by
    # ORDER, which is exactly what must never happen again.
    n_events = sum(1 for _, a, _i in pairs if a == "create_event")
    carried_day = None

    for item, action, intent in pairs:
        if action in ("update_event", "delete_event"):
            _target._rule_anaphor_guard(state, intent, tl, rel, action)
            if action == "update_event":
                _target._rule_move_time_fill(state, intent, transcript)
            continue
        if action == "create_event":
            _target._rule_create_from_remove_guard(state, item, intent)
            if item.action != "create_event" or item.intent is None:
                continue
            carried_day = _resolve_onto_intent(state, item, intent, today,
                                               carried_day)
            _obj._rule_past_date_bump(state, intent, today)
            _obj._rule_now_means_now(state, intent, transcript)
            _obj._rule_morning_title_guard(state, intent, transcript)
            _obj._rule_junk_event_drop(state, item, intent, n_events, pairs)
            if item.intent is None:
                continue
            # A FLAG, NOT A BLOCK (Gil, 2026-09-08). The verdict's logic is
            # unchanged; only what happens to it is. A blocked item is a command
            # that silently did nothing, and the speaker is better served by the
            # event existing with a note they can act on.
            reason = _gate._observance_verdict(intent, cfg)
            if reason:
                state.add_fix("validate", "flag:observance",
                              getattr(intent, "title", ""), "", note=reason)
                item.slots.setdefault("flags", []).append(f"observance: {reason}")
        elif action == "create_todo":
            _target._rule_create_from_remove_guard(state, item, intent)
            if item.intent is None:
                continue
            carried_day = _resolve_onto_intent(state, item, intent, today,
                                               carried_day)

    _obj._rule_question_creates_nothing(state, cfg, pairs)
    _obj._rule_cadence_round_and_announce(state, tl)

    applied = state.fixes[fixes_before:]
    if state.trace and applied:
        state.trace.step(VALIDATE, "Sanity fixes",
                         "; ".join(f.human() for f in applied),
                         rules=[f.rule for f in applied])
    return state


def _as_dict(item) -> dict:
    """An Item -> the plain shape `resolve`/`checks` work in."""
    out = {"kind": getattr(item, "kind", ""),
           "text": getattr(item, "text", "") or "",
           "time": getattr(item, "time", None)}
    for f in VALUE_FIELDS:
        out[f] = (item.slots or {}).get(f)
    return out


def resolve_values(state, anchor: "dt.date | None" = None):
    """The TEXT pass's value fill: values into `item.slots`, before objects exist.

    Returns (fixes, flags). Flags land in `slots["flags"]` and never in
    `item.blocked` — a flag notifies, it does not refuse.
    """
    anchor = anchor or dt.date.today()
    items = list(getattr(state, "items", []) or [])
    if not items:
        return [], []

    said = getattr(state, "text", "") or getattr(state, "raw_text", "") or ""
    dicts = []
    for item in items:
        d = _as_dict(item)
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
    for item, d in zip(items, checked):
        if item.slots is None:
            item.slots = {}
        for f in VALUE_FIELDS:
            if d.get(f) is not None:
                item.slots[f] = d[f]
    if flags:
        items[0].slots.setdefault("flags", []).extend(
            f"{flag.rule}: {flag.why}" for flag in flags)
    return fixes, flags


def run(state, cfg):
    """X2 -> X3. Split, tidy the words, then resolve values and check them."""
    _decompose.run(state, cfg)
    _tidy.tidy(state, cfg)
    try:
        resolve_values(state)
    except Exception as exc:
        # Never take the command down over a value pass — but RECORD it. A silent
        # except is how a broken resolver looks exactly like one with nothing to
        # say.
        if state.items:
            if state.items[0].slots is None:
                state.items[0].slots = {}
            state.items[0].slots.setdefault("flags", []).append(
                f"resolve_values failed: {type(exc).__name__}: {exc}")
    return state
