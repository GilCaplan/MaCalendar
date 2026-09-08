# Segment tuning — the run log

One entry per cycle. Each states the hypothesis BEFORE the run, then actual vs.
expected, then what it means. A score is a pointer, not the point.

**Every number here names three things: the DATASET, the METRIC, and what it
MEANS.** "55.9%" is not a result; "exact-row 33.1% → 43.3% on the segment-tuning
train half (1,040 rows) — it now gets action, time and tag all three right on
4 rows in 10 instead of 3" is.

## The corpus these numbers are computed over

`segment_tuning/data/*.jsonl` — **1,694 rows**, split BY FAMILY (a family never
straddles), ~60/40 train/test.

| | rows | train | note |
|---|---|---|---|
| `nosplit_traps.jsonl` | 65 | 37 | hand-written, 11 must-NOT-split traps |
| `split_traps.jsonl` | 75 | 43 | hand-written, must-split shapes |
| `generated.jsonl` | 1,554 | — | 259 template families, gold by construction |

Ask-count spread `{1: 978, 2: 604, 3: 110, 4: 2}`. The **test half is not scored
except at a milestone**, reports aggregates only, and never spawns a hypothesis.

---

## Cycle 1 — 2026-09-08 · the corpus's first contact with the code

**Hypothesis.** Building gold from the templates' *structure* (slot names, not
surface regex) would disagree with FastSeg wherever FastSeg was wrong, and the
disagreements would be findable. Predicted change: none — this cycle was meant
to produce a baseline, not move a number.

**What actually happened: the generator found four bugs, three of them in the
code rather than in the gold.** That was not the predicted outcome and is the
main result of the cycle.

### The four

1. **The invariant existed as three drifted copies.** The runtime guard in
   `llmseg.accept` would reject a model answer that defaulted an untimed item
   to `"today"` — which is what SPEC tells it to do. A correct answer was
   being thrown away for being correct. Now one `invariant.py`, imported by
   the guard, the scorer and the generator.
2. **`find_time_refs` asserted longest-match in a docstring, not in code.**
   The pattern list is grouped by KIND, so bare `today` outranked `a week from
   today`; "plan lunch a week from today" yielded `today` and stranded "a week
   from" in the action. Matches are now collected and taken longest-first, so
   the ordering of `_TIME_PATTERNS` cannot silently decide the answer.
3. **The time dropped its preposition.** SPEC captures AS SPOKEN — `on the
   15th`, `for christmas day` — but only some patterns spelt the preposition
   out. It cost twice: missing from the time AND stranded in the action
   ("schedule flight to Chicago for"). One absorb step fixed both.
4. **Two labelling rules were genuinely undecided, and the two hand-written
   files had been built to OPPOSITE conventions.** Settled in SPEC:
   - **The date floor** — the day defaults to `today`, the clock never does.
     FastSeg emitted `at 8` while the tuned LLMSeg prompt taught `today at 8`,
     so the deterministic and model halves disagreed on *every* clock-only
     item and the accept step paid for it on each.
   - **Edge distribution is directional** — leading times scope forward per
     slot class; trailing times reach back only to an item with no time at all.
     Per-class in both directions gave "do i have anything this weekend and
     book the haircut at 3:45" the gold `this weekend at 3:45` for the
     question.

### FastSeg alone — segment-tuning TRAIN half, 1,040 rows

| metric | before | after | |
|---|---|---|---|
| exact-row (action+time+tag) | 33.1% | **43.3%** | +10.2 |
| exact-set (actions only) | 51.5% | **55.9%** | +4.4 |
| time on a SPOKEN time | 49.1% | **66.1%** | +17.0 |
| NO-LOSS violations | 304 items / 275 rows | **152 / 145** | −50% |
| right item count (the CUT) | 78.6% | 78.6% | unchanged |
| tag accuracy | 83.7% | 83.7% | unchanged |
| latency | — | **~3 ms/row** | no model |

**What it means.** The component now keeps the words it was given and puts the
time in the right place far more often — but it cuts in exactly the same places
it did before, because nothing in this cycle touched the splitter. The two
unchanged lines are the honest ones: **the cut and the tagger are now the
ceiling**, and every point of exact-row above ~55% has to come from them.

### Where it is weak, read off board F

| trap | exact-row | reading |
|---|---|---|
| `lead_time` | 0.0% | "remind me an hour before X" — treated as a time, not a modifier |
| `time_list_vs_range` | 0.0% | "at 9 and 2:30" vs "from 9 to 2:30" |
| `joiner` | 17.9% | verbless conjuncts: "gym at 7, tomorrow meeting at 10" |
| `three_ask` | 2.4% | three-item commands |
| `attendee` | 83.3% | name coordination is solid |
| `np_decoy` | 69.4% | the must-not-split decoys mostly hold |

