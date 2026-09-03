# Assistant audit — accuracy, latency, self-check

_Generated 2026-09-03 19:01 · 94 commands · scratch DB · vocabulary 374 words · machine arm64. Re-run: `python -m scripts.audit_assistant`._

## Headline

- **Correct after the quick answer:** 88%  ·  **correct once settled (after self-check):** 88% — case-level exact match against this corpus's hand-written expectations, 94 cases, not a real-usage or human-judged figure
- **Recall 90%** (103/114 expected items produced correctly) · **precision 90%** (112/121 produced actions were expected, plus 3 extra task rows beyond what was expected) — accuracy alone doesn't distinguish missing something asked for from producing something extra
- **Time to first result:** p50 16.7 s · p95 55.3 s  ·  **time to settled:** p50 17.7 s · p95 55.3 s
- Parse paths: deep 55, fast 39

## By area

| Area | n | quick ✓ | settled ✓ | recall | precision | first p50 | first p95 | settled p50 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| adversarial | 7 | 100% | 100% | 100% | 100% | 24.7 s | 27.1 s | 24.7 s |
| events | 41 | 88% | 88% | 89% | 95% | 18.0 s | 67.4 s | 18.2 s |
| from-chats | 15 | 87% | 87% | 88% | 100% | 22.3 s | 36.4 s | 22.3 s |
| mixed | 3 | 100% | 100% | 100% | 100% | 0.1 s | 55.8 s | 9.9 s |
| query | 3 | 100% | 100% | 100% | 100% | 0.0 s | 0.0 s | 7.2 s |
| tasks | 18 | 83% | 83% | 89% | 68% | 0.0 s | 46.7 s | 7.9 s |
| update-delete | 7 | 86% | 86% | 86% | 100% | 0.0 s | 22.5 s | 7.5 s |

## By parse path

| Path | n | quick ✓ | settled ✓ | recall | precision | first p50 | first p95 | LLM ms p50 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| deep | 55 | 82% | 82% | 86% | 86% | 22.7 s | 75.8 s | 13148 |
| fast | 39 | 97% | 97% | 98% | 100% | 0.0 s | 0.1 s | 0 |

## Quick answer vs self-check

- Self-check ran on 39 commands; it proposed a correction on 1 (0 applied).
- **Fixed by self-check:** 0  ·  **broken by self-check:** 0

## Engine stages (latency; a slow or misbehaving stage is fixed in ITS module)

| Stage | ran on | ms p50 | ms p95 |
|---|---:|---:|---:|
| vocab | 94/94 | 13 | 26 |
| rule | 92/94 | 25 | 103 |
| llm | 56/94 | 12850 | 59876 |
| validate | 27/94 | 1 | 10 |
| execute | 89/94 | 5 | 30 |
| verify | 55/94 | 8854 | 22143 |

## Named-rule fixes applied

| Rule | times |
|---|---:|
| due_date_pin | 5 |
| relative_date_pin | 4 |
| observance_gate | 4 |
| anaphor_guard | 4 |
| weekly_start_day | 1 |
| bare_hour_pm | 1 |

## Cross-check (step 6)

- Findings: 16 (extra, missing) across 4 command(s); loop-backs on 3 command(s) (9 re-entries total).
- Budget exhausted (answer flagged as unsure): 3.

## By shape (failures first)

