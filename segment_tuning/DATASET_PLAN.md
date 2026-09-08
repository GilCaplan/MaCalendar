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
