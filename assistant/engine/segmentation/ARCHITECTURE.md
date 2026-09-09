# Segmentation

The engine's second step. It takes one spoken command and returns the separate
things the speaker asked for. Everything downstream — decompose, generate, the
calendar write — operates on what this step decides, so a boundary drawn wrong
here cannot be recovered later.

---

## 1 · The component as a black box

```
        "tomorrow gym at 7 and meeting at 11"
                        |
                        v
        +---------------------------------+
        |          SEGMENTATION           |
        |                                 |
        |   FastSeg  --->  LLMSeg         |
        |      \             /            |
        |       \           /             |
        |        v         v              |
        |          ACCEPT                 |
        +---------------------------------+
                        |
                        v
     [ (gym,     "tomorrow at 7",  event),
       (meeting, "tomorrow at 11", event) ]
```

**Input** — one command as text, already repaired by `ingest`.

**Output** — a list of ITEMs. An item is exactly three strings:

| field | meaning |
|---|---|
| `action` | the item's words with the time reference removed — verb, object, people, places, quantities, everything else kept |
| `time` | the time reference for this item, **copied as spoken** |
| `tag` | `event` \| `task` \| `review` |

Three properties the component guarantees, each enforced by code rather than
by intention:

**CAPTURE, DO NOT RESOLVE.** `time` holds words, never a date, a range or a
clock reading. `"next friday"` stays `"next friday"`. Resolution happens
downstream in `decompose_validate` (`relative_dates` + `_rule_past_date_bump`),
which reads the raw transcript — so `"the 15th"` on the 20th becomes the 15th
of *next* month without Segmentation knowing anything about it.

**THE INVARIANT.** For every item, `tokens(action) ∪ tokens(time)` covers every
content token of that item and contains nothing absent from the input. A token
may appear in two items — that is what a shared modifier is. One definition,
`fastseg/invariant.py`, imported by the runtime guard, the scorer and the
dataset generator. It was three copies once and they drifted: the guard
rejected a correct model answer for defaulting an untimed item to `"today"`,
which is exactly what the spec tells it to do.

**THE TAG NAMES THE SURFACE, NOT THE OPERATION.** `"cancel the dentist"` is
`event` because it concerns the calendar. Whether an item creates, edits or
deletes is decided later.

---

## 2 · FastSeg — the deterministic half

No model. ~10 ms per command. Three phases, and the order is measured rather
than chosen: DialogUSR (Findings of EMNLP 2022) reports Split → (Delete +
Complete) beating the reverse by 9 exact-match points.

```
   text ──► 1 CUT ──► pieces ──► 2 ASSIGN TIME ──► 3 TAG ──► items
                          ▲                │
                          └────────────────┘
                        both phases see the ORIGINAL string
```

### Phase 1 — CUT

Delimiters, then the clause parse, **looped to a fixed point** rather than run
once. A fixed point is also the stopping test the literature uses: DisSim
recurses a rule set until no rule fires, ADaPT on executor failure, DecomP on a
size check. None of them trains an "is this atomic?" classifier, and the one
paper that did reports 54–66% on the decision.

A second tier handles what a clause splitter structurally cannot see — the
**verbless conjunct**:

> `set up physical therapy at 9:15 and birthday dinner at midnight`

The second conjunct is a bare noun phrase, so nothing marks it as a clause. The
evidence used instead of a verb: **both sides carry their own time reference,
and the right side has content that is not part of its time.** That second
condition is load-bearing — it is what keeps the decoys whole:

| text | verdict |
|---|---|
| `set up physical therapy at 9:15 and birthday dinner at midnight` | split — `birthday dinner` survives removing its time |
| `walk the dog at 9 and 2:30` | keep — nothing is left on the right |
| `take the tablets at noon and at six` | keep — nothing is left |
| `meeting with Sam and Alex at 8` | keep — the left side carries no time |

### Phase 2 — ASSIGN TIME

Reads the pieces **and** the original string together, because once a command
is cut, a splitter working piece-by-piece can no longer see that a leading
"tomorrow" covers the second piece too.

Time expressions are found longest-first. That used to be a claim in a
docstring rather than a property of the code — the pattern list is grouped by
kind, so bare `today` outranked `a week from today` and stranded "a week from"
in the action. Matches are now collected and taken longest-first so pattern
order cannot silently decide the answer.

