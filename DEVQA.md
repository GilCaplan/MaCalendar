# DEVQA — async questions for Gil

Instead of interrupting with prompts, questions live here; answer inline
whenever (a one-liner under the question is enough). I may edit or withdraw a
question if the data resolves it first, and I keep the list SHORT on purpose —
if it ever grows past a handful, the newest ones can wait. Answered items move
to the log below so decisions stay findable.

## Open

**Q16 — Does a trailing deadline scope over every task, or only the last
one?** (2026-09-08, from cycle A's diagnosis.) "submit the grades and prepare
the slides **by friday**" — is friday the deadline for both, or only for the
slides? English supports both readings, and this project's standing convention
is to pick one and apply it everywhere rather than guess per sentence (the same
call already made for "until" vs "through").

**Why I am asking instead of measuring.** I looked, and the data cannot decide
it: **0 of 10,920 corpus rows have the explicit-marker shape**, and the nearest
attested shape has self-contradictory gold — 45 train rows attach the trailing
date to ask 1, 15 attach it to ask 2, and none attach it to both. So any rule I
picked would be my preference wearing a measurement's clothes.

**Why it matters now.** Segment's clause tier deliberately shares only a date
the utterance OPENS with, never a trailing one, because a repeated relative
date silently overwriting real dates was a shipped bug (a987aba). That
asymmetry is currently a safety choice, not a ruling — and a wrong due date is
user-visible harm in both directions: sharing invents a deadline nobody gave,
not sharing drops one they did.

My recommendation, if you want one: **share it for TASKS with an explicit
marker ("by friday", "before monday"), not for events, and not for a bare
trailing date.** A deadline marker scopes naturally over a list; an event's
date does not. But this is your call, and I will implement whichever way you
say — including "leave it alone", which is the current behaviour and costs
nothing measurable today.


**Q13 — Is a fast commit on a compound a violation when it produces exactly
the right records?** (F16, 2026-09-07.) `fastrule_shape` scores ANY commit
on a non-atomic row as a routing violation. On B-test 129 such commits
exist and **103 of them produce the right events/tasks** — the rule parser
read both asks and executed both. Deferring all of them lifts the
non-atomic defer rate 77.1 → **95.6%** and cuts violations to 25, but (a)
throws away 96 complete correct answers into a ~35 s deep pass, and (b)
**loses them entirely when Ollama is down** — measured: "book gym on
tuesday at 7am and remind me to buy milk" produces NOTHING on the deep
track with the LLM unreachable, where fast produced both records. Shipped
for now: layer 0 reports "compound" honestly (its board is what improved),
and routing commits anyway when the parse covers every ask
(`_parse_covers_the_compound`, gated on intent-count ≥ ask-joiners + 1).
**Question: is that carve-out right, or is "FastRule never commits a
compound, full stop" the ruling?** If the latter, delete the function —
one line — and the shape board jumps, at the cost above.

**Q11 — [DESIGN] FastRule v2 restructure** (Gil proposed 2026-09-07; the
draft is `DOCUMENTATION/FASTRULE2_DESIGN.md`): five single-responsibility
components (Normalizer=lexical-only / Router=the Q10 two-subsystem center /
SlotFiller=specs-as-data / Scorer=named signals / Gatekeeper=the gates),
semantic rewrites retired, models kept at the F12 state, parallel build +
diff-gated switch. Three sub-questions at the doc's end (identical-first
port?; calibration before or after?; slot-spec extensions in or out?).


**Q6 — Reminders for events INSIDE Shabbat/yom tov (e.g. Shabbat lunch):
suppress entirely (shipped default) or roll into one pre-candle-lighting
digest banner?** Lifestyle call, not engineering.

## Answered (log)

- 2026-09-07 — **Q9 (interrogative creates)**: "should i add yoga to my
  calendar tomorrow?" must neither auto-create nor be silently dropped — pop a
  confirmation showing the parsed proposal; YES creates it, NO discards it and
  the memory record marks it declined. → *Implemented:* the confirm-create
  gate (`parse: "confirm_create"` + `proposal`, `POST /voice/confirm`, Mac
  Add/No box, iOS alert) — FEATURES.md and ENGINE.md carry the detail.

