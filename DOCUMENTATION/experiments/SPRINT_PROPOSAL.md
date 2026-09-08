# Three broad cycles — the research proposal

_2026-09-07. Gil: "spend 3 cycles where we can make unlimited changes in
implementation, since we are happy with the architecture — then narrow what
we focus on in future cycles."_

## Why a sprint rather than the usual one-hypothesis cycle

The normal loop changes ONE component per cycle so a delta has one cause.
That discipline is right when the system is close to its ceiling and we are
hunting points. It is the wrong tool right now, because today's measurement
work found several **large, independent, already-diagnosed** defects — each
with a reproduction and a board that can see it. Waiting eight cycles to fix
eight known bugs one at a time would be ceremony, not rigour.

**What does NOT relax during the sprint:**

- **The architecture is frozen.** Every item below is implementation:
  no new stage, no contract change, no reshaping `EngineState`, no change to
  who decides what. Anything that turns out to need one comes back to Gil.
- **A prediction is registered before each cycle**, naming the boards and the
  direction expected. Breadth is not licence to skip the honest comparison.
- **Every gate still binds**: sealed test halves stay unmined, the dual gate
  against real-usage data holds, negatives get banked.
- **The outer gate still outranks everything**: if the real-usage flag rate
  does not move, the sprint did not succeed, whatever the benchmarks say.

## Cycle A — the atomizer

**Why first: it is the ceiling on everything else.** FastRule is the
atomic-item executor; it can only be as good as the items it is handed. The
board measured **6.2% of compounds atomized correctly** on the test half and
**0.0% on the personas** (deterministic path).

**The diagnosis is not "the code is bad" — it is that segment's deterministic
tier looks for brackets, the coalescing wrapper and a configured separator,
which are artifacts the PHONE inserts, not features of speech.** On real
dictation it can never fire: 0 splits in 4,920 rows. It was built for batched
phone commands and nobody noticed, because there was no board.

Work:

1. **`coordination.has_clause_coordination` returns the BOUNDARY, not a
   boolean.** It already computes where the second clause begins and throws
   that away. The same signal reaches 87.9% compound recall in the atomicity
   model — we detect compounds well and use it only to DEFER, never to SPLIT.
2. **Segment gains a real deterministic tier**: split at a confident
   boundary; fall back to the LLM otherwise. Its under-split bias is
   preserved — an unconfident boundary does not split.
