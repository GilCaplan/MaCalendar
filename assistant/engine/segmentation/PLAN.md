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

#### HOW — three local changes, and deliberately no fourth

Read the code before planning the edit, and it is smaller than it looks.

**1 · Entries in `_TIME_PATTERNS`, and ORDER DOES NOT MATTER.** `find_time_refs`
collects every candidate from every pattern and then takes them
**longest-first, non-overlapping** — the docstring records that this was once only
a claim and cost 31 content-loss rows before it became a property of the code. So a
longer alternative automatically beats the shorter one inside it: adding
`late afternoon` fixes `at late` without being placed above `afternoon`, and adding
`9 in the morning` beats both `at 9` and `in the morning`. `_absorb_preposition`
then pulls the spoken `at`/`on`/`for` in on its own.

That is the whole of classes 1–8 and the four corpus-only ones: **table rows.**

**2 · `_slot()` must agree with the gold about two new kinds.** Today it is
`"clock" if kind == "clock" else "day"`, so a `lead` or a `range` would fall to
`"day"` — colliding with the real date, and worse, satisfying the
`any(_slot(r) == "day")` test that guards the date floor, which would silently stop
the floor applying.

**No third slot class is needed**, and the reason is worth writing down: the gold
already decided. `experiments/generate.py` has `_CLOCK_SLOTS = {time, time_range,
lead_time}` and `_DAY_SLOTS = {date, recurrence, query_range}` — two classes, and a
lead time is a **clock**. So the change is one line extending the clock side to
`("clock", "range", "lead")`, chosen to match gold rather than invented here.

**3 · The time string is joined in the wrong ORDER.** `assign_times` uses
`sorted(mine, key=r.start)` — position. The gold uses
`order = {"day": 0, "clock": 1}` with a stable sort — **slot class, day first**.
That is the `until_through` mismatch (`every week at 8 o'clock until next tuesday`
scored against `every week until next tuesday at 8 o'clock`). One line: sort by
`(slot_order, start)`. Board B prices order-only at ~10 items, so this is worth
doing because the code is open, not because it is a lever.

**Nothing else.** No new module, no new tier, no change to `cut`, no change to the
`Item` contract. If a fix in this phase wants a fourth kind of change, that is the
signal to stop and re-read this section.

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

**Phase 1 must come first for a MECHANICAL reason, not just a leverage one.** The
hard part of this rule is telling an enumeration from a decoy, and Phase 1 removes
most of the difficulty:

| piece | after Phase 1 | so the rule |
|---|---|---|
| `walk the dog at 9 and 2:30` | two clock refs | fires — distribute |
| `take the tablets at noon and at six` | two clock refs | fires — distribute (§8.1 says it should) |
| `book gym between 2 and 4` | **ONE range ref** | cannot fire |
| `meeting with Sam and Alex at 8` | ONE clock ref | cannot fire |

So once ranges are a single reference the test is simply **≥2 clock-class refs and
the right side has no own content of its own → distribute the action over them**.
Written before Phase 1 it would need a special case per decoy; written after, the
decoys exclude themselves by their reference count. That is the argument for the
order.

It also makes `_split_verbless_conjuncts`'s docstring true: it claims a joiner
inside a time reference is protected, and today `between 2 and 4` is actually saved
by the content test instead. With a range pattern the claim becomes the mechanism.

§8.1's five gold rows are the specification; write them first.

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

**Added 2026-09-09**: 22 rows in `nosplit_traps.jsonl`, TWO families per class —
one train, one test. That respects family-disjointness (a family cannot straddle
the split) while still giving the sealed half coverage of each class, which one
family per class could not do.

All four are visible and failing on the first run, which is the point of adding
them: `offset-hours` **0.0%**, `plural-weekday` **0.0%**, `one-word-cadence`
**0.0%**, `numbered-noon` **50.0%**. Before this the defects were real and no
board could see them.

Not the generated set, whose templates would spray each form across hundreds of
rows and drown the classes that are already covered.

One caveat on the corpus figures: they count occurrences of a form in 11,932
utterances, which is evidence of what people SAY, not of what the dataset should
weight. Four traps of a dozen rows each is the right size; matching corpus
frequency would rebuild the dataset around am/pm spellings.

