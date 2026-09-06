# DEVQA — async questions for Gil

Instead of interrupting with prompts, questions live here; answer inline
whenever (a one-liner under the question is enough). I may edit or withdraw a
question if the data resolves it first, and I keep the list SHORT on purpose —
if it ever grows past a handful, the newest ones can wait. Answered items move
to the log below so decisions stay findable.

## Open

**Q1 — Dated "I need to \<meet/talk\>…": event or task?**
"on Monday, the 20th, I need to have a conversation with Greg" — today this
becomes a task; the dataset's ground truth calls it a calendar event. Same
family as the occasion-reminder rule you approved, one step further (no
remind-word at all). ~1 row on dev-fast, so low stakes — whenever convenient.

**Q4 — Notifications: do you want Mac reminders with the calendar CLOSED?**
That means detaching `assistant.api` into a launchd LaunchAgent (launch-model
change: --reload, HUD, shutdown ownership). If "no", the phone is officially
the only always-on ringer and the plan's riskiest phase disappears.
*(The build shipped with the phone-only default — this stays reversible.)*

**Q5 — Notifications: default lead time — opt-in (0: only where you asked)
or blanket (e.g. 30 min before everything)?** Shipped as 0 (opt-in);
blanket changes the feature's noise level on a dense calendar.

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
