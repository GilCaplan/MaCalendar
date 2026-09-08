# Retired — the object-brain design (2026-09-07)

`OBJECT_BRAIN_DESIGN.md` is the proposal that introduced the class wrapping the
re-runnable stage list. That wrapper was **removed on 2026-09-08** (Gil): it
held no logic of its own, and the rewire's loop — which re-enters at
Segmentation with a rewritten utterance — makes the boundary it marked explicit
instead. `Engine` now owns one flat ordered list.

Kept per the project convention that a superseded design is never just deleted.
What survived from it and is still true: `Component` / `Stage`, the frozen
per-stage I/O contracts, and FastRule's object shape.

The live documents are `assistant/engine/ARCHITECTURE.md` (the chain) and
`DOCUMENTATION/ENGINE_REWIRE.md` (the plan that replaced this one).
