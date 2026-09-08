# The real-speech dataset

The missing input distribution.

Every board this project owns measures **well-formed prompts**.
`assistant/engine/fastrule/datasets/`'s 7,200 rows are clean single-clause commands (mean 11.0
words, no decimal-point times, no self-corrections). The 3,000-row
verification pool is tidied history. Meanwhile `scripts/weekly_review.py` —
the only instrument pointed at real usage — reads a **50% flag rate**, against
a sealed-test engine number in the 80s.

The benchmarks are not lying. They are measuring a different distribution. A
dataset that contains no rambling multi-event dictation, no speech-recognition
damage and no self-correction cannot tell you whether the engine survives any
of them, and an improvement loop run against it will optimise clean prompts
while real usage stays where it is.

This set is that distribution, rebuilt: **1,200 rows whose SHAPE is measured
from the author's real command history and whose CONTENT is invented.**

---

## The privacy rule, first, because it governs everything else

The source is `~/.assistant_tools/nlu_memory.db` — the author's real commands.
It was opened **read-only** (`file:...?mode=ro`), read once, and reduced to
aggregate statistics. Three rules follow, and they are absolute:

1. **No real utterance is copied anywhere.** Not into the generated rows, not
   into this file, not into a commit message. Every number below is an
   aggregate over 83 rows; no row is quoted, paraphrased closely enough to
   identify, or reconstructable from what is written here.
2. **No personal vocabulary reaches a generated row.** The generator runs the
   leak gate `scripts/gen_personas.py` uses — it imports that gate rather than
   reimplementing it — reading the real `~/.assistant_tools/vocab.json` (374
   entries) read-only and **failing the build** if any word of it (>= 5
   characters, word-boundary; the standard
   `tests/unit/test_artifact_claims.py` sets) appears in a row's text, its
   clean base, or any ground-truth slot value.

   It then goes **one step stricter than the persona gate**, and has to: that
   gate checks the vocabulary's corrected WORDS, which is right for a dataset
   of invented nouns, but this dataset's entire job is generating mangled
   surface forms — and a vocabulary ALIAS *is* a real mangled surface form of
   a real personal word. That is the one string a speech-damage generator
   could plausibly collide with while the word-side gate stayed green, so both
   sides are checked (374 words + 37 aliases in the current build).

   Three entries are declared general in `allowed_words.txt`, with reasons —
   all three are ordinary calendar English the vocabulary layer happened to
   learn as *repair* pairs, not personal shorthand.
3. **The store is never written.** The generator does not import `assistant`
   at all; the scorer inherits `fastrule_shape`'s import-time redirection of
   every `MACALENDAR_*` store to a scratch directory. Verified by mtime: the
   real db, vocab and trace bus are untouched by every run in this dataset's
   construction.

The content banks are consequently generic to the point of blandness —
`Jordan`, `dentist appointment`, `walk the dog`, `cold brew`. **That is the
design.** The claim this dataset makes is about *shape*, and shape is exactly
what survives the substitution.

---

## What was measured (n = 83)

The store held 149 rows, of which 66 carried `source = "test"` (synthetic
traffic from development) and were excluded by the same rule
`memory.retrieve()` uses. **83 real utterances remain** — 50 from the Mac, 33
from the phone, spanning 2026-08-26 to 2026-09-07.

**This is a small sample and the tail estimates are thin.** Say so out loud
whenever a number from here is quoted: the 3-ask bucket rests on one row.

### Asks per utterance (hand-annotated over all 83)

| asks | rows | share |
|---:|---:|---:|
| 0 (no ask at all) | 4 | 4.8% |
| 1 | 66 | 79.5% |
| 2 | 10 | 12.0% |
| 3 | 1 | 1.2% |
| 4 | 2 | 2.4% |

Multi-ask (>= 2): **15.7%** of all rows, 16.5% of rows carrying any ask at
all. Mean 1.23 asks over non-null rows; maximum 4.

Annotation method: every one of the 83 was read and its ask count judged by
hand. A self-correction ("book it Monday — no, Tuesday") counts as **one**
ask, not two, which is the distinction that matters most and the one no
automated counter gets right.

### Disfluency and surface shape (regex detectors, reproducible)

