# Assistant audit — accuracy, latency, self-check

_Generated 2026-09-03 21:09 · 94 commands · scratch DB · vocabulary 374 words · machine arm64. Re-run: `python -m scripts.audit_assistant`._

## Headline

- **Correct after the quick answer:** 91%  ·  **correct once settled (after self-check):** 91% — case-level exact match against this corpus's hand-written expectations, 94 cases, not a real-usage or human-judged figure
- **Recall 93%** (106/114 expected items produced correctly) · **precision 91%** (114/122 produced actions were expected, plus 3 extra task rows beyond what was expected) — accuracy alone doesn't distinguish missing something asked for from producing something extra
- **Time to first result:** p50 5.3 s · p95 22.1 s  ·  **time to settled:** p50 5.6 s · p95 22.1 s
- Parse paths: deep 55, fast 39

## By area

| Area | n | quick ✓ | settled ✓ | recall | precision | first p50 | first p95 | settled p50 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| adversarial | 7 | 100% | 100% | 100% | 100% | 6.2 s | 6.8 s | 6.2 s |
| events | 41 | 93% | 93% | 93% | 96% | 6.6 s | 65.9 s | 6.6 s |
| from-chats | 15 | 93% | 93% | 94% | 100% | 6.0 s | 11.7 s | 6.0 s |
| mixed | 3 | 100% | 100% | 100% | 100% | 0.1 s | 21.4 s | 2.7 s |
| query | 3 | 100% | 100% | 100% | 100% | 0.0 s | 0.0 s | 1.3 s |
| tasks | 18 | 83% | 83% | 89% | 68% | 0.0 s | 20.7 s | 1.7 s |
| update-delete | 7 | 86% | 86% | 86% | 100% | 0.0 s | 6.2 s | 1.6 s |

## By parse path

| Path | n | quick ✓ | settled ✓ | recall | precision | first p50 | first p95 | LLM ms p50 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| deep | 55 | 87% | 87% | 90% | 87% | 6.6 s | 37.1 s | 4763 |
| fast | 39 | 97% | 97% | 98% | 100% | 0.0 s | 0.1 s | 0 |

## Quick answer vs self-check

- Self-check ran on 39 commands; it proposed a correction on 1 (0 applied).
- **Fixed by self-check:** 0  ·  **broken by self-check:** 0

## Engine stages (latency; a slow or misbehaving stage is fixed in ITS module)

| Stage | ran on | ms p50 | ms p95 |
|---|---:|---:|---:|
| vocab | 94/94 | 13 | 25 |
| rule | 92/94 | 15 | 49 |
| llm | 55/94 | 4763 | 29109 |
| validate | 13/94 | 2 | 15 |
| execute | 90/94 | 4 | 14 |
| verify | 55/94 | 1862 | 8477 |

## Named-rule fixes applied

| Rule | times |
|---|---:|
| observance_gate | 5 |
| relative_date_pin | 4 |
| anaphor_guard | 4 |
| due_date_pin | 3 |
| recurrence_words | 1 |
| weekly_start_day | 1 |
| bare_hour_pm | 1 |

## Cross-check (step 6)

- Findings: 15 (extra, missing) across 4 command(s); loop-backs on 4 command(s) (12 re-entries total).
- Budget exhausted (answer flagged as unsure): 4.

## By shape (failures first)

