# LLMJudge — the plan (2026-09-09)

`ARCHITECTURE.md` is how it works today. This is what is coming to it and what to
do about it. **Nothing here is built yet** — it is written now because two pieces
of FastRule are moving here, and the receiving end should be designed before they
arrive rather than after.

---

## 1 · Two things arrive from FastRule (Gil, 2026-09-09)

FastRule is being trimmed to one job — `Item -> object` — because *"if there's an
issue it tells the LLMVerify."* Two of its four current jobs are this stage's.

### 1.1 · `Gatekeeper` moves here, and becomes CONTEXT rather than a veto

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

### 1.2 · The LLM fallback moves here

Today, when FastRule cannot read an item, **FastRule itself** calls the model
(`_parse_item`'s model half, plus `_honour_refusal`, `_grounded_title`,
`_guard_inventions`, `_llm_trace` — about 150 lines). Under Gil's definition
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

## 2 · What this stage then is

    IN    the objects FastRule built + the DEFERs it could not, with reasons
          + Gatekeeper's objections as context
    OUT   approve, or a repaired object, or X1' — a rewritten utterance

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
| 1 | Wait for FastRule's converter (its `PLAN.md` steps 1–3) | the boundary move should follow a working converter, never accompany it |
| 2 | Move `Gatekeeper` here as prompt context | self-contained; the objections are already computed |
| 3 | Move the LLM fallback here with its three guards | the boundary change; one stage's behaviour at a time |
| 4 | `rewrite_for_retry` | last, because it is the only piece that needs the other three to be useful |

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