| shape | rows | rate | same detector on FastRule 7,200 |
|---|---:|---:|---:|
| wake word present in `raw_transcript` | 30 | 36.1% | — |
| same day named 2+ ways in one utterance | 23 | **27.7%** | 4.15% |
| declarative framing ("i have", "there will be") | 20 | **24.1%** | 1.79% |
| decimal-point time ("4.30 pm") | 15 | **18.1%** | **0.00%** |
| bare "N o'clock" | 12 | 14.5% | — |
| self-correction ("sorry", "i mean", "one moment") | 9 | **10.8%** | 0.43% |
| opener filler ("alright,", "right,", "again,") | 6 | 7.2% | 2.92% |
| fused-digit time ("910am", "1040") | 6 | **7.2%** | **0.00%** |
| chaining cue ("in addition to that", "as well as") | 6 | 7.2% | 0.39% |
| trailing dangler (ends on "to"/"and"/"with") | 6 | 7.2% | — |
| politeness frame ("can you", "please") | 5 | 6.0% | — |
| trailing hedge ("yeah", "okay", "as well") | 5 | 6.0% | — |
| `raw` differs from `transcript` (vocab repair fired) | 5 | 6.0% | — |
| meta-addressing ("so do that as well") | 3 | 3.6% | — |
| fragment (<= 3 words) | 3 | 3.6% | — |
| view tag prefix | 1 | 1.2% | — |

The right-hand column is the gap this dataset closes. **Two of the most
frequent real shapes occur exactly zero times in 7,200 FastRule rows.**

### Length

Mean 15.3 words, median 12, p90 28, max 92 (wake-word suffix stripped).
Buckets: 1–3w 3.6% · 4–8w 24.1% · 9–15w 37.3% · 16–30w 28.9% · 31–60w 4.8% ·
61+w 1.2%. FastRule 7,200 for comparison: mean 11.0, median 10, **max 29** —
its longest row is shorter than the real distribution's 90th percentile tail.

Date expressions per utterance: mean 1.25 (0: 12 rows, 1: 48, 2: 15, 3+: 8).
Time expressions: mean 0.80 (0: 32, 1: 41, 2: 6, 3+: 4).

### Speech-recognition damage (hand-annotated; a row may carry several kinds)

| kind | rows | rate |
|---|---:|---:|
| proper-noun homophone substitution | 16 | 19.3% |
| number-format damage | 8 | 9.6% |
| loanword rendered as English word salad | 7 | 8.4% |
| **command verb** heard as content | 6 | 7.2% |
| cut-off / truncated audio | 6 | 7.2% |
| wake word bleeding into content | 4 | 4.8% |
| possessive fused or lost | 3 | 3.6% |
| compound word fused | 3 | 3.6% |
| stuttered / doubled word (automated) | 2 | 2.4% |

**Any damage: 39 of 83 = 47.0%.** Kinds per row: 0 in 44 rows, 1 in 29, 2 in
7, 3 in 2, 4 in 1.

Damage is strongly length-dependent, which is the single most useful thing
this measurement produced:

- **<= 12 words: 28.6% damaged** (12/42)
- **> 12 words: 65.9% damaged** (27/41)
- multi-ask rows: 46.2% damaged (6/13)

A long utterance is not merely harder to segment — it arrives **more than
twice as broken**. Any evaluation that draws its long rows from clean text is
measuring the easy half of the problem.

### What the user thought of the results

Feedback on those 83: rejected 45.8%, skipped 22.9%, approved 18.1%,
corrected 13.3%. The 13 corrected rows carry the author's own ground truth and
were used to sanity-check the ask annotation (10 corrections name one action,
1 names two, 2 name four).

---

## How the shapes became rows

Same machinery as `assistant/engine/fastrule/datasets/`, one layer taller.

**Layer 1 — the clean base.** An utterance is composed of 0–4 *asks*. Each ask
is a skeleton from `banks/ask_patterns.json` in one of the four registers the
real store uses (imperative / declarative / bare / polite), with slots filled
from `banks/fillers.json`. Ground truth falls out of composition: the
generator chose the asks, so it knows the event count, the task count, the
action, whether the utterance is atomic, and what went into every slot.
Placeholders follow the FastRule generator's contract
(`scripts/gen_fastrule_dataset.BASE_INFO`), imported rather than copied, so
the same scorers read both datasets.

