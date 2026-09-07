# The persona test sets

**What they are for.** Every measurement this project has ever run scores the
engine on the author's own speech — the 3,000-utterance verification pool is
his history, and the FastRule 7,200's banks are generic but its pattern
families were written by someone who had been reading his transcripts for a
week. The standing claim that the engine works for *other people* rests on one
argument: the three trained classifiers
(`assistant/intent/classifier.py`) decide **structure** — how many asks, which
verb class, event or task — while a user's personal words land in **slots**
(titles, places, names), so personal vocabulary cannot move them. That
argument was spot-checked on ten hand-written phrases and never measured.

These sets measure it. Six synthetic users, each with its own vocabulary *and*
its own phrasing habits, scored by `scripts/persona_board.py`, which reports
one board per persona plus the **spread** between the best- and worst-served.
The spread is the deliverable: near-zero means the claim holds; large means we
have tuned to one dialect without knowing it.

## THE TWO RULES THAT BIND THIS DATA

**1. TEST-ONLY. FOREVER.** Every row carries `split: "test"`. No persona row
is ever used to fit a model, select a feature, sweep a threshold, or seed a
few-shot prompt — not the ones scored, not the ones that fail, not the banks
they came from. They exist to answer *"does this work for people other than
its author?"*, and a set you have optimised against cannot answer that
question about anything. Hypotheses for engine work keep coming from the real
pool's training half, exactly as `DOCUMENTATION/experiments/ITERATION_PROTOCOL.md`
says. A persona number may be **reported**; it may not **direct** a change,
beyond naming an already-independently-confirmed bug.

The one thing a persona result legitimately does is raise a *question* for
`DEVQA.md` — "should the operation featurizer read verb-initial imperatives
only?" is a design question, and design questions are Gil's. Answering it by
fitting on persona rows would burn the instrument.

**2. NO REAL PERSONAL DATA.** Every name, place, institution and activity is
invented. `scripts/gen_personas.py` runs a **leak gate** on every build: it
reads the author's real `~/.assistant_tools/vocab.json` read-only and fails
the build if any word of it (≥ 5 characters, word-boundary match) appears in
any generated row — the same standard as
`tests/unit/test_artifact_claims.py`'s published-page leak test. A word is a
leak *unless* it has been declared, with a reason, in
`dataset/personas/allowed_words.txt`. Today that file holds exactly one entry
(`tomorrow`), which is the honest state: everything else in these 2,520 rows
was invented for them.

The control persona is deliberately in the author's *register* (religious,
Israeli, student) — that is what makes it the control — but not his
*vocabulary*: it says `chavruta`, `night seder`, `melava malka`, `beit
midrash`, `ulpan`, `moadon`, none of which is in his word list, and it never
says the terms that are.

## The six personas

| id | who | speech habits | action bias | mean words/utterance |
|---|---|---|---|---|
| `observant_student` | **CONTROL** — religious Israeli student | imperative, complete sentences, transliterated Hebrew nouns in English frames | balanced, slightly event-heavy | 10.4 |
| `household_parent` | parent running a household | rushed and run-on, subject-dropping, afterthoughts and self-correction | task-heavy | 9.3 |
| `freelance_consultant` | freelance consultant | polished, hedged politeness, business idiom (`block off`, `pencil in`), subordinate clauses | meeting-heavy, big update/cancel tail | 11.8 |
| `retiree` | retiree | long fully-grammatical sentences, elaborate politeness, explanatory aside before the ask, spelled-out clock times | balanced; heavy medical calendar | 14.5 |
| `uni_student` | university student | verbless fragments (`the exam 12:30`), no politeness, no punctuation, slang verbs | create- and delete-heavy | 6.6 |
| `esl_speaker` | non-native English speaker | article drops, calqued prepositions (`in monday`), infinitive modals (`i must to`), 24-hour clock | balanced, admin-heavy | 10.7 |

Each persona owns its filler banks (`names`, `event_titles`, `task_titles`,
`items`, `occasions`, `quotable`) and may override the register-neutral ones
(`dates`, `times`, `recurrences`, `filler_words`) where how it says a time or
a day is itself a habit — the ESL persona's 24-hour clock and the retiree's
`quarter to four` are speech habits, not subject matter.

## The design that makes the comparison mean anything

`structures.json` is a **shared structure catalog**: 33 asks defined by their
*grammar* — how many asks, which action, which slots — not by their words.
Every persona realises **every** structure in its own voice, and the generator
fails the build if a persona's template produces a different slot set from the
one its structure declares. So the structural composition is identical across
personas by construction, and the board's **structure-matched macro** (equal
weight per structure, restricted to structures every persona has a defined
value for) isolates vocabulary and phrasing from "one persona got more
compounds".

