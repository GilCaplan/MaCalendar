# The FastRule dataset

A fresh eval/train set for `assistant/engine/fastrule/fastrule.py` (the deterministic
selective-classifier front door — see its module docstring and
`DOCUMENTATION/experiments/FASTRULE_RESEARCH.md`). Built 2026-09-07 because
the existing 3,000-row verification dataset (`dataset/DATASET.md`) had been
touched everywhere by threshold sweeps and full replays and could no longer
serve as an unmined FastRule measurement — every rank had, at some point,
had a human look at how FastRule did on it. Grown from 6,000 to 7,200 rows
later the same day (Gil) with a test-only pool that widens unseen-wording
coverage without touching a single train row — see "Growing test-only"
below and `engine/TRAIN_TEST_SPLIT_CONVENTION.md`.

**TEST ROWS ARE NEVER MINED — see `engine/TRAIN_TEST_SPLIT_CONVENTION.md` first.** That rule is the whole
point of the 80/20 split existing at all, and it applies identically to
every row in `split == "test"` regardless of which pool (original
stratified, or the newer forced-test-only growth) it came from. This file
is schema and composition, not the leakage discipline.

## What's here

    banks/fillers.json              generic slot-filler word lists (names, dates, times, ...)
    banks/categories_fixture.json   canonical event-category + task-tag scheme (label ground truth)
    banks/simple_patterns.json      202 single-intent pattern families (157 original + 45 test-only)
    banks/complex_patterns.json     316 nuance-targeting pattern families (260 original + 56 test-only)
    fastrule_7200.jsonl             the generated dataset — 7,200 rows, one JSON object per line
    ../../TRAIN_TEST_SPLIT_CONVENTION.md   how the split is built (80/20 + force_split), and the
                                    no-mining rule — ENGINE-WIDE, every stage's dataset obeys it
    DATASET.md                      this file

`scripts/gen_fastrule_dataset.py` is the only code involved: it reads the
banks, expands them into rows, assigns ground truth **by construction** (it
put the fillers in, so it knows what the correct parse is), and writes
`fastrule_7200.jsonl`. There is no hand-labelling step and no LLM in this
pipeline — it's pure deterministic string templating, which is also why
regeneration is byte-identical (verified: `md5` of two consecutive runs
matches, and — the load-bearing check for the 2026-09-07 growth — a
from-scratch run of only the original 417 families reproduces the current
file's 4,800 train rows exactly, full-JSON and text-only hashes both
matching; see `engine/TRAIN_TEST_SPLIT_CONVENTION.md`).

## Why patterns + fillers, not 6,000 hand-written rows

Hand-writing 6,000 realistic commands is either extremely slow or extremely
repetitive (or both). The alternative used here: author the **wording
variety** once per pattern skeleton (a "family"), author **generic filler
banks** once, and let combinatorics produce volume. A family like

    "book {event_title} {date} at {time} and remind me to {task_title2}"

expands to a dozen-plus distinct sentences ("book dentist appointment
tomorrow at 7am and remind me to buy groceries", "book team meeting next
friday at noon and remind me to walk the dog", ...) — all sharing one
wording skeleton (so FastRule's handling of *that construction* is what's
being measured) while varying enough that no two rows are near-duplicates of
each other beyond the skeleton itself.

The generator does NOT need to guess what each row means: it filled
`{event_title}` from the `event_titles` bank and knows that value became
`slots.title`; it filled `{date}` and knows that became `slots.date_phrase`;
the family declares `action`/`atomic`/`events`/`tasks` once (simple tier: a
lookup table keyed by `action`, since single-intent rows are fully
determined by their action; complex tier: stated explicitly per family,
since compounds vary too much to default). So ground truth falls out of
generation instead of being labelled after the fact.

## The row schema

One JSON object per line:

```json
{
  "id": "c_and_et_1-004",
  "text": "book dentist appointment tomorrow at 7am and remind me to buy groceries",
  "split": "train",
  "tier": "complex",
  "family": "c_and_et_1",
  "expect": {
    "events": 1,
    "tasks": 1,
    "action": "mixed",
    "atomic": false,
    "slots": {
      "title": "dentist appointment",
      "date_phrase": "tomorrow",
      "time_phrase": "7am",
      "category": "Health",
      "title_2": "buy groceries",
      "tags": ["Groceries"]
    }
  }
}
```

- **`id`** — `<family>-<counter>`, counter zero-padded to 3 digits, stable
  and unique; regenerating produces the same id for the same row.
- **`split`** — `"train"` or `"test"`. See `engine/TRAIN_TEST_SPLIT_CONVENTION.md`.
- **`tier`** — `"simple"` (single-intent, wording-variety focused) or
  `"complex"` (nuance-targeting: compounds, decoys, edge cases).
- **`family`** — the pattern skeleton's slug. This is what the stratified
  80/20 split is stratified over (`force_split` families are assigned
  directly instead — see `engine/TRAIN_TEST_SPLIT_CONVENTION.md`), and what "no family > 3% of the
  total" is measured against (largest family in the current build:
  `c_and_te_6` at 17 rows / 0.24%).
