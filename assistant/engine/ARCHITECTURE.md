# The engine

The brain. Every device — the Mac GUI and the iPhone — POSTs text to
`assistant.api`, which hands it here. This file is the map: each stage is a
**black box** with an input and an output, and each has its own
`ARCHITECTURE.md` for what happens inside.

---

## The chain

`X_i` is the output of the previous stage and the input to the next.

```
                                            ┌──────────────────────────────────┐
                                            │   X1' = rewrite(X4), up to 3×    │
                                            ▼                                  │
  audio          ┌───────────┐       ┌──────────────┐      ┌──────────────────┐│
  transcript ─X0►│ Ingest    │──X1──►│ Segmentation │──X2─►│ decompose_       ││
                 │ & fix     │       │              │      │ validate         ││
                 └───────────┘       └──────────────┘      └──────────────────┘│
                                                                    │          │
                                                                    X3         │
                                                                    ▼          │
                 ┌───────────┐       ┌──────────────┐      ┌──────────────────┐│
                 │  COMMIT   │◄──────│  LLMJudge    │◄─X4──│    FastRule      ││
                 │  + label  │       │              │──────┴──────────────────┘│
                 └───────────┘       └──────────────┘                          │
                       ▲                     └─────────────────────────────────┘
                       │  confident? commit immediately
                       └──────────────────────── FastRule
```

- **FastRule confident → COMMIT immediately.** LLMJudge still runs afterwards.
- **If LLMJudge is not satisfied**, it rewrites the utterance into `X1'` — a
  string in X1's format — and re-enters at Segmentation, bounded at 3 rounds.
  A commit already made is **retracted and re-committed**.

> **Not all of this is wired yet.** The table under *Status* says exactly which
> parts are live today and which are planned in
> `DOCUMENTATION/ENGINE_REWIRE.md`. A diagram of a system that does not exist is
> how documentation starts lying.

---

## The stages, as black boxes

| stage | in | out | folder |
|---|---|---|---|
| **Ingest & fix** | `X0` the raw transcript(s) | `X1` one repaired command string | `ingest/` |
| **Segmentation** | `X1` a command | `X2` `[(action, time, tag), …]` | `segmentation/` |
| **decompose_validate** | `X2` = (items, X1) — items **and** the fixed transcript | `X3` items, COMPLETE: every field an object needs, resolved and traceable | `decompose_validate/` |
| **FastRule** | `X3` complete items — no transcript | `X4` calendar / to-do objects ready to write | `fastrule/` |
| **LLMJudge** | `X4` objects + the raw text | approve, or `X1'` a rewritten command | `llmjudge/` |
| **COMMIT + label** | approved objects | rows in the DB, categorised | `label/` + the orchestrator |

**Ingest & fix** — everything between "what Whisper wrote" and "words worth
parsing": several queued recordings coalesce into one input, the personal
vocabulary repairs what it is confident about, false starts are dropped and
never remembered.

**Segmentation** — the separate things the speaker asked for. `action` is the
words minus the time, `time` is the time reference **as spoken** (never
resolved), `tag` is `event | task | review`.

**decompose_validate** — takes the items **and the transcript** (`X2`).
`decompose` splits until each item is atomic and then COMPLETES it: the date and
clock times resolved from its own `time`, recurrence rounded, quantity, lead
time, attendees. `validate` then compares the completed items back against the
transcript and fixes or blocks what does not hold.

X3 is therefore **complete or blocked, never half-built** — FastRule receives
items with nothing left to re-read, which is why the transcript stops here.
Every field must be TRACEABLE to the words: an unsupported date is an invention.

Not built that way yet — see `decompose_validate/PLAN.md` for what exists, why
it is convoluted, and the order to fix it.

**FastRule** — turns items into objects that can be written. Rules first, a
model only where they cannot decide, and a DEFER verdict that is a contract:
`REFUSAL` must not be overturned, `STRUCTURE` means split further, `INCAPACITY`
hands over its partial parse rather than starting cold.

**LLMJudge** — the last check before anything is trusted. The model **extracts**
what the raw text asked for; deterministic code diffs that against what was
produced. The model never judges and never picks the blame.

**COMMIT + label** — the only place that writes to the DB. Category and colour
for events, tags for tasks; adjacent events never share a colour.

---

## Component vs Stage

> **`Component`** — any runnable unit: `.run()` in, result out.
> **`Stage`** — a Component that is one of the boxes above:
> `run(state, cfg) -> state`, ordered, trace-visible, and it owns a folder.

`Stage ⊂ Component`. **Every rectangle in the diagram is a Stage.** The parts
*inside* a stage folder are Components that are not Stages:

