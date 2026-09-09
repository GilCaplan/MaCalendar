# LLMJudge — the plan (2026-09-09)

`ARCHITECTURE.md` is how it works today. This is what is coming to it and what to
do about it. **Nothing here is built yet** — it is written now because two pieces
of FastRule are moving here, and the receiving end should be designed before they
arrive rather than after.

---

## 1 · Two things arrive from FastRule (Gil, 2026-09-09)

FastRule is being trimmed to one job — `Item -> object` — because *"if there's an
issue it tells the LLMVerify."* Two of its four current jobs are this stage's.

---

## 1.0 · STEP 0 — the port comes BEFORE the demolition (Gil, 2026-09-09)

> Gil: *"make sure before we start breaking FastRule code to port what's relevant
> to the LLMJudge folder to deal with when we get there — then the rest of the
> FastRule restructure plan."*

**This is the first step of the whole restructure, ahead of everything in
FastRule's own `PLAN.md` §3.** The reason is not tidiness. If FastRule is trimmed
first, the ~118 lines of `Gatekeeper` and the ~150 of the LLM fallback exist only
in git history, and "port" quietly becomes "rewrite from memory" — which is how a
guard gets dropped. `_guard_inventions` is the one that matters: it exists because
of a measured cycle-7 defect where a model fabricated an event onto the calendar,
and nothing about the LLM fallback's new home makes that risk smaller.

### It is a MOVE with an import redirect — not a copy

The distinction decides whether this step is safe:

```
    PORT  = FastRule phase A               TRIM = FastRule phase B (B5/B6)
    the code LIVES here                    FastRule's call sites go away
    FastRule imports it from here          the redirect goes away with them
    behaviour identical, boards identical  behaviour changes, boards re-run
```

A **copy** would leave two versions of `_honour_refusal` alive at once — and the
rule it enforces (*a REFUSAL may be resolved, never overturned*) has already been
broken once in this codebase, by exactly that mechanism: the per-item path
re-implemented the commit test with the gates omitted. Two copies of a guard is
the shape of that bug, not a step toward fixing it.

So step 0 changes **no behaviour and moves no board**. That is its acceptance
test: `pytest tests/unit/test_fastrule.py` and FastRule's product-shape board
report the same numbers before and after. A port that moves a number is a port
that changed something, and should be reverted rather than explained.

### The inventory — verified against the code, 2026-09-09

| name | today | lines | port verdict |
|---|---|---|---|
| `Gatekeeper` | `fastrule.py:284-351` | ~68 | **moves** |
| `_which_store_holds` | `fastrule.py:234-259` | ~26 | **moves** — Gatekeeper's only caller |
| `_names_something_real` | `fastrule.py:260-283` | ~24 | **moves** — Gatekeeper's only caller |
| `_GENERIC_TARGET_RE` | `fastrule.py:54` | 8 | **moves** — see below |
| `_POLITE_IMPERATIVE_RE` | `fastrule.py:62` | 4 | **moves** — Gatekeeper-only |
| `_INTERROGATIVE_RE` | `fastrule.py:66` | 4 | **moves** — Gatekeeper-only |
| `_llm_trace` | `objects.py:150-160` | 11 | **moves** |
| `_honour_refusal` | `objects.py:161-196` | 36 | **moves** |
| `_parse_item` (model half) | `objects.py:197-280` | ~84 | **moves** — the hard one, below |
| `_grounded_title` + `_TITLE_STOP` | `objects.py:281-300` | 20 | **moves** |
| `_guard_inventions` | `objects.py:301-318` | 18 | **moves** |
| `REFUSAL` · `STRUCTURE` · `INCAPACITY` · `_REASON_CLASS` · `reason_class()` | `fastrule.py:103-131` | ~30 | **STAYS in FastRule** |

**The LLM fallback is in `objects.py`, not `fastrule.py`** — §1.2 below says "FastRule
itself calls the model" and that is true of the stage, not of the file. Worth
stating because the two files have very different shapes: `fastrule.py` is the
rule engine, `objects.py` is the per-item build loop, and the fallback is woven
into the second.

