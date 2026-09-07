# FastRule v2 — restructure proposal (for Gil's review)

_2026-09-07. Design only — nothing builds until approved. Prompted by Gil:
"restructure from scratch… use the ideas/stages/components that worked well
(especially the ML model classification routing on operation and kind) but
see what general structure would be helpful."_

## The product shape (Gil's ruling, 2026-09-07 — what v2 exists to serve)

**"Simple — one create/edit/remove of one event/task — must work at a very
high commit AND success rate. Complex defers, unless easy enough to
complete."** In numbers (working targets, Gil-adjustable, measured on
B-test):

- **Simple tier: the star metric.** North star ≥90% commit at ≥95%
  correct-on-committed; the standing milestone on the way is 80% at ≥90%
  (today: 72.0% at 92.4%). Every v2 decision optimizes this first.
- **Complex tier: NO commit-rate target at all.** Deferring is correct
  behavior, not failure. The only complex numbers that matter: whatever
  DOES commit stays ≥90% correct (today's 71% on committed-complex is the
  real complex problem — v2's split-and-recurse commits only all-clear
  splits, which fixes it by construction), and the gates' atomicity
  precision stays high so simple traffic is never mistaken for complex.

## Why (the convolution, named)

Fourteen F-batches accreted onto a structure designed before we knew what
FastRule had to be. The specific rot:

- **The normalization list became a junk drawer.** Lexical cleanup ("tmrw"→
  tomorrow) sits beside SEMANTIC decisions disguised as string rewrites
  ("mark ‹date› as X" → "add X on ‹date›", completions → "mark X as done").
  Rewrites destroy information and lie to downstream stages — the
  "set X as high priority" bug where the task got RETITLED "high priority"
  came from exactly this.
- **Routing is four accreted tiers** (phrase overrides → verb table → WH
  fallback → model tier), each added where the previous one leaked, with
  ORDER as load-bearing, undocumented structure.
- **Slot extraction is per-action branches with patches at various depths.**
  One F10 capture landed inside the wrong sub-branch and silently did
  nothing until a probe caught it. There is no way to see, per action, what
  extractors exist and in what order.
- **Confidence is uncalibrated folklore** — hand-chosen multipliers scattered
  in code (F8 measured the distribution is bimodal; R2 never ran).
- **The gates are the one part that aged well** — named reasons, direct
  supervision, measured precision/recall. v2 keeps their shape and gives
  the rest of the system the same discipline.

## The organizing idea: ONE decision pattern, applied everywhere (Gil, 2026-09-07)

Every judgment in v2 has the same tiered shape:

    rules answer when confident  →  a tiny model answers when they can't
    →  DEFER when neither is sure

Three decisions get it: **Is this atomic?** (the new first layer), **which
operation?**, **which kind?**. That uniformity — not component count — is
what un-convolutes the system: one pattern to understand, test, and
supervise, three times.

**The division of labor it implies (Gil's framing):** an "atomic item" =
one event or task. FastRule is the ATOMIC-ITEM EXECUTOR — it only ever
handles one item; the DEEP SYSTEM is the ATOMIZER — its whole point is
breaking a command into atomic items, then calling FastRule per item (the
0.60 fragment instance) to create each one. The front door (0.80) is just
the special case where the user's whole command is already one atom.

## The v2 shape: a first layer + five components

    FastRule(threshold)                    # unchanged public face:
      .run(text) -> FastRuleResult         # committed | reason, intents,
                                           # confidence, missing_slots

    0. Atomicity    — THE FIRST LAYER (Gil): is this ONE atomic item?
                      Rules tier = the existing compound gates
                      (strong-compound cue words, clause-coordination,
                      mixed-mode) — precision-strong (87–91%) and kept
                      as-is. Model tier = a third tiny logistic, trained on
                      dataset B's atomic flag (labels by construction,
                      train half only) — aimed squarely at the measured
                      recall hole (gates catch only ~45–50% of true
                      compounds). Verdict: atomic → proceed; compound or
                      unsure → DEFER (and later: hand the boundary to
                      split-and-recurse). The fragment instance (0.60)
                      skips this layer's defer — deep already atomized —
                      but keeps it as the "needs further breakdown" alarm.
    1. Normalizer   — LEXICAL ONLY: expansions, misspellings, filler/
                      courtesy strip. Semantic rewrites are RETIRED; their
                      jobs move to where the meaning lives (Router routes
                      "mark X as done" AS a phrase; SlotFiller captures the
                      date in "mark ‹date› as X" AS a slot).
    2. Router       — Gil's Q10 two-subsystem design PROMOTED from bolt-on
                      to center:
                        OperationClassifier: rules tier → model tier (K3)
                        KindClassifier:      rules tier → model tier (K1)
                      Each answers (label, source: rule|model, margin).
                      action = compose(operation, kind). Both provenances
                      ride the result — the Scorer bills them, the trace
                      explains them, a rules-vs-model disagreement is a
                      first-class signal the Gatekeeper may use.
    3. SlotFiller   — per-action slot SPECS AS DATA: required/optional
                      slots + an ORDERED extractor list per slot
                      (phrase-captures first — they are the precise ones —
                      then noun-chunking, then the temporal recognizer).
                      Every F6c/F7b/F10 patch becomes a visible, testable
                      table entry instead of a buried branch edit.
    4. Scorer       — every confidence penalty is a NAMED signal in one
                      table (model-routed, domain-guessed, anaphora,
                      two-times, …), so R2's calibration finally has one
                      place to refit, and the bimodality F8 found is
                      inspectable per signal.
    5. Gatekeeper   — intent-level vetoes ONLY (interrogative→propose,
                      generic-target, misroute) — the compound gates moved
                      up into layer 0 where they belong; each gate stays a
                      named object with its own test and supervision
                      metric. Downstream of layer 0, everything may assume
                      ONE atomic item — the assumption that simplifies
                      every component below it.

