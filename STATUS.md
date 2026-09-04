# STATUS — where we are

**One-screen reference. A fresh conversation reads this first, then CLAUDE.md.**
Keep it current and short; details live in the files it points to.

_Updated 2026-09-04._

## The state

- **The brain is being rebuilt** as `assistant/engine/` (8 stages, frozen
  contracts) on branch `engine-v2`. `DOCUMENTATION/ENGINE.md` is the contract
  reference.
- **NOT yet cut over.** The live Mac/phone assistant still runs the OLD brain
  from the `main` checkout. Cutover = merge `engine-v2` → `main`; in progress.
- The old brain is archived at `retired/old-brain-v1/` (+ git tag
  `pre-engine-v2`) for revert/compare.

## Primary evaluation

The verification dataset (`dataset/`, see `dataset/DATASET.md`) — 3000 real
utterances, count-correctness + 4 other metrics, dev/held-out subsets. The
hand-written audit corpus is now only a regression floor.

- **Latest numbers (count-correctness, metric #1):** engine **73.5%** vs old
  **70%** on the 2400 sealed held-out prompts; compounds 2–3× the old brain.
  Full table: `dataset/RESULTS.md`.
- Frontier: complex compounds (35–39%); the event half drops in 72% of
  event+task failures.

## The loop

`dataset/DATASET.md` + `DOCUMENTATION/experiments/ITERATION_PROTOCOL.md`:
run a subset → compare to ground truth via the metrics → fix the one guilty
stage → rerun; small subset for big deltas, upsize to avoid overfitting.

## In flight / next

- Cutting the system over to the engine + retiring the old brain (this thread).
- Next tuning target: the event-drop on event+task compounds (metric:
  count-correctness, slice: event+task).
- Proposed, not yet built: an explicit precision/invention metric; each cycle
  stating its target metric+slice up front.

## Working notes

- Two Claude sessions share this project's checkouts; re-read a `main`-checkout
  file immediately before editing (uncommitted work has no git net).
- Never run an audit/replay beside another model-loading job (spaCy/torch
  segfault). RAM is near full — LLM replays are serial.
