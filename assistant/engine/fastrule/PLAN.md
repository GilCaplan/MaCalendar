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
most plausibly sits. Step 1 below measures it before anything is moved.

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
| `Gatekeeper` + `_which_store_holds` + `_names_something_real` | ~118 | ❌ **LLMJudge's** (Gil) |
| the LLM fallback — `_parse_item`'s model half, `_honour_refusal`, `_grounded_title`, `_guard_inventions`, `_llm_trace` | ~150 | ❌ **LLMJudge's** (Gil) |
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
| `Gatekeeper` + its two DB helpers | **LLMJudge**, as prompt CONTEXT (Gil) | it is a *reading* judgement — "this would execute the wrong thing" — and the model is the thing that can resolve it. As a veto it could only refuse; as context it can be answered |
| the LLM fallback + its guards | **LLMJudge** | Gil: *"if issue it tells the LLMVerify."* FastRule reports `DEFER(INCAPACITY)` and carries its partial parse; the model call happens where the model lives |
| `fast_propose` + `Scorer` | the fast track / orchestrator | "confident enough to COMMIT?" is a commit decision. FastRule builds; something else decides when to write |
| the `run_objects` call | `decompose_validate` | already its own stage's finish line |

**What is left is small and testable on its own**: a pure function from one `Item`
to one object, with no model, no database, and no opinion about whether to commit.
That is what makes it measurable against its own task — which is the other half of
what this restructure is for.

## 3 · Order of work

| # | step | why it is first / last |
|---|---|---|
| 1 | **Measure the ceiling** — of the 573 `below-threshold` deferrals, how many carry slots the parser failed to read | a number before a refactor. If it is small, the converter is not the lever and this order changes |
| 2 | `FastRule.build(item)` — COPY the slots, parse only operation/title/people/target | the substance; everything else is arrangement |
| 3 | Move `Atomicity` to `fast_track.py` | safe once `build` no longer needs it |
| 4 | Move `Gatekeeper` + the LLM fallback to **LLMJudge** | the biggest move, and it changes a STAGE BOUNDARY — so it goes after the converter works, never beside it |
| 5 | Two boards | measure each contract on its own question |
| 6 | Delete what is now dead | `_honour_refusal` and the invention guards go with the model call |

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
separate piece of work — **it falls out of step 2 of this plan**, which is the
argument for doing step 2 properly rather than bolting slots on beside the parse.

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
