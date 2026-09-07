# Engine architecture audit — 2026-09-07

_Read-only audit. No code was changed. Every "unused" claim below was verified
by grep across `assistant/`, `scripts/`, `tests/` (excluding `retired/`);
claims that depend on a measurement we do not have are marked
**[UNMEASURED]**, and recommendations that can only be confirmed by a
whole-engine run are marked **[needs full-engine run]** — those are blocked
while cycles are paused (`STAGE_ISOLATION_PLAN.md`)._

**The lens:** FastRule is the ATOMIC-ITEM EXECUTOR (one event or task,
deterministic, ~50 ms, defers anything else); the DEEP SYSTEM is the ATOMIZER
(break the command into atomic items, then create each one, then check the
result against what was actually said).

**Line numbers are as of `21d6133`** (plus, for `assistant/intent/rule_parser.py`
and `assistant/intent/classifier.py`, whatever the F19 batch had in the working
tree at the time — those two files were being edited concurrently, so refs
below line ~168 in `rule_parser.py` may have shifted by ~18 lines. Every
finding was verified by symbol, not by offset; grep the named symbol if a
number looks wrong.)

---

## 0 · The headline

The architecture Gil settled on is **written down in three places and built in
one and a half.** `FASTRULE2_DESIGN.md` §"division of labor" and
`DEEPSYSTEM_DESIGN.md` §3.3/§5.1 both say the deep track calls
`FastRule(0.60)` per fragment and routes its abstain-reason back to decompose.
That code does not exist. `FastRule` is instantiated **exactly once** in
production:

```
assistant/engine/generate.py:96-99   FastRule(RULE_THRESHOLD).run(...)   # the 0.80 front door
```
(verified: `grep -rn "FastRule("` → the only other hits are `tests/unit/test_fastrule.py`,
`scripts/fastrule6k.py`, `scripts/fastrule_shape.py`.)

The per-item path instead **re-implements FastRule's commit predicate inline
and omits both gate layers**:

```python
# assistant/engine/generate.py:157-173  (_parse_item)
rr = rule_parser.analyze(item.text, current_view=state.current_view)
is_fragment = item.text.strip() != state.text.strip()
bar = SUBITEM_RULE_THRESHOLD if is_fragment else RULE_THRESHOLD
if rr.confidence >= bar and not rr.missing_slots and rr.intents:
    return rr.intents          # <- no Atomicity, no Gatekeeper
```

Everything in §2 below flows from that one gap. It is the difference between
"FastRule is the executor" and "FastRule is a fast path that the slow path
quietly duplicates without its safety rails."

---

## 1 · REMOVE / RETIRE

Ordered by confidence-that-it-is-dead × cost.

### 1.1 — 129 lines of verbatim duplicated code in the orchestrator · **certain**

`assistant/engine/__init__.py` defines `_create_spec`, `_confirm_proposal` and
`_confirm_response` **twice**, byte-identical:

| symbol | first def | second def (the one that wins) |
|---|---|---|
| `_create_spec` | line 638 | line 775 |
| `_confirm_proposal` | line 712 | line 849 |
| `_confirm_response` | line 733 | line 870 |

Verified: `diff <(sed -n '638,766p') <(sed -n '775,903p')` → identical; present
in `HEAD` (`git show HEAD:… | grep -c "^def _create_spec"` → 2), working tree
clean. The section header comment `# The confirm-create gate (DEVQA Q9) …` is
also duplicated (lines 634-636 and 771-773).

