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
   │      find every independent action. CUTTING ONLY —
   │      no time reasoning happens here at all.
   │        A  literal delimiters   (phone artifacts)
   │        B  clause parse         (fires on speech)
   │        C  one gated LLM call   (only if A and B found nothing)
   │        ↺  loop A+B to a fixed point
   │        GUARD  refuse a split where any piece is not an ask
   │   ↓
   │   pieces: ["gym", "buy milk"]
   │
   │ ── PHASE 2 · TIME ASSIGNMENT ────────────────────────
   │      INPUT: the pieces AND the original string, together.
   │      For each piece decide its date and its time:
   │        · a reference INSIDE a piece      → binds to that piece
   │        · a reference at an EDGE of the
   │          command, owned by no piece      → covers every piece
   │                                            that has none of its own
   │        · no date anywhere                → TODAY
   │        · a time is needed and none given → NOW (the clock)
   │   ↓
   │   pieces + when: [("gym", tomorrow), ("buy milk", tomorrow)]
   │
   └── PHASE 3 · CLASSIFY ───────────────────────────────
          each piece → event | task | review
```

**Why three phases and not one pass:** each has a different input, a different
failure mode and a different metric, so each can be tuned and blamed on its
own. Phase 1 is judged on boundaries, phase 2 on whether the right piece got
the right date, phase 3 on kind accuracy. Today all three are entangled in one
function, which is why fixing the splitter this morning made mis-typing worse
and no single number could say why.

**One nuance in the "default to now" rule, flagged not assumed.** Gil: *"if no
time given the default should be today, and if need specific time then right
now whatever the current time is."* Read literally that would end all-day
events — `"add the interview on next friday"` is legitimately 00:00–23:59
today and should stay that way. My reading: the time defaults to the clock only
when the item NEEDS a clock time; a dated event with no time spoken stays
all-day. **Confirm this reading before it is labelled.**

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

**B · the edit**
- no-invention violations (tokens not in the input) — must be **0**
- no-loss violations (input content tokens in no item) — must be **0**
- shared-modifier accuracy: did the right items get the shared date

**C · classification**
- kind accuracy + per-class P/R/F1 + the confusion matrix
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