3. **Fix the four bugs the board found** (evidence in RESULTS): `_split_tasks`
   hard-codes `kind="task"` so a mixed command's event half is unreachable;
   the task splitter tears wrapper phrases into garbage titles ("Jordan to my
   to-do list"); a shared trailing deadline is lost from the first conjunct;
   `_TASK_RE` recognises no non-create todo verb, so update/delete/complete
   items are mis-kinded ~100% of the time — and `decompose` branches entirely
   on kind, so a mis-kind silently applies the wrong half of the stage.
4. **Relabel the np_decoy families** per Q14 (a list of things for one verb is
   one item PER THING; the never-split case is a list of PEOPLE or a shared
   object). Those over-splits were mislabels, not defects.
5. **Run the atomizer board's `--llm` lane** — never yet measured, because
   Ollama was busy with the sealed run. Nobody knows whether the deep path's
   real-usage failure is the prompt, the model, or the under-split guard.

**Boards:** `atomizer_board` (count-correct, over/under/mis-typed, boundary
integrity) on the FastRule test half AND the personas.

## Cycle B — speech that is not Gil's

**Why: the measured spread is enormous.** Atomic handle-rate 72.2% for the
persona who talks like the author vs **33.9%** for a terse student. The
ablation localises it exactly: swapping content nouns moves the classifiers
**0–3 pt**; swapping PHRASING moves them **7–29 pt**. The engine is tuned to
sentence shapes, not vocabulary.

**Mechanism, visible in the code:** every `OperationFeatures` verb signal is
`^`-anchored, so terse fragments and polite circumlocution fire ZERO non-bias
features and receive only the class prior — 48.6% of terse-student rows
against 6.2% for the control.

**Run it as a TWO-ARM COMPARISON (Gil, 2026-09-07): build both approaches
and let the data pick.** The choice between them was going to be my risk
judgment; measuring it is better, and both are implementation.

- **Arm 1 — TEACH the models the phrasings.** Split each verb class into
  `-initial` and `-anywhere` features so the model LEARNS what position is
  worth instead of it being hard-coded at "everything"; add signals that fire
  without a verb (noun-then-time, bare-NP, determiner opener) for "the exam
  12:30". Conservative: nothing the user said is altered.
- **Arm 2 — CANONICALISE in cleanup.** Rewrite unusual phrasings into one
  standard form before anything parses ("would you be kind enough to put the
  gym in for tomorrow at 7" → "add gym tomorrow at 7"; "gym tomorrow 7" →
  the same). Fixes every downstream component at once and every speaker at
  once. Aggressive: a rewrite that misreads a phrasing corrupts the command
  SILENTLY, and unlike a defer there is no second chance — the "set X as high
  priority" bug retitled a task to "high priority" exactly this way.

**How the comparison is judged:** both arms measured on the persona boards
(the spread is the point), the FastRule shape board, and the real-usage dual
gate. Watch specifically whether Arm 2 introduces NEW harm — a canonicaliser
failure shows up as a wrong action or a corrupted title, not as a defer, so
the harm line and the title-quality line matter more than handle-rate here.
They may also be COMPLEMENTARY (canonicalise the shapes that are safe,
teach the rest); the cycle decides that too, on evidence.
3. **The daypart defects, both of them.** (a) A daypart word ANYWHERE,
   including inside a title, overrides an explicit clock time — "book the
   coffee morning … at 7pm" → 08:00, live and user-visible. (b) `_CLOCKISH_RE`
   counts dayparts as clock times, which makes any remind-phrased errand with
   a daypart a calendar entry: **499 of 609 mis-kinds** on the test half.
4. **Re-fit and re-measure per persona**, reporting the SPREAD.

**Risk to watch, stated up front:** teaching the models to act on fragments
raises handle rate AND risk. If correctness drops on the persona boards,
that is a banked negative, not something to push through.

## Cycle C — what the user actually sees

**Why: these are the errors that reach the calendar.**

1. **Explicit times: 82.6% right** — one spoken time in six is wrong.
2. **Dates: 90.4% right** — one committed create in ten lands on the wrong day.
3. **35 destructive errors** on the test half (14 wrong `update_todo`, 14
   wrong `update_event`, 5 wrong `complete_todo`, 2 wrong `delete_event`).
   The harm metric exists now; these are the ones worth spending a cycle on,
   because a spurious row is an annoyance and an overwritten event is a loss.
4. **Half-executed compounds: 31** — the only non-atomic number that matters
   under Q13.

**Boards:** the FastRule shape board's slot and harm lines, plus the engine
board.

## The prerequisite that is not a cycle: the real-speech dataset

**The sealed benchmark reads 85%; Gil's real usage reads 50%** (20 commands,
flag rate 50%). The failures are rambling multi-event dictation with
transcript damage — "Walk Mark Stalk", "Moxdog", "Kupahre sheet" — a
distribution NO dataset we own contains. The memory database holds that
history, and the correction pairs are ground truth Gil already produced.

Without it the sprint optimises clean prompts and could leave the 50%
untouched while every board improves. **Recommendation: build it alongside
cycle A**, so cycles B and C can be judged against real speech as well as
generated speech.

## After the sprint

Narrow again to single-hypothesis cycles, aimed by whatever the sprint's
boards say is then the binding constraint — and by the real-usage flag rate,
which is the number that decides whether any of it mattered.

## Still on Gil's desk, deliberately not in the sprint

- **Should cleanup CANONICALISE phrasing** ("would you be kind enough to put
  the walk in for friday" → "add the walk on friday"), not merely remove
  noise? It would close the persona spread at its root and fits the rule that
  speech-specific handling belongs in cleanup — but rewrites destroy
  information, which is how the "high priority" retitle bug happened.
- ~~Should a daypart count as a clock time?~~ **RULED (Q15): NO.** "remind me
  to take the trash out tonight" is a task to do in the evening. The daypart
  belongs in the task's due time, not in the kind decision. Cycle B
  implements it.
