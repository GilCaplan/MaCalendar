# FastRule

**The ATOMIC-ITEM EXECUTOR.** Given one atomic item — a single event or task —
it produces the object, in about 50 ms, with no model. The deep system is the
**ATOMIZER**: it splits until items are atomic and then hands each one back
here. Gil's framing: *"the deep system's main idea is breaking down to atomic
items so the FastRule can then create the right event/task per item."*

FastRule is not a pipeline stage of its own. It is the thing `generate` reaches
for first, and it is the whole of the fast track: when it is confident on a
complete input, its answer commits instantly.

---

## 1 · The organizing idea

Every judgement is the same tiered decision — **rules when confident, a tiny
model when they cannot be, DEFER when neither is sure** — applied three times:

```
   text ──► parse ──► Atomicity ──► Gatekeeper ──► Scorer ──► commit
                     (one or many?)  (must this      (confident   or
                                      NOT execute?)   enough?)    DEFER
```

| unit | question | on failure |
|---|---|---|
| **parse** | Normalizer + Router + SlotFiller | — |
| **Atomicity** | one item, or several? | rules **or** model, both unconditional |
| **Gatekeeper** | is this a reading that must not execute as stated? | veto |
| **Scorer** | threshold + missing slots | DEFER |

Atomicity answers *only* whether the item is atomic; what routing does about a
compound is `run`'s business. v1 had the two fused, and the fusion cost the
layer half its recall.

---

## 2 · The verdict is a contract, not a suggestion

When FastRule declines, `reason_class()` says what the deep track **owes** it.
This is the part most easily got wrong, and it has been got wrong:

| class | reasons | what the deep track owes |
|---|---|---|
| **REFUSAL** | generic-target, rename-misroute, interrogative-create | A *correct* reading that must not execute as stated. The LLM may **resolve** it (anaphora → a real title); it must **never overturn** it by handing back the same empty target. |
| **STRUCTURE** | the compound gates | More than one item — split further. |
| **INCAPACITY** | below-threshold, missing-slots, skip | The LLM takes over, and receives FastRule's **partial parse** rather than starting cold. |

**REFUSAL was a real bug.** The per-item path re-implemented the commit test
with the gates omitted, and re-committed what the front door had vetoed.

**A deferral never wastes the work.** `state.fastrule_verdict` carries the
reason, its class and the confidence forward, and `segment` uses it as both
evidence and prompt grounding.

**And FastRule is DETERMINISTIC** — a loop-back on unchanged text cannot get a
new answer, so `state.asked_fastrule` sends it straight to the model instead.

---

## 3 · History

This file **is** FastRule. v1 is retired (2026-09-07); its code is at
`retired/fastrule-v1/` and the last commit that ran it is tagged `fastrule-v1`.

The switch was an **identical-behaviour port**: every regex and check came over
unchanged, and a diff harness proved **7,200 / 7,200 verdicts identical** before
v1 was stood down. The deltas the new structure exists *for* — pre-parse
atomicity, split-and-recurse, calibrated Scorer signals, slot-specs-as-data —
land as later measured batches, not as part of the port.

---

## 4 · The dataset — `datasets/`

**7,200 rows**, generated from the banks in `datasets/banks/`:

| bank | what it holds |
|---|---|
| `complex_patterns.json` | 321 templates with `atomic`, item counts, and **named slots** |
| `simple_patterns.json` | single-item shapes |
| `fillers.json` | slot values — invented names only, no personal vocabulary |
| `categories_fixture.json` | category assignment fixture |

Split into halves; **the test half reports aggregates only and never spawns a
hypothesis**, the same rule as the verification corpus.

> These templates turned out to be worth far more than the board they were
> built for. Because they carry `atomic` and *named* slots, they generate
> **exact segment gold by construction** — 1,554 of Segmentation's 1,694 rows
> come from them. See `../segmentation/ARCHITECTURE.md` §4.

---

## 5 · The evaluation — `experiments/`

Scored against its **product shape**, not against a generic accuracy:

> **defer on non-atomic items, create the right event/task otherwise.**

| metric | |
|---|---|
| **atomic handle-rate** | PRIMARY — how often it acts on a single-item command instead of deferring |
| **correct-on-handled** | PRIMARY — of those, how many are right |
| date / time correctness | |
| invention rate | |
| harm | |
| non-atomic diagnostic split | did it defer for the *right* reason |

`experiments/fastrule_shape.py` is the board. `experiments/fast_sandbox.py` is
the deterministic fast lane — seconds, full-set allowed, selective-classifier
scoring, held-out aggregates only.

**Always name the metric with the number.** "handle rate 49.7% → 53.5% on the
7,200 test half (atomic rows) — it now acts on half of the single-item commands
instead of deferring them" is a result; "53.5" is not.

---

## 6 · Layout

```
fastrule/
    ARCHITECTURE.md   this file
    fastrule.py       the system itself
    datasets/         7,200 rows + the banks that generate them
    experiments/      fastrule_shape.py · fastrule6k.py · fast_sandbox.py
```
