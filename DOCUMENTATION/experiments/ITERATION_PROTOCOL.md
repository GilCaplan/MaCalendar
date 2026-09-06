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
3. **Change only that stage's internals** (contracts frozen). No bundling: two
   fixes in one cycle make the delta — and the hypothesis test — unattributable.
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
timestamps, duration, commit, slice, every metric column, and a one-line
summary. `RESULTS.md` is the prose understanding; the csv is the machine-
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
