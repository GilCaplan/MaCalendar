# The Engine — stage contracts

This is the document you open when a stage needs fixing. It defines what each
stage of the deep track receives and must hand on. **These contracts are
frozen**: they were designed once, before implementation, and do not change at
any point of development. Fixing a weak stage means improving its internals
toward the best version of itself — inside its own module, against its own
tests — never reshaping `EngineState`, touching the orchestrator, or another
stage. `tests/unit/test_engine_contracts.py` enforces every claim on this
page; if it goes red you are changing a contract, not fixing a stage.

## The shape

```
text ─▶ 0 intake      orchestrator   queue + coalescing
     ─▶ 1 transcript  transcript.py  vocabulary repair + confidence gate
     ─▶ 2 segment     segment.py     split into typed items
     ─▶ 3 decompose   decompose.py   items that are several things, or one × N
     ─▶ 4 validate    validate.py    named format rules, text repair, observance
     ─▶ 5 generate    generate.py    items → intents (rules first, LLM for gaps)
     ─▶ 4′ validate.run_objects      field-level named rules on the intents
     ─▶   commit      orchestrator   execute via the action registry
     ─▶ 7 label       label.py       category / tag read-back
     ─▶ 6 crosscheck  crosscheck.py  raw text vs. produced objects, loop-back
```

Every command runs the deep track. The **fast track** is the same machinery
short-circuited: when `generate.fast_propose` finds the rule parser confident
about the whole input (≥ `RULE_THRESHOLD`, no missing slots), items are built
straight from its intents, committed instantly, and the deep track's
cross-check runs behind the answer. `parse_path` says which happened:
`"fast"` or `"deep"` (plus `"error"`, `"ignored"`, `"needs_edit"`).

Stages exchange **only** the `EngineState` (`assistant/engine/state.py`) and
each exposes exactly one public entry point, `run(state, cfg) -> state`
(step 4 additionally `run_objects`, step 5 additionally `fast_propose`). No
stage imports another stage's internals. `validate` also exports named
*readers* (`relative_dates`, `at_times`, `spoken_times`, `end_is_exclusive`,
`is_placeholder_title`…) — shared vocabulary other stages may call, never a
channel to mutate state through.

## The state contract

| Field | Written by | Read by | Meaning |
|---|---|---|---|
| `raw_text`, `source`, `current_view`, `supports_edit`, `mode` | intake | all | read-only after intake; `mode` is `foreground` or `background` (fast-track verify pass) |
| `text` | transcript | all later | the working transcript (stop words stripped, vocab applied) |
| `corrections` | transcript | response | vocab fixes, client shape |
| `needs_edit` | transcript | orchestrator | doubtful words; non-empty ⇒ the gate fired, nothing executes |
| `ignored` | transcript | orchestrator | false start: not parsed, not executed, **not remembered** |
| `items` | segment (create), decompose (split), generate (fill/expand) | validate, commit, label, crosscheck | the item tree; ids `item_1`, `item_1-2` |
| `item.blocked` | validate | commit | refusal reason; a blocked item is reported, never silently dropped |
| `item.intent = None` after generation | validate (drop rules) | commit | dropped as parser noise; traced, not messaged |
| `executed`, `messages`, `refresh` | commit | label, crosscheck, response | what actually ran, per item |
| `findings`, `retries`, `mistakes` | crosscheck | orchestrator | mismatches, loop-back budget, context for retried stages |
| `fixes` | any stage via `state.add_fix` | trace, audit | every named-rule correction |
| `trace`, `parse_path`, `llm_ms`, `rule_confidence`, `memory_id`, `verify_token`, `pending_id` | orchestrator + stages as noted | response | bookkeeping |

## The stages

### 0 · intake (orchestrator — `assistant/engine/__init__.py`)
Queueing and coalescing. Commands arriving mid-run queue; before the next run
they are coalesced up to `engine.coalesce_max_tokens` as `("…")and("…")` —
a wrapper step 2 splits deterministically — and overflow runs sequentially.
*Status: coalescing not yet built (sequencing phase 4); bracket batching from
the phone already flows through step 2.*

### 1 · transcript (`transcript.py` · trace stage `vocab` · tests `test_engine_flow.py`)
Reads `raw_text`; writes `text`, `corrections`, `needs_edit`, `ignored`.
Stop-word strip → trivial-transcript filter (a false start is ignored AND not
remembered) → `apply_vocab` (confident fixes, phonetic matching) → the
confidence gate: doubtful words with `engine.confirm_transcript` on and a
client that declared `supports_edit` become a `needs_edit` response — the
client shows an editor, resubmits, and the saved edit is learned (alias +
phonetic key). *Status: gate live; the learning loop and the confirm-twice
whitelist are phase 5.*

### 2 · segment (`segment.py` · trace `rule` · tests `test_engine_segment.py`)
Reads `text`; writes fresh `items` (id, kind, text only). Deterministic
delimiters first (brackets, coalescing wrapper, configured separator), LLM
segmentation only after they found nothing, **biased to under-split** — a
wrong merge gets two more chances (steps 3 and 6); a wrong split of "meeting
with Tal and Ravid" is immediate garbage. This is the pipeline's single point
of failure and carries the densest tests. *Status: deterministic splits live;
LLM segmentation is this stage's build gate.*