**The two edges do not behave the same.** This asymmetry was found by
generating gold from templates, not by reasoning:

> **LEADING** scopes forward over the whole command, per slot class — a day and
> a clock are separate slots, so a leading day still reaches an item that has a
> clock but no day.
>
> **TRAILING** attaches to its own clause, reaching back only to an item with
> no time at all.

| text | times | why |
|---|---|---|
| `tomorrow gym at 7 and meeting at 11` | `tomorrow at 7` · `tomorrow at 11` | leading day, per slot |
| `gym session at 7, tomorrow meeting at 10` | `today at 7` · `tomorrow at 10` | interior — no backscope |
| `submit the grades and prepare the slides by friday` | `by friday` · `by friday` | trailing; item 1 had no time |
| `do i have anything this weekend and book the haircut at 3:45` | `this weekend` · `today at 3:45` | trailing clock stays put |

Distributing per slot class in *both* directions gave the question
`this weekend at 3:45`. The asymmetry also matches English: pre-posed temporal
adverbials scope over the utterance, post-posed ones attach to the nearest
clause.

**The date floor** — the day defaults to `today`, the clock is never invented.
Nothing said → `today`; a clock only → `today at 7`; a day only → `tomorrow`.

### Phase 3 — TAG

The engine's own reader decides first, then **one** correction is applied in
**one** direction: the lexicon may talk it out of `event`, never into it.
Measured over 1,383 matched items — overriding both ways loses more events than
it gains tasks:

| | accuracy | task recall |
|---|---|---|
| engine tagger alone | 84.7% | 70.7% |
| lexicon overrides everywhere | 82.4% | 78.5% |
| **lexicon only over `event`** | **87.5%** | **89.9%** |

A parser was tried here first and was much worse (65.0%) — see §6.

#### Candidate, not yet tried: the logistic `kind` head (Gil, 2026-09-08)

The engine already carries a trained **event/task classifier** —
`classifier.py`'s `KindFeatures` + `LogisticModel`, weights in
`intent/route_model_weights.json` — and FastRule consults it as a fallthrough
tier. TAG is the same question, so it is worth measuring here instead of a
hand-built reader plus a lexicon override.

**What it would have to beat: 87.5% accuracy / 89.9% task recall** on the 1,383
matched items above. Cheap enough to be worth the test — inference is a
hand-written dot product over a float list, no ML dependency, well inside
FastSeg's 0.002 s/row.

Three things to get right before believing any number it produces:

- **It has two classes; TAG has three.** `kind` is event/task, and `review` is
  absent. The review test is deterministic and deliberately SHARED with LLMSeg
  so the two cannot disagree about what a review looks like — so the shape to
  test is *review pre-check first, then the head decides event vs task*, not a
  three-class head.
- **It was fitted on a different dataset** — `fastrule_7200.jsonl`'s train half.
  Scoring it on segmentation's items is therefore a genuine cross-dataset
  generalisation test, which is a point in its favour, but the two corpora
  overlap in provenance (both are built from the same filler banks), so the
  comparison must be run on segmentation's own held-out half or it will read
  high for the wrong reason.
- **Compare it against the RIGHT baseline.** Not the engine reader alone
  (84.7%) — against reader + lexicon-over-`event` (87.5%), which is what ships.
  Beating the weaker number would be a measurement artifact, and that is exactly
  the mistake the table above exists to prevent.

Not a design change: TAG's contract (`event | task | review`) is unchanged, and
swapping the reader for a Component inside the stage is invisible to the trace.

---

## 3 · LLMSeg — the model half, **OFF BY DEFAULT**

