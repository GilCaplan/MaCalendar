# STATUS — where we are

**One-screen reference. A fresh conversation reads this first, then CLAUDE.md.**
Keep it current and short; details live in the files it points to.

_Updated 2026-09-06 10:10 — cycles 1–6 closed (C6 graduated); notifications
shipped (phases 1+2+4); branches merged at afc8c80._

**Next session picks up here (paused 2026-09-06 ~18:00 on Gil's token call):**
1. **Cycle 8 run is IN FLIGHT** (spoken lead-times @ 48b9ac9, prediction in
   RESULTS.md: full board flat, judged on stage tests + alert-before rows).
   The local run survives the session: results in scratchpad
   cycle8_devfast.log + auto-archived to dataset/runs/x_auto-*. Close it
   with `python -m scripts.run_board` after renaming the archive to
   run14_cycle8-fix (manifest loop_run=14).
2. **Simple-tier fieldq anomaly SOLVED — fix not yet written**: two scorer
   artifacts in scripts/field_quality.py: (a) `_content_words` regex
   `[a-z0-9']+` keeps quote-apostrophes, so `'christmas'` ≠ `christmas`
   (title scored 0 on verbatim quotes); (b) a title whose words are all
   STOPWORDS ("Reminder", the fallbacks' honest default) hits
   `if not words: return 0.0` in `_title_sim` — should score by verbatim
   containment in the transcript instead. Fix in the WORKTREE copy, test
   with run-12's worst-12 rows (analysis printout in this session's log),
   merge, then manually recompute fieldq for runs 12–13 for comparability.
3. Then cycle 9 = HYPOTHESES #4 ungated half ("update X with new items" ⇒
   create) + the dentist query-mutation bug fix riding along.
4. Unnamed localhost duplicate-maker: fingerprint log now on POST /todos —
   check launch.log for `ua=` on its next appearance.
 loop = hypothesis **#5 invention guard**
