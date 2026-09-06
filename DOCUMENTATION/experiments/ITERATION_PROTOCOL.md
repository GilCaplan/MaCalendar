# The iteration protocol (coarse-to-fine, one component at a time)

This is the loop that improves the engine against the verification dataset,
run as a **supervised-ML loop**: the dataset is the ground truth, the metrics
are the score, and each "prediction" is a whole `.db` instance — the
events/tasks the system produced from an input. The twist over a classic
classifier is that the label is a *structured instance*, not one class, and the
input is real speech, so the metrics decompose the error rather than giving one
accuracy.

Two things hold the loop honest:

- **The big-picture design is frozen — only component *implementations*
  change.** We fine-tune and re-implement the internals of a stage; we do not
  reshape the pipeline, the stage contracts, or `EngineState`. A design change
  is a separate decision (TASKS.md), never smuggled into a tuning cycle.
- **Every gain must be attributable AND understood.** Form a hypothesis about
  one component, change only that, measure on a slice sized to the gain you
  expect, read *why* the score moved (not just that it did), and only believe a
  win a larger slice confirms.

**Never run the full 3000 as the working loop.** Start on the smallest slice
that is rich enough to show the failure you're chasing (dev-fast, ranks 1–250,
~80 min, naturally stratified across simple/medium/complex), and upsize only as
gains slow. The full set is an occasional generalisation check — never a cycle.

## The subset ladder — reused fixed slices, so deltas compare across cycles

| Rung | ranks | n | ~wall-clock (8B, serial) | one flipped prompt = | use it for |
|---|---|---|---|---|---|
| **dev-fast** | 1–250 | 250 | ~80 min | 0.40 pt | rapid single-component cycles |
| **dev-full** | 1–600 | 600 | ~3¼ h | 0.17 pt | confirm a fast-slice win before believing it |
| **held-out** | 601–3000 | 2400 | ~13 h | 0.04 pt | periodic generalisation — NEVER mined |

Tier ordering interleaves complexity, so every contiguous slice is naturally
stratified (the working 250 ≈ balanced across simple/medium/complex). The
slices are **fixed**: always the same ranks, so a cycle's delta is comparable to
the last cycle's, not confounded by a different sample.

    python -m scripts.engine_dataset_compare --limit 0 --max-rank 250  # dev-fast (~80 min)
    python -m scripts.engine_dataset_compare --limit 0 --max-rank 600  # dev-full
    python -m scripts.engine_dataset_compare --limit 0 --min-rank 601  # held-out

`--limit 0` disables the script's default 150-row cap so the rank slice is taken
whole — without it, `--max-rank 600` still returns only the first 150 rows.

**Small-delta cycles run their verification twice** (replay is ~75%
deterministic, so ±1–2 rows are noise): when the predicted effect is under
~4 rows, measure twice and read the pair. **If dev-fast looks overfitted**
(Gil, 2026-09-05): resample — take a fresh same-size slice of history prompts
(e.g. ranks 251–500), run the next rounds there, and mark the slice in
loop_log.csv so scores are never silently mixed. **F1 joins count-correctness**
as a headline pair: recall (nothing missed) vs precision (nothing invented),
item-level micro — see DATASET.md's metric table.

**The harness replays history, not "now"** (Gil, 2026-09-05): each row runs
frozen at its recorded `ts` (freezegun), and observance gating stands down via
`MACALENDAR_OBSERVANCE=0` — the dataset has no concept of Shabbat, and a
Friday replay penalised the engine for correctly refusing (cycle 2). This
reset the measurement epoch on 2026-09-05: loop_log.csv rows before/after that
boundary are not comparable. Standing policies: **merge the loop branch into
`main` every few graduated cycles**, and **product questions go to DEVQA.md**
(root) for Gil's inline answers — never blocking prompts.

`triage.json` now reports `by_complexity` and `by_compound_kind` old-vs-new
deltas, so a cycle that targets one component sees THAT component move, not
just the overall blur.

## One cycle — a hypothesis, tested

Every cycle is an experiment with a **written prediction**, so the result can be
compared against what you expected. That comparison — not the raw number — is
what teaches the next step.

1. **Cluster** the dev failures by the stage that caused each (model-free;
   `dev_failure_piles.json` is the template). Rank the piles, and **read a
   handful of the actual failing rows** — understand the failure mode, don't
   just count it. A metric is a pointer to a behaviour; the behaviour is the
   thing.
2. **State the hypothesis before touching code:** which ONE component, what
   change, and which metric+slice you expect it to move, in which direction and
   roughly how much — e.g. *"loosening segment's under-split on 'X and Y at T'
   should raise count-correct on event+task; I expect +3–5 pt there, flat
   elsewhere."* Write it into `RESULTS.md` as the cycle's prediction.
   **`dataset/HYPOTHESES.md` is the ranked queue these come from** — take the
   top unblocked entry, and after every verification rerun feed the fresh
   failures back into it and re-rank (prune every ~3 cycles). A
   product-convention question in an entry is Gil's call, never assumed.
3. **Change only that stage's internals** (contracts frozen). No bundling of
   *improvements*: two experiments in one cycle make the delta — and the
   hypothesis test — unattributable. **Bugs are exempt (Gil, 2026-09-05): fix
   as many as found, whenever found** — a bug is objectively wrong, not an
   experiment. Each bug still gets its ledger row, and one that lands between
   a cycle's two measurements is named in the verdict so its share of the
   delta isn't silently credited to the hypothesis.
4. **Measure dev-fast.** Read the delta on the TARGETED slice
   (`by_compound_kind`/`by_complexity`) *and the rows behind it*, not the
   headline alone.