### There is no circular import — the first reading of this was wrong

Counting raw occurrences suggested `REFUSAL` (6 uses in `fastrule.py`) and
`_GENERIC_TARGET_RE` (3 uses outside it) were SHARED, and that moving them would
create `fastrule -> llmjudge -> fastrule`. Reading the enclosing scopes says
otherwise, and the difference is the whole design of this step:

- **`REFUSAL`'s six "uses" in `fastrule.py` are its own definition** — the constant
  at line 103 and the five `_REASON_CLASS` table rows at 111-114 — plus one
  comment inside `Gatekeeper`. Nothing in FastRule *reads* it.
- **Every code use of `_GENERIC_TARGET_RE` is inside a piece that is already
  moving**: `Gatekeeper` at 326/338/343, and `_honour_refusal` at
  `objects.py:178/183`. The remaining hit is a comment in `fastrule_shape.py`.

So the pieces are coupled to **each other**, not to the rest of FastRule. They lift
out as one connected component and the cycle never forms. The lesson is the one
this project keeps re-learning: **a usage count is not a dependency** — the
enclosing scope is.

### Which leaves exactly one dependency edge, and it points the right way

`_parse_item` reads `REFUSAL`/`STRUCTURE`/`INCAPACITY` (`objects.py:213, 255, 268`),
so after the move LLMJudge imports the reason-class contract from FastRule:

    llmjudge  ──imports the DEFER vocabulary──►  fastrule        ✔ one direction

That is the correct direction and the reason the contract **stays put**: the DEFER
is FastRule's *product*, `REFUSAL/STRUCTURE/INCAPACITY` is the vocabulary it is
written in, and the consumer of a value importing that value's vocabulary is
ordinary. Moving the contract here would invert it — LLMJudge is not the only
consumer (`atomizer_board.py`, `test_artifact_claims.py` and `objects.py` all read
it), and a contract does not belong inside one of its readers.

During the window between the port and FastRule's **B5/B6** there is a transitional back-edge —
`fastrule.objects` calls into `llmjudge` for the fallback it has not yet stopped
calling. **Both edges are function-local imports** (`objects.py`'s imports at 178
and 213 already are), so nothing resolves at import time and no cycle can bite.
The back-edge disappears with the trim; it is not a design, it is scaffolding, and
FastRule's B6 is not done while it survives.

### What goes red the moment `Gatekeeper` leaves the folder

Named here so it is planned rather than discovered:

| | what to do |
|---|---|
| `test_artifact_claims.py:610` — the published page names `FastRule · Atomicity · Gatekeeper · Scorer` as FastRule's components | the page and its claim check are updated **in the same change** — the artifact-claims rule exists for exactly this |
| `engine/ARCHITECTURE.md:111` — the Component-vs-Stage table puts `Gatekeeper` in `fastrule/` | move the row to `llmjudge/` |
| `fastrule/ARCHITECTURE.md:25,34` — the flow diagram and the component table | redraw without the veto box |
| `tests/unit/test_fastrule.py` | Gatekeeper's tests move with it, to `test_engine_llmjudge.py` |

`BRAIN_VERSION` is **not** bumped by any of this. Gatekeeper and the fallback are
Components, not Stages — the chain's shape is unchanged, `Stage("fastrule")` and
`Stage("llmjudge")` both still exist and still run in that order. This is the
`old_seg -> FastSeg` case from `engine/ARCHITECTURE.md`, not the rename case.

### Order within step 0

| # | | why |
|---|---|---|
| 0a | `llmjudge/gatekeeper.py` — the six Gatekeeper names, verbatim | self-contained; nothing else can be affected |
| 0b | `llmjudge/llm_fallback.py` — the five fallback names, verbatim | the connected component's second half |
| 0c | FastRule imports both from their new homes; call sites unchanged | the redirect. Behaviour identical by construction |
| 0d | Move the tests that belong to the moved code | a guard without its test is half-ported |
| 0e | Re-run `test_fastrule.py` + the product-shape board | **the numbers must not move.** If they do, the port changed something |

