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

- **BUG (open; found 2026-09-06 by the query-no-mutation check): queries can
  emit mutations.** "Is my appointment to the dentist still on for tomorrow
  morning?" → deep produced `update_event(match_title="dentist")` — a
  question that MOVES the appointment on a real calendar. Present in every
  archived run (14 hits on the full-3000 sweep). Deterministic guard: an
  interrogative with no imperative verb must not generate
  delete_*/update_*/complete_* actions. Bugs are exempt from
  one-change-per-cycle; fix when the engine tree is next idle.


0. ✅ **Resolved (Gil, 2026-09-05) — frozen replay clock + observance flag.**
   Better than pinning to an arbitrary Tuesday: each row now replays AT ITS
   RECORDED TIMESTAMP (the dataset is a history), and Shabbat gating stands
   down in tests via the user flag `observance.enabled` /
   MACALENDAR_OBSERVANCE=0. **Measurement epoch reset**: results from
   2026-09-05 onward are not comparable to earlier rows in loop_log.csv — the
   re-baseline run marks the boundary.

1. ✅ **C3 — fast-path compound gate** (generate `fast_propose`, @ ce0c9b3).
   Actual: task+task 35 → 55 (+20), e+e 59 → 63, overall +0.8; fast-path
   correctness rose to 79% with the mangles gone. Graduated. Learning for the
   queue: dips elsewhere diffed as replay nondeterminism — overall deltas
   under ~1.5 pt on dev-fast are noise; judge cycles by their targeted slice.

2. ⚖️ **C5 — grounded default-title events** (generate `event_fallback`,
   @ b3c6656, run 10). Actual: +0.8 raw / +0.8 adj — under the noise floor;
   evidence rows were partly stale (already passing under the new epoch).
   KEPT (honest, deterministic, pinned) but not claimed. Byproducts for the
   queue: (a) loose groundings ("in the future", "the following event")
   create default events → direct evidence for #5's invention guard;
   (b) "set reminder at 3 pm" fails on the FAST path — a rule-parser gap,
   new entry below. Process lesson: re-verify evidence rows against the
   current epoch before taking an entry.

2b. ✅ **C6 — generic-target veto** (fast gate, @ 13edcce, run 11). A
   confident fast MUTATION whose match_title is a bare ask-noun routes deep.
   Targeted row flipped as designed, zero veto regressions, fast held 79%;
   headline −0.8 = garble-row flicker (noise). Graduated.

3. ✅ **C4 — cue iteration** (segment, @ f1c8d9d). notify + festival +
   "calendar invite". Actual: e+t 41 → 46 (top of band; the calendar-invite
   row creates a real brunch event), e+e 63 → 67, complex 51 → 54; headline
   flat (one t+t noise give-back). Festival residual accepted as a semantic
   boundary (standing-alert reads as a query). Graduated.

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

6. ✅ **Resolved (Gil, 2026-09-05): NO** — lists stay Today/General + tags,
   no separate lists by voice. The "create a new list" dataset rows are
   accepted convention losses, permanently. (Informs #4: "update the workout
   list with new items" should read as create-todos-with-tag, not a new list.)

7. **[DEVQA Q1] dated "I need to <meet/talk>…" ⇒ event** — convention edge,
   parked in DEVQA.md for Gil's inline answer. One row on this slice.

## Standing process items (not hypotheses)

- **Dev-full confirm** (`--limit 0 --max-rank 600`): after every couple of
  graduated wins, to confirm off the tuning slice.
- **Merge the loop branch into `main` every few graduated cycles** (Gil,
  2026-09-05). First merge done @ a425ca2.
- **Questions go to DEVQA.md**, never blocking prompts (Gil, 2026-09-05).
- **Diminishing returns → upsize** (Gil): when dev-fast cycles stop moving
  their targeted slices (two cycles < ~2 rows), the working slice becomes
  dev-full, with held-out for milestones.
- **Held-out check** (sealed): only at a milestone, never mined.
- **Re-rank this file** after every verification rerun; prune on every third.
