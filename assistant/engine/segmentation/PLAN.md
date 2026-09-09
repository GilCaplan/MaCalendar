# Segmentation — the plan (2026-09-09)

Read `ARCHITECTURE.md` first: this file says what to DO and in what order, and it
does not restate how the stage works.

---

## 1 · The diagnosis — three measurements, one conclusion

**(a) The oracle ablation** (ARCHITECTURE §6) already named the lever:

| give FastSeg the gold for… | exact-row | gain |
|---|---|---|
| nothing | 51.5% | — |
| perfect time only | 52.7% | +14 |
| perfect action only | 56.6% | +55 |
| **perfect SPAN (action + time together)** | **71.1%** | **+205** |
| perfect everything on correctly-cut rows | 84.5% | +345 |

**(b) From the receiving end** (`decompose_validate/eval_metrics/end_to_end.py`,
1,924 rows): item recall **89.6%**, **162** spurious items, **106** provably
malformed (54 with two clocks in one item, 52 with an action ending in a joiner),
and **1,445** downstream value errors caused by different WORDS arriving — against
**0** caused by the resolver itself. The next stage scores 99.9% on gold items and
makes no value errors of its own on real ones, so the end-to-end **51.6%** row
accuracy is this stage's number.

**(c) Nine hand-probes through the real segmenter**, every one wrong:

| said | action | time | what the time field lost |
|---|---|---|---|
| `call mum 9 in the morning` | `call mum 9` | `in the morning` | the clock |
| `book yoga late afternoon` | `book yoga late` | `afternoon` | the modifier |
| `book dentist the 20th of november` | `book dentist of november` | `the 20th` | **the month** |
| `meeting from 3 to 4pm` | `meeting from 3` | `today to 4pm` | the range start |
| `call sam at ten thirty` | `call sam at ten thirty` | `today` | **all of it** |
| `book gym between 2 and 4` | `book gym between 2 and 4` | `today` | **all of it** |
| `physio the end of the month` | `physio the end of the month` | `today` | **all of it** |
| `standup every tuesday and thursday at 9` | `standup and` | `every tuesday thursday at 9` | the joiner leaked |

## 2 · The unit of failure is the SPAN, and that is one fix, not two

The invariant is `tokens(action) ∪ tokens(time)` covers every content token. So
**under-detect the time and the remainder is forced into the action** — there is no
third place for it to go. "Action polluted" and "time truncated" are the same event
seen twice.

That is why the ablation's singles understate so badly (+14 and +55 against +205):
fixing either field alone still fails the row, because the boundary is what is
wrong. It also means the fix has ONE address — the time-span vocabulary — rather
than one per symptom.

**And it explains the downstream number completely.** Given `time="the 20th"` and
`action="book dentist of november"`, the resolver correctly resolves the 20th;
November was never handed to it. No downstream work can recover that, which is why
1,445 value errors attribute here.

---

## 3 · The order of work

### Phase 1 — the time-span vocabulary  ·  the +205 lever  ·  ONE table

Every defect in §1(c) is a missing or short entry in `fastseg._TIME_PATTERNS`.
Concretely, ordered by how much real speech they cover (counts are corpus
occurrences from the 11,932-text mining below):

| class | missing form | corpus |
|---|---|---|
| coarse + modifier | `late afternoon`, `early evening`, `mid morning` — the bare word matches and the modifier strands | 130+ |
| clock + half-of-day | `9 in the morning`, `eight in the evening` — matched as *two* refs, so the clock lands in the action | 484 / 335 |
| **spoken clocks** | `ten thirty`, `three o'clock`, `twenty past eight`, `ten past six`, `quarter to five` — **not matched at all** | high |
| ranges | `from 3 to 4pm`, `between 2 and 4` — no range pattern, so both ends match separately or not at all | 59 distinct |
| month + ordinal, `of` order | `the 20th of november` — **this is §8.2**, and it is a missing pattern rather than a separate defect | 58 distinct |
| month ends | `the end of the month`, `the end of september` | 74 |
| bare coarse words | `night`, `lunchtime` | 52 / 122 |
| multi-day series | `every tuesday and thursday` as ONE recurrence span | — |

**The vocabulary already exists and is already adjudicated.** Building
decompose_validate's gold mined 11,932 corpus texts (sealed 300 excluded) into 248
hand-checked fillers — `datasets/normalization.py` there, and the coverage report
that produced it. Those are exactly the surface forms this stage must recognise.
The two stages are the same vocabulary at ISO-TimeML's two levels: **extent** here,
**value** there.

> **Copy the forms, never import the module.** Stages do not reach into each
> other, and that gold's independence from resolvers is what lets its board catch
> bugs. The mining is the SOURCE for hand-writing patterns here; the coupling
> stays at the level of a human reading a list.

Ordering inside the table is load-bearing and already documented: longest-first, or
a fragment wins over the phrase that contains it. `late afternoon` must precede
`afternoon`; `the 20th of november` must precede `the 20th`.

**Target**: exact-row 51.5% → the ablation's 71.1% ceiling is the honest bound for
span work alone. Anything past ~65% is the phase paying for itself.

### Phase 2 — the dangling joiner

`'standup and'`. A trailing coordinator is wrong on any reading, since "and"
belongs to neither field. One line: `_DANGLING` in `fastseg._tidy` strips a
trailing preposition already and simply does not list the coordinators.

