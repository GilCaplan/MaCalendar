# The iteration protocol (coarse-to-fine, one component at a time)

The loop that improves the engine against the verification dataset. Its whole
purpose is to keep every gain **attributable**: change one component, measure
on a slice sized to the gain you expect, and only believe a win the held-out
set confirms.

## The subset ladder — reused fixed slices, so deltas compare across cycles

| Rung | ranks | n | ~wall-clock (8B, serial) | one flipped prompt = | use it for |
|---|---|---|---|---|---|
| **dev-fast** | 1–150 | 150 | ~22 min | 0.67 pt | rapid single-component cycles |
| **dev-full** | 1–600 | 600 | ~90 min | 0.17 pt | confirm a fast-slice win before believing it |
| **held-out** | 601–3000 | 2400 | ~7 h | 0.04 pt | periodic generalisation — NEVER mined |

Tier ordering interleaves complexity, so every contiguous slice is naturally
stratified (dev-fast is ~48/50/52 simple/medium/complex). The slices are
**fixed**: always the same ranks, so a cycle's delta is comparable to the
last cycle's, not confounded by a different sample.

    python -m scripts.engine_dataset_compare --max-rank 150            # dev-fast
    python -m scripts.engine_dataset_compare --max-rank 600            # dev-full
    python -m scripts.engine_dataset_compare --min-rank 601            # held-out

`triage.json` now reports `by_complexity` and `by_compound_kind` old-vs-new
deltas, so a cycle that targets one component sees THAT component move, not
just the overall blur.

## One cycle

1. **Cluster** the dev failures by the stage that caused each (model-free;
   `dev_failure_piles.json` is the template). Rank the piles.
2. **Pick ONE pile** — the largest, or the one whose fix is cleanest. Change
   **only that stage's internals** (contracts frozen). No bundling: two fixes
   in one cycle make the delta unattributable.
3. **Measure dev-fast.** Read the delta on the TARGETED slice
   (`by_compound_kind`/`by_complexity`), not only the headline.
4. **Graduate or drop:**
   - targeted-slice delta clearly positive AND overall non-negative →
     **graduate**: confirm on dev-full before believing.
   - flat or negative → drop/refine the fix; the pile stays open.
5. Unit-test every fix in its stage's file; the corpus smoke
   (`audit_assistant --limit 20`) is the regression floor.

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
