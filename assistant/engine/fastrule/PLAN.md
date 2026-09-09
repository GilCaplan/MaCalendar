# FastRule — the restructure plan (2026-09-09)

`ARCHITECTURE.md` is how it works today. This is what to change and why.

---

## 1 · The box (Gil, 2026-09-09)

> *"This step shouldn't be redoing segmentation's work. It takes the work from
> segmentation and decompose_validate — which is a `List[Item]` — and makes it
> into an object format the software accepts, and if there's an issue it tells
> LLMVerify."*

    IN    List[Item]  — everything the two stages upstream worked out
    OUT   the objects the software accepts (CalendarIntent / CreateTodoIntent …)
    ELSE  a DEFER with a reason, handed to LLMJudge

**So FastRule is a CONVERTER, not a parser.** That single sentence is the
restructure: the current code re-reads the raw text and works the whole thing out
again, and almost every defect below follows from that.

## 2 · What the Item already carries, and what is genuinely left to do

| the object needs | who decided it | today |
|---|---|---|
| `date`, `start_time`, `end_time` | **decompose_validate** | re-derived from text |
| `recurrence`, `recur_days`, `recur_until` | **decompose_validate** | re-derived |
| `quantity`, `reminder_minutes` | **decompose_validate** | re-derived |
| event vs task vs review vs other | **segmentation** (`tag`) | re-derived |
| the words of the ask | **segmentation** (`action`) | re-derived |
| **which OPERATION** — create / update / delete / complete / query | **nobody yet** | ✔ FastRule's |
| **the TITLE** — the ask minus its verb | nobody yet | ✔ FastRule's |
| **attendees, location** | nobody yet | ✔ FastRule's |
| **the TARGET record** for an edit or delete | nobody yet | ✔ FastRule's |

Six of ten fields are already decided upstream and thrown away. **What is actually
left is the operation, the title, the people and the target** — and those are the
four things the rule parser is genuinely good at, because they are about the ACTION
words, not about time.

### The cost of re-deriving, measured

Whole-command parses of things segmentation reads correctly (2026-09-09):

| said | segmentation | the rule parser |
|---|---|---|
| `remind me to call the bank in two hours` | action `remind me to call the bank`, time `today in two hours` | title **`call the bank in two hours`** — the time is IN THE TITLE |
| `book yoga late afternoon` | action + time both right | **nothing** |
| `book the dentist the 20th of november at 3pm` | both right | **nothing** |
| `gym on sundays at 7am` | action `gym`, time `on sundays` | **`RuleParserSkip`** |

Three of four produce nothing at all. Segmentation learned lead times, ranges,
spoken clocks, month-of-ordinals, plural weekdays and one-word cadences on
2026-09-09; `rule_parser.py` knows none of them.

**And teaching it is the wrong fix.** A second time vocabulary is a second thing to
keep in step, and the project already paid for that lesson three times — the
invariant that was three copies, the logistic regression that was four, the pipeline
GUI and server each with their own parser. The fix is to stop asking it about time.

`below-threshold` is **573 of about 989** atomic deferrals, and a parser that
returns nothing scores zero confidence by construction — so this is where that mass
most plausibly sits. **B1** below measures it before anything is moved.

## 2b · It does FOUR jobs; three are other components' (Gil, 2026-09-09)

> *"FastRule's job is only to take each Item and make it into an object format the
> software/system [accepts] so we can commit when ready."*

Measured against that, of ~890 lines in `fastrule.py` + `objects.py`:

| what it does | lines | whose |
|---|---:|---|
| **copy the Item's values onto the object** (`_apply_slots`) | **11** | ✅ **FastRule's** |
| read operation · title · attendees · target | ~90 | ✅ FastRule's |
| build the object per item (`run`, `_event_fallback`, `_kind_for`) | ~135 | ✅ FastRule's |
| parser + registry plumbing | ~50 | ✅ needs it |
| `Atomicity` — *"one item or several?"* | ~100 | ❌ **segmentation's** question |
| `Gatekeeper` + `_which_store_holds` + `_names_something_real` — `fastrule.py:234-351` | ~118 | ❌ **LLMJudge's** (Gil) |
| the LLM fallback — `_parse_item`'s model half, `_honour_refusal`, `_grounded_title`, `_guard_inventions`, `_llm_trace` — all in **`objects.py:150-318`** | ~150 | ❌ **LLMJudge's** (Gil) |
| `fast_propose` + `Scorer` — whole-command instant commit | ~55 | ❌ a COMMIT decision |
| `stage.run` → `decompose_validate.run_objects` | 2 | ❌ that stage's rules |