**Deliberately after Phase 1**, because some instances are *symptoms* of the span
gap — `standup every tuesday and thursday` leaves the "and" only because the series
matched as two refs instead of one. Fix causes, then count what remains.

**Target**: the end-to-end board's "action ends in a joiner" count, 52 → 0.

### Phase 3 — the CUT: §8.1, an enumeration of times

`walk the dog at 9 and 2:30` must become TWO items sharing one action. Today it is
one item holding two clocks, and downstream cannot recover — one item is all the
words it gets.

This is a **new split mode**, not a tweak to the existing one:
`_split_verbless_conjuncts` splits into items with *different* actions, and this
distributes ONE action over N times. Keep them separate functions; merging them is
how the condition that protects the decoys gets lost.

The genuinely hard part, and the reason this is Phase 3 rather than Phase 1: the
same rule must still keep `take the tablets at noon and at six` — which is
arguably also an enumeration — and `meeting with Sam and Alex at 8`, which is a
person list. So the test cannot be "two times ⇒ split". §8.1's five gold rows are
the specification; write them first.

**This is also what retires `decompose.py`.** Its `_split_times` exists to
compensate for exactly this gap, and it produces garbage when it fires on a
malformed item (`'Untitled Event'`, measured). Segmentation doing the split
correctly is what lets the last v1 file in the next stage go — see TASKS item 1.

**Target**: item count 84.5% → 90%+; the end-to-end board's "two clocks in one
item" count, 54 → 0; then re-run TASKS item 1's audit A/B and delete
`decompose.py` if it holds.

### Phase 4 — §8.3, the date floor injected as a WORD

`fastseg.py:352` writes the literal `"today"` into `time`, which is **resolving**,
and this stage's contract is capture-do-not-resolve. It already costs two
workarounds (`Item.spoken()`'s filter and decompose_validate's boundary strip) and
caused one live audit failure.

Cheap to delete, not cheap to land: this stage's own gold encodes the floored form
(`experiments/generate.py` inserts `("day", "today")`, `check_prompt.py` asserts
it, `compare_boards.py` scores `time_default_ok`). So it means regenerating the
dataset and re-reading the boards. If both halves must agree on a format, normalise
at **LLMSeg's accept step** instead, so the bare form is what both emit.

**Target**: two workarounds deleted — that is the test that it actually landed.

### Phase 5 — TAG: try the logistic `kind` head

Recorded in ARCHITECTURE §2 Phase 3 with what it must beat (**87.5% accuracy /
89.9% task recall**) and three ways the measurement could lie. Oracle value +82
rows. Cheap: inference is a dot product.

Last because the ablation ranks it third, and because a tagger measured through a
broken span is measured through a broken span.

---

## 4 · The rules that keep this from becoming convoluted

The stage's shape is good and the work must not change it.

**The four-tier dispatch in `__init__.py` stays four tiers.** envelope → FastSeg →
LLMSeg → accept. No new tier, no fifth path, no second entry point.

**New time vocabulary goes in `_TIME_PATTERNS` and nowhere else.** It is one
ordered table with one rule (longest-first). A new module per class of expression
is how a table becomes a system.

**A new split mode is a new FUNCTION in `fastseg.py`, called from `cut`'s
`once()`.** Not a new file, not a new tier. `cut` stays the fixed-point loop it is.

**Boards stay the six in `experiments/score.py`.** A new number is a column, not a
file. The end-to-end board deliberately lives in the *consuming* stage, because it
measures the seam and would be marking its own homework here.

**Measure on the TRAIN half. The sealed 654 rows stay sealed** — never scored
except at a milestone, aggregates only, per `engine/TRAIN_TEST_SPLIT_CONVENTION.md`.

**Retire rather than accumulate.** `old_seg` (716 lines) is inactive but three
things are still borrowed from it: `_envelope_split`'s reader, FastSeg's
`_enforce_pinned_kinds`/`_kind_of`, and `object_rules.is_interrogative_create` in
the next stage. That is the exact shape `validate.py` had — not dead enough to
delete, not alive enough to reason about. Retire it the same way: extract the three
borrowed pieces to real homes, move the rest to `retired/`, tag it. Its own track,
between measured cycles, never during one.

**`llmseg` stays as it is** — off, flagged, and refuted four ways in §3. Keeping it
is a decision already made; the rule is only that it does not grow.

**`experiments/` is an archive as much as a toolkit**, and the ARCHITECTURE should
say which scripts are live tools and which are historical records, so nobody
re-runs a refuted experiment. `batch_sizing`, `pos_sizing`, `gate_sizing` and
`prompt_lab` are LLMSeg-era; `score`, `run_board`, `generate`, `compare_boards` are
live.

---

## 5 · Not doing, and why

**The refuted list in ARCHITECTURE §6 is binding** — a spaCy POS rewrite of the
tagger (65.0% vs 84.7%), destination distribution, gating LLMSeg, the model doing
the cutting (item count 83.9% → 57.3%), any similarity threshold for the action.
Each cost a measurement; none gets re-spent.

**Not touching the `Item` contract.** `(action, time, tag)` is frozen and the next
stage is built on it.

**Not chasing exact-row past the ablation's ceiling.** Perfect everything on
correctly-cut rows is 84.5%, so the cut bounds the row metric; work the cut
(Phase 3) rather than grinding the span past its own limit.
