# Assistant audit — accuracy, latency, self-check

_Generated 2026-09-03 18:11 · 92 commands · scratch DB · vocabulary 374 words · machine arm64. Re-run: `python -m scripts.audit_assistant`._

## Headline

- **Correct after the quick answer:** 85%  ·  **correct once settled (after self-check):** 80% — case-level exact match against this corpus's hand-written expectations, 92 cases, not a real-usage or human-judged figure
- **Recall 83%** (94/113 expected items produced correctly) · **precision 88%** (105/112 produced actions were expected, plus 8 extra task rows beyond what was expected) — accuracy alone doesn't distinguish missing something asked for from producing something extra
- **Time to first result:** p50 33.3 s · p95 131.7 s  ·  **time to settled:** p50 41.2 s · p95 131.7 s
- Parse paths: deep 51, error 2, fast 39

## By area

| Area | n | quick ✓ | settled ✓ | recall | precision | first p50 | first p95 | settled p50 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| adversarial | 5 | 100% | 100% | 100% | 100% | 12.9 s | 74.7 s | 13.4 s |
| events | 41 | 85% | 85% | 87% | 98% | 52.5 s | 133.2 s | 52.5 s |
| from-chats | 15 | 73% | 73% | 75% | 100% | 61.2 s | 112.4 s | 64.6 s |
| mixed | 3 | 100% | 100% | 100% | 100% | 0.1 s | 198.7 s | 7.2 s |
| query | 3 | 100% | 100% | 100% | 100% | 0.0 s | 0.1 s | 7.7 s |
| tasks | 18 | 83% | 61% | 63% | 58% | 0.0 s | 100.2 s | 9.1 s |
| update-delete | 7 | 86% | 86% | 86% | 100% | 0.1 s | 83.5 s | 17.8 s |

## By parse path

| Path | n | quick ✓ | settled ✓ | recall | precision | first p50 | first p95 | LLM ms p50 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| deep | 51 | 78% | 78% | 84% | 87% | 70.1 s | 152.0 s | 43088 |
| error | 2 | 0% | 0% | 0% | 100% | 22.1 s | 31.9 s | 11039 |
| fast | 39 | 97% | 87% | 88% | 89% | 0.0 s | 0.1 s | 0 |

## Quick answer vs self-check

- Self-check ran on 39 commands; it proposed a correction on 18 (0 applied).
- **Fixed by self-check:** 0  ·  **broken by self-check:** 4
  - broke: “add buy milk, eggs and bread to my list” → {'ok': False, 'severity': 'minor', 'patch': {}, 'speech': "I first missed part of that — Added 'add eggs' to Today tagged Groceries. I first missed part of that — Added 'add bread' to Today tagged Groceries.", 'refresh': 'both'}
  - broke: “i want to buy chicken and rice” → {'ok': False, 'severity': 'minor', 'patch': {}, 'speech': "I first missed part of that — Added 'buy rice' to Today tagged Groceries.", 'refresh': 'both'}
  - broke: “remind me to buy a birthday gift for mom and dad” → {'ok': False, 'severity': 'minor', 'patch': {}, 'speech': "I first missed part of that — Added 'buy a birthday gift for dad' to Today.", 'refresh': 'both'}
  - broke: “put milk and bananas on the groceries list” → {'ok': False, 'severity': 'minor', 'patch': {}, 'speech': "I first missed part of that — Added 'bananas' to Today tagged Groceries.", 'refresh': 'both'}

## Engine stages (latency; a slow or misbehaving stage is fixed in ITS module)

| Stage | ran on | ms p50 | ms p95 |
|---|---:|---:|---:|
| vocab | 92/92 | 13 | 26 |
| rule | 90/92 | 19 | 102 |
| llm | 53/92 | 42969 | 126504 |
| validate | 21/92 | 2 | 25 |
| execute | 83/92 | 7 | 21 |
| verify | 51/92 | 22578 | 34818 |

## Named-rule fixes applied

| Rule | times |
|---|---:|
| relative_date_pin | 22 |
| observance_gate | 16 |
| due_date_pin | 11 |
| anaphor_guard | 8 |
| bare_hour_pm | 4 |
| recurrence_words | 3 |
| weekly_start_day | 3 |
| morning_title_guard | 2 |

## Cross-check (step 6)

- Findings: 232 (extra, missing) across 39 command(s); loop-backs on 39 command(s) (114 re-entries total).
- Budget exhausted (answer flagged as unsure): 37.

## By shape (failures first)