| Shape | n | settled ✓ | first p50 |
|---|---:|---:|---:|
| multi/same-due-date | 1 | 0% | 22.0 s |
| update/move-by-time | 1 | 0% | 18.8 s |
| multi/interleaved-clauses | 1 | 0% | 38.2 s |
| multi/disfluent-duration | 1 | 0% | 208.5 s |
| multi/self-correction-count | 1 | 0% | 67.4 s |
| multi/same-list-3 | 1 | 0% | 95.3 s |
| multi/same-day-2 | 3 | 33% | 43.7 s |
| multi/same-day-3 | 2 | 50% | 34.9 s |
| chat-phrasing | 15 | 87% | 22.3 s |
| multi/different-days | 2 | 100% | 29.4 s |
| update/move-day | 1 | 100% | 0.0 s |
| ambiguous/no-time | 1 | 100% | 19.3 s |
| task+event | 1 | 100% | 0.1 s |
| single/duration | 1 | 100% | 0.1 s |
| single/range | 1 | 100% | 17.9 s |
| query/today | 1 | 100% | 0.0 s |
| query/tomorrow | 1 | 100% | 0.0 s |
| event+task | 1 | 100% | 0.1 s |
| query/week | 1 | 100% | 0.0 s |
| multi/different-days-3 | 1 | 100% | 51.6 s |
| single | 2 | 100% | 0.0 s |
| single/full-name | 1 | 100% | 0.1 s |
| generated/single | 12 | 100% | 20.7 s |
| multi/shared-verb-3 | 1 | 100% | 0.1 s |
| multi/tagged | 1 | 100% | 0.0 s |
| single/terse | 1 | 100% | 15.6 s |
| single/disfluency | 1 | 100% | 30.0 s |
| delete/by-time | 1 | 100% | 0.0 s |
| update/rename | 1 | 100% | 0.1 s |
| observance-gate | 1 | 100% | 24.7 s |
| single/hebrew-name | 1 | 100% | 0.0 s |
| 3events+task | 1 | 100% | 62.0 s |
| recurring/daily | 1 | 100% | 15.4 s |
| multi/same-list | 2 | 100% | 0.0 s |
| single/spoken-time | 1 | 100% | 18.0 s |
| task-not-event | 1 | 100% | 0.0 s |
| event-not-task | 1 | 100% | 0.0 s |
| single/hebrew-term | 2 | 100% | 16.3 s |
| multi/shared-verb-people | 1 | 100% | 0.1 s |
| single/due-tomorrow | 1 | 100% | 0.0 s |
| single/weekday | 1 | 100% | 16.9 s |
| single/day-of-month | 1 | 100% | 22.7 s |
| single/inferred-tag | 1 | 100% | 0.0 s |
| single/place | 1 | 100% | 14.2 s |
| multi/shared-verb | 1 | 100% | 0.0 s |
| single/general-list | 1 | 100% | 0.1 s |
| update/extend | 1 | 100% | 24.0 s |
| misheard-names | 1 | 100% | 27.5 s |
| single/internal-and | 1 | 100% | 0.0 s |
| single/due-weekday | 1 | 100% | 0.0 s |
| single/stop-word | 1 | 100% | 0.0 s |
| observance-meal-ok | 1 | 100% | 26.3 s |
| multi/different-due-dates | 1 | 100% | 37.7 s |
| past-tense-noise | 1 | 100% | 26.3 s |
| delete/by-title | 1 | 100% | 0.0 s |
| update/move-by-title | 1 | 100% | 0.0 s |
| single/explicit-time | 3 | 100% | 0.1 s |
| recurring/weekly | 2 | 100% | 21.9 s |
| single/next-weekday | 1 | 100% | 0.1 s |

## Produced more than expected (precision failures)

Distinct from a wrong or missing answer: the system did something on top of what was asked for — an extra action, or extra rows from one action (a duplicated task from a misread clause is invisible to an action-count check, since the action count can still be right).

- **set a meeting at 4pm today, but it is only 20 minutes meeting with one moment meeting with reards, okay, then let's do another meeting from 6 from 6 o'clock to 640 meetings with kids for project defense** — 1 extra action(s) — got ['create_event', 'create_event', 'create_event']
- **a meeting for me tomorrow at two one sorry one pm and four pm and then another one a pizza party at 6.30 pm at edo's** — 2 extra action(s) — got ['create_event', 'create_event', 'create_todo', 'create_todo', 'create_event']
- **add tasks: submit the Haxaga grades, prepare Netivim slides, pay rent** — 1 extra action(s) — got ['create_todo', 'create_todo']
- **two tasks due tomorrow: buy groceries and return the library book** — 1 extra action(s) — got ['create_todo', 'create_todo']
- **[TASKS VIEW] i need to buy some groceries, i need rice and chicken, the chicken i need to get far away, the rice i can get at whole foods** — 4 extra action(s), 3 extra task row(s) — got ['create_todo', 'create_todo', 'create_todo', 'create_todo', 'create_todo']