---

### THE MANIFEST — everything "go" needs, already resolved

Written out so execution is transcription, not re-derivation. Line numbers are
2026-09-09; the names are the contract, the numbers are a convenience.

**0a · new file `llmjudge/gatekeeper.py`** — cut from `fastrule/fastrule.py`:

| name | from | lines |
|---|---|---|
| `_GENERIC_TARGET_RE` | `fastrule.py:54-57` | 4 |
| `_POLITE_IMPERATIVE_RE` | `fastrule.py:62-64` | 3 |
| `_INTERROGATIVE_RE` | `fastrule.py:66-69` | 4 |
| `_which_store_holds` | `fastrule.py:234-257` | 24 |
| `_names_something_real` | `fastrule.py:260-281` | 22 |
| `Gatekeeper` | `fastrule.py:284-349` | 66 |

Needs `import re` and nothing else at module scope — `assistant.db` is already
imported lazily inside both store helpers, which is what keeps this file free of
the database at import time. **Carry the comment blocks verbatim**: the ones at
`fastrule.py:295-304` (why the store lookup must CONFIRM the parse, not merely
permit it) and `314-330` (why `_GENERIC_TARGET_RE` and not validate's
`is_placeholder_title` — using the latter as a commit veto broke 14 tests) are
each a recorded defect, and a port that keeps the code and drops the reason
invites the same fix to be re-attempted.

**0b · new file `llmjudge/llm_fallback.py`** — cut from `fastrule/objects.py`:

| name | from | lines |
|---|---|---|
| `_llm_trace` | `objects.py:150-158` | 9 |
| `_honour_refusal` | `objects.py:161-194` | 34 |
| `_TITLE_STOP` | `objects.py:281` | 1 |
| `_grounded_title` | `objects.py:284-298` | 15 |
| `_guard_inventions` | `objects.py:301-316` | 16 |

Needs `import re` and `from assistant.engine.state import EngineState, Item`.
`_honour_refusal`'s own `from …fastrule import _GENERIC_TARGET_RE` at
`objects.py:178` becomes a local import from `.gatekeeper` — same file, one hop
shorter.

**`_parse_item` does NOT move in step 0.** It is the branch point, not a unit;
it stays in `objects.py` calling the four helpers at their new addresses.
FastRule's **B5/B6** replaces it with a `DEFER(INCAPACITY)` consumer, which is a
behaviour change and therefore not this step's business.

**The `_friendly` question, decided.** `_honour_refusal` calls `_friendly`
(`objects.py:145`) for its trace label, and `_friendly` **stays** — it has eight
other callers in `objects.py`, including one at line 362 outside everything that
is moving. So `llm_fallback._honour_refusal` imports it **lazily, inside the
function**, exactly as it already imports `assistant.trace.RULE` two lines above.
Three reasons this is the right call rather than a compromise:

- **No import-time cycle is possible.** `objects.py`'s only top-level engine
  import is `assistant.engine.state`; every FastRule→LLMJudge call is a
  function-local import. Neither module can be loaded "first" and break.
- **Moving `_friendly` to `state.py` was the tidier alternative and is rejected** —
  it edits the frozen contract module during a step whose entire guarantee is
  that nothing structural changed. Tidiness does not buy enough to spend that.
- **It becomes a tripwire.** When FastRule's B5/B6 dismantles `objects.py`, this import
  fails loudly and names the last thing that needs a home — which is better than
  a silent loss, and a silent loss is the whole risk Gil asked to eliminate.

**0d · the tests that move**, from `tests/unit/test_fastrule.py` to a new
`tests/unit/test_engine_llmjudge.py` (the stage has **no unit test file today** —
this port creates its first):