**Layer 2 — the speech layer.** The clean base is then run through the
transforms in `banks/speech.json`, each one a shape from the table above and
each firing at a rate calibrated to its measured marginal. **A transform
changes what was HEARD, never what was MEANT** — that invariant is what keeps
ground truth correct through the damage:

- a time drawn as `4:30pm` may surface as `4.30 p.m.`, `430PM` or (for
  afternoon hours) `4 o'clock`; `slots.time_phrase` stays `4:30pm`;
- a date drawn as `next thursday` may surface as `next week on thursday`;
  `slots.date_phrase` stays `next thursday`;
- an opener, a mid-sentence filler, a stutter, a trailing dangler, a hedge, a
  meta-address, an apology, a truncated afterthought and a bleeding wake word
  attach without adding an ask.

Self-correction is generated by *naming a wrong value and fixing it*: the
sentence carries both, the ground truth carries only the corrected one. That
is the shape a parser has to survive, and it is the reason a hand-annotated
ask count was necessary — an automated counter reads the correction as a
second ask.

**Damage to a title or a name is different, and the choice is deliberate.**
When `Jordan` surfaces as `Gordon`, or `walk Jordan's dog` as
`walk Jordan Stalk`, the **ground truth becomes the surface form**, with the
intended value kept in `intended_title` / `intended_attendee` as diagnostic
metadata only. Nothing in the sentence lets a parser recover the intended
spelling; extracting what was actually said is the correct behaviour, and
repairing it is the vocabulary layer's job. Scoring the parser against a
spelling it cannot see would measure the wrong component.

The mangle tables are generic by construction — 26 invented first names with
plausible acoustic twins, twelve loanwords with their word-salad renderings,
eight fused compounds, six possessive constructions. None of them is the real
damage; all of them have the real damage's geometry. (One small confirmation
that the geometry is right: the generator's independently-authored verb table
contains `set a meeting -> set meaning`, and the real vocabulary file turns
out to hold exactly that repair pair. The table was written before that was
noticed.)

### Two pools, never blended

| pool | rows | asks-per-utterance | what it is for |
|---|---:|---|---|
| `faithful` | 800 | reproduces the measured real mix (0: 38, 1: 636, 2: 96, 3: 10, 4: 20) | **the real-usage proxy — quote this one** |
| `stress` | 400 | 1: 40, 2: 160, 3: 120, 4: 80 | the multi-ask tail, oversampled for diagnosis |

The real sample is too thin to slice the tail — one 3-ask row, two 4-ask rows
— so the stress pool exists to make that tail measurable at all. It is a
microscope, not a headline: **a board that averages the two pools is not a
statement about real usage**, and `scripts/realspeech_board.py` defaults to
`faithful` so the honest number is the easy one to get.

Because the per-ask transforms fire once per ask, the stress pool's shape
marginals run higher than the faithful pool's by construction. The generator
prints both columns; only the `faithful` column is calibrated against the
measurement.

### Generated vs measured (faithful pool)

`python -m scripts.gen_realspeech --shapes` prints this live.

| shape | generated | measured |
|---|---:|---:|
| date restatement | 26.8% | 27.7% |
| decimal time | 14.4% | 18.1% |
| bare o'clock | 16.9% | 14.5% |
| fused-digit time | 5.9% | 7.2% |
| self-correction | 11.6% | 10.8% |
| opener filler | 6.9% | 7.2% |
| trailing dangler | 7.9% | 7.2% |
| trailing hedge | 6.0% | 6.0% |
| cut-off tail | 6.9% | 7.2% |
| meta tail | 3.2% | 3.6% |
| stutter | 2.6% | 2.4% |
| view tag | 1.9% | 1.2% |
| name mangle | 16.2% | 19.3% |
| verb mangle | 7.9% | 7.2% |
| **ANY STT damage** | **46.1%** | **47.0%** |

Every shape lands within ~4 points of its measured rate; the residuals are not
chased further because the measurement itself has an n=83 confidence interval
several times wider than the residual.

Length, faithful pool: mean 13.2, median 11, p90 22, max 59 — **shorter than
the real distribution** (15.3 / 12 / 28 / 92). The generated asks carry less
descriptive material than real ones do. This is the dataset's clearest known
under-representation; see below.

