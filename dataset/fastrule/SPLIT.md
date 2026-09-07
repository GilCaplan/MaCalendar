# The 80/20 split — how it's built, and the rule that protects it

## TEST RESULTS ARE NEVER USED TO IMPROVE FASTRULE

**This is the load-bearing rule of this dataset. Read it before you score
anything against `split == "test"`.**

- Scoring on `split == "test"` reports **aggregates only** — pass rate,
  per-metric summaries. No per-row output, no failing texts, no printed
  transcripts.
- No test row is ever printed, mined, or eyeballed to write a regex,
  feature, threshold, or gate. Not "just to understand the failure" — the
  understanding has to come from the train half.
- Hypotheses about what to change come from the **train half's failures
  exclusively**.
- A disappointing test aggregate means **more train-half mining**, never a
  look at which test rows failed. If the test number is bad, go back to
  train, find the analogous failure pattern there, fix it, and only then
  re-run test to see if it moved.
- Any scoring/verification tooling built against this dataset must default
  to this behavior: gate per-row detail behind an explicit
  `--i-know-this-is-train-only` style flag (or simply never implement it for
  `split == "test"`), so the safe path is the default path, not an
  opt-out.

This mirrors the main verification dataset's held-out region
(`dataset/DATASET.md`: "sealed: measured, never used to pick a fix, so its
delta is the honest generalisation claim") — same discipline, same reason:
the moment a human (or an agent) reads a test-set failure and reacts to it,
the test set has been folded into training and stops measuring
generalization.

## Why split by PATTERN FAMILY, not by row

A row-level random 80/20 split would put near-identical siblings of the same
template on both sides (same wording skeleton, different filler words) —
FastRule would then be "tested" on sentences that are trivial paraphrases of
what it just trained on. That measures memorization of a template, not
generalization to a new way of phrasing a command.

Instead, the split unit is the **pattern family** (the skeleton — e.g.
`c_and_et_1`: `"book {event_title} {date} at {time} and remind me to
{task_title2}"`). Every row generated from a family goes entirely to one
side. **A family present in `test` never appears in `train`, and vice
versa** — enforced mechanically by `scripts/gen_fastrule_dataset.py`
(`stratified_split()`), and checked again as a hard assertion right before
the file is written (`leaked families` must be empty or the script raises).

This means the test set measures something real: can FastRule handle a
**wording pattern it never saw**, not just new names/dates plugged into a
pattern it memorized.

## Stratification

A pure global 80/20 over 417 families could, by chance, leave some `(tier,
action)` combination — say `complex` × `query` — entirely on one side. That
would silently stop measuring that slice. So the split is stratified by
`(tier, action)`:

1. Group all families by `(tier, action)` — 8 buckets for `simple` (no
   `mixed` there; simple rows are single-intent by construction) and 9 for
   `complex` (adds `mixed`, which most compounds land in).
2. Within each bucket, order families by a stable hash of
   `(SEED, "split", tier, action, family)` — deterministic, independent of
   JSON file order or `PYTHONHASHSEED`.
3. Take `max(1, round(0.2 * n))` families as `test`, capped at `n - 1` so a
   bucket never loses its train side either. A singleton bucket (`n == 1`)
   stays entirely in `train` — there's no way to split one family without
   losing coverage on one side, and train is where mining happens anyway.
4. Everything else in the bucket is `train`.

Verified on the current generation (`python -m scripts.gen_fastrule_dataset
--no-write` prints this): **every one of the 17 `(tier, action)` buckets has
at least one family in both `train` and `test`** — the smallest are
`complex × query` (1 family each side) and `complex × delete_todo` /
`complex × update_todo` / `complex × complete_todo` (2 train / 1 test each).
Nothing scores as "action X, complex tier" in test without a train
counterpart to have been mined against first.

## The actual numbers (this generation, SEED = "fastrule-6000-v1")

| | rows | families |
|---|---:|---:|
| train | 4,800 (80.0%) | 331 |
| test | 1,200 (20.0%) | 86 |
| **total** | **6,000** | **417** |

Simple tier: 1,600 train / 400 test (of 2,000). Complex tier: 3,200 train /
800 test (of 4,000). Both exact — the split target is computed independently
per tier from `TRAIN_FRAC = 0.8`, then family row-quotas are distributed
with a largest-remainder method *within* each split (not estimated and
rounded after the fact), so the achieved split is exact rather than merely
"close to 80/20 ±1%." (The ±1% tolerance is enforced as a hard check in the
generator regardless — see `main()`'s verification block — in case a future
edit to the banks changes family capacities enough to force a deficit
redistribution.)

Leaked families (present in both splits): **0** — asserted by the generator
on every run; the script refuses to write the file if this is ever nonzero.

## Regenerating

`python -m scripts.gen_fastrule_dataset` rebuilds the split from scratch
every time — it is not a stored assignment, it's a pure function of the bank
files + `SEED`. Adding a new family to `banks/simple_patterns.json` or
`banks/complex_patterns.json` **may reshuffle which existing families land
in train vs test** (the stable-hash ordering is a function of the full
bucket membership), so treat a bank edit as "regenerate and re-read
`fastrule_6000.jsonl`," not "append a delta." `SEED` in
`scripts/gen_fastrule_dataset.py` is the only knob that changes the split
deterministically; changing it is a deliberate act, noted here and in
`DATASET.md`, not a routine operation.
