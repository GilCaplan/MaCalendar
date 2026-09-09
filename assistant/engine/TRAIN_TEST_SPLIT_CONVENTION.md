# Train / test splits — the engine-wide convention

**This is the rule for EVERY stage's dataset, not just FastRule's.** Moved up
here from `fastrule/datasets/SPLIT.md` (Gil, 2026-09-08) when a second stage
needed it, because a leakage rule that lives inside one stage's folder reads as
that stage's local habit instead of the standard it is.

Two things are general and binding — the no-mining rule in the next section, and
splitting by **pattern family** rather than by row. Everything after that is
FastRule's *instantiation*: its numbers, its buckets, its generator. A new
stage copies the mechanism and records its own numbers.

| stage | dataset | split unit | test rows | mechanism |
|---|---|---|---|---|
| **FastRule** | `fastrule_7200.jsonl` | pattern family | 2,400 | stratified 80/20 + `force_split: "test"` |
| **decompose_validate** | `datasets/generated.jsonl` | pattern family | 840 (21 families) | growth: the 268 original families are train **by construction**; 49 grown families split 40/60, stratified by nuance |
| **Segmentation** | `datasets/generated.jsonl` | pattern family | sealed half (289 rows) | — |

**Why an existing dataset cannot simply be cut in half.** decompose_validate's
795 rows were all fitted against — the resolver was tuned until it scored 100%
on them — so a split carved out of them now would be measuring memorisation, not
generalisation. The only honest sealed half is built from material the code has
never seen. That is what `force_split: "test"` is for, and it is why growth is
the way to get a test set rather than division.

---

# FastRule's instantiation: the 80/20 split

**Two pools make up `split == "test"` now (2026-09-07 growth): the original
stratified 80/20's test slice (1,200 rows, 86 families) and a newer
force-split-only pool grown on top of it (1,200 rows, 101 families — see
"Growing test-only: force_split" below). Both are equally eval-only. The
rule in the next section applies to `split == "test"` as a whole, without
exception for which pool a row came from.**

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

## The stratified pool's numbers (unchanged by the 2026-09-07 growth)

| | rows | families |
|---|---:|---:|
| train | 4,800 (80.0%) | 331 |
| test | 1,200 (20.0%) | 86 |
| **stratified pool total** | **6,000** | **417** |

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

## Growing test-only: `force_split` (Gil, 2026-09-07)

The goal: widen test's **unseen-wording** coverage without touching train at
all, and without perturbing the stratified 80/20's own hash-based bucket
membership for any of the original 417 families. Mechanism
(`scripts/gen_fastrule_dataset.py`):

1. A family may declare `"force_split": "test"` in `simple_patterns.json` /
   `complex_patterns.json`. Everything else about it — `template`,
   `action`/`atomic`/`events`/`tasks` (or the simple-tier action defaults),
   `event_label_sources`/`task_label_sources`, `fixed_slots`, `flags` — works
   exactly like any other family; only the split assignment differs.
2. `main()` partitions each tier's families into `free` (no `force_split`)
   and `forced` **before either pool is touched**. `free` is handed to
   `build_tier()` — the ORIGINAL stratified path, completely unmodified,
   operating on the identical input set it always did (a `force_split`
   family passed to `build_tier()` is a hard assertion failure, not a silent
   no-op — see `_init_family`/`build_tier`'s assert). `stratified_split()`
   never even sees a forced family, so it cannot shift any (tier, action)
   bucket's hash ordering or 80/20 arithmetic for the original families.
3. `forced` is handed to a new function, `build_forced_test()`: every family
   in it is assigned `split = "test"` directly (asserted — the function
   only supports `force_split: "test"` today), given its own row quota via
   the same `distribute_quota()` largest-remainder mechanism (capacity-aware,
   same as always), and generated with the same `gen_family_rows()` +
   labelling pipeline as everything else.
4. `build_forced_test()` runs **after** `build_tier()` completes for both
   tiers, and only ever *appends* to `rows`/`global_seen`. A brand-new
   family's candidate text colliding with an existing row (astronomically
   unlikely given the filler banks' cardinality, but the dedup logic doesn't
   assume it away) always loses to the existing row — the new family just
   tries its next candidate — so existing rows never even have visibility
   into the forced pool's existence, let alone react to it.
5. The forced-test row target is its own budget (`SIMPLE_FORCE_TEST_TOTAL =
   400`, `COMPLEX_FORCE_TEST_TOTAL = 800`), **added on top of**
   `SIMPLE_TOTAL`/`COMPLEX_TOTAL`, never carved out of them — that's what
   keeps train exactly 4,800 rather than being diluted.

**101 new families this round** (45 simple + 56 complex), all
`force_split: "test"`, targeting the tier/action/strata mix the original
417 already cover (all 8 simple actions, all 9 complex actions including a
new `propose_confirm` nuance — see DATASET.md) plus genuinely new wording
skeletons throughout — the whole point being wider unseen-wording coverage,
not more rows behind the same templates.

**Train-invariance, verified two ways:**

- **Structurally**: `build_tier()`'s input (`free`) and every function it
  calls are byte-for-byte the same code path operating on the same data as
  before `force_split` existed; nothing about the forced pool's existence
  reaches it.
- **Empirically**: a from-scratch run of `build_tier()` against ONLY the
  157 simple + 260 complex original (non-`force_split`) families reproduces
  a train set whose **full-row JSON** (sorted, hashed) and **sorted
  `text`-only** hashes both match the actual `split == "train"` subset of
  `fastrule_7200.jsonl` exactly — 4,800 rows, identical ids, identical
  `expect` blocks, identical everything. `main()` also asserts this at
  generation time: `train_n` must equal the original `4,800` exactly, and
  no `force_split` family may produce a single `train` row (both are hard
  `ValueError`s, not warnings).

## The combined numbers (stratified pool + forced-test pool)

| | rows | families |
|---|---:|---:|
| train | 4,800 (66.7%) | 331 |
| test | 2,400 (33.3%) | 187 |
| **total** | **7,200** | **518** |

Test's 2,400 = the original stratified 1,200 + the new forced 1,200. The
stratified pool's OWN internal ratio is still exactly 80/20 (verified
above) — the overall dataset's ratio moved to roughly 2:1 only because an
entirely new, additive, test-only pool was grown alongside it; no row that
used to be train became test, or vice versa.

## Regenerating

`python -m scripts.gen_fastrule_dataset` rebuilds the whole dataset from
scratch every time — it is not a stored assignment, it's a pure function of
the bank files + `SEED`. Adding a new NON-force_split family to
`banks/simple_patterns.json` or `banks/complex_patterns.json` **may
reshuffle which existing (non-forced) families land in train vs test** (the
stable-hash ordering is a function of the full stratified-pool bucket
membership), so treat a stratified-pool bank edit as "regenerate and re-read
`fastrule_7200.jsonl`," not "append a delta." Adding a new `force_split:
"test"` family carries none of that risk — by construction it can only ever
add test rows and can only ever change which OTHER forced families' quotas
absorb the largest-remainder rounding, never anything about `free` families
or train. `SEED` in `scripts/gen_fastrule_dataset.py` is the only knob that
changes the *stratified* split deterministically; changing it is a
deliberate act, noted here and in `DATASET.md`, not a routine operation.