| Shape | n | settled ✓ | first p50 |
|---|---:|---:|---:|
| single/internal-and | 1 | 0% | 0.1 s |
| multi/shared-verb | 1 | 0% | 0.1 s |
| multi/interleaved-clauses | 1 | 0% | 44.8 s |
| multi/same-list-3 | 1 | 0% | 86.9 s |
| single/disfluency | 1 | 0% | 133.2 s |
| update/move-by-time | 1 | 0% | 64.5 s |
| multi/disfluent-duration | 1 | 0% | 33.0 s |
| multi/tagged | 1 | 0% | 0.1 s |
| multi/self-correction-count | 1 | 0% | 176.5 s |
| multi/same-due-date | 1 | 0% | 90.3 s |
| multi/same-day-2 | 3 | 33% | 39.7 s |
| multi/same-list | 2 | 50% | 0.0 s |
| chat-phrasing | 15 | 73% | 61.2 s |
| generated/single | 12 | 92% | 72.8 s |
| recurring/daily | 1 | 100% | 16.3 s |
| single/hebrew-term | 2 | 100% | 60.1 s |
| single/day-of-month | 1 | 100% | 54.5 s |
| update/move-by-title | 1 | 100% | 0.0 s |
| single/next-weekday | 1 | 100% | 0.1 s |
| single/due-tomorrow | 1 | 100% | 0.0 s |
| delete/by-time | 1 | 100% | 0.0 s |
| single/place | 1 | 100% | 65.4 s |
| 3events+task | 1 | 100% | 220.8 s |
| multi/shared-verb-people | 1 | 100% | 0.0 s |
| single/spoken-time | 1 | 100% | 62.5 s |
| single/terse | 1 | 100% | 61.9 s |
| single/inferred-tag | 1 | 100% | 0.0 s |
| past-tense-noise | 1 | 100% | 72.4 s |
| multi/same-day-3 | 2 | 100% | 42.4 s |
| query/week | 1 | 100% | 0.0 s |
| task+event | 1 | 100% | 0.1 s |
| single | 2 | 100% | 0.0 s |
| recurring/weekly | 2 | 100% | 58.8 s |
| multi/different-days | 2 | 100% | 37.6 s |
| delete/by-title | 1 | 100% | 0.1 s |
| update/extend | 1 | 100% | 91.7 s |
| multi/different-due-dates | 1 | 100% | 156.3 s |
| single/due-weekday | 1 | 100% | 0.0 s |
| query/today | 1 | 100% | 0.1 s |
| multi/different-days-3 | 1 | 100% | 61.0 s |
| single/explicit-time | 3 | 100% | 0.1 s |
| ambiguous/no-time | 1 | 100% | 12.9 s |
| task-not-event | 1 | 100% | 0.1 s |
| single/general-list | 1 | 100% | 0.0 s |
| multi/shared-verb-3 | 1 | 100% | 0.0 s |
| update/rename | 1 | 100% | 0.0 s |
| misheard-names | 1 | 100% | 75.3 s |
| query/tomorrow | 1 | 100% | 0.0 s |
| event-not-task | 1 | 100% | 0.1 s |
| event+task | 1 | 100% | 0.1 s |
| single/range | 1 | 100% | 66.4 s |
| single/weekday | 1 | 100% | 75.8 s |
| update/move-day | 1 | 100% | 0.1 s |
| single/stop-word | 1 | 100% | 0.0 s |
| single/hebrew-name | 1 | 100% | 0.0 s |
| single/full-name | 1 | 100% | 0.1 s |
| single/duration | 1 | 100% | 0.0 s |

## Produced more than expected (precision failures)

Distinct from a wrong or missing answer: the system did something on top of what was asked for — an extra action, or extra rows from one action (a duplicated task from a misread clause is invisible to an action-count check, since the action count can still be right).

- **meeting tomorrow at 2 sorry not 2, 3 pm with Adin for the project** — 1 extra action(s) — got ['create_event', 'create_event']
- **add buy milk, eggs and bread to my list** — 2 extra task row(s) — got ['create_todo']
- **i want to buy chicken and rice** — 1 extra task row(s) — got ['create_todo']
- **remind me to buy a birthday gift for mom and dad** — 1 extra task row(s) — got ['create_todo']
- **add tasks: submit the Haxaga grades, prepare Netivim slides, pay rent** — 1 extra action(s) — got ['create_todo', 'create_todo']
- **two tasks due tomorrow: buy groceries and return the library book** — 1 extra action(s) — got ['create_todo', 'create_event']
- **put milk and bananas on the groceries list** — 1 extra task row(s) — got ['create_todo']
- **[TASKS VIEW] i need to buy some groceries, i need rice and chicken, the chicken i need to get far away, the rice i can get at whole foods** — 4 extra action(s), 3 extra task row(s) — got ['create_todo', 'create_todo', 'create_todo', 'create_todo', 'create_todo']

## Failures

### events · single/disfluency · `deep` · 133.2 s
- **Said:** meeting tomorrow at 2 sorry not 2, 3 pm with Adin for the project
- **Did:** ['create_event', 'create_event'] — I'm not sure I caught every part of that — worth a glance. Created event 'Meeting' on Friday, Sep 4, 2026 from 2 PM to 3 PM. Created event 'Meeting with Adin' o
- extra actions ['create_event']