---

## The row schema

Same shape as `assistant/engine/fastrule/datasets/`'s, so `assistant/engine/fastrule/experiments/fastrule_shape.py` reads it
unmodified.

```json
{
  "id": "rs_e1_decl-f017",
  "text": "i have book club this coming monday at four sorry, i mean 9 o'clock",
  "clean": "i have {event_title} {date} at {time}",
  "split": "train",
  "tier": "realspeech",
  "pool": "faithful",
  "family": "rs_e1_decl",
  "register": "decl",
  "join": "period",
  "n_asks": 1,
  "shapes": ["date_restatement", "date_weekday_relative", "selfcorrection",
             "spelled_oclock"],
  "raw_text": "i have book club ... , execute.",
  "expect": {
    "events": 1, "tasks": 0, "action": "create_event", "atomic": true,
    "slots": {"title": "book club", "date_phrase": "this monday",
              "time_phrase": "9pm"}
  }
}
```

- **`text`** — what the engine sees: the post-recognition transcript, wake
  word stripped, exactly as `nlu_memory.examples.transcript` holds it.
- **`raw_text`** — present on 36% of rows, mirroring the store: the same text
  with the wake-word suffix still attached. Diagnostic; not the scoring input.
- **`clean`** — the undamaged skeleton, for diagnosis only. Never score this.
- **`shapes`** — which speech transforms fired. This is what makes the set a
  *measuring* instrument rather than just a hard one: any metric can be
  sliced by shape to attribute a loss to a cause.