(validate stage; fresh evidence: cycle 5's loose "in the future" groundings
+ the garble-row "New Event" fabrication; judge with the adjusted metric +
precision, count-correct expected ~flat). Also open: notifications phase 3
(voice lead-time phrase — engine files, now unblocked by the merge; per
Gil's model-budget rule, weigh delegating vs. loop time), the dentist
query-mutation bug (queued in HYPOTHESES.md), and DEVQA Q1/Q4–Q6 await Gil.
Per Gil (2026-09-06): Fable works ONLY the self-improvement cycles; feature
work goes to Sonnet/Opus subagents.

## The state

- **The brain was rebuilt** as `assistant/engine/` (8 stages, frozen
  contracts; branch `engine-v2`, now merged). `DOCUMENTATION/ENGINE.md` is
  the contract reference.
- **LIVE in production (cut over 2026-09-04, merge bce502e).** The engine is
  the brain on `main`; smoke-verified (parse=fast, brain=engine-v2).
- The old brain is archived at `retired/old-brain-v1/` (+ tag `pre-engine-v2`).
  Rollback: `git reset --hard 4c61f82` (keeps the dataset work, drops the
  engine) then relaunch.

## Primary evaluation

The verification dataset (`dataset/`, see `dataset/DATASET.md`) — 3000 real
utterances, count-correctness + 4 other metrics, dev/held-out subsets. The
hand-written audit corpus is now only a regression floor.

- **Current anchor (epoch baseline, run 9, 2026-09-05):** count-correct
  **78.4% raw / 81.2% product-adjusted** on dev-fast-250, F1 82.1, field
  quality 84.6 (frozen row-timestamps, observance off — the epoch reset;
  pre-2026-09-05 rows in loop_log.csv are not comparable). Full record:
  `dataset/RESULTS.md`.
- **Two standing instruments (2026-09-06):** every run auto-archives its
  scratch to `dataset/runs/` (manifest = identity; `scripts/rescore_runs.py
  --write` recomputes the whole history when a metric changes), and the
  conventions-overrides layer (`dataset/inputs/convention_overrides.json`)
  reports product-adjusted `count_ok_adj` beside raw — its query-no-mutation
  check found an OPEN engine bug (a query emitting `update_event`; queue row
  in HYPOTHESES.md).
- Frontier: fast/deep rescue is largely harvested (deep rescues 7/21 fast
  failures but breaks 6/82 passes — net +1 row); remaining losses are
  convention/capability rows. Model-comparison closed: the tuned local llama
  beat Claude Sonnet/Haiku drop-ins on identical rows (worktree
  `dataset/MODEL_COMPARISON.md`) — do not respawn the sims.

## Forward roadmap (2026-09-07)

1. ✅ **INTEGRATED @ effebeb (2026-09-07)** — FastRule object + F1/F2/F3 +
   0.80 threshold on the loop tree; sandbox matches (34%/93.0% adj); joint
   confirmation run **CONFIRMED 2026-09-06** (run 16 = era-2 baseline: adj
   80.0 flat-within-noise, fast correct 79→90). **Merged to main**; fastlane
   worktree reset onto the integrated state (pre-integration tag kept). Original plan:
   INTEGRATE the stacked fast-lane work into the loop tree — F1+F2+F3
   vetoes + tuned RULE_THRESHOLD 0.80 + SUBITEM 0.60 + cycle-9 sub-item
   trust — and run ONE joint full-engine cycle (the remerge gate: nothing
   from the sandbox counts on the main board until this confirms).
2. **HARD CHECKPOINT (Gil, 2026-09-07): describe the updated algorithm
   structure and get Gil's read BEFORE running the next cycle.** No cycle 10
   until then.
3. **Cycle 10** — full rules-first-per-fragment (green-lit by cycle 9's
   latency win), LLM = end-judge only, at the 0.60 sub-item bar.
4. **F4+ sandbox** — parse-quality batches (task+task soft spot, safe
   low-conf recoverables) in parallel.
5. **Path B** — crosscheck-precision metric → improve crosscheck.py → flip
   self_check_apply (verify auto-updates fast commits).
6. **Per-instance/context threshold fine-tuning** (Gil's forward idea) —
   once integrated, thresholds per FastRule instance/command class.
7. Queued hypotheses (dentist bug, list-op, fieldq anomaly) reopen last.

## Plan of record

**STAGE ISOLATION (Gil, 2026-09-07) — see DOCUMENTATION/STAGE_ISOLATION_PLAN.md.**
Engine cycles paused. Order: (1) FastRule dataset+metrics right — defers on
non-atomic, creates otherwise; (2) every other stage tested in isolation
with its OWN dataset (separate dir, own train-test split, no leakage),
improved separately, each an object where that helps; (3) rebuild the
system from proven parts and measure connected. Segment + decompose first —
they ARE the atomizer FastRule depends on.

**ENGINE CYCLES PAUSED (Gil, 2026-09-07, until further notice).** Lane-only
work: FastRule F-batches toward F15 + K-model iteration. No engine runs, no
integration (even at F15) without Gil's go.

**Data plan (Gil, 2026-09-07):** sealed 300 on the real pool + FastRule's
own 6,000 (80–20 by family) + external corpora as train-side augmentation
only. Three sources, three roles — A real pool = calibration, B generated =
structure supervision (dual-gate rule: win on B-train AND no regress on A),
C external = wording coverage after a conventions pass. Test results never
drive improvement (tooling-enforced, aggregates only). **Every 10th cycle =
a sealed-test milestone run on the main engine — pure eval, one aggregate
line in RESULTS, first at era-2 cycle 10.** Lane order (SIMPLE-FIRST, Gil 2026-09-07): F7 targeting →
R2 calibration + simple-slice sweep → title spans → K1b/K2. Target: simple
commit 66→80%+ at ≥90% correct. Complex work (gate recall, EXT0/EXT1)
deferred until that holds; complex regression floor enforced.

**Era 2 opens with the joint confirmation run** (Gil, 2026-09-06): cycle
history kept, but boards compare within-era only — the integration changed
too much for cycle-vs-cycle reads against era 1. **FastRule lane cadence**:
sandbox keeps iterating on full-3000 in ../MACalendar-fastlane while cycles
run the loop tree's pinned FastRule; graduates integrate every 2–3 cycles at
a boundary, joint-confirmed. **Design choices stay frozen** — implementation
improvements are the loop's initiative, algorithm changes are Gil's call,
asked at boundaries. **Slice growth**: dev-fast 250 is the working slice;
climb to dev-full 600 when target-slice gains near the ~1.5-pt noise floor
(or the target slice is too thin in 250); held-out 601–3000 only to seal
milestones — never mined. (Gil, 2026-09-07) — this order, before ANY new hypotheses

1. **Track 1 — improve the rule system in its sandbox** (fast-lane worktree,
   full-3000 measurable). Batch F3, F4… until abstention + parse quality
   plateau. Self-contained.
2. **Track 2 — restructure the deep pipeline around the rule system.** Vision:
   LLM segments/decomposes → EACH fragment parsed by RULES (not LLM) → the
   assembled events/tasks judged TOGETHER by the LLM once (crosscheck) →
   loop/proceed. Replace N per-item LLM parses with rules + one judgment.
   - Cycle 9 (IN FLIGHT) = conservative step 1: fragments trust rules at 0.60,
     LLM per-item fallback still allowed. Reads latency + accuracy.
   - Cycle 10 = the FULL version — CONFIRMED by Gil (2026-09-07) to run right
     after cycle 9's read: after decompose's separation, EACH fragment goes
     through the rule system; the LLM is the end-judge (crosscheck) only, not
     a per-item parser. Gil-authorized design change.
3. **Verify-and-auto-update, safely (Gil chose B, 2026-09-07).** The LLM
   crosscheck ALREADY verifies every FastRule commit (reconcile:"always",
   incl. 100%-confident); what's gated is auto-APPLYING its corrections
   (self_check_apply, default false — the old auto-applier fixed 0/broke 1
   in the audit). Path B: make the crosscheck's correction PRECISION a loop
   target (improve its extract-and-blame accuracy — a legit implementation
   cycle on crosscheck.py) until false-corrections are measurably rare, THEN
   flip self_check_apply:true. Needs a metric: crosscheck-correction
   precision on the dataset (proposed-and-right / proposed) + a regression
   floor (the retracted-time "2pm sorry 3pm" case must never re-break).
4. Only after these tracks plateau do queued hypotheses reopen (dentist
   query-mutation bug, #4 list-op misreads, simple-tier fieldq anomaly).

## The two improvement lanes

**Deep lane** — the 55-min dev-fast cycles below, now pairable (one [fast]
+ one [deep] hypothesis per run; [routing] rides alone — protocol).
**Fast-sandbox lane (live 2026-09-07)** — `python -m scripts.fast_sandbox`
scores the rule system alone as a selective classifier in ~18s (commit
rate × adjusted-on-committed; an abstain is deep's job). Batched
predictions, dev-full gate, sealed held-out, and NOTHING lands on the main
board until a joint full run confirms. Batch F1 graduated at sandbox level
(89.9%/90.1% adjusted-on-committed, from 82.5 baseline). The
personalization layers are guarded, not metricized — see the protocol's
personalization-guard section (weekly flag rate = post-merge tripwire;
personal rule mining ships shadow-mode).

## The loop

`dataset/DATASET.md` + `DOCUMENTATION/experiments/ITERATION_PROTOCOL.md`:
a supervised-ML loop — run the **smallest rich-enough subset** (dev-fast, ranks
1–250, ~80 min; **never the full 3000 as the working loop**) → score via the
metrics →
understand *why* (read the breakdown + the failing rows, not just the number) →
**hypothesise** and fix ONE component's implementation (design frozen) → rerun →
compare actual vs. expected in `RESULTS.md` → upsize only as gains slow.

## In flight / next

- **App stream (worktree `../MACalendar-app`, branch `app-features`) — the
  whole approved queue SHIPPED 2026-09-06** (243d99f → 3b89809): .ics share
  (server+Mac+iOS), search + jump-to-date (server+Mac toolbar+iOS offline
  sheet), duplicate event, ISO week numbers, Timer CSV, agenda view,
  observance settings checkbox, iOS /heartbeat, ThinkingView file move.
  Two bugs found+fixed on the way: the extracted settings dialog dropped
  imports (NameError on open) and pydantic silently discarded
  `observance.enabled` (field never declared). **Notifications is planned
  only** (`DOCUMENTATION/NOTIFICATIONS_PLAN.md` + preview artifact), blocked
  on Gil's DEVQA Q4–Q6. Merge app-features + loop-cycle-1 + main at the next
  cycle boundary.
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
- **Deep-track improvement loop — RUNNING (branch `loop-cycle-1`), cycle 5
  in flight** (hypothesis #2, grounded default-title events —
  `event_fallback` @ b3c6656; prediction 78.4 → 79.4–79.9 recorded first).
  History: cycles 1–4 took the old-epoch dev-fast 73.2 → 77.6 (dev-full
  74.2 → 78.0, all four graduated); then the epoch reset re-baselined at
  78.4/81.2-adj.
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
   /events/<id>.ics, Mac dialog button; iOS share sheet ✅ @ 7c9d3ab).
4. ✅ **Search** — DONE @ 243d99f (GET /search, Mac toolbar box +
   jump-to-date; iOS offline SearchView ✅ @ 7c9d3ab).
5. **Small wins** — mostly DONE @ 243d99f: duplicate-event ✅ · week
   numbers ✅ (`ui.show_week_numbers`) · Timer CSV ✅ · observance checkbox ✅
   (found + fixed the pydantic-drops-`observance.enabled` bug, DEVQA Q2
   closed). Agenda view ✅ @ 3b89809 · iOS `/heartbeat` ✅ @ 7c9d3ab (endpoint
   already existed server-side). **The approved queue is fully shipped.**
6. ✅ **Convolution #1** — DONE @ 243d99f: ThinkingView + EngineChain live in
   `Views/ThinkingView.swift` (byte-identical move, simulator build green).
7. ✅ **Confirm-create gate (DEVQA Q9, ruled 2026-09-07)** — DONE: an
   interrogative create ("should i add yoga to my calendar tomorrow?") is
   neither executed nor silently dropped. Step 4 holds the validated intent
   (`interrogative_create_asks_first`), the orchestrator answers
   `parse: "confirm_create"` with ready-to-POST `proposal` bodies, and
   `POST /voice/confirm` accepts (replay-safe) or declines (files the memory
   record as rejected). Gated on `supports_confirm`, so old clients are
   unchanged. Mac Add/No box + iOS "Add this?" alert; **the phone needs a
   reinstall** to get it. FEATURES.md + ENGINE.md carry the detail.

## Working notes

- Two Claude sessions share this project's checkouts; re-read a `main`-checkout
  file immediately before editing (uncommitted work has no git net).
- Never run an audit/replay beside another model-loading job (spaCy/torch
  segfault). RAM is near full — LLM replays are serial.
