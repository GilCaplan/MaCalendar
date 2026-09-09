# Segmentation

**`PLAN.md` is what to do next and in what order** (2026-09-09) — the span
vocabulary is the measured lever, and it carries the rules that keep this folder
from becoming convoluted. This file is how the stage WORKS.

---

## 0 · Where this stage stands — 2026-09-09

**Wired and live**: `IMPLEMENTATION = "fastseg"`, LLMSeg off, 0 model calls.
Verified end to end through `engine.run_transcript`, not inferred from the boards.

| | train (1,051 rows) | **SEALED (660 rows)** |
|---|---|---|
| exact-set (actions) | 76.6% | **75.5%** |
| exact-row (action+time+tag) | 68.2% | **66.5%** |
| **the CUT alone** — right item count | 85.3% | **81.4%** |
| item precision · recall · F1 | 96.8 · 92.4 · 94.6 | **97.0 · 90.6 · 93.7** |
| over-split · under-split | 46 · 108 | **28 · 95** |
| time on a **spoken** time | 91.9% | **93.5%** |
| tag accuracy | 89.7% | **90.2%** |
| A2 — 2 of 3 fields | 91.6% | **93.6%** |
| NO-INVENTION violations | 0 | **0** |
| cost | **0 model calls**, 3.5 s for 1,051 rows | same |
| **downstream, end to end** | **85.9%** rows fully right | — |

**The sealed half was read once, at the milestone, aggregates only** — and it
holds: within 1–4 points of train on every metric and BETTER on five of them
(tag, time-on-spoken, item precision, 2-of-3, over-split rate). The largest gap is
item count, −3.9, which is the CUT — the part deliberately left unfinished. Work
that had been fitted to the train half would not look like this.

### THE BINDING CONSTRAINT IS NOW THE CUT

The span was the lever and it has been spent — time on a spoken time went
73.4% → 91.6%, and A2's most-missed field fell from time (166) to 21. What is left
is the cut, and three readings say so independently:

    1 ask   641 rows (61%)  ->  71.8%      under-split  108 rows
    2 ask   358 rows (34%)  ->  53.9%      over-split    47 rows
    3 ask    52 rows ( 5%)  ->  53.8%

An 18-point gap between single- and multi-ask rows; under-split more than twice
over-split, so the failure is *not cutting* rather than cutting wrongly; and every
worst trap is a compound — `remind_then` 43.8%, `joiner` 46.2%, `and_compound`
46.4%, `texture` 48.6%.

The oracle ablation bounds it: perfect everything on correctly-cut rows is 84.5%,
so the cut caps the row metric no matter how good the rest gets.

### What is DONE

| | |
|---|---|
| the time-span vocabulary | `PLAN.md` Phase 1 — one table, +13.5 exact-row, +34 end-to-end |
| discourse tails | a trailing confirmation is not part of the command (Gil) |
| the `other` tag | `ITEM_KINDS`' fourth value, which nothing had ever produced |
| the dataset | incoherent gold 15 → 0, duplicates 21 → 0, four missing trap classes added, and the generator un-broken |

### What is OPEN, in the order the boards argue for

