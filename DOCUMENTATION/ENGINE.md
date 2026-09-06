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
Two halves, both live. **Serialization**: `run_transcript` holds a lock — one
command at a time, FIFO, so concurrent requests cannot race the anaphora
context; the wait shows honestly in the trace total. **Coalescing**:
`engine.coalesce(texts, budget)` combines queued inputs into `("…")and("…")`
batches under `engine.coalesce_max_tokens` (a wrapper step 2 splits
deterministically), overflow running sequentially — used by the pending-retry
loop, where server-side inputs genuinely pile up; the phone's bracket batching
flows through step 2 as before.

### 1 · transcript (`transcript.py` · trace stage `vocab` · tests `test_engine_flow.py`)
Reads `raw_text`; writes `text`, `corrections`, `needs_edit`, `ignored`.
Stop-word strip → trivial-transcript filter (a false start is ignored AND not
remembered) → `apply_vocab` (confident fixes, phonetic matching) → the
confidence gate: doubtful words with `engine.confirm_transcript` on and a
client that declared `supports_edit` become a `needs_edit` response — the
client shows an editor and resubmits with `edited_from`. A changed word is
learned as a vocab alias (`learn_from_edit`); an untouched resubmit counts a
confirmation (`confirm_unchanged`, counters beside the vocab in
`transcript_confirms.json` — never inside the hand-curated vocab), and at 2
confirmations the word is whitelisted and never asked about again. The Mac
sends `supports_edit`, shows the dialog (`ask_transcript_edit`, real-click
tested) and has the Settings toggle; the iOS sheet is queued. *Status: live.*

### 2 · segment (`segment.py` · trace `rule` · tests `test_engine_segment.py`)
Reads `text`; writes fresh `items` (id, kind, text only). Deterministic
delimiters first (brackets, coalescing wrapper, configured separator), LLM
segmentation only after they found nothing, **biased to under-split** — a
wrong merge gets two more chances (steps 3 and 6); a wrong split of "meeting
with Tal and Ravid" is immediate garbage. This is the pipeline's single point
of failure and carries the densest tests. *Status: live — deterministic splits
plus self-skipping LLM segmentation (a compound hint in the words is required
before the model is consulted; a split producing a fragment is refused). Gate:
`engine_stage_check --stage segment`.*

### 3 · decompose (`decompose.py` · trace `rule` · tests `test_engine_decompose.py`)
Reads `items`; may replace an item with sub-items (`item_N-M`, depth ≤ 2) and
fill `item.slots`. Two times joined by "and" → two events; task lists ride
`intent/list_split.py` (verb handed down, idioms respected); counts ride
`intent/quantity.py` — "buy 5 apples" is ONE task of (apples, 5). *Status: live —
deterministic shapes plus a self-skipping LLM pass for wordier double-times
(two clock-time mentions required; ranges excluded). Gate:
`engine_stage_check --stage decompose`.*

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

### 5 · generate (`generate.py` · trace `rule`/`llm` · tests `test_engine_generate.py` + integration)
Owns ALL text→intent conversion. **`FastRule`** (`engine/fastrule.py`) is the
deterministic rule parser + its abstention gates + a threshold, as a
self-contained SELECTIVE CLASSIFIER: `FastRule(threshold).run(prompt)` returns
a commit-or-abstain verdict. Two live instances, tuned per population:
`FastRule(0.80)` is the conservative whole-command fast track (deep is its
net); `FastRule(0.60, compound_gates=False)` is the aggressive per-fragment
instance the deep track calls after decompose (a fragment is atomic, so the
compound gates are off; crosscheck is its net). Its abstention gates:
strong-compound (two-request wording), mixed-mode (create+edit/query),
interrogative-create (a question producing a create), generic-target (a
mutation aimed at a bare noun). `fast_propose` (whole input) is the thin
adapter over `FastRule(0.80)`; `run` works per item: FastRule first (~50ms,
free), LLM fills gaps
from the rule parser's partial analysis, or parses from scratch — grounded on
the item's own words, never another item's. An item parsing into several
intents is expanded into sub-items, one intent each (per-item attribution is
the row-75 fix). Slots from decomposition land on the intent (`quantity`).
`AssistantError` propagates: the orchestrator owns offline queueing.

Two deterministic fallbacks close the honest-failure ladder (both pinned in
`test_engine_generate.py`): **task_fallback** (run 12) — a task-kind item
never parses to nothing; the item text IS the task. **event_fallback**
(cycle 5) — an event-kind item that still parses to unknown after the
event-kind retry becomes a default-titled event ONLY when the words
literally contain event/reminder/appointment (that noun is the title) AND
the date recognizer grounds a date or clock time in them; nothing is ever
invented, no match stays unknown.

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
not-found second opinion (the last still lives in commit until this stage
absorbs it). *Status: live. Foreground: extraction + diff + loop-back run
pre-commit, budget honoured, exhaustion admitted in the reply. Background
(fast track): verify token issued, placeholder titles renamed (minor), a
missing ask parsed and committed additively (minor), an extra row reported as
major — ADVISORY unless `self_check_apply` is on, because the old always-on
verifier measurably proposed far more than it fixed (78 proposals, 0 fixes,
2026-08-28). **One-tap revert (done 2026-09-04):** when a removal *is* applied,
`_remove_extra` captures the row first and the correction carries
`revert: [{kind, body}]` — ready-to-POST `/events`/`/todos` bodies. An applied
change is also echoed to the Mac HUD as a late `verify` step (the foreground
trace's bus listener is still attached), carrying the same specs; the review
panel's `_RevertBar` and the iOS banner re-POST them to undo. Gate:
`engine_stage_check --stage crosscheck`.*

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

## The thinking panel renders by brain version (merge requirement)

`assistant/trace.py` holds `BRAIN_VERSION` (currently `"engine-v2"`), `CHAINS`
— the single source of truth for how a brain's chain of thought reads, as
ordered `(stage, short-label)` pairs matching the explorer diagram — and
`STAGE_INFO`, the in-depth "what this step is" copy behind each slot's ⓘ,
mirroring the explorer page's per-stage aria-labels. The engine stamps
`BRAIN_VERSION` onto every response (`resp["brain"]`, which iOS reads) and every
trace-bus payload (`result["brain"]`, which the HUD reads), and
`thinking_panel._ResultCard`/`finish` stashes it as `self._brain`.

**Both panels render this chain as a scaffold** (done as of 2026-09-04). A
`_ChainRail` (Mac `thinking_panel.py`) and the mirrored `chainRail` (iOS
`ThinkingView`) draw the `CHAINS[brain]` slots as a compact rail above the live
timeline, naming the version and lighting each slot done / active / skipped as
the live steps arrive (mapped to slots by stage, in order — the two `rule`
slots and any self-skipped stage resolve correctly). Each slot carries an ⓘ
that reveals `STAGE_INFO[brain][label]` as a tooltip (Mac) / popover (iOS). The
raw per-step timeline still shows below, with its real titles and timings — the
rail is the map, the steps the journey.

Keeping it honest: bump `BRAIN_VERSION` whenever the pipeline's shape changes so
an old trace still renders in its old format; add the new slots' `STAGE_INFO`.
`test_panel_agreement` fails the build if a `CHAINS` slot has no `STAGE_INFO`
entry, and `test_stage_info_parity` fails if the iOS Swift copy
(`EngineChain.scaffold`) drifts from the Python source. A future claim-check
can also assert the explorer diagram's step labels equal `CHAINS["engine-v2"]`.