**Cost:** every future edit to the confirm-create proposal shape has a 50%
chance of landing in the dead copy and silently doing nothing — the exact
failure mode `FASTRULE2_DESIGN.md` names for the F10 slot patch ("landed
inside the wrong sub-branch and silently did nothing until a probe caught
it"). Delete lines 634-766. Zero behaviour change.

### 1.2 — The old brain's LLM self-verifier, still in `intent/parser.py` · **certain**

Four methods with **no callers anywhere outside `parser.py` itself**:

| method | lines | superseded by |
|---|---|---|
| `verify_fast_path_async` | 210-240 | `engine/crosscheck.py` |
| `_run_verification` | 329-360 | ” |
| `verify_actions_async` | 361-388 | ” |
| `_verify_block` | 389-504 | ” |

≈200 lines. `ENGINE.md` already says step 6 "owns what used to be four
bolt-ons". These are the bolt-ons; they were never deleted.
`_call_ollama_verify` (505) must stay — `fix_title_async` and `call_llm_json`
use it.

**Cost:** ~200 lines of prompt text that reads like live behaviour, a second
LLM-verification prompt that can be mistaken for the crosscheck's, and a
maintenance trap when someone tunes "the verifier" and tunes the wrong one.

### 1.3 — Three write-only `EngineState` fields · **verified by grep**

| field | written at | read at |
|---|---|---|
| `state.mode` (`state.py:108-110`) | `__init__.py:585` only | **nowhere** |
| `state.retries` (`state.py:127`) | `__init__.py:153` only | **nowhere** |
| `item.labels` (`state.py:71`) | `label.py:39,44` only | **nowhere** |

`ENGINE.md`'s state table claims `retries` is "read by orchestrator" and
`item.labels` is read by "reply, trace and audit". Neither is true — `label.py`
emits a trace *step* (line 50) and that is the only thing that survives; the
`labels` dict on the item is written and dropped. `mode` was meant to make the
background verify pass "compare, never re-commit"; nothing checks it, so the
background pass's safety is enforced only by `self_check_apply` being false by
default.

**Recommendation:** either delete them (contract change — needs
`test_engine_contracts.py:41-56` updated in the same commit, which is exactly
the deliberate-extension protocol the test's docstring describes), or wire
them. `mode` is the one worth wiring, not deleting — see §2.6.

### 1.4 — Two `BLAME` keys and one loop-back branch that cannot fire · **certain**

`crosscheck.BLAME` (`crosscheck.py:33-38`) has four keys. `crosscheck.run`
constructs only `type="missing"` (line 208) and `type="extra"` (line 215).
`"wrong_fields"` and `"format"` are never produced by anything, so
`BLAME["wrong_fields"] → generate` and `BLAME["format"] → validate` are dead
map entries — and `test_engine_contracts.py:129` *pins the dead keys as
frozen contract*.

Downstream, `_loop_target` (`__init__.py:432-444`) tests
`f.blamed_stage in ("segment", "generate")`, but every finding crosscheck
makes carries `blamed_stage == "segment"` (both `BLAME["missing"]` and
`BLAME["extra"]` are `"segment"`). The `"generate"` half is unreachable.

**Cost:** low in runtime, high in comprehension — the deterministic blame
router *looks* like it can send work back to generate or validate and cannot.
Either implement `wrong_fields` (crosscheck already computes token overlap;
it just never compares *fields*) or shrink the map to what it does.

### 1.5 — `CONFIDENCE_SIGNALS` in `fastrule.py:78-87` · **dead, and its docstring is false**

The dict has no readers (`grep -rn CONFIDENCE_SIGNALS` → only its own
definition and a docstring reference). Its comment claims "Keep in sync with
rule_parser (test-pinned)" — **there is no test that pins it.** The real
values live at `rule_parser.py:1661-1673` and only a human diff keeps them
equal today.

**Recommendation:** either delete it, or add the one-line test that makes the
claim true. Do not leave a documentation dict asserting a guarantee that does
not exist — the project's own artifact-claims discipline exists precisely for
this.

### 1.6 — Smaller vestiges (all grep-verified, all zero-risk deletes)

| thing | location | evidence |
|---|---|---|
| `RuleParseResult.routed_to_llm` | `rule_parser.py:120` | never set, never read |
| `recurrence_rounded_from` slot | `rule_parser.py:1287-1288` | pydantic default `extra='ignore'` drops it at `model_validate` (`rule_parser.py:1786`); nothing consumes it. **The rounding it was added to announce is therefore never announced from this path** — see §2.5 |
| `Recurrence.has_until` | `recurrence.py:57` | set, never read |
| duplicate `\bappt\b` expansion | `rule_parser.py:139` and `:144` | literal duplicate row |
| `confirmation_level` | `config.py:276,299-303`, `config.example.yaml:58` | `pipeline.py:81-83` logs a warning that it has no effect; nothing else reads it. `CLAUDE.md` already documents it as inert. Retire the knob rather than warning about it forever |
| `RuleBasedParser.parse()` | `rule_parser.py:1807-1819` | no production caller; only `tests/test_ollama_parser.py`, `tests/test_todo_parser.py`, `scripts/test_pipeline.py`. Its docstring still describes "Pipeline should catch RuleParserSkip" — a pipeline that no longer parses |

### 1.7 — Documentation that describes a system that isn't there

Not code, but it costs the same thing: the next agent trusts it.

| doc | claim | reality |
|---|---|---|
| `ENGINE.md:115-117` | step 5's fast-track guard calls `is_interrogative_create` "so the two cannot disagree about what a question is" | `grep -rn is_interrogative_create` → callers are `validate.py:753` and tests. **`generate.fast_propose` never calls it**; the fast track uses `fastrule._INTERROGATIVE_RE` (a different, broader regex). See §2.4 |
| `ENGINE.md:135-141` | the ordered named-rule list | omits `move_time_fill` (`validate.py:632`) and `create_from_remove_guard` (`validate.py:705`), both live and both firing before the listed rules |
| `ENGINE.md:75` | `retries` read by orchestrator | write-only (§1.3) |
| `SYSTEM.md:94` | "`_normalise_intents` in `assistant/api/server.py`" | that function no longer exists anywhere outside `retired/` |
| `FASTRULE2_DESIGN.md:136-139` | "Retired: semantic rewrites in the normalization list" | still present at `rule_parser.py:179-209`, and **F16/F18 added more of them** — as did F19 *while this audit was being written* (`note to self, X` → `add X`; `put a marker on ‹date› for ‹X›` → `add X on ‹date›`; `i should ‹encounter›` → `i need to ‹encounter›`). These are semantic rewrites by the design doc's own definition, in the list the design doc says was retired |
| `DEEPSYSTEM_DESIGN.md:182-188, 270-273` | `Generate.fragment = FastRule(0.60)`, atomicity re-entry to Decompose | not built (§0) |
| `DEEPSYSTEM_DESIGN.md:254-258` | `Stage.can_skip` / `Stage.metric` | not in `component.py`; `grep -rn "can_skip\|def metric"` → no hits |
| `TASKS.md:106-130` | "cycle 5 in flight 2026-09-06", branch `loop-cycle-1` | superseded by `STAGE_ISOLATION_PLAN.md` (cycles PAUSED) |
| `STATUS.md` | dated 2026-09-06 | `CLAUDE.md` says read it first; it predates the plan of record |

---

## 2 · IMPROVE — priority order

### P1 · The deep track re-commits what FastRule's gates refused

**The problem.** When FastRule vetoes a command at the front door, the
orchestrator sends it to the deep track (`__init__.py:238-248`). For a
**single-item** command, segment produces one item whose text equals
`state.text`, so `_parse_item`'s `is_fragment` is False and the bar is
`RULE_THRESHOLD` — the *same* 0.80 — and it calls the *same*
`rule_parser.analyze` on the *same* text. It gets the same result and commits
it, with no Atomicity check and no Gatekeeper.

Worked example, traced by hand through the code:

- `"remove my reminder"` → front door: `Gatekeeper.judge` matches
  `_GENERIC_TARGET_RE` on `match_title="reminder"` → defer,
  `reason="generic-target:reminder"` (`fastrule.py:132-137`).
- deep: segment → 1 item; `_parse_item` → `analyze` → `delete_todo`,
  `match_title="reminder"`, no missing slots, confidence 1.0 → **committed**.
- `validate.run_objects` has no generic-target rule; crosscheck cannot see it
  (a delete is neither `missing` nor `extra`); commit deletes a task the
  speaker did not identify.

The same undo applies to `rename-misroute` (`fastrule.py:129-131` — validate
has no counterpart rule) and, whenever segment declines to split, to
`strong-compound` / `clause-coordination` / `model-compound`.

**Why it matters for the task.** This is the atomizer/executor split violated
in the one direction that costs correctness: the executor's refusal is
overruled by the atomizer's fallback, and `CLAUDE.md`'s "Deleting is
destructive… guessing is not" is bypassed on the deep path.

**Evidence, and its limits.** Run 16 (`RESULTS.md:7-22`) is *consistent* with
this — the F1/F3 gates raised fast correct-on-committed 79%→90% while deep
fell 78→71 on the rows they deflected — but that run predates the current gate
set and does not isolate the mechanism. **[UNMEASURED]** as a specific class.

**Smallest fix.** Make `_parse_item` call `FastRule(bar).run(item.text,
state.current_view)` instead of `rule_parser.analyze` + an inline predicate.
That is roughly a ten-line change inside `generate.py`, touches no contract,
and is exactly what both design docs already specify. Route
`res.reason` in the compound family to the LLM path (today's behaviour on a
gate hit) rather than to a rule commit. **[needs full-engine run]** to
confirm the net, because it will shift rows from rule-commit to LLM.

### P2 · Three different readers answer "is this a question?", and they disagree

| reader | location | shape it accepts |
|---|---|---|
| `is_interrogative_create` | `segment.py:124-141` | narrow: question-shaped **AND** first-person weighing (`should I`, `what if we`) **AND** a create verb |
| `_INTERROGATIVE_RE` + `_POLITE_IMPERATIVE_RE` | `fastrule.py:57-64` | broad: any WH/aux opener or trailing `?`, minus polite imperatives |
| `_QUESTION_START` / `_QUERY_OPENER` | `validate.py:726-730` | third list, no `should` |

`ENGINE.md` asserts the first two are the same reader. They are not. The
observable consequence: an input the broad regex calls a question but the
narrow one does not (e.g. `"Do I have time to add gym at 7?"`) is **deferred
by FastRule**, then reaches `_rule_question_creates_nothing`
(`validate.py:766-799`), matches `whole_question`, and has its intent set to
`None` — a silent drop. Gil's Q9 ruling is explicitly that an interrogative
create must be *neither* auto-created *nor* silently dropped; this path
silently drops it. **[UNMEASURED]** how many rows fall in the gap — the
fastrule dataset relabels 251 interrogative rows as `action="propose"`
(`TASKS.md:103`), so the data to measure it exists.

**Smallest fix.** One reader, exported from `segment.py` as `ENGINE.md`
already claims, with the breadth question settled once (§4 Q2). Have
`fastrule.Gatekeeper` and `validate` both call it.

### P3 · The daypart defaults invent times that nothing penalises and nothing scores

`_SPOKEN_TIMES` (`rule_parser.py:237-253`) is applied unconditionally inside
`_preprocess` (`:452-453`), **before** temporal extraction:

```python
(r"\blate\s+afternoon\b", "at 4pm"),
(r"\bearly\s+evening\b",  "at 6pm"),
(r"\bfirst thing(?:\s+in the morning)?\b", "at 8am"),
```

After the rewrite the text literally says "at 4pm", so `_extract_temporal`
resolves it through the recognizer, `_source` stays `"recognizer"`, and
`_compute_confidence` applies **no penalty** (the `regex_fallback` ×0.95 at
`:1661-1662` does not fire). A guessed time commits at full confidence, and
its provenance is unrecoverable downstream — validate, crosscheck and the
trace all see a time the speaker "said".

This directly contradicts the project's own rule ("nothing should ever be
guessed at") and the F17 precedent, where a *rounded recurrence* is announced
rather than done quietly.

**And it is measured by a metric that cannot see it.** `fastrule6k.py`'s
docstring lists the scored slots: commit/abstain, counts, action, atomicity,
**title**, labels. Times are not scored. So F15's daypart additions could only
show up as a handle-rate gain — which is what was predicted and reported
— with the correctness cost invisible by construction. **[UNMEASURED], and
currently unmeasurable.**

**Smallest fix, in order of value:**
1. add `start_time` to the fastrule scorer's slot comparison, so the question
   can be asked at all;
2. carry a `time_defaulted` flag on the slots and give it a named entry in the
   Scorer's signal registry (the registry exists for exactly this,
   `fastrule.py:82-87`) — so a defaulted daypart commits at a lower
   confidence than a spoken clock time;
3. or announce it the way a rounded cadence is announced.

### P4 · The complexity gate is a word-count proxy for atomicity, and it runs *before* the atomicity layer

`_preprocess` (`rule_parser.py:472-497`) hard-skips on:

- `len(content_words) > 12`
- `len(clause_verbs) > 3`
- any relative clause with an explicit subject

A skip raises `RuleParserSkip`, which `FastRule.run` converts to
`reason="skip:…"` **before** `Atomicity.judge` ever runs
(`fastrule.py:169-175`). So:

- a genuinely atomic but wordy item — *"book the quarterly planning meeting
  with the whole product team next Tuesday at 3pm in the big conference
  room"* — is refused by the executor whose entire job is one atomic item, on
  a proxy the architecture has since replaced with a real atomicity layer;
- the same gate fires again on the deep path (`_parse_item` catches
  `RuleParserSkip` at `:180` and falls through to the LLM), so every long
  atomic fragment costs an LLM call.

The gate predates layer 0 and now overlaps it: `Atomicity` (rules + the F15
model tier) is the designed answer to "is this more than one thing", and the
word count is a cruder answer to the same question, applied first and
unconditionally.

**Compounding measurement problem:** `fastrule_shape.py:99,105,108` buckets
abstain reasons by `reason.split(":")[0]`, so `skip:Complexity gate fired…`
and `skip:No action matched…` land in the **same "skip" bucket**. F19's
prediction (`RESULTS.md:1046+`) characterises that 253-row bucket as
"no action matched at all" — but the bucket also contains complexity-gate
skips, and the two need opposite fixes (vocabulary vs. gate removal).

**Smallest fix.** Split the skip reason into two (`skip-complexity` /
`skip-noroute`) so the buckets separate; then measure how many rows the
word-count gate refuses that layer 0 calls atomic. That is a pure
FastRule-lane experiment and does **not** need a full-engine run.

### P5 · Cadence rounding is implemented twice, with different tables, and one gap is silent

| | `intent/recurrence.py:30-41` (`_PATTERNS`) | `engine/validate.py:50-57` (`_UNSUPPORTED_CADENCE`) |
|---|---|---|
| every other X | → weekly, `rounded_from` set | → announced |
| every weekday | → daily, `rounded_from` set | → announced |
| twice/N times a week | → weekly, `rounded_from` set | → announced |
| **every year / yearly / annually** | **→ monthly, `rounded_from` set** | **no entry** |

`recurrence.detect` rounds *yearly to monthly* — a large, confidently wrong
series — and puts the original words in `recurrence_rounded_from`, which
pydantic then drops (§1.6). Validate has no yearly row, so nothing is said.
The project rule is "the rounding is announced in the reply rather than done
quietly". This one is done quietly.

Second divergence: `recurrence.detect`'s anchor loop
(`recurrence.py:79-83`) iterates `_WEEKDAYS` in **dict-literal order** and
breaks on the first weekday word present, so *"every sunday and tuesday"*
anchors on **Tuesday**, not on the soonest. `validate._rule_weekly_start_day`
(`:538-553`) computes the soonest correctly and repairs it — so the bug is
masked, but only because the same rule is written twice and only one copy is
right.

**Smallest fix.** One recurrence reader. `validate` should read
`recurrence.detect`'s result (cadence + `rounded_from`) rather than re-deriving
it from its own regex table, and `rounded_from` should ride the intent (add
the field, or carry it in `item.slots`) so the announcement has something to
announce.

### P6 · `state.fixes` is invisible outside `validate`

`state.add_fix` is called from `generate` five times — `invention_guard`
(`:214`), `event_kind_retry` (`:264`), `event_fallback` (`:270`),
`task_fallback` (`:283`), `item_parse_failed` (`:242`) — and **none of them
produce a trace step or reach the response.** Only `validate.run` /
`run_objects` slice `state.fixes` into trace steps (`:383-386`, `:447-451`).
`grep -rn "state.fixes"` outside validate → tests only.

`ENGINE.md:144` says "Every applied rule lands in `state.fixes` under its name
and in the trace." Half of that is true. The consequence is operational: when
`event_fallback` invents a default title, or `invention_guard` drops an LLM
event, the thinking panel and the HUD show nothing, so the failure mode is
invisible in exactly the review surface built to expose it.

**Smallest fix.** One trace step at the end of `generate.run` that emits the
fixes added during that pass, mirroring validate's block. Five lines.

### P7 · The loop-back commits an unjudged parse and feeds stale mistakes back in

`DeepSystem.judge` (`__init__.py:141-165`):

```python
while reentries < MAX_REENTRIES:
    self.crosscheck.run(state, cfg)
    loop_to = _loop_target(state)
    if loop_to is None: break
    reentries += 1
    ...
    self.parse(state, cfg)
else:
    if any(f.type == "missing" for f in state.findings): ...
```

Two defects:

1. **The last re-parse is never crosschecked.** On exhaustion the loop exits
   after `self.parse(...)` with `reentries == 3`, so the objects that get
   committed were produced by a pass no judge ever saw. The "worth a glance"
   message is decided from `state.findings`, which still describe the
   *previous* parse's objects — objects that no longer exist.
2. **`state.mistakes` is never cleared.** `crosscheck.py:222` appends;
   nothing resets. By the third loop the segment prompt
   (`segment.py:326-328`) carries three rounds of accumulated complaints,
   including ones the re-parse already fixed, told to the model as "do not
   repeat them".

Cost: up to 3 extra LLM segment calls + 3 rounds of generate per command, and
the run-8 comment in `_loop_target` records that this already produced "39
loop storms" once. **Smallest fix:** run the crosscheck once more after the
final re-parse (or judge before deciding to loop again), and reset
`state.mistakes` at the top of `DeepSystem.parse`.

### P8 · Background threads are not gated by `MACALENDAR_NO_WARMUP`, and one writes to the DB during measurement

`CLAUDE.md` states: "The engine reads the same flag before starting any daemon
thread." Of three thread spawns in `engine/__init__.py`, **one** checks it:

| spawn | line | `_no_bg()` checked |
|---|---|---|
| `crosscheck-bg` (background verify) | 493 | **no** |
| `_log_nlu` worker | 1035 | **no** (it checks `source == "test"`, which covers the harnesses) |
| `reformulations` | 1075 | yes (1051) |

The consequential one is `crosscheck-bg`. It runs a **full LLM extract call**
per fast-committed row and, at `__init__.py:508-524`, **unconditionally**
renames placeholder event titles in the database — that path is not gated by
`self_check_apply` (only the missing/extra patches at `:532` and `:541` are).

In `scripts/engine_dataset_compare.py` the replay loop
(`:341-348`) calls `_reset_calendar()` (`:130-139`, `DELETE FROM events/todos/
subtasks`) at the top of each row while the previous row's `crosscheck-bg`
thread may still be in flight. Row ids are reused after a wipe, so a late
`update_event(row_id, title=…)` can land on a *different row's* event. Nothing
joins or drains those threads.

**[UNMEASURED]** how often it actually collides. But it is also a straight
latency tax: one extra LLM call per fast row, running concurrently with the
next row's foreground work, on every dev-fast-250 run.

**Smallest fix.** Guard `_start_background_verify` with `_no_bg()` (or with
`state.source == "test"`, matching `_log_nlu`). One line, and it makes
`CLAUDE.md`'s claim true.

### P9 · The two FastRule scorers disagree about what an atomicity abstain is

```
scripts/fastrule_shape.py:40  _ATOMICITY_REASONS = {"strong-compound", "clause-coordination",
                                                    "mixed-mode-compound", "model-compound"}
scripts/fastrule6k.py:54      _COMPOUND_REASONS  = ("strong-compound", "clause-coordination",
                                                    "mixed-mode-compound")
```

F15 added `"model-compound"` (`fastrule.py:116`) and updated only one scorer.
`fastrule6k.py` is the one whose docstring calls atomicity "the first direct
gate supervision"; it will now score every model-tier compound detection as
*not* a compound detection, understating atomicity recall. The TEST-EVAL
snapshot figure (atomicity P 90.8 / R 49.4, `RESULTS.md:96-111`) predates the
model tier, so it is not itself wrong — but the next `fastrule6k` run will be.

**Smallest fix.** One shared constant, imported by both scorers, defined next
to `Atomicity` in `fastrule.py` — which is where the reasons are produced.
No measurement needed; this is a correctness fix to the instrument.

### P10 · "Which domain is this?" is answered in four independent places

| answer | location |
|---|---|
| `_kind_of` + `_enforce_pinned_kinds` (regex, project conventions) | `segment.py:144-191` |
| `_kind_for` (string match on the action name) | `generate.py:125-132` |
| `_CALENDAR_SIGNALS` / `_TODO_SIGNALS` + view fallback | `rule_parser.py:352-362, 991-1008` |
| `KindFeatures` (learned) | `classifier.py:136-163` |

F13's actual (`RESULTS.md:82-95`) is directly about this: rebuilding
`KindFeatures` on segment's "proven" regexes **regressed** test macro-F1
82.6 → 80.5, and was reverted. That is measured evidence that the four readers
are not interchangeable — but nothing decides which one is authoritative for a
given decision, and `segment`'s conventions (the reminder rules, the
"calendar invite" rule, the encounter-verb rule) exist only on the deep path.
FastRule has no access to them, which is one plausible source of the
kind errors the model tier is being asked to fix.