- 2026-09-06 — **Q2 shipped without needing an answer**: the observance
  checkbox is in the Mac settings dialog (243d99f), persisted via
  config_store — and building it exposed that `observance.enabled` was
  silently DROPPED by pydantic (`ObservanceConfig` never declared the
  field), so the yaml flag never reached `is_enabled()`; only the env
  override worked. Field declared + pinned by test.
- 2026-09-06 — **Q3 withdrawn** (API key): the model sims ran through Claude
  Code subagent workers, no key needed; the experiment is closed on partial
  data (llama beat both drop-ins — `dataset/MODEL_COMPARISON.md`).
- 2026-09-05 — **Old-brain comparison**: Gil doesn't care about it; the
  questions that matter are "is the new system better, and can it get
  better?" → answered in chat (yes / yes); vs-old numbers stay incidental.
- 2026-09-05 — **Invention vs missing**: balance both, F1-style. →
  *Implemented:* item-level micro precision/recall/F1 in the harness
  (`_prf`), reported per run + by complexity + untuned sub-slice.
- 2026-09-05 — **Overfitting the subset**: authorized to resample a fresh
  same-size slice and mark it in the log. → Standing policy in the protocol.

- 2026-09-05 — **Shabbat gating in tests**: turn off via a user-controllable
  flag; replays must simulate each row's recorded timestamp. → *Implemented:*
  `observance.enabled` + `MACALENDAR_OBSERVANCE` env override standing down
  both gates; the harness freezes each replay at the row's `ts` (freezegun).
- 2026-09-05 — **Separate task lists**: no — lists stay Today/General plus
  tags. → Queue #6 closed; "create a new list" dataset rows are accepted
  convention losses.
- 2026-09-05 — **Merging**: fold the loop branch into `main` every few
  graduated cycles. → Standing policy in ITERATION_PROTOCOL.md; first merge
  done (@ a425ca2).
- 2026-09-04 — **Date-only occasion reminders**: calendar events. → Cycle 2.

## Answered log

**Q15 (2026-09-07, Gil): a DAYPART IS NOT A CLOCK TIME.** "remind me to take
the trash out tonight" is **a task to do in the evening**, not a calendar
event. The pinned reminder convention turns on a real clock time ("remind me
about the dentist tomorrow AT 9AM" = event; "remind me TO <verb>" = task),
but `segment._CLOCKISH_RE` lists `tonight|morning|evening|afternoon`
alongside actual times, so any remind-phrased errand with a vague daypart
became a calendar entry. A daypart is a rough WHEN — it belongs in the
task's due time, not in the decision of what kind of thing this is. This is
the single largest mis-kind driver: **499 of 609** on the FastRule test half,
383 of 418 on the personas. Fixed in sprint cycle B.

**Q14 (2026-09-07, Gil): "buy apples and eggs" is TWO tasks** — same action,
separate items ("buy eggs", "buy apples"). This settles a contradiction the
atomizer board found between our own documents: `decompose.py` and
`list_split.py` split shopping lists; `dataset/fastrule/DATASET.md` labelled
them one task titled "apples and eggs". The CODE was right. Every over-split
in the FastRule test half was this disagreement and nothing else — so those
were never defects. **The dataset's np_decoy families need relabelling**
(a list of things for one verb = one item PER THING); the genuine
never-split case is a list of PEOPLE or a shared object ("meeting with Tal
and Sam", "wash and fold the laundry").

**Q13 (2026-09-07, Gil): non-atomic behaviour is DIAGNOSTIC, not a target.**
"I just want to see that it succeeds on recognising and executing well on
atomic items, and we can decide what to do with non-atomic which is run
through anyway and pass that to the next stage and let the engine decide."
So: the PRIMARY metrics are atomic handle-rate and correct-on-handled;
FastRule's atomicity call is information handed upward (the REFUSAL /
STRUCTURE / INCAPACITY contract), not a verdict it must get right alone.
The non-atomic bucket is reported as three outcomes — covered (acceptable,
and the only path that survives the LLM being down), half-executed (the real
defect), deferred — with no single "violation" number. `_parse_covers_the_
compound` stays.

**Q12 (2026-09-07, Gil design ruling): the retry loop must CHANGE the input,
and the LLM is the last resort.** Two parts. (a) **Determinism rule:** when
the crosscheck loop-back re-enters an atomic item, FastRule must not be
asked the same question twice — identical text gives an identical verdict by
construction, so a re-run on unchanged text is wasted work. On re-entry,
either the item's text differs from the attempt that failed (the LLM stages
rewrote it) or FastRule is SKIPPED for that item. (b) **Escalation rule:**
after the retry budget (3) is spent on an atomic item, the final attempt
belongs to the LLM — it creates the event/task directly rather than
deferring to a deterministic parser that has already failed on that exact
text. Implementation: per-item attempt fingerprints on EngineState;
generate consults them before calling FastRule. Deferred until the in-flight
sealed run finishes (engine files are read-only during a measurement).

