# Metrics for scoring a dataset run

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

## Findings so far (1000-row partial build, in progress)

- Count-correct: simple 91%, medium 89%, **complex 28%**.
- event+task compounds are the worst compound kind (15% correct) and the
  failure mode is specific: dropping the event, not the task.
- Cross-event date collapse is only ~3% of event+event failures — the
  75% failure rate there is mostly something else, not the bug already
  fixed.
- Hybrid parse path is the weakest (57% vs rule 75%, llm 77%).

These numbers are from a partial build and will move once the full
3000-row run finishes — treat them as directional, not final. Re-run
`python -m scripts.score_dataset_run <db>` for current numbers.

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
