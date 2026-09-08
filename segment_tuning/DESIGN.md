# Segment tuning — the design, for confirmation

**Status: NOT IMPLEMENTED. Gil asked to confirm the design before any
implementation or testing.** This file is the thing to argue with.

The premise (Gil, 2026-09-08): treat segmentation as a supervised ML problem
where **the hyper-parameter is the code**. A fixed dataset, fixed metrics, and
we tune the implementation against them.

---

## 1 · What the component is

Not "splitting". **Cut AND edit** — Gil's words, and the distinction matters:

> "i dont think it should be an entire rewrite rather a edit to split
> correctly … the 'tomorrow' is relevant to both the gym session and the
> meeting."

So `"tomorrow gym at 7 and meeting at 11"` becomes **`"tomorrow gym at 7"`**
and **`"tomorrow meeting at 11"`** — the shared word is COPIED into the second
item, not left behind and not invented.

That gives the two invariants the whole dataset rests on, both checkable by
arithmetic rather than judgement:

- **NO INVENTION** — every token in every output item appears in the input.
- **NO LOSS** — every content token of the input appears in ≥ 1 output item.
- A token MAY appear in more than one item. That is exactly what a shared
  modifier is, and it is the only thing that distinguishes an edit from a
  rewrite.

## 2 · The scoping model — WHERE the reference sits decides who gets it

Gil's framing, and it is the right one: *"where in the string is the reference
to anything time related? that decides, once we split it, what time reference
goes to what item."*

So the question is positional. Every time reference is either **INSIDE** one
of the pieces, or at an **EDGE** of the whole command — before the first piece
or after the last — belonging to no piece on its own.

> **INTERIOR reference → binds to its own piece.
> EDGE reference → distributes to every piece that has none of its own.**

One rule, and it settles all four cases Gil gave, including the two that look
contradictory:

| input | where the reference sits | result |
|---|---|---|
| `tomorrow gym at 7 and meeting at 11` | **leading edge** | both tomorrow |
| `tomorrow meeting at 7, today gym session` | interior ×2 | each keeps its own |
| `gym session at 7, tomorrow meeting at 10` | **interior** to piece 2 | gym → today (default), meeting → tomorrow |
| `submit the grades and prepare the slides by friday` | **trailing edge** | both due friday |

My earlier "forward only" rule was wrong: it got the first three right and the
fourth wrong. Edge-vs-interior gets all four, and it does not need to
recognise deadline marker words to do it — which is the better sign.

**Still to settle, and the research angle on coordination scope is aimed at
exactly this:** whether an edge reference distributes when the pieces are of
DIFFERENT kinds (`"buy milk and book the dentist tomorrow"` — does the milk
get a due date?), and whether TIMES behave like DATES (`"gym and yoga at 7"` —
both at 7, or only the yoga?). The dataset must contain both shapes so the
question is answered by data rather than by me.

## 3 · The architecture — THREE PHASES, not one

Gil, 2026-09-08, and this replaces what I had:

> "given a string input we need to break down to all the independent
> actions/tasks, then GIVEN THAT AND THE ORIGINAL STRING we need to adjust
> where needed the time tag."

The correction that matters: **time assignment is its own phase, and it reads
the ORIGINAL STRING, not just the pieces.** I had it fused into the cut as an
"edit", which is wrong for exactly the reason Gil raised about tier A — once
`("gym tomorrow")and("buy milk")` has been cut on its brackets, a splitter
working piece-by-piece can no longer see that "tomorrow" might cover the milk.
A separate phase holding both the pieces AND the original can.

