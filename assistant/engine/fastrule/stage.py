"""The FastRule STAGE: X3 (items) -> X4 (objects ready to commit).

Gil, 2026-09-08: "FastRule's job is to take the Items defined and convert them
to calendar/task list objects that can be easily committed."

The stage is "make the objects"; FastRule-first is HOW. `objects.run` tries
`FastRule` per item and falls back to a schema-constrained model call only when
the rules cannot decide — the tiered decision this folder's ARCHITECTURE.md
describes.

It ends by running decompose_validate's OBJECT pass. Those are that stage's
rules, not this one's; they run here only because they need `item.intent` to
exist, which is not true until this stage has run. ENGINE_REWIRE.md carries the
open question of folding them back where they belong.
"""
from __future__ import annotations

from assistant.engine.decompose_validate import stage as _decompose_validate
from assistant.engine.fastrule import objects as _objects


def run(state, cfg):
    """X3 -> X4. Build the objects, then apply the field rules to them."""
    _objects.run(state, cfg)
    _decompose_validate.run_objects(state, cfg)
    return state
