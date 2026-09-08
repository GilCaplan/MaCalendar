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
