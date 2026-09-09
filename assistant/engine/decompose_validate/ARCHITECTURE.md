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

**validate** compares the completed items back against `X1`, repairs what it can
prove, and **flags** the rest.

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

    datasets/normalization.py   the gold's CLOSED LOOKUP TABLE — every filler, by hand
    datasets/generate.py        composes gold items from segmentation's own templates
    datasets/generated.jsonl    795 rows / 1,186 items / 268 families / 5 anchors
    eval_metrics/score.py       the boards + a 12-check self-test
    eval_metrics/run_board.py   run the resolver over the set and print them

**The gold and the code are deliberately different implementations.**
`normalization.py` is a closed table; `resolve.py` is a general parser. Copying
the table would make the two move together and the board would measure nothing.
Nothing in `assistant/engine/` is consulted for a gold VALUE.

Rows come from **segmentation's own template derivation**, so the two stages
agree BY CONSTRUCTION about where an item's boundaries are — a
decompose_validate score can never be quietly measuring a segmentation
disagreement.

The 5 anchors are chosen to make hard cases **reachable rather than hoped for**:
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

### Where it stands

Board, generated set (795 rows / 1,186 items, **gold-fed items** so segmentation
is not charged), 2026-09-08:

    all fields exact (row)     100.0%  (795/795)
    date 100% · start_time 100% · end_time 100% · recurrence 100%
    quantity 100% · reminder_minutes 100%
    inventions 0 · phrases lost 0 · contradictions 0 · harm/item 0.000
    0 model calls · 0.000 s/row

**This board is SATURATED and has stopped being an instrument.** 100% on a
generated set means the resolver covers every pattern the generator emits — that
is not evidence about real speech, and there is **no held-out number for this
stage**: the split does not exist yet and one carved now would not be held out,
because the resolver was tuned against all 268 families. The next measurement has
to come from a different source: real utterances, and real segmentation output
instead of gold-fed items.

## What the boards caught, and what that cost

Nine defects on the way from 88.3% to 100%. **Only five were in the code** — two
were the board itself, one the gold, one the dataset. That ratio is the lesson
worth keeping: read the failing ROWS, because a metric moving sharply against a
change is as likely to be wrong as the change is.

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
| `resolve.py` — the decompose half | **done**, 100% on the generated set |
| `datasets/` + `eval_metrics/` | **done**, 9 boards, self-test green |
| `checks.py` — the validate half | **next** |
| the observance **flag** | not built — replaces the old block |
| wiring into `stage.py` | not done; the legacy `decompose.py`/`validate.py` still run |
| deleting `run_objects` | the finish line |

`PLAN.md` holds the design record: what existed, the five reasons it was
convoluted, the X3 field spec and what validate can do that segmentation cannot.