**This is the atomizer/executor split's other half:** if the deep system is
the atomizer, "what kind of thing is this" is arguably *its* judgment to make
and hand down — but on the fast track there is no atomizer, so FastRule must
answer it too. That tension is a design question (§4 Q3), not something the
audit can settle. What it *can* say: four copies with no ownership statement
is how F13's kind of surprise happens.

### P11 · The crosscheck's matching threshold is an unexplained constant

`crosscheck.py:199,201`: `best_score >= 0.25` on a
`len(a & b) / min(len(a), len(b))` token overlap, after a hand-written
16-word stopword list (`:97-99`). Every other threshold in the engine carries
its tuning provenance in a comment (`RULE_THRESHOLD = 0.80  # tuned
2026-09-07…`, the margin floors `2.5/1.5  # tightened 2026-09-07 after the
A-pool dual-gate…`). This one has none.

It is load-bearing: it decides `missing` (which triggers a 3× loop-back) and
`extra` (which, with `self_check_apply` on, **deletes a committed row**).
`STAGE_ISOLATION_PLAN.md` lists crosscheck's dataset as "not started"; when it
is built, this constant is the first thing it should sweep.

### P12 · Note on work in flight — domain-agnostic entries for ambiguous verbs

Observation only, on the F19 batch landing while this audit was written (it
has a registered prediction, so it is inside the protocol). Four of the new
`INTENT_MAP` rows are `(lemma, None)` — domain-agnostic — for words that are
also very common nouns or calendar verbs:

