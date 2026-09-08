# STATUS — where we are

> Naming note (2026-09-08): `crosscheck.py` is now
> `assistant/engine/llmjudge/llmjudge.py` and `generate.py` is
> `assistant/engine/fastrule/objects.py`. Older entries below use the
> old names; the chain is in `assistant/engine/ARCHITECTURE.md`.

**One-screen reference. A fresh conversation reads this first, then CLAUDE.md.**
Keep it current and short; details live in the files it points to.

_Updated 2026-09-08 — sprint cycle A parts 1 and 2 closed and banked; part 3
(the never-measured LLM lane) is in flight._

**The loop is self-driving.** A cycle ends by STARTING THE NEXT ONE — banking
the result in `dataset/RESULTS.md` is the report, and the next prediction is
registered in the same breath (CLAUDE.md, and the rule in
`ITERATION_PROTOCOL.md`). Implementation fixes and cleanups between cycles
need no permission. Stop only for a DESIGN decision, or when three cycles
running move nothing past the noise floor.

**Where the sprint is (`DOCUMENTATION/experiments/SPRINT_PROPOSAL.md`):**

1. **Cycle A part 1 — the atomizer, DONE** (a222f60). Segment could only split
   on delimiters the PHONE inserts, so it split nothing in 4,920 rows of
   speech. It now splits at the clause boundary the coordination check was
   already computing and discarding. Boundary-clean 5.8%→41.7% and 0%→43.2%;
   complex count-correct 60.4%→75.1% and 49.8%→70.5%; all six personas up
   4.5–12.6 pt; ~25–30% fewer model calls.
2. **Cycle A part 2 — the kind decision, DONE** (bb2b80c). Part 1 promoted it
   to the binding constraint: splitting exposes second items, and each needs a
   kind. `_TASK_RE` recognised only CREATE-shaped to-do wording, so completing,
   editing and un-listing a task all fell through to "event". Held-out kind
   accuracy 59.4%→73.7%, 79.1%→87.7%, 93.8%→97.8%. New instrument:
   `scripts/kind_board.py`.
3. **Cycle A part 3 — IN FLIGHT.** The atomizer board's default lane runs with
   the model OFF, so the deep track's actual splitting ability has never been
   measured. Prediction registered in RESULTS.md. Run:
   `python -m scripts.atomizer_board --split test --dataset B --llm`.

**The next constraint is already named by part 2's board:** 1-ask rows are at
98.4% count-correct, 2-ask rows at 44.1% (UNDER 55.9%). Compounds are the
whole remaining gap. Part 3 decides whether the fix belongs in coverage (more
compounds reaching the model) or in the prompt/model itself.

**Two lessons this sprint keeps re-teaching, worth reading before starting:**

- **Fixing a stage exposes the next one.** Part 1's splitter made the kind
  decision the ceiling; part 2's kind fix routed hundreds of items into
  `_split_tasks` for the first time and surfaced its tearing. Expect the
  measurement after a win to look worse somewhere, and check downstream first.
- **Look at the rows, not the headline.** Part 1's first cut over-split 139
  atomic rows; part 2's first cut destroyed words. Both were caught by reading
  failures, and neither by the top-line number, which had improved.

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

**THE NUMBER THAT MATTERS MOST (2026-09-07):** the sealed benchmark reads
85% while Gil's REAL usage reads 50% (20 real commands, flag rate 50%,
`scripts/weekly_review.py` — now filtered to exclude our own test traffic,
which had been inflating it to 83%). The benchmarks are not lying; they
measure clean prompts. Real speech is rambling multi-event dictation with
transcript damage, which no dataset we own contains. **A self-driven loop
started against the current boards would optimise clean prompts and could
leave that 50% untouched.** The real-speech dataset is the fix, and it is
queued.

**PERSONA FINDING:** the engine is tuned to sentence SHAPES, not vocabulary
— swapping content nouns moves the classifiers 0–3 pt, swapping phrasing
moves them 7–29 pt. Atomic handle-rate 72.2% for the persona who talks like
Gil vs 33.9% for a terse student. Cause: `^`-anchored operation features.

**LOOP STATE (2026-09-07).** Stage isolation closed; whole-engine cycles
resume. FastRule: 13 batches, atomic handle-rate 49.7 → 58.4% and
half-executed compounds 40 → 31 on its own test half; the atomicity model
now LEADS layer 0 (compound recall 68.8 → 87.9%). Engine: the deferral
contract (REFUSAL / STRUCTURE / INCAPACITY) is live, FastRule's verdict
travels forward to segment, background-verify no longer fires in
measurement runs, 137 duplicated lines gone. Last engine read: a PARTIAL
sealed-test eval (163 of 300 rows) at raw 85% / adjusted 83%, complex 69%,
fast-path 94% — encouraging but partial, and its latency was inflated by
the background-verify bug now fixed. **NEXT: a clean full run on the sealed
300 for a trustworthy board, then cycles resume against it.**

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

**LAYER 0 (atomicity) — F16–F18b landed on `fast-lane`, 2026-09-07.**
`python -m scripts.atomicity_board` is the new instrument: the binary
"one item or several" board, three predictors (rules / model / the wired
layer) × two datasets, both error kinds as COUNTS because the cost is
asymmetric. **B-test (FastRule 7,200 test half): layer accuracy 88.0 →
93.5%, compound recall 68.8 → 87.9%, half-executable misses 195 → 76.
A-test (verification pool, real wordings): 93.3 → 97.9%, recall 85.0 →
99.1%, misses 34 → 2.** Downstream `fastrule_shape` B-test: handle rate
53.5 → 54.2%, defer 77.1 → 78.2%, actual half-executions 26 → 20.
**Open for Gil: DEVQA Q13** — is a fast commit on a compound a routing
violation when it produces exactly the right records? The answer moves the
non-atomic defer rate between 78.2% and 95.6%.

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
**Fast-sandbox lane (live 2026-09-07)** — `python -m assistant.engine.fastrule.experiments.fast_sandbox`
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