### events · multi/same-day-2 · `deep` · 30.6 s
- **Said:** tomorrow gym at 7 am and a meeting with Tal at 11
- **Did:** ['create_event', 'create_event'] — Created event 'Gym' on Friday, Sep 4, 2026 from 7 AM to 8 AM. Created event 'Meeting with Tal' on Thursday, Sep 3, 2026 from 11 AM to 12 PM.
- no event matching {'date': '2026-09-04', 'start_time': '11:00', 'title_contains': 'Tal'} in DB [('Meeting with Tal', '2026-09-03', '11:00'), ('Gym', '2026-09-04', '07:00')]

### events · multi/same-day-2 · `deep` · 147.8 s
- **Said:** two events tomorrow, one at four o'clock meeting with Rei and one at seven pm pizza with Ezra
- **Did:** ['create_event'] — I'm not sure I caught every part of that — worth a glance. Created event 'Meeting with Rei' on Friday, Sep 4, 2026 from 4 PM to 5 PM. I didn't book 'Pizza with 
- missing action create_event (got ['create_event'])
- no event matching {'date': '2026-09-04', 'start_time': '19:00', 'title_contains': 'Ezra'} in DB [('Meeting with Rei', '2026-09-04', '16:00')]

### events · multi/disfluent-duration · `error` · 33.0 s
- **Said:** set a meeting at 4pm today, but it is only 20 minutes meeting with one moment meeting with reards, okay, then let's do another meeting from 6 from 6 o'clock to 640 meetings with kids for project defense
- **Did:** [] — Validation failed for 'create_event': 1 validation error for CalendarIntent
title
  Value error, Event title cannot be empty [type=value_error, input_value='', 
- missing action create_event (got [])
- missing action create_event (got [])
- no event matching {'date': '2026-09-03', 'start_time': '16:00', 'end_time': '16:20'} in DB []

### events · multi/self-correction-count · `deep` · 176.5 s
- **Said:** a meeting for me tomorrow at two one sorry one pm and four pm and then another one a pizza party at 6.30 pm at edo's
- **Did:** ['create_event', 'create_event', 'create_event'] — I'm not sure I caught every part of that — worth a glance. Created event 'Meeting' on Friday, Sep 4, 2026 from 1 PM to 2 PM. Created event 'Meeting' on Thursday
- no event matching {'date': '2026-09-04', 'start_time': '16:00', 'end_time': '17:00'} in DB [('Meeting', '2026-09-03', '16:00'), ('Pizza Party', '2026-09-03', '18:30'), ('Meeting', '2026-09-04', '13:00')]
- no event matching {'date': '2026-09-04', 'start_time': '18:30', 'end_time': '19:30', 'title_contains': 'pizza'} in DB [('Meeting', '2026-09-03', '16:00'), ('Pizza Party', '2026-09-03', '18:30'), ('Meeting', '2026-09-04', '13:00')]

### tasks · multi/same-list · `fast` · 0.0 s
- **Said:** add buy milk, eggs and bread to my list
- **Did:** ['create_todo'] — Added 'buy milk', 'buy eggs' and 'buy bread' to Today tagged Groceries.
- expected 3 todos, got 5: ['buy milk', 'buy eggs', 'buy bread', 'add eggs', 'add bread']

### tasks · multi/shared-verb · `fast` · 0.1 s
- **Said:** i want to buy chicken and rice
- **Did:** ['create_todo'] — Added 'buy chicken' and 'buy rice' to Today tagged Groceries.
- expected 2 todos, got 3: ['buy chicken', 'buy rice', 'buy rice']

### tasks · single/internal-and · `fast` · 0.1 s
- **Said:** remind me to buy a birthday gift for mom and dad
- **Did:** ['create_todo'] — Added 'buy a birthday gift for mom and dad' to Today.
- expected 1 todos, got 2: ['buy a birthday gift for mom and dad', 'buy a birthday gift for dad']

### tasks · multi/same-list-3 · `deep` · 86.9 s
- **Said:** add tasks: submit the Haxaga grades, prepare Netivim slides, pay rent
- **Did:** ['create_todo', 'create_todo'] — I'm not sure I caught every part of that — worth a glance. Sorry, I didn't understand that. Added 'prepare netivim slides' to Today tagged Work. Added 'pay re
- extra actions ['create_todo']
- no todo containing 'grades' (todos=['prepare netivim slides', 'pay rent'])

### tasks · multi/same-due-date · `deep` · 90.3 s
- **Said:** two tasks due tomorrow: buy groceries and return the library book
- **Did:** ['create_todo', 'create_event'] — I'm not sure I caught every part of that — worth a glance. Added 'buy groceries' to Today tagged Groceries. Created event 'library book' on Friday, Sep 4, 2026 
- extra actions ['create_event']
- no todo containing 'library' (todos=['buy groceries'])

### tasks · multi/tagged · `fast` · 0.1 s
- **Said:** put milk and bananas on the groceries list
- **Did:** ['create_todo'] — Added 'milk' and 'bananas' to Today tagged Groceries.
- expected 2 todos, got 3: ['milk', 'bananas', 'bananas']

### tasks · multi/interleaved-clauses · `deep` · 44.8 s
- **Said:** [TASKS VIEW] i need to buy some groceries, i need rice and chicken, the chicken i need to get far away, the rice i can get at whole foods
- **Did:** ['create_todo', 'create_todo', 'create_todo', 'create_todo', 'create_todo'] — Added 'buy some groceries' to Today tagged Groceries. Added 'buy rice' to Today tagged Groceries. Added 'buy chicken' to Today tagged Groceries. Added 'get chic
- extra actions ['create_todo', 'create_todo', 'create_todo', 'create_todo']
- expected 2 todos, got 5: ['buy some groceries', 'buy rice', 'buy chicken', 'get chicken', 'get rice']

### update-delete · update/move-by-time · `deep` · 64.5 s
- **Said:** move my 1pm meeting tomorrow to 3pm
- **Did:** ['update_event'] — I'm not sure I caught every part of that — worth a glance. Updated 'Meeting with Tal' successfully.
- expected 'Meeting with Tal' at 15:00; have [('Meeting with Tal', '2026-09-04', '13:00')]

### from-chats · chat-phrasing · `deep` · 130.5 s
- **Said:** Kems tomorrow at 8 with Ravid and Ezra
- **Did:** [] — I'm not sure I caught every part of that — worth a glance. I didn't book 'Kems meeting': that lands on Shabbat (Friday, Sep 4).
- missing action create_event (got [])
- no event matching {'date': '2026-09-04', 'start_time': '20:00'} in DB []

### from-chats · chat-phrasing · `error` · 11.3 s
- **Said:** bowling tuesday night for Rei's birthday
- **Did:** [] — Validation failed for 'create_event': 2 validation errors for CalendarIntent
start_time
  Value error, time must be HH:MM, got 'night' [type=value_error, input_
- missing action create_event (got [])
- no event matching {'date': '2026-09-08', 'title_contains': 'bowling'} in DB []
- vocab corrections: [{'from': "Rei's", 'reason': 'alias', 'score': 1.0, 'to': "Edo's"}]

### from-chats · chat-phrasing · `deep` · 104.6 s
- **Said:** night shift tomorrow from 8 pm to 6 am
- **Did:** [] — I'm not sure I caught every part of that — worth a glance. I didn't book 'Night Shift': that lands on Shabbat (Friday, Sep 4).
- missing action create_event (got [])
- no event matching {'date': '2026-09-04', 'start_time': '20:00'} in DB []

### from-chats · chat-phrasing · `fast` · 5.2 s
- **Said:** meeting with Guri moved from 9:30 to 9 on wednesday
- **Did:** [] — I couldn't find an event matching 'guri'.
- missing action create_event|update_event (got [])

### events · generated/single · `deep` · 71.2 s
- **Said:** meeting with Ezra on friday at 7 pm about the robotics project
- **Did:** [] — I'm not sure I caught every part of that — worth a glance. I didn't book 'Meeting with Ezra': that lands on Shabbat (Friday, Sep 4).
- missing action create_event (got [])
- no event matching {'date': '2026-09-04', 'start_time': '19:00', 'title_contains': None} in DB []

## Slowest 10

| s | path | command |
|---:|---|---|
| 220.8 | deep | tomorrow: Shacharit at 6:30, Haxaga TA at 12, dinner with Ezra at 8 pm, and remi |
| 176.5 | deep | a meeting for me tomorrow at two one sorry one pm and four pm and then another o |
| 156.3 | deep | add buy a gift for Tamar due thursday and book the driving test due next monday |
| 147.8 | deep | two events tomorrow, one at four o'clock meeting with Rei and one at seven pm pi |
| 133.2 | deep | meeting tomorrow at 2 sorry not 2, 3 pm with Adin for the project |
| 130.5 | deep | Kems tomorrow at 8 with Ravid and Ezra |
| 104.6 | deep | night shift tomorrow from 8 pm to 6 am |
| 91.7 | deep | extend the meeting with Tal tomorrow until 3 pm |
| 90.3 | deep | two tasks due tomorrow: buy groceries and return the library book |
| 86.9 | deep | add tasks: submit the Haxaga grades, prepare Netivim slides, pay rent |

## Raw

Full per-case JSON: `DOCUMENTATION/ASSISTANT_AUDIT.md.json`