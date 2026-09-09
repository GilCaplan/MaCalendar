"""Segmentation — the engine's step 2, and the switch between its two engines.

    text  ->  [Item(kind=tag, text=action, time=time), ...]

Two implementations live here and either can be the one that runs:

    IMPLEMENTATION = "fastseg"   FastSeg, deterministic, no model    <- DEFAULT
    IMPLEMENTATION = "old_seg"   the previous stage, LLM-assisted

Switch with `MACALENDAR_SEGMENTATION=old_seg`, or `engine.segmentation` in
config.yaml. ARCHITECTURE.md section 3 carries the flag table and the measured
trade between them; read it before changing the default.

THE SHAPE IT RETURNS
--------------------
`Item` now carries `time` separately (added 2026-09-08 — a deliberate contract
change), so an item is `(kind=tag, text=action, time=time)` and the time is no
longer buried in the text.

Anything that PARSES an item for a date calls `Item.spoken()`, which is the
action with its time reattached. That matters: `FastRule` and the LLM parser both
extract the time from the string they are handed, so passing `text` alone
produced events with no time. `generate` and `decompose` were migrated to
`spoken()` in the same change.

HOW A COMMAND GETS THROUGH
--------------------------
    1  envelope   transport delimiters (coalesced / batched / separator) — the
                  ingest queue wraps batches as ("a")and("b"), which is not
                  English and which FastSeg's cutter would return as ONE piece
    2  FastSeg    deterministic cut + tag, ~10ms, no model
    3  LLMSeg     the model half — OFF by default, so tier 2's answer stands
    4  ACCEPT     the invariant guard; a model answer that loses or invents a
                  word is reverted to FastSeg's

Tiers 2-4 are one call into `llmseg.segment`, which owns the flag, so there is
no second code path to keep in step.
"""
from __future__ import annotations

import os

from assistant.engine.segmentation import old_seg          # noqa: F401
from assistant.engine.state import Item

#: Which implementation runs. FastSeg by default (Gil, 2026-09-08).
#: `old_seg` remains fully wired and one env var away — see ARCHITECTURE.md §3
#: for the measured differences, including where FastSeg is WORSE.
IMPLEMENTATION = os.environ.get("MACALENDAR_SEGMENTATION", "fastseg").strip().lower()


def _envelope_split(text: str, cfg):
    """Transport delimiters, before any language is looked at.

    The ingest queue coalesces several commands into `("a")and("b")`, the phone
    sends bracket batches, and a user can configure a spoken separator. None of
    those are English, and FastSeg's cutter has never seen them — it returns the
    whole wrapper as ONE piece, which would collapse a batch of queued commands
    into a single item. So the envelope is opened first, with `old_seg`'s own
    reader, and FastSeg runs per envelope.
    """
    from assistant.engine.segmentation.old_seg.segment import (
        _BRACKET_RE, _COALESCE_RE)

    hits = _COALESCE_RE.findall(text)
    if len(hits) > 1:
        return [s.strip() for s in hits if s.strip()], "coalesced"
    hits = _BRACKET_RE.findall(text)
    if len(hits) > 1:
        return [s.strip() for s in hits if s.strip()], "batched"
    separator = (getattr(getattr(cfg, "audio", None), "event_separator", "") or "").strip()
    if separator:
        import re
        parts = [s.strip() for s in
                 re.split(re.escape(separator), text, flags=re.IGNORECASE)
                 if s.strip()]
        if len(parts) > 1:
            return parts, "separator"
    return [text.strip()], None


def _segment_items(text: str):
    """One envelope -> [(action, time, tag)] — the component, both halves.

    `llmseg.segment` IS the component: it runs FastSeg, then LLMSeg, then the
    deterministic ACCEPT guard, and it honours `llmseg.ENABLED` itself. With the
    flag off it returns FastSeg's answer and makes no model call, so this one
    call is the whole chain either way and there is no second code path to keep
    in step.
    """
    from assistant.engine.segmentation.llmseg.llmseg import segment

    out = segment(text)
    return [(i["action"], i["time"], i["tag"]) for i in out["items"]]


def run(state, cfg):
    """Step 2. Envelope split, then the component, then Items."""
    if IMPLEMENTATION == "old_seg":
        return old_seg.segment.run(state, cfg)

    from assistant.engine.segmentation.old_seg.segment import (
        _enforce_pinned_kinds, _kind_of)
    from assistant.trace import RULE

    envelopes, how = _envelope_split(state.text, cfg)
    # A transport delimiter must not survive into a title, so the working
    # transcript becomes the joined envelopes. Nothing to strip when none fired.
    if how:
        state.text = " ".join(envelopes)

    items: "list[Item]" = []
    for envelope in envelopes:
        for action, when, tag in _segment_items(envelope):
            # `other` is one of ITEM_KINDS and is passed THROUGH. It used to fall
            # to the else branch and be re-read as an event, which threw away the
            # one verdict that says "this is not a calendar ask at all" — so the
            # tag existed in the contract and nothing could ever produce it.
            kind = tag if tag in ("event", "task", "review", "other") else \
                _enforce_pinned_kinds(_kind_of(action), action)
            items.append(Item(id=f"item_{len(items) + 1}", kind=kind,
                              text=action, time=when))

    if not items:                      # never hand on an empty decomposition
        items = [Item(id="item_1", text=state.text,
                      kind=_enforce_pinned_kinds(_kind_of(state.text), state.text))]
    state.items = items

    if state.trace:
        state.trace.step(RULE, "Split into commands",
                         f"{len(items)} item(s)" + (f" ({how})" if how else "")
                         + ": " + " · ".join(it.spoken()[:40] for it in items))
    return state
