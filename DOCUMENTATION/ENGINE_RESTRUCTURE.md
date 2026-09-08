# Engine restructure — component folders

**Status: NOT STARTED. Blocked until the `v4-full` prompt run finishes.**
Agreed with Gil 2026-09-08. This is a **cleanup**: files move, the pipeline's
shape does not. Work the checklist in order and tick as you go — it exists so a
half-finished restructure can be resumed by someone who was not here.

## The one rule

**`Stage("…")` identifiers do NOT change in this work.** `assistant/trace.py`'s
`CHAINS` keys off generic kinds (`vocab`, `rule`, `validate`, `llm`, `execute`,
`verify`, `done`), not module names — so folders and modules rename freely,
but renaming a *stage identifier* triggers the whole panel procedure
(bump `BRAIN_VERSION`, update `CHAINS`, add the icon + ship the SVG, update
`thinking_panel.py`, iOS `ThinkingView`, the explorer diagram) and
`test_panel_agreement.py` will go red naming what to fix. Keep them stable.

Corollary worth stating: after this change the folder is `llmjudge/` while the
stage identifier is still `"crosscheck"`. That inconsistency is deliberate and
temporary — the trace-visible rename is its own change, listed at the bottom.

## Target layout

```
assistant/engine/
  __init__.py  state.py  component.py  llm.py     orchestrator + frozen contract, unmoved

  ingest/            ARCHITECTURE.md
      repair.py      <- engine/transcript.py          (vocab fixes, false starts, needs_edit)
      coalesce.py    <- the queue extracted from __init__.py   (concatenation)

  segmentation/      ARCHITECTURE.md      <- the deep one
      fastseg/       <- segment_tuning/fastseg.py + invariant.py
      llmseg/        <- segment_tuning/llmseg.py + prompts/
      old_seg/       <- engine/segment.py   KEPT, NOT PROMOTED (Gil promotes when ready)
      datasets/      <- segment_tuning/data/            (1,694 rows)
      experiments/   <- score, run_board, generate, gate_sizing, pos_sizing,
                        prompt_lab, batch_sizing, check_prompt, old_vs_new,
                        SPEC.md DESIGN.md RESULTS.md DATASET_PLAN.md, runs/

  fastrule/          ARCHITECTURE.md
      fastrule.py    <- engine/fastrule.py              (the system itself)
      datasets/      <- dataset/fastrule/               (7,200 rows + banks)
      experiments/   <- scripts/{fastrule_shape,fastrule6k,fast_sandbox}.py

  decompose_validate/  ARCHITECTURE.md
      decompose.py     <- engine/decompose.py    functions stay SEPARATE (Gil)
      validate.py      <- engine/validate.py     still runs twice; that is unchanged

  generate/   generate.py  <- engine/generate.py    + ARCHITECTURE.md
  llmjudge/   llmjudge.py  <- engine/crosscheck.py  + ARCHITECTURE.md
  label/      label.py     <- engine/label.py       + ARCHITECTURE.md
```

**`dataset/` stays put** for the 3,000-utterance whole-system verification
corpus (`engine_dataset_compare`) — it is cross-component, not Segmentation's.
Only the fastrule and segmentation datasets move.

## Order of work

- [ ] **0. WAIT.** `v4-full` must finish. Two reasons, both real: the running
      job holds `segment_tuning` modules and appends to `segment_tuning/runs/`,
      and `old_vs_new.py` calls the OLD stage which falls back to
      `_llm_segments` — a second Ollama client would contend and silently
      inflate every latency number. Check with
      `ps -ax -o command | grep -c "^/opt/homebrew.*segment_tuning"` — must be 0.
- [ ] 1. Branch. Never `main`.
- [ ] 2. `git mv` every file per the table. `git mv`, not copy — history matters.
- [ ] 3. Add temporary shim modules at the old paths re-exporting the new ones,
      so the tree stays importable between steps.
- [ ] 4. Update the **43 importers** (see below).
- [ ] 5. `pytest tests/unit` green. This is the gate — `test_engine_contracts`,
      `test_engine_flow` and `test_panel_agreement` are what prove the shape
      did not move.
- [ ] 6. Delete the shims. Re-run `pytest tests/unit`.
- [ ] 7. `pytest tests/` (integration skips without Ollama).
- [ ] 8. Write the ARCHITECTURE.md files.
- [ ] 9. Run `old_vs_new.py`, record the result in
      `segmentation/experiments/RESULTS.md`.
- [ ] 10. `python scripts/gen_api_reference.py` if any request field moved.
- [ ] 11. Update `CLAUDE.md`, `DOCUMENTATION/SYSTEM.md`, `CODE_MAP.md`,
      `ENGINE.md`, `TASKS.md` to the new paths.

## The 43 importers of `assistant.engine`

| where | n | note |
|---|---|---|
| `tests/unit/`, `tests/integration/` | 25 | mechanical |
| `scripts/` | 9 | `engine_dataset_compare`, `engine_stage_check`, `fast_sandbox`, `fastrule6k`, `fastrule_shape`, `atomicity_board`, `atomizer_board`, `kind_board`, `persona_board` |
| `assistant/api/server.py` | 1 | the front door |
| `assistant/cli.py` | 1 | **Gil asked for this explicitly** |
| `assistant/pipeline.py` | 1 | GUI glue |
| `segment_tuning/fastseg.py` | 1 | becomes internal once moved |
| `retired/fastrule-v1/` | 1 | leave alone — retired code stays frozen |

`segment_tuning/fastseg.py` imports, all of which must keep resolving:
`assistant.intent.asks`, `assistant.intent.coordination`,
`assistant.intent.cleanup`, and `assistant.engine.segment`
(`_kind_of`, `_enforce_pinned_kinds`) — that last one becomes
`segmentation.old_seg`, so **FastSeg will depend on old_seg until promotion**.
Note it in the ARCHITECTURE.md rather than hiding it.

## What each ARCHITECTURE.md contains

`segmentation/ARCHITECTURE.md` is the template, per Gil:

1. Segmentation as a **black box** — contract in, contract out, FastSeg and
   LLMSeg named but not opened.
2. Then FastSeg's own architecture (cut → assign time → tag).
3. Then LLMSeg's (prompt, tag coercion, the ACCEPT guard).
4. The **datasets** used to improve it, and how they were built.
5. The **evaluation metrics** — the six boards, and why never one number.
6. The **results**, including what was REFUTED, so nobody re-spends on it.

`fastrule/ARCHITECTURE.md` gets the same treatment. The rest get a short
honest stub saying what the component does and that it has not been dug into
yet — `decompose_validate` says Gil is designing it next.

## Deliberately NOT in this change

- Promoting FastSeg/LLMSeg over `old_seg` — Gil promotes when ready.
- Merging decompose and validate into one **stage** — folder only; validate
  still runs twice (text pass, then `validate_objects` after generate).
- `llmjudge`'s behaviour change (verify → repair the string → re-enter at
  segmentation). Today `crosscheck` routes blame to several stages. Rename and
  move now; behaviour when Gil gives the details.
- The trace-visible stage rename `crosscheck` -> `llmjudge`, which needs the
  full `BRAIN_VERSION` procedure.
