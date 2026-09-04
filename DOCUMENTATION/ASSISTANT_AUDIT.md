# Assistant audit — accuracy, latency, self-check

_Generated 2026-09-04 00:11 · 94 commands · scratch DB · vocabulary 374 words · machine arm64. Re-run: `python -m scripts.audit_assistant`._

## Headline

- **Correct after the quick answer:** 80%  ·  **correct once settled (after self-check):** 80% — case-level exact match against this corpus's hand-written expectations, 94 cases, not a real-usage or human-judged figure
- **Recall 78%** (89/114 expected items produced correctly) · **precision 91%** (104/111 produced actions were expected, plus 3 extra task rows beyond what was expected) — accuracy alone doesn't distinguish missing something asked for from producing something extra
- **Time to first result:** p50 8.6 s · p95 28.7 s  ·  **time to settled:** p50 8.6 s · p95 28.7 s
- Parse paths: deep 55, fast 39

## By area

| Area | n | quick ✓ | settled ✓ | recall | precision | first p50 | first p95 | settled p50 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| adversarial | 7 | 57% | 57% | 50% | 100% | 10.5 s | 12.1 s | 10.5 s |
| events | 41 | 93% | 93% | 87% | 98% | 10.2 s | 50.0 s | 10.2 s |
| from-chats | 15 | 80% | 80% | 81% | 100% | 8.3 s | 17.3 s | 8.3 s |
| mixed | 3 | 33% | 33% | 50% | 100% | 0.1 s | 28.2 s | 2.9 s |
| query | 3 | 100% | 100% | 100% | 100% | 0.0 s | 0.0 s | 1.6 s |
| tasks | 18 | 72% | 72% | 74% | 68% | 0.0 s | 26.6 s | 1.9 s |
| update-delete | 7 | 57% | 57% | 57% | 100% | 0.0 s | 14.0 s | 1.9 s |

## By parse path

| Path | n | quick ✓ | settled ✓ | recall | precision | first p50 | first p95 | LLM ms p50 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| deep | 55 | 73% | 73% | 71% | 87% | 11.0 s | 37.9 s | 8896 |
| fast | 39 | 90% | 90% | 90% | 100% | 0.0 s | 0.1 s | 0 |

## Quick answer vs self-check

- Self-check ran on 39 commands; it proposed a correction on 1 (0 applied).
- **Fixed by self-check:** 0  ·  **broken by self-check:** 0

## Engine stages (latency; a slow or misbehaving stage is fixed in ITS module)

| Stage | ran on | ms p50 | ms p95 |
|---|---:|---:|---:|
| vocab | 94/94 | 13 | 28 |
| rule | 92/94 | 15 | 76 |
| llm | 56/94 | 8751 | 32830 |
| validate | 21/94 | 2 | 13 |
| execute | 84/94 | 4 | 14 |
| verify | 55/94 | 2115 | 9651 |

## Named-rule fixes applied

| Rule | times |
|---|---:|
| observance_gate | 18 |
| relative_date_pin | 4 |
| anaphor_guard | 4 |
| recurrence_words | 3 |
| weekly_start_day | 3 |
| due_date_pin | 3 |
| move_time_fill | 2 |
| morning_title_guard | 1 |
| bare_hour_pm | 1 |

## Cross-check (step 6)

- Findings: 7 (missing) across 3 command(s); loop-backs on 3 command(s) (7 re-entries total).
- Budget exhausted (answer flagged as unsure): 2.

## By shape (failures first)

