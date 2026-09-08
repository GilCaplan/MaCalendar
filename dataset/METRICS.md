# The metrics — organised by what they measure

_Restructured 2026-09-07. There is no longer one flat list: each COMPONENT is
measured at its own granularity, which is the whole point of stage isolation
— the engine's headline can only say THAT something is wrong; a component
measured on its own says WHAT._

**The pattern is the same everywhere** (Gil's framing): recall = "of the
things that should have happened, how many did", precision = "of what we
did, how much was right" — asked at the level of a classifier decision, a
component's job, an item, or a slot. Three metrics deliberately break that
pattern, each because precision/recall cannot express something we care
about: **harm** (errors are not equal), the **knew-vs-accident split**
(measures the mechanism, not the outcome), and **latency**.

## Level 1 — the ENGINE (`engine_dataset_compare` → `score_dataset_run`)

| metric | question |
|---|---|
| count-correctness (raw + product-adjusted) | did the command produce the right number of events/tasks? |
| item-level precision / recall / F1 | of expected items, how many exist; of created items, how many were asked for |
| missing-half | on a two-part command that failed, WHICH half vanished |
| date-collapse | did two dated things land on one date |
| garbage titles | a title the transcript never justified |
| field quality / when-correct | are the matched items' contents grounded in what was said |
| label-correctness | category accuracy + macro P/R/F1 (events), tag micro-P/R/F1 (tasks) |
| parse path + latency (p50/p95) | which track answered, and how slowly |

## Level 2 — FASTRULE, the atomic-item executor (`scripts/fastrule_shape.py`)

Measured by what it is FOR, not how busy it is. **Primary** (Gil, Q13):

| metric | question |
|---|---|
| **atomic handle-rate** | of single-item commands, how many did it act on (coverage) |
| **correct-on-handled** | of what it acted on, how much was right (precision) |
| date correctness | of committed creates with a resolvable date phrase, how many landed right |
| time correctness | of committed events with an explicit spoken time, how many matched |
| invention rate | events where NO time was said — did it invent one anyway |
| **harm** | severity-weighted cost of wrong commits: delete=4, update/complete=2, create=1, query=0 — because a wrong delete and a wrong title are not the same failure |

**Diagnostic** (non-atomic rows — the engine decides, so no target):
covered (all asks present, acceptable) · **half-executed** (an ask missing —
the real defect) · deferred, split into "knew it was compound" vs "by
accident", because only the first survives as FastRule improves.

## Level 3 — the CLASSIFIERS (`scripts/fit_route_models.py`, `atomicity_board.py`)

Accuracy + per-class precision/recall/F1 + macro-F1 for atomicity,
operation and kind — reported per dataset, and for atomicity as three
separate predictors (rules alone / model alone / the wired layer), because
that is what revealed the layer scoring worse than the model inside it.
Error COUNTS not just rates: a wrong "compound" costs a slow path, a wrong
"atomic" half-executes a command.

## Level 4 — SPEAKERS (`scripts/persona_board.py`)

Per-persona boards plus the SPREAD between best and worst — the spread is
the finding. Plus the vocabulary-vs-phrasing ablation, which showed the
engine is tuned to sentence shapes (7–29 pt) and not to vocabulary (0–3 pt).

## Level 5 — REAL USAGE (`scripts/weekly_review.py`) — the outer gate

Flag rate and accuracy on Gil's actual commands, test traffic excluded.
**This one outranks the others**: it is the only instrument measuring real
speech, and it currently disagrees with them sharply (50% vs an 85%
benchmark). A cycle that moves a benchmark while this stays flat has not
helped anybody.

---


`scripts/score_dataset_run.py` scores a `dummy_<N>.db` (or diffs two of
them) without any hand-written ground truth. That's only possible because of
where the ground truth actually comes from — read that before the metric
list, since it's what decides which of these travel to other data and which
don't.

## Where the ground truth comes from

This dataset has no `expect` field the way `scripts/audit_assistant.py`'s
hand-written corpus does. Instead, every "complex" prompt was *built* by
joining two real utterances of a known kind (`fetch_hwu64_sample.py`,
`_compose_complex`) — event+event, task+task, or event+task. That
construction is itself a claim about what should happen: an event+event
compound should produce at least 2 events, whether or not a human ever
wrote that down. "Simple"/"medium" prompts get a weaker version of the same
idea from their source intent (`set`/`createoradd` should create something;
`query`/`remove` should not create something *instead of* querying or
deleting).

**This means about half of these metrics are dataset-specific — they need
`hwu64_sample.json`'s provenance (scenario/intent/complexity per prompt) to
know what "correct" means — and about half are fully general, computed only
from `actions_json`/timing with no provenance at all.** Marked below. The
general ones are the ones actually reusable once real usage exists to score.

## The metrics

| Metric | Deterministic? | Needs provenance? | What it catches |
|---|---|---|---|
| **Count-correctness** (does a compound produce the right minimum event/task count) | Yes | **Yes** — dataset-only | The core one. Directly targets the multi-date and duplicate-task bugs found earlier this session. |
| **event+task missing-half** (which side gets dropped: event, task, both, neither) | Yes | **Yes** — dataset-only | Finer than pass/fail — tells you *what* to fix. Found: 68% of failures drop the event specifically, not a random mix. |
| **Cross-event date collapse** (2+ events in one command landing on the identical date+time) | Yes | No — general | Would catch the exact bug fixed earlier this session, on ANY input with 2+ events, synthetic or real. |
| **Garbage titles** (a title that's just a leaked connective — "then", "also") | Yes (proxy, not true quality) | No — general | Real defect, found live on first real row inspected. |
| **Parse-path distribution, latency percentiles** | Yes | No — general | Standard operational metrics, sliceable by any grouping available (complexity, parse path, whatever). |
| **Correctness by parse path** | Yes | **Yes** — dataset-only | Needs count-correctness as an input. Found: hybrid underperforms both pure rule and pure LLM paths (57% vs 75%/77%) — worth its own investigation. |
| **Determinism** (same prompt, replayed, same action sequence?) | Yes to compute, but confounded | No — general | Real result: 75% raw, ~85% once context-memory-dependent cases (2 of 5 diffs, isolated replay vs in-sequence) are set aside. Needs replaying at the *same sequence position* to measure cleanly, not in isolation. |
| **Title/description "quality"** | No — no ground truth exists | — | Deliberately not built. Would need an LLM-judge model that isn't the system under test (avoids self-grading bias), and the same "prove it can fail before trusting it" discipline the self-check itself has never fully had. Noted as future work, not attempted here. |

## Findings (full 3000-row build, 2026-09-03)

Report: `output/dummy_3000.score.md`. The partial-build numbers held.

- Count-correct: simple 92%, medium 88%, **complex 29%** — overall 70%.
- event+task compounds are the worst compound kind (17% correct) and the
  failure mode is specific: of 275 failures, 229 dropped the event, 20 the
  task, 26 both — 83% are a dropped *event*.
- event+event is barely better (20% correct), and cross-event date collapse
  is only 4% of those rows — the failure mode is mostly something other
  than the bug already fixed.
- Hybrid parse path is the weakest (58% vs rule 74%, llm 78%) across
  951/1372/677 rows respectively.

One data note: every join in the build and scorer is keyed on
`COALESCE(NULLIF(raw_transcript,''), transcript)` — the verbatim input —
because the pipeline can rewrite a transcript before recording it ("Open
calendar.  Set event." is stored as "Open calendar"), and a text join on
the stored form leaves such rows permanently unmatchable (the build's
resume replayed one forever before this was keyed right).

## Reusing this once something goes to production

The general-purpose metrics (date collapse, garbage titles, latency/parse-
path, determinism) need no changes — point `score_db()` at any db with an
`examples` table shaped like this project's command memory (transcript,
actions_json, parse_path, timing) and they compute the same way, real
traffic or synthetic.

The provenance-dependent ones (count-correctness, missing-half, correctness-
by-path) need a stand-in for `hwu64_sample.json` — i.e., *something* that
says what a given real command should produce. For real production traffic
that doesn't exist by construction the way it does here, so this would mean
either: human-labelled review verdicts (the existing `feedback`/
`correction_json` columns in the real command memory already carry some of
this), or restricting these specific metrics to synthetic/constructed test
traffic the way this dataset already is.


## 6 · Label-correctness (added 2026-09-07, Gil)

On MATCHED items only (an unmatched item is layer-1's failure): **events —
category accuracy + macro precision/recall/F1** over classes (single-label;
macro so a rare category's systematic miss stays visible); **tasks — micro
precision/recall/F1 over tag sets** (multi-label; an expected-empty set
counts). Ground truth exists where labels are by construction — the FastRule
6,000 against its canonical `banks/categories_fixture.json`, loaded via
MACALENDAR_CATEGORIES so personal config never enters scoring. The real pool
carries no label ground truth (hand-labeling it is an open ruling for Gil).
Implemented by the FS1 scorer; reported on FS boards like every metric —
named, sliced, never bare.
