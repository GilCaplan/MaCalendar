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

## 2 · There are exactly TWO failure modes, and every board is measuring one of them

Worth pinning down, because the boards name things in ways that invite
double-counting:

**THE CUT — which ITEM a word lands in.** Board A: item count 84.5%, 110 rows
under-split, 51 over-split. Board B's `NO-LOSS violations` (146 items, 415 tokens,
136 rows) is **the same thing counted in tokens, not a third defect** —
`_lost_tokens` compares a *matched* gold item against its *matched* predicted item,
so a "loss" means those words reached a DIFFERENT item. 136 loss rows against
110 + 51 mis-cut rows is the same population.

> Checked directly rather than assumed: run FastSeg over all 1,040 train rows and
> **0 content tokens of the transcript are lost**. The runtime invariant holds. The
> board's label reads like deletion and is not.

**THE SPAN — which FIELD a word lands in, inside one item.** `tokens(action) ∪
tokens(time)` covers everything, so under-detecting the time **forces** the
remainder into the action; there is no third place. "Action polluted" and "time
truncated" are one event seen twice, which is why the ablation's singles understate
so badly (+14 and +55 against **+205** together) — fixing either field alone still
fails the row because the boundary is what is wrong.

**The span explains the downstream number completely.** Given `time="the 20th"` and
`action="book dentist of november"`, the resolver correctly resolves the 20th;
November was never handed to it, and no downstream work can recover it. That is why
1,445 value errors attribute here.

So Phase 1 works the SPAN and Phase 3 works the CUT, and no phase is aimed at
board B's loss line — it will move when the cut does.

---

## 3 · The order of work

### Phase 1 — the time-span vocabulary  ·  the +205 lever  ·  ONE table

#### The research behind this list (2026-09-09)

Two independent sources, and they agree — which is why the table below is a
finding rather than a guess.

**(i) The dataset's own failures, as a census.** For all 1,040 train rows, the
token sequences gold puts in `time` that FastSeg leaves in the action:
**53 distinct phrases, 192 occurrences.** The reverse direction is almost empty —
`evening` 3x, `daily` 1x — so FastSeg barely ever OVER-captures a span. Recall of
spans is the whole problem, and that matches item precision 96.2% against the span
numbers.

**(ii) The real-speech corpus**, 11,932 texts with the sealed 300 excluded, mined
for time expressions. Of 515 distinct forms, **343 never appear in segmentation's
dataset at all** — and a handful of those are pattern classes the dataset cannot
show, because it has no rows for them.

#### The classes, ranked, with both sources' evidence

| # | class | forms | dataset census | corpus | trap now |
|---|---|---|---|---:|---|
| 1 | **lead time** | `15 minutes before`, `an hour before`, `two hours before`, `a day before`, `a week before` | **48** | 26+ | `lead_time` **0.0%** on 72 rows |
| 2 | **ranges** | `between 2 and 4`, `from 6 to 8`, `from 3 to 4pm` | **33** | 59 distinct | `time_list_vs_range` **2.8%** on 36 |
| 3 | **spoken clocks** | `ten thirty`, `twenty past eight`, `ten past six`, `at nine` | **20** | high | — |
| 4 | **end of a month** | `the end of the month`, `the end of september` | **18** | 74 | — |
| 5 | **coarse + modifier** | `late afternoon`, `early evening`, `first thing in the morning` | **17** | 130+ | `texture` 37.5% |
| 6 | `around lunchtime` | | **14** | — | — |
| 7 | **frequency cadences** | `every weekend`, `twice a week`, `once a week` | **13** | 79 | `recurrence` 61.1% |
| 8 | `the rest of the day` | | 4 | — | — |

Classes 1–8 account for **167 of the 192** missed occurrences.

#### Four classes ONLY the corpus reveals — and these need dataset rows too

Each verified to produce **no time reference at all** today:

| class | example | corpus | why the dataset cannot show it |
|---|---|---:|---|
| **offset in HOURS** | `in two hours`, `in one hour` | **25** | the pattern covers `day\|week\|month` and not `hour`; the dataset has **zero** rows of it |
| **plural weekday = recurrence** | `on sundays`, `sundays` | **31** | `_WEEKDAY` has no plurals, so `\bsunday\b` fails on "sundays" — and the MEANING is a weekly series, not a date |
| **yearly / one-word cadences** | `every year`, `everyday` | **38** | neither is in the recurrence pattern. `yearly` is now a real cadence downstream (2026-09-08), so this is the seam |
| **`12 noon`** | | 12 | `noon` matches and the `12` strands — the `at late` defect in another costume |

Also found and left out deliberately: **`before it starts` / `before the meeting`
/ `before my meeting at 3pm`** (24 occurrences). A `before` pointing at ANOTHER
EVENT is a relation, not a lead time, and the next stage already draws that line
(`resolve_lead_time`'s tail test). Capturing it here needs a ruling first, so it is
a question rather than a pattern.

And **`thanksgiving`** (6) is out of scope: US-specific, and the Jewish calendar
comes from `hebrew_calendar`, not a regex.

#### Two defects that are the SAME defect

`at late` (14x) and `12 noon` (12x) are one bug: a **shorter pattern matches inside
a longer phrase and the remainder strands in the action**. `afternoon` wins over
`late afternoon`; `noon` wins over `12 noon`. The table is already documented as
longest-first — these are entries missing from it, not a broken rule. Adding a
longer alternative fixes each.

#### One pattern fixes two symptoms

`9 in the morning` is currently TWO refs (`in the morning` as a *date*, the `9`
stranded). Class it as ONE clock span and the second symptom goes too: because
`in the morning` is classed as a day, `assign_times` thinks the item has a day and
**skips the date floor**, so gold's `today at 9 in the morning` comes back as
`at 9 in the morning`. That is 4 of the 5 sampled `and_compound` failures. Fix the
span, and the floor starts applying.

#### Ordering, measured — a small residual, not a lever

Gold orders a time string by SLOT CLASS (day/recurrence → bound → clock);
`assign_times` joins by POSITION in the text. So
`every week at 8 o'clock until next tuesday` is scored against
`every week until next tuesday at 8 o'clock` — same tokens, different order, and
`until_through` (33.3%) is where it shows. But board B prices it: time accuracy
78.2% against 78.9% same-tokens-any-order, so ordering alone is **~10 items**.
Worth fixing while in the code, never worth a phase.

**Target**: exact-row 51.5% → the ablation's 71.1% is the honest bound for span
work alone. Past ~65% the phase has paid for itself.

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

## 3b · Does the DATASET need updating? Yes — four classes, and only four

The census in Phase 1 is derived FROM the dataset, so the dataset already exercises
classes 1–8; the CODE lacks them. Adding rows there would measure nothing new.

The four corpus-only classes are different: the dataset has **zero rows** for them,
so no board can currently see them fail. Those need rows before the patterns are
written, or the fix ships unmeasured:

    offset in hours          "call Sam in two hours"
    plural weekday           "gym on sundays"          (a SERIES, not a date)
    one-word cadences        "yoga every year", "walk the dog everyday"
    12 noon                  "lunch at 12 noon"

Where they go, without disturbing anything: `datasets/split_traps.jsonl` and
`nosplit_traps.jsonl` are the hand-written trap files and this is exactly what they
are for — a named trap, a handful of rows, gold written by hand. **Not** the
generated set, whose templates would spray each form across hundreds of rows and
drown the classes that are already covered.

One caveat on the corpus figures: they count occurrences of a form in 11,932
utterances, which is evidence of what people SAY, not of what the dataset should
weight. Four traps of a dozen rows each is the right size; matching corpus
frequency would rebuild the dataset around am/pm spellings.

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