| Shape | n | settled ✓ | first p50 |
|---|---:|---:|---:|
| update/extend | 1 | 0% | 13.7 s |
| multi/same-due-date | 1 | 0% | 10.3 s |
| multi/different-due-dates | 1 | 0% | 18.9 s |
| delete/by-time | 1 | 0% | 5.6 s |
| multi/interleaved-clauses | 1 | 0% | 26.5 s |
| 3events+task | 1 | 0% | 31.3 s |
| misheard-names | 1 | 0% | 12.1 s |
| multi/disfluent-duration | 1 | 0% | 76.8 s |
| multi/self-correction-count | 1 | 0% | 115.1 s |
| event+task | 1 | 0% | 0.1 s |
| multi/same-list-3 | 1 | 0% | 27.2 s |
| event-not-task | 1 | 0% | 0.1 s |
| past-tense-noise | 1 | 0% | 10.5 s |
| single/due-tomorrow | 1 | 0% | 0.0 s |
| update/move-by-time | 1 | 0% | 14.1 s |
| multi/same-day-2 | 3 | 67% | 22.4 s |
| chat-phrasing | 15 | 80% | 8.3 s |
| generated/single | 12 | 100% | 9.7 s |
| multi/different-days | 2 | 100% | 20.1 s |
| delete/by-title | 1 | 100% | 0.0 s |
| task-not-event | 1 | 100% | 0.0 s |
| multi/shared-verb | 1 | 100% | 0.0 s |
| single/due-weekday | 1 | 100% | 0.0 s |
| single/full-name | 1 | 100% | 0.1 s |
| query/today | 1 | 100% | 0.0 s |
| ambiguous/no-time | 1 | 100% | 10.9 s |
| single/spoken-time | 1 | 100% | 12.6 s |
| single/place | 1 | 100% | 10.7 s |
| single/hebrew-term | 2 | 100% | 10.0 s |
| recurring/daily | 1 | 100% | 10.1 s |
| single/range | 1 | 100% | 8.1 s |
| single/next-weekday | 1 | 100% | 0.1 s |
| query/tomorrow | 1 | 100% | 0.0 s |
| task+event | 1 | 100% | 0.1 s |
| single/stop-word | 1 | 100% | 0.1 s |
| single/inferred-tag | 1 | 100% | 0.1 s |
| single/disfluency | 1 | 100% | 14.0 s |
| multi/shared-verb-people | 1 | 100% | 0.0 s |
| single/weekday | 1 | 100% | 9.4 s |
| multi/shared-verb-3 | 1 | 100% | 0.1 s |
| single/explicit-time | 3 | 100% | 0.1 s |
| recurring/weekly | 2 | 100% | 14.9 s |
| multi/different-days-3 | 1 | 100% | 50.0 s |
| single | 2 | 100% | 0.0 s |
| update/move-by-title | 1 | 100% | 0.0 s |
| observance-meal-ok | 1 | 100% | 9.8 s |
| multi/same-list | 2 | 100% | 0.0 s |
| multi/tagged | 1 | 100% | 0.0 s |
| single/general-list | 1 | 100% | 0.0 s |
| multi/same-day-3 | 2 | 100% | 28.1 s |
| single/terse | 1 | 100% | 9.7 s |
| single/duration | 1 | 100% | 0.0 s |
| single/hebrew-name | 1 | 100% | 0.0 s |
| update/rename | 1 | 100% | 0.0 s |
| query/week | 1 | 100% | 0.0 s |
| single/day-of-month | 1 | 100% | 6.9 s |
| single/internal-and | 1 | 100% | 0.1 s |
| observance-gate | 1 | 100% | 11.8 s |
| update/move-day | 1 | 100% | 0.0 s |

## Produced more than expected (precision failures)

Distinct from a wrong or missing answer: the system did something on top of what was asked for — an extra action, or extra rows from one action (a duplicated task from a misread clause is invisible to an action-count check, since the action count can still be right).

- **set a meeting at 4pm today, but it is only 20 minutes meeting with one moment meeting with reards, okay, then let's do another meeting from 6 from 6 o'clock to 640 meetings with kids for project defense** — 1 extra action(s) — got ['create_event', 'create_event', 'create_event']
- **add tasks: submit the Haxaga grades, prepare Netivim slides, pay rent** — 1 extra action(s) — got ['create_todo', 'create_todo']
- **two tasks due tomorrow: buy groceries and return the library book** — 1 extra action(s) — got ['create_todo', 'create_todo']
- **[TASKS VIEW] i need to buy some groceries, i need rice and chicken, the chicken i need to get far away, the rice i can get at whole foods** — 4 extra action(s), 3 extra task row(s) — got ['create_todo', 'create_todo', 'create_todo', 'create_todo', 'create_todo']

