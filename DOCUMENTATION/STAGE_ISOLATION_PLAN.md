# Stage isolation — the plan of record (Gil, 2026-09-07)

_Supersedes the whole-engine cycle loop until it completes. Engine cycles
stay PAUSED; nothing is measured end-to-end until the parts are proven._

## The strategy, in Gil's words

1. **FastRule** — make sure it has the right dataset and metrics: it
   **defers on non-atomic items**, and otherwise **creates the relevant
   event/task**.
2. **Every other engine stage** — test each one in isolation. Build or tune
   a dataset per stage, **stored separately** (never mutating another
   stage's data), each with its own **train–test split and no leakage**.
   Improve each implementation on its own. Each stage may become **its own
   object** where that helps, otherwise stays a function — the code must be
   clean, not convoluted.
3. **Then rebuild the system properly** from the proven parts and measure
   how good it is connected together.

## Why this order

The engine's headline number can only tell us *that* something is wrong. A
stage in isolation tells us *what* — and a stage with its own dataset can be
improved in minutes instead of the ~75 minutes a full cycle costs. The
FastRule lane already proved the pattern: its own dataset turned vague
"complex is bad" into fourteen specific, individually-measured fixes.

## The stages, and what each needs

| stage | its question | dataset it needs | status |
|---|---|---|---|
| transcript | did we hear it right? | (word, corrected word) pairs from real vocab history | not started |
| **segment** | **how many separate things were asked for?** | text → expected item count + kinds + boundaries | **next** |
| **decompose** | **what are the atomic items?** | item → expected atomic items (the ATOMIZER's core) | **next** |
| validate | are the objects correct? | malformed object → corrected object, per named rule | partly (unit tests) |
| generate | one atom → the right action | **the FastRule 7,200** | done — step 1 |
| crosscheck | does the result match the words? | (raw text, produced objects) → expected findings | not started |
| label | right category / tags? | text → category + tags | done (fixture labels in the 7,200) |

Segment and decompose come first because they **are** the atomizer — the
half of the architecture FastRule depends on ("deep breaks things into
atomic items so FastRule can create each one").

## Rules that bind every stage dataset

- **Its own directory**: `dataset/stages/<stage>/` — never edit another
  stage's data to make yours work.
- **Train–test split by construction**, with test rows sealed under the same
  leakage rule as everything else: reported as aggregates, never mined,
  never fitted on, never used to pick a fix.
- **Ground truth by construction** wherever possible (the FastRule 7,200's
  lesson: generated data with known answers beats hand-labeling).
- **A scorer per stage**, reporting that stage's own named metrics — no
  stage is judged by the engine's headline.
- **Registered prediction before each change**, as always.

## Definition of done, per stage

A stage graduates when its isolated metric is good enough that it stops
being the binding constraint on the stage below it — judged on its own
test half, not on the engine board.

## Then: the rebuild

Only once the parts are proven do we reconnect and measure end-to-end. That
run is the honest answer to "how good is it when it all works together" —
and, unlike today, a bad number will point at the seam rather than at a
mystery.