| Shape | n | settled ✓ | first p50 |
|---|---:|---:|---:|
| update/move-by-time | 1 | 0% | 5.2 s |
| multi/disfluent-duration | 1 | 0% | 66.6 s |
| multi/same-due-date | 1 | 0% | 7.5 s |
| multi/same-list-3 | 1 | 0% | 24.7 s |
| multi/interleaved-clauses | 1 | 0% | 20.0 s |
| multi/self-correction-count | 1 | 0% | 87.5 s |
| multi/same-day-2 | 3 | 67% | 13.8 s |
| chat-phrasing | 15 | 93% | 6.0 s |
| multi/different-days | 2 | 100% | 11.6 s |
| single/next-weekday | 1 | 100% | 0.1 s |
| event-not-task | 1 | 100% | 0.1 s |
| misheard-names | 1 | 100% | 6.3 s |
| update/move-by-title | 1 | 100% | 0.0 s |
| delete/by-time | 1 | 100% | 0.0 s |
| query/tomorrow | 1 | 100% | 0.0 s |
| single/weekday | 1 | 100% | 8.3 s |
| recurring/weekly | 2 | 100% | 5.9 s |
| single/hebrew-term | 2 | 100% | 5.6 s |
| single/place | 1 | 100% | 5.9 s |
| update/rename | 1 | 100% | 0.0 s |
| recurring/daily | 1 | 100% | 5.3 s |
| update/move-day | 1 | 100% | 0.0 s |
| query/week | 1 | 100% | 0.0 s |
| single/stop-word | 1 | 100% | 0.0 s |
| single/full-name | 1 | 100% | 0.1 s |
| single/duration | 1 | 100% | 0.0 s |
| single/terse | 1 | 100% | 4.8 s |
| multi/same-list | 2 | 100% | 0.1 s |
| task+event | 1 | 100% | 0.1 s |
| single/hebrew-name | 1 | 100% | 0.0 s |
| single | 2 | 100% | 0.0 s |
| ambiguous/no-time | 1 | 100% | 4.3 s |
| multi/shared-verb | 1 | 100% | 0.0 s |
| multi/different-due-dates | 1 | 100% | 11.4 s |
| single/spoken-time | 1 | 100% | 5.2 s |
| single/general-list | 1 | 100% | 0.0 s |
| event+task | 1 | 100% | 0.1 s |
| query/today | 1 | 100% | 0.0 s |
| single/disfluency | 1 | 100% | 10.8 s |
| single/internal-and | 1 | 100% | 0.1 s |
| generated/single | 12 | 100% | 6.6 s |
| observance-gate | 1 | 100% | 6.2 s |
| single/day-of-month | 1 | 100% | 9.1 s |
| multi/tagged | 1 | 100% | 0.1 s |
| delete/by-title | 1 | 100% | 0.0 s |
| multi/different-days-3 | 1 | 100% | 18.0 s |
| past-tense-noise | 1 | 100% | 6.9 s |
| observance-meal-ok | 1 | 100% | 6.5 s |
| multi/same-day-3 | 2 | 100% | 17.3 s |
| update/extend | 1 | 100% | 6.6 s |
| single/due-tomorrow | 1 | 100% | 0.0 s |
| multi/shared-verb-people | 1 | 100% | 0.0 s |
| multi/shared-verb-3 | 1 | 100% | 0.1 s |
| task-not-event | 1 | 100% | 0.0 s |
| single/due-weekday | 1 | 100% | 0.0 s |
| single/inferred-tag | 1 | 100% | 0.0 s |
| single/explicit-time | 3 | 100% | 0.0 s |
| 3events+task | 1 | 100% | 23.7 s |
| single/range | 1 | 100% | 8.7 s |

## Produced more than expected (precision failures)

Distinct from a wrong or missing answer: the system did something on top of what was asked for — an extra action, or extra rows from one action (a duplicated task from a misread clause is invisible to an action-count check, since the action count can still be right).

- **two events tomorrow, one at four o'clock meeting with Rei and one at seven pm pizza with Ezra** — 1 extra action(s) — got ['create_event', 'create_event', 'create_event']
- **set a meeting at 4pm today, but it is only 20 minutes meeting with one moment meeting with reards, okay, then let's do another meeting from 6 from 6 o'clock to 640 meetings with kids for project defense** — 1 extra action(s) — got ['create_event', 'create_event', 'create_event']
- **add tasks: submit the Haxaga grades, prepare Netivim slides, pay rent** — 1 extra action(s) — got ['create_todo', 'create_todo']
- **two tasks due tomorrow: buy groceries and return the library book** — 1 extra action(s) — got ['create_todo', 'create_todo']
- **[TASKS VIEW] i need to buy some groceries, i need rice and chicken, the chicken i need to get far away, the rice i can get at whole foods** — 4 extra action(s), 3 extra task row(s) — got ['create_todo', 'create_todo', 'create_todo', 'create_todo', 'create_todo']

## Failures

### events · multi/same-day-2 · `deep` · 65.9 s
- **Said:** two events tomorrow, one at four o'clock meeting with Rei and one at seven pm pizza with Ezra
- **Did:** ['create_event', 'create_event', 'create_event'] — I'm not sure I caught every part of that — worth a glance. Created event 'Event 1' on Friday, Sep 4, 2026 from 10 AM to 11 AM. Created event 'Event 2' on Friday
- extra actions ['create_event']
- no event matching {'date': '2026-09-04', 'start_time': '19:00', 'title_contains': 'Ezra'} in DB [('Event 1', '2026-09-04', '10:00'), ('Event 2', '2026-09-04', '14:00'), ('Meeting with Rei', '2026-09-04', '16:00')]

### events · multi/disfluent-duration · `deep` · 66.6 s
- **Said:** set a meeting at 4pm today, but it is only 20 minutes meeting with one moment meeting with reards, okay, then let's do another meeting from 6 from 6 o'clock to 640 meetings with kids for project defense
- **Did:** ['create_event', 'create_event', 'create_event'] — I'm not sure I caught every part of that — worth a glance. Created event 'meeting with meeting and reards' on Thursday, Sep 3, 2026 from 4 PM to 5 PM. Created r
- extra actions ['create_event']
- no event matching {'date': '2026-09-03', 'start_time': '16:00', 'end_time': '16:20'} in DB [('meeting with meeting and reards', '2026-09-03', '16:00'), ('Meeting with kids for project defense', '2026-09-03', '18:00'), ('Meeting with kids for project defense', '2026-09-03', '18:00'), ('Meeting with kids for project defense', '2026-09-04', '18:00'), ('Meeting with kids for project defense', '2026-09-04', '18:00'), ('Meeting with kids for project defense', '2026-09-06', '18:00')]
- no event matching {'date': '2026-09-03', 'start_time': '18:00', 'end_time': '18:40'} in DB [('meeting with meeting and reards', '2026-09-03', '16:00'), ('Meeting with kids for project defense', '2026-09-03', '18:00'), ('Meeting with kids for project defense', '2026-09-03', '18:00'), ('Meeting with kids for project defense', '2026-09-04', '18:00'), ('Meeting with kids for project defense', '2026-09-04', '18:00'), ('Meeting with kids for project defense', '2026-09-06', '18:00')]