## 3c · Is the dataset SOUND? Audited 2026-09-09 — yes, with three defects

Asked before building against it, because a dataset defect is invisible in every
number computed from it.

**It is sound where soundness is hard**, which is the part that cannot be fixed
later:

| check | result |
|---|---|
| rows | 1,694 — 1,554 generated + 140 hand-written |
| split | 1,040 train / 654 sealed |
| families | 314, and **0 leak across the split** |
| duplicate texts appearing in BOTH halves | **0** — so no leakage that family-disjointness would miss |
| duplicate texts with DISAGREEING gold | **0** — no contradictory labels |
| gold INVENTING content the text lacks | **0 rows** |
| family concentration | max 6 rows, median 6 — no family dominates |
| trap coverage | 44 traps, only 2 with ≤4 rows |
| ask-count spread | 1-ask 978 · 2-ask 604 · 3-ask 110 · 4-ask 2 |

> **STATUS 2026-09-09: defects 1 and 3 are FIXED, and the four missing classes now
> have rows.** Both fixes went into the GENERATOR rather than the .jsonl, so they
> cannot come back on the next regeneration. Defect 2 still needs a ruling.
>
>     rows      1,694 -> 1,711      (1,051 train / 660 test)
>     families    314 -> 322        leaked across the split: still 0
>     incoherent gold items  15 -> 0
>     duplicate texts        21 -> 0
>     baseline exact-row  51.5% -> 51.1% on the cleaned set
>
> And a defect the audit did not go looking for: **the generator was BROKEN.**
> `_BANKS` still pointed at `dataset/fastrule/banks`, a path that moved in the
> per-stage restructure, so it raised `FileNotFoundError` and the dataset could not
> be rebuilt at all. Nothing caught it because regenerating is a manual step and
> the committed `.jsonl` kept working — the failure mode of any build step that
> only runs by hand.

### Defect 1 — 15 incoherent gold items (9 train, 6 test)

The generator pairs a `{date}` filler with a `{time}` filler that contradicts it:

    "project sync tonight at 9 in the morning"        time='tonight at 9 in the morning'
    "...town hall on the calendar this evening..."    time='this evening at 9 in the morning'
    "...sales call ... this afternoon at 9 ..."       time='this afternoon at 9 in the morning'

Two halves of the day inside one item's time. Nobody says these, and a row whose
gold is itself incoherent cannot teach a correct boundary — the same defect class
already fixed in decompose_validate's generator (`_incoherent()`), and the same fix
applies: refuse the pairing and let the generator try another filler.

**The 6 in TEST must be fixed too, and that is not a leakage violation.** Auditing
whether gold is CORRECT is not reading test failures to direct a fix. Left alone, a
wrong gold in the sealed half depresses the sealed number permanently with no way
to diagnose it — which is the one thing the sealing rule cannot protect against.

### Defect 2 — 14 rows where GOLD loses content, and it is a spec question

All of them are tag questions, and gold drops the discourse tail:

    "cross off take out the trash does that seem right"   loses: does, seem, right
    "move the dentist to friday at ten is that ok"        loses: is
    "cancel yoga on thursday does that work"              loses: does, work

Dropping the tail is arguably the RIGHT product behaviour — "does that seem right"
is not part of the command — but the invariant says gold covers every content
token, so as written gold violates it. This is the `tag-question` trap sitting at
**0.0%**: gold drops the tail, FastSeg keeps it, and neither is wrong by its own
rule.

**Needs a ruling, not a patch.** Either the invariant gains an explicit exemption
for discourse tails (and `invariant.py`'s stop-word set is where it would live), or
gold keeps them. Until then the trap measures a disagreement about the spec rather
than a defect in the code.

### Defect 3 — 21 duplicate texts

Harmless: no cross-split pair, no gold disagreement. Worth de-duplicating for
tidiness, worth nothing for accuracy.

### The coverage gap — see §3b

Four pattern classes with **zero rows**. That is the only place new rows are
needed; classes 1–8 of the census are already present and adding rows to them would
measure nothing new.

### So: 29 rows of content defect out of 1,694 (1.7%)

The dataset does not need rebuilding. It needs a coherence guard in the generator,
one ruling on discourse tails, and four traps' worth of new rows.

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