## Failures

### events · multi/same-day-2 · `deep` · 22.9 s
- **Said:** two events tomorrow, one at four o'clock meeting with Rei and one at seven pm pizza with Ezra
- **Did:** ['create_event', 'create_event'] — Created event 'Meeting with Rei' on Thursday, Sep 3, 2026 from 4 PM to 5 PM. Created event 'Meeting with Rei' on Thursday, Sep 3, 2026 from 5 PM to 6 PM. I didn
- no event matching {'date': '2026-09-04', 'start_time': '16:00', 'title_contains': 'Rei'} in DB [('Meeting with Rei', '2026-09-03', '16:00'), ('Meeting with Rei', '2026-09-03', '17:00')]
- no event matching {'date': '2026-09-04', 'start_time': '19:00', 'title_contains': 'Ezra'} in DB [('Meeting with Rei', '2026-09-03', '16:00'), ('Meeting with Rei', '2026-09-03', '17:00')]

### events · multi/disfluent-duration · `deep` · 76.8 s
- **Said:** set a meeting at 4pm today, but it is only 20 minutes meeting with one moment meeting with reards, okay, then let's do another meeting from 6 from 6 o'clock to 640 meetings with kids for project defense
- **Did:** ['create_event', 'create_event', 'create_event'] — Created event 'meeting' on Friday, Sep 4, 2026 from 4 PM to 5 PM. Created event 'Meeting with Reards' on Friday, Sep 4, 2026 from 4 PM to 4:20 PM. Created event
- extra actions ['create_event']
- no event matching {'date': '2026-09-03', 'start_time': '16:00', 'end_time': '16:20'} in DB [('meeting', '2026-09-04', '16:00'), ('Meeting with Reards', '2026-09-04', '16:00'), ('Meetings with Kids for Project Defense', '2026-09-04', '18:00')]
- no event matching {'date': '2026-09-03', 'start_time': '18:00', 'end_time': '18:40'} in DB [('meeting', '2026-09-04', '16:00'), ('Meeting with Reards', '2026-09-04', '16:00'), ('Meetings with Kids for Project Defense', '2026-09-04', '18:00')]

### events · multi/self-correction-count · `deep` · 115.1 s
- **Said:** a meeting for me tomorrow at two one sorry one pm and four pm and then another one a pizza party at 6.30 pm at edo's
- **Did:** [] — I'm not sure I caught every part of that — worth a glance. I didn't book 'Meeting': that lands on Shabbat (Saturday, Sep 5) — after 19:37 works. I didn't book '
- missing action create_event (got [])
- missing action create_event (got [])
- missing action create_event (got [])

### tasks · multi/same-list-3 · `deep` · 27.2 s
- **Said:** add tasks: submit the Haxaga grades, prepare Netivim slides, pay rent
- **Did:** ['create_todo', 'create_todo'] — I'm not sure I caught every part of that — worth a glance. Sorry, I didn't understand that. Added 'prepare netivim slides' to Today tagged Work. Added 'pay re
- extra actions ['create_todo']
- no todo containing 'grades' (todos=['prepare netivim slides', 'pay rent'])

### tasks · single/due-tomorrow · `fast` · 0.0 s
- **Said:** remind me tomorrow to send the syllabus to Guri
- **Did:** ['create_todo'] — Added 'send the syllabus to guri' to Today tagged Coursework.
- todo 'send the syllabus to guri' due 2026-09-05 != 2026-09-04

### tasks · multi/same-due-date · `deep` · 10.3 s
- **Said:** two tasks due tomorrow: buy groceries and return the library book
- **Did:** ['create_todo', 'create_todo'] — Added 'buy groceries' to Today tagged Groceries. Added 'return library book' to Today tagged Errands.
- extra actions ['create_todo']
- todo 'buy groceries' due 2026-09-05 != 2026-09-04
- todo 'return library book' due 2026-09-05 != 2026-09-04

