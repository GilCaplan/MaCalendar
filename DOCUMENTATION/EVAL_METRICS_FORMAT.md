# The common eval-metrics format for an engine stage

Two stages already have scoring harnesses. They agree on the *discipline* and
diverge on nearly every *mechanic*. `decompose_validate` is about to become the
third (`assistant/engine/decompose_validate/PLAN.md` §5d: "it needs a dataset
and metrics of its own"), and it should not invent a fourth dialect.

This file is the contract a new stage's `eval_metrics` implements. It is
descriptive where the two existing harnesses agree, prescriptive where one of
them is clearly the better precedent, and **explicitly undecided** where they
genuinely disagree — those are collected in §7 as questions for a person, not
silently reconciled.

Scope: the *shape* of a scorer and its board. Which metrics a stage needs is
`dataset/METRICS.md`'s job (it is organised by component, five levels).

---

## 1 · What exists today

| | segmentation | fastrule |
|---|---|---|
| scorer | `assistant/engine/segmentation/experiments/score.py` | `assistant/engine/fastrule/experiments/fastrule_shape.py` |
| entry | `score_rows(rows, predict, fastseg=None, samples=10) -> dict` (score.py:485) | `main() -> int` (fastrule_shape.py:165) |
| renderer | `format_board(result) -> str` (score.py:749) | inline `print()` inside `main()` (fastrule_shape.py:325–381) |
| runners | `run_board.py`, `compare_boards.py` | `persona_board.py`, `realspeech_board.py` reuse it by import |
| doc'd at | `segmentation/ARCHITECTURE.md` §5 | `fastrule/ARCHITECTURE.md` §5 |

---

## 2 · Q1 — the shape of a score result today

### segmentation: a dict, and the only one of the two

`score_rows` builds one literal at score.py:661–713 with nine top-level keys:

```
n_rows            int
match_threshold   float      the Dice cutoff every P/R below is conditional on
boundaries        dict       board A
action_time       dict       boards A2 + B
tag               dict       board C   (incl. per_class P/R/F1 + confusion)
verifier          dict|None  board D — None when not run (score.py:692)
cost              dict       board E
composition       dict       board F
failures          list[dict] the appendix; [] when samples=0
```

Three properties worth copying:

- **Counts and their denominators are both present, and rates are precomputed
  beside them.** `boundaries` carries `tp`, `n_pred`, `n_gold` *and*
  `precision`, `recall`, `f1` (score.py:664–671). A consumer can re-derive or
  read straight off.
- **A rate with a zero denominator is `None`, not `0.0`** —
  `cost.calls_per_row` (score.py:695), `verifier.correction_recall`
  (score.py:730). `_pc` then renders it as an em-dash-ish blank (score.py:746).
  Zero would be a lie; `None` is "not measured".
- **A whole board can be absent as `None`** (`verifier`), and the renderer says
  so out loud rather than skipping the section (score.py:845–846).

**JSON-serialisable: yes. Round-trip identical: no.** Verified against the
self-test rows — `json.dumps` succeeds (3,712 bytes), but
`json.loads(json.dumps(r)) == r` is `False`, because
`composition.exact_by_count` values are 2-tuples (score.py:705–706) and
`failures[*].gold` / `.pred` are lists of 3-tuples (score.py:655–656). Tuples
come back as lists. Nothing in the repo currently persists a result as JSON, so
this has never bitten; a new stage should use lists so it does not.

One key is added *outside* the scorer: `result["wall_seconds"]` (run_board.py:210).

### fastrule: there is no result object at all

`fastrule_shape.main()` declares ~20 bare integer counters
(fastrule_shape.py:183–195), mutates them in one loop, prints, and returns
`int` 0. No dict, no separable renderer, nothing serialisable, no way to score
without printing.

That is not a stylistic quibble — it has already cost the project. Because the
only reuse surface is the module itself, `scripts/persona_board.py:53` and
`scripts/realspeech_board.py:95` reuse the board by
`from scripts import fastrule_shape`, monkey-patching `fastrule_shape.DATA` and
`sys.argv` (realspeech_board.py:96–105) and reaching into private names
(`FS._CLOCK`, `FS._ATOMICITY_REASONS`, `FS._EXPLICIT_TIME_RE`,
`FS._phrase_to_hhmm`, `FS._HHMM` — persona_board.py:233–318). **The file has
since moved to `assistant/engine/fastrule/experiments/fastrule_shape.py`, so
both imports are broken today.** A returned dict would have survived the move.

**Rule for the new stage: return a dict. Print from the dict, never instead of it.**

---

## 3 · Q2 — the shape of a printed board

### segmentation

Header, then lettered sections, then a clearly-labelled non-board appendix.
Real output, from `python assistant/engine/segmentation/experiments/score.py`:

```
segment board — 7 rows, 13 gold items, 13 predicted items
(items matched by action token-overlap ≥ 0.50, Dice)

A · BOUNDARIES — did we cut in the right places
   exact-set match (actions)   71.4%  (5/7)   <- the headline
   exact-row (action+time+tag) 14.3%  (1/7)
   right ITEM COUNT            71.4%  (5/7)   <- the CUT alone
   item precision              92.3%  (12/13)
   OVER-split                 1 rows (+1 items)   <- garbage immediately
   UNDER-split                1 rows (-1 items)   <- two more chances downstream
   (never summed: the two failures do not cost the same)
...
F · COMPOSITION — what the numbers above were computed OVER
   gold-count distribution (asks per row)
      1   ask      2 rows (28.6%)   exact-row   0.0%
   by trap
      interior-no-backscope            n=2     exact-row   0.0%

--- reading the failures (not a board; a pointer) ---
   [st-01] tomorrow gym at 7 and meeting at 11
      gold  [('gym', 'tomorrow at 7', 'event'), ...]
      why   ['right items, wrong time or tag']
```

Layout rules readable off score.py:762–901:

1. **Line 1 names the board and its composition** — `"<stage> board — {n} rows,
   {n_gold} gold items, {n_pred} predicted items"`.
2. **Line 2 discloses any threshold the numbers are conditional on**
   (`match_threshold`, score.py:764–765). A P/R printed without its matcher
   cutoff is not reproducible.
3. **Section header: `LETTER · UPPERCASE NAME — lowercase gloss`**, preceded by
   a blank line (`"\nA · BOUNDARIES — did we cut in the right places"`).
   Fixed order A, A2, B, C, D, E, F — the order in `ARCHITECTURE.md` §5's table.
4. **Metric line**: three spaces, label left-aligned to ~col 30, then
   `_pc(x, n)` = `f"{x/n:6.1%}"` (score.py:745–746 — fixed width, so a column
   of rates aligns), then two spaces and `({x}/{n})`, then optionally
   `   <- annotation` marking the headline or the thing that cannot be guessed.
5. **Every rate carries its denominator.** Stated as the reason `format_board`
   exists at all: *"a percentage without an n is the thing this project keeps
   banning"* (score.py:751–752).
6. **Sub-metrics indent under their parent** (`     on a SPOKEN time`,
   score.py:826) and use `(n=…)` when the denominator is a different
   population from the parent's.
7. **Caveats print as parenthesised lines inside the section**, not footnotes —
   score.py:789, 795, 806–807, 860–861. The "how to read this" travels with the
   number.
8. **An unpopulated board prints a reason, not nothing** — `"not run (needs
   BOTH a fastseg and a final prediction)"`, `"not reported by the predictor"`.
9. **Row detail is not a board.** It is fenced off under
   `--- reading the failures (not a board; a pointer) ---` (score.py:894).

### fastrule

Same spirit, different mechanics (fastrule_shape.py:325–381):

```
[test] FastRule product-shape board

ATOMIC rows (1841) — should HANDLE
   handled (committed)      58.4%
   correct-on-handled       72.1%
   deferred (missed work)   41.6%

TITLE QUALITY (on committed creates)
   titles that name nothing  3.2%  (14/438) — 'event', 'the appointment', 'a task'
...
--- mining (train only) ---
```

- Header is `[{split}] FastRule product-shape board` — **the split is in the
  header**, which the segmentation board does not do (its runner prints it,
  run_board.py:203–204).
- **Section titles carry their n and their purpose**: `ATOMIC rows ({A_N}) —
  should HANDLE`, `NON-ATOMIC rows ({N_N}) — diagnostic; the engine decides`,
  `PROPOSE rows ({P_N}) — should DEFER (Q9)`. No letters.
- `pc(x, n)` = `f"{x/n:.1%}"` (fastrule_shape.py:324) — **no fixed width**, and
  `(x/n)` appears only on some lines (title quality, "now" rows) while others
  print `(n=…)` or nothing at all.
- **A section with a zero denominator is omitted entirely** (`if D_N:`,
  `if TITLE_N:`, `if A_WRONG:`, `if T_N or INVENT_N:`) — the opposite of
  segmentation's "print the reason".
- Mining detail is fenced under `--- mining (train only) ---`
  (fastrule_shape.py:370) and gated on the split.

A third, newer precedent disagrees with both: `scripts/kind_board.py:168`
prints `f"{correct}/{n} ({100 * correct / n:.1f}%)"` — count first, percent in
parentheses, no fixed width. Three boards, three rate formats.

---

## 4 · Q3 — where they agree and where they diverge

### They agree on

| | evidence |
|---|---|
| A board of named metrics, never one number | score.py:6–8; `segmentation/ARCHITECTURE.md` §5; `fastrule/ARCHITECTURE.md` §5 |
| Composition is reported, not assumed | score.py board F (score.py:876); fastrule puts n in every section header |
| Train detail, test aggregates only | run_board.py:14–17 + 209; fastrule_shape.py:366–368 |
| Failure modes with different costs are never summed | score.py:789 + compare_boards.py:160–162 (over/under split); `_SEVERITY` harm weights, fastrule_shape.py:127–133 |
| Row/mining detail fenced off from the board | score.py:894; fastrule_shape.py:370 |
| Primary metrics are declared, not inferred | score.py:769 `<- the headline`; `fastrule/ARCHITECTURE.md` §5 marks two PRIMARY |
| `--split` / `--test` argparse + `main() -> int` | run_board.py:177; fastrule_shape.py:167 |
| A metric is added *because* a real defect was invisible | score.py:512, 585, 1063; fastrule_shape.py:246–252, 280–284, 297–300 |

### They diverge on

| dimension | segmentation | fastrule | consequence |
|---|---|---|---|
| result object | dict, 9 keys, JSON-safe (score.py:661) | none; local ints, printed (fastrule_shape.py:183) | fastrule cannot be diffed, cached, archived or re-scored; consumers monkey-patch instead |
| renderer | separable `format_board(result)` | inline prints | no way to score quietly |
| section naming | lettered `A`…`F` | uppercase names only | cross-board references ("board B") work for one stage only |
| rate format | `{x/n:6.1%}` fixed width, `(x/n)` **always** | `{x/n:.1%}`, `(x/n)` **sometimes** | columns align in one, not the other |
| empty section | prints "not run"/"not reported" (score.py:846, 865) | section vanishes (`if D_N:`) | a silent omission reads as "fine" |
| default split | **train** (`--test` opts in, run_board.py:177) | **test** (fastrule_shape.py:167) | the same command word means opposite halves; `kind_board.py:194` and `fastrule6k.py:68` both default train |
| threshold disclosure | `match_threshold` in the dict *and* line 2 | none in the header; harm weights printed inline only when `A_WRONG` | one board is reproducible from its own text |
| latency / cost | board E, reported *by the predictor* (score.py:364–384) | not measured | no cost axis on FastRule despite ~50 ms being its selling point |
| per-class P/R/F1 + confusion | yes, on matched items (score.py:715–725) | no | `dataset/METRICS.md` level 3 asks for these |
| predictor | pluggable `predict(text)`, three accepted return shapes | hard-wired `FastRule(RULE_THRESHOLD)` | fastrule cannot A/B two implementations on one board |
| dataset loading | `load_rows()` with split/family/trap filters (score.py:401) | inline `json.loads` + a substring prefilter (fastrule_shape.py:178) | no slice/stratify story on the fastrule side |
| import surface | **stdlib only**, an enforced allowlist, documented at score.py:25–31 | imports `assistant`, `freezegun`; needs env scratch first (fastrule_shape.py:38–44) | score.py is safe to import from a process already holding a model — which is why `check_invariant` can be both a metric and a runtime guard (score.py:38–42) |
| self-test | `python score.py` runs `_selftest()` (score.py:991) with planted defects proving **each board sees its own defect** (score.py:956–957) | none | one scorer is verified, the other is not |
| harm | none | severity-weighted (delete 4 · update/complete 2 · create 1 · query 0) | asymmetric-cost weighting exists on one board only |
| module naming | `experiments/score.py` | `experiments/fastrule_shape.py` | no convention for where a third goes |

---

## 5 · Q4 — the load-bearing conventions

Things that break something else if changed:

1. **`compare_boards._ROWS` addresses the result dict by key path**
   (compare_boards.py:42–63, e.g. `("action_time", "invention_items")`). Renaming
   or removing a `score_rows` key does **not** raise — `_get` returns `None`
   (compare_boards.py:66–72) and `fmt` prints `"—"` (compare_boards.py:77–78).
   So a key rename silently blanks a comparison column. **The dict keys are a
   published interface; treat them like the frozen stage contracts.**

2. **`run_board.py` filters `format_board`'s *text*** in `--test` mode, by line
   prefix (run_board.py:213–215):

   ```python
   board = "\n".join(l for l in board.splitlines()
                     if not l.strip().startswith(("·", "-", "row ", "  '")))
   ```

   That is a text-layout dependency. It is also **not the guard it looks like**:
   the failure appendix's row lines strip to `[st-01] …`, which matches none of
   those prefixes. The real leakage guard is `samples=0` on the line above
   (run_board.py:209). Keep `samples=0` as the mechanism; do not rely on prefix
   filtering, and do not add a prefix a filter elsewhere assumes.

3. **`tests/unit/test_artifact_claims.py:826–833` regex-parses
   `fastrule_shape.py`'s source** for the `_SEVERITY` weights:

   ```python
   sev = dict(_re.findall(
       r'"(delete_event|update_event|complete_todo|create_event)":\s*(\d)', shape))
   ```

   So the *literal formatting* of that dict is load-bearing — reflowing it so a
   weight lands on the next line turns the artifact-claims test red. A new
   stage's scorer should expect the same treatment for any constant a published
   page quotes (`DOCUMENTATION/ARTIFACT_BUILDER.md`).

4. **Metric *label text* is a cross-file convention.**
   `dataset/personas/boards/*.txt` reproduces fastrule_shape's section names and
   metric labels verbatim in a transposed layout, and persona_board.py:20–25
   documents them as the shared vocabulary. Renaming a printed label orphans the
   archived boards.

5. **score.py's stdlib-only import list is a hard requirement**, not tidiness:
   `check_invariant` is exported and used as the runtime ACCEPT guard
   (score.py:38–42), and two model-loading jobs segfault this project
   (score.py:25–31, CLAUDE.md). A scorer that imports `assistant` cannot be the
   runtime's guard.

6. **`score.py`'s `_selftest()` is the scorer's only test.** No file under
   `tests/` imports either scorer — the sole test-side reference to
   fastrule_shape is the source-regex above. `python score.py` must stay green;
   a new stage inherits that obligation, since pytest will not catch it.

7. **Scratch-store setup must happen before importing `assistant`** —
   fastrule_shape.py:38–44, compare_boards.py:26–32, kind_board.py:38–46 all do
   it at module top. CLAUDE.md: the paths are read at import time, so a fixture
   is too late. `MACALENDAR_TRACE_BUS` and `MACALENDAR_NO_WARMUP=1` included.

---

## 6 · Q5 — the format a new stage must provide

### 6.1 · Module contract

A stage's eval harness is **one scorer module plus one runner**:

```
assistant/engine/<stage>/experiments/
    eval_metrics.py     the scorer:  score_rows() + format_board() + _selftest()
    run_board.py        the runner:  dataset loading, slicing, splits, printing
```

The scorer:

```python
def score_rows(rows, predict, *, samples: int = 10, **stage_opts) -> dict: ...
def format_board(result: dict) -> str: ...
def main(argv=None) -> int: ...          # no args => run _selftest()
```

Requirements, each carried over from a precedent that earned it:

- **`predict` is a callable, not a hard-wired system.** Accept the three return
  shapes `call_predictor` already accepts (score.py:364–384): a plain list, a
  `(items, meta)` tuple, or a dict with `items` plus `calls` / `seconds` /
  `tier`. A pluggable predictor is what lets a cycle run a COMPARISON
  hypothesis (`ITERATION_PROTOCOL.md` §"Two kinds of hypothesis").
- **`samples=0` suppresses all row detail** (score.py:495–496). This is the
  leakage mechanism, not a text filter.
- **Latency is reported by the predictor, never measured in the scorer** — it is
  what keeps the scorer's import list clean (score.py:27–31, run_board.py:134–136).
- **Stdlib-only if the stage's checks allow it.** `decompose_validate`'s do:
  PLAN.md §4c states its checks are "arithmetic and set comparison". A stdlib
  scorer can be imported by the runtime as its own guard, exactly as
  `check_invariant` is.
- **`_selftest()` with planted defects, one per board**, asserting expected
  values — and each defect must show up on *its own* board (score.py:956–957,
  1052–1070). A board that cannot be shown to see its own defect is not
  evidence.

### 6.2 · The required result-dict schema

**JSON-serialisable, lists not tuples, `None` for an unmeasured rate.**

Required top level, every stage:

| key | type | meaning |
|---|---|---|
| `stage` | `str` | the stage name, e.g. `"decompose_validate"` — new; neither existing scorer has it, and a board dict that cannot say what it scored is not archivable |
| `split` | `str` | `"train"` \| `"test"` \| `"selftest"` |
| `n_rows` | `int` | rows actually scored (after dropping rows with no gold) |
| `thresholds` | `dict[str, float]` | every cutoff the numbers below are conditional on (segmentation's `match_threshold` generalised) |
| `composition` | `dict` | what the score was computed over — see below |
| `boards` | `dict[str, dict]` | one entry per board, keyed by its short name |
| `failures` | `list[dict]` | `[]` when `samples=0`; each row `{id, text, gold, pred, why}` (score.py:652–658) |

`composition` must carry at least:

| key | type |
|---|---|
| `n_rows` | `int` |
| `by_<primary axis>` | `dict[str, int]` — the distribution the corpus could teach instead of the criterion (segmentation: gold ask-count, score.py:703) |
| `correct_by_<axis>` | `dict[str, [ok, n]]` — the headline metric sliced by that axis |
| `by_family` or `by_trap` | `dict[str, {n, correct, seconds}]` |

Each board sub-dict must carry, for every rate it reports, **the numerator and
the denominator as separate integer keys**, and may carry the precomputed rate.
A rate whose denominator is 0 is `None`, never `0.0`.

**Per-stage extensions** — everything inside `boards` is the stage's own, and a
new board name is not a schema change. The invariant is: nothing outside
`boards` is stage-specific, and nothing inside `boards` is required by this
document. For `decompose_validate` the boards fall out of PLAN.md §4c:

| board | what it answers | source |
|---|---|---|
| `honoured` | every time-phrase in X1 was honoured — the value-level analogue of segmentation's no-loss invariant, **must be 0 violations** | PLAN.md §4c |
| `resolution` | resolved date/clock agrees with the words (weekday, ordinal, series start) | PLAN.md §4c table |
| `arithmetic` | cross-field: `end_time > start_time`, `recur_until > date`, no past date | PLAN.md §4c |
| `completeness` | a clock with no day; `recur_until` with no `recurrence` | PLAN.md §4c |
| `invention` | a date/recurrence/quantity no words support — validate's invariant | PLAN.md §5c |
| `cost` | calls/row, seconds/row (0 calls expected; validate is deterministic) | score.py board E |
| `composition` | ask-count spread, per-family, per-rule | SPEC.md:205–209 |

Two shapes that must **not** be collapsed into one number, because they cost
differently (the over/under-split precedent, score.py:789): a field left
**unresolved** is recoverable downstream — LLMJudge holds X1 (PLAN.md §4b
property 3) — while a field resolved **wrongly** is a confident wrong answer
that reaches the calendar. Report them as separate counts and never sum them.

### 6.3 · Board layout rules

1. Line 1: `"<stage> board — {n} rows, <composition summary>"`.
2. Line 2: the thresholds, in parentheses. Omit only if there are none.
3. Sections in a fixed documented order, each preceded by a blank line, headed
   `NAME — lowercase gloss` with the section's `n` in parentheses when the
   section scores a sub-population.
4. Metric line: 3-space indent · label left-aligned to col 30 · rate ·
   two spaces · `({x}/{n})` · optional `   <- annotation`.
5. **Every rate carries its denominator.** No exceptions, including
   sub-metrics — a sub-metric over a different population shows `(n=…)`.
6. Sub-metrics indent to 5 spaces under their parent.
7. A rate with a zero denominator prints a blank, not `0.0%`.
8. **An unpopulated section prints the reason it is empty.** Do not omit it.
9. Caveats print as parenthesised lines inside their section.
10. Row detail is fenced under a line that says it is not a board, and is
    emitted only when `samples > 0`.
11. Mark the PRIMARY metrics inline (`<- the headline`), so the board says what
    it is optimising rather than leaving a reader to rank eight rates.

---

## 7 · The rules the project already insists on

Each of these is already written down somewhere; a new board inherits all of
them. Sources given so they can be argued with at the source, not here.

| rule | source |
|---|---|
| **Never one number.** A single figure hides which way a run is failing, and the ways cost different amounts. | score.py:6–8; `segmentation/ARCHITECTURE.md` §5; DESIGN.md §6 |
| **Always name the metric with the number.** "70→72" is meaningless; "count-correct 73.5%→75% on event+task" is a result. | CLAUDE.md; `fastrule/ARCHITECTURE.md` §5 |
| **Every figure carries dataset + slice, metric, and meaning** — three things, one clause of consequence included. | `ITERATION_PROTOCOL.md` §"Reporting: dataset + metric + meaning" |
| **Always report composition** — what the score was computed over. A corpus with a characteristic ask-count teaches the COUNT rather than the criterion, so the distribution prints beside every score. | SPEC.md:205–209; score.py:16–20 |
| **Train detail, test aggregates only.** Direction comes from the training pool alone; a run that could show which held-out rows to fix is a run that lets you fit the test set. No test number ever spawns a hypothesis. | run_board.py:14–17; fastrule_shape.py:366–368; `ITERATION_PROTOCOL.md` §"The train–test split" |
| **Never sum failure modes that cost differently.** Over- vs under-split stay separate counts; harm is severity-weighted because a wrong delete and a wrong title are not the same failure. | score.py:789; compare_boards.py:160–162; fastrule_shape.py:127–133; `dataset/METRICS.md` level 2 |
| **A percentage without an n is banned.** | score.py:751–752 |
| **Report the FULL board every run**, in chat and in the md file alike — a metric that moved against you and went unreported is a broken instrument next cycle. | `ITERATION_PROTOCOL.md` §"Report the FULL board"; compare_boards.py:41–42 |
| **A measured number must cite a run that still exists.** | CLAUDE.md; `ARTIFACT_BUILDER.md` |
| **Split by family, not by row**, and report item-string disjointness as a number. | SPEC.md:195–203; run_board.py:8–12 |
| **Stratify a sample so no shape is absent.** A proportional slice that leaves traps empty cannot test a hypothesis about them. | run_board.py:53–60; `segmentation/ARCHITECTURE.md` §5 |
| **The scorer never touches the real stores.** Scratch `MACALENDAR_*` before importing `assistant`, `MACALENDAR_NO_WARMUP=1`, BLAS pinned to one thread, and `source: "test"` on anything driving the API. | CLAUDE.md; fastrule_shape.py:38–44 |
| **Audit the gold before scoring against it.** score.py's `--rows` mode runs the invariant over the labels with no predictor in sight, and reports duplicate ids. | score.py:1125–1160 |

---

## 8 · How to add a new stage's board — checklist

1. **Write the stage's contract first**, as one testable sentence. Segmentation's
   is the invariant; `decompose_validate`'s candidate is PLAN.md §5c ("every
   field must be traceable to the transcript"). A board cannot exist before the
   thing it checks is stated mechanically.
2. **List the boards** and mark the PRIMARY ones. Add each to
   `dataset/METRICS.md` under its component level, and to the stage's
   `ARCHITECTURE.md` §5 table.
3. **Build the dataset before changing behaviour** — `dataset/stages/<stage>/`
   (per `ITERATION_PROTOCOL.md`'s per-stage rules), split by family, its own
   sealed test half, never mutated to suit another stage.
4. **Write `eval_metrics.py`**: `score_rows` → the §6.2 dict, `format_board` →
   the §6.3 layout, stdlib-only if the checks allow it.
5. **Write `_selftest()` with one planted defect per board** and assert the
   expected value of each. Confirm each defect lands on its own board, and that
   a perfect predictor scores perfectly everywhere.
6. **Add a gold audit mode** — run the contract over the labels themselves,
   report violations and duplicate ids, exit non-zero.
7. **Write the runner**: `--split`/`--test`, `--limit`, `--sample`,
   stratified sampling with a per-family floor, `samples=0` on the held-out
   half, scratch stores set before any `assistant` import.
8. **Print the board once, from the dict.** No metric computed inside
   `format_board` that is not in the result.
9. **Register the baseline** in the stage's `RESULTS.md` with dataset + slice +
   metric + meaning, and append the run to `dataset/loop_log.csv`.
10. **Check the consumers**: if any comparison table addresses result keys by
    path (as compare_boards.py does), add the new keys there — a missing key
    prints `—` rather than failing.
11. **Do not rename anything a published page or an archived board quotes**
    without running `pytest tests/unit/test_artifact_claims.py`.

---

## 9 · What the two existing stages do inconsistently — decisions for a person

These are real disagreements, not oversights. Each has two defensible readings
and picking one silently would make a third board wrong-by-fiat. Recorded here
rather than resolved.

**D1 · The default split.** `fastrule_shape` defaults to **test**
(fastrule_shape.py:167); `run_board`, `kind_board` (kind_board.py:194) and
`fastrule6k` (fastrule6k.py:68) default to **train**. So the same bare command
means "the sealed half" on one board and "the mining half" on three others.
FastRule's reading is defensible — `ITERATION_PROTOCOL.md`'s lane-reporting rule
says the reported figures *are* the test half's. The train default is defensible
too — mining is the common operation and the sealed half should require asking
for it by name (which is exactly `load_rows`' argument, score.py:411–413).
**Which is the project default?**

**D2 · Rate formatting.** Three formats in three boards: `{x/n:6.1%}` +
always-`(x/n)` (score.py:745), `{x/n:.1%}` + sometimes-`(x/n)`
(fastrule_shape.py:324), and `{x}/{n} ({pct:.1f}%)` (kind_board.py:168). §6.3
above proposes the first because fixed width aligns a column and the
denominator is never optional — but persona_board's archived text boards are
built on the second, so standardising means either reformatting those or
accepting a permanent split.

**D3 · Lettered sections or named sections.** Segmentation's `A`…`F` make
cross-board references possible ("board B", used throughout its docs and
`compare_boards._ROWS` labels). FastRule's named sections read better standalone
and survive inserting a board in the middle. **Pick one for new boards.**

**D4 · Empty section: reason, or omit.** Segmentation prints `"not run"` /
`"not reported"`; FastRule drops the section (`if D_N:`). A dropped section is
indistinguishable from a clean one to a reader diffing two boards. §6.3 proposes
"print the reason", but FastRule's conditional sections were deliberate — the
board is already long.

**D5 · Does `fastrule_shape` get retrofitted?** Everything in §6 assumes a
result dict. FastRule has none, and two scripts are broken today
(`from scripts import fastrule_shape`, persona_board.py:53 and
realspeech_board.py:95, pointing at a file that moved to
`assistant/engine/fastrule/experiments/`). Retrofitting a dict would fix both
and make the persona/realspeech boards derived rather than hand-reproduced —
but it touches a scorer whose numbers are the reported figures for 13 batches,
and any change to it needs its own before/after proof. **Retrofit, or leave
FastRule as a documented exception?**

**D6 · The failure-appendix shape.** score.py returns structured rows
(`result["failures"]`, capped by `samples: int`) and prints them uniformly;
fastrule_shape collects a `dict[str, list[str]]` of truncated text snippets
bucketed by failure category (fastrule_shape.py:196, 372–377). The buckets are
more diagnostic; the structured rows are machine-readable and archivable.

**D7 · Does the new board own a harm metric?** FastRule weights errors by cost
(`_SEVERITY`); segmentation does not. `decompose_validate` plausibly needs one —
a wrong resolved date silently books the wrong day, an unresolved field is
recoverable — but the weights are a product judgement, like the
delete=4/create=1 scale was.

**D8 · Module and directory naming.** `experiments/score.py` (segmentation) vs
`experiments/fastrule_shape.py` (fastrule) vs `scripts/kind_board.py` (a
component board outside the stage tree entirely). §6.1 proposes
`assistant/engine/<stage>/experiments/eval_metrics.py`, matching the name this
work was commissioned under — but that is a third name, and it would be
reasonable to standardise on `score.py` inside each stage instead.