## Kept exactly (the things that worked)

- The **selective-classifier contract** and both instances (0.80 front door /
  0.60 fragment) — thresholds as constructor args.
- The **two ML models at the F12 state** (weights, floors 2.5/1.5, balanced
  fit, train-only fitting, test-eval reporting) — now the Router's model
  tier rather than a None-return patch.
- The **gates** — semantics, names, supervision metrics (compound gates
  relocated to layer 0, not changed).
- The **verb table and phrase overrides** — as the Router's rules tier,
  with tier order made explicit and documented.
- The **measurement discipline** — registered predictions, B-test reported,
  A-pool dual-gate, per-family floors, leakage guards.

## Retired

- Semantic rewrites in the normalization list (each one's job reassigned:
  routing meaning → Router rules tier; slot meaning → SlotFiller captures).
- The four-tier routing sprawl (collapsed into the two named tiers).
- Buried per-branch slot patches (become spec-table entries).

## Migration — parallel build, diff-gated switch

1. Build `fastrule2.py` beside v1 in the lane; v1 stays live everywhere.
2. A **diff harness** runs both on B-train, B-test (aggregate) and A-dev:
   same-verdict rate reported; every divergence classified (v2-better /
   v1-better / neutral) from TRAIN rows only.
3. Switch when v2 ≥ v1 on every board (test simple commit/correct, full
   board, dual-gate) — then v1 retires per the retirement convention
   (folder + tag, never deleted).
4. The engine never notices: same FastRuleResult, same call sites.

## Complex-but-doable — the split-and-recurse affordance (designed in, built later)

Today a compound defers wholesale (complex commit ~28%, and commits are
only 71% right). v2's per-fragment components enable the doable subset:
when the coordination check fires WITH a confident boundary, split there
and run EACH HALF through the same five components at the fragment
instance (FastRule(0.60) — the lenient bar that exists for pre-atomized
pieces); commit only if every half clears its bar and gates — one shaky
half defers the whole command, so the failure mode stays "slower", never
"half-executed". This is the cycle-10 rules-first-per-fragment idea living
inside FastRule. Guards: recursion only on high-margin boundary detections
(a wrong split makes two garbage halves — the known spaCy mis-parse shapes
stay deferred); depth 1 (a half that still looks compound defers).
Per the simple-first ruling this is an AFFORDANCE of the structure, not
first-port scope — it becomes a lane batch when simple hits its target.

## Open questions for Gil

1. **Scope of the first build:** straight port into the new structure
   (behavior-identical, boring, safe) and only then improve — or allow the
   port to fix known warts as it goes? (Recommend: identical-first, the Q7
   lesson.)
2. **The Scorer's calibration:** run R2 as part of v2 (one table makes it
   cheap) or keep hand values until after the switch? (Recommend: after.)
3. **Slot specs as data** opens the door to per-family extractor tests and
   the R8 title work — in scope for v2, or a follow-up lane batch?
   (Recommend: follow-up.)
4. **The atomicity model** (layer 0's model tier): train and wire it as
   part of the v2 build, or port the current gates first and add the model
   as the first post-switch batch? (Recommend: port gates first — the
   model is additive and its labels/eval already exist, so it slots in
   cleanly as a measured batch.)
