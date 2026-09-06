# The self-improving assistant — how the AI system gets better on its own

The assistant's brain (speech → text → understanding → events and tasks in the
database) improves through an **autonomous, hypothesis-driven loop**: it
measures itself against a fixed ground truth, reads its own failures, predicts
what one change will do, makes that change, and checks the prediction — over
and over, with every step recorded. A human (Gil) rules on *what the product
should do*; the loop owns the mechanics of getting there.

This page is the map. The working files it describes:

| file | what it holds |
|---|---|
| [`dataset/DATASET.md`](../dataset/DATASET.md) | the ground truth: 3,000 real voice utterances + constructed compounds, the subsets, the metric definitions |
| [`DOCUMENTATION/experiments/ITERATION_PROTOCOL.md`](experiments/ITERATION_PROTOCOL.md) | the loop's rules — the canonical protocol |
| [`dataset/HYPOTHESES.md`](../dataset/HYPOTHESES.md) | the ranked experiment queue (the future) |
| [`dataset/RESULTS.md`](../dataset/RESULTS.md) | every cycle's prediction vs. actual, and the interpretation (the why) |
| [`dataset/loop_log.csv`](../dataset/loop_log.csv) | one row per measurement run — timestamps, duration, commit, every metric incl. `adj_pct` (product-adjusted count-correct) — the plottable trajectory |
| [`dataset/loop_changes.csv`](../dataset/loop_changes.csv) | every change shipped, per component: bugfix / improvement / convention / metric |
| [`dataset/runs/`](../dataset/runs/) | every run's scratch, archived with an identity manifest — `scripts/rescore_runs.py --write` recomputes the whole history when a metric changes |
| [`convention_overrides.json`](../dataset/inputs/convention_overrides.json) | the product-conventions layer behind the adjusted score (raw never changes) — see [`DATASET_AUDIT.md`](../dataset/DATASET_AUDIT.md) |
| [`DEVQA.md`](../DEVQA.md) | async product questions for Gil, and the log of his rulings |

## The framing: a classic ML problem, with a twist

- **Ground truth** — utterances whose correct outcome is known *by
  construction*: an `event+task` compound ("book gym and remind me to buy
  milk") must produce ≥1 event and ≥1 task. No hand labelling.
- **The model** — the engine: an 8-stage pipeline with **frozen contracts**.
  We never reshape the design; we re-implement the internals of one stage at a
  time — tuning "parameters" that happen to be code.
- **The score** — not one number but a decomposition of error:
  - **count-correctness** — did the right *number* of things appear (by
    complexity tier and compound kind, plus which half went missing);
  - **precision / recall / F1** — inventing vs. missing, balanced (creating
    anything in response to "remove the meeting" is pure invention);
  - **field quality** — are the *contents* right, weighted by what matters:
    the **when** is paramount (objective — the words pin it), titles need
    only be short-and-similar (subjective — scored as similarity), tags are
    closed-set classification over the registry's finite classes,
    location/description must merely not be invented. Components the words
    don't pin are *uncovered, never guessed*, and complex prompts weigh more
    than simple ones;
  - **operational** — latency percentiles, fast/deep path mix.

## One cycle

    measure   a small, complexity-rich slice (~250 rows), each row replayed
              at its RECORDED timestamp — the dataset is a history
       ↓
    understand read the actual failing rows, not the score; cluster them by
              the guilty stage
       ↓
    hypothesize take the top of the ranked queue and write the prediction
              FIRST: "changing X should move metric Y on slice Z by ~N"
       ↓
    change    ONE component's internals per hypothesis (bugs are exempt —
              a bug is objectively wrong, fix any number, each logged)
       ↓
    verify    re-measure, compare actual vs. predicted — a miss that gets
              explained teaches as much as a hit
       ↓
    record    RESULTS.md (why) · loop_log.csv (scores) · loop_changes.csv
              (what) — then re-rank the queue and go again

**Prediction-first is the heart.** A number that merely went up proves
nothing; a number that moved *as predicted* proves the system is understood.

## The honesty machinery

- **Graduation**: a win on the tuning slice only counts after it holds on
  rows the loop never tuned against (the untuned sub-slice is quoted
  separately); the held-out 2,400 stays sealed for the final claim.
- **Noise floor**: replays are ~75% deterministic, so overall deltas under
  ~1.5 pt are noise — cycles are judged on their targeted rows.
- **Fair measurement**: replays freeze each row at its own timestamp and park
  the Shabbat/observance rules (a user-controllable flag), so the engine is
  never penalised for being correctly observant of things the dataset doesn't
  model. The ruler itself is auditable and has been fixed as often as the
  engine.
- **Known ceiling**: some dataset rows are *accepted convention losses*
  (product decisions, garbled sources) — recorded, so "diminishing returns"
  is judged against the achievable ceiling, not 100%.
- **Every claim is metric + slice + commit.** Always.

## The division of labour, and the exit

The loop measures, diagnoses, fixes and verifies autonomously. **Product
meaning stays human**: conventions ("is a dated reminder an event?") go to
`DEVQA.md` for Gil's ruling and become permanent. Every few graduated cycles
the work merges into `main`, so the live assistant keeps inheriting the gains.
The loop upsizes to bigger slices when the small one stops moving, resamples
if it suspects overfitting, and stops at diminishing returns — at which point
`loop_log.csv` plots the whole journey.