| Component, not a Stage | in |
|---|---|
| `FastSeg` · `LLMSeg` · `old_seg` | `segmentation/` |
| `Atomicity` · `Gatekeeper` · `Scorer` | `fastrule/` |
| `Engine` | the whole pipeline as one runnable thing |

Two consequences worth knowing:

- **A folder can hold more than one Stage.** `decompose_validate/` does.
- **Swapping a stage PIECE is invisible to the trace.** Segmentation moved from
  `old_seg` to `FastSeg` without touching `BRAIN_VERSION`, because
  `Stage("segment")` did not change. Renaming a *Stage* is the expensive one.

---

## What is shared, and what is frozen

**`EngineState`** (`state.py`) is the only thing passed between stages. An
`Item` is `(kind, text, time, slots, …)`:

| field | meaning |
|---|---|
| `kind` | `event` \| `task` \| `review` — the SURFACE it concerns, not the operation. "cancel the dentist" is `event`. |
| `text` | the ACTION words. The time is **not** in here. |
| `time` | the time reference as spoken — never a resolved date |
| `spoken()` | action + time reattached — **what anything parsing for a date must use** |

`spoken()` is not a convenience. `FastRule` and the LLM parser both extract the
date from the string handed to them, so passing `text` alone produces events
with no time at all.

**The stage contracts are frozen** and `tests/unit/test_engine_contracts.py`
pins them. Fix a weak stage inside its own folder, against its own tests — never
by reshaping `EngineState` or reaching into another stage. If the contract
itself is wrong, that is a design change: it goes to `TASKS.md` and gets decided,
the way `Item.time` was.

---

## The trace, and why renaming a stage costs something

`trace.py` holds `BRAIN_VERSION` and `CHAINS`; the HUD, the Mac thinking panel
and the iOS `ThinkingView` render a command's chain of thought from it.

`CHAINS` and `thinking_panel._STAGE_ICONS` key off trace **kinds** (`vocab`,
`rule`, `validate`, `llm`, `execute`, `verify`, `done`) — **not stage names**. So
a stage rename needs no new icon. What costs is changing the chain's SHAPE:
bump `BRAIN_VERSION` (an old trace must still render in its old format), add the
new `CHAINS` entry, and update the panel, iOS and the explorer diagram.
`test_panel_agreement.py` goes red until they agree, naming what to fix.

---

## Status — what is wired TODAY

The chain above **is** the code. Verified by `scripts/engine_pipeline_check`,
which asserts the shape at every boundary and runs commands end to end.

| box | Stage | module |
|---|---|---|
| Ingest & fix | `Stage("transcript")` | `ingest/repair.py` + `ingest/coalesce.py` |
| Segmentation | `Stage("segment")` | `segmentation/` — FastSeg, LLMSeg **off** |
| decompose_validate | `Stage("decompose_validate")` | `decompose_validate/stage.py` |
| FastRule | `Stage("fastrule")` | `fastrule/stage.py` → `fastrule/objects.py` |
| LLMJudge | `Stage("llmjudge")` | `llmjudge/llmjudge.py` |
| COMMIT + label | inside `_commit` | orchestrator + `label/label.py` |

Two things are wired but **deliberately inert**, and both are named rather than
hidden:

| | state |
|---|---|
| **LLMSeg** | off by default (`MACALENDAR_LLMSEG`). Measured net-negative four ways — §6. |
| **the loop** | `llmjudge.rewrite_for_retry` is a stub returning None, so no loop fires. The contract and its single call site are in place; the rewrite itself wants a model call grounded on `state.raw_text`. |

**Why the loop is gated on a rewrite rather than just re-running.**
Segmentation is deterministic, so re-entering it with the same text returns the
same items — the retry can only spend the budget. Real usage, 2026-09-08: *"Let
an event to go out for a run now"* looped three times to the identical result
and apologised after 30 seconds. So: **no rewrite, no loop.**

Also still open, recorded in `segmentation/ARCHITECTURE.md` §6b: the month can
be severed from its ordinal (`the 20th of November`), which is the one NEW test
failure this rewire introduced.

## Where to read next

| | |
|---|---|
| a stage's internals | `assistant/engine/<stage>/ARCHITECTURE.md` |
| the frozen contracts | `DOCUMENTATION/ENGINE.md` |
| the rewire plan | `DOCUMENTATION/ENGINE_REWIRE.md` |
| how components got their folders | `DOCUMENTATION/ENGINE_RESTRUCTURE.md` |
| the workflow rules | `CLAUDE.md` |
