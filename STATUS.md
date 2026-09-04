# STATUS — where we are

**One-screen reference. A fresh conversation reads this first, then CLAUDE.md.**
Keep it current and short; details live in the files it points to.

_Updated 2026-09-04 — engine live in production._

## The state

- **The brain is being rebuilt** as `assistant/engine/` (8 stages, frozen
  contracts) on branch `engine-v2`. `DOCUMENTATION/ENGINE.md` is the contract
  reference.
- **LIVE in production (cut over 2026-09-04, merge bce502e).** The engine is
  the brain on `main`; smoke-verified (parse=fast, brain=engine-v2).
- The old brain is archived at `retired/old-brain-v1/` (+ tag `pre-engine-v2`).
  Rollback: `git reset --hard 4c61f82` (keeps the dataset work, drops the
  engine) then relaunch.

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
a supervised-ML loop — run the **smallest rich-enough subset** (dev-fast, ranks
1–250, ~80 min; **never the full 3000 as the working loop**) → score via the
metrics →
understand *why* (read the breakdown + the failing rows, not just the number) →
**hypothesise** and fix ONE component's implementation (design frozen) → rerun →
compare actual vs. expected in `RESULTS.md` → upsize only as gains slow.

## In flight / next

- **Client/UI** (endorsed 2026-09-04) — all three done:
  - ✅ iOS edit-transcription sheet — server threads `supports_edit` through the
    audio routes; iOS shows the editor on `needs_edit` and resubmits.
  - ✅ Thinking panel renders *by brain version* — a `CHAINS[BRAIN_VERSION]`
    scaffold rail with per-step ⓘ (in-depth copy from `trace.STAGE_INFO`), Mac
    panel + iOS `ThinkingView`; iOS red→amber consistency fix folded in. See
    `ENGINE.md`'s render section. **HUD needs a restart to show it.**
  - ✅ One-tap revert — a destructive background patch carries `revert` specs
    (ready-to-POST bodies); Mac `_RevertBar` + iOS banner re-create what was
    undone. Dormant until `self_check_apply` is on (removals are advisory by
    default). **HUD needs a restart to show it.**
- **Deep-track improvement loop — RUNNING (branch `loop-cycle-1`).**
  Cycle 1 ✅ confirmed & graduated (2026-09-04): enforcing the pinned
  remind+clock-time⇒event rule over segment's LLM labels took dev-fast(250)
  count-correct **73.2→76.0%** (event+task 35→41, predicted ~40). Full record:
  `dataset/RESULTS.md` (prose) + `dataset/loop_log.csv` (plottable, one row
  per run — a protocol requirement now). Run outputs preserved per cycle in
  `DOCUMENTATION/experiments/engine_compare/<label>/`.
  **If a session ends mid-loop, resume here:** read the newest RESULTS.md entry
  + loop_log.csv row, then continue the protocol
  (`DOCUMENTATION/experiments/ITERATION_PROTOCOL.md`): next pile is
  **task+task 35% (n=20)** — read its failing rows in the latest
  `engine_compare/cycle1_fix/` outputs, write the cycle-2 hypothesis in
  RESULTS.md, fix ONE stage, rerun dev-fast. A dev-full confirm is batched
  with the next graduated win.
- **Backlog — user-gated, do not start unprompted:** add fast-rule-parser rules
  mined from the user's real data + the dataset. Only on Gil's explicit say-so,
  and only after the deep track is improved — not on my own initiative.

## Working notes

- Two Claude sessions share this project's checkouts; re-read a `main`-checkout
  file immediately before editing (uncommitted work has no git net).
- Never run an audit/replay beside another model-loading job (spaCy/torch
  segfault). RAM is near full — LLM replays are serial.
