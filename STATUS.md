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
  Four graduated cycles on 2026-09-04 took dev-fast(250) count-correct
  **73.2 → 77.6%** (complex 40→54, e+e 52→67, e+t 35→46, t+t 35→50/55);
  dev-full confirmed C1+C2 at +1.8 off-slice, C3+C4 confirm in flight.
  Full record:
  `dataset/RESULTS.md` (prose) + `dataset/loop_log.csv` (plottable, one row
  per run — a protocol requirement now). Run outputs preserved per cycle in
  `DOCUMENTATION/experiments/engine_compare/<label>/`.
  **If a session ends mid-loop, resume here:** read the newest RESULTS.md entry
  + loop_log.csv row, then continue the protocol
  (`DOCUMENTATION/experiments/ITERATION_PROTOCOL.md`): take the top unblocked
  entry of **`dataset/HYPOTHESES.md`** (the ranked experiment queue), write its
  prediction in RESULTS.md, fix ONE stage, rerun dev-fast, re-rank the queue.
  A dev-full confirm is batched with the next graduated win. Since
  2026-09-05 the harness replays each row frozen at its recorded ts with
  observance gating off (measurement epoch reset — re-baseline first);
  questions for Gil live in `DEVQA.md`; the loop branch merges into `main`
  every few graduated cycles.
- **Backlog — user-gated, do not start unprompted:** add fast-rule-parser rules
  mined from the user's real data + the dataset. Only on Gil's explicit say-so,
  and only after the deep track is improved — not on my own initiative.

## App stream — next session picks up here (Gil, 2026-09-06)

Work happens in THIS worktree (`../MACalendar-app`, branch `app-features`);
merge with `main` + the loop branch between cycles. Queue, in order:

1. **Model-comparison — CLOSED (Gil stopped it, 2026-09-06).** Partial-data
   verdict in `dataset/MODEL_COMPARISON.md`: on identical rows the tuned
   local llama beat both Claude drop-ins (deep rows: 80% vs Sonnet 60% /
   Haiku 53%) — the engine's llama tuning + mechanical schema constraint
   outweigh raw model strength; privacy costs nothing. Do not respawn sims.
2. **Notifications** — PLANNED 2026-09-06: `DOCUMENTATION/NOTIFICATIONS_PLAN.md`
   (5 phases; phone = reliable ringer from the offline cache, server computes
   `notify_at`, Mac banners best-effort, observance quiet windows on the fire
   time) + visual preview artifact linked there. Build blocked on Gil's three
   answers (DEVQA Q4-Q6): Mac-with-calendar-closed?, default lead 0 or 30?,
   in-Shabbat events suppress or pre-candle digest?
3. ✅ **.ics export/share** — DONE @ 243d99f (ics_export.py, GET
   /events/<id>.ics, Mac dialog button; iOS share sheet in flight).
4. ✅ **Search** — DONE @ 243d99f (GET /search, Mac toolbar box +
   jump-to-date; iOS offline SearchView in flight).
5. **Small wins** — mostly DONE @ 243d99f: duplicate-event ✅ · week
   numbers ✅ (`ui.show_week_numbers`) · Timer CSV ✅ · observance checkbox ✅
   (found + fixed the pydantic-drops-`observance.enabled` bug, DEVQA Q2
   closed). Remaining: agenda view (agent in flight) · iOS `/heartbeat`
   (agent in flight — endpoint already existed server-side).
6. ✅ **Convolution #1** — DONE @ 243d99f: ThinkingView + EngineChain live in
   `Views/ThinkingView.swift` (byte-identical move, simulator build green).

## Working notes

- Two Claude sessions share this project's checkouts; re-read a `main`-checkout
  file immediately before editing (uncommitted work has no git net).
- Never run an audit/replay beside another model-loading job (spaCy/torch
  segfault). RAM is near full — LLM replays are serial.
