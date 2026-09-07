# Models in the stack

Three models. All of them run on this machine; none of them is reached over the
internet. This file is the canonical answer to "how many models, which ones,
what does each one do" — `DOCUMENTATION/ARTIFACT_BUILDER.md` and the artifacts
cite it rather than restating it.

| # | Model | Size | Where it runs | What it decides |
|---|-------|------|---------------|-----------------|
| 1 | **Whisper `base`** | 74 M params | Apple GPU via `mlx-whisper`, or CPU via `faster-whisper` int8 | sound → words |
| 2 | **spaCy `en_core_web_sm`** | 13 MB | CPU, in-process | part of speech, named entities, sentence roots |
| 3 | **Llama 3.1 8B** (`llama3.1:8b`) | 8 B params, Q4 | Ollama on `localhost:11434` | meaning, and the judgement of meaning |

Set in `config.example.yaml` under `mlx_whisper.model`, hardcoded as
`spacy.load("en_core_web_sm")` in the rule parser, and `ollama.model`.

There is **no embedding model**. Retrieval of past commands is lexical —
0.6 × Jaccard over word sets + 0.4 × `SequenceMatcher` ratio. That was a
deliberate choice (a fourth model to load, for a corpus of a few hundred short
strings) and it is one of the things the harness should re-examine.

There is also **no model doing classification**. Category colours and task tags
are keyword scoring plus the personal vocabulary — see
`assistant/actions/calendar/categories.py` and `assistant/actions/todo/tagging.py`.
Handing labelling to model 3 is open work, not shipped behaviour.

## The six jobs model 3 does

One model, one loaded copy (`keep_alive: -1`, warmed at startup), six different
prompts. They are genuinely different tasks and it is worth keeping them
straight:

| Job | Entry point | When | Blocking? |
|-----|-------------|------|-----------|
| **Cold parse** | `IntentParser.parse` | rules scored below 0.85, or produced nothing | yes |
| **Hybrid fill** | `parse_with_context` | rules got some slots; the LLM is given them and fills the rest | yes |
| **Self-check (rule path)** | `verify_fast_path_async` | after a rule-path record is already written | no — daemon thread |
| **Self-check (any path)** | `verify_actions_async` | after execution, on **every** command, with memory in the prompt | no — daemon thread |
| **Title naming** | `fix_title_async` | the parse produced a placeholder title like the bare keyword | yes, briefly |
| **Escalation re-parse** | `parse`, again | an action matched nothing (`TargetNotFound`) — e.g. "complete X" where X isn't a task | yes |

Only three of those are on the path between speaking and seeing the event.
The self-checks run after the record exists, which is why their latency is not
a user-facing cost — the correction, when there is one, arrives as an edit.

Structured output is enforced with Ollama's `format` JSON schema on the parse
calls (`_call_ollama(sys, user, schema)`); the verify calls use a looser
free-JSON call (`_call_ollama_verify`) and are parsed defensively.

`ollama.verify_model` exists so the self-check can be pointed at a *stronger*
model than the parser — it is `null` today, meaning both jobs use 8B. If the
harness ever shows the self-check is the weak link, that is the knob.

## The three routing classifiers (`assistant/intent/classifier.py`)

All three share one `LogisticModel` object — features, fit, predict-with-
margin, per-class P/R/F1 — because the same regression previously existed in
four copies. **Fitted** with scikit-learn (a DEV dependency only: L-BFGS, L2,
class-balanced); **inference** is a hand-written dot product over JSON
weights, so the shipped engine imports no ML stack and stays inside
FastRule's ~50ms budget. Weights are fitted on TRAIN halves only and
committed like any other constant.

| model | decides | test-half macro-F1 | where it runs |
|---|---|---|---|
| **atomicity** | one item, or several? | 87.6 (compound recall 87.9%) | layer 0 — it LEADS, the rule gates override for their own catches |
| operation | new / edit / remove / complete / query | 72.4 | the routing fallthrough, behind margin floors |
| kind | event or task | 85.7 | the routing fallthrough, behind margin floors |

Measured lesson: the atomicity model was wired as a last resort and the
layer containing it scored WORSE than the model alone (compound recall 68.8%
vs 83.4%) — good pieces wired timidly perform like bad pieces.

## The kind scorer — the stack's first TRAINED component (K1, status: experiment)

A 16-weight logistic regression for the event-vs-task kind decision
(Q8, Gil-approved 2026-09-07). Not a neural model: the features are the
segment stage's own regexes (clock, dated, remindish, occasion, encounter,
list-words, …) plus a few lexical cues, the output is P(kind = event), and
the fit is `scripts/kind_classifier_experiment.py`'s pure-python gradient
descent — no sklearn, no runtime dependency, weights printed and versioned
like any other constant. Measured: **99.0% dev / 98.5% held-out**
kind-accuracy vs the deterministic chain's 71.5/67.8 on 1,495 labeled
create rows.

**Status: experiment passed, NOT yet wired.** K2 (a registered deep cycle)
wires it into segment as the arbiter ONLY where the pinned convention rules
are silent — Gil's rulings stay authoritative; the scorer replaces the blind
fallthrough. K1b first retrains on the full 2,699-row train pool. Until K2
lands, ENGINE.md and FEATURES.md intentionally do not list it (they document
the shipped engine).

## Approach — why it is shaped this way

**Rules first, model second, model again as an auditor.** The rule parser is
not a fallback for when the LLM is down; it is the fast path, and it handles
the majority of commands with no model call at all. The 8B model exists for the
sentences the rules cannot score confidently — and, separately, as a reviewer
of everything the rules *did* score confidently, because a confident rule parse
is exactly where a silent error hides. See the `verify_fast_path` comment in
`config.example.yaml` for the measurement that put it there, and
`self_check_apply` for the measurement that stopped it from writing.

**Small models, chosen for the machine.** Whisper `base` and an 8B parser are
both several steps down from what is available. The constraint is that the whole
thing has to sit resident on a laptop that is also being used for other work —
`keep_alive: -1` means the 8B model never unloads, and that is only tolerable
because it is 8B.

**One brain.** Both the Mac GUI and the iPhone POST to `assistant.api`; neither
runs a parser of its own. Everything above happens exactly once, in one process,
regardless of which device was spoken to.