- **`pool`** / **`n_asks`** / **`register`** / **`join`** — slicing keys.
- **`expect`** — ground truth by construction. `events`/`tasks` count what
  should be CREATED (every non-create action expects 0, following
  `dataset/DATASET.md`'s count-correctness convention); `action` is the single
  action for a homogeneous utterance and `"mixed"` when the sub-asks span
  action types; `atomic` is `n_asks == 1`; slots use the FastRule numbered
  suffix convention (`title`, `title_2`, `title_3`, ...) per ask position.
- **Null rows** (`n_asks: 0`, `null_input: true`) carry
  `action: "propose"` and `must_not_commit: true`. The `propose` bucket is
  reused because its scoring semantics are exactly right here — a defer is
  correct, any commit is a violation — and `null_input` lets a future scorer
  separate the two populations. 4.8% of real usage is an utterance with no ask
  in it, and creating something from one is the most visible failure the store
  contains.

## The train/test split

**By family**, so a test row is an unseen *construction*, not an unseen filler
of a construction already trained on. 79 families = (structure x register x
join style); the split is stratified over (ask-count, primary action) using
`stratified_split` imported from the FastRule generator. A family never
straddles the split — the generator asserts it.

Current build: **875 train / 325 test** (72.9% / 27.1%). The ratio is a
consequence of family-level splitting with unequal family sizes, not a target;
the generator enforces a [70%, 88%] band and a 5% cap on any one family.

**The leakage rule from `DOCUMENTATION/experiments/ITERATION_PROTOCOL.md`
binds these test rows identically to every other sealed set: a test number may
be REPORTED, never ANALYSED for direction.** Hypotheses come from train-row
mining only. `scripts/realspeech_board.py` enforces the important half of this
mechanically — its `--shape` slicing flag refuses to run on the test split,
because slicing a sealed set by shape to decide what to fix is precisely the
leakage the protocol forbids.

## The one convention this dataset does not settle

A relative weekday has two defensible readings. On Wednesday 2026-09-09,
"next thursday" is either **tomorrow** (the soonest such weekday) or
**2026-09-17** (the Thursday of next calendar week). FastRule holds the
second reading; `fastrule_shape._phrase_to_date` holds the first. The project
has ruled neither, and "this monday" has the same problem in the other
direction (FastRule resolves it into the past).

This is a **product convention question for Gil (DEVQA), not a defect** — and
it must not be allowed to contaminate a real-speech board, because it is not
speech damage. So the generator flags every row whose ground-truth date is a
relative weekday with the pseudo-shape `date_weekday_relative` (30.1% of the
faithful pool), declared at generation time, before any score existed. The
board's `--undisputed-dates` flag drops them, and because the slice is defined
by a pre-declared convention dispute rather than by which rows failed, it is
legitimate on the test half too.

Measured impact, train / faithful (working numbers): date correctness
**71.8% -> 96.7%** once the disputed rows are excluded. Read that as: on
real-speech-shaped input FastRule's date handling is fine, and the number that
looked broken was an unresolved convention.

## How to regenerate

    python -m scripts.gen_realspeech             # generate + verify + write
    python -m scripts.gen_realspeech --no-write  # verify + composition table only
    python -m scripts.gen_realspeech --shapes    # the shape-rate table alone

Fully deterministic: `SEED = "realspeech-v1"` plus the three bank files are
the only inputs. No network, no wall-clock, no personal store, no LLM, no
dict-iteration-order dependence (every RNG stream is reseeded from a stable
string key, per family). **Two consecutive runs produce a byte-identical
`realspeech_1200.jsonl`** — verified; current build's md5 is
`c8121bd93f65883306574f6d31e2396d`, 1,200 rows, 793,967 bytes.

The script self-verifies before writing, and any violation raises rather than
writing a bad file: all texts unique, all ids unique, no family straddling the
split, train fraction inside [70%, 88%], no family over 5% of the set,
`atomic` agreeing with `n_asks`, event+task counts agreeing with the ask
count, no internal `_`-prefixed slot leaking into ground truth. The leak gate
runs last and fails the build on any hit.

Changing `SEED` or any bank reseeds rows; note the regeneration here and
record the new md5.

## How to score it

    python -m scripts.realspeech_board                        # faithful, test
    python -m scripts.realspeech_board --undisputed-dates     # ...minus the convention dispute
    python -m scripts.realspeech_board --pool stress          # the multi-ask microscope
    python -m scripts.realspeech_board --split train --shape selfcorrection

`scripts/realspeech_board.py` **owns no metric of its own**. It selects a
slice, writes it to scratch, points `scripts/fastrule_shape` at it and runs
it — so the numbers are literally the FastRule product-shape board (atomic
handle rate, correct-on-handled, date/time correctness, invented times,
severity-weighted harm, the non-atomic diagnostic buckets, propose defer
rate), produced by the same code that scores `assistant/engine/fastrule/datasets/`. Two boards
that share a scorer are comparable; two that share only a vocabulary are not.

Report per `ITERATION_PROTOCOL.md`: dataset + slice + metric + meaning, every
time. "dataset/realspeech faithful/test (n=243), atomic handle rate 70.3%"
is a report; "70%" is not.

## The first read (2026-09-07, build `c8121bd`)

FastRule at `assistant/engine/fastrule/fastrule.py` as committed, scored by
`scripts/fastrule_shape` through `realspeech_board`. Reported figures are the
**test half**; train figures are labelled working numbers, per
`ITERATION_PROTOCOL.md`'s lane-reporting rule.

**dataset/realspeech faithful/test (n=243)** — the real-usage proxy:

| metric | realspeech faithful/test | FastRule 7,200 test (same scorer) |
|---|---:|---:|
| atomic rows | 212 | 1,472 |
| **handled (committed)** | **70.3%** | 58.6% |
| **correct-on-handled** | **85.9%** | 70.5% |
| deferred (missed work) | 29.7% | 41.4% |
| resolvable date right | 73.1% (n=26) | 90.4% (n=197) |
| explicit time right | 96.2% (n=26) | 82.6% (n=115) |
| invented a time | — (n=0) | 0.0% (n=108) |
| harm score | 21 over 21 wrong commits, **0 destructive** | 252 over 254, 35 destructive |
| non-atomic deferred | 95.7% (all knowingly) | 73.0% (63.7% knowingly) |
| **half-executed** | **0.0%** | 5.5% |
| propose/null defer rate | 100.0%, 0 violations | 66.5%, 122 violations |

**dataset/realspeech stress/test (n=82)** — the multi-ask microscope, thin
(14 atomic rows; do not quote its atomic rates): non-atomic deferred 92.6%
(91.2% knowingly), half-executed 1.5%, covered 5.9%.

Three things this says, and one it does not:

1. **FastRule is not where the 50% real-usage flag rate comes from.** On
   real-speech-shaped input it handles MORE (70.3% vs 58.6%) and is MORE often
   right on what it handles (85.9% vs 70.5%) than on its own benchmark. The
   FastRule 7,200's complex tier is adversarial by design — decoys and
   interrogatives authored to be hard — not distribution-matched, so its
   numbers understate performance on ordinary traffic. The gap to real usage
   lives elsewhere: the deep track, the multi-ask half, or fields this scorer
   does not check (title text, attendee, description).
2. **It fails safely here.** Zero destructive errors, zero half-executions,
   100% defer on null utterances — every wrong commit was a spurious row.
   That is the failure mode the project's harm rule prefers, and it holds
   under speech damage.
3. **The date number is a convention dispute, not damage.** 73.1% looks bad
   until the pre-declared relative-weekday dispute is excluded; train-side,
   date correctness goes 71.8% -> 96.7% (working numbers). Time correctness
   under real speech damage is 96.2% — decimal-point and fused-digit times
   are being read correctly.
4. **What it does NOT say:** this is FastRule alone, on counts/action/date/
   time. It is silent on whether the engine produces the right TITLE from a
   damaged utterance, which is where the corrected rows in the real store
   most often disagreed with the assistant. That metric does not exist yet;
   `intended_title`/`intended_attendee` are in the schema so it can.

Train-side working numbers, faithful pool (n=557): handled 66.3%,
correct-on-handled 90.4%, non-atomic deferred 87.4%, half-executed 2.9%,
propose defer 93.3% (2 violations). Mining view (`--split train`) shows the
largest deferral reason is `below-threshold` (46 rows), then `skip` (30) and
`interrogative-create` (29); the largest single wrongness pattern is the
**declarative register read as a task** — "i have <event> <date> at <time>"
committing `create_todo` instead of `create_event`. That register is 24.1% of
real usage and 1.79% of the FastRule 7,200.

## What was deliberately left out

- **Self-contradicting restatements.** The real store contains utterances that
  name a day two *incompatible* ways. Those have no single right answer, so
  ground truth by construction is impossible and they are excluded. This makes
  the set **easier** than reality on exactly the shape that is 27.7% frequent.
- **Damage that destroys a slot.** Cut-off audio is generated as a truncated
  *afterthought* appended to a complete utterance, never as truncation of the
  ask itself, so the truncation never invalidates ground truth. Real cut-offs
  do both; only whole-utterance nulls model the destructive case.
- **Hebrew and liturgical vocabulary**, which is where a large share of the
  real loanword damage lives. Generic loanwords carry the same damage geometry
  with none of the personal content, but no observance-domain utterance is
  represented, so the engine's observance gate is unexercised here. Naming
  those terms in this file would itself widen the allowlist for no measurement
  benefit, so they are left unnamed.
- **Multi-turn context.** "the event you just made" appears as a *phrase*; no
  row is resolvable only against a previous command's state.
- **Absolute dates/times.** Everything is a phrase, per `assistant/engine/fastrule/datasets/`'s
  rule; resolving one is the parser's job, never this dataset's.
- **Title/attendee string scoring.** The set carries `intended_title` and
  `intended_attendee`, so a future scorer *could* measure vocabulary repair —
  but no metric here does, and `fastrule_shape` scores counts, action, date
  and time only.

## Honest limits

- **n = 83.** Every rate in the measurement table has a wide interval; the
  3-ask bucket is a single row. Treat the shape *inventory* as solid — every
  kind listed was observed and is reproducible from the store — and the
  *rates* as estimates that a few more weeks of usage could move by several
  points.
- **One speaker, one accent, one recognizer, twelve days.** This is the
  author's distribution, not "real speech". Generalisation to another user is
  what `dataset/personas/` measures; this set deliberately does not claim it.
- **Generated rows are shorter than real ones** (faithful p90 22 words vs 28)
  and carry less descriptive material per ask. Combined with the two
  exclusions above, **the faithful pool is somewhat easier than the real
  distribution it models.** A score here is a ceiling on real-usage
  performance, not an estimate of it.
- **The ask annotation is one reader's judgement.** It was made by reading all
  83 rows, and the 13 author-corrected rows agree with it, but a second
  annotator would move a handful of rows.