| test | what it pins |
|---|---|
| `test_f4a_polite_imperative_is_not_a_question` | the `_POLITE_IMPERATIVE_RE` exemption |
| `test_f7_rename_never_commits_a_create` | the rename-misroute veto |
| `test_personalisation_is_lookup_not_training` | `_names_something_real` — lookup, not a refit |

Three more files reference the moved names and must be checked, not assumed:
`test_engine_generate.py`, `test_event_matching.py`, `test_artifact_claims.py`.
The first two go through the public path and should need nothing; the third is
the published-page agreement check and **will** go red (§ "What goes red" above).

**0e · the acceptance test, exactly**

    pytest tests/unit/test_fastrule.py tests/unit/test_engine_generate.py \
           tests/unit/test_event_matching.py tests/unit/test_artifact_claims.py
    python -m assistant.engine.fastrule.experiments.fastrule_shape   # train half

The board must print the §5 baseline unchanged — `handled 69.1% ·
correct-on-handled 94.2% · deferred 30.9%`. **A moved number means the port
changed behaviour and should be reverted rather than explained**; that is the
one rule that makes this step worth separating from the restructure at all.

Only then does FastRule's `PLAN.md` §3 start. Steps 1-3 there (measure the ceiling,
build the converter, move `Atomicity`) no longer touch any of this code, because it
is no longer in the building.

### Why `_parse_item` is the hard one, and what to do about it

The other ten names are lifts. `_parse_item` is not: it is the per-item **branch
point**, and the model half is woven into it rather than sitting beside it —
it reads FastRule's partial parse, decides rules-vs-model, calls the model,
then runs `_honour_refusal` and `_guard_inventions` over the result.

**Do not try to make the port clean here.** The honest move is to port the model
half and its three guards as one function that FastRule *calls* at the same branch
point, leaving the branch itself in `objects.py` until FastRule's B6 deletes it.
The alternative — restructuring the branch during the port — is a behaviour change
wearing a port's clothes, and it would break step 0's one acceptance test.

The clean version of this boundary is `DEFER(INCAPACITY)` returned by
`build()` and read here, which is what §1.2 describes. **That shape belongs to
FastRule's phase B, not to this port.** Step 0 only guarantees the code is here,
tested, and no longer duplicated when the demolition starts.

## 1.1 · `Gatekeeper` moves here, and becomes CONTEXT rather than a veto

> Gil: *"perhaps move Gatekeeper code to LLMJudge… so it's given to the LLM as
> context."*