**Q10 (2026-09-07, Gil design ruling): Stage-2 routing becomes TWO tiered
subsystems.** (1) KIND — event vs task; (2) OPERATION — new/edit/remove/
complete/query. Each is rules-first (regex/tables/pinned conventions answer
when confident — trivial cases stay trivial and Gil's rulings stay
sovereign) with a small logistic-regression model as the fallthrough when
rules aren't confident. Action = kind × operation, composed. K1 is the KIND
subsystem's model (proven 99.0/98.5); K3 is the OPERATION subsystem's model
(labels free in dataset B). A rules-vs-model disagreement is an abstain
signal. Implemented in the lane (F-batches), integrated at F15.

**Q9 (2026-09-07): interrogative creates → CONFIRM PROMPT.** "should i add
yoga…?" neither auto-creates nor gets silently dropped: the client pops a
box with the parsed proposal — yes creates it, no discards it. Same
response-contract pattern as the transcript-edit gate (`needs_edit` +
`supports_edit`): the server sends a proposal payload only to clients that
declare `supports_confirm`; older clients keep today's behavior (deep
decides). Dataset's interrogative families relabel to expect a PROPOSAL,
not a create — labels follow product.

**Q8 (2026-09-07): APPROVED — "can try the q8 idea."** A small logistic
regression over hand features for the event-vs-task kind decision, fit
offline on dev labels, deterministic at inference. Ships only if it beats
the regex family in a measured cycle; negative result gets banked too.

**Q7 (2026-09-06): object-based restructure APPROVED — with the acceptance
criterion in Gil's words: "the logic doesn't change at all nor should the
results, should just be cleaner." All three recommendations confirmed:
(1) pure refactor first, cycle 10 separate; (2) `run_transcript` stays as a
shim; (3) shared Component interface. Verification bar: full test suite
green + a behavior-identical confirmation run against the era-2 baseline
before merge.**

**Q1 (2026-09-06): dated "I need to <meet/talk>…" = EVENT.** Implemented same
day: `_NEED_ENCOUNTER_RE` in segment's pinned-kind rules (encounter verbs +
date/clock ⇒ event; errands and undated encounters unchanged) + unit tests.

**Q4 (2026-09-06): Mac reminders with the calendar closed = a notification-
settings OPTION.** Queued in TASKS (app stream): settings toggle first, the
LaunchAgent detach ships behind it, default off.

**Q5 (2026-09-06): default lead time = PER CATEGORY.** Matches the built
mechanism (`resolve_lead`: event override → category lead/mute → fallback);
the per-category leads in notification settings are the primary surface.

**Q6 (2026-09-06): events inside Shabbat/yom tov get NO reminders.** The
shipped suppress-entirely default is confirmed; no digest.