## Failures

### events · multi/same-day-3 · `deep` · 18.2 s
- **Said:** set a meeting tomorrow at 1 pm, another one at 4 pm and then pizza at 6:30 pm tomorrow
- **Did:** ['create_event', 'create_event', 'create_event'] — Created event 'meeting' on Friday, Sep 4, 2026 from 1 PM to 2 PM. Created event 'meeting' on Friday, Sep 4, 2026 from 4 PM to 5 PM. Created event 'meeting' on F
- no event matching {'date': '2026-09-04', 'start_time': '18:30', 'title_contains': 'pizza'} in DB [('meeting', '2026-09-04', '13:00'), ('meeting', '2026-09-04', '16:00'), ('meeting', '2026-09-04', '18:30')]

### events · multi/same-day-2 · `deep` · 41.4 s
- **Said:** tomorrow gym at 7 am and a meeting with Tal at 11
- **Did:** ['create_event', 'create_event'] — Created event 'Gym' on Friday, Sep 4, 2026 from 7 AM to 8 AM. Created event 'Meeting with Tal' on Thursday, Sep 3, 2026 from 11 AM to 12 PM.
- no event matching {'date': '2026-09-04', 'start_time': '11:00', 'title_contains': 'Tal'} in DB [('Meeting with Tal', '2026-09-03', '11:00'), ('Gym', '2026-09-04', '07:00')]

### events · multi/same-day-2 · `deep` · 162.7 s
- **Said:** two events tomorrow, one at four o'clock meeting with Rei and one at seven pm pizza with Ezra
- **Did:** ['create_event', 'create_event'] — I'm not sure I caught every part of that — worth a glance. Created event 'Meeting with Rei' on Friday, Sep 4, 2026 from 4 PM to 5 PM. Created event 'Pizza with 
- no event matching {'date': '2026-09-04', 'start_time': '19:00', 'title_contains': 'Ezra'} in DB [('Pizza with Ezra', '2026-09-03', '19:00'), ('Meeting with Rei', '2026-09-04', '16:00')]

### events · multi/disfluent-duration · `deep` · 208.5 s
- **Said:** set a meeting at 4pm today, but it is only 20 minutes meeting with one moment meeting with reards, okay, then let's do another meeting from 6 from 6 o'clock to 640 meetings with kids for project defense
- **Did:** ['create_event', 'create_event', 'create_event'] — I'm not sure I caught every part of that — worth a glance. Created event 'meeting with meeting and reards' on Thursday, Sep 3, 2026 from 4 PM to 5 PM. Created e
- extra actions ['create_event']
- no event matching {'date': '2026-09-03', 'start_time': '16:00', 'end_time': '16:20'} in DB [('meeting with meeting and reards', '2026-09-03', '16:00'), ('Event', '2026-09-03', '18:00'), ('Another meeting', '2026-09-04', '18:00')]

### events · multi/self-correction-count · `deep` · 67.4 s
- **Said:** a meeting for me tomorrow at two one sorry one pm and four pm and then another one a pizza party at 6.30 pm at edo's
- **Did:** ['create_event', 'create_event', 'create_todo', 'create_todo', 'create_event'] — Created event 'Meeting' on Friday, Sep 4, 2026 from 1 PM to 2 PM. Created event 'Meeting' on Thursday, Sep 3, 2026 from 4 PM to 5 PM. Added 'buy chicken' and 'b
- extra actions ['create_todo', 'create_todo']
- no event matching {'date': '2026-09-04', 'start_time': '16:00', 'end_time': '17:00'} in DB [('Meeting', '2026-09-03', '16:00'), ('Pizza Party', '2026-09-03', '18:30'), ('Meeting', '2026-09-04', '13:00')]
- no event matching {'date': '2026-09-04', 'start_time': '18:30', 'end_time': '19:30', 'title_contains': 'pizza'} in DB [('Meeting', '2026-09-03', '16:00'), ('Pizza Party', '2026-09-03', '18:30'), ('Meeting', '2026-09-04', '13:00')]