- **`expect.events` / `expect.tasks`** — how many NEW events/tasks the
  command should produce. Following the main dataset's convention
  (`dataset/DATASET.md`'s count-correctness metric): creates count, every
  other action (query/delete/update/complete) expects `0` — nothing new is
  *created* by a mutation or a read, even though it clearly acts on
  something that exists. `update_event`/`update_todo` are **not** treated
  as "1" here on purpose — they change a field, they don't add an item.
- **`expect.action`** — one of `create_event`, `create_todo`, `query`,
  `delete_event`, `delete_todo`, `complete_todo`, `update_event`,
  `update_todo`, `mixed`. `query` unifies the engine's `query_schedule` /
  `query_todos` (the row's family slug still distinguishes which — e.g.
  `s_q_show_my_tasks` vs `s_q_show_schedule` — if that finer grain is ever
  needed). **`mixed`** means the row's sub-asks span more than one action
  *type* (e.g. a create + a delete, or an event-ask + a task-ask, which are
  different actions — `create_event` vs `create_todo` — even though both are
  "creates"). A homogeneous compound (`event + event`, both `create_event`;
  `task + task`, both `create_todo`) keeps that single action name, not
  `mixed` — only cross-action compounds get folded into `mixed`.
- **`expect.atomic`** — `true` for a single ask, `false` for a compound
  (however many sub-asks). This is the property FastRule's abstention gates
  are trying to detect (strong-compound / clause-coordination /
  mixed-mode-compound in `fastrule.py`) — but this field is **ground truth
  about the utterance**, not a simulation of FastRule's current gate
  behavior. A rhetorical "should I add X to my calendar?" is `atomic: true,
  action: create_event` here even though today's `_INTERROGATIVE_RE` gate
  makes FastRule abstain on it — the dataset says what's *correct*, which is
  the target the gates are supposed to approximate, not a mirror of what
  they currently do.
- **`expect.slots`** — ground truth for the fields FastRule/the engine
  should extract, **whichever apply to that row**. The brief's baseline set
  is `title`, `date_phrase`, `time_phrase`, `quantity`, `recurrence`,
  `attendee`. Two documented extensions beyond that baseline, both required
  to ground-truth nuances the brief explicitly calls out:
  - **Numbered suffixes** (`title_2`, `date_phrase_2`, `time_phrase_2`,
    `attendee_2`, `title_3`, ...) for a compound row's 2nd/3rd sub-ask. The
    first ask's slots are unsuffixed; every later ask's corresponding slot
    is suffixed. (A single-ask row with an NP-coordination decoy —
    `"buy {item} and {item2}"` — can also carry `title` *and* `title_2`
    even though `atomic: true`: both items belong to the *same* one task: two
    fillers, one ask. `title` there is deliberately the full coordinated
    phrase, e.g. `"apples and eggs"`, with `title_2` = the second item alone
    — extra detail, not a contradiction.)
  - **New keys** beyond the base six, added only when a bank entry needs
    them: `lead_time` (reminder lead-times: "remind me 30 minutes before"),
    `duration` (extend/shorten deltas), `quoted` (bool — the target was
    named with an explicit quoted string, e.g. `remove 'dentist' from my
    calendar`), `generic_target` (bool — the target is an unresolvable
    pronoun-like reference, e.g. "delete this event"; the row still records
    `title` as the literal referring phrase), `all_day` (bool), `recurrence`
    (the phrase as said) vs `recurrence_rounded` (what the engine's output
    should be, always `daily`/`weekly`/`monthly` per the project's rounding
    convention — see below), and `end_inclusive` (bool, for `until` vs
    `through`/`including` recurrence endings).
  - Absent keys mean "not applicable to this row," not "unknown" — a
    `delete_event` row has no `quantity`, and a bare `create_todo` with no
    stated time has no `time_phrase`. Don't score a missing key as a miss.

### Label-level ground truth: `category` and `tags` (Gil, 2026-09-07)

Every expected EVENT also carries a `category` (single label); every
expected TASK carries `tags` (a list — empty, one, or multiple). Same
numbered-suffix convention as everything else: the first expected event's
label is `category`, the second (if any) is `category_2`, a third
`category_3`; the first expected task's labels are `tags`, second `tags_2`,
third `tags_3`. Absent when `events`/`tasks` is 0 for that row, same as any
other not-applicable slot.

**These are computed by calling the real classifier, not a reimplementation
of it.** `scripts/gen_fastrule_dataset.py`'s `setup_label_env()` points
`MACALENDAR_CATEGORIES` at `banks/categories_fixture.json` and imports
`assistant.actions.calendar.categories.classify()` directly — the exact
function the live engine calls — so `category` in this dataset is *by
definition* what the product would output against this fixture, not a
best-effort guess at what it should output. `tags` uses
`assistant.actions.todo.tagging._score()` (the real per-tag scoring
function) against `banks/categories_fixture.json`'s `task_tags` section,
scored per tag and keeping every tag whose score is `> 0` — genuinely
multi-label, unlike the shipped `tagging.infer_tag()` which only ever
returns its single argmax (Gil's schema explicitly asked for "a list, may
be empty or multi"; the underlying math is identical, this dataset's
ground truth is just less lossy about it). An empty `tags: []` is a valid,
expected answer — `tagging.py`'s own docstring: "no tag at all when nothing
matches ... an untagged task is the honest answer."

**`banks/categories_fixture.json` is part of the dataset, not a side
file — point `MACALENDAR_CATEGORIES` at it for any scoring run that needs
these labels to mean what this file says they mean.** It's a trimmed,
faithful copy of the real shipped defaults:
`assistant/actions/calendar/categories.py`'s `DEFAULTS` for the
`categories`/`removed` keys (loadable via `MACALENDAR_CATEGORIES` exactly
as the real `CATEGORIES_PATH` mechanism expects — verified by loading it
through the real `categories.classify()` while building this dataset), and
`assistant/actions/todo/tagging.py`'s `KEYWORDS` for the `task_tags`
section. **Only `categories`/`removed` are consumed by the product's own
env-var override — `tagging.py` has no file-based override at all (its
`KEYWORDS` is a hardcoded module dict)**, so `task_tags` is a dataset-only
companion block, read only by this generator (and by any scoring code that
wants the same keyword scheme); a scoring run reproducing tag ground truth
needs to import `tagging._score` and read `task_tags` from this file itself,
the same way the generator does.

11 categories (`Work, Study, Meeting, Social, Family, Fitness, Health,
Errand, Meal, Travel, Personal`) — the real `DEFAULTS` trimmed by 2
(`Shabbat Meal`, `Prayer`, both Israeli/Jewish-observance-specific and never
triggered by this dataset's generic content; both listed in the fixture's
`"removed"` so `categories.py`'s default-merge doesn't silently keep them
active — the real `_load()` merges a `MACALENDAR_CATEGORIES` file *into*
`DEFAULTS` rather than replacing it, so removal has to be explicit). 4 task
tags (`Groceries, Coursework, Errands, Work`) — the real built-in set,
unchanged. **Deliberate consequence of using the live functions:
regenerating is byte-identical only as long as `categories.py`/`tagging.py`
and the bank files are unchanged** — if their scoring algorithm changes,
regenerating reflects the new algorithm, which is the *correct* behavior
here (ground truth should track the real classifier on a fixed fixture, not
fossilize a hand-copied formula that would silently drift out of sync). This
generation's `md5` is recorded the same way as any other — see "How to
regenerate" below.

**Which title is a label source, and which is excluded.** A category/tags
value is only computed for a title that belongs to a genuinely CREATED
event/task — never for a delete/update/query/complete TARGET, even though
those rows also carry a `title` naming what they act on. Each family
declares this explicitly for every `action: "mixed"` row (required — a
`"mixed"` row's title-ish keys can belong to either type, or to an excluded
non-create target, and nothing about the action name alone says which) via
`event_label_sources`/`task_label_sources` in `complex_patterns.json` (e.g.
`c_mixedmode_3`, `"cancel {event_title2} and book {event_title} ..."`, has
`event_label_sources: ["title"]` — only the booked event gets a category,
the cancelled one doesn't). For a homogeneous `create_event`/`create_todo`
family it's auto-derived (every title-ish key present is that one type) —
except the 4 NP-decoy item-pair families
(`c_npdecoy_buy_two_items`/`pickup_two_items`/`buy_two_party`/
`remind_buy_two`) which override to `task_label_sources: ["title"]` only,
since their `title_2` is a redundant duplicate already folded into the
combined `title` (`"apples and eggs"`), not a second countable task. The
generator asserts `len(event_label_sources) == events` and
`len(task_label_sources) == tasks` for every family at load time — an
authoring mistake here fails the build, not silently mislabels 15 rows (this
caught one real bug while building this addition: `c_joiner_commathen_te_1`,
"buy {qty} {item}, then remind me to {task_title2}", was originally
declared `events: 1, tasks: 1` — wrong, both sides are tasks; fixed to
`create_todo`, `events: 0, tasks: 2`).

### Label metrics (how a scoring run should judge `category`/`tags`)

Per Gil's instruction, computed **only on MATCHED items** — the same rule
`field quality` already uses in the main dataset (`dataset/DATASET.md`):
an uncovered/uncreated item is excluded and counted, never guessed at.

- **`category`** (single-label): **accuracy** over matched events (did the
  produced event's category equal `expect...category`?), plus **macro
  precision/recall/F1** across the 11 classes — macro so a rare class
  (`Study`, `Travel`) counts as much as a common one (`Personal`, `Health`),
  rather than being drowned out by class frequency.
- **`tags`** (multi-label): **micro precision/recall/F1** over tag *sets* —
  pool every (matched task, tag) pair across the whole scored slice, not
  per-task-then-averaged, so a task expecting 2 tags and getting 1 right
  contributes partial credit at the pair level rather than an all-or-nothing
  per-task score. `precision = |predicted ∩ expected| / |predicted|`,
  `recall = |predicted ∩ expected| / |expected|`, pooled over all matched
  tasks' tag sets.

### Recurrence rounding

Per `CLAUDE.md`: recurrence is only ever `daily`/`weekly`/`monthly` in the
product; anything else a speaker says gets rounded. `recurrence` in a row's
slots is exactly what the template said (`"every other tuesday"`, `"every
weekday"`); `recurrence_rounded` is the value the engine's *output* should
carry (`RECURRENCE_ROUND` in the generator — every weekday-ish phrase rounds
to `weekly`, `every day`/`daily` to `daily`, `monthly`/`every month` to
`monthly`). 16 `recurrence`-nuance families and 10 `until_through` families
exercise this; `c_until_endofmonth` specifically encodes the CLAUDE.md
exception that "until the end of the month/September" is **inclusive**
(`end_inclusive: true`) even though "until" is exclusive everywhere else in
this bank (`c_until_1`, `c_until_2`, `c_until_3`, `c_until_4`:
`end_inclusive: false`) — that's the one phrase that names the final day
rather than a boundary past it, per the project's own rule.

## Composition (this generation — regenerate to reproduce exactly)

    python -m scripts.gen_fastrule_dataset

prints this table and writes `fastrule_7200.jsonl`; `--no-write` runs the
same generation + verification without touching the file (useful for
checking a bank edit before committing to a regenerate).

**Totals.** 7,200 rows, 7,200 unique texts, 518 pattern families (202
simple + 316 complex). Train 4,800 (66.7%) / test 2,400 (33.3%). Largest
family is 0.24% of the total, well under the 3% cap. Full mechanism and the
train-invariance proof: `engine/TRAIN_TEST_SPLIT_CONVENTION.md`.

**Before → after the 2026-09-07 test-only growth:**

| | before | after | change |
|---|---:|---:|---:|
| total rows | 6,000 | 7,200 | +1,200 |
| train rows | 4,800 | 4,800 | **+0 (byte-identical)** |
| test rows | 1,200 | 2,400 | +1,200 |
| total families | 417 | 518 | +101 (45 simple + 56 complex) |
| train families | 331 | 331 | +0 |
| test families | 86 | 187 | +101 |

**By tier x split:**

| tier | train | test | total |
|---|---:|---:|---:|
| simple | 1,600 | 800 | 2,400 |
| complex | 3,200 | 1,600 | 4,800 |

**By action x tier (row counts):**

| action | simple | complex | total |
|---|---:|---:|---:|
| create_event | 627 | 2,122 | 2,749 |
| create_todo | 567 | 1,074 | 1,641 |
| query | 240 | 50 | 290 |
| delete_event | 229 | 112 | 341 |
| delete_todo | 187 | 51 | 238 |
| complete_todo | 209 | 71 | 280 |
| update_event | 187 | 108 | 295 |
| update_todo | 154 | 79 | 233 |
| mixed | 0 | 1,133 | 1,133 |

(Simple tier has no `mixed` by construction — single-intent only.)

**By atomic flag x tier:**

| tier | atomic | compound |
|---|---:|---:|
| simple | 2,400 | 0 |
| complex | 2,820 | 1,980 |

**Complex-tier nuance coverage** (each is the brief's "measured failures"
list, one bank category per line — family count is distinct skeletons,
rows is generated volume; `*` marks a nuance the 2026-09-07 growth added
rows to, `propose_confirm` is new that round):

| nuance | families | rows | what it targets |
|---|---:|---:|---|
| and_compound* | 27 | 407 | plain "and" joining two asks, all 4 type-orders (ee/tt/et/te) |
| np_decoy* | 22 | 328 | NP-coordination that must NOT split ("meeting with X and Y", "buy A and B", serial verbs) |
| joiner* | 26 | 398 | explicit cue-word compounds: "and then", ", then", "also", "plus", "as well as", "along with" |
| remind_then* | 13 | 199 | "remind me to X, then Y" — task leading into a differently-typed second ask |
| mixed_mode* | 22 | 339 | create + query/delete in one utterance |
| interrogative_polite* | 18 | 281 | "should I add...?" vs "can you add...?" — both are creates, not questions |
| propose_confirm (new) | 20 | 291 | propose-then-seek-confirmation shapes: "I was thinking about booking X — does that work?", "how about I add Y?", including compound and mixed-action variants |
| generic_target_complex* | 12 | 155 | "delete this event" / "clear my list" embedded in longer sentences |
| time_list_vs_range* | 18 | 280 | "walk the dog at 9 and 2:30" (2 items) vs "from 9 to 2:30" (1 item, range) |
| recurrence* | 18 | 282 | recurrence incl. roundable phrasings ("every other tuesday", "every weekday") |
| until_through* | 11 | 172 | "until" (exclusive) vs "through"/"including" (inclusive), + the end-of-month exception |
| attendee* | 14 | 221 | named attendees on an event/task |
| lead_time* | 14 | 217 | reminder lead-times as an event *attribute*, not a second item |
| date_marking* | 11 | 174 | "mark {date} as {occasion}" — a day-marker, never `complete_todo` |
| dated_encounter* | 11 | 171 | "I need to talk to X on {date}" — an encounter, i.e. `create_event` |
| all_day* | 9 | 137 | all-day phrasings |
| three_ask* | 17 | 267 | 3-ask compounds across type combinations |
| texture* | 16 | 245 | misspellings, STT filler words, quoted targets, rambling — in compound/complex context |
| extra* | 17 | 236 | topping up thin action buckets (update_event/update_todo/query/delete_*/complete_todo) with complex-register phrasing |

**Label coverage** (`python -m scripts.gen_fastrule_dataset --no-write` prints this):

| event category | count | share of expected events |
|---|---:|---:|
| Personal | 1,253 | 29.9% |
| Health | 822 | 19.6% |
| Meeting | 764 | 18.3% |
| Social | 471 | 11.3% |
| Work | 272 | 6.5% |
| Fitness | 250 | 6.0% |
| Errand | 154 | 3.7% |
| Travel | 120 | 2.9% |
| Study | 80 | 1.9% |

`Family` and `Meal` never fire — this dataset's generic filler banks
(deliberately: no personal/family-specific words) never contain their
trigger keywords. Not a bug: a category that's genuinely unused by the
dataset's vocabulary should show 0, not be forced to appear.

Task tags: 2,047 of ~3,150 expected tasks (65.0%) are legitimately untagged
(`tags: []`) — most of `task_titles`' generic chores ("call the plumber",
"pay the electricity bill", "walk the dog") don't hit any of the 4 built-in
tag keyword lists, which is the real classifier's own honest behavior, not
a generation defect. Of the tagged remainder: Errands 545, Groceries 427,
Work 131. **Multi-tag rows: 0** in this generation — the mechanism supports
it (verified directly: `"buy milk and homework"` scores `["Coursework",
"Groceries"]` through the real `_score()`), but every `item`/`item2` pair in
this bank's NP-decoy families draws from the same single `items` bank
(Groceries-flavored), so no generated row happens to straddle two tag
domains. A future bank edit that pairs a task_title with a cross-domain
item would start producing multi-tag rows for free — no generator change
needed.

## Growing test-only: `force_split`

See `engine/TRAIN_TEST_SPLIT_CONVENTION.md` for the full mechanism, the exact numbers, and the
train-invariance proof. Short version: a family may declare
`"force_split": "test"` and is then assigned directly to test, entirely
bypassing the stratified 80/20's hash-based bucket assignment — so adding
one can never reshuffle any *other* family's train/test side, and can never
produce a train row (`build_forced_test()` in `scripts/gen_fastrule_dataset.py`
asserts both). **These rows are eval-only, exactly like the rest of
`split == "test"`** — the leakage rule at the top of `engine/TRAIN_TEST_SPLIT_CONVENTION.md` (test
results are never mined) makes no distinction between the two test pools.
Growing this pool is therefore always safe to do between measurement runs:
it changes what generalization is measured against, never what the model is
allowed to see.

## Slot-filler banks (`banks/fillers.json`)

Generic only — no personal names, places, or anything else from the
project's real `~/.assistant_tools/vocab.json`. The `names` bank (Alex,
Jordan, Sam, Taylor, Morgan, Casey, Riley, Jamie, Drew, Reese, Avery, Quinn,
Skyler, Rowan, Dana, Charlie, Jesse, Cameron, Harper, Emerson, Finley,
Blake, Sage, Robin, Parker, Devon) was cross-checked against the live
`vocab.json` (word-boundary match, read-only) before finalizing this
dataset — zero overlap. `event_titles`/`task_titles`/`items` are ordinary
generic nouns (dentist appointment, team meeting, buy groceries, walk the
dog, apples, ...). Dates and times are stored and emitted as **phrases**
("tomorrow", "next monday", "half past six", "from 6 to 8") — resolving a
phrase to an absolute date/time is the parser's job, never this dataset's;
scoring should compare the phrase (or its presence/absence), not attempt
date arithmetic against it.

## How to regenerate

    python -m scripts.gen_fastrule_dataset            # writes fastrule_7200.jsonl
    python -m scripts.gen_fastrule_dataset --no-write  # prints the composition table, doesn't write

Fully deterministic: `SEED = "fastrule-6000-v1"` in
`scripts/gen_fastrule_dataset.py` (a fixed historical identifier now, not a
live row-count description — see the module docstring; changing the STRING
would reseed every family's RNG independently and break every row, forced
or not), the current bank files (including `categories_fixture.json`), and
— for `category`/`tags` only — the current behavior of
`assistant/actions/calendar/categories.py` /
`assistant/actions/todo/tagging.py` are the only inputs (no network, no
wall-clock). Two consecutive runs produce byte-identical
`fastrule_7200.jsonl` (verified via `md5` during construction of this
dataset, and again — full-JSON and text-only hashes both — for the 4,800
train rows specifically across the 2026-09-07 growth; see `engine/TRAIN_TEST_SPLIT_CONVENTION.md`). The
script also **self-verifies on every run** before writing: exact row
count, all-unique texts, the stratified pool's own split fraction in [19%,
21%], train count exactly the original 4,800, no `force_split` family
producing a train row, no family over 3% of the total, zero families
leaked across train/test, all ids unique, every family's declared
`events`/`tasks` count matches its `event_label_sources`/`task_label_sources`
— any violation raises instead of silently writing a bad file. The script
never touches `~/.assistant_tools/`: `setup_label_env()` points
`MACALENDAR_CATEGORIES`, `MACALENDAR_VOCAB`, `MACALENDAR_DB`,
`MACALENDAR_MEMORY_DB` and `MACALENDAR_TRACE_BUS` at a throwaway
`tempfile.mkdtemp()` directory before importing anything from `assistant`
(the one exception being `MACALENDAR_CATEGORIES`, deliberately pointed at
this dataset's own fixture rather than a scratch dir, since that's the
whole mechanism being used).