### 3 · decompose (`decompose.py` · trace `rule` · tests `test_engine_decompose.py`)
Reads `items`; may replace an item with sub-items (`item_N-M`, depth ≤ 2) and
fill `item.slots`. Two times joined by "and" → two events; task lists ride
`intent/list_split.py` (verb handed down, idioms respected); counts ride
`intent/quantity.py` — "buy 5 apples" is ONE task of (apples, 5). *Status:
deterministic decomposition live; LLM pass for ambiguous items at its gate.*

### 4 · validate (`validate.py` · trace `validate` · tests `test_engine_validate.py`)
Two passes, both contract:
- `run` (pre-generation, item level): format hygiene, text repair of garbled
  fragments.
- `run_objects` (post-generation, field level): the NAMED rules, in fixed
  order — `anaphor_guard`, `relative_date_pin`, `past_date_bump`,
  `recurrence_words`, `until_exclusive`, `weekly_start_day`,
  `at_time_is_start`, `morning_title_guard`, `bare_hour_pm`,
  `junk_event_drop`, `due_date_pin`, `cadence_round_and_announce` — and the
  **observance gate**: an AI-created one-off event inside Shabbat/yom tov
  (sundown-bounded) must be leyning / a meal / davening; on a fast day a meal
  must not be booked before the fast ends (Yom Kippur: the fast wins). Blocked
  items get `item.blocked` and an honest refusal in the reply. Manual
  edits/additions are never gated; series skipping stays in
  `db._skip_for_observance`. Allowed on any computation failure.
Every applied rule lands in `state.fixes` under its name and in the trace.

### 5 · generate (`generate.py` · trace `rule`/`llm` · tests `test_engine_flow.py` + integration)
Owns ALL text→intent conversion. `fast_propose` (whole input) is the fast
track; `run` works per item: rule parser first (~50ms, free), LLM fills gaps
from the rule parser's partial analysis, or parses from scratch — grounded on
the item's own words, never another item's. An item parsing into several
intents is expanded into sub-items, one intent each (per-item attribution is
the row-75 fix). Slots from decomposition land on the intent (`quantity`).
`AssistantError` propagates: the orchestrator owns offline queueing.

### commit (orchestrator)
The only place the engine touches the database, via the existing action
classes. Blocked items → explained refusal; `unknown` → honest "didn't
understand"; `TargetNotFound` → the not-found message (empty slots are the
right answer for a delete; guessing is not). Records `(kind, row_id, action,
idx)` per item for the command memory and the 24h corrected/rejected hooks.

### 7 · label (`label.py` · trace `validate`)
Categories/colours and task tags are applied by the actions themselves
(`categories.py`, `tagging.py`); this stage reads the results back onto
`item.labels` so reply, trace and audit can see them. The two-level hierarchy
(row 58) lands here.

### 6 · crosscheck (`crosscheck.py` · trace `verify` · gate: extraction + blame tests)
1. EXTRACT, don't judge: the LLM lists items the RAW text mentions
   (schema-constrained) — small models extract far better than they
   self-evaluate.
2. COMPARE deterministically: diff against produced objects → `missing` /
   `extra` / `wrong_fields` findings.
3. BLAME by mismatch type via the fixed `BLAME` map (missing/extra → segment,
   wrong_fields → generate, format → validate; generate when ambiguous). The
   model never picks the stage.
Loop-back: re-run from the blamed stage with the mistake in that stage's
prompt context; ≤ `MAX_REENTRIES` (3) per command; on exhaustion commit the
best attempt, say so, mark the memory record uncertain. On the fast track this
stage patches the committed answer — **tiered**: additive fixes silent,
destructive corrections visible with one-tap revert. It owns what used to be
four bolt-ons: the background verify, both placeholder-title fixers, the
not-found second opinion. *Status: contract placeholder — records nothing,
loops nothing, patches nothing. Its build (sequencing phase 3) is gated on
`scripts/engine_stage_check.py --stage crosscheck`.*

## The response contract (unchanged from the old brain)

`message, actions, refresh ("events"|"todos"|"both"|""), parse, transcript,
original_transcript, corrections, trace, uncertain_words` + optional
`memory_id, verify_token, pending_id, needs_edit`. Trace stage names stay
`stt/vocab/rule/memory/llm/validate/execute/verify/done/error` — the iOS
timeline and the HUD key off them. LLM offline ⇒ pending queue + honest
message; trivial ⇒ `parse: "ignored"` with nothing recorded.

## Config knobs (mirror into config.example.yaml)

`engine.confirm_transcript` (step 1 gate), `engine.reconcile`
(`always|uncertain`, step 6), `engine.fast_track` (`on|off` escape hatch),
`engine.coalesce_max_tokens` (step 0). The routing threshold stays
`RULE_THRESHOLD` in `intent/rule_parser.py`; `rule_confidence` is recorded on
every command so it can finally be calibrated from outcomes (row 57).

## Fixing a stage

1. Reproduce in the stage's own test file, or via
   `scripts/engine_stage_check.py --stage <name>` (Ollama-guarded, scratch
   stores, `source: "test"`).
2. Improve the stage's internals until its tests and stage check pass.
3. Run the audit; read the per-stage lines, not just the headline.
4. If you believe the *contract* is wrong: that is a design change — take it
   to TASKS.md, don't slip it into a fix.