Today `Gatekeeper` (~68 lines, plus `_which_store_holds` and `_names_something_real`
which query the user's own stores) sits inside FastRule and **vetoes** readings that
must not execute as stated:

| it catches | example |
|---|---|
| a mutation aimed at a bare noun | "move it to five" — move WHAT? |
| a rename that would misroute | "rename the dentist to physio" hitting the wrong record |
| an interrogative that would create | "should I book the gym?" creating the gym |

**Why it is better here.** As a veto it has exactly one move — refuse — and a
refusal is the end of the conversation. The objection it raises is precisely the
kind a model CAN answer: *"move it"* has an antecedent somewhere in the utterance,
and resolving anaphora is what a language model is for. So the same judgement,
handed over as context, becomes answerable instead of terminal.

**The rule it must not break.** `REFUSAL` today means *the LLM may RESOLVE the
objection but must never overturn it* — the deep track once re-committed exactly
what the front door had vetoed, and the engine audit named it. Moving the code here
puts the veto and its escape hatch in the SAME module, which makes that rule easier
to hold, not harder:

    the model may answer  "move it"  ->  "move the dentist appointment"
    the model may NOT answer  "move it"  ->  "move it"   (the same empty target)

So the prompt gets the objection AND the constraint: *here is what is wrong with
this reading; you may fix it by naming the thing, and you may not hand it back
unchanged.*

## 1.2 · The LLM fallback moves here

Today, when FastRule cannot read an item, **FastRule itself** calls the model
(`_parse_item`'s model half, plus `_honour_refusal`, `_grounded_title`,
`_guard_inventions`, `_llm_trace` — about 150 lines, all of them in
`fastrule/objects.py`, not `fastrule.py`; §1.0 has the line numbers). Under Gil's definition
FastRule reports `DEFER(INCAPACITY)` and carries its partial parse forward; the
model call happens where the model lives.

**What comes with it, and must not be dropped on the way:**

- **`_guard_inventions`** — a model-fabricated event never reaches the calendar.
  This exists because of a measured cycle-7 defect, and rule-parser output is
  deliberately never subject to it.
- **`_grounded_title`** — every content word of an LLM title must have been spoken.
- **`_honour_refusal`** — the REFUSAL rule above, in code.
- **the partial parse rides along** — `state.fastrule_verdict` already carries
  reason, reason class and confidence forward (Gil, 2026-09-07: *"a deferral never
  wastes the work"*). The model starts from FastRule's reading, not cold.

---

## 1.3 · THE LOOP — commit what is right, rewrite only what is wrong (Gil, 2026-09-09)

> *"Given the output from FastRule it compares the original text prompt and the
> objects, and for the objects which are good it pushes them through. Whatever is
> left it fixes/trims the original text to pass only the objects that are wrong and
> need fixing, in better wording… if FastRule passed 5 objects and 3 are good and 2
> are bad, LLMJudge lets the 3 good ones get committed and the 2 bad ones it rewords
> best it can into a new prompt and passes it back to segmentation. This cycle
> repeats up to 3 times before objects get committed or thrown away."*

```
   original text ─────────────────────────────────────────────┐
        |                                                     │
        v                                                     │
   segmentation -> decompose_validate -> FastRule             │
        |                                                     │
        v                                                     │
   ┌──────────────────── LLMJudge ────────────────────┐       │
   │  compare each object against the ORIGINAL text   │       │
   │                                                  │       │
   │   3 good  ─────────────────────► COMMIT now      │       │
   │                                                  │       │
   │   2 bad   ─► reword ONLY those parts ──► X1' ────┼───────┘
   └──────────────────────────────────────────────────┘   round < 3
                                  |
                            round == 3
                                  v
                        commit best / discard
```

### Why the rewrite is a TRIM, not a retry of the whole thing

This is the part that makes the loop safe, and it is worth stating as a rule
rather than leaving to the implementation:

**X1′ contains only the failed asks.** Not the original utterance, not the original
minus a flag — the words for the two things that went wrong, reworded. Three
consequences, each of which is the point:

1. **No double-commit.** The three good objects are already written. If X1′ still
   described them, round two would create them again. The trim is what prevents
   that, so it is a correctness requirement rather than an optimisation.
2. **Each round is a SMALLER problem.** Five asks became two. A command that was
   too tangled to segment correctly gets simpler every round instead of being
   re-attempted at full difficulty — which is why three rounds is enough.
3. **The retry can actually differ.** Segmentation is DETERMINISTIC, so re-entering
   with unchanged text returns the identical answer and burns the budget for
   nothing. Real usage, 2026-09-08: *"Let an event to go out for a run now"* looped
   three times to the same result and apologised after 30 seconds. A trimmed,
   reworded X1′ is a genuinely different input — which is exactly why
   `rewrite_for_retry` was gated as a stub until it could produce one.

### What "good" means, and who decides it

The model must not be the judge — that is this stage's founding rule. So:

- the model **EXTRACTS** the asks it can see in the original text;
- deterministic code **DIFFS** that list against the objects FastRule built;
- an object is GOOD when it matches an extracted ask and carries no finding
  against it. Everything else is bad and goes into the trim.

Which means `extract_asks` and `_produced` — both already here — are the machinery
the loop needs; what is missing is the partition and the rewrite.

### The budget, and what happens when it runs out

Three rounds per original prompt, counted per COMMAND rather than per object, so a
row cannot loop forever by failing a different ask each time.

On exhaustion the existing convention holds and should not be quietly changed:
**commit the best attempt, say so in the reply, and mark the memory record
uncertain** so it reaches the review queue. Gil's *"committed or thrown away"* leaves
the choice open; discarding silently is the one option that is not acceptable,
because the speaker asked for something and heard nothing back.

> **Open question for Gil.** Should a *destructive* ask that is still unresolved at
> round 3 commit as the best attempt, or be dropped with an explanation? The
> project's own rule — *"when the engine cannot identify what to delete, 'I couldn't
> find…' is the right answer; guessing is not"* — argues for dropping deletes and
> committing creates, but that asymmetry should be a decision rather than an
> inference.

## 2 · What this stage then is

    IN    the objects FastRule built + the DEFERs it could not, with reasons
          + Gatekeeper's objections as context
          + the ORIGINAL text, which is what everything is compared against
    OUT   the GOOD objects, committed now
          + X1' — only the failed asks, reworded, back to segmentation
          + on round 3, the best attempt and an honest reply

Which makes the existing shape more honest, not less: LLMJudge already **extracts**
what the raw text asked for and lets deterministic code diff it. It gains the two
places where a model is genuinely the right tool — resolving an objection, and
reading an item the rules could not.

---

## 3 · The thing to fix that is already here

**The loop never fires.** `rewrite_for_retry` is a stub returning `None`, so the
re-entry budget is never spent and the one mechanism for recovering from a bad
segmentation is inert. It is gated deliberately — segmentation is deterministic, so
re-entering with unchanged text cannot produce a new answer (real usage, 2026-09-08:
*"Let an event to go out for a run now"* looped three times to the identical result
and apologised after 30 seconds).

So the gate is right and the rewrite is the missing half. It wants a model call
grounded on `state.raw_text` that produces a CLEARER utterance in the same format —
and with `Gatekeeper`'s objections now available here as context, it has something
concrete to rewrite *toward* rather than a vague "try again".

---

## 4 · Order

| # | step | why |
|---|---|---|
| **0** | **PORT the code here, behaviour unchanged** — §1.0 | Gil: *port before breaking FastRule.* Trimming first would leave the guards in git history only |
| **⏸** | **WAIT — FastRule phases B, C and D** (`fastrule/PLAN.md` §3) | Gil, 2026-09-09: *"once we totally finish FastRule then let me know and we can work on LLMJudge"* |
| 1 | Turn `Gatekeeper` from a veto into prompt context | now a local change — the code is already here |
| 2 | Make the fallback a `DEFER(INCAPACITY)` consumer, and delete FastRule's branch | the boundary change; one stage's behaviour at a time |
| 3 | `rewrite_for_retry` | last, because it is the only piece that needs the other three to be useful |

**Step 0 happens NOW; steps 1-3 wait for Gil.** The port is FastRule's phase A —
it runs first precisely so this code is safe while FastRule is taken apart. Steps
1-3 are this stage's own redesign and do not begin until FastRule is finished and
Gil says to start.

**Step 0 is a MOVE; steps 1-2 are the BEHAVIOUR change.** Splitting them is the
point: step 0's acceptance test is that no number moves, so anything that does move
a number is provably in steps 1-2 and not in the relocation. Doing both at once
gives up that isolation, and the boards are the only way this stage is measured.

## 5 · Rules

**The model EXTRACTS; deterministic code JUDGES.** That is this stage's founding
idea and none of the above changes it — Gatekeeper's objections are computed
deterministically and handed over; the model answers them.

**A REFUSAL may be resolved, never overturned.** The one rule that has already
been broken once in this codebase.

**Board D has never run.** It needs both a FastSeg answer and a final prediction, so
it only reports with LLMSeg on — see segmentation's `ARCHITECTURE.md` §3. The one
board built to ask *"does the correction pay for itself"* has no data, and that is
worth fixing before trusting any verdict this stage produces.