**~423 of ~890 lines belong somewhere else.** And the function doing the job the
stage exists for is **eleven lines** that copy **two of eight** available values
(`reminder_minutes`, `quantity`) — defensively, as a "hint", and only when the
intent has nothing there already. It never copies `date`, `start_time`, `end_time`,
`recurrence`, `recur_days` or `recur_until` at all.

## 2c · What FastRule becomes

```
    List[Item]  ──►  for each Item:
                       1. COPY item.slots onto the object   (all 8 values)
                       2. read the ACTION words for
                          operation · title · attendees · target
                       3. can't build it?  ──►  DEFER(reason)  ──►  LLMJudge
                     ──►  List[object], ready for whoever commits
```

Nothing else. No model call, no atomicity test, no veto, no commit decision.

**Where each removed piece goes, and why there:**

| moves | to | because |
|---|---|---|
| `Atomicity` | the FAST TRACK (`fast_track.py`) | at the front door there is no Item yet, so *"is this one ask?"* is exactly the right question. In the deep track the item is atomic by contract, so the test is dead weight |
| `Gatekeeper` + its two DB helpers | **LLMJudge**, as prompt CONTEXT (Gil) — ported in **phase A** | it is a *reading* judgement — "this would execute the wrong thing" — and the model is the thing that can resolve it. As a veto it could only refuse; as context it can be answered |
| the LLM fallback + its guards | **LLMJudge** — ported in **phase A** | Gil: *"if issue it tells the LLMVerify."* FastRule reports `DEFER(INCAPACITY)` and carries its partial parse; the model call happens where the model lives |
| `fast_propose` + `Scorer` | the fast track / orchestrator | "confident enough to COMMIT?" is a commit decision. FastRule builds; something else decides when to write |
| the `run_objects` call | `decompose_validate` | already its own stage's finish line |

**What is left is small and testable on its own**: a pure function from one `Item`
to one object, with no model, no database, and no opinion about whether to commit.
That is what makes it measurable against its own task — which is the other half of
what this restructure is for.

## 2d · THE TARGET — what FastRule is when this is done

One module, one entry point, one job.

```python
def build(item: Item, *, today: date) -> BuildResult:
    """One Item -> one object the system accepts, or a DEFER saying why."""
```

    BuildResult = object   a CalendarIntent / CreateTodoIntent / … ready to commit
                | DEFER    (reason, reason_class, partial)  ->  LLMJudge

**`BuildResult` is INTERNAL to this folder — it is not the stage's output.** X4
stays `item.action` + `item.intent` on the frozen `Item`, and `stage.run` unwraps a
`BuildResult` onto them; the DEFER rides `state.fastrule_verdict`, which already
exists. Both are pinned by `test_engine_contracts.py`, so making `BuildResult` the
stage's actual output would be a contract change — a TASKS.md design decision, not
part of this restructure. §3's B3 has the detail.

### What it DOES, in order

1. **COPY the values.** All eight, from `item.slots`, unconditionally:
   `date · start_time · end_time · recurrence · recur_days · recur_until ·
   quantity · reminder_minutes`. Not as hints, not "if the intent has nothing
   there" — as the answer. The stage that produced them is measured at 99.9%
   train / 98.7% sealed on exactly this question, and this stage has no better
   information.
2. **Pick the OPERATION** from the action words — create / update / delete /
   complete / query. `item.tag` narrows it (`event` vs `task` vs `review`); the
   verb decides the rest.
3. **Fill the object's own fields** from the action words: title, attendees,
   location, and for an edit or delete the TARGET record.
4. **Return the object** — or `DEFER` when a required field cannot be filled,
   carrying the partial parse so the next stage starts from it rather than cold.

### What it does NOT do — and where each went

