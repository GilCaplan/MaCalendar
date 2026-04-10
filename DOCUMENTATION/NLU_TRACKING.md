# NLU Action Tracking

Auto-appended by the pipeline after every successfully executed action
(create, update, delete — events and todos).

Use this to evaluate rule fast-path hit rate and identify transcripts that should
be improved in the rule parser.

**Source:** `🖥️ Mac` (voice pipeline) | `📱 iOS` (API server)

**Parse method legend:**
- `✅ rule fast-path` — RuleBasedParser handled it entirely, no LLM call
- `🤖 hybrid` — Rule parser found partial slots, LLM filled the gaps
- `🤖 llm` — Full LLM parse (rule parser skipped or had low confidence)
- `🤖 separator` — Multi-segment split; each segment parsed independently
- `❌ failed (method)` — Parse or execution error; also written to SCENARIO_BUG.md

Review entries where `🤖 llm` or `🤖 hybrid` appears for commands that _should_
be simple enough for the rule parser. Add regression tests or rule improvements
to cover those patterns.

---

## [2026-04-06 17:50:46] SUCCESS — 🖥️ Mac
**Transcript:** `on this coming thursday, please send an event for me at 1pm to go to tellmond to visit my friend tal with idor`

**Parse:** ✅ rule fast-path | **Actions:** create_todo

- Added 'event' to Today.

---

## [2026-04-06 17:52:54] SUCCESS — 🖥️ Mac
**Transcript:** `create event this coming thursday to go visit my friend tal at 1 p.m. on the night. got`

**Parse:** ✅ rule fast-path | **Actions:** create_event

- Created event 'event' on Thursday, Apr 16, 2026 from 1 PM to 2 PM.

---

## [2026-04-06 17:54:39] SUCCESS — 🖥️ Mac
**Transcript:** `next week on monday on the 13th create event to ta class`

**Parse:** 🤖 hybrid | **Actions:** create_event

- Created event 'TA Class' on Monday, Apr 13, 2026 from 9 AM to 10 AM.

---

## [2026-04-06 17:55:09] SUCCESS — 🖥️ Mac
**Transcript:** `the last event that you just created on next monday on the 13th fixer time is not 9 o'clock rather it's 4.30 to 5.30 pm`

**Parse:** 🤖 llm | **Actions:** update_event

- I couldn't find an event at 17:30 on 2026-04-13.

---

## [2026-04-06 17:55:37] SUCCESS — 🖥️ Mac
**Transcript:** `no, edit event next week on the 13th. that says 9am, change it to the same title, but change it to 4.30pm to 5.30pm`

**Parse:** 🤖 llm | **Actions:** update_event

- Updated 'TA Class' successfully.

---

## [2026-04-06 17:56:37] SUCCESS — 🖥️ Mac
**Transcript:** `this week on friday set for 12 o'clock defend my eurovision homox execute at 12`

**Parse:** ✅ rule fast-path | **Actions:** create_event

- Created event 'eurovision homox execute' on Friday, Apr 10, 2026 from 12 PM to 1 PM.

---

## [2026-04-06 17:58:03] SUCCESS — 🖥️ Mac
**Transcript:** `again, creative and on friday at 12 o'clock this coming friday, eurovision homework defense`

**Parse:** 🤖 llm | **Actions:** create_event

- Created event 'Eurovision Homework Defense' on Friday, Apr 17, 2026 from 12 PM to 1 PM.

---

## [2026-04-06 19:00:02] SUCCESS — 🖥️ Mac
**Transcript:** `set event tomorrow at 4.30 pm for one hour with yarev regarding his bugroot`

**Parse:** ✅ rule fast-path | **Actions:** create_event

- Created event 'event' on Tuesday, Apr 7, 2026 from 4:30 PM to 5:30 PM.

---

## [2026-04-07 13:56:46] SUCCESS — 🖥️ Mac
**Transcript:** `can you set a meeting for next week on the 14th on tuesday at 2pm to do a meeting with manachem to do a run of simulation with him`

**Parse:** ✅ rule fast-path | **Actions:** create_event

- Created event 'meeting' on Tuesday, Apr 14, 2026 from 2 PM to 3 PM.

---

## [2026-04-07 16:37:34] SUCCESS — 🖥️ Mac
**Transcript:** `today i have an event at 6 o'clock a meeting`

**Parse:** 🤖 llm | **Actions:** create_event

- Created event 'meeting' on Tuesday, Apr 7, 2026 from 6 PM to 7 PM.

---

## [2026-04-09 18:54:17] SUCCESS — 🖥️ Mac
**Transcript:** `on tuesday, the 14th next week, set an event at 3 o'clock meeting with ora for project xq. xq.`

**Parse:** 🤖 llm | **Actions:** create_event

- Created event 'Meeting with Ora for XQ' on Tuesday, Apr 21, 2026 from 3 PM to 4 PM.

---

## [2026-04-09 21:51:11] SUCCESS — 🖥️ Mac
**Transcript:** `please make a meeting for me at 1040 on monday the 13th for makabi visiting the doctor`

**Parse:** 🤖 hybrid | **Actions:** create_event

- Created event 'meeting' on Monday, Apr 13, 2026 from 10:40 AM to 11:40 AM.

---