```
  text
   │
   │ ── PHASE 1 · BREAK DOWN ─────────────────────────────
   │      find every independent action. CUTTING ONLY.
   │        A  literal delimiters   (phone artifacts)
   │        B  clause parse         (fires on speech)
   │        C  one gated LLM call   (only if A and B found nothing)
   │        ↺  loop A+B to a fixed point
   │        GUARD  refuse a split where any piece is not an ask
   │   ↓
   │   pieces (spans of the original)
   │
   │ ── PHASE 2 · TIME ASSIGNMENT ────────────────────────
   │      INPUT: the pieces AND the original string, together.
   │      Splits each piece into two strings and fills the gaps:
   │        · a reference INSIDE a piece      → binds to that piece
   │        · a reference at an EDGE, owned
   │          by no piece                     → covers every piece
   │                                            that has none of its own
   │        · captured AS SPOKEN — never resolved,
   │          never expanded to a range or a duration
   │        · NO expression anywhere for an item → today
   │          (or the clock, if a time is truly required)
   │   ↓
   │   (action, time) per item
   │
   └── PHASE 3 · CLASSIFY ───────────────────────────────
          (action, time) → tag ∈ {event, task, review}
   ↓
   ITEM = (action, time, tag)
```

### The output contract (Gil, 2026-09-08)

Segmentation returns **a list of items, each three strings**:

```
  action  str   everything in this item that is NOT the time
  time    str   the time reference for this occurrence
  tag     str   "event" | "task" | "review"
```

**The invariant that makes it safe**, and the reason Gil specified it:

> "make sure that the action includes all the text for that item that is not
> related to time so we dont lose information like occurences etc which the
> decompose step is suppose to deal with"

So: **`tokens(action) ∪ tokens(time)` must cover every content token of that
item.** Nothing may fall on the floor between phase 2's two outputs. That is
checkable by arithmetic, and it is what stops the time-extractor quietly
eating a recurrence, an attendee or a location on its way past.

Worked example:

| input | action | time | tag |
|---|---|---|---|
| `book haircut every monday at 9am` | `book haircut` | `every monday at 9am` | event |
| `tomorrow gym at 7 and meeting at 11` | `gym` / `meeting` | `tomorrow at 7` / `tomorrow at 11` | event / event |
| `submit the grades and prepare the slides by friday` | `submit the grades` / `prepare the slides` | `by friday` / `by friday` | task / task |
| `buy 5 apples` | `buy 5 apples` | `today` (default) | task |

### Segment CAPTURES; it does not RESOLVE

Gil, on whether `"add the interview on next friday"` should become an all-day
block: *"the time will be friday. dont add more information that is not your
job here."*

That is the stage boundary, and it settles several questions at once. `time`
holds **the expression as spoken**. Segment never turns "friday" into a date,
never expands a dateless event into 00:00–23:59, never picks a duration. Every
one of those is a later stage's job, and doing them here would be inventing
information the speaker did not give.

So the defaults are a floor, not a resolver: when an item has **no time
expression anywhere** — none of its own and none distributed to it — `time`
falls back to today (or the clock, where a specific time is genuinely
required). An expression that EXISTS is captured verbatim and left alone.

### Recurrence — RULED (Gil, 2026-09-08)

Split by what kind of repetition it is:

| kind | example | goes in | why |
|---|---|---|---|
| **temporal** repetition | `every friday buy groceries` | **`time`** = `every friday` | it IS the time expression |
| **quantity** | `buy 5 apples` | **`action`** = `buy 5 apples` | not temporal at all — don't touch it |

Gil: *"reoccurent on time include in the time feature, other type of
reoccurence like buy x5 apples stays in the action feature. then the next
stage in the pipeline should deal with it."* Both are captured and passed on;
neither is expanded here.

### Edge references cross kinds — RULED

`"buy milk and book the dentist tomorrow"` → **break first, then time both**:

| action | time | tag |
|---|---|---|
| `buy milk` | `tomorrow` | task |
| `book the dentist` | `tomorrow` | event |

Gil: *"it should get broken to two items first — buy milk, book dentist — then
the time feature for both according to this is tomorrow."* So a trailing edge
reference distributes even when the pieces are of different kinds. This also
confirms the edge/interior model on a fifth example, and on the one shape that
could most easily have broken it.

## 4 · The classification method — RESEARCH FIRST

Gil: *"is the ML model good enough or another method?"*

What is known today, measured: the atomicity model scores `atomic` at **margin
9.20** against a floor of 0.25 on the real-usage failure I traced this
morning — decisive and correct. On the FastRule test half it reaches ~88%
compound recall. But it has never been evaluated *as the gate of a recursive
loop*, where a false "not atomic" costs a whole extra round.

