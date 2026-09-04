# Hypothesis queue — ranked, so cycles roll out fast

The planned experiments, best first. Each entry: the hypothesis, the ONE stage
it touches, the evidence it came from, the expected effect (metric + slice),
and effort/risk. A cycle takes the top unblocked entry, moves it to *In
flight*, and on verification the result goes to `RESULTS.md` + `loop_log.csv`
and the queue is **re-ranked** — fresh failures usually add entries.
**Re-rank and prune every ~3 cycles**; an entry that survives three re-ranks
untouched is probably not worth its slot.

Ranking = expected count-correct gain on dev-fast × confidence ÷ (effort +
risk). Product-convention questions are Gil's, never assumed — an entry
needing one is marked **[Gil]** and is blocked until asked.

## Done / in flight

- ✅ **C1 — remind + clock-time ⇒ event over LLM labels** (segment).
  73.2 → 76.0 overall; e+t 35 → 41. Predicted ~40 — on the nose.
- ✅ **C2 — dated occasion reminder ⇒ event** (segment; Gil's convention call
  2026-09-04). Actual @ 8a3e127: overall 76.8 (+1.2, predicted +1.5–2), e+e 59
  (predicted 63–67), e+t 43. Direction right everywhere; shortfall decomposed
  (see RESULTS.md): Friday-replay observance clash + garble halves + fast-path
  mangle. Graduated.

## The queue

0. **[Gil] Replay-date pinning** — harness (`engine_dataset_compare`), not the
   engine. *Evidence (cycle 2):* replays use the real clock, so a Friday run
   makes every "tomorrow" event land on Shabbat and the observance gate
   correctly refuses it — the dataset doesn't model Shabbat, so the engine is
   penalised for being right, gains are understated, and runs replayed on
   different weekdays are not comparable. *Proposal:* pin the replay clock to
   a fixed mid-week date (e.g. a Tuesday) inside the compare harness only;
   re-baseline dev-fast once after. Measurement correctness, zero engine risk —
   but it resets comparability, so it is Gil's call when.

1. **Fast-path compound gate** — stage: generate (`fast_propose`).
   *Evidence:* the fast path mangles compounds it confidently commits:
   "Remind me to read book next week — and can you add Gloria…" → three
   garbage todos; "…at noon. **Also**, Please remind to get donuts…" swallowed
   into one title; cycle 2 added a todo titled literally **"then"** from
   "…at 9am, and then Remind me of my meeting tomorrow". Fast 71% vs deep 81%.
   *Hypothesis:* when the rule parse is single-intent but the text carries a
   strong compound marker (" — and ", ". Also, ", "and then", ; with clauses),
   refuse the fast commit and take the deep track.
   *Expected:* +1.5–2.5 pt overall (several e+t/e+e/t+t rows move to the
   deeper, better path); garbage titles down. *Effort:* low. *Risk:* latency —
   more commands go deep (~10–30 s); watch the fast/deep mix.

2. **Grounded default-title events** — stage: generate (event twin of the
   existing `task_fallback`).
   *Evidence:* explicit asks that name no title die as unknown: "Set a event
   for the evening" (0 created), "please set event on Tuesday", "Set reminder
   for three o'clock" (simple row, 0/0). The event-kind retry fires and still
   gets nothing. *(Scope note after C2: items the occasion rule flips DO get
   sensible LLM defaults — "my meeting today" → 10:00 event — so this entry is
   only the title-less/unknown remainder.)*
   *Hypothesis:* an event-kind item whose text literally asks to set an
   event/reminder AND names a when (date or time) but no title becomes a
   default-titled event ("Event", time from the words) instead of unknown.
   *Expected:* +1–1.5 pt (3–4 rows across simple + compounds). *Effort:* low.
   *Risk:* invention-adjacent — the title default must be grounded ("event"
   is in the words); never invent a time that isn't there.

3. **C2 rule iteration** — stage: segment (extend `_OCCASION_RE`/`_DATED_RE`).
   *Evidence:* forms C2 knowingly misses: "Remind me at the 15th that we are
   going to comic con" (no occasion-noun match), "I need to have a
   conversation with Greg on Monday the 20th" ("conversation" not in the
   noun list; "i need to" form).
   *Hypothesis:* after C2's rerun, add the misses its failures actually show
   (data-driven nouns/date forms, never speculative ones).
   *Expected:* +0.5–1 pt, cheap increments. *Effort:* trivial. *Risk:* noun
   list creep — each addition needs a failing row as its justification.

4. **List-op misreads** — stage: generate (or rule-parser mapping).
   *Evidence:* "update work out list with new items" → `update_todo` (found
   nothing); "Give an entry to this list" → `query_todos`. Dataset wants
   creates.
   *Expected:* +0.5–1 pt on task+task. *Effort:* medium. *Risk:* fuzzy —
   "update X with new items" as create is defensible; "give an entry" has no
   content to create (clarify may be the honest answer). Partial [Gil].

5. **Garble→invention guard** — stage: validate.
   *Evidence:* "new scenario, time or calendar to new list…" produced a
   fabricated "New Event", conference room, 10:00–11:00 — fields not in the
   words. **A precision failure count-correctness barely sees** (it even
   *helped* the count).
   *Hypothesis:* an AI-created event whose title AND fields aren't grounded in
   the transcript is held back with the honest message.
   *Expected on count-correct:* ~0, possibly −0.5 pt. **Queued for product
   value, not this metric** — pair with a precision/invention measure when we
   define one. *Effort:* medium. *Risk:* over-blocking legitimate defaults
   (interacts with #2 — do #2 first, then this guard can key off its
   grounding rule).

6. **[Gil] "create a new list X" as a voice action** — capability, not a bug.
   *Evidence:* task+task 35% is mostly "Create a new list… Also, Start
   creating a new list" forms; the product has no create-list action, so one
   generic todo appears. Blocked on: should voice create task lists at all?
   *Expected if yes:* +1–1.5 pt on task+task. Until asked: accepted losses.

7. **[Gil] dated "I need to <meet/talk>…" ⇒ event** — convention edge.
   "on Monday, the 20th, I need to have a conversation with Greg" — dated
   meeting-ish i-need-to. Today: task. Dataset: event. One row on this slice —
   ask only if #3's rerun shows more of the form.

## Standing process items (not hypotheses)

- **Dev-full confirm** (`--limit 0 --max-rank 600`, ~1½–3¼ h): run after the
  next graduated win to confirm C1+C2 together off the tuning slice.
- **Held-out check** (sealed): only at a milestone, never mined.
- **Re-rank this file** after every verification rerun; prune on every third.
