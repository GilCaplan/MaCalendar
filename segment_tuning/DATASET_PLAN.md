# The segment dataset — what gets built, in what order

Everything lives in `segment_tuning/`. Nothing under `dataset/` is edited.

## The row

```json
{"id": "...",
 "text": "the command exactly as segment receives it (after step-1 repair)",
 "gold": [{"action": "...", "time": "...", "tag": "event|task|review"}],
 "family": "the shape",
 "traps": ["name-coordination", "shared-date-edge", ...],
 "source": "handwritten|template|persona|realspeech",
 "split": "train|test",
 "disputed": false}
```

`gold` is the whole contract in one field: how many items, what each says,
which time each carries, and what kind it is. Every metric reads off it.

## Build order — SMALL FIRST, and the reason

**Not** "generate thousands, then score". The order is chosen so the labelling
rules are proven before volume is committed to them, and so we get a number on
the CURRENT implementation early.

**1 · The trap inventory + labelling rules** — the spec. Every shape that has
   caused a real bug in this project, each with a worked gold row. This is the
   document that makes two people label the same command the same way.

**2 · ~100 hand-written rows, adversarial** — the honest half. Small enough to
   label carefully, and it forces the rules from step 1 to be precise: any
   command I cannot label confidently means the rule is underspecified, and
   that is worth finding at 100 rows rather than 4,000.

**3 · The scorer** — the six boards in §6 of DESIGN.md.

**4 · BASELINE: measure today's `segment.py` against 1–3.** A number for the
   current implementation before anything is changed. Without this there is
   nothing to improve against, and every later claim is unanchored.

**5 · The generator** — templates rendered as PARTS then joined, so gold is
   exact by construction rather than inferred. Volume and pattern coverage.

**6 · Real speech, hand-labelled** — the honest distribution.

**7 · Personas** — six voices, so an implementation cannot win by fitting one.

Steps 1–4 are the milestone. If the scorer disagrees with intuition on the 100
rows, the rules are wrong and no amount of generated volume fixes it.

## Where it actually stands (2026-09-08)

**1,694 rows — 140 hand-written + 1,554 generated.** Steps 1–5 are done.

| file | rows | what it is |
|---|---|---|
| `nosplit_traps.jsonl` | 65 | hand-written; all 11 must-NOT-split traps |
| `split_traps.jsonl` | 75 | hand-written; the must-split shapes |
| `generated.jsonl` | 1,554 | 259 template families, gold by construction |

Ask-count spread `{1: 978, 2: 604, 3: 110, 4: 2}`; tags
`{event 1416, task 1047, review 61}` — review is thin and is the next gap.

### The generator did not start from scratch — and that is the point

`dataset/fastrule/banks/complex_patterns.json` already held 321 templates built
for a different board, and they carry exactly what segment gold needs: an
`atomic` flag and **named slots**. Because the template says `{date}`, the
action/time split is *known* rather than inferred — a regex over rendered text
would just be FastSeg marking its own homework.

**187 of the 321 templates are `atomic`, and 74 of those contain a joiner**
("buy {item} and {item2}", "wash and fold the laundry"). Those 74 are decoy
rows a naive splitter fails — the most expensive kind to write by hand and the
cheapest to get this way.

**62 families are excluded, never guessed** (`--report` prints them):
38 `propose` templates ("should i book X?"), which ask for advice and so have
no honest label in a three-tag contract; 15 whose action or tag is underivable;
and 9 whose derivation failed validation. Two of the exclusions are open
questions for Gil, listed in DESIGN.md §11.

### Two bugs the generator found in the code it was built to measure

Generating gold from structure disagreed with the implementation twice, and
**both times the implementation was wrong**:

1. **The invariant rejected its own documented default.** SPEC says an untimed
   item gets `"today"`; the check called that an invention, because "today" is
   not in the text. It was three copies of one rule that had drifted, so the
   runtime guard in `llmseg.accept` would have rejected a *correct* model
   answer. Now one definition in `invariant.py`, imported by all three.
2. **Edge distribution is directional.** Distributing a trailing time per slot
   class gave "do i have anything this weekend and book the haircut at 3:45"
   the gold `this weekend at 3:45` for the question. Leading edges scope
   forward per slot class; trailing edges reach back only to an item with no
   time at all. Both `fastseg.py` and SPEC's scoping table now say so.

## Splitting — three rules, not one

Family-split alone is NOT enough; *Split and Rephrase* (ACL 2018) found
WebSplit leaked >89% of its unique simple sentences between halves, so a model
scored well by memorising fragments.

1. **Split by FAMILY**, never by row — the held-back half is unseen
   constructions, not the same shape with different nouns.
2. **Verify item-string disjointness.** No gold `action` string in the test
   half may appear in the train half. Checked mechanically, reported as a
   number, not assumed.
3. **Prompt examples come from TRAIN only.** Learned the hard way today: 9 of
   the 14 commands in my prompt-tuning set appeared verbatim in the prompt's
   own examples, so 11/14 was inflated — on the 5 unseen commands it was 3/5.
   Any example placed in a prompt is training data and must be split as such.

## Distribution — deliberately skewed

*MinWikiSplit* (2019): WikiSplit has exactly one split per source sentence, so
models trained on it learn "always emit two" regardless of input. If our rows
are mostly 1-or-2 asks, an implementation learns the COUNT rather than the
criterion, scores well, and fails on three-ask commands.

So: **oversample 3+ ask rows**, and **report the gold-count distribution beside
every score** so a number can never be read without its composition.

## What it measures

| board | question |
|---|---|
| A boundaries | exact-set match · boundary P/R/F1 · over vs under, separately |
| B action/time | no-invention (must be 0) · no-loss (must be 0) · time-assignment accuracy |
| C tag | accuracy · per-class P/R/F1 · confusion |
| D verifier | correction RECALL · correction PRECISION · "No Change" on known-wrong rows |
| E cost | model calls per row · wall clock |
| F attribution | which tier decided each row — the explainability line |

Board D is the one that decides whether the verifier ships: a component that
repairs 80% of errors while corrupting 5% of correct answers is net negative,
because correct answers vastly outnumber wrong ones.

## The first experiment, already specified

Once steps 1–4 exist, the first tuning question is settled and waiting: the
deterministic splitter is NOT idempotent — re-running it on its own output
changes the count on 2 of 5,014 FastRule rows and 8 of 847 real-speech rows,
and the rows it fixes are three-ask ones. Looping it to a fixed point is free.
Measure it, take it if it holds.
