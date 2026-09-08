"""The shared shape of every brain worker (Q7, Gil-approved 2026-09-06).

`Component` is the one interface: a worker exposes `run()` and nothing else
is assumed about it. `FastRule` (fastrule.py) already has this shape;
`Engine` (engine/__init__.py) adopts it; `Stage` gives it to
the seven stage modules without touching them — each module keeps its frozen
`run(state, cfg) -> state` contract (test_engine_contracts.py pins them) and
the Stage object is a named handle around exactly that function.

Behavior rule for this layer: it ADDS structure, it never adds logic. A
Stage.run is the module function, verbatim; if a stage needs fixing, fix the
module, not the wrapper.
"""

from __future__ import annotations

from typing import Any


class Component:
    """Anything the brain runs: `.run(...)` in, result out."""

    def run(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError


class Stage(Component):
    """One pipeline step: a name plus the stage module's frozen entry.

    LATE-BOUND on purpose: the function is looked up on the module at every
    call, exactly as the function orchestrator's `_module.run(...)` was — a
    monkeypatched stage (tests simulate an offline LLM by patching
    `generate.run`) must reach the engine, and an eagerly captured function
    object would silently ignore the patch (caught by test_engine_flow on
    the first refactor attempt)."""

    def __init__(self, name: str, module, attr: str = "run") -> None:
        self.name = name
        self._module = module
        self._attr = attr

    def run(self, state, cfg):
        return getattr(self._module, self._attr)(state, cfg)

    def __repr__(self) -> str:  # the trace/debug-friendly handle
        return f"Stage({self.name})"
