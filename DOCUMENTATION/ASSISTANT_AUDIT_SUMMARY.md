# Assistant audit — summary & gap list (2026-08-26)

Three runs of `scripts/audit_assistant.py` (84 generated commands + 8 audio, scratch DB, real vocabulary) on the M4 / llama3.1:8b setup. Raw per-run reports: `ASSISTANT_AUDIT.md` (latest) and the JSON next to it.

## Progression

| Run | Quick answer ✓ | Settled ✓ | First result p50 / p95 | Settled p50 | What changed before it |
|---|---:|---:|---:|---:|---|
| 1 | 45 % | 44 % | 9.5 s / 18.9 s | 26.8 s | baseline after num_ctx fix |
| 2 | 71 % | 69 % | 8.3 s / 17.9 s | 25.8 s | vocab false-positive guard; task-title extraction; sanity pass (past dates, recurrence, junk events); conservative self-check; prompt rules |
| 3 | **88 %** | **86 %** | **7.9 s / 15.8 s** | 24.1 s | deterministic relative-date resolution; self-check guards (no task→event flips); rule-parser titles with attendees; time-format normaliser |

By area, run 3: query 100 %, adversarial 100 %, mixed 100 %, events 90 %, update/delete 86 %, tasks 83 %, chat-phrasing 80 %.
By path: **rule fast path 91 % correct at 0.1 s**; LLM path 88 % at ~10 s; hybrid 75 %.

## Bugs found and fixed today (all verified by the harness or unit tests)

1. **Ollama context window** — default 4096 < our ~4k-token system prompt. Every call overflowed: prefix cache lost (30–60 s calls) and the date table truncated (wrong weekdays). `ollama.num_ctx: 8192`.
2. **Placeholder-date leak** — few-shot examples used `<resolve-from-today>`; the 8B model copied it into real events (two junk rows existed in the real calendar). Dates are now stripped from examples and `CalendarIntent` rejects non-ISO dates / normalises `12:00 PM`.
3. **Vocab auto-correct false positives** — with 300+ words, fuzzy matching rewrote *Shacharit→Nachman, Mincha→Liora, Tamar→Meshulam, Golda→Peleg* and learned bad aliases. Now: never rewrite an English or already-known word, stricter thresholds for short words, first letter must match, aliases only learned at ≥0.9 or when you teach them.
4. **Rule parser tasks** — "remind me to buy milk" produced a task titled *me*; "I need to…" routed to complete_todo; "put X on the groceries list" to query. Phrase-level extraction + route overrides; "remind me about X at 9 am" becomes an event.
5. **Relative dates** — the LLM picked yesterday's or today's weekday ~40 % of the time. Weekday/tomorrow/"the 19th" phrases are now resolved deterministically on the server and override the model; past dates are bumped.
6. **Recurrence** — "every monday / daily / mondays" never set `recurrence`; now set from the transcript.
7. **Self-check** — proposed a change on 98 % of commands, fixed 0–3, broke 2–4 per run. Patches are now filtered (times must be spoken in the command, no date/list changes, titles only over placeholders, no task→event flips) **and it is advisory by default** (`self_check_apply: false`): visible in the trace/log, not applied.
8. **Server/phone parity** — trailing "execute" stripped, keyword titles ("set meeting") fixed in the background, title-fixer no longer puts dates/times in titles, prompt-cache-friendly prompts for all three LLM call types.

## What is good

- The rule fast path is the star: 91 % correct, 100 ms, no LLM. Most single events, queries, deletes and simple tasks never touch the model.
- Multi-event commands (2–3 events, same or different days) now parse correctly on the LLM path in the large majority of cases.
- The trace makes every failure diagnosable from the phone; the harness reproduces them in minutes.
- Vocabulary + Whisper prompt: names that appear in the vocab come out right in audio tests (Ravid, Tal, Golda, Technion).

## Re-checked 2026-08-28

- Gap 1 **no longer reproduces**: "lunch with Tal on monday at noon and coffee with Ezra on friday at 9"
  and similar now raise `RuleParserSkip` or land at 0.59 confidence, so they reach the LLM instead of
  fast-pathing as a single event.
- Gap 2 is fixed for the evening cases (Kems/dinner/gym at a bare hour all resolve PM), but re-testing it
  surfaced a worse bug in the other direction: **an explicitly spoken "7am" was booked at 7 PM**, because
  the morning exemption tested `\b(am|a.m.)\b` and neither "7am" nor "a.m." carries the word boundary it
  needs. Morning words were not consulted at all, so "shacharit at 7" was also PM. Fixed, with regression
  tests in `tests/unit/test_rule_parser_meridiem.py`.
- The harness itself was writing the transcripts it replays, and any aliases the auto-corrector learned
  from them, into the real `~/.assistant_tools/vocab.json`. It now copies the vocabulary and works from
  the copy, so a run measures the real word list without changing it.

## Run 4 — 2026-08-28 (84 commands)

**94% correct** (was 88%), 0 parse errors. First result p50 6.7 s / p95 15.6 s.
By area: query/adversarial/mixed 100%, events 97%, from-chats 93%, update-delete 86%, tasks 83%.
By path: rule 94% at 0.1 s, llm 98%, hybrid 78%.

Bugs found by re-testing and fixed in this run: the `7am`→19:00 meridiem hole, the
`from 9 to 10` parser crash, `12 to 1` ending before it starts, and rename. See TASKS 41–45.

Five failures remain in the report:

| Failure | Real? | Note |
|---|---|---|
| `update/rename` — "rename the meeting with Tal to robotics sync" | **was real** | fixed after this run; re-run to confirm |
| `tasks · multi/different-due-dates` — "book the driving test due next monday" became an event | **real** | gap 3 below: the hybrid prompt still allows `create_event` when the rule parser said `create_todo` |
| `events · multi/same-day-3` — "dinner with Danny at 8 pm" booked 18:00–20:00 | **real** | the LLM read "at 8 pm" as the end; a sanity fix could pin a stated "at" time to the start |
| `tasks · multi/same-due-date` | harness | two `create_todo` actions vs one with two titles — same result for the user |
| `from-chats · chat-phrasing` — "moved from 9:30 to 9" | harness | the event to update was never seeded (`in DB []`) |

The self-check proposed a correction on 78 of 81 commands and fixed none: it remains
pure cost (it is what makes "settled" ~21 s vs 6.7 s) and is correctly left advisory.

## Should the self-check come back? — measured 2026-08-28

The design is sound and is what is built: the rule path answers in 0.1 s, an LLM
re-reads the result in the background and patches it. The question is only
whether the checker is accurate enough to be trusted with the patch. Ran the
full corpus with `verify_fast_path: true` **and** `self_check_apply: true`:

| | self-check off | on, and applying |
|---|---:|---:|
| correct (quick answer) | 95% | 98% |
| correct once settled | 95% | **95%** |
| time to settled p50 | 7.2 s | 25.7 s |
| time to settled p95 | 16.0 s | **72.9 s** |

It proposed a correction on 78 of 81 commands, applied 29 of them, **fixed 0 and
broke 2** — it takes correct answers and makes them wrong. The two it broke show
why:

- "meeting tomorrow at 2 **sorry not 2, 3 pm** with Adin" — the speaker corrected
  themselves mid-sentence and the checker undid the correction, back to 2 pm.
- "Kems tomorrow at 8 with Ravid and Ezra" — "Meeting time is 8am, not 8pm",
  overriding the evening heuristic, which is right (Kems is a bar).

Both are cases where the command was unambiguous and the checker second-guessed
it. It has no way to tell "different from what I would have said" from "wrong".

Note this is *worse* than the earlier runs, not better, and the reason matters:
the deterministic layer improved a lot on 2026-08-28, so the checker is now
mostly second-guessing rules that are already right. **The better the
deterministic layer gets, the more damage a low-precision checker does.**

Worth revisiting only with: verification limited to genuinely ambiguous commands
(low rule confidence, a bare hour with no morning/evening signal, a placeholder
title) rather than all of them; a requirement that any correction cite a token
actually spoken; and a stronger model for the checker than the one doing the
first pass.

## Run 5 — 2026-08-31 (89 commands)

**93% correct**, 0 parse errors. First result p50 5.5 s / p95 13.9 s.
By area: query/adversarial/mixed/update-delete 100%, events 95%, from-chats 87%,
**tasks 88% (was 83%)**. By path: rule 97% at 0.1 s, llm 93%, hybrid 78%.

The headline is inside run-to-run noise of run 4's 94%: the one extra failure is
`from-chats` "sadna on sunday the 15th at 9 am then driving lesson at 8 am",
which returned one event instead of two. Re-run four times either side of this
change it returns two every time — an LLM-path flake, not a regression.

What this run was measuring: **a multi-item task command produced one task.**
"I want to buy chicken and rice" gave a single task — on the LLM path a merged
"Buy chicken and rice" (and, as reported, sometimes an invented "buy
groceries"), on the rule path "buy chicken" plus a task called "rice". Now it is
one task per item with the verb shared out, and a tag inferred from each title.

Six cases were added to the corpus for it — `multi/shared-verb`,
`multi/shared-verb-3`, `multi/shared-verb-people`, `single/internal-and`,
`single/inferred-tag`, plus row counts on the existing multi cases — and all six
pass on the rule path at ~30 ms.

The checker could not have caught this before: `titles_contain: ["chicken",
"rice"]` is satisfied by one task called "buy chicken and rice" just as well as
by two. It now also checks `todo_count` and `tags_contain`.

The two remaining task failures are the same two as run 4 (gap 3, hybrid
over-creation on task lists with due dates), unchanged by this work.

One thing the 8B model still gets wrong on the LLM path, and did before this
change too: it splits "buy a birthday gift for mom and dad" into two tasks, in
spite of an explicit prompt rule not to. The rule parser gets it right and
handles that phrasing at 0.95 confidence, so the model rarely sees it.

## Run 6 — 2026-09-02 (89 commands)

**97% correct** after the quick answer, and **97% once settled** — the first run
where those two are equal. 0 parse errors. First result p50 4.7 s / p95 19.4 s;
settled p50 17.1 s / p95 39.2 s.

By path: **rule 97%** (n=39, p50 0.0 s), **llm 98%** (n=41, p50 7.8 s),
**hybrid 89%** (n=9, p50 12.1 s). By area: adversarial/mixed/query/update-delete
100%, events 97%, tasks 94%, from-chats 93%.

Routing: 39 of 89 commands answered by the rules alone, 50 by the model — a
44 / 56 split. That is the number the 0.85 threshold actually buys.

What changed before it: the self-check now runs on **every** command rather
than only low-confidence ones, and it judges what reached the database instead
of the parser's raw slots. The effect of that second change is the headline
here — it proposed a correction on 37 of 89 commands, **fixed 0 and broke 0**,
against a rate of ~96% proposals earlier in the week. It stays advisory
(`self_check_apply: false`); the run that measured applying its patches fixed 0
and broke 1.

Settled equalling quick is the point of the run. Previously the self-check cost
accuracy between the two columns; now it costs nothing and still catches
confidently-wrong parses at execution time through the escalation path.

**These are the figures the published explainer quotes.** `ASSISTANT_AUDIT.md`
is overwritten by the next run, so a number cited anywhere durable has to be
copied here first — `tests/unit/test_artifact_claims.py` checks that the
artifact's headline still appears in this file.

## Run 7 — 2026-09-03 — the first time the memory was measured at all

Every previous run replayed the corpus against an **empty** command history,
because the harness pointed `MACALENDAR_MEMORY_DB` at a fresh temporary file.
So every claim about personalisation was untested by construction, and nothing
said so. `--memory` replays against a copy of the real history; `--memory-k 0`
turns retrieval off under otherwise identical conditions.

Both arms, same code, same corpus, same machine, minutes apart:

| | memory ON (k=4) | memory OFF (k=0) |
|---|---:|---:|
| **overall** | **98%** | **97%** |
| rule path | 97% (n=39) | 97% (n=39) |
| llm path | 100% (n=41) | 100% (n=42) |
| hybrid path | 89% (n=9) | 75% (n=8) |

**The honest conclusion is that this did not measure what it was built to
measure.** The reason is in the third row: the LLM path is the only place
few-shot examples enter the prompt, and it scores **100% in both arms**. There
is no headroom. A corpus on which the affected path is already perfect cannot
detect an improvement to it, and would only detect harm.

What the other rows are worth:

- **rule path, identical.** Expected — retrieval never touches it. A useful
  negative control: it says the two runs were otherwise comparable.
- **hybrid, 89% vs 75%.** Do not read this. The n differs (9 vs 8), so a
  command changed parse path between runs; the buckets do not contain the same
  commands, and at n=8 one command is 12 points.
- **overall, one command.** 98% against 97% is a single command out of 89, and
  it is the one that moved buckets.

So: **no measurable effect, and the instrument cannot currently detect one.**
That is a finding about the harness as much as about the feature, and it was
worth two runs to learn — the alternative was continuing to argue about `k`.

### What would actually answer the question

The corpus is the wrong instrument for this. It is built from commands chosen
to exercise the parser, and the parser is at ceiling on the path that matters.
Measuring the memory needs commands the model gets *wrong* without help — which
means selecting them from the real history's failures rather than from a
hand-written corpus, and holding each out of the memory it is being tested
against.

Until that exists, `k=4` versus `k=0` is not a decision the data supports
either way, and the reasonable thing is to leave it where it is.

### Also confirmed this run

- Self-check proposed a correction on 39 of 89, **fixed 0, broke 0** — the
  same result as every run since it was demoted to advisory. It stays advisory.
- Routing split unchanged at 39 rule / 50 model, so the 0.85 threshold is
  sending the same proportion each way as it did in run 6.
- No parse errors in either arm.

## Remaining gaps (ranked, from the 2026-08-26 run)

1. ~~**Rule parser splits multi-event sentences into one**~~ — fixed, see above. ("lunch with Tal on monday at noon and coffee with Ezra on friday at 9" → only lunch). It is confident (0.90), so the LLM never sees it. Fix: lower confidence when a span contains two time expressions, forcing hybrid.
2. **Ambiguous bare hours** ("Kems tomorrow at 8" → 8 AM). Fix: heuristic — evening-ish venues/words (dinner, Kems, drinks, pregame) or hours 1–6 without am/pm → PM; ask when truly ambiguous.
3. **Hybrid over-creation** for task lists with due dates ("two tasks due tomorrow…" adds an event; "buy a gift due thursday" becomes events). Fix: when the rule parser identified create_todo, forbid create_event in the hybrid prompt.
4. **update_event rename / "moved from 9:30 to 9"** — rename not supported by the rule slots; "moved from…to…" needs match_start_time=9:30, new_start_time=9:00.
5. **Disfluencies** ("at 2 sorry not 2, 3 pm") — the LLM usually gets it; the self-check "corrected" it back. Keep self-check advisory.
6. **Whisper** (3/8 audio correct with synthetic voices): "Talat noon", "Adjim" — beyond vocab's reach. Options: whisper-small when idle, or a second-pass STT on low-confidence segments.
7. **Latency** — LLM path ~8–10 s first result, dominated by ~15 tok/s generation of JSON with a 4k-token prompt. Options: trim the system prompt (schemas are verbose), a smaller JSON envelope, or a faster model for the first pass with the 8B as verifier once RAM allows.

## How to re-run

```
python -m scripts.audit_assistant --audio            # full, ~20 min
python -m scripts.audit_assistant --area tasks       # one area
python -m scripts.benchmark_models --history         # LLM models on your real history
```

## Runs 8–9 — 2026-09-03 — the engine's first measurements (branch `engine-v2`)

The brain was rebuilt as the 8-stage engine (TASKS row 79, `ENGINE.md`); these
two runs are its acceptance measurements against run 7's baseline (98% exact
match, tasks 95%/79% recall/precision, old brain, k=4).

**Run 8 (92 cases): 85% quick / 80% settled · recall 83% · precision 88% ·
first p50 33.3s.** The per-stage tables named every mechanism, which is the
design working:

- The cross-check cried wolf: 232 findings, loop-backs on 39 of 51 deep
  commands (85s avg vs 36s unlooped). Three causes, all stage-internal: a
  multi-title create_todo could satisfy only ONE extracted ask ("milk, eggs
  and bread" → two false "missing" → the background patch added DUPLICATES,
  breaking 4 commands that were right at the quick answer); observance-gate
  refusals didn't count as covering their ask (every gated command
  loop-stormed pointlessly); extraction kind-mislabels became false missings.
- The observance gate itself worked exactly as specified — ~5 "failures" were
  Friday-evening bookings it rightly refused; the corpus predated the policy.
  Gate-colliding cases are now weekday-pinned and the gate has its own two
  cases (Saturday gym → refusal; Friday-night Shabbat dinner → booked).
- Two commands died whole on one item's validation error.

**Run 9 (94 cases, after the revamp + extraction-prompt fine-tune): 88%
quick = 88% settled · recall 90% · precision 90% · first p50 16.7s · settled
p50 17.7s.** Loop-backs 39→3 commands, findings 39→4, broken-by-self-check
4→0, extra task rows 8→3, deep p50 70s→22.7s. **The fast track is at
parity with the old brain: 97% quick AND settled, recall 98%, precision
100%, ~50ms.** The capacity-aware matcher plus a granularity contract in the
extraction prompt (mirroring decompose's own splitting rules, with worked
examples from run 8's failures) is what closed the false-alarm gap.

**Remaining gap to the 98% bar (11 failures), ranked:**
1. Multi-item deep segmentation quality (6): event chains ("one at 4,
   another at 6:30") drop or duplicate an item; colon task-lists sometimes
   over-split now. Next single-stage tune: event-chain examples in the
   segment prompt, and an update/delete that ended NOT-FOUND should stop
   counting as covering an ask (it hid a "night shift" create misread from
   the checker).
2. Action-layer quirks the corpus surfaces (2, predate the engine): an
   update that reports success while changing nothing ("move my 1pm meeting
   to 3pm"), and `_find_event` missing a seeded "Guri Karpas" on 'guri'.
3. Worst-case deep latency: three disfluent monsters at 95–208s (bounded by
   the loop budget, still ugly). `engine.reconcile: uncertain` is the
   designed lever; run 9's telemetry (findings on 4/94) begins to justify it.

Conclusions live here because ASSISTANT_AUDIT.md is overwritten every run.

## Run 10 + the first real-utterance comparison — 2026-09-03 evening

**Run 10 (94 cases, after round 3's stage fixes): 91% quick = 91% settled ·
recall 93% · precision 91% · first answer p50 5.3s (was 16.7s) · deep p50
6.6s / p95 37.1s (was 22.7/75.8).** Three cycles of measure→name-the-stage→
fix: 80% → 88% → 91%, first-answer latency down 6×. The event-chain
segment examples and the calmer cross-check did most of it; the disfluent
monsters that burned 95–208s in run 9 now settle in ~10–20s. Remaining 8
failures: an over-splitting cluster (tasks precision stuck at 68% — the
chain examples overcorrected on colon/task lists), the two move cases
(root-caused AFTER the snapshot: the parser filed "from 9:30" as the
DESTINATION; move_time_fill now reads the spoken from/to and overrides the
model — lands in run 11), and one disfluent self-correction.

**The pilot against the verification dataset** (150 real HWU-64 utterances,
first slice of dummy_3000, scored by the dataset owner's own
count-correctness metric; the old rows are BEHAVIOR, not ground truth):

- shared-prompt count-correct: **old brain 70% · engine-v2 73%** —
  13 prompts flipped better, 8 worse, 97/32 unchanged pass/fail.
- by complexity (engine vs old-full-3000): simple 90% vs 92, medium 94% vs
  88, **complex 38% vs 29** — and by compound kind: event+event **47% vs
  20**, event+task **32% vs 17**, task+task 40%. The compound handling this
  dataset was built to expose (83% of old failures drop the EVENT) is
  where decompose-then-generate gains most. Cross-event date collapse: 0%.
- the 8 worse-flips are the triage queue
  (`DOCUMENTATION/experiments/engine_compare/triage.json`); several look
  like odd rows where the old brain "passed" by doing nothing ("remove
  'table' from furniture"). Triage verdicts (old right / new right / both
  wrong) are a human's or an independent judge's call, not the harness's.

Instruments now in place: the corpus audit (98% bar for merge) AND
`scripts/engine_dataset_compare.py` on real utterances. The full-3000
comparison remains a deliberate overnight run. Next tune: the
over-splitting cluster, then re-audit (run 11 also picks up the
from/to-aware move_time_fill).

### The memory-scaling answer, and what it means for the engine (2026-09-03, late)

The C-tier runs (owned by the dataset session; its collation is canonical)
answered row 76: external-pool retrieval at k=4 is FLAT across 60/300/1000/
3000 tiers (93/92/91/92% vs a 92% k=0 baseline) — no pool-size effect, no
"just having examples" effect — while the real 74-command history at k=4
reaches 95% on the held-out variant. **Personalisation does the work, not
example count.** Engine-side implication: the engine ships with
`nlu.memory_examples: 0` on run 7's "no measurable effect", but that was
measured before recall/precision existed and on the old brain; the C-tier
result says the REAL history specifically may be worth k=4. Queued: the
same A/B on the engine (`--memory --memory-k {0,4}` corpus runs) before
touching the default — the finding transfers only if the engine's LLM path
benefits the way the old one did.

### Runs 12–13 — the engine's memory A/B: personalisation does NOT transfer (2026-09-04)

Run 12 (k=0, with round 4's header fix): **95%** — same five failures as
run 11; the header fix's real mechanisms turned out to live elsewhere
(an unknown-parse on a bare task fragment, and a schedule-only "due
tomorrow" part), both fixed as round 5 and pinned by tests, to be
measured in the next run.

Run 13 (k=4 against a copy of the real history): **80%** — fixed 0,
broke 14 (recall 96%→78%, p50 5.7s→8.6s). The old brain gains +3 from
the same memory (its A-sweep, same day); the engine LOSES 15. The
mechanism fits the architecture change: the engine prompts the LLM
PER ITEM with short fragment texts, and whole-command multi-action
examples retrieved for a fragment teach it the wrong output shape —
retrieval noise the old whole-transcript prompting never saw. So
`nlu.memory_examples: 0` is now EVIDENCE-BACKED for the engine, not
inherited; if personalisation returns it must be per-item-shaped
(retrieve by item text, reformat examples as single-item parses) — a
designed experiment, not a default. This also retroactively explains
run 9 (98%→run 7's number) vs run 12: the engine was never getting the
old brain's +3, and doesn't need it to beat the old brain's live 92/95.