> ### The flag
>
> ```python
> llmseg.ENABLED          # False unless MACALENDAR_LLMSEG is set
> segment(text)                      # -> FastSeg only, route "fastseg-only"
> segment(text, use_model=True)      # -> forces the model on, for experiments
> segment(text, use_model=False)     # -> forces it off
> ```
>
> `MACALENDAR_LLMSEG=1` turns it on for one command. **The default is OFF**
> (Gil, 2026-09-08). LLMSeg stays wired, tested and kept — it simply does not
> run unless something asks for it.
>
> **Any board measuring LLMSeg must pass `use_model=True` explicitly.** If a
> measurement inherited the default it would report FastSeg's numbers under
> LLMSeg's name, and that class of silent-measurement bug has already bitten
> this module twice.
>
> **When Segmentation is promoted over `old_seg`, this becomes a config
> setting** — `engine.segmentation.llmseg: off` in `config.yaml`, mirrored into
> `config.example.yaml` per the project convention. It is a module flag today
> only because the component is not yet wired to `config.py`.
>
> **Why it is off**, in one line: measured four independent ways against
> FastSeg on 571 trap-stratified rows, every one came back negative, and the
> most decisive test used a prompt written *after* an audit fixed five defects
> in the old one — so the prompt was not the problem. Numbers in §6.



One schema-shaped call to the local llama3.1:8b, anchored on FastSeg's
proposal, followed by two deterministic guards.

```
   FastSeg proposal ──► prompt ──► model ──► TAG COERCION ──► ACCEPT ──► items
                                                                 │
                                            invariant fails ─────┘──► keep FastSeg
```

**The protocol was measured, not assumed.** Against llama3.1:8b on 14 cases:

| | |
|---|---|
| V1 "No Change" or a correction | 5/14 |
| V2 V1 + a four-point checklist | 1/14 — it narrates |
| **V3 no judgement, always emit, we diff** | **11/14** |
| V6 V3 with no proposal shown | 8/14 — the anchor is worth +3 |

Asking an 8B "is this right?" invites the accept bias — V1 waved through 4 of
7 broken inputs, the same self-assessment over-estimate ADaPT measured at 30+
points. Taking the decision away from the model fixes it.