1. **The CUT** — `PLAN.md` Phase 3. §8.1's enumeration (`walk the dog at 9 and
   2:30`, still 54 malformed items downstream) plus the under-split compounds.
2. **TAG, stuck at 87.3%.** The logistic head is refuted (§6). The error is
   one-directional — event read as task, 116 of 175 — so it needs a different
   idea rather than a better classifier.
3. **§8.3** — the date floor injected as a literal word, costing two workarounds.
4. **Two contract questions from Gil** — where an enumeration header's count goes,
   and whether `other` should carry it. `PLAN.md` §3c.
5. **`old_seg` retirement** — 716 lines inactive with three things still borrowed.
6. **No board for unusable input.** The `other` work was verified on 11 hand
   probes; the audit's 25 cases are all well-formed commands, so nothing in the
   repo measures this.

---

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

No model. ~3 ms per command, 0 model calls over 1,051 rows. **Five phases**, and
the order is measured rather than chosen: DialogUSR (Findings of EMNLP 2022) reports
Split → (Delete + Complete) beating the reverse by 9 exact-match points.

```
   text
     |
     v
  +--------------------------------------------------------------+
  |  0  CLEAN                                                    |
  |     strip_spoken_noise      "um", "so", false starts         |
  |     strip_discourse_tail    "...does that seem right"        |
  +--------------------------------------------------------------+
     |  clean
     v
  +--------------------------------------------------------------+
  |  1  CUT            -> pieces (SUBSTRINGS of `clean`)         |
  |     loop to a FIXED POINT, max 3 rounds:                     |
  |       a. split_clauses + every_part_is_an_ask                |
  |       b. _split_verbless_conjuncts                           |
  |          both sides timed AND the right side has content      |
  +--------------------------------------------------------------+
     |  pieces
     v                          .-------------------------------.
  +----------------------------|  find_time_refs(clean)         |
  |  2  ASSIGN TIME            |  every pattern, then LONGEST-  |
  |     reads the pieces AND   |  FIRST, non-overlapping, with  |
  |     the ORIGINAL string    |  the preposition absorbed left |
  |                            '-------------------------------'
  |     INTERIOR ref -> its own piece                            |
  |     LEADING     -> fills a SLOT any piece left empty         |
  |     TRAILING    -> only a piece with NO time at all          |
  |     the DATE FLOOR: no day named -> "today"                  |
  |     joined by SLOT CLASS (day, then clock), not by position  |
  +--------------------------------------------------------------+
     |  [(action, time), ...]
     v
  +--------------------------------------------------------------+
  |  3  EXPAND ENUMERATIONS                                      |
  |     one activity at SEVERAL times becomes several items      |
  |     "at 9 and 2:30" -> "at 9" + "at 2:30", action COPIED     |
  +--------------------------------------------------------------+
     |  [(action, time), ...]
     v
  +--------------------------------------------------------------+
  |  4  TAG          event | task | review | other               |
  |     engine reader decides; then ONE-WAY vetoes over `event`  |
  +--------------------------------------------------------------+
     |
     v
   [ {action, time, tag}, ... ]