### tasks · multi/same-list-3 · `deep` · 95.3 s
- **Said:** add tasks: submit the Haxaga grades, prepare Netivim slides, pay rent
- **Did:** ['create_todo', 'create_todo'] — I'm not sure I caught every part of that — worth a glance. Sorry, I didn't understand that. Added 'prepare netivim slides' to Today tagged Work. Added 'pay re
- extra actions ['create_todo']
- no todo containing 'grades' (todos=['prepare netivim slides', 'pay rent'])

### tasks · multi/same-due-date · `deep` · 22.0 s
- **Said:** two tasks due tomorrow: buy groceries and return the library book
- **Did:** ['create_todo', 'create_todo'] — Added 'buy groceries' to Today tagged Groceries. Added 'return library book' to Today tagged Errands.
- extra actions ['create_todo']

### tasks · multi/interleaved-clauses · `deep` · 38.2 s
- **Said:** [TASKS VIEW] i need to buy some groceries, i need rice and chicken, the chicken i need to get far away, the rice i can get at whole foods
- **Did:** ['create_todo', 'create_todo', 'create_todo', 'create_todo', 'create_todo'] — Added 'buy some groceries' to Today tagged Groceries. Added 'buy rice' to Today tagged Groceries. Added 'buy chicken' to Today tagged Groceries. Added 'get the 
- extra actions ['create_todo', 'create_todo', 'create_todo', 'create_todo']
- expected 2 todos, got 5: ['buy some groceries', 'buy rice', 'buy chicken', 'get the chicken', 'get rice at Whole Foods']

### update-delete · update/move-by-time · `deep` · 18.8 s
- **Said:** move my 1pm meeting tomorrow to 3pm
- **Did:** ['update_event'] — Updated 'Meeting with Tal' successfully.
- expected 'Meeting with Tal' at 15:00; have [('Meeting with Tal', '2026-09-04', '13:00')]

### from-chats · chat-phrasing · `deep` · 18.3 s
- **Said:** night shift on wednesday from 8 pm to 6 am
- **Did:** [] — I couldn't find an event at 20:00 on 2026-09-09.
- missing action create_event (got [])
- no event matching {'date': '2026-09-09', 'start_time': '20:00'} in DB []

### from-chats · chat-phrasing · `fast` · 8.8 s
- **Said:** meeting with Guri moved from 9:30 to 9 on wednesday
- **Did:** [] — I couldn't find an event matching 'guri'.
- missing action create_event|update_event (got [])
- no event matching {} in DB []

## Slowest 10

| s | path | command |
|---:|---|---|
| 208.5 | deep | set a meeting at 4pm today, but it is only 20 minutes meeting with one moment me |
| 162.7 | deep | two events tomorrow, one at four o'clock meeting with Rei and one at seven pm pi |
| 95.3 | deep | add tasks: submit the Haxaga grades, prepare Netivim slides, pay rent |
| 67.4 | deep | a meeting for me tomorrow at two one sorry one pm and four pm and then another o |
| 62.0 | deep | tomorrow: Shacharit at 6:30, Haxaga TA at 12, dinner with Ezra at 8 pm, and remi |
| 51.6 | deep | gym tomorrow at 6 am, tuesday at 6 am and friday at 6 am |
| 51.5 | deep | on thursday I have Shacharit at 6:30 am, a lecture at 10 and dinner with Danny a |
| 43.7 | deep | walk Kyra the dog at 3:30 pm today and then go to shul for Mincha Maariv at 7:30 |
| 43.3 | deep | meeting with Ravid on friday at 4 pm about Haxaga |
| 41.4 | deep | tomorrow gym at 7 am and a meeting with Tal at 11 |

## Raw

Full per-case JSON: `DOCUMENTATION/ASSISTANT_AUDIT.md.json`