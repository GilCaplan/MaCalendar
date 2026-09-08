# Engine rewire — one flat chain, and a loop that rewrites the input

**Status: DONE, 2026-09-08** — on `engine-component-folders`, not merged.
The chain is wired and `assistant/engine/ARCHITECTURE.md` is the live map; this
file is the record of what was decided and what is still open.

Two things shipped deliberately INERT, both named in the architecture doc:
LLMSeg is off, and `rewrite_for_retry` is a stub returning None so no loop
fires. The contract and its call site exist; the rewrite itself is the work
left.

## The chain

```
X0 ─► Ingest&fix ─X1─► Segmentation ─X2─► decompose_validate ─X3─► FastRule ─X4─► LLMJudge
                            ▲                                          │              │
                            │                                    confident?           │
                            │                                          ▼              │
                            └──── X1' = rewrite(X4), up to 3× ──── COMMIT (+label) ◄───┘
                                                                       ▲
                                                    retract & re-commit when the loop fires
```

`X_i` is the output of the previous stage and the input to the next.

## The two words, settled

> **`Component`** — any runnable unit: `.run()` in, result out.
> **`Stage`** — a Component that is a numbered box above: `run(state, cfg) -> state`,
> ordered, trace-visible, owns a folder.

`Stage ⊂ Component`. Every rectangle in the diagram is a Stage. The things
*inside* a stage folder are Components that are not Stages — `FastSeg`,
`LLMSeg`, `old_seg`, and FastRule's `Atomicity` / `Gatekeeper` / `Scorer`.

**This is the meaning `Component` did not previously have.** Only `Engine`
and the now-removed stage-list wrapper declared it, and nothing consumed it
polymorphically, so it was documentation. It needs the definition above or it
should be deleted too.

## What changes

| today | after |
|---|---|
| a wrapper class holds the re-runnable stage list | **deleted** — one flat ordered list on `Engine` |
| `Stage("generate")` calls `FastRule` per item | **`Stage("fastrule")`** — the stage IS object-making |
| `Stage("validate_objects")` runs after generate | **folded into `decompose_validate`** |
| `Stage("crosscheck")` routes blame to 3 stages | **`Stage("llmjudge")`** — always rewrite X1 and re-enter at Segmentation |
| `label` runs after commit, separately | **part of the COMMIT step** |
| commit is final | **retractable** — the loop can undo and re-commit |

## Why the loop rewrites the string

Today `crosscheck` loops back and re-runs segmentation **on unchanged text**.
FastSeg is deterministic and LLMSeg is off, so it returns the identical answer
and the loop is inert — the same reason `state.asked_fastrule` exists for
FastRule. Rewriting the utterance into something Segmentation can break down is
what makes a retry able to produce anything new. **This is the defect the
rewire fixes, not a nicety.**

`X1'` is a STRING in X1's format (a repaired transcript), not items. So the
loop's contract is `rewrite(X4) -> str`, bounded at 3 re-entries.

## Retraction — the machinery already exists

`state.records` tracks what each item created, **per item** (which is what fixed
the row-75 batch-attribution bug), and `db.delete_event` / `db.delete_todo` are
there. So "undo what was committed" is wiring, not new capability. The rule to
keep: a retraction is user-visible, so it surfaces in the review panel with a
one-tap revert, exactly like today's destructive patches.

## The trace surfaces — smaller than it first looked

`CHAINS` and `thinking_panel._STAGE_ICONS` key off trace **kinds** (`vocab`,
`rule`, `validate`, `llm`, `execute`, `verify`, `done`), **not stage names**. So
renaming a stage costs nothing there, and **no new icon is needed** as long as
LLMJudge keeps emitting `VERIFY`.

What does change is the chain's SHAPE, so:

- [x] bump `BRAIN_VERSION` (an old trace must still render in its old format)
- [x] add the new version's `CHAINS` entry
- [x] update the explorer diagram + iOS `ThinkingView` labels if the wording moves
- [x] `test_panel_agreement.py` goes red until these agree — by design

## Order of work

- [x] 1. Branch off `engine-component-folders`.
- [x] 2. Delete the stage-list wrapper; flatten to one ordered list on `Engine`.
- [x] 3. Give `fastrule/` a stage module (`run(state, cfg) -> state`) that turns
      Items into objects. `generate`'s per-item LLM fallback moves inside it —
      the stage is "make the objects", FastRule-first is *how*.
- [x] 4. Fold `validate.run_objects` into `decompose_validate`.
- [x] 5. Move `label` into the commit step.
- [x] 6. `crosscheck` -> `llmjudge`: replace the blame router with
      `rewrite(X4) -> X1'`, re-enter at Segmentation, bounded at 3.
- [ ] 7. Retraction path on the loop (`state.records` -> delete -> re-commit).
      NOT DONE — nothing loops yet, so nothing needs retracting. It becomes
      necessary the moment `rewrite_for_retry` stops returning None.
- [x] 8. `BRAIN_VERSION` + `CHAINS` + panel/iOS/explorer.
- [x] 9. `pytest tests/unit` green. Baseline to beat: **1319 passed**.
- [x] 10. Update `CLAUDE.md`, `ENGINE.md`, `CODE_MAP.md`, and each
      `ARCHITECTURE.md`; regenerate the API reference if a field moved.

## Open, for when we design `decompose_validate`

Gil, 2026-09-08: *"all this should be done in the decompose_validate step, we
didn't get to the details of this component yet."* Recorded so it is not lost:

- **Date resolution lands here.** `relative_dates`, `_rule_relative_date_pin`,
  `_rule_past_date_bump` currently run in `validate.run_objects` AFTER generate,
  because they need `item.intent`. Folding them in means either running them on
  `Item.time` (which segmentation now provides separately) or keeping a second
  internal pass.
- **`Item.time` makes the first option possible for the first time** — the
  reading no longer has to be re-derived from the transcript with the
  `ev_idx`/`n_events` index-pinning that broke in commit `a987aba`.
- **The observance gate** also lives in `run_objects` and is object-level.

## Deliberately NOT in this change

- Promoting or retiring `old_seg` — it stays behind `MACALENDAR_SEGMENTATION`.
- Turning LLMSeg on — it stays off behind `MACALENDAR_LLMSEG`.
- Redesigning `decompose_validate` — only the fold-in, per above.
- The one known-failing test (`test_loop_back_reruns_segment_with_the_mistake`),
  which Gil parked. Step 6 is what makes it meaningful again: once the loop
  rewrites the string, a deterministic segmenter CAN return something new.