```python
("sort",   None): "create_todo",   ("review", None): "create_todo",
("file",   None): "create_todo",   ("invite", None): "create_event",
```

`_route_intent`'s Pass 4 (`rule_parser.py:1070-1078`) matches **any token's
lemma**, at any position and any POS. So a `(lemma, None)` entry is the
strongest, least-guarded kind of routing rule in the table — `"move the design
review to 4pm"` now has a `create_todo` lemma sitting inside an update
command, and `domain_material=False` means the domain guess costs it no
confidence penalty either. Whether Pass 4 reaches it depends on whether an
earlier pass matched first, which is the "ORDER as load-bearing, undocumented
structure" that `FASTRULE2_DESIGN.md:38-40` names as the thing v2 exists to
fix.

Not a claim that F19 is wrong — the mined evidence (19 `grab`, 15 `sort`,
7 `review`…) is real, and the prediction is registered. The point is that the
lane has no metric that would notice the *collateral* damage: `fastrule_shape`
reports handle-rate and correct-on-handled for atomic rows, and a newly
mis-routed mutation shows up there only if it happens to be in the sample.
A per-family floor on mutation rows (the discipline `FASTRULE2_DESIGN.md:132`
already lists as "kept") would catch it.

---

## 3 · GOOD — protect these

These carry their weight. A refactor that loses them costs real correctness.