```

**Why phase 3 is separate from phase 1**, which looks like it should be the cut's
job: `cut` returns SUBSTRINGS and phase 2 maps each one back into `clean` by
position (`_locate`). A synthesised piece — "walk the dog at 2:30", assembled from
words that are not adjacent in the text — has nowhere to be located. On
(action, time) PAIRS that constraint is gone, so the expansion happens after the
mapping and `cut` stays the fixed-point loop it is.

### The time-reference vocabulary — one table, eight kinds

`_TIME_PATTERNS` is the single place a new time expression is taught, and **its
order does not matter**: `find_time_refs` collects every candidate from every
pattern and then takes them longest-first, non-overlapping. So `late afternoon`
beats `afternoon` by being longer rather than by being placed above it. That was
once a docstring claim rather than a property of the code, and it cost 31
content-loss rows before it became one.

| kind | slot | example | why the kind exists |
|---|---|---|---|
| `date` | day | `next friday`, `the 20th of november` | |
| `recurrence` | day | `every tuesday and thursday`, `on sundays` | temporal repetition IS the time (Gil) |
| `deadline` | day | `by friday`, `until next tuesday` | it is what distributes over a whole command |
| `clock` | clock | `at 7am`, `ten thirty`, `9 in the morning` | |
| `range` | clock | `from 3 to 4pm`, `between 2 and 4` | ONE reference, not two ends — otherwise the joiner cuts the range in half |
| `lead` | clock | `15 minutes before`, `an hour ahead` | a reminder offset, and it must NOT make a side look independently timed |
| `enum_clock` | clock | `at 9 and 2:30` | a bounded enumeration, expanded in phase 3 |
| `enum_day` | day | `on tuesday and thursday` | the same, over days |

**The two slot classes are the GOLD's**, not this file's invention:
`experiments/generate.py` has `_DAY_SLOTS` and `_CLOCK_SLOTS`, and it puts
`lead_time` and `time_range` on the clock side. Matching it matters more than it
looks — a `lead` falling to `day` would both collide with a real date and satisfy
the `any(_slot(r) == "day")` test that guards the date floor, switching the floor
off silently.

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

### Phase 3 — EXPAND ENUMERATIONS

A **bounded enumeration** of times is SEVERAL items; an **unbounded `every X`** is
ONE item with a recurrence. Gil, 2026-09-08: *"the segmentation is supposed to split
'walk the dog at 9 and 2:30' into two events of walk the dog."*

    walk the dog at 9 and 2:30        ->  walk the dog @ today at 9
                                          walk the dog @ today at 2:30
    gym on tuesday and thursday this week  ->  two events, bounded by "this week"
    gym every tuesday and thursday    ->  ONE event, recurring

The action is **copied, not divided** — which is why the invariant permits a token
in more than one item. The preposition is copied too: "at 9 and 2:30" says `at` once
and means it twice, so a part that lost it gets it back rather than reading
"today 2:30".

**The three decoys survive by their reference TYPE**, not by a special case each:

| | the trailing conjunct is | so |
|---|---|---|
| `walk the dog at 9 and 2:30` | only a TIME (`enum_clock`) | expand |
| `book gym between 2 and 4` | inside ONE `range` reference | untouched |
| `meeting with Sam and Alex at 8` | a NAME, and no time left of the joiner | untouched |
| `buy milk and eggs` | an OBJECT, no time at all | untouched |

That is why the vocabulary work in phase 2 had to land first: once a range is a
single reference, the rule is simply *"two clock-class references, expand"* and the
decoys exclude themselves by counting. Written the other way round it needs a
carve-out per decoy.

### Phase 4 — TAG

`event | task | review | other`. The engine's own reader decides first, so this
module and the tuning experiments cannot disagree about what a review looks like.
Then **every correction is a ONE-WAY VETO over `event`, never into it** — and that
asymmetry, rather than the quality of any single signal, is what makes the phase
work. It has now been measured three times:

| signal | as a verdict (both directions) | as a veto over `event` |
|---|---|---|
| the task-verb lexicon | 82.4% | **87.5%** |
| the logistic `kind` head | 80.4% | 80.1% — refuted either way (§6) |
| `_NOT_CALENDAR` → `other` | never tried; it would swallow tasks | shipped |

**The three vetoes, in order** (`tag()`):

1. **`other`** — not a calendar ask at all (`thanks`, `play some music`,
   `turn on the lights`). A closed vocabulary, because a bare noun phrase is the
   NORMAL way to name an event (`physio`, `standup`) so no shape test can separate
   `physio` from `i love you`. **A stated time overrules the veto**: "turn on the
   lights" is smart-home, "turn on the oven at 6" is a reminder, and the only
   difference is that the speaker scheduled one.
2. **the task-verb lexicon, read at the HEAD VERB** — after skipping the preamble
   (`i need to`, `please`, `um so`). Reading every word let a NOUN decide: "add the
   budget review" and "add a call with Riley" were tagged `task` because `review`
   and `call` are on the list, though the verb is `add`. 56 of 179 errors.
3. **a STATED CLOCK cancels a task verdict** — "walk the dog" is a to-do and "walk
   the dog at 9" is an appointment. Same verb; the speaker named a time. 34 of 179.
   The floor's bare "today" does not count, since the engine wrote it.

Measured on 1,516 gold items: lexicon anywhere **88.6%** → head verb only 89.8% →
+ the clock rule **90.8%**. Live board: **89.7% train, 90.2% sealed**.

The historical measurements that set the shape:
Measured over 1,383 matched items — overriding both ways loses more events than
it gains tasks:

| | accuracy | task recall |
|---|---|---|
| engine tagger alone | 84.7% | 70.7% |
| lexicon overrides everywhere | 82.4% | 78.5% |
| **lexicon only over `event`** | **87.5%** | **89.9%** |

A parser was tried here first and was much worse (65.0%) — see §6.

#### MEASURED AND REFUTED: the logistic `kind` head (2026-09-09)

Run as `experiments/tag_head.py` — **88.7% shipped against 80.4%** for the head,
and worse on every slice including the hand-written rows that cannot be in its
fitting data. It over-predicts `task`, which is precisely the failure the lexicon
experiment below already measured and rejected.

**The lesson generalises past this one arm.** Two independent signals — a task-verb
lexicon and a fitted task/event classifier — both fail the same way on this data,
by calling events tasks. Calendar commands are verb-rooted imperatives, so anything
keyed on the verb leans task; and of 439 items no verb list decides, **349 are
events**. The shipped tagger wins by using the signal only as a ONE-WAY veto, and
that asymmetry is doing the work rather than the signal's quality.

The brief below is kept as the record of what was tried and why.

#### The original candidate (Gil, 2026-09-08)

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

> ### TEST LLMSEG AGAIN WHEN THIS STAGE IS PICKED BACK UP (Gil, 2026-09-09)
>
> Its four measurements against FastSeg were taken when FastSeg was a **much weaker
> segmenter** — exact-row 51.5%, time-on-a-spoken-time 74.2%, no lead times, no
> ranges, no spoken clocks. FastSeg is now 68.2% train / 66.5% sealed with
> time-on-spoken at 91.9%, so **every one of those comparisons is stale in both
> directions**:
>
> - the gap LLMSeg had to close is far smaller, so it has less room to help;
> - but the rows it was breaking may be rows FastSeg now gets right on its own,
>   which is exactly where a verifier stops being able to do harm.
>
> The oracle-gate figure (+3.8%) and the accept-step arithmetic in §6 are the
> numbers to re-derive first. **Board D has never run** — it needs both a FastSeg
> answer and a final prediction, so it only reports with LLMSeg on, which means the
> one board built to answer "does the correction pay for itself" has no data at all.
> Re-run it before deciding anything.
>
> Cheap to check and easy to get wrong by reusing the old conclusion.

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

| metric | start | segment-tuning | **+ span vocabulary (2026-09-09)** |
|---|---|---|---|
| exact-set | — | 61.2% | **76.3%** |
| exact-row | 33.1% | 51.5% | **64.8%** |
| item count — *the cut* | 78.6% | 84.5% | **85.3%** |
| item F1 | 91.2% | 94.1% | **94.5%** |
| over / under split | — | 51 / 110 | **47 / 108** |
| time on a SPOKEN time | 49.1% | 74.2% | **91.6%** |
| row-level 2-of-3 | — | 79.7% | **83.5%** |
| tag accuracy | 83.7% | 87.5% | 87.3% |
| NO-INVENTION violations | 0 | 0 | **0** |
| latency | 3 ms | ~10 ms | **~10 ms**, zero model calls |

The third column is `PLAN.md` Phase 1 — the time-span vocabulary, which was the
oracle ablation's biggest lever (+205 rows) and turned out to be entries in ONE
table plus two one-line changes. **Downstream it moved the pipeline from 51.6% to
86.0%** rows-fully-right (`decompose_validate/eval_metrics/end_to_end.py`), and the
attribution there still shows zero value errors that are the resolver's own.

Traps that moved: `lead_time` 0.0% → 50.0% (72 rows), `time_list_vs_range`
2.8% → 72.2%, `recurrence` 61.1% → 88.9%, `until_through` 33.3% → 64.3%.

**Tag is now the binding constraint** — flat at 87.3% while everything around it
moved, and it is the field A2 reports missed most often (129) now that time has
fallen to 21. That is the case for the `kind`-head candidate in §2 Phase 3.

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
| **the logistic `kind` head is a better TAG** | **NO — 88.7% → 80.4%**, and refuted on all three slices including hand-written rows that cannot be in its fitting data. It over-predicts `task`: task recall rises 90.2% → 92.8% while **event recall collapses 87.7% → 71.4%**, event→task errors 106 → 247. Tried as a decisive-only tier (81.2%) and as a one-way veto over `event` (80.1%) — both worse. `experiments/tag_head.py` |

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

## 7b · What the stage below measures coming out of here (2026-09-09)

`decompose_validate/eval_metrics/end_to_end.py` runs the real FastSeg and then
resolves values, and splits every value error by whose it is. On the 1,924 rows of
that stage's train split:

| | |
|---|---:|
| gold items that reached the next stage | **89.6%** (2292/2557) |
| spurious items produced | **162** |
| items with TWO clock times inside one | **54** |
| items whose action ends in a dangling joiner | **52** |
| value errors downstream caused by different WORDS arriving | **1,445** |
| value errors that were the resolver's own | **0** |

The last two lines are the ones to read together. The downstream stage scores
99.9% when fed gold items and makes **zero** errors of its own on real ones — so
the 51.6% end-to-end row accuracy is this stage's number, not its.

None of this is a new defect: the dangling joiner and the two-clock item are §8.1
and its (a)/(b) split, seen at scale instead of one example. The 265 missing items
and 162 spurious ones are the item-count metric of §6 (FastSeg 77.9% there) from
the receiving end.

---

# 8 · TO FIX — known defects, recorded not repaired

Each is a real case with a real reproduction. They are written down rather than
fixed because the work in flight is elsewhere; this section is the queue.

## 8.1 · RESOLVED 2026-09-09 — a bounded enumeration of times must SPLIT

> **Done.** Phase 3 (`_expand_enumerations`) implements it and the five gold rows
> were corrected in the same change; the trap was renamed from
> `two-times-one-activity`, whose NAME was the mistaken premise, to
> `time-enumeration`. It scores 66.7% now (0.0% before) — the remaining row fails
> on the action wording, not the cut. **The record below is kept as written**,
> because it called the fix, the decoy risk and the board's dip in advance and that
> is worth being able to check.

### The original entry (Gil, 2026-09-08)

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

### Live evidence, measured end to end (2026-09-09)

`"walk the dog at 9 and 2:30"` produces this from THIS stage:

    [('walk the dog and', 'today at 9 2:30', 'task')]
       ^^^^^^^^^^^^^^^^^^         ^^^^^^^^^^
       the joiner leaked          TWO clocks, one item

and the engine then commits `create_todo 'walk the dog'` **plus**
`create_event 'Untitled Event'` at 14:30 — neither of the two events the sentence
names.

**Isolate it and the blame is unambiguous.** The single case is flawless, so
nothing downstream is at fault:

| said | items | committed |
|---|---|---|
| `walk the dog at 9` | `[('walk the dog', 'today at 9', 'task')]` | event, 9–10 AM ✓ |
| `walk the dog at 2:30` | `[('walk the dog', 'today at 2:30', 'task')]` | event, 2:30–3:30 PM ✓ |
| `walk the dog` | `[('walk the dog', 'today', 'task')]` | todo ✓ |
| **`walk the dog at 9 and walk the dog at 2:30`** | two items | **two correct events** ✓ |
| **`walk the dog at 9 and 2:30`** | **one malformed item** | **todo + `'Untitled Event'`** ✗ |

The fourth row is the one that settles it: repeat the verb and the machinery
handles it perfectly. So this is not a hard problem downstream — it is the CUT
declining to split, and once one item carries two clocks no later stage can
recover, because one item is all the words it has.

### TWO defects here, and they are independently fixable

**(a) The joiner leaks into the action.** `'walk the dog and'` is wrong on any
reading — "and" belongs to neither the action nor the time. This is a bug even if
the keep-decision stands, and it is the smaller of the two.

**(b) The keep-decision itself.** §2 Phase 1 lists this sentence as a deliberate
KEEP ("nothing is left on the right"), and that is the rule §8.1 says is wrong: a
bounded enumeration of times must SPLIT. Note the tension is real rather than an
oversight — the same rule correctly keeps `take the tablets at noon and at six`
whole, so the fix has to distinguish an enumeration of times for ONE action from
a decoy, not simply drop the condition.

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