To extend the dataset: add a family to `banks/simple_patterns.json` or
`banks/complex_patterns.json` (simple needs only `family`/`action`/
`template`; complex additionally needs `atomic`/`events`/`tasks` stated
explicitly — see the module docstring and `validate_family()` in
`scripts/gen_fastrule_dataset.py` for the placeholder-suffix convention that
avoids two asks silently clobbering the same slot key), then regenerate.
**Two ways to add a family, with different blast radii** (`engine/TRAIN_TEST_SPLIT_CONVENTION.md` has
the full mechanism): a plain family joins the stratified 80/20 pool and
*can reshuffle which existing families land in train vs test* (the
stratified split is a function of full `(tier, action)` bucket membership),
so that kind of bank edit is "regenerate and re-diff," not "append a
delta." A family with `"force_split": "test"` carries none of that risk —
it's assigned directly, can only ever add test rows, and cannot perturb any
other family's split or any train row (asserted by the generator, not just
documented) — that's the mechanism to reach for when the goal is adding
eval coverage without an audit of what else moved.

## What was deliberately left out

- **No absolute dates/times.** Everything is a phrase; the dataset takes no
  position on today's date or timezone, matching the "dates/times as
  PHRASES, resolution is the parser's job" instruction. A scorer that needs
  an absolute answer must resolve the phrase itself (or better: score
  phrase-level field quality, per the main dataset's field-quality metric).
- **No location/description fields.** The brief's slot list didn't ask for
  them, and adding them would have meant an additional filler bank + a
  judgment call about which nuance rows carry a location versus which don't
  for no measured benefit; not modeled.
- **No adversarial/garbled STT rows** (word salad, cut-off audio, competing
  speakers). The `texture` category covers filler words, misspellings, and
  rambling qualifiers, but genuinely broken transcripts are a different
  (and much harder to ground-truth-by-construction) problem — closer to
  what the main 3,000-row HWU-derived dataset already covers via real
  utterances. This set stays in the "clean-ish real speech" register the
  brief's examples (book/schedule/add/remind/buy) live in.
- **No multi-turn / context-dependent rows** ("that one", "the one from
  before" resolved against prior conversation state). `generic_target`
  covers the *reference* shape but not resolution against history — FastRule
  itself is stateless per command, so this wasn't in scope.
- **Query sub-type (`query_schedule` vs `query_todos`) isn't a top-level
  `action` value** — the brief's action enum has one `query`. The
  distinction still exists in the data (readable off the family slug, e.g.
  `s_q_show_my_tasks` vs `s_q_show_schedule`) for anyone who wants the finer
  grain later, but isn't promoted to `expect.action` since that would have
  meant deviating from the specified enum.
- **No custom/user-added categories or tags.** The fixture is the built-in
  scheme only (11 categories, 4 tags) — no simulation of a user who renamed
  "Errand" to something else or added a personal tag. Ground truth would
  become undefined without a specific user's real overrides to anchor it,
  and those live in personal `~/.assistant_tools/` files this dataset must
  never touch or depend on.
- **No location/attendee/description signal fed into `classify()`.** The
  real `classify()` accepts `attendees`/`location`/`description` too (and
  weighs a title hit higher than a hit in those); this dataset only ever
  passes the title, since attendee names are generic placeholders with no
  real category affinity (a name alone would only ever hit the `Social`
  "people from vocab" fallback, which is deliberately never triggered here
  — this script's vocab is always empty, see `setup_label_env()`) and no
  family models a location/description field at all (see the earlier
  "no location/description fields" note). If a future bank adds those,
  wiring them into `classify()`'s call is a small, localized change.


## Q9 labels — reconciliation note (2026-09-07)

The dataset agent, lacking this chat's context, read the Q9 relabels as an
injection and reverted them while building the test expansion. They are
RE-APPLIED here on the expanded banks (the ruling stands: a first-person
create QUESTION proposes — `action: "propose"`, `proposal_kind` kept):
the 16 original interrogative families, the agent's own 20 propose_confirm
families (its independently-authored question shapes — same category,
now labeled per the ruling), and the 5 confirm-subprompt families
(imperative half executes, question half silent). 565 propose rows total.
Scoring semantics unchanged: an abstain on a propose row is correct
routing; any fast commit is a violation. Train TEXTS are the agent's
byte-identical 4,800; only the ruled labels differ.
