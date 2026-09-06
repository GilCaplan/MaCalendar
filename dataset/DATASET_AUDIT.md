# Dataset conventions audit — 2026-09-06

The HWU-64-derived ground truth encodes its source corpus' worldview; our
product deliberately differs. Scoring those rows raw penalizes the engine for
being right — an honest "lists live as tags here" loses to inventing a list.
This audit found every such class, quantified it, and added a **versioned
overrides layer** so the scorer reports a product-adjusted number *next to*
the raw one. **Raw `count_ok` never changed** — every logged run stays
comparable.

## Method (held-out discipline)

Rules were mined from the **dev region only** (`tier_rank ≤ 600`), then
applied to all 3000 rows **mechanically** — no held-out row was ever read.
Generator: `scripts/audit_dataset_conventions.py` →
`dataset/inputs/convention_overrides.json` (140 rows, 4.7%). The inputs file
stays frozen; the overrides file is the second layer and is regenerated only
by rerunning the script.

## Classes found

| class | dev (≤600) | all | product convention it encodes | treatment |
|---|---|---|---|---|
| `remind_half` | 16 | 69 | "remind me to VERB" may be a task even when the source called it an event (clock time ⇒ event stays, per cycle 1) | `split_flexible`: total ≥ 2 creations, kinds free |
| `standing_alert` | 5 | 30 | no standing-alert object; "notify me when X" gets an honest reply (or a dated reminder when datable) | `noop_ok` / `half_flexible` in compounds |
| `list_create_bare` | 6 | 21 | no list objects — Today/General + tags; "open a new list" with no items has nothing to create | `noop_ok` |
| `placeholder` | 8 | 17 | `xxx` / `{client name}` / `<insert …>` can't be executed faithfully; the clean half still must happen | `half_flexible` (compounds), `noop_ok` (bare set) |
| `truncated` | 1 | 3 | "Set reminder on calendar for" — a clarify is correct | `noop_ok` |

Treatments (implemented in `scripts/score_dataset_run.py` as `count_ok_adj`):
**noop_ok** — pass on (0 creations, 0 mutations) *or* (≥1 clean creation);
**half_flexible** — pass on ≥1 clean creation; **split_flexible** — pass on
total ≥ 2, per-kind split dropped. The item-verb distinction matters:
"add cereal to my shopping list" is a task + Groceries tag and stays strictly
scored — only verbs acting on *the list itself* qualify as bare.

## The no-op check (Gil's addition)

For `query` rows the raw scorer only asserted *zero creations*. The adjusted
verdict now also requires **zero mutations** (`delete_*`, `update_*`,
`complete_*`): a query must not change the stores. First run caught a real
defect — the deep track turned *"Is my appointment to the dentist still on
for tomorrow morning?"* into `update_event(match_title="dentist", …)`.
Against the empty scratch store that no-ops; against a real calendar it
**moves the appointment**. Logged as a bug candidate in HYPOTHESES.md.

## First rescore under the adjusted ruler (no new engine runs)

| run | raw | adjusted | up-flips | down-flips |
|---|---|---|---|---|
| row 9 epoch baseline (mixed) | 78.4% | **81.2%** | 8 (5 remind_half, 2 placeholder, 1 list_bare) | 1 (dentist query-mutation) |
| row 8 all-deep A/B | 79.2% | 81.2% | 8 | 2 (dentist + one more query-mutation) |

Every overridden row in the mixed slice passes adjusted — i.e. on this slice
the convention gap is now **fully accounted for**, and the adjusted number
measures only what the engine actually gets wrong.

The first published version of this table scored a misidentified db as
"row 8" (actually run 2's — caught within the hour by the archive salvage's
parse_path fingerprints). The true row-8 db rescores at exactly its logged
79.2 raw. Archive manifests (`dataset/runs/*/manifest.json`) now record
identity at archive time so no analysis ever again infers which db is
which.

## Follow-ups

- `_prf` and `field_quality` don't yet read the overrides — an overridden
  row's precision/recall still assumes the raw expectation. Small, do next.
- `loop_log.csv` gained an `adj_pct` column, backfilled for ALL runs 1–9:
  the whole Friday epoch's scratch dbs were salvaged from tmp into
  `dataset/runs/` during the archive build (`scripts/rescore_runs.py --write`
  redoes the backfill whenever a metric changes).
- The dentist bug (queries emitting mutations) — deterministic guard in the
  engine, next cycle.