Candidates to compare on the same rows: the existing logistic model, the
dependency-parse rules alone, the two in union (today's arrangement), a
small gradient-boosted model on the same features, and the LLM as an upper
bound on what is achievable. **The deliverable is a table, not a preference.**

## 5 · The dataset — `/segment_tuning`

Built fresh here, changing nothing under `dataset/`.

**Row schema:**
```json
{"id": "...", "text": "the input segment receives (post step-1 repair)",
 "gold": [{"text": "...", "kind": "event|task|review|other", "atomic": true}],
 "family": "shape name", "pattern": "what makes it hard",
 "source": "template|persona|realspeech|handwritten",
 "split": "train|test", "disputed": false}
```

**Gold is exact by construction, not reconstructed.** The 321 templates in
`dataset/fastrule/banks/complex_patterns.json` already encode the structure —
e.g. `book {event_title} {date} at {time} and {event_title2} {date2} at
{time2}`. A generator that renders the PARTS and joins them knows the gold
split for free. That is far stronger than inferring boundaries after the fact,
which is what a previous attempt managed for only 76% of rows.

**Sources, in descending trustworthiness:**
- **real speech** (`dataset/realspeech/`) — the honest half. Hand-labelled.
- **personas** — six speaking styles, so an implementation cannot win by
  fitting one voice.
- **templates** — volume and pattern coverage, gold free by construction.
- **hand-written adversarial** — the traps below that no generator produces.

**Patterns that MUST be represented** (every one of these has already caused a
real bug in this project, most of them today):

*must split* — two asks joined by and/then/comma · three asks · mixed
event+task · `remind me to X then remind me to Y` · `as well as` · a second
imperative whose verb spaCy tags as a noun ("and then **book** tennis lesson")

*must NOT split* — names joined by "and" · a list of THINGS for one verb ·
serial verbs ("wash and fold the laundry") · a shared object · two times for
one activity · a lead-time clause ("give me a nudge an hour before") · an
anaphoric tail ("put that in the diary") · a completion marker ("wrapped up")
· a tag question · a wrapper phrase ("add X and Y to my list") · an
enumeration header ("two tasks due tomorrow:")

*edit, not just cut* — the three date-scoping cases in §2

**Split: by FAMILY, never by row** — so the held-back half is constructions
never seen, not the same shape with different nouns. Same rule the other sets
use.

## 6 · Metrics

Reported as a board, never as one number — today proved that a single figure
hides which way it is failing.

**A · boundaries** (the cut)
- exact-set match — the whole row right
- boundary precision / recall / F1 — partial credit
- **over-split and under-split as separate counts.** They are not
  symmetric: an under-split has two more chances downstream, an over-split is
  garbage immediately.

**B · the (action, time) split** — phase 2
- no-invention violations (a token in no part of the input) — must be **0**
- no-loss violations (an item's content token in NEITHER action nor time) —
  must be **0**. This is the invariant Gil specified, scored directly.
- time-assignment accuracy: did each item get the RIGHT time, including the
  distributed ones and the defaults (today / the clock)
- action purity: does `action` still carry the recurrence, attendees and
  location the later stages need

**C · classification** — phase 3, scored on `(action, time)` as given
- tag accuracy + per-class P/R/F1 + the confusion matrix
- atomicity accuracy, and separately its cost AS A GATE: how many extra
  recursion rounds a false "not atomic" bought

**D · cost** — LLM calls per row, and wall-clock. A tier that wins on
accuracy and doubles the calls has not obviously won.

**E · attribution** — which tier decided each row. Not a score; the thing
that makes a regression explainable. Gil: *"explainability of the system is
extremely important."*

## 7 · What I am NOT sure about — argue with these

1. **Does the forward-distribution rule hold for TIMES and DUE-DATES?** §2 is
   evidenced for dates only, from three examples. "submit the grades and
   prepare the slides by friday" — Gil ruled both are due friday, which is
   forward distribution of a *trailing* marker, i.e. the OPPOSITE direction.
   Either the rule is "a bare date distributes forward, an explicit deadline
   marker distributes to all", or my §2 is too simple. **This needs settling
   before the labels are written**, because it decides them.
2. **Does recursion pay?** It is a real architecture change. It may be that
   one good pass plus decompose is enough, and the honest way to find out is
   to measure the ceiling first: how many rows does a perfect second pass fix?
3. **Should kind move out of segment?** Splitting it out is cleaner and I
   recommended it; Gil's answer implies keeping them adjacent. Not blocking.
4. **Dated tasks on the calendar** — Gil raised it ("a task that shows in the
   calendar"). Noted as a product idea, out of scope here.

---

# 8 · What the research changed (2026-09-08)

Six angles searched, every paper verified to exist by a second agent. Five
findings change a decision here; the rest confirmed what we had.

## 8.1 · DROP the atomicity classifier. The stopping test should be mechanical.

Gil asked whether the ML model is the right method for the "is this atomic?"
gate. The literature answers three-for-three, and the answer is that **nobody
trains one**:

- **DisSim** (Niklaus, ACL 2019) recurses a rule set until no rule fires —
  a deterministic fixpoint, 100% reliable by construction, zero cost. Its
  accuracy on the construction we actually care about, COORDINATE CLAUSES,
  is **99.1%**.
- **ADaPT** (NAACL Findings 2024) recurses only when the EXECUTOR reports it
  could not do the task.
- **DecomP** (arXiv 2210.02406) recurses on a hard-coded size check.

And the one paper that did try a learned complexity head — **Adaptive-RAG**
(NAACL 2024) — reports **54–66%** accuracy on a 3-way decision, with heavy
confusion between adjacent classes. That is the weakest link in any loop.

**We already own the mechanical test.** FastRule's `reason_class() ==
STRUCTURE` is exactly ADaPT's "the executor could not execute this" trigger.
So the rule becomes **recurse while a STRUCTURE gate fires**, not "recurse
while a classifier says non-atomic" — and combined with §3's measured ceiling
(2 of 5,014 rows) this is now the cheap deterministic fixpoint and nothing
more.

**Depth**, from the flagship assistant benchmark: TOP (EMNLP 2018) reports
median tree depth **2**, mean 2.54, 35% deeper than 2. So cap at 2, escalate
to 3. Not unbounded.

## 8.2 · Cutting is the EASY half. Copying is where the work is.

**DialogUSR** (Findings of EMNLP 2022) is the closest published problem to
ours — 11,669 multi-intent assistant commands **with all punctuation stripped
to match post-ASR input**, which is our exact register. It splits the task
into Split / Delete / Complete, and the gap is stark:

| | score |
|---|---|
| Split accuracy (where to cut) | 84.4% → **98.8%** |
| Exact match on pieces NEEDING completion | 56.9% → **70.3%** |

**A ~28-point gap between finding the boundary and filling the piece in.**
That reverses my instinct: phase 2 deserves the engineering budget, not
phase 1.

Two more results from the same paper:

- **ORDER IS MEASURED, and ours is the winning one.** Their ablation:
  Split→(Delete+Complete) is best (EM 56.17); (Delete+Complete)→Split is
  worst (47.57); Split→Delete→Complete as three stages is worse than two.
  So: **cut on the raw text first, then do the removing and the copying as one
  operation** — which is exactly the phase 1 / phase 2 shape Gil described.
- **Anaphora is the wrong tool.** 62.5% of follow-on pieces are incomplete,
  and of those only **2.4%** are coreference — the rest are bare omissions.
  A pronoun resolver would address 2.4% of the problem. We need modifier
  COPYING, which is what §2 already describes.

## 8.3 · ABCD — the closest published architecture, and it fits what we own

**ABCD** (ACL 2021) recasts splitting as a **graph edit**: nodes are word
tokens, edges are linear-adjacency plus dependency relations, and every
element is classified **Accept / Break / Copy / Drop**. Its COPY action is
precisely our shared-modifier mechanism — a token duplicated into the second
component so each piece is self-contained. Cut-and-distribute as ONE decision,
not two stages.

Why it matters here: it runs on a dependency parse and a small classifier —
**exactly the spaCy + pure-python-logistic stack we already have** — and on
messy informal text it beats a seq2seq generator by ~17 points on count-match
(53.29% vs 36.20%), while tying on clean text. Worth prototyping against our
hand-written rules before assuming rules win.

Related: **Question Decomposition with Dependency Graphs** (arXiv 2104.08647)
shows a tagger reaching this shape at ~80ms against ~1.3s for a generator, for
a ~3-point accuracy tax — and, decisively for us, the graph parser
**outperforms seq2seq at 10% of training data or less**. With a few thousand
mostly-generated rows we are squarely in that regime.

## 8.4 · Two dataset traps, both of which we would have walked into

- **Fragment leakage.** *Split and Rephrase: Better Evaluation* (ACL 2018)
  found the WebSplit benchmark leaked **>89% of its unique simple sentences**
  between train and test, so a plain seq2seq scored well by MEMORISATION.
  Our family-split is necessary and **not sufficient**: we must also verify
  the ATOMIC ITEM STRINGS in the held-back half are unseen in training. If
  "remind me to buy milk" appears in both, the number is partly a memorisation
  score.
- **Count-learning.** *MinWikiSplit* (2019) notes WikiSplit has exactly one
  split per source sentence, so models learn "always emit two" regardless of
  input. If our rows are almost all 1-or-2 asks, an implementation will learn
  the COUNT rather than the criterion — and will fail on three-ask utterances
  while scoring well. **Deliberately oversample 3+ ask rows**, and report the
  gold-count distribution beside every score.

## 8.5 · Do NOT add an LLM decomposition round

*When Do Decompositions Help for Machine Reading?* (EMNLP 2023), verbatim:
decompositions help in the few-shot case, but "when models are given access to
datasets with around a few hundred or more examples, decompositions are not
helpful (and can actually be detrimental)". We have thousands of rows. Stated
honestly: their decomposition is a MEANS to a downstream answer where ours is
the OUTPUT, so this does not say "don't split" — it says don't buy an extra
model-driven round to help a stage with enough data to learn the split itself.
It is the hypothesis to beat before spending a 2–8 s call per piece per round.

**Calibration for our hardware**, from MAC-SLU (arXiv 2512.01603): Qwen3-8B —
our model's class — scores **60.7%** on multi-intent commands with gold text,
falling to **47.2%** at 3.6% CER and **35.5%** at 10.4% CER. So an
LLM-does-everything decompose tops out around 60% even before ASR damage,
which is the quantitative case for deterministic-first. It also prices the
transcript stage: ~7 points of CER costs ~12 points of end-to-end accuracy.

---

# 9 · FastSeg + the verifier (Gil, 2026-09-08)

The deterministic part is called **FastSeg**. The model is not asked to
decompose — it is asked to **audit FastSeg's answer and correct it only if it
is wrong**. When FastSeg is right the reply is two words, so the common case
is cheap.

This is the right way round on our hardware. MAC-SLU measures Qwen3-8B — our
model's class — at **60.7%** doing multi-intent decomposition from scratch on
clean text. Judging a proposed answer is a much easier task than producing
one, and DialogUSR's grounding result says the same: a model handed the
deterministic parse does better than one starting cold.

## The prompt

```
The command, exactly as the speaker said it:
{prompt}

A deterministic parser has already decomposed it into independent items:
{fastseg_output}

YOUR JOB: check that decomposition and correct it only if it is wrong.

An item is ONE independent thing the speaker asked for. Each item has three
parts:

  action - the item's words with the time reference removed. Keep EVERYTHING
           else: the verb, the object, people, places, quantities ("5 apples")
           and any repetition that is not temporal.
  time   - the time reference that applies to this item, copied from the
           command AS SPOKEN. Do not resolve it into a date, do not add a
           duration, do not turn it into a range.
  tag    - one of: event, task, review

HOW TIME IS ASSIGNED
  - a time reference sitting INSIDE an item belongs to that item alone
  - a time reference at either END of the command, belonging to no single
    item, applies to EVERY item that has none of its own
  - a repeating time ("every friday") IS the time
  - an item with no time reference at all gets "today"

EXAMPLES

  "tomorrow gym at 7 and meeting at 11"
  {"1": ["gym", "tomorrow at 7", "event"],
   "2": ["meeting", "tomorrow at 11", "event"]}

  "gym session at 7, tomorrow meeting at 10"
  {"1": ["gym session", "today at 7", "event"],
   "2": ["meeting", "tomorrow at 10", "event"]}
  the later "tomorrow" does NOT reach back to the gym

  "submit the grades and prepare the slides by friday"
  {"1": ["submit the grades", "by friday", "task"],
   "2": ["prepare the slides", "by friday", "task"]}

  "buy 5 apples"
  {"1": ["buy 5 apples", "today", "task"]}
  a quantity is not a time - it stays in the action

  "every friday buy groceries"
  {"1": ["buy groceries", "every friday", "task"]}

  "meeting with Sam and Alex at 8"
  {"1": ["meeting with Sam and Alex", "at 8", "event"]}
  the "and" joins two PEOPLE - one item, not two

  "wash and fold the laundry"
  {"1": ["wash and fold the laundry", "today", "task"]}
  two verbs, one object - one item

OUTPUT
  If the decomposition above is correct, output exactly: No Change
  Otherwise output ONLY the corrected JSON object - no explanation, no
  preamble, no code fence.
```

## The one risk, named up front

**A model asked "is this right?" says yes too readily.** ADaPT (NAACL Findings
2024) measured exactly this: their executor's self-assessment over-estimated
success by **more than 30 points**, terminating recursion early. So this
verifier will be biased toward "No Change", and that bias is in the SAFE
direction for us — a missed correction leaves FastSeg's answer, which is the
under-split-by-default behaviour we already want — but it must be MEASURED,
not assumed.

The dataset makes it measurable directly: run the verifier over rows where
FastSeg is known-wrong and count how often it says "No Change" anyway. That
number is the verifier's real value, and it belongs on the board next to
the deterministic scores.

Two cheap mitigations if the bias proves large:
1. Ask for the checks explicitly rather than a global judgement — the shapes
   it should test are known and listed above.
2. Show it FastSeg's answer only AFTER asking it to decompose, so it commits
   first. Costs more tokens; only worth it if the bias is bad.

## 9.1 · The verifier runs on EVERY command — RULED (Gil, 2026-09-08)

> "the LLM call should be made regardless — if it returns No Change we
> continue anyway; if a correction, we take the correction and continue from
> there."

So it is synchronous and in the path, and the correction is authoritative:
FastSeg's answer is replaced, not merged.

**The cost, stated plainly because it is large.** Today FastRule commits in
~50 ms on ~47% of commands with no model call at all. An always-on verifier
means every command pays one round trip — even a two-word "No Change" costs
prompt processing plus generation, which on this hardware is roughly **1–2 s
minimum**. The common case therefore goes from ~50 ms to ~1–2 s, a 20–40×
increase, though it stays well under the 4–30 s the deep path costs today.

That may be entirely acceptable for a calendar assistant. The point is that it
is a real trade and it should be **decided on a number rather than a
preference** — which is exactly what this dataset makes possible.

**The two numbers that settle it.** A verifier is not judged by accuracy but
by whether its interventions help:

- **Correction RECALL** — of the rows where FastSeg is wrong, how many does
  the verifier fix? This is the value it adds.
- **Correction PRECISION** — of the rows it chooses to change, how many does
  it actually improve? A verifier that repairs 80% of errors while breaking
  5% of the answers that were already right can still be **net negative**,
  because correct answers vastly outnumber wrong ones. This is the number
  that decides whether the design ships.

Both fall straight out of the dataset: run FastSeg alone, run FastSeg +
verifier, and diff against gold. Add a third line for the bias ADaPT warns
about — how often it says "No Change" on a row that is known wrong.

**Two consequences for the implementation**, given the call is now on the
critical path of every command:
1. **Keep the prompt short.** Every token is latency on every command. The
   seven worked examples in §9 are there for accuracy; if latency bites, they
   are the first thing to measure trimming.
2. **A smaller model may be the right one here.** Judging a proposal is an
   easier task than producing one, so the verifier may not need the same model
   the deep track uses. Worth testing once the board exists.