### tasks · multi/different-due-dates · `deep` · 18.9 s
- **Said:** add buy a gift for Tamar due thursday and book the driving test due next monday
- **Did:** ['create_todo', 'create_todo'] — Added 'buy a gift for Tamar' to Today. Added 'book driving test' to Today.
- todo 'buy a gift for Tamar' due 2026-09-10 != 2026-09-03

### tasks · multi/interleaved-clauses · `deep` · 26.5 s
- **Said:** [TASKS VIEW] i need to buy some groceries, i need rice and chicken, the chicken i need to get far away, the rice i can get at whole foods
- **Did:** ['create_todo', 'create_todo', 'create_todo', 'create_todo', 'create_todo'] — Added 'buy some groceries' to Today tagged Groceries. Added 'buy rice' to Today tagged Groceries. Added 'buy chicken' to Today tagged Groceries. Added 'get far 
- extra actions ['create_todo', 'create_todo', 'create_todo', 'create_todo']
- expected 2 todos, got 5: ['buy some groceries', 'get rice', 'buy rice', 'buy chicken', 'get far away']

### update-delete · update/move-by-time · `deep` · 14.1 s
- **Said:** move my 1pm meeting tomorrow to 3pm
- **Did:** [] — I couldn't find an event matching 'my 1pm meeting'.
- missing action update_event (got [])
- expected 'Meeting with Tal' at 15:00; have [('Meeting with Tal', '2026-09-04', '13:00')]

### update-delete · update/extend · `deep` · 13.7 s
- **Said:** extend the meeting with Tal tomorrow until 3 pm
- **Did:** [] — I couldn't find an event at 15:00 on 2026-09-05.
- missing action update_event (got [])
- expected 'Meeting with Tal' ending 15:00; have [('Meeting with Tal', '14:00')]

### update-delete · delete/by-time · `fast` · 5.6 s
- **Said:** cancel my 1 pm meeting tomorrow
- **Did:** [] — I couldn't find an event at 13:00 on 2026-09-05.
- missing action delete_event (got [])
- 'Meeting with Tal' still in DB

### mixed · event+task · `fast` · 0.1 s
- **Said:** set a meeting with Ravid tomorrow at 2 pm and remind me to buy a gift for him
- **Did:** ['create_todo'] — I didn't book 'meeting with ravid': that lands on Shabbat (Saturday, Sep 5) — after 19:37 works. Added 'buy a gift for him' to Today.
- missing action create_event (got ['create_todo'])
- no event matching {'date': '2026-09-04', 'start_time': '14:00'} in DB []

### mixed · 3events+task · `deep` · 31.3 s
- **Said:** tomorrow: Shacharit at 6:30, Haxaga TA at 12, dinner with Ezra at 8 pm, and remind me to pay rent
- **Did:** ['create_event', 'create_event', 'create_todo'] — Created event 'Shacharit' on Saturday, Sep 5, 2026 from 6:30 AM to 7:30 AM. I didn't book 'Haxaga TA': that lands on Shabbat (Saturday, Sep 5) — after 19:37 wor
- missing action create_event (got ['create_event', 'create_event', 'create_todo'])
- no event matching {'date': '2026-09-04', 'start_time': '06:30'} in DB [('Shacharit', '2026-09-05', '06:30'), ('Dinner with Ezra', '2026-09-05', '20:00')]
- no event matching {'date': '2026-09-04', 'start_time': '12:00'} in DB [('Shacharit', '2026-09-05', '06:30'), ('Dinner with Ezra', '2026-09-05', '20:00')]

### adversarial · event-not-task · `fast` · 0.1 s
- **Said:** remind me about the dentist tomorrow at 9 am
- **Did:** [] — I didn't book 'dentist': that lands on Shabbat (Saturday, Sep 5) — after 19:37 works.
- missing action create_event (got [])
- no event matching {'date': '2026-09-04', 'start_time': '09:00'} in DB []