**TAG COERCION** snaps whatever string comes back to `event|task|review`
(exact → synonym → word scan → closest match → FastSeg's tag), so the tag is
structurally correct rather than trusted.

**ACCEPT** takes the model's answer only if it satisfies the invariant. Its
commonest failure is deleting a shared `"tomorrow"` instead of distributing it,
or dropping `remind` from `"remind me to X"` — 12 of 37 rejections in one run.

**The prompt is V4, and `experiments/check_prompt.py` proves it still agrees
with the spec.** V3 was audited and found to teach five things the gold no
longer accepts: the symmetric edge rule (12.2% of rows), a missing date floor
in an example that contradicted another example in the same prompt, a dropped
preposition, a half-stated floor rule, and nothing at all about what the tag
means for a delete. Every one graded the model **wrong for obeying its
instructions**, which makes any measurement taken against V3 worthless as
evidence about the model. The check parses the shipped examples and asserts
each satisfies the invariant, the floor, preposition capture and the tag
vocabulary — the same idea as `test_artifact_claims.py` keeping published pages
honest about the code.

---

## 4 · The datasets — `datasets/`

**1,694 rows**, split BY FAMILY so a family never straddles the boundary.

| | rows | source | traps |
|---|---|---|---|
| TRAIN | 1,040 | 960 generated / 80 hand-written | 44/44 |
| **TEST (sealed)** | 654 | 594 / 60 | 44/44 |

Leakage: 0 family overlap, 0 exact-text overlap; 11 test rows (1.8%) share a
gold action-set with train — the one blemish, recorded rather than hidden.

**1,554 rows did not start from scratch.** `assistant/engine/fastrule/datasets/banks/
complex_patterns.json` already held 321 templates built for a different board,
and they carry exactly what segment gold needs: an `atomic` flag and **named
slots**. Because the template says `{date}`, the action/time split is *known by
construction* rather than inferred — a regex over rendered text would just be
FastSeg marking its own homework. 187 templates are atomic and **74 of those
contain a joiner** ("buy {item} and {item2}"), which makes them decoy rows a
naive splitter fails: the most expensive kind to write by hand.

**62 families are excluded and reported, never guessed.** 38 are `propose`
("should i book X?"), which asks for advice and has no honest label in a
three-tag contract.

**Known gaps.** 13 traps have fewer than 4 rows in the whole train pool, and
`review` is thin (61 items). The next expansion should target thin traps, not
more volume from the same templates.

---

## 5 · The evaluation — `experiments/score.py`

**Six boards, never one number.** A single figure hides *which way* a run is
failing, and the two ways cost very different amounts.

| board | what it answers |
|---|---|
| **A boundaries** | exact-set, exact-row, item count (*the cut alone*), item P/R/F1, over- vs under-split **kept separate and never summed** |
| **A2 partial credit** | 2 of 3 fields, action judged by *kind* of difference — plus which field is being missed |
| **B action/time** | the invariant (invention · loss, both MUST be 0) + time on a *spoken* time vs the `today` default |
| **C tag** | accuracy, per-class P/R/F1, confusion |
| **D verifier** | does the model's correction pay for itself |
| **E cost** | model calls/row, latency/row |
| **F composition** | what the score was computed *over* — ask-count spread, per-trap breakdown |

**`exact-row`** is the product-level number: the predicted decomposition, as a
multiset of `(action, time, tag)`, equal to gold. All-or-nothing — one wrong
tag on one item of a two-item command sinks the row.

**`A2` exists because the action boundary is a judgement call.** A similarity
threshold was tried first and **rejected on measurement**: at Dice 0.80 it
admitted 140 real errors while rejecting 85 genuine boundary calls, because the
two populations overlap and no cutoff separates them. Cosine and Jaccard invert
the same way — the catastrophic under-split scores *higher* than the harmless
boundary call, because overlap measures penalise proportionally and a short
action is punished harder for the same absolute error.

> So the test is not *how much* differs but *what kind* of token differs:
> **the action is correct when every token the two readings disagree on is a
> TIME token.** No threshold, and it uses only data already in the items.

Report the missed-field breakdown beside the 2-of-3 rate, always: "2 of 3" can
be passed by failing the *same* field every time.

**Sampling is trap-stratified** (`MIN_PER_TRAP` first, then proportional). The
first prompt slice was proportional and left 13 of 44 traps EMPTY — including
`serial-verb` and `name-coordination`, the shapes most likely to *refute* the
hypothesis being tested. Measuring a hypothesis on a set that excludes its
failure mode is not a measurement.

---

## 6 · Results

FastSeg alone, segment-tuning **TRAIN** half (1,040 rows). The sealed 654 rows
have never been scored.

| metric | before | after |
|---|---|---|
| exact-row | 33.1% | **51.5%** |
| item count — *the cut* | 78.6% | **84.5%** |
| item F1 | 91.2% | **94.1%** |
| time on a SPOKEN time | 49.1% | **74.2%** |
| tag accuracy | 83.7% | **87.5%** |
| task recall | 70.7% | **89.9%** |
| NO-INVENTION violations | 0 | **0** |
| row-level 2-of-3 | — | **79.7%** |
| latency | 3 ms | **~10 ms**, zero model calls |

### Where the remaining headroom is — oracle ablation

| give FastSeg the gold for… | exact-row | gain |
|---|---|---|
| nothing | 51.5% | — |
| perfect tag | 59.2% | +82 rows |
| perfect action only | 56.6% | +55 |
| perfect time only | 52.7% | +14 |
| **perfect SPAN (action+time together)** | **71.1%** | **+205** |
| perfect everything on correctly-cut rows | 84.5% | +345 |

**The span is the biggest lever, and the singles understate it badly.** The
errors are coupled: a mis-cut span leaves residue in the action *and* truncates
the time, so fixing either field alone still fails the row. The work is
multi-word fuzzy time expressions — `late afternoon`, `first thing in the
morning`, `9 in the morning`.

### Refuted — recorded so they are not re-attempted

| hypothesis | verdict |
|---|---|
| a spaCy POS/dependency rewrite fixes the tagger | **NO** — 65.0% vs 84.7%. Calendar commands are VERB-rooted imperatives, so "root is a VERB → task" calls `add vet appointment to my calendar` a task. Of 439 items no verb list decides, **349 are events**. |
| the destination distributes like an edge time | **NO** — +15 blanket, −23 scoped |
| gating LLMSeg to the right rows rescues it | **NO** — it fixes 6 and breaks 16, so an *oracle* gate is worth +3.8% |
| the model should do the cutting, FastSeg the copying | **NO** — item-count 83.9% → **57.3%**, breaks 132. Predicted from DialogUSR's cut-vs-copy gap, but that compares a model's cut to its *own* copy, not to a tuned deterministic cutter. |
| a similarity threshold can score the action | **NO** — see §5 |

### LLMSeg's standing — turned OFF, on four measurements

| test | result |
|---|---|
| V3 full rewrite | −10 rows — **void**, the prompt taught a superseded rule on 12.2% of rows |
| `boundaries` — model cuts, FastSeg copies | exact-row −17.3pp, item-count −26.6pp, **NO-INVENTION 0 → 4** |
| `count` — model returns only a digit | −2.4pp, breaks 19 |
| **`v4-full` — every prompt defect fixed** | **−12pp; fixes 1, breaks 42** |

Full board for `boundaries`, all twenty metrics, 571 identical rows:

| metric | FastSeg | +LLMSeg | |
|---|---|---|---|
| exact-set / exact-row | 61.1% / 51.1% | 40.8% / 33.8% | WORSE |
| right item count | 83.9% | 57.3% | WORSE |
| item P / R / F1 | 95.8 / 92.5 / 94.1 | 51.5 / 94.7 / 66.7 | WORSE |
| rows over- / under-split | 33 / 59 | **238** / 6 | WORSE |
| A2 rows ≥ 2 of 3 | 78.3% | 53.6% | WORSE |
| NO-INVENTION items *(must be 0)* | **0** | **4** | WORSE |
| NO-LOSS items *(must be 0)* | 89 | 226 | WORSE |
| tag accuracy | 86.5% | 85.4% | WORSE |
| seconds / row | 0.01 | 6.30 | WORSE |

Read the "better" cells carefully: recall rises only because it over-splits 238
rows, and precision falls 44 points to pay for it. **Over- and under-split are
never summed** — an over-split makes garbage immediately, an under-split gets
two more chances downstream, so trading one for the other is not a win.

`v4-full` is the one that settles it. Every prompt defect fixed, examples
verified mechanically by `check_prompt.py`, and it still fixed **one row in
358**:

```
put do the laundry and return the rental car on my list
```

### old_seg vs FastSeg — the promotion question, measured

294 trap-stratified TRAIN rows, judged only on what BOTH systems were built to
do. `old_seg` emits `(text, kind)` and never separated time from action, so
`time` and `exact-row` are N/A for it **by design** — it is not scored on them,
and its gold is rebuilt as `action + time` (the span it should have produced),
minus the date floor, which is a value the labelling adds rather than a word the
speaker said.

| | item count | item F1 | tag acc | over / under | sec/row |
|---|---|---|---|---|---|
| `old_seg` (shipped) | **86.1%** | **95.1%** | 84.6% | 21 / 20 | **0.903** |
| FastSeg (new) | 83.7% | 94.0% | **87.2%** | 19 / 29 | **0.002** |
| delta | −2.4% | −1.1% | +2.6% | | **551× faster** |

**Read the cost column first, because it changes what the rest means.**
`old_seg` falls back to the LLM whenever its deterministic pass finds nothing,
so its 86.1% is a **model-assisted** score. FastSeg is within 2.4 points of it
with **zero model calls**, at 551× the speed — and it additionally produces the
`time` field, which `old_seg` does not do at all.

So FastSeg is **not yet a clear win on boundaries alone**, and that is the
honest state of the promotion question: it trades ~2 points of cut accuracy for
a 551× latency cut, a better tagger, and a field the old stage never had. The
+205-row span headroom in the oracle table above is what would settle it.

### Three limits of that conclusion — recorded so it can be revisited honestly

1. **The corpus is 92% template-generated**, from the very templates FastSeg
   was tuned against. That is a structural bias toward the deterministic side.
2. **One model, one protocol.** llama3.1:8b rewriting a proposal item-by-item.
   This does not show that no model belongs in Segmentation.
3. **The strongest case for a model is a population this dataset cannot
   measure.** A corpus of templates plus hand-written traps cannot contain
   phrasings nobody thought of, and that is exactly where a model would earn
   its keep. `scripts/weekly_review.py` on real usage is the instrument for
   that, and per CLAUDE.md real usage **outranks** every dataset number.

The `v4-full` run was stopped at 458 of 571 rows, so the generated-vs-handwritten
split is **untested** — every hand-written row sorts after the generated ones
and none was reached. If that split is ever wanted, the cache makes it cheap to
finish.

---

## 7 · Layout

```
segmentation/
    ARCHITECTURE.md     this file
    fastseg/            the deterministic half + invariant.py
    llmseg/             the model half + prompts/
    old_seg/            the SHIPPED stage, kept until Gil promotes the new one
    datasets/           1,694 rows, train/test split by family
    experiments/        scorer, boards, generator, and every study above
```

**`old_seg` is still the stage the engine runs.** FastSeg and LLMSeg are proven
on their own dataset first, per STAGE ISOLATION mode; promotion is a separate,
deliberate change. Note the coupling honestly: `fastseg` currently *imports*
`old_seg` for `_kind_of` / `_enforce_pinned_kinds`, so the two are not yet
independent.

---

# 8 · TO FIX — known defects, recorded not repaired

Each is a real case with a real reproduction. They are written down rather than
fixed because the work in flight is elsewhere; this section is the queue.

## 8.1 · A bounded enumeration of times must SPLIT (Gil, 2026-09-08)

**The gold is wrong, and so is the code.**

```
'walk the dog at 9 and 2:30'                                -> gold 1, should be 2
'take the tablets at noon and at six'                       -> gold 1, should be 2
'guitar practice at 11 and 4 tomorrow'                      -> gold 1, should be 2
'gym session on tuesday and thursday this week'             -> gold 1, should be 2
'can you add the stand up meeting on monday and wednesday'  -> gold 1, should be 2
```

All five carry the trap `two-times-one-activity`, which is itself the mistaken
premise — **they are one activity happening SEVERAL TIMES, which is several
events.** Gil: *"the segmentation is supposed to split 'walk the dog at 9 and
2:30' into two events of walk the dog."*

**The rule that separates it from recurrence:**

> A **bounded enumeration** of times is SEVERAL items.
> An **unbounded `every X`** is ONE item with a recurrence.

```
"walk the dog at 9 and 2:30"              TWO events  — two instances
"gym on tuesday and thursday this week"   TWO events  — bounded by "this week"
"gym every tuesday and thursday"          ONE event, recurring
```

Recurrence is a FEATURE of an item, not more segmentation — and it is
`decompose_validate`'s to fill, not this stage's.

**It is implementable without endangering the must-not-split decoys**, because
the trailing conjunct's TYPE separates them, and `find_time_refs` already
identifies the type:

| | trailing conjunct is | verdict |
|---|---|---|
| `walk the dog at 9 and 2:30` | only a TIME | split |
| `meeting with Sam and Alex at 8` | a NAME | keep |
| `buy milk and eggs` | an OBJECT | keep |

Today the verbless-conjunct tier keeps all three whole via "the right side has
no content of its own". That guard is right for the last two and wrong for the
first.

**Expect the board to DROP when the gold is fixed and before the rule lands** —
those five rows currently pass and will start failing. That is the gold getting
more correct ahead of the code, not a regression.

**Fallback if this is missed:** Gil, 2026-09-08 — if segmentation fails to split
a multi-DAY enumeration, `decompose_validate` should read it as a recurrence
rather than lose the second day. A degraded answer, but not a lost one.

### Live evidence, 2026-09-08

Measured end to end through the real engine, `"walk the dog at 9 and 2:30"` is
wrong in BOTH configurations of the stage below it:

| decompose_validate's legacy splitter | result |
|---|---|
| enabled | `create_todo 'walk the dog'` **plus** `create_event 'Untitled Event'` at 14:30 |
| disabled | one `create_event` titled `'dog'` at 14:30 — the 9 o'clock is lost entirely |

Neither is the two events the sentence names, and note that the downstream stage
cannot fix it either way: with one item it has one item's words, and with a
garbage title it has a garbage title. **This is the argument for fixing the split
here** rather than compensating for it later — §8.1's five gold rows are the same
defect seen from the dataset side.

## 8.2 · The month can be severed from its ordinal

Recorded rather than fixed, because the current job is wiring the engine
together, not improving FastSeg (Gil, 2026-09-08). Each is a real case with a
real reproduction.

### The month can be severed from its ordinal

**Input**

```
add gym on tuesday at 6am and add yoga on tuesday at 7pm
and add my conference on the 20th of November at 9am
```

**What Segmentation returns for the third item**

```
text = 'add my conference of November'      <- the month is in the ACTION
time = 'on the 20th at 9am'                 <- and missing from the TIME
```

**What went wrong.** `_TIME_PATTERNS` knows `November 20` but not
`the 20th of November`, so the bare-ordinal pattern claims `the 20th` and
`of November` is left behind in the action. No token is lost — `spoken()`
returns `add my conference of November on the 20th at 9am` — but the month has
moved *before* the ordinal, and the title now reads "conference of November".

**Consequence.** The event books in the CURRENT month.
`tests/integration/test_date_sanity_fixes.py::
test_a_relative_date_repeated_for_two_events_does_not_swallow_a_third` fails
because of this — **it is a NEW red introduced by the wiring**, not one of the
three pre-existing failures, and it should be counted as such.

**The fix, when we get to it**, is a pattern, not a downstream repair: capture
`the 20th of November` as one span. That stays inside the capture contract —
it adds no information and resolves nothing. A downstream fix cannot help here,
because by then the month is already part of the title.

> **Distinguish this from the case that is NOT a gap.** "the 20th" with no month
> at all is correctly captured as `on the 20th` and correctly resolved
> downstream to the next future 20th. Segmentation captures words; deciding
> WHICH 20th is `decompose_validate`'s job and it already works.

## 8.3 · The date FLOOR is injected into `time` as a WORD (found 2026-09-08)

`fastseg.py`'s floor block writes the literal string `"today"` into an item's
`time` when the item names a clock but no day:

```python
if not any(_slot(r) == "day" for r in mine):
    time_str = f"today {time_str}".strip()      # fastseg.py:352
```

**This resolves, and segmentation's contract is CAPTURE, DO NOT RESOLVE.** The
floor is a value-level default, and `decompose_validate` owns it —
`checks.date_floor` applies it there, from the anchor, without putting a word in
the item that nobody said.

### Why it is worth fixing rather than living with

It makes a FLOORED day indistinguishable from a SPOKEN one for every consumer
downstream, and two separate workarounds already exist for that:

1. `Item.spoken()` filters the injected `"today"` back out, and says so:
   *"pasting that in would put a word in the title that nobody uttered."*
2. `validate._resolve_onto_intent` now strips it again at this stage's boundary,
   because a carried day could not tell it had permission to fill a gap.

**The live failure it caused**, from the audit corpus:

    "set a meeting tomorrow at 1 pm, another one at 4 pm and then pizza
     at 6:30 pm tomorrow"

Item 2 arrives as `time="today at 4 pm"`. The day was never spoken — the
transcript contains no `"today"` at all — but it LOOKS spoken, so the leading
`"tomorrow"` cannot carry forward and the event books on the wrong day. Both
workarounds above exist solely to undo this one injection.

### What it costs to fix

The reason it was added is in the code comment: FastSeg emitted the bare form
while the tuned LLMSeg prompt taught the floored one, so **the two halves
disagreed on every clock-only item and the accept step paid for it each time**.
Note that LLMSeg is OFF by default (§3), so today the injection serves an inert
component while an active stage pays for it.

So the fix is not a one-line deletion:

- **Segmentation's own gold encodes the floored form.** `experiments/generate.py`
  inserts `("day", "today")`, and `experiments/check_prompt.py` asserts
  *"FLOOR requires 'today {t}'"*. Removing the injection means regenerating the
  dataset and re-reading the boards — the `time_default_ok` metric in
  `compare_boards.py` is scoring exactly this.
- **LLMSeg's prompt teaches the floored form.** If both halves must agree, the
  normalisation belongs at LLMSeg's ACCEPT step (strip a floored `"today"` from
  what the model returns) rather than in FastSeg's output, so the bare form is
  what both emit.
- **`Item.spoken()`'s filter can then go**, along with this stage's boundary
  strip — which is the test that the fix actually landed: two workarounds
  disappear.

Not urgent — the boundary strip contains it — but it is a contract violation, and
it has already cost one live bug and two workarounds.
