# DEVQA — async questions for Gil

Instead of interrupting with prompts, questions live here; answer inline
whenever (a one-liner under the question is enough). I may edit or withdraw a
question if the data resolves it first, and I keep the list SHORT on purpose —
if it ever grows past a handful, the newest ones can wait. Answered items move
to the log below so decisions stay findable.

## Open

**Q9 — Interrogative creates: does a question CREATE?** "should i add yoga
to my calendar?", "what if i booked town hall for the 3rd?" — the FastRule
dataset's ground truth labels these CREATE (the speaker is taken to want
it); the engine's F3 gate deliberately treats questions as not-commits and
defers to deep, where the LLM decides case by case. The two policies
disagree, and the answer defines both the gate's target behavior and what
the labels mean. (Already ruled and NOT in question: polite imperatives —
"can you add X" — are creates, F4a.)
  **(a) Questions create** — fast path commits them like any create; snappy,
  matches the dataset labels; risk: a genuinely deliberative "should I…?"
  books something the speaker was only weighing.
  **(b) Questions never auto-create** (my recommendation) — a question is
  not consent to mutate; deep answers or asks back ("Want me to add it?"),
  the reply makes one-tap-create easy. Cost: these rows become deliberate
  non-creates, so the dataset's ~8 interrogative families get relabeled to
  match the ruling (labels follow product, as with the conventions layer).
  **(c) Split by shape** — "should i / what if" = ask-back (b), "why don't
  we / let's…?" = create; most precise, most rules to maintain.


**Q6 — Reminders for events INSIDE Shabbat/yom tov (e.g. Shabbat lunch):
suppress entirely (shipped default) or roll into one pre-candle-lighting
digest banner?** Lifestyle call, not engineering.

## Answered (log)

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