### events · multi/self-correction-count · `deep` · 87.5 s
- **Said:** a meeting for me tomorrow at two one sorry one pm and four pm and then another one a pizza party at 6.30 pm at edo's
- **Did:** ['create_event', 'create_event', 'create_event'] — I'm not sure I caught every part of that — worth a glance. Created event 'Meeting' on Friday, Sep 4, 2026 from 2 PM to 3 PM. Created event 'Meeting' on Friday, 
- no event matching {'date': '2026-09-04', 'start_time': '13:00', 'end_time': '14:00'} in DB [('Meeting', '2026-09-04', '14:00'), ('Meeting', '2026-09-04', '16:00'), ('Pizza Party', '2026-09-04', '18:30')]

### tasks · multi/same-list-3 · `deep` · 24.7 s
- **Said:** add tasks: submit the Haxaga grades, prepare Netivim slides, pay rent
- **Did:** ['create_todo', 'create_todo'] — I'm not sure I caught every part of that — worth a glance. Sorry, I didn't understand that. Added 'prepare netivim slides' to Today tagged Work. Added 'pay re
- extra actions ['create_todo']
- no todo containing 'grades' (todos=['prepare netivim slides', 'pay rent'])

### tasks · multi/same-due-date · `deep` · 7.5 s
- **Said:** two tasks due tomorrow: buy groceries and return the library book
- **Did:** ['create_todo', 'create_todo'] — Added 'buy groceries' to Today tagged Groceries. Added 'return the library book' to Today tagged Errands.
- extra actions ['create_todo']

### tasks · multi/interleaved-clauses · `deep` · 20.0 s
- **Said:** [TASKS VIEW] i need to buy some groceries, i need rice and chicken, the chicken i need to get far away, the rice i can get at whole foods
- **Did:** ['create_todo', 'create_todo', 'create_todo', 'create_todo', 'create_todo'] — Added 'buy some groceries' to Today tagged Groceries. Added 'buy rice' to Today tagged Groceries. Added 'buy chicken' to Today tagged Groceries. Added 'get chic
- extra actions ['create_todo', 'create_todo', 'create_todo', 'create_todo']
- expected 2 todos, got 5: ['buy some groceries', 'buy rice', 'buy chicken', 'get chicken', 'buy rice']

### update-delete · update/move-by-time · `deep` · 5.2 s
- **Said:** move my 1pm meeting tomorrow to 3pm
- **Did:** ['update_event'] — Updated 'Meeting with Tal' successfully.
- expected 'Meeting with Tal' at 15:00; have [('Meeting with Tal', '2026-09-04', '13:00')]

### from-chats · chat-phrasing · `fast` · 0.0 s
- **Said:** meeting with Guri moved from 9:30 to 9 on wednesday
- **Did:** ['update_event'] — Updated 'Meeting with Guri Karpas' successfully.
- expected 'Guri' at 09:00; have [('Meeting with Guri Karpas', '2026-09-09', '09:30')]

## Slowest 10

| s | path | command |
|---:|---|---|
| 87.5 | deep | a meeting for me tomorrow at two one sorry one pm and four pm and then another o |
| 66.6 | deep | set a meeting at 4pm today, but it is only 20 minutes meeting with one moment me |
| 65.9 | deep | two events tomorrow, one at four o'clock meeting with Rei and one at seven pm pi |
| 24.7 | deep | add tasks: submit the Haxaga grades, prepare Netivim slides, pay rent |
| 23.7 | deep | tomorrow: Shacharit at 6:30, Haxaga TA at 12, dinner with Ezra at 8 pm, and remi |
| 21.1 | deep | on thursday I have Shacharit at 6:30 am, a lecture at 10 and dinner with Danny a |
| 20.0 | deep | [TASKS VIEW] i need to buy some groceries, i need rice and chicken, the chicken  |
| 18.0 | deep | gym tomorrow at 6 am, tuesday at 6 am and friday at 6 am |
| 14.4 | deep | sadna on sunday the 15th at 9 am then driving lesson at 8 am |
| 13.8 | deep | meeting with Ravid tomorrow at 2 pm and dentist on thursday at 9 am |

## Raw

Full per-case JSON: `DOCUMENTATION/ASSISTANT_AUDIT.md.json`