| not this | goes to |
|---|---|
| decide whether the command is one item or several | segmentation (`Atomicity` → the fast track's admission test) |
| re-read the date, time or recurrence from the text | nowhere — `decompose_validate` already did it |
| veto a reading that must not execute | **LLMJudge**, as prompt context |
| call the model when the rules fall short | **LLMJudge** |
| decide whether the answer is good enough to COMMIT | the fast track / orchestrator |
| apply another stage's field rules | `decompose_validate.run_objects` |

### The two properties that make it testable alone

**No I/O and no model.** No database lookup, no LLM call, no config. `build` is a
pure function of `(Item, today)`, so its board can be a table of items and expected
objects, and a failure is reproducible from the row alone.

**DEFER is an output, not an exception.** Which keeps the primary metric a PAIR —
how often it builds, and how right it is when it does. Either number alone is
gameable: a converter that defers everything is never wrong, and one that guesses
everything always answers.

## 3 · Order of work — FOUR PHASES (Gil, 2026-09-09)

> Gil: *"Make sure in the FastRule plan it points to what needs to be ported
> first. Then work on the restructuring / implementation fixes for FastRule. Then
> work on FastRule with making sure it has its own dataset and eval metrics to
> improve the implementation until we are satisfied. Then once we totally finish
> FastRule then let me know and we can work on LLMJudge."*

    A  PORT OUT ......... what leaves, before anything breaks    → llmjudge/PLAN.md §1.0
    B  RESTRUCTURE ...... build(), and the implementation fixes
    C  MEASURE .......... its own dataset + its own boards, iterate until satisfied
    D  STOP ............. report to Gil. LLMJudge does not start before this

**The phase boundaries are not bookkeeping.** A is the only phase that must move
no number; C is the only phase that may not change behaviour without a board
saying why; D is a decision point that belongs to Gil, not to this plan.

### PHASE A — port out first

**This is the whole of `llmjudge/PLAN.md` §1.0 and nothing else** — that file
carries the manifest: eleven names, their exact source lines, the tests that move,
and the acceptance test. Summarised here only so the order is unmissable:

| | leaves `fastrule/` | lands |
|---|---|---|
| A1 | `Gatekeeper`, `_which_store_holds`, `_names_something_real`, `_GENERIC_TARGET_RE`, `_POLITE_IMPERATIVE_RE`, `_INTERROGATIVE_RE` | `llmjudge/gatekeeper.py` |
| A2 | `_llm_trace`, `_honour_refusal`, `_grounded_title`, `_TITLE_STOP`, `_guard_inventions` | `llmjudge/llm_fallback.py` |
| A3 | 3 tests from `test_fastrule.py` | `tests/unit/test_engine_llmjudge.py` (new) |

**Stays here, deliberately**: `REFUSAL`/`STRUCTURE`/`INCAPACITY`, `_REASON_CLASS`
and `reason_class()` (`fastrule.py:103-131`). The DEFER is FastRule's product and
this is the vocabulary it is written in; three other readers depend on it.

**A moves the code, not the design.** Turning the veto into prompt context and the
fallback into a `DEFER(INCAPACITY)` consumer is LLMJudge's own work, in phase D's
successor. Phase A's success condition is that `fastrule_shape.py` prints the §5
baseline unchanged.

### PHASE B — restructure, then WIRE IT IN

| # | step | why here |
|---|---|---|
| B1 | **Measure the ceiling** — of the 573 `below-threshold` deferrals, how many carry slots the parser failed to read | a number before a refactor. If it is small, the converter is not the lever and B2 changes shape |
| B2 | **`build(item, *, today)`** — COPY all eight slots, parse only operation / title / attendees / target. Unit-tested ALONE, not yet wired | the substance; everything else is arrangement. It is a pure function, so it can be proven before the engine ever calls it |
| **B3** | **WIRE IT INTO THE ENGINE** (Gil, 2026-09-09) — the five touch-points below | *"once initial working implementation is done, fix wiring to the engine."* A converter nothing calls is not a working stage |
| B4 | Move `Atomicity` + `fast_propose` to a **new `fastrule/fast_track.py`**, and follow the one call site | safe once `build` no longer needs them. The file does not exist yet |
| B5 | Delete FastRule's call sites into the phase-A code | the STAGE BOUNDARY changes here — after the converter works and is wired, never beside it |
| B6 | Delete what is now dead | phase A's import redirect, and `_parse_item`'s branch once nothing takes it |

B1 is measured on the CURRENT board, which still works because phase B has not
changed the box's input shape yet. **That stops being true the moment B2 lands** —
which is the whole reason phase C exists and is not optional.

**B2 and B3 are deliberately separate.** `build()` is a pure function of
`(Item, today)` with no model, no database and no config — so it can be tested
exhaustively from a table of items before anything in the engine points at it.
Wiring a converter and writing it in the same step means a failure could be either,
and the whole reason this stage is being made pure is to stop that.

#### B3 · the five wiring touch-points, mapped 2026-09-09

| # | site | what changes |
|---|---|---|
| W1 | `fastrule/stage.py:22-26` | `run()` calls `_objects.run` then `_decompose_validate.run_objects`. Becomes: `build(item)` per item. **`run_objects`' VALUE pass is then dead** — §"computed TWICE" below — leaving only its targeting, boundary guards and observance flag |
| W2 | `engine/__init__.py:111` — `Stage("fastrule", _fastrule)` | **unchanged.** The stage identity survives, which is why no `BRAIN_VERSION` bump |
| W3 | `engine/__init__.py:246` — `_generate.fast_propose(state, cfg)` | follows `fast_propose` to `fast_track.py` in B4 |
| W4 | `engine/__init__.py:612` — **a SECOND caller of the stage body** | inside `_commit_missing_ask`, on a synthesised sub-state. Easy to miss; see the defect below |
| W5 | the parser + registry accessors | **the one that is not mechanical** — below |

**W5 · `objects.py` is the engine's shared accessor, not only the stage.** Four of
its functions are infrastructure the rest of the system reaches through, at six
sites outside this stage:

    get_registry()        engine/__init__.py:353   (_commit's action registry)
    _get_parser(cfg)      engine/__init__.py:540   (fix_title_async)
                          engine/__init__.py:828   (retry re-parse)
                          engine/__init__.py:942   (call_llm_json, retry detection)
    _get_rule_parser()    api/server.py:177        (warm-up)
    _get_parser(cfg)      api/server.py:181        (warm-up)

**This collides with the box definition head-on.** §2d says `build` has *no model
and no I/O* — so the LLM parser accessor cannot live in FastRule once the
restructure is real, and six callers would break when `objects.py` goes. The
accessors need a home before B5/B6 delete the file, and the natural one is
`assistant/engine/llm.py`, which already exists and is already what `llmjudge.py:116`
reaches for. **Decide this in B3, not in B6** — discovering it during a deletion is
how a warm-up path silently stops warming up.

**A probable live defect found while mapping W4.** `_commit_missing_ask`
(`engine/__init__.py:600-616`) is the recovery path for a `missing` finding — the
one that re-commits an ask the chain dropped. It builds its item as:

    sub.items = [Item(id="item_1", kind="other", text=words)]
    _generate.run(sub, cfg)

but `objects.run` **skips every item whose `kind` is `"other"`** (`objects.py:323-329`),
setting `action="unknown", intent=None`. `Item.kind` is a plain required field with
no `__post_init__`, so nothing rewrites it in between. **So the recovery path reads
as a no-op**: `_commit(sub, cfg)` is handed nothing to commit.

Flagged rather than asserted — it wants one live check before it is called a bug,
because `kind="other"` may have been chosen for a reason that is no longer visible.
But it is exactly the class of thing B3 exists to catch, and it is the kind of
defect no board would ever show, because the path only runs when something else has
already gone wrong.

#### B3 · the FORMAT question — and why `BuildResult` must stay INTERNAL

> Gil: *"it means fixing the pipeline and wiring code to accept the corrected
> format of the FastRule step."*

The pipeline has to accept what `build()` produces — which raises the question §2d
does not answer, and getting it wrong would breach a freeze. **What
`tests/unit/test_engine_contracts.py` actually pins:**

    test_item_fields()   Item == {id, kind, text, time, slots, action,
                                  intent, blocked, labels}          FROZEN
    test_stage_roster_is_fixed()   "fastrule" is a stage             FROZEN
    line 95              imports `assistant.engine.fastrule.objects`
                         as the stage's module                       FROZEN

So **X4 is `item.action` + `item.intent` on a frozen `Item`** — that is the
format the rest of the pipeline consumes, and it is pinned. Therefore:

- **`BuildResult` is a COMPONENT-level return value, internal to this folder.**
  `build(item, today) -> BuildResult` is how the converter is *tested* and *reasoned
  about*; `stage.run` unwraps it onto `item.action` / `item.intent` exactly as
  `objects.run` does today. The Stage contract does not move.
- **A DEFER is likewise internal** — it already has a carrier: `state.fastrule_
  verdict`, itself a frozen `EngineState` field. Nothing new is needed.
- **If X4 should genuinely BECOME a `BuildResult`**, that is an `Item`-contract
  change, and CLAUDE.md's rule applies without exception: *"If the contract itself
  seems wrong, that is a design change: take it to TASKS.md, don't slip it into a
  fix."* Phase B does not get to decide it.

**So "the corrected format" is a smaller change than it sounds, and that is the
finding.** The pipeline already accepts FastRule's output shape; what changes is
that the values arriving in it are COPIED from `item.slots` instead of re-parsed.
Downstream sees the same fields, better filled. The two places that genuinely must
adapt are W1 (`run_objects`' value pass becomes a no-op) and W5 (the accessors).

**One frozen-contract edit is unavoidable and must be deliberate.**
`test_engine_contracts.py:95` names `fastrule.objects` as the stage's module, so
renaming or deleting that file turns the contract test red *by design*. When B6
gets there, update the pinned module name and record it in the test's comment the
way the 2026-09-08 re-cut did — a recorded design change, never a quiet edit to get
green.

#### B3 · the md files that go stale, and the ones that must NOT be touched

> Gil: *"and also to fix relevant md files documenting the system how it works and
> workflow files."*

Derived by sweeping for the names that stop being true, not guessed:

| file | what changes |
|---|---|
| `fastrule/ARCHITECTURE.md` | the flow diagram (`text → parse → Atomicity → Gatekeeper → Scorer → commit`) and the component table — both describe the pre-restructure box |
| `engine/ARCHITECTURE.md` | four places: the black-box table's FastRule row, the Component-vs-Stage table (`Gatekeeper` moves to `llmjudge/`), the Status table (`fastrule/stage.py → fastrule/objects.py`), and the FastRule paragraph |
| `DOCUMENTATION/ENGINE.md` | the per-stage contract reference — X3→X4 and the DEFER classes |
| `llmjudge/ARCHITECTURE.md` | gains the two ported components |
| `DOCUMENTATION/CODE_MAP.md` | module rows: `fast_track.py` added, `objects.py` gone |
| `STATUS.md` | the one-screen "where we are" — CLAUDE.md says it is read first, so it is the worst one to leave stale |
| `CLAUDE.md` | the *"FastRule's verdict is a contract"* section describes the ATOMIC-ITEM EXECUTOR and its gates — the gates leave in phase A. Plus *"Where we are working right now"* |
| `DOCUMENTATION/FEATURES.md` | CLAUDE.md's rule: a shipped change adds its entry in the SAME change |
| `DOCUMENTATION/ENGINE_REWIRE.md` | it carries the open question of folding `run_objects` back where it belongs. **W1 answers it** — close it rather than leaving it open |
| `fastrule/datasets/DATASET.md` | phase C: the gold `item` field, and the corrected regeneration path |
| `dataset/METRICS.md` | phase C: FastRule's product-shape board changes shape when it starts feeding Items |
| `DOCUMENTATION/artifacts/engine_flow.html` + `test_artifact_claims.py` | the published page names FastRule's components; the check goes red and names the file |

**Explicitly NOT updated** — and this needs saying, because "fix the relevant md
files" could reasonably be read as including them:

- **`DOCUMENTATION/ENGINE_AUDIT.md`, `dataset/RESULTS.md`, `dataset/HYPOTHESES.md`** —
  records of runs that actually happened. Rewriting them to match the new design
  would destroy the audit trail and break the rule that *a measured number must
  cite a run that still exists*. They are history; they stay as written.
- **`retired/fastrule-v1/README.md`, `retired/deepsystem/OBJECT_BRAIN_DESIGN.md`** —
  the retiring convention exists so a superseded design stays readable as itself.
- **`DOCUMENTATION/artifacts/explorer.html`** — Gil, this session: *"ignore
  explorer.html, it's stale."* Left alone deliberately, not overlooked.
- `DEVQA.md` and `DOCUMENTATION/FASTRULE2_DESIGN.md` — check what each is before
  editing; a design doc for a superseded proposal is history, a live QA script is not.

**B3's acceptance test** is the wiring's own, not a score:

    pytest tests/unit/test_engine_contracts.py tests/unit/test_engine_flow.py \
           tests/unit/test_panel_agreement.py
    python -m scripts.engine_pipeline_check      # asserts the shape at every boundary

**One trace consequence to expect.** `CHAINS["engine-v3"]` already gives FastRule
the `rule` slot — *"the object-making box is FastRule (rules-first, so its slot is
`rule` and no longer `llm`)"*. Making it pure rules makes that MORE accurate, so no
`CHAINS` edit and no version bump. But the `llm` KIND leaves this stage entirely,
and it does not reappear until LLMJudge emits it in its own phase — so between here
and there, a deep-track trace has no `llm` step at all. That is expected, not a
regression; `test_panel_agreement.py` is in the list above so it says so out loud
rather than being discovered on the phone.

### PHASE C — its own dataset and its own eval metrics

**Not polish. B2 invalidates the instrument**, and that is the finding that sets
this phase's content:

    TODAY   fastrule_shape.py  ──  FastRule(threshold).run(TEXT)      ✔ works
    AFTER B2                   ──  build(ITEM, today=…)              ✘ no Items to feed it

The 7,200 rows are `text` → expected object (`"book haircut every monday at
quarter to nine"` → `create_event`, slots `title`/`time_phrase`/`recurrence`).
The restructured box does not take text. So after B2 **the primary board cannot
run at all**, and FastRule would be unmeasurable exactly when it has just been
rewritten. Phase C's steps, in order:

| # | step | note |
|---|---|---|
| **C0** | **FIX THE GENERATOR — it is broken today** | blocker for everything below |
| C1 | Teach the generator to emit a gold `item` per row | the non-circular route, below |
| C2 | Regenerate; assert the existing 7,200 rows are byte-identical | the new field is ADDITIVE or the split is void |
| C3 | Rewrite `fastrule_shape.py` to feed `build(item)` | the board follows the box |
| C4 | Iterate: read failing rows → fix the implementation → rerun | until Gil is satisfied |

**C0, found 2026-09-09.** `scripts/gen_fastrule_dataset.py:56-57` still points at
`dataset/fastrule/banks/` and `dataset/fastrule/fastrule_7200.jsonl` — the
pre-restructure locations. The banks now live at
`assistant/engine/fastrule/datasets/banks/`, so the generator raises
`FileNotFoundError` at `load_json("fillers.json")`. **The dataset cannot currently
be rebuilt or extended**, which is precisely what C1 needs to do.

This is the **fourth** instance of the rot CLAUDE.md names — after segmentation's
generator, FastRule's primary board and `fit_route_models.py` — and it has the same
cause: a committed output kept working while the thing that produces it did not.
Two consequences worth acting on rather than noting:

- **Move it into the stage folder** as `fastrule/datasets/generate.py`, matching
  `decompose_validate/datasets/generate.py`. Gil's rule is that a stage owns its
  folder and *"the datasets used to improve it"* live there; a generator in
  `scripts/` is the one piece that did not move, which is why it rotted.
- **Mind the `ROOT` trap.** After the move `Path(__file__).parents[1]` means the
  STAGE folder, not the repo root — the same inversion that made the first fix of
  the other three worse. Check what each path resolves to, do not pattern-match.

**C1 — where gold Items come from, and the one route that is not circular.**
The obvious source is wrong: running segmentation + decompose_validate to produce
Items would score FastRule against *what the upstream produced* rather than against
truth, and segmentation is frozen and lossy (265 items lost, 162 invented). Gold
derived that way would bake both in.

The generator does not have that problem, because **it composed the sentence from
the parts in the first place** — DATASET.md: *"the generator does NOT need to guess
what each row means: it filled [the slots] at generation instead of being labelled
after the fact."* It knows which words are the action and which are the time when
it writes the row, so it can emit the gold Item beside the gold object for free.
This is the same trick segmentation's and decompose_validate's datasets already
use, and it keeps the gold independent of every stage's implementation.

The multi-item rows already carry `title_2`/`title_3`, `time_phrase_2`,
`date_phrase_2`/`_3` — so a compound row yields a gold Item *list*, which is what
the non-atomic diagnostic split needs.

**C4's metric is the PAIR, unchanged**: how often it builds, and how right it is
when it does — `handled` and `correct-on-handled`. Either alone is gameable; a
converter that defers everything is never wrong.

### PHASE D — stop and report

FastRule is finished when C4 stops moving and Gil says so. **LLMJudge's own work
does not begin here** — phase A only relocated its code; §1.1-§1.3 of
`llmjudge/PLAN.md` (the veto becoming context, the fallback becoming a DEFER
consumer, the loop) are the next conversation, not the next step.

### Why phase A is a MOVE and B5 is the boundary change

The two used to be one row, and separating them is what makes the demolition
reviewable. **Phase A's acceptance test is that no number moves** — same
`test_fastrule.py`, same product-shape board, because the code is identical and
only its address changed. So any number that moves later is provably the
restructure and not the relocation.

Doing it the other way round — trim first, port after — means the ~118 lines of
`Gatekeeper` and ~150 of the fallback exist only in git history when the port
happens, and "port" becomes "rewrite from memory". The guard that would be lost
first is `_guard_inventions`, which exists because a model once fabricated an event
onto the calendar (cycle 7), and nothing about its new home makes that smaller.

**The full inventory, the four things that go red, and the one dependency edge are
in `llmjudge/PLAN.md` §1.0** — it is written from the receiving end, which is where
the design decisions actually are. Two results from it that change this plan:

- **The reason-class contract STAYS here.** `REFUSAL`/`STRUCTURE`/`INCAPACITY`,
  `_REASON_CLASS` and `reason_class()` (`fastrule.py:103-131`) are the vocabulary
  FastRule's *product* is written in, and three other readers depend on them. The
  earlier reading — that they were shared and would cause a circular import —
  was wrong: their six occurrences in this file are the definition table itself.
- **`_GENERIC_TARGET_RE` leaves.** Every code use is inside a moving piece
  (`Gatekeeper` ×3, `_honour_refusal` ×2), so it is not shared after all. The
  remaining hit is a comment in `fastrule_shape.py`.

### SEGMENTATION IS FROZEN — which changes the instrument, not the plan (Gil, 2026-09-09)

> Gil: *"For now segmentation we leave, I don't want to edit or make changes
> there. The idea is to work on FastRule now, then LLMJudge."*

Nothing in this plan edits `segmentation/`, and two steps need saying out loud so
they are not mistaken for one that does:

- **B4 moves `Atomicity` to `fast_track.py`, a NEW file in `fastrule/`** — it
  does not exist yet. §2c calls atomicity *"segmentation's question"*, which is
  about which stage the QUESTION belongs to, not about where the code goes. The
  fast track is the front door, before any Item exists; that is inside this
  stage's own folder.
- **`fast_propose` lives at `objects.py:92`** and is called once, from
  `engine/__init__.py:246`. Its move is a `fastrule/` internal.
- **Phase C rebuilds this stage's OWN dataset and boards** — `fastrule/datasets/`
  and `fastrule/experiments/`. It reads nothing from `segmentation/` and writes
  nothing to it. The gold Items come from the generator's own templates, which is
  what makes C1 possible while segmentation is frozen.

**The consequence that does bite is which board to trust.** The end-to-end
measurement in TASKS.md stands — 51.6% row accuracy against 99.9% gold-fed, and
the gap is segmentation's. With segmentation frozen, that gap is now a **fixed
ceiling** rather than a thing to fix, so:

| board | fed by | usable while segmentation is frozen |
|---|---|---|
| `fastrule/experiments/fastrule_shape.py` — the 7,200 product-shape set | its own texts, straight into FastRule | ✅ **this is the instrument**. Segmentation is not in the path |
| `scripts/engine_dataset_compare.py` — the whole chain | the real segmenter | ❌ dominated by an upstream loss we have agreed not to touch |

So B1 and all of phase C read the product-shape board, and a whole-engine number is
not evidence about FastRule until segmentation is unfrozen. Reporting one as if it
were would be the "every number needs the dataset, the metric and what it means"
rule broken in the most expensive direction — blaming this stage for another's
loss.

**And it is why phase C is the one that decides when FastRule is done.** The
freeze removes the only other instrument, so *"improve the implementation until we
are satisfied"* means: satisfied on the Item-fed product-shape board, on its train
half, with the test half sealed. There is no second opinion available, which raises
the cost of that board being wrong — hence C2's byte-identity assertion and C1's
insistence that the gold never passes through a stage's implementation.

### The values are computed TWICE today, and this plan is what fixes it

Follow one date through the current chain:

    1  decompose_validate.run()        resolves it -> item.slots        ✔
    2  fastrule.objects.run()          RE-PARSES the text -> intent     ✘
    3  decompose_validate.run_objects()  resolves it AGAIN, from the
                                         words, ONTO the intent         ✘

Step 3 exists because step 2 threw step 1 away. **Once `build` copies the slots,
step 3's value pass has nothing left to do** — and what remains of `run_objects` is
only its non-value rules: targeting, the boundary guards, the observance flag.

That is the same wrinkle `decompose_validate/ARCHITECTURE.md` lists as its finish
line ("FastRule reading `slots`", then "deleting `run_objects`"). It is not a
separate piece of work — **it falls out of B2**, which is the argument for doing
B2 properly rather than bolting slots on beside the parse.

(The 1/2/3 above are the three passes over the same date in today's chain, not the
plan's phases. Only the last sentence refers to a plan step.)

---

## 4 · The rules that keep this from becoming convoluted

The same discipline segmentation's plan carries, because it worked there.

**`FastRule` is one class with one job.** If a new question is not *"can I build
THIS item?"*, it does not belong in it. `Atomicity` leaving is the test case.

**DEFER stays a first-class output with a reason class.** `REFUSAL` /
`STRUCTURE` / `INCAPACITY` is a contract the deep track depends on — a fourth
reason class needs the same discussion a new tag value would.

**Two boards, not one with sections.** A "diagnostic" section is what a board
grows when it is measuring two things.

**No new tier.** Rules → tiny model → DEFER is the tiered decision, applied three
times. A fourth tier is a redesign, not a fix.

**Measure on the TRAIN half; the 2,400 test rows stay sealed** — see
`engine/TRAIN_TEST_SPLIT_CONVENTION.md`, which this dataset is the worked example
of.

---

## 5 · Baseline, 2026-09-09 (train half, 3,200 atomic rows)

Recorded here because the board could not be RUN until today — it pointed at a
pre-restructure path and raised `FileNotFoundError`, as did the script that fits
the logistic weights.

    PRIMARY   handled 69.1%   correct-on-handled 94.2%   deferred 30.9%
    dates     91.7% right     titles naming nothing 0.2%
    times     81.1% right     INVENTED a time 4.4%  (n=294)
    harm      165 over 129 wrong commits
              destructive: complete_todo 16 · update_event 13 · delete_event 5
    non-atomic  75.1% deferred · 19.7% covered · HALF-EXECUTED 72 (5.1%)
    propose     defer rate 52.2%  ·  96 violations

Atomic deferrals by reason — the mining that sets the order above:

    573  below-threshold        45  generic-title
    131  generic-target         43  model-compound
     87  clause-coordination    20  rename-misroute
     83  skip                    7  interrogative-create

Two other candidates once the threshold work lands: **`propose` rows defer only
52.2%** where the target is ~100%, and the **destructive tail** — 16 wrongly
completed todos and 13 wrong event updates are what the harm score is made of, and
they are the errors a user cannot easily undo.