Personas *also* carry a `mix` — relative weights per structure — because a
parent genuinely does create more tasks than a consultant does. The board
reports both readings and labels them: **natural mix** (product-realistic) and
**structure-matched** (the clean comparison).

Structures cover: the create/query/delete/update/complete simple tier; the
NP-coordination decoys (`X with A and B`, `buy A and B`) that must not split;
time ranges; reminder lead-times; quoted and generic delete targets; a
disfluent ramble; the Q9 propose question; and eight compound shapes
(`and` in all four type-orders, an announced joiner, `also`, cancel-and-book,
and a three-ask).

## The ablation: is it the WORDS or the WAY OF SPEAKING?

A persona changes both at once, so the persona board alone cannot say which
causes the spread. `--ablation` splits them. A persona's banks divide into
**content** (`names`, `event_titles`, `task_titles`, `items`, `occasions`,
`quotable` — the material that lands in a slot, i.e. "vocabulary" in the sense
the multi-user claim uses the word) and **style** (the templates plus the
temporal expressions and disfluencies — habits, not subject matter). Two
blocks of six cells each hold one half fixed against the control:

    vocab:<p>    control's phrasing + <p>'s content   →  spread = vocabulary alone
    phrase:<p>   <p>'s phrasing + control's content   →  spread = phrasing alone

    python -m scripts.gen_personas --ablation
    python -m scripts.persona_board --data dataset/personas/personas_ablation.jsonl

## Ground truth is by construction

The generator chose the filler that became `slots.title`; the structure
declares `action` / `atomic` / `events` / `tasks` once. Nothing is
hand-labelled and no LLM is in the pipeline — it is deterministic string
templating, which is also why regeneration is byte-identical. The row schema
is `dataset/fastrule/`'s, so the same scorers read both:

```json
{
  "id": "uni_student:and_et:0-007",
  "text": "poster session tomorrow 12:30 and remind me pay the flat bills",
  "persona": "uni_student",
  "split": "test",
  "tier": "complex",
  "structure": "and_et",
  "family": "uni_student:and_et:0",
  "gold": {"atomicity": "compound", "operation": null, "kind": null},
  "expect": {"events": 1, "tasks": 1, "action": "mixed", "atomic": false,
             "slots": {"title": "poster session", "date_phrase": "tomorrow",
                       "time_phrase": "12:30", "title_2": "pay the flat bills"}}
}
```

`gold` is the ModelRouter classifier ground truth. `null` means the row has no
single right answer for that classifier — a cross-action compound is neither
`new` nor `remove` — and the board **excludes** those rows from that
classifier's score rather than guessing.

Two things are deliberately not modelled: **labels** (`category` / `tags`), because
the persona question is about structure and the shared
`categories_fixture.json` scheme was built for generic English content; and
**garbled STT** (word salad, cut-off audio), which cannot be ground-truthed by
construction.

## How to regenerate

    python -m scripts.gen_personas              # writes personas.jsonl (2,520 rows)
    python -m scripts.gen_personas --no-write   # composition table only
    python -m scripts.gen_personas --ablation   # writes personas_ablation.jsonl (2,520 rows)

Fully deterministic: `SEED = "personas-v1"` in `scripts/gen_personas.py` plus
the bank files are the only inputs — no network, no wall-clock, no
dict-order dependence (every RNG stream is keyed off a stable hash of the
family name, so adding a persona or a structure cannot move any other family's
rows). Two consecutive runs produce a byte-identical file; verified by `md5`.

The script self-verifies before writing: exact row count, all texts unique,
all ids unique, every row `split: "test"`, every persona covering every
structure, every template's slot set matching its structure's — and the leak
gate. Any violation raises instead of writing.

It never touches `~/.assistant_tools/` except to *read* `vocab.json` for the
leak gate. It imports `scripts/gen_fastrule_dataset.py`'s slot machinery
(`placeholder_info`, `resolve_slots`, `family_capacity`, …) rather than
reimplementing it, so "which placeholder becomes which slot key" has exactly
one definition in the repo.

## Scoring

    python -m scripts.persona_board                 # the boards + the variance summary
    python -m scripts.persona_board --structures    # per-structure spread, worst first
    python -m scripts.persona_board --examples 6    # failing rows, per persona per bucket
    python -m scripts.persona_board --data dataset/personas/personas_ablation.jsonl

