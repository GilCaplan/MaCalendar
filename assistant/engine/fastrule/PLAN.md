# FastRule — the restructure plan (2026-09-09)

`ARCHITECTURE.md` is how it works today. This is what to change and why.

---

## 1 · The box, and the code that does not match it

**The task, as a black box** (Gil, 2026-09-09):

    IN   one ATOMIC item — (action, time, tag)
    OUT  a committable calendar / to-do object
         ── or ── DEFER + a reason (REFUSAL | STRUCTURE | INCAPACITY)

Four ways the code says something different.

### (a) It takes TEXT, not an item

`FastRule.run(text, current_view)`. Both callers flatten an item back into a
string before handing it over — the deep track calls `run(item.spoken())` — so the
executor never sees `action`, `time` or `tag` separately even though segmentation
worked them out and `decompose_validate` resolved them into values.

### (b) So it re-derives what two stages already decided — and its vocabulary is now far behind

Measured 2026-09-09, whole-command parses of things segmentation reads correctly:

| said | segmentation | the rule parser |
|---|---|---|
| `remind me to call the bank in two hours` | action `remind me to call the bank`, time `today in two hours` | title **`call the bank in two hours`** — the time is IN THE TITLE |
| `book yoga late afternoon` | action `book yoga`, time `today late afternoon` | **nothing** |
| `book the dentist the 20th of november at 3pm` | action, time both right | **nothing** |
| `gym on sundays at 7am` | action `gym`, time `on sundays` | **`RuleParserSkip`** |

Three of four produce nothing at all. Segmentation learned lead times, ranges,
spoken clocks, month-of-ordinals, plural weekdays and one-word cadences on
2026-09-09; `rule_parser.py` knows none of them and never will unless the
vocabulary is taught twice.

**This is the single biggest lead in the folder.** `below-threshold` is 573 of
about 989 atomic deferrals, and a parser that returns nothing scores zero
confidence by construction.

### (c) `Atomicity` belongs to the front door, not to the executor

`FastRule` carries an `Atomicity` component that asks *"one item or several?"* —
which is **segmentation's question**, and is meaningless for a caller whose
contract says the item is already atomic. It exists because the same class serves
two different jobs:

| caller | input | bar | needs Atomicity? |
|---|---|---|---|
| `fast_propose` | the WHOLE command | `RULE_THRESHOLD` | **yes** — it is the fast track's admission test |
| `_parse_item` | ONE item | `SUBITEM_RULE_THRESHOLD` | no — atomic by contract |

And which contract you are in is decided by a string comparison —
`item.text.strip() != state.text.strip()` — rather than by which thing you called.

### (d) The board measures the front door, not the executor

`fastrule_shape.py` feeds whole dataset rows, so the "atomic-item executor" is
scored as a whole-command executor with 1,399 non-atomic rows reported as
"diagnostic". That section exists only because the two jobs share a class.

---

## 2 · The restructure

**One idea: separate the two contracts, and let each be measured on its own
question.** Everything below follows from it.

```
   BEFORE                              AFTER

   fast_propose ─┐                     fast_track.propose(state)
                 ├─► FastRule.run(text)   └─ Atomicity  (admission test)
   _parse_item  ─┘   ├─ Atomicity          └─► FastRule.build(item)
                     ├─ Gatekeeper
                     └─ Scorer          objects.run(state)
                                          └─► FastRule.build(item)
                                                ├─ Gatekeeper
                                                └─ Scorer
```

### 2.1 · `FastRule.build(item) -> object | DEFER` — the executor, and only that

- Takes an **`Item`**, not a string. Reads `action`, `time`, `tag` and the values
  `decompose_validate` already resolved into `item.slots`.
- **No `Atomicity`.** Its contract is that the item is atomic; if that is ever
  untrue, that is segmentation's defect and the item-count board is where it shows.
- One threshold, its own, not chosen by the caller.
- `Gatekeeper` and `Scorer` stay exactly as they are — they are about *this item*
  and they are the two things that make DEFER a first-class output.

### 2.2 · Use what upstream decided, and parse only the rest

The rule parser stops being the source of the date, time and recurrence when the
item already carries them. It keeps its real job: **reading the ACTION** — which
verb, which object, which target record.

> Order of preference, and the reason: `item.slots` was produced by the stage that
> owns values and is measured at 99.9% train / 98.7% sealed on exactly that
> question. The rule parser's own reading is a fallback for items that arrive
> without slots (the front door, where segmentation has not run yet).

This is where the `below-threshold` mass should move, and it is the first thing to
measure rather than assume.

### 2.3 · `fast_track.py` — the front door, with `Atomicity` as its admission test

The whole-command fast path becomes its own small module, and `Atomicity` moves
into it, where the question *"is this one ask?"* is exactly the right one to ask.
It calls `FastRule.build` once it has decided there is a single item.

### 2.4 · `objects.py` splits by concern

453 lines holding: registry access, parser caching, the fast-track proposal,
per-item generation, the LLM fallback, refusal-honouring, invention guards, an
event fallback and slot application.

    fast_track.py   the front door + Atomicity
    objects.py      the per-item loop: FastRule first, the LLM for the rest
    guards.py       _honour_refusal, _guard_inventions, _grounded_title
    (registry and parser caching stay in objects.py — they are one-liners)

### 2.5 · Two boards, because there are two questions

    fastrule_shape.py    the EXECUTOR: atomic items in, handled / correct-on-handled
    front_door.py        the FAST TRACK: whole commands in, committed instantly?
                         wrongly admitted a compound? (today's "non-atomic
                         diagnostic" section, given its own board)

---

## 3 · Order of work

| # | step | why it is first / last |
|---|---|---|
| 1 | **Measure the ceiling of 2.2** — how many `below-threshold` deferrals carry slots the parser failed to read | a number before a refactor. If it is small, 2.2 is not the lever and the order changes |
| 2 | `FastRule.build(item)` + use `item.slots` | the substance; the rest is arrangement |
| 3 | Split `fast_track.py` out, move `Atomicity` into it | now safe, because `build` no longer needs it |
| 4 | Two boards | measure each contract on its own question |
| 5 | `guards.py` | tidying, last, no behaviour change |

**Not in this plan, deliberately:** `stage.py` calls `decompose_validate.run_objects`
at its tail. That is the OTHER stage's rules living here because they need
`item.intent` to exist. It is a real wrinkle and it is that stage's to unwind —
`ENGINE_REWIRE.md` carries it.

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
