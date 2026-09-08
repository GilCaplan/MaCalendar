"""The decompose_validate STAGE: X2 (items) -> X3 (atomic, repaired, legal).

One box in the chain, two functions kept separate inside it (Gil): `decompose`
splits until items are atomic, `validate` repairs them and applies the
observance gate.

    run(state, cfg)          the text pass — what the chain calls
    run_objects(state, cfg)  the OBJECT pass

`run_objects` needs `item.intent` to exist, so it cannot run here in the chain
order — it is invoked at the tail of the FastRule stage, and it is re-exported
from this module so it is obvious whose rules they are. It is where date
RESOLUTION lives (`relative_dates`, `_rule_past_date_bump`) and where the
observance gate sits. Folding it properly into this stage is the open design
question in DOCUMENTATION/ENGINE_REWIRE.md.
"""
from __future__ import annotations

from assistant.engine.decompose_validate import decompose as _decompose
from assistant.engine.decompose_validate import validate as _validate


def run(state, cfg):
    """X2 -> X3. Decompose to atomic items, then repair them."""
    _decompose.run(state, cfg)
    _validate.run(state, cfg)
    return state


def run_objects(state, cfg):
    """The object pass — this stage's rules, run after objects exist."""
    return _validate.run_objects(state, cfg)