Metrics are `scripts/fastrule_shape.py`'s, imported rather than recopied:
atomic **handle-rate** and **correct-on-handled** are primary; the non-atomic
bucket (deferred / covered / **half-executed**) is diagnostic; plus explicit-time
correctness, invention rate, the Q9 propose defer rate, and the three
classifiers' accuracy and macro-F1.

Three scorer notes worth knowing before reading a number:

- **Pin the engine.** The board must be run against one commit; record it with
  the numbers. The engine is under active change, and a board measured across
  two commits is a mixture, not a measurement. (This bit once already: a first
  pass straddled four commits to `assistant/` and had to be thrown away.)
- **A persona is a DAY-ONE user, with no personal config.** `KindFeatures`'s
  `user-category` / `user-tag` features read the user's own categories and tag
  scheme at inference; the scorer points `MACALENDAR_CATEGORIES` at a scratch
  path, so for a persona they fire from the shipped defaults only. That is
  deliberate and it is the right baseline — a new user has taught the app
  nothing yet, and "works on day one" is the question these sets exist to
  answer. It also means these two features are the one place where a *later*
  persona board could legitimately improve without any model changing, by the
  persona being given a config; that would be a different experiment, and it
  would need saying out loud.

- **Fast track only.** A deferred row is not a wrong answer — it goes to the
  LLM deep track, which may well handle it. `handle-rate` variance is variance
  in *who gets the deterministic, offline-capable, ~50 ms path*, which is a
  real disparity in latency and robustness, not (by itself) in correctness.
- **The spelled-out-time row is convention-confounded.** `_phrase_to_hhmm`
  resolves `quarter past four` to `04:15`; the engine prefers the afternoon.
  That disagreement lands entirely on the personas who spell times out, so the
  board splits time correctness into "the speaker fixed am/pm" (real errors)
  and "spelled out" (convention), and only the first is evidence of a defect.

## First measurement (2026-09-07, engine pinned at `5449eb2`)

Full boards archived in `boards/` — `2026-09-07_5449eb2_personas.txt` and
`2026-09-07_5449eb2_ablation.txt`. Data: `personas.jsonl`
md5 `787cbba41a5125047ef7034a2652ffcd`, `personas_ablation.jsonl`
md5 `943c9d77942bda8a09a246691081d5a0`. Headline:

| metric (persona set, structure-matched) | best | worst | spread |
|---|---|---|---|
| atomic handle-rate | observant 72.2% | student 33.9% | **38.3 pt** |
| correct-on-handled | esl 92.6% | retiree 61.0% | **31.6 pt** |
| operation accuracy (natural mix) | observant 100% | student 77.6% | **22.4 pt** |
| kind accuracy (natural mix) | observant 85.3% | student 64.2% | **21.1 pt** |
| atomicity accuracy (natural mix) | parent 98.3% | retiree 90.2% | 8.1 pt |
| compound recall @floor (natural mix) | four at 100% | student 62.1% | **37.9 pt** |

And the ablation, which says which half of a persona causes that:

| spread within block (structure-matched) | vocabulary varies | phrasing varies |
|---|---|---|
| atomic handle-rate | 5.5 pt | **31.5 pt** |
| correct-on-handled | 9.6 pt | **52.4 pt** |
| operation accuracy | **0.0 pt** | **20.9 pt** |
| kind accuracy | 3.2 pt | **17.3 pt** |
| atomicity accuracy | 1.0 pt | 7.1 pt |
| compound recall @floor | 2.0 pt | **28.8 pt** |

**Read: the vocabulary-independence claim survives; a broader
"works for other people" claim does not.** Swapping content nouns alone moves
the three classifiers by 0–3 pt. Swapping phrasing alone moves them by 7–29 pt
and moves the fast track's handle-rate by 31 pt. The engine is not tuned to
the author's *words*; it is tuned to his *sentence shapes* — verb-initial
imperatives of moderate length. Detail, mechanism and the failure families are
in the boards.

## Adding a persona

Add `banks/<id>.json` with a `persona` block (id, label, speech habits, action
bias, leak note), a `fillers` block (at minimum the six content banks), an
optional `mix`, and a `templates` entry for **every** structure in
`structures.json`; then add the id to `PERSONAS` in `scripts/gen_personas.py`
and regenerate. The generator will refuse a missing structure, an unknown
structure, a template whose slot set disagrees with its structure, and any
word that collides with the author's vocabulary — so a bad addition fails the
build rather than quietly skewing a board.