**Under-split 189 rows vs over-split 34** — the designed bias is intact
(precision 97.2% / recall 86.2%). Under-splitting is the cheap failure: the
deep track gets two more chances at it, whereas an over-split makes garbage
immediately.

### Next cycle's hypothesis

Fix the **verbless-conjunct cut** ("gym session at 7, tomorrow meeting at 10"
comes back as one piece). Expect: right-item-count 78.6% → ~84% and `joiner`
exact-row 17.9% → ~40% on the train half; expect exact-row to follow about
half as far. Expect NO effect on tag accuracy — if tag moves, something
unintended happened and the run should be read again before it is believed.

---

## Cycle 2 — the verbless conjunct · PREDICTED AND CONFIRMED

**Hypothesis** (registered above): right-item-count 78.6% → ~84%, `joiner`
exact-row 17.9% → ~40%, no tag movement.

**Actual — segment-tuning TRAIN half, 1,040 rows:**

| metric | before | after | predicted |
|---|---|---|---|
| right item count (the CUT) | 78.6% | **84.5%** | ~84% ✓ |
| `joiner` trap exact-row | 17.9% | **42.3%** | ~40% ✓ |
| exact-row | 43.3% | **48.4%** | ~46% ✓ |
| item F1 | 91.4% | **94.1%** | — |
| `np_decoy` (must-NOT-split) | 69.4% | **69.4%** | unchanged ✓ |
| tag accuracy | 83.7% | 84.7% | unchanged ✓ |

**The rule.** A clause splitter cannot see "set up physical therapy at 9:15 and
birthday dinner at midnight" — the second conjunct is a bare noun phrase with
no verb. The evidence used instead: **both sides carry their own time
reference, AND the right side has content that is not part of its time.** The
second condition is what protects the decoys — "walk the dog at 9 and 2:30"
has nothing left on the right once its time is removed, so it does not split.

Cost: under-split 189 → 110 rows, over-split 34 → 51. Precision fell 97.2% →
96.2% while recall rose 86.2% → 92.1%. Worth it, but the bias is now less
lopsided than designed and should not be pushed further without cause.

---

## Cycle 3 — the tagger · TWO HYPOTHESES REFUTED, THIRD ONE PAID

Task recall had not moved all session (70.7%; 159 tasks called events). Three
candidate explanations, tested before any was built.

**1 · "A POS/dependency parse will fix it." REFUTED, decisively.**
Every parser variant scored WORSE than the tagger already in place
(`pos_sizing.py`, same 1,383 matched items):

| tagger | accuracy | task→event fixed | new event→task |
|---|---|---|---|
| current `tag()` | **84.7%** | — | — |
| syntactic (root POS) | 65.0% | +116 | +359 |
| lexical (verb lists) | 80.1% | −7 | +27 |
| lexical → syntactic | 68.5% | +72 | +267 |
| clock-time control | 59.3% | +102 | +424 |

Why: calendar commands are VERB-rooted imperatives — "add vet appointment to
my calendar" has root `add`/VERB, so "VERB → task" calls an event a task. Of
the 439 items no verb list decides, **349 are events**. The root POS is
anti-correlated with the answer. **This killed a planned spaCy rewrite of
FastSeg**, which is the cycle's most valuable output.

**2 · "The destination distributes like an edge time." REFUTED.**
118 of the 159 errors have no list marker in the item because the split
stripped it ("remind me to X and to Y" → item 2 is a bare "to Y"), so the
theory was that `remind me to` / `on my list` should scope every item without
its own. Simulated both readings:

| variant | fixes | breaks | net |
|---|---|---|---|
| blanket command-level override | 46 | 31 | **+15** |
| scoped (only items with no local verb) | 11 | 34 | **−23** |

Predicted ~+150. The scoped version is *worse* because the items with no local
verb evidence are overwhelmingly events, so they inherit "task" and break.

**3 · "Use the lexicon only where the current tagger says `event`." PAID.**

| tagger | accuracy | task recall | event recall |
|---|---|---|---|
| baseline | 84.7% | 70.7% | 94.2% |
| lexicon when it knows, else current | 82.4% | 78.5% | 85.6% |
| **lexicon only where current says event** | **87.5%** | **87.1%** | 87.8% |

Asymmetric on purpose: the current tagger's `task` verdicts are already good
(89.3% precision), so only its `event` verdicts are second-guessed. Net +2.8pp
accuracy, +16.4pp task recall.

**Not yet banked.** The verb lists were written by reading TRAIN failures, so
this is a train-derived hypothesis and only counts once it survives the sealed
half. It is also a *lexicon*, which is the kind of thing that overfits
quietly — the test-half number is the one to believe.