1. **The frozen-contract discipline, and its enforcement.**
   `test_engine_contracts.py` is the reason a five-agent codebase still has
   one `EngineState`. Note that it works *because* it is annoying: its
   docstring tells you a red is a design change, not a fix. Keep it. Even the
   dead `BLAME` keys (§1.4) should be removed *through* it, not around it.

2. **Deterministic-first, with self-skipping LLM stages.**
   `segment._llm_segments` (`:321`) refuses to call the model without a
   compound hint and ≥6 words; `decompose._llm_split_times` (`:72-81`)
   requires two clock-time mentions and excludes ranges;
   `validate._repair_text` (`:347`) requires an actual mangle signature. This
   is the pattern that keeps the engine offline-capable and cheap, and it is
   applied consistently.

3. **The under-split bias, and its justification.** `segment.py:14-17` and
   the refusal at `:354` (a split producing a one-word fragment is rejected).
   The asymmetry argument — a wrong merge gets two more chances, a wrong split
   is immediate garbage — is correct and is the single most important
   invariant in the atomizer.

4. **Crosscheck's extract-don't-judge split.** `crosscheck.py:10-19`. Asking
   a small model to *list what was asked* and having code do the diff is the
   right division, and the fixed `BLAME` map ("the model never picks the
   stage") is the right guard against an LLM steering its own re-run.

5. **The honest-failure ladder in generate.** `task_fallback` (`:274-288`),
   `event_fallback` (`:313-336`, which fires *only* when the noun and a
   grounded when are both literally in the words), and `_guard_inventions` /
   `_grounded_title` (`:193-225`). This is "nothing is ever invented"
   implemented rather than asserted. `_grounded_title`'s prefix-stem check is
   a genuinely good, cheap idea.

6. **Named rules with bug provenance.** Every rule in `validate.py` has a
   docstring naming the real command that bought it ("every sunday and tuesday
   at 9am once produced 106 events, none on a Sunday or Tuesday"). This is
   what makes the file safe to edit. Preserve it verbatim in any rewrite —
   the rules are cheap, the *reasons* are not reconstructible.

7. **Blocked items are reported, never dropped.** `_commit`'s
   `item.blocked` branch (`__init__.py:346-353`) and crosscheck's decision to
   count blocked items as *covered* (`crosscheck.py:135-149`) — the comment
   there records that not doing so sent every gated command into a loop storm
   that could never resolve. That is a subtle interaction, easy to
   re-break.

8. **`lead_time.py` and `recurrence.py` as shared `intent/` modules.**
   F16's move of the lead-time strip out of `decompose` into `intent/` so both
   readers share it is the *correct* response to a duplication problem, and
   the module docstring says why. This is the pattern P5 and P10 should
   follow.

9. **The measurement discipline itself** — registered predictions, sealed
   test halves, banked negatives (F13, F14), the leakage guard enforced *in
   the scorer* (`fastrule6k.py:18-21`). Four negative results are recorded as
   carefully as the positives. That is rare and it is why the F-batch history
   is trustworthy.

10. **`Stage`'s late binding.** `component.py:29-35` — the comment records
    that an eagerly-captured function silently ignored monkeypatched stages
    and that `test_engine_flow` caught it on the first refactor attempt. A
    future "optimisation" will want to bind eagerly. It must not.

---

## 4 · Questions the audit cannot settle — for Gil

**Q1 · Does the deep track's generate stage owe FastRule's vetoes?**
This is P1, and it is a product call, not a code call. If FastRule is the
executor, its refusal should be final and the deep track should route a vetoed
parse to the LLM (slower, safer). If FastRule is only a fast path, the current
behaviour is correct and the gates are purely a fast-track latency/safety
tradeoff. The docs say the former; the code does the latter. **Which is it?**
(Concretely: should `"remove my reminder"` delete something, ask, or refuse?)

**Q2 · How broad is "a question"?**
Three readers, three breadths (P2). The narrow one (`should I` / `what if we`
+ create verb) is what the Q9 ruling described. The broad one is what actually
gates the fast track today. Settling this settles P2 and removes a whole class
of silent drops.

**Q3 · Who owns "event or task"?**
Four implementations (P10). Options: (a) segment is authoritative and hands
`kind` down as a slot FastRule must honour — but then the fast track has no
segment; (b) FastRule owns it and segment's conventions move into
`intent/`; (c) the learned `KindFeatures` becomes authoritative and the regexes
become its features. F13 measured that (c)-style merging *hurts*, so (a) or
(b). This is the biggest remaining structural decision.

**Q4 · Is a defaulted daypart a commit or a defer?**
P3. "Late afternoon" → 16:00 is a guess that currently commits at full
confidence and is invisible to every metric. Three consistent answers exist:
penalise it (Scorer signal), announce it (like a rounded cadence), or defer
it. All three are defensible; the current fourth option — guess silently —
is the one the project's stated principles rule out.

**Q5 · Should the complexity gate survive layer 0?**
P4. The word-count/clause-count skip is a pre-atomicity proxy for atomicity.
Now that `Atomicity` exists with a measured model tier, is the gate still
earning its place, or is it refusing atomic-but-wordy items that the executor
should handle? The FastRule lane can answer this cheaply once the skip bucket
is split — but whether to *try* is a scope call.

**Q6 · What is the stage-isolation plan for `generate`?**
`STAGE_ISOLATION_PLAN.md` marks generate "done — step 1 (the FastRule 7,200)".
But the FastRule 7,200 exercises the **0.80 front door only** (`fastrule6k.py`
and `fastrule_shape.py` both build `FastRule(RULE_THRESHOLD)`), while the
generate *stage* is the 0.60 per-item path with a different bar, no gates, and
an LLM fallback. **The stage's actual production behaviour is currently
unmeasured by any lane.** Is generate really graduated, or does it need its own
dataset (item → expected intent) before the rebuild?

**Q7 · Process: F15–F18 shipped without logged actuals.**
`RESULTS.md` carries F15's *prediction* and F19's *prediction*; there is no
F15/F16/F17/F18 ACTUAL entry, and F16–F18 have no registered prediction at
all. The numbers F19 quotes as current (atomic handle 55.0%, correct-on-handled
73.9%) are the post-F18 state but were never banked. `CLAUDE.md` requires
"compare actual vs. expected … in `dataset/RESULTS.md`" per cycle. Is the
stage-isolation lane exempt from the prediction protocol, or did four batches
slip through it?

---

## 5 · Suggested order of work

Cheap, no measurement needed, do first:

1. Delete the duplicated 129 lines (§1.1) — pure win.
2. Share the atomicity-reason constant between the two scorers (P9) — fixes
   the instrument before it reports a wrong number.
3. Guard `_start_background_verify` with `_no_bg()` (P8) — one line, removes
   an LLM call per fast row from every measured run and closes a DB race.
4. Split `skip:` into `skip-complexity` / `skip-noroute` (P4, first half) —
   makes F19's bucket honest.
5. Delete the dead verifier in `parser.py` (§1.2), `CONFIDENCE_SIGNALS`
   (§1.5) and the §1.6 vestiges.
6. Fix the doc drift in §1.7 — cheapest way to stop the next agent building
   on a false premise.

FastRule-lane experiments (measurable now, cycles paused is fine):

7. Score `start_time` in `fastrule6k` (P3, step 1), then measure the daypart
   defaults.
8. Measure how many `skip-complexity` rows layer 0 calls atomic (P4).

Needs a full-engine run — queue behind the rebuild:

9. `_parse_item` → `FastRule(bar)` (P1). **[needs full-engine run]**
10. One question reader (P2). **[needs full-engine run]**
11. Crosscheck loop-back fixes (P7) and the 0.25 threshold sweep (P11) —
    both belong to crosscheck's own stage dataset, which
    `STAGE_ISOLATION_PLAN.md` has not started.