### adversarial · misheard-names · `deep` · 12.1 s
- **Said:** meet Ravid at the french bakery in Jerusalem after shacharis at 9 am tomorrow
- **Did:** ['create_event'] — Created event 'Meet Ravid' on Saturday, Sep 5, 2026 from 9 AM to 10 AM.
- no event matching {'date': '2026-09-04', 'start_time': '09:00', 'title_contains': 'Ravid'} in DB [('Meet Ravid', '2026-09-05', '09:00')]
- vocab corrections: [{'from': 'shacharis', 'reason': 'alias', 'score': 1.0, 'to': 'Shacharit'}, {'from': 'Ravid', 'reason': 'alias', 'score': 1.0, 'to': 'Ravid'}, {'from': 'Jerusalem', 'reason': 'alias', 'score': 1.0, 'to': 'Jerusalem'}]

### adversarial · past-tense-noise · `deep` · 10.5 s
- **Said:** I had a meeting today at 8:30 pm with Nurit to work on the project
- **Did:** [] — I didn't book 'Meeting with Nurit to work on the project': that lands on Shabbat (Friday, Sep 4).
- missing action create_event|update_event|clarify (got [])
- no event matching {} in DB []

### from-chats · chat-phrasing · `deep` · 8.3 s
- **Said:** zoom with Alon thursday at 3 pm
- **Did:** ['create_event'] — Created event 'Zoom with Alon' on Thursday, Sep 10, 2026 from 3 PM to 4 PM.
- no event matching {'date': '2026-09-03', 'start_time': '15:00', 'title_contains': 'Alon'} in DB [('Zoom with Alon', '2026-09-10', '15:00')]

### from-chats · chat-phrasing · `deep` · 7.2 s
- **Said:** lunch 12:30 with Tal on campus tomorrow
- **Did:** ['create_event'] — Created event 'Lunch with Tal' on Saturday, Sep 5, 2026 from 12:30 PM to 1:30 PM.
- no event matching {'date': '2026-09-04', 'start_time': '12:30', 'title_contains': 'Tal'} in DB [('Lunch with Tal', '2026-09-05', '12:30')]

### from-chats · chat-phrasing · `deep` · 8.7 s
- **Said:** Netivim zoom 1800-2000 tonight
- **Did:** ['create_event'] — Created event 'Netivim Zoom' on Friday, Sep 4, 2026 from 6 PM to 8 PM.
- no event matching {'date': '2026-09-03', 'start_time': '18:00', 'end_time': '20:00'} in DB [('Netivim Zoom', '2026-09-04', '18:00')]

## Slowest 10

| s | path | command |
|---:|---|---|
| 115.1 | deep | a meeting for me tomorrow at two one sorry one pm and four pm and then another o |
| 76.8 | deep | set a meeting at 4pm today, but it is only 20 minutes meeting with one moment me |
| 50.0 | deep | gym tomorrow at 6 am, tuesday at 6 am and friday at 6 am |
| 32.7 | deep | on thursday I have Shacharit at 6:30 am, a lecture at 10 and dinner with Danny a |
| 31.3 | deep | tomorrow: Shacharit at 6:30, Haxaga TA at 12, dinner with Ezra at 8 pm, and remi |
| 27.2 | deep | add tasks: submit the Haxaga grades, prepare Netivim slides, pay rent |
| 26.5 | deep | [TASKS VIEW] i need to buy some groceries, i need rice and chicken, the chicken  |
| 23.5 | deep | set a meeting tomorrow at 1 pm, another one at 4 pm and then pizza at 6:30 pm to |
| 22.9 | deep | two events tomorrow, one at four o'clock meeting with Rei and one at seven pm pi |
| 22.4 | deep | walk Kyra the dog at 3:30 pm today and then go to shul for Mincha Maariv at 7:30 |

## Raw

Full per-case JSON: `DOCUMENTATION/ASSISTANT_AUDIT.md.json`