# Results log

Every meaningful run, newest first. **Always: metric + slice + the commit that
produced it.** Baselines are replayed, not frozen — cite the score report and
md5, not "the dataset".

## Dev-full confirm of C3+C4 — the day's milestone (2026-09-04, @ f1c8d9d)

Count-correctness, dev-full 600 (6049 s): **78.0%** — +2.0 from C3+C4 off the
tuning slice, **+3.8 total for the day** vs the 74.2 pre-loop reference; old
brain 71% on the same rows. task+task generalises at +10 (47 → 57), complex
45 → 51, garbage titles 0%. All four cycles hold off-slice. Two rows took an
'error' parse path — to be glanced at next session. **Loop paused at this
milestone**: after midnight the replay clock is *Saturday* (a new variant of
the observance clash), so further measurement waits on the date-pinning
decision (queue #0).

## Cycle 4 — data-driven cue iteration (2026-09-04, base @ ce0c9b3)

**Hypothesis (queue #3):** three additions to segment's kind enforcement, each
justified by a live failing row, none speculative: (a) `notify` joins the
remind-cues — "notify me about any festival occurring next month" (0 events);
(b) `festival` joins the occasion-nouns (same row); (c) the unambiguous phrase
"calendar invite" ⇒ event on its own — "Will you send a calendar invite …
for brunch at 11 am on Tuesday" (0 events; no remind-word, so C1/C2 never
fire). **Expected:** event+task +2 rows (41 → ~46%); overall +~1 pt — at the
stated noise floor, so the verdict will be read on the targeted rows
themselves (do those two rows now pass?), not the headline. Everything else
flat. Watch: "notify" over-firing on non-calendar notifications.

**Actual (rerun @ f1c8d9d, 2373 s):** judged on the targets per the noise-floor
rule — **event+task 41 → 46%** (top of the predicted band ✓; the
calendar-invite row now creates *'Brunch with James and Alice', Tue 11 AM* —
exactly right), **event+event 63 → 67%** (+4 bonus: the cues catch e+e halves
too), complex 51 → **54**. Headline flat at 77.6 (task+task returned one
noise-class row, 55 → 50). The festival row's residual is a **semantic
boundary**, not a bug: the kind flip works, but generate reads "notify me
about any festival occurring next month" as a *schedule query* — a
standing-alert concept the product doesn't have — and the event-kind retry
rightly accepts queries as calendar-consistent. Accepted as a convention loss.
**Verdict: graduated.** Next measurement: dev-full confirm of C3+C4.

## Cycle 3 — the fast-path compound gate (2026-09-04, base @ 8a3e127)

**Hypothesis (queue #1):** the fast path confidently swallows compounds — every
observed mangle ("…at noon. **Also,** Please remind…", "…at 9am, **and then**
Remind me…" → a todo literally titled "then") is a **single-intent** parse of
text carrying a **strong joiner**. Gate `fast_propose`: when the text has a
strong compound joiner (". Also,", ", and then", " — and", "and also", a
sentence break + joiner) AND the confident parse read only ONE request, refuse
the instant commit and take the deep track (deep 81% vs fast 71% on dev-fast).
Weak joiners (a plain "and") never gate — "meeting with Tal and Ravid" stays
fast. **Expected:** overall +1–2 pt (→ ~78–79%); e+t +2–5, e+e +2–4, t+t +0–5
(tempered: deep still misreads some garbly halves); fast share drops ~5–8 rows
and those commands go instant → 10–30 s (accepted correctness trade). Watch:
any legit fast command slowed, and the fast/deep mix in the report.

**Actual (rerun @ ce0c9b3, 2365 s):** overall 76.8 → **77.6%** (+0.8, just
under the +1–2 band). The slices tell the real story: **task+task 35 → 55%
(+20 — far above the tempered +0–5)**: the gated ", and then" task compounds
went deep and split properly. event+event 59 → **63%** (top of band ✓).
complex 46 → **51**. Fast share 115 → 103 (−12, a little more than predicted);
fast-path correctness *rose* to 79% (the mangles left it). event+task 43 → 41
and simple 92 → 90 read as **regressions but diff as noise**: the flipped rows
("Remind me at the 15th of every month and pUT MILK…") involve no gate marker —
pure replay nondeterminism (the LLM is ~75% deterministic run-to-run).
**Noise floor made explicit:** on dev-fast a handful of rows flip between
identical-code runs, so overall deltas under ~1.5 pt are not signal; targeted
slice moves like +20 are. One real loss: "Open me a new list — and please add
milk…" was *accidentally passing* fast and now lands on the create-list
capability gap (queue #6 [Gil] gains a data point). **Verdict: graduated** —
targeted slices clearly up, the dips are noise-class, and the mangle class is
gone from the fast path. Next: queue #2, grounded default-title events.

## Dev-full confirm of C1+C2 (2026-09-04, @ 8a3e127)

Count-correctness, dev-full ranks 1–600 (5405 s): **76.0%** vs the pre-loop
dev-full reference 74.2% — **+1.8 pt on rows the loop never tuned against** —
and vs the old brain's 71% on the same slice. Slices: simple 90 / medium 89 /
complex 45; e+e 53, t+t 47, e+t 38; garbage titles 0%. Caveat: the pre-loop
reference ran on a different weekday, and the Friday/Shabbat replay clash
(cycle-2 finding) makes cross-day deltas approximate. **C1+C2 fully
graduated.** Next per the queue: the fast-path compound gate.

## Cycle 2 — the date-only occasion reminder (2026-09-04, base @ e956763)

**Reading (from cycle-1-fix failures):** 6 of 8 listed event+event failures and
several event+task ones hinge on one form — a reminder **about/of/for an
occasion-noun with a date but no clock time** ("set a reminder for my meeting
today", "remind me of my meeting tomorrow", "the get-together on Sunday").
Product convention decided by Gil (2026-09-04): **occasion-nouns → event** —
the about/of/for-noun form with any date reference becomes a calendar event;
"remind me to \<verb\> …" stays a task (clock time still flips it, per cycle 1).
Also flagged, not chased this cycle: the deep path *invented* a full event
("New Event", conference room, 10:00) from garbled text — an invention/precision
failure the count metric barely sees; and task+task's remaining failures are
mostly capability/convention gaps ("create a new list", contentless "give an
entry to this list") — low clean upside.

**Hypothesis (cycle 2):** extending segment's `_enforce_pinned_kinds` — flip an
LLM "task" label to "event" when the text is remind-ish, NOT the "remind me to
\<verb\>" form, and has an occasion-noun plus a date reference — will fix ~3 of
12 event+event failures and ~1–2 event+task ones. **Expected:** event+event
56% → ~63–67%, event+task 41% → ~44–46%, overall +1.5–2 pt (→ ~77.5–78%);
task+task flat; simple/medium flat-to-slightly-up (single date-only occasion
reminders also flip, and their provenance is calendar). Watch for: a
wanted-task row flipping to event (over-reach of the occasion list), and
invented default times on the new events.

**Actual (rerun @ 8a3e127, 2087 s):** direction confirmed on every slice,
magnitude under prediction — overall 75.6 → **76.8%** (+1.2 vs +1.5–2
predicted); event+event 56 → **59%** (predicted 63–67); event+task 41 →
**43%**; task+task 35 flat ✓; simple 91 → 92, medium flat ✓; complex 44 → 46;
deep path 79 → 81%. The flip itself works ("set a reminder for my meeting
today" → `create_event`, sensible 10:00 default). The shortfall decomposes
into three understood causes:
1. **Novel — the replay-date/observance clash:** today's replays run on a
   *Friday*, so every "tomorrow" event lands on Shabbat and the observance
   gate **correctly refuses** it ("I didn't book 'meeting': that lands on
   Shabbat") — the product is right, the dataset doesn't model Shabbat.
   Cycle 1–2 gains are *understated* on Friday runs, and runs replayed on
   different weekdays are not strictly comparable. Today's runs are all
   Friday-consistent, so within-day deltas hold.
2. Garble first-halves ("Mark reminder with these people" → `complete_todo`
   misread) keep their rows failing even when the fixed half now works — as
   predicted.
3. The fast path mangled a two-reminder compound into todos titled
   "meet james at work tomorrow at 9am" and literally **"then"** — queue #1's
   evidence grows.
**Verdict: graduated** (targeted slices clearly up, nothing down); dev-full
confirm of C1+C2 next. Queue re-ranked: replay-date pinning added as a
measurement-correctness item [Gil to confirm].

## Cycle 1 — dev-fast(250) baseline + hypothesis (2026-09-04, code @ 2588612)

**Measurement** (metric: count-correctness; slice: dev-fast ranks 1–250;
report `engine_compare/engine_run.score.md`, wall-clock 4882 s ≈ 81 min with
the app stack up):

- overall: engine **73.2%** vs old brain 67.2% (29 flipped better / 14 worse)
- by complexity: simple 89% · medium 91% · **complex 40%** (the frontier)
- by compound kind: event+event **52%** (n=27) · task+task **35%** (n=20) ·
  event+task **35%** (n=37)
- event+task missing half: **event missing 20** · task missing 4 · both present 13
- parse path: deep 76% · fast 70% · garbage titles 1%

**Interpretation** (from `actions_json` of the failing rows — the event half is
rarely *dropped*; it is created as the wrong kind, or held back):

- **(A) dominant: reminder-phrased event halves become todos, even with clock
  times.** "create a birthday wish reminder for tomorrow **at 10 AM**",
  "remind me to go to my doctors **at 4pm**", "my meeting **at 3pm**" — all
  `create_todo`. The pinned product rule (remind + clock time ⇒ event) is
  implemented in segment's deterministic `_kind_of`, but the LLM's kind label
  wins on the deep path and is never corrected — so generate's own
  event-kind-retry safety net (which exists and works) never fires, because the
  item arrives labeled "task".
- (B) smaller: vague event halves ("Set a event for the evening", "pencil me in
  for sarahs birthday thing") parse to unknown and are held back honestly.
- (C) a slice of "failures" are convention clashes: "remind me to \<verb\> +
  date-only" is a task-with-due-date by product design but an event in the
  dataset's ground truth. Consciously NOT chased — the product rule stands.
- Also seen: the fast path mangling a compound outright ("Remind me to read
  book next week — and…" → three garbage todos) — a separate pile for a later
  cycle.

**Hypothesis (cycle 1):** making the deep path obey the *existing* pinned rule
— override an LLM "task" label to "event" when the text has remind/reminder
phrasing AND a clock time (`segment.py` internals only; contracts frozen; it
makes the LLM path agree with `_kind_of`'s deterministic path, no new
convention) — will let generate's event-retry engage for those items.
**Expected:** event+event 52% → ~58–60%, event+task 35% → ~40%, overall
dev-fast +1–2 pt; simple/medium and task+task flat (the override touches only
remind+clock-time items). Modest by design: one narrow, attributable change.

**Actual (rerun @ e956763, 2265 s):** overall 73.2 → **76.0%** (+2.8 — above
the predicted +1–2); event+task 35 → **41%** (predicted ~40 — on the nose);
event+event 52 → **56%** (predicted ~58–60 — right direction, slightly under:
two of its failures are the `update_todo`-misread and no-remind-word forms the
narrow rule deliberately skips); task+task 35 → 35 flat ✓; simple 89 → 91 and
medium 91 → 92 — a small **unexpected** gain: the rule also catches
single-command timed reminders the LLM mislabels on the deep path, not only
compound halves. complex 40 → 44. event-missing halves 20 → 18. Also novel:
p50 latency 9.5 s → 5.7 s, p95 74 s → 31 s (plausibly less unknown/retry
churn now the event-kind retry succeeds; possibly partly warmer caches — not
claimed as a fix effect). **Verdict: confirmed → graduated; the dev-full
confirm will be batched with the next cycle's win. Next pile: task+task 35%
(n=20), untouched by this fix as predicted.**

## Baseline — old brain on the full 3000 (verified 2026-09-04 20:56)

- **count-correct 70%** overall — `baseline/dummy_3000.db`
  (md5 `2511537fb93c32d28b87fe1998f77275`), report `dummy_3000.score.md`.
- Caveats (per the dataset owner): the db is not bit-reproducible (~75%
  determinism on regen); one row (tier_rank 2022, "Open calendar. Set event.")
  was replayed post-build and parses differently — negligible for aggregates.
- Frozen inputs: `inputs/history_3000.json`, `inputs/hwu64_sample.json`.

## engine-v2 vs baseline — count-correctness (metric #1)

| run | code @ | slice | old | engine | note |
|---|---|---|---|---|---|
| full-3000 | (round 5) | overall | 70.0% | **74.0%** | 252 better / 135 worse |
| full-3000 | (round 5) | held-out 601–3000 (n=2400, sealed) | 69.5% | **73.5%** | +4.0, generalises |
| full-3000 | (round 5) | complex | 29% | **39%** | the frontier |
| full-3000 | (round 5) | event+event | 20% | **36%** | decompose gain |
| full-3000 | (round 5) | event+task | 17% | **35%** | decompose gain |
| dev-full 600 | (cycles 2–3) | overall | 71% | 74.2% | invention guards — flat on this metric (they fix precision, not count) |

Other metrics on the full-3000 engine run: garbage titles ≤1%, cross-event
date collapse ≤2%, missing-half = the *event* dropped in 72% of event+task
failures, parse-path fast 76% / deep 71%.

## Reading note

The invention-guard cycles (remove-echo, question-creates-nothing, quote-shed)
did not move count-correctness — they fix *invention* (precision), which this
metric barely sees. Right fix, wrong ruler: a precision-class change needs a
precision metric. This is why every entry names its metric.
