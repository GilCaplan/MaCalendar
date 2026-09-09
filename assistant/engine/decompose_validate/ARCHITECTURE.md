# decompose_validate

Stage 3 of the chain. **`X2 = (items, X1)` in, `X3 = (items, X1)` out**, where
the items arrive with `(action, time, tag)` and leave with every field an object
needs.

    segmentation          decides WHICH WORDS belong to which item
    decompose_validate    decides WHAT THOSE WORDS MEAN

That is the whole division of labour, and it is why the two stages are scored on
different things: segmentation on **words**, this stage on **values**. The names
come from ISO-TimeML / TempEval-3, which splits a time expression the same way —
its *extent* (segmentation's board) and its normalized *WREN* against an anchor
(this one).

Combined into one folder (Gil, 2026-09-08) because they are one concern. **The
functions stay separate** — this is a folder, not a merge.

## The two halves

> **decompose RESOLVES. validate CHECKS. Neither one SPLITS.**

Splitting is segmentation's job and asking twice is how items get double-cut.
"walk the dog at 9 and 2:30" is two items *before* this stage sees it; a
recurrence is **not** a split — "every tuesday" is ONE item with a cadence.

**decompose** (`resolve.py`) turns each item's spoken `time` into values. Pure
functions, one item at a time, no transcript scan, no list to index into:

| in | out |
|---|---|
| `resolve_date` | `date` — ISO, floored to today |
| `resolve_clock` | `start_time` — "HH:MM" |
| `resolve_range` | `start_time` + `end_time` |
| `resolve_recurrence` | `recurrence` + `recur_days` + `recurrence_rounded` |
| `resolve_until` | `recur_until` — the series' END |
| `resolve_lead_time` | `reminder_minutes` |
| `resolve_quantity` | `quantity` |

**validate** (`checks.py`) compares the completed items back against `X1`, repairs
what it can prove, and **flags** the rest. 7 fix rules, 5 flag rules.

The repair that is always available: read the item's own words again and let them
win — because an item may arrive with values from the LLM judge, FastRule's partial
parse or a rewritten retry, not just from `resolve.py`. Two guards keep that from
being destructive: where the words name **nothing** the existing value stands
(silence is not evidence), and only fields the words speak to are touched.

A rule **flags** when the disagreement is real but the wrong half is unknowable —
a series whose end precedes its start could have either end mistaken, so guessing
would either book a series nobody asked for or drop one they did.

**Flags, never blocks** (Gil, 2026-09-08). A blocked item is a command that
silently did nothing. A flagged one is committed with a note the speaker can see.

## Why every resolver takes ONE item's own time

The stage this replaces read the **whole transcript**, produced a flat list of
dates, and pinned them to events by index (`ev_idx`, `n_events`,
`orig_event_dates`). That is a bug class, not a bug: `relative_dates` returns two
dates for three events on *"add gym on tuesday … and add yoga on tuesday … and
add my conference on the 20th of November"* — because the bare-ordinal branch
correctly refuses to claim a month-named ordinal — and the conference lands in
September. It caused `a987aba`.

Segmentation already decided which words belong to which item. So a resolver
takes one item's time and nothing else, there is no list to index into, and
**"which event does this date belong to" is never asked.** That is the fix; the
rest of `resolve.py` is doing the arithmetic carefully.

## The conventions, and who decided them

Each of these is a choice rather than a fact, so it is written once and applied
everywhere instead of being guessed per sentence.

| convention | rule |
|---|---|
| **the date floor** | no day named ⇒ **today**. The clock is never invented. |
| **bare hour** | 1–6 is PM; 7–8 is PM only with evening words. "gym at 5" is not 5am. |
| **until / through** | "until" EXCLUDES the day it names; "through" and "including" keep it (CLAUDE.md). |
| **a series' first instance** | the **soonest** weekday the sentence names — not the first one said. An explicit "starting X" outranks the cadence but must still land on a day the cadence names. |
| **recurrence** | only `daily` / `weekly` / `monthly`; anything else is rounded and the rounding is **announced in the reply**, never done quietly. |
| **late afternoon** | 17:00–19:00 (Gil, 2026-09-08). "early evening" and "around lunchtime" have no ruling, so they resolve to **nothing** rather than to a number nobody chose. |
| **"next week"** | too vague to resolve — context-dependent, so it is left unresolved (Gil). |
| **a duration is not a count** | "extend the blood test by 30 minutes" has no quantity. |
| **`reminder_minutes` is about THIS item** | "an hour before **sales call**" measures from a different event; it is a relation, not a lead time. |

## Datasets and boards

    datasets/normalization.py      the gold's CLOSED LOOKUP TABLE — 248 fillers, by hand
    datasets/generate.py           composes gold items from segmentation's own templates
    datasets/banks/grown_*.json    THIS stage's own families and filler pools
    datasets/generated.jsonl       2,764 rows / 3,637 items / 317 families / 16 anchors
    eval_metrics/score.py          the boards + a 12-check self-test
    eval_metrics/run_board.py      --split train (default, full detail) | test (aggregates)

### The split — train 1,924 / test 840

Per `engine/TRAIN_TEST_SPLIT_CONVENTION.md`, and the reason it had to be built by
GROWTH rather than division is worth keeping:

> The original 268 families were tuned against until the board read 100%. A test
> set carved out of them measures memorisation, not generalisation. The only
> honest sealed half is made of material the code has never seen.

|  | rows | families | source |
|---|---:|---:|---|
| train | 1,924 | 296 | the 268 original (train **by construction**) + 28 grown |
| test | 840 | 21 | grown only — never mined, never printed |

Family-disjoint and **asserted, not assumed**: `build()` raises if a family
appears on both sides, and raises if an original family ever reaches test.
Stratified by nuance over a stable hash so no construction class lands entirely on
one side — all 11 grown buckets have families in both.

`run_board` defaults to `--split train`. `--split test` prints aggregates only,
and there is deliberately **no flag that unlocks test row detail** — the safe path
is the default path.

Two filler banks, for a load-bearing reason: the grown pools live here rather than
in `fastrule/datasets/banks/`, because editing that file would reshuffle
FastRule's own 7,200-row split, and widening a pool the original families draw
from would change which filler each existing row picks.

The 16 anchors are chosen for the arithmetic they break — a leap day, a year end
and start, a 31st, two month ends, and the five weekdays the original five never
covered (they are Tue/Sun/Wed/Sun/Thu, so no Monday, Friday or Saturday anchor
existed at all).

### Where the growth came from — mined, not invented

11,932 corpus texts (the sealed 300 excluded, and the exclusion asserted
non-empty before mining) scanned for time expressions and diffed against the gold
table. The dataset grew where real speech actually lives: `"march 5th"` occurs
**147x** and named months were barely tested; `"morning"` / `"evening"` /
`"afternoon"` occur **484 / 335 / 233x** and the gold declines all three.

Every new value is adjudicated from the **written conventions**, never from what
`resolve.py` returns. Two entries stopped being `AMBIGUOUS` by *derivation*:
`the end of the month` (CLAUDE.md already rules that "the end of September" names
the final day) and the four bare ranges (the bare-hour convention fixes the start,
`end_before_start` then forces the end — "from 6 to 8" cannot be 18:00–08:00).

**The gold and the code are deliberately different implementations.**
`normalization.py` is a closed table; `resolve.py` is a general parser. Copying
the table would make the two move together and the board would measure nothing.
Nothing in `assistant/engine/` is consulted for a gold VALUE.

Rows come from **segmentation's own template derivation**, so the two stages
agree BY CONSTRUCTION about where an item's boundaries are — a
decompose_validate score can never be quietly measuring a segmentation
disagreement.

The original 5 anchors were chosen to make hard cases **reachable rather than
hoped for**:
a mid-month Tuesday, a Sunday past the 15th (so "the 15th" must roll a month),
a month end, December (so it must roll the year), and a short February.

### The boards

Nine, because a single figure hides WHICH WAY a run fails and the ways cost
differently.

| | board | what it answers |
|---|---|---|
| **A** | VALUES | did the words become the right value — per field, and all-fields-exact |
| **B** | TRACEABILITY | a value no words support is an **INVENTION** · must be 0 |
| **B2** | ABSTENTION | of items whose gold named a value, did we commit one — catches the degenerate resolver that declines everything and so scores 0 inventions |
| **C** | HONOURED | every time phrase in the text reached some item's value · must be 0 lost |
| **D** | CONTRADICTIONS | impossible on their own terms — **needs no gold**, so it runs on real traffic |
| **D2** | HARM | wrong fields weighted by cost. `recurrence` is worst: the only failure that REPEATS ITSELF |
| **E** | COST | model calls and seconds per row |
| **F** | COMPOSITION | what the number was computed OVER — by anchor, by trap |
| **G** | FIXES | validate's repairs: improved / **BROKE** / still wrong. Never summed |

**A's denominator counts a field when EITHER side names it**, so an invented
value is a miss. B2's counts only gold. When the two disagree — `45/48` against
`45/45` — the gap *is* the information: three values were invented.

**G never sums improved and BROKE.** A repair that damages a correct item is not
paid for by one that helps elsewhere; that is the over/under-split precedent from
segmentation.

### validate's dataset — injected defects

`datasets/perturb.py`. Validate cannot be scored on "text → values"; that is
decompose's board. Its question is **"(a broken item, the transcript) → repaired,
or flagged"**, which the existing gold gives once a defect is injected. 11 defect
classes, from the settled check table rather than invented.

**A third of items are left alone.** Those controls are the only rows that can see
the failure that actually matters — a rule that rewrites what was already right —
and without them a rule that overwrites everything scores perfectly.

One class is deliberately excluded: shifting a date that came from the **floor**.
The words then name no day at all, so there is nothing to repair from, and scoring
it as a failure would push validate toward guessing. That is a test of
clairvoyance, not of validation.

### Where it stands — 2026-09-08

**Gold-fed items**, so a segmentation slip is never charged here.

The stage has two jobs, so it is measured two ways. **Clean** runs validate over
decompose's own output and asks *does it damage correct work?* **Perturbed**
injects defects and asks *does it repair?*

| | train (1,924 / 296 fam) | **sealed test (840 / 21 fam)** |
|---|---|---|
| all fields exact — clean | 100.0% (1924/1924) | **98.1% (824/840)** |
| all fields exact — perturbed | 100.0% (1924/1924) | **99.4% (835/840)** |
| perturbed, WITHOUT validate | — | 31.2% (262/840) |
| date · start_time (clean) | 100% · 100% | 98.6% · 99.9% |
| end_time · recurrence · quantity · reminder | 100% each | **100% each** |
| inventions · lost · contradictions | 0 · 0 · 0 | **0 · 0 · 0** |
| board G — improved / **BROKE** | 1691 / **0** | 682 / **0** |
| harm / matched item | 0.000 | 0.044 |
| cost | 0 model calls, 0.000 s/row | same |

**98.1% is the honest end-to-end figure** (words → values). Perturbed reads higher
for a structural reason: there validate restores gold values from the words, while
in clean mode it inherits decompose's 16 residual errors, which it cannot fix —
the resolver is what is wrong there.

Those 16 sit in a construction class **train has no failing instance of** (train is
100%), so the next step is growing train in the date-heavy classes, never looking
at test rows. Test has been read at milestones only, aggregates only.

### The bug no board could have found

`resolve()` ALWAYS returns a date, because of the floor. So `agree_with_words` was
treating **today** as evidence and overwriting any date whose words name no day —
destroying values an LLM or FastRule had supplied. **2,764 scored rows could never
catch it**: the gold applies the same floor, so both sides agreed and every item
scored correct. A unit test caught it in one line.

`resolve()` now reports `date_floored`, and the floor is applied by the rule whose
job that is. It also took board G's BROKE column on the sealed half from 4 to 0 —
those broken items were validate imposing the floored date on items that had
arrived correct.

The lesson generalises: **a board cannot see a defect its gold shares.** Unit tests
and boards fail differently, which is why both exist.

### The saturation this replaced

Before the growth the board read **100% (795/795)** and had stopped being an
instrument: it measured only patterns the generator already emitted. Adding new
constructions dropped it to **80.0%** immediately, which is the whole argument for
growing a dataset rather than polishing against a saturated one. The original
families now read 95.9% rather than 100% — improving the gold made those rows
harder, so part of that 100% was a measure of what the gold declined to ask.

## What the boards caught, and what that cost

**23 defects fixed on this stage so far, and only 14 were in the code** — 6 were
the boards, 2 the gold, 1 the dataset. That ratio is the lesson worth keeping:
read the failing ROWS, because a metric moving sharply against a change is as
likely to be wrong as the change is.

The board bugs all had one shape: **the check knew a single spelling of the
truth.** It had never heard of "twice a week", so 115 correct recurrences were
reported as invented; it demanded a bare `9` from `"09:30"`; it looked for "six"
in `"twenty to seven"` (a *to*-hour is one MORE than the hour it resolves to); it
wanted the digits of an end time derived from a duration to appear in words that
cannot contain them; and it treated a series' derived start date as an invention.

The two board bugs both had the same shape — the check knew **one spelling of
the truth**. A digits-only search for the hour called 26 correct answers
inventions because "ten thirty" contains no digit; the day-of-month check
demanded the START equal an ordinal that an `until` puts on the END.

The dataset fix is the one to be careful about, so it is written down: **3 rows
were dropped whose gold contradicts ITSELF** — a series ending before it begins
("every weekend until this afternoon"), or starting on a day its cadence never
names ("every monday tonight"). The template pairs cadence and bound
mechanically and nobody says these. A row that cannot teach a correct value must
not be answered by either side — the same treatment an ambiguous filler gets.
No family was lost: the generator retried other anchors, so all 268 remain.

## Status

| piece | state |
|---|---|
| `resolve.py` — the decompose half | **done**, 99.9% train / 97.1% sealed |
| `datasets/` + `eval_metrics/` | **done**, 9 boards, self-test green, split sealed |
| `checks.py` — the validate half | **done**, 12 rules, board G live, BROKE 0 both splits |
| `datasets/perturb.py` + board G | **done**, 11 defect classes, a third controls |
| the observance **flag** | **done** — reuses `db._skip_for_observance`, says nothing when observance cannot be computed |
| wiring into `stage.py` | **partial**: values land in `item.slots`, traced; the legacy pair still runs and is still what feeds FastRule |
| FastRule reading `slots` | **next** — the swap that makes these values what rows are built from |
| deleting `run_objects` | the finish line, blocked on the row above |

## Open questions for Gil — both real product gaps, neither guessed at

**1. Coarse parts of the day.** `"morning"`, `"afternoon"`, `"evening"`,
`"night"`, `"lunchtime"` are the MOST frequent time words in the corpus (484 /
233 / 335 / 52 / 122 occurrences) and the gold declines every one of them. Only
`late afternoon` has a ruling (17:00–19:00, Gil 2026-09-08). They are marked
`AMBIGUOUS` and their rows are dropped rather than resolved to a number nobody
chose — so a large slice of real speech is currently untested and, in the live
engine, unresolved.

**2. A yearly cadence cannot be represented.** `"every year"` / `"annually"` /
`"yearly"` (24x in the corpus) have no home in `daily|weekly|monthly`. Rounding to
monthly fires eleven extra times a year, so the resolver DECLINES instead — which
means an annual reminder currently gets no recurrence at all. The options are a
fourth cadence, or a flag telling the speaker it was not booked as a series.

`PLAN.md` holds the design record: what existed, the five reasons it was
convoluted, the X3 field spec and what validate can do that segmentation cannot.