5. **Compare to the prediction:** did the expected metric move as predicted?
   Did anything *unexpected* move — a regression elsewhere, or a novel gain you
   didn't anticipate? Both are findings. Record prediction vs. actual vs. your
   interpretation in `RESULTS.md`; that record is the input to the next
   hypothesis, and it is how a wrong hypothesis still teaches something.
6. **Graduate or drop:**
   - targeted-slice delta clearly positive AND overall non-negative →
     **graduate**: confirm on dev-full (and periodically held-out) before
     believing it.
   - flat or negative → the hypothesis or the fix was wrong; write down *why* it
     didn't behave as expected, drop/refine, and the pile stays open.
7. Unit-test every fix in its stage's file; the corpus smoke
   (`audit_assistant --limit 20`) is the regression floor.

**Every measurement run also appends one row to `dataset/loop_log.csv`** —
baseline, fix rerun, upsize confirm, held-out check alike: started/finished
timestamps, duration, commit, slice, and **all five metrics with their
breakdowns** — count-correct (overall/complexity/compound-kind),
missing-half, latency p50/p95, parse-path mix (n_deep/n_fast + per-path
correctness), e+e date-collapse, garbage titles — plus a one-line summary.
The COMPLETE reports (per-slice tables, every failing row, triage) are
preserved per run in `DOCUMENTATION/experiments/engine_compare/<label>/`.
**And every change ships a ledger row in `dataset/loop_changes.csv`** (cycle,
component/stage, kind: bugfix/improvement/convention/feature/metric/process,
description, commit) — each cycle report to Gil includes the tally: totals +
breakdown per component, this cycle and cumulative. `RESULTS.md` is the prose understanding; the csv is the machine-
readable trajectory, so the whole improvement process can be plotted
(metric-vs-time / metric-vs-cycle) when it concludes. A run that isn't logged
there didn't happen.

## Coarse-to-fine: when to climb the ladder

Start on **dev-fast** — early fixes move many rows and a noisy slice still
shows them. When two cycles in a row move fewer than ~2 rows on dev-fast, the
big-delta phase for that component is over: switch that component's primary
measure to **dev-full**, and periodically spend a **held-out** run for the
conclusive, generalisation-checked number. The full 3000 stays a deliberate,
occasional job — not every cycle.

## Parallelism — what this machine allows

One local 8B model, and RAM is near full: a second `ollama serve` (~5.8 GB)
would swap. So **LLM replays run serially.** What runs in parallel is the
model-free half — clustering the last run's failures, writing the next stage
fix, unit tests, report-writing — alongside the one measurement in flight.
That is the real parallelism here, and it is already the working pattern.

If a machine with more RAM is available later, two `ollama serve` on separate
ports would allow either sharding one run to ~halve wall-clock, or a true
concurrent A/B of two variants — coordinate first with any session running
tier audits so the two do not contend.


## The runs archive (added 2026-09-06 — after two misidentified-db retractions)

Every measurement run auto-archives its scratch (engine_run.db + calendar.db
+ trace_bus, gzipped) to `dataset/runs/<name>/` with a `manifest.json`
recording identity: row count, **parse-path fingerprint**, source path,
md5s, loop run number. Rules:

- **Never analyze an unlabeled scratch db.** Verify identity against the
  manifest (parse_paths) before any cross-run join — inferring it later
  published a wrong deep-rescue figure (0/21; truth 7/21) and a wrong
  "row 8 = 75.6" retraction in a single night.
- When a metric is added or fixed, `python -m scripts.rescore_runs --write`
  replays the CURRENT scorer over every archive, backfills loop_log's
  backfillable columns (today: `adj_pct`), and prints drift against
  as-logged values. As-logged numbers are never rewritten.
- Scoring reports **raw and product-adjusted** count-correct together: the
  conventions-overrides layer (`dataset/inputs/convention_overrides.json`,
  see `dataset/DATASET_AUDIT.md`) feeds `count_ok_adj`; queries additionally
  must mutate nothing to pass adjusted. Raw stays the cross-run comparable
  number; adjusted is the product-true one.
- Empirical noise floor (cycle 3 verdict): overall dev-fast deltas under
  **~1.5 pt are noise** — judge a cycle by its targeted slice, and measure
  twice when the predicted effect is under ~4 rows.

## Report the FULL board, every run (Gil, 2026-09-06)

A cycle close reports EVERY metric — count raw+adjusted, complexity tiers,
compound kinds, missing-half, date-collapse, garbage titles, P/R/F1, field
quality (+when-correct, +difficulty-weighted), parse-path correctness and
counts, latency p50/p95, query-mutation violations — in chat and in
RESULTS.md alike. Never a highlights-only summary: a metric that moved
against you and went unreported is a broken instrument next cycle.
`python -m scripts.run_board <run>` prints the full table from loop_log.csv
(vs the epoch baseline and the previous same-slice run).

## Paired-track cycles (Gil, 2026-09-07)

The fast (rule) and deep (7-stage) tracks are parallel systems; a cycle MAY
carry TWO hypotheses — one per track — since a run costs the same and every
row is scored with its parse path. Rules that keep attribution honest:

- Pairable: a rule-parser INTERNAL change (parse better, stay fast) + a
  deep-stage INTERNAL change. Each verdict is read off its own parse-path
  slice, with its own prediction registered up front.
- NEVER pairable: routing changes (fast gates, thresholds, track selection)
  — they move rows between populations and confound both verdicts; routing
  rides alone (C6 moved 5 rows fast→deep).
- Rows that CHANGED parse path between the runs are excluded from both
  verdicts and reported as their own count.
- If both hypotheses miss their predicted bands, rerun each alone.
- Bugs remain exempt and ride any cycle.
