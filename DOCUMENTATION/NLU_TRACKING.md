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

## [2026-04-12 12:12:59] SUCCESS — 🖥️ Mac
**Transcript:** `a certain meeting on wednesday at 5.15pm to meet with vika for magsha meme bagru progress update`

**Parse:** ✅ rule fast-path | **Actions:** update_event

- Updated 'Content creation meeting with Vika' successfully.

---

## [2026-04-12 14:23:14] SUCCESS — 🖥️ Mac
**Transcript:** `for this coming tuesday on to do two events one at four o'clock meeting with pelic and another meeting at five o'clock with ido`

**Parse:** 🤖 llm | **Actions:** create_event, create_event

- Created event 'Meeting with Pelic' on Tuesday, Apr 14, 2026 from 4 PM to 5 PM.
- Created event 'Meeting with Ido' on Tuesday, Apr 14, 2026 from 5 PM to 6 PM.

---

## [2026-04-12 18:17:59] SUCCESS — 🖥️ Mac
**Transcript:** `at a meeting tomorrow monday, 13th, for a zoom ae pie zoom at 8 o'clock pm`

**Parse:** 🤖 llm | **Actions:** create_event

- Created event 'Zoom AE Pie Meeting' on Monday, Apr 13, 2026 from 8 PM to 9 PM.

---

## [2026-04-13 11:55:54] SUCCESS — 🖥️ Mac
**Transcript:** `set an appointment for tomorrow morning on tuesday at 910am`

**Parse:** ✅ rule fast-path | **Actions:** create_event

- Created event 'appointment' on Tuesday, Apr 14, 2026 from 9:10 AM to 10:10 AM.

---

## [2026-04-13 18:55:41] SUCCESS — 🖥️ Mac
**Transcript:** `i have a dense squirmant tomorrow morning at 9.10am`

**Parse:** 🤖 llm | **Actions:** create_event

- Created event 'dense squirmant' on Tuesday, Apr 14, 2026 from 9:10 AM to 10:10 AM.

---

## [2026-04-13 21:01:14] SUCCESS — 🖥️ Mac
**Transcript:** `reading tomorrow at six p.m. with it time`

**Parse:** ✅ rule fast-path | **Actions:** query_schedule

- You have 5 events tomorrow: Dentist appointment at 9:10 AM, Meeting W Menachem - simulation on project at 2 PM, Meeting with Ora for Project at 3 PM, Meeting with Peleg at 4 PM, and Meeting with Ido at 5 PM.

---

## [2026-04-13 21:01:37] SUCCESS — 🖥️ Mac
**Transcript:** `set a meeting tomorrow on tuesday at 6pm with etai`

**Parse:** ✅ rule fast-path | **Actions:** create_event

- Created event 'meeting' on Tuesday, Apr 14, 2026 from 6 PM to 7 PM.

---

## [2026-04-13 21:02:15] SUCCESS — 🖥️ Mac
**Transcript:** `again, create an event tomorrow at 6pm with etie`

**Parse:** ✅ rule fast-path | **Actions:** create_event

- Created event 'event' on Tuesday, Apr 14, 2026 from 6 PM to 7 PM.

---

## [2026-04-13 22:35:10] SUCCESS — 🖥️ Mac
**Transcript:** `start emitting for me on wednesday at 6.30. excuse me. excuse me.`

**Parse:** 🤖 llm | **Actions:** create_event

- Created event 'Meeting' on Wednesday, Apr 15, 2026 from 6:30 PM to 7:30 PM.

---

## [2026-04-14 18:27:22] SUCCESS — 🖥️ Mac
**Transcript:** `set a meeting tomorrow at 2 o'clock meeting with omri for project`

**Parse:** ✅ rule fast-path | **Actions:** create_event

- Created event 'meeting' on Wednesday, Apr 15, 2026 from 2 AM to 3 AM.

---

## [2026-04-14 18:29:24] SUCCESS — 🖥️ Mac
**Transcript:** `create a meeting tomorrow at 2pm on wednesday meeting with omri for the project`

**Parse:** ✅ rule fast-path | **Actions:** create_event

- Created event 'meeting' on Wednesday, Apr 15, 2026 from 2 PM to 3 PM.

---

## [2026-04-15 15:11:29] SUCCESS — 🖥️ Mac
**Transcript:** `set a meeting for me tomorrow at 11 a.m. and also set meeting for 5.30 p.m. to 6.30 p.m. tomorrow as well`

**Parse:** 🤖 llm | **Actions:** create_event, create_event

- Created event 'Meeting' on Thursday, Apr 16, 2026 from 11 AM to 12 PM.
- Created event 'Meeting' on Thursday, Apr 16, 2026 from 5:30 PM to 6:30 PM.

---

## [2026-04-15 18:01:07] SUCCESS — 🖥️ Mac
**Transcript:** `meeting on monday next week, the 20th of april 10 o'clock meeting with victoria on content, execute`

**Parse:** 🤖 llm | **Actions:** create_event

- Created event 'Meeting with Victoria on Content' on Monday, Apr 20, 2026 from 10 AM to 11 AM.

---

## [2026-04-15 20:38:25] SUCCESS — 🖥️ Mac
**Transcript:** `set meaning for tomorrow at 7 p.m. with noah`

**Parse:** ✅ rule fast-path | **Actions:** create_event

- Created event 'meaning' on Thursday, Apr 16, 2026 from 7 PM to 8 PM.

---

## [2026-04-15 22:22:38] SUCCESS — 🖥️ Mac
**Transcript:** `meeting tomorrow at full pm with dad for brokerage advice tomorrow at thursday`

**Parse:** 🤖 llm | **Actions:** create_event

- Created event 'Meeting with Dad' on Thursday, Apr 16, 2026 from 6 PM to 7 PM.

---

## [2026-04-16 10:28:23] SUCCESS — 🖥️ Mac
**Transcript:** `set a meeting at 4pm today, but it is only 20 minutes meeting with one moment meeting with reards, okay, then let's do another meeting from 6 from 6 o'clock to 640 meetings with kids for project defense`

**Parse:** 🤖 llm | **Actions:** create_event, create_event

- Created event 'Meeting' on Thursday, Apr 16, 2026 from 4 PM to 4:20 PM.
- Created event 'Meeting' on Thursday, Apr 16, 2026 from 6 PM to 7:40 PM.

---

