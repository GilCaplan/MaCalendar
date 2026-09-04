# Assistant audit — accuracy, latency, self-check

_Generated 2026-09-03 13:57 · 92 commands · scratch DB · vocabulary 374 words · machine arm64. Re-run: `python -m scripts.audit_assistant`._

## Headline

- **Correct after the quick answer:** 93%  ·  **correct once settled (after self-check):** 93% — case-level exact match against this corpus's hand-written expectations, 92 cases, not a real-usage or human-judged figure
- **Recall 92%** (104/113 expected items produced correctly) · **precision 96%** (108/110 produced actions were expected, plus 2 extra task rows beyond what was expected) — accuracy alone doesn't distinguish missing something asked for from producing something extra
- **Time to first result:** p50 7.1 s · p95 14.8 s  ·  **time to settled:** p50 18.9 s · p95 32.2 s
- Parse paths: rule 39, hybrid 10, llm 43, error 0

## By area

| Area | n | quick ✓ | settled ✓ | recall | precision | first p50 | first p95 | settled p50 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| adversarial | 5 | 100% | 100% | 100% | 100% | 9.3 s | 12.7 s | 21.1 s |
| events | 41 | 93% | 93% | 89% | 100% | 8.8 s | 15.4 s | 22.4 s |
| from-chats | 15 | 87% | 87% | 88% | 100% | 6.7 s | 11.4 s | 17.1 s |
| mixed | 3 | 100% | 100% | 100% | 100% | 0.1 s | 20.2 s | 10.8 s |
| query | 3 | 100% | 100% | 100% | 100% | 0.0 s | 0.0 s | 3.8 s |
| tasks | 18 | 94% | 94% | 95% | 83% | 0.0 s | 14.2 s | 7.9 s |
| update-delete | 7 | 100% | 100% | 100% | 100% | 0.0 s | 9.4 s | 7.7 s |

## By parse path

| Path | n | quick ✓ | settled ✓ | recall | precision | first p50 | first p95 | LLM ms p50 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| rule | 39 | 97% | 97% | 98% | 100% | 0.0 s | 3.5 s | 0 |
| hybrid | 10 | 90% | 90% | 92% | 100% | 10.1 s | 15.1 s | 10091 |
| llm | 43 | 91% | 91% | 88% | 93% | 10.2 s | 15.4 s | 10109 |

## Quick answer vs self-check

- Self-check ran on 92 commands; it proposed a correction on 42 (0 applied).
- **Fixed by self-check:** 0  ·  **broken by self-check:** 0

## By shape (failures first)

| Shape | n | settled ✓ | first p50 |
|---|---:|---:|---:|
| multi/interleaved-clauses | 1 | 0% | 11.2 s |
| multi/disfluent-duration | 1 | 0% | 11.6 s |
| multi/self-correction-count | 1 | 0% | 14.1 s |
| multi/same-day-3 | 2 | 50% | 13.5 s |
| chat-phrasing | 15 | 87% | 6.7 s |
| 3events+task | 1 | 100% | 22.4 s |
| single/due-weekday | 1 | 100% | 0.0 s |
| single/hebrew-term | 2 | 100% | 12.3 s |
| misheard-names | 1 | 100% | 9.7 s |
| query/tomorrow | 1 | 100% | 0.0 s |
| multi/different-days-3 | 1 | 100% | 15.3 s |
| update/rename | 1 | 100% | 0.0 s |
| single/spoken-time | 1 | 100% | 13.7 s |
| ambiguous/no-time | 1 | 100% | 9.3 s |
| delete/by-title | 1 | 100% | 0.0 s |
| single/place | 1 | 100% | 12.6 s |
| multi/same-day-2 | 3 | 100% | 12.2 s |
| multi/shared-verb-3 | 1 | 100% | 0.1 s |
| query/week | 1 | 100% | 0.0 s |
| multi/tagged | 1 | 100% | 0.0 s |
| generated/single | 12 | 100% | 8.0 s |
| past-tense-noise | 1 | 100% | 13.5 s |
| task-not-event | 1 | 100% | 0.0 s |
| single/inferred-tag | 1 | 100% | 0.0 s |
| single/duration | 1 | 100% | 0.0 s |
| recurring/daily | 1 | 100% | 7.1 s |
| recurring/weekly | 2 | 100% | 7.1 s |
| multi/same-list | 2 | 100% | 0.0 s |
| update/extend | 1 | 100% | 9.6 s |
| multi/different-days | 2 | 100% | 15.0 s |
| multi/same-list-3 | 1 | 100% | 7.7 s |
| delete/by-time | 1 | 100% | 0.0 s |
| query/today | 1 | 100% | 0.0 s |
| task+event | 1 | 100% | 0.1 s |
| update/move-by-time | 1 | 100% | 9.0 s |
| single/due-tomorrow | 1 | 100% | 0.0 s |
| single/range | 1 | 100% | 8.8 s |
| single/disfluency | 1 | 100% | 10.8 s |
| multi/same-due-date | 1 | 100% | 14.4 s |
| single/explicit-time | 3 | 100% | 0.0 s |
| multi/different-due-dates | 1 | 100% | 14.2 s |
| single/weekday | 1 | 100% | 8.0 s |
| single/general-list | 1 | 100% | 0.1 s |
| event+task | 1 | 100% | 0.1 s |
| single/stop-word | 1 | 100% | 7.4 s |
| single/full-name | 1 | 100% | 0.1 s |
| single/terse | 1 | 100% | 11.3 s |
| single/hebrew-name | 1 | 100% | 0.1 s |
| single/day-of-month | 1 | 100% | 12.7 s |
| single | 2 | 100% | 0.0 s |
| event-not-task | 1 | 100% | 0.0 s |
| single/next-weekday | 1 | 100% | 3.2 s |
| update/move-day | 1 | 100% | 0.0 s |
| multi/shared-verb-people | 1 | 100% | 0.0 s |
| single/internal-and | 1 | 100% | 0.0 s |
| update/move-by-title | 1 | 100% | 0.1 s |
| multi/shared-verb | 1 | 100% | 0.0 s |

## Produced more than expected (precision failures)

Distinct from a wrong or missing answer: the system did something on top of what was asked for — an extra action, or extra rows from one action (a duplicated task from a misread clause is invisible to an action-count check, since the action count can still be right).

- **[TASKS VIEW] i need to buy some groceries, i need rice and chicken, the chicken i need to get far away, the rice i can get at whole foods** — 2 extra action(s), 2 extra task row(s) — got ['create_todo', 'create_todo', 'create_todo']

## Failures

### events · multi/same-day-3 · `llm` · 10.2 s
- **Said:** on thursday I have Shacharit at 6:30 am, a lecture at 10 and dinner with Danny at 8 pm
- **Did:** ['create_event'] — Created event 'Shacharit' on Thursday, Sep 3, 2026 from 6:30 AM to 7:30 AM.
- missing action create_event (got ['create_event'])
- missing action create_event (got ['create_event'])
- no event matching {'date': '2026-09-03', 'start_time': '10:00'} in DB [('Shacharit', '2026-09-03', '06:30')]

### events · multi/disfluent-duration · `llm` · 11.6 s
- **Said:** set a meeting at 4pm today, but it is only 20 minutes meeting with one moment meeting with reards, okay, then let's do another meeting from 6 from 6 o'clock to 640 meetings with kids for project defense
- **Did:** ['create_event', 'create_event'] — Created event 'Meeting with Reards' on Thursday, Sep 3, 2026 from 4 PM to 4:20 PM. Created event 'Meetings with kids for project defense' on Thursday, Sep 3, 20
- no event matching {'date': '2026-09-03', 'start_time': '18:00', 'end_time': '18:40'} in DB [('Meeting with Reards', '2026-09-03', '16:00'), ('Meetings with kids for project defense', '2026-09-03', '18:00')]

### events · multi/self-correction-count · `llm` · 14.1 s
- **Said:** a meeting for me tomorrow at two one sorry one pm and four pm and then another one a pizza party at 6.30 pm at edo's
- **Did:** ['create_event', 'create_event'] — Created event 'Meeting' on Friday, Sep 4, 2026 from 1 PM to 4 PM. Created event 'Pizza Party' on Friday, Sep 4, 2026 from 6:30 PM to 7:30 PM.
- missing action create_event (got ['create_event', 'create_event'])
- no event matching {'date': '2026-09-04', 'start_time': '13:00', 'end_time': '14:00'} in DB [('Meeting', '2026-09-04', '13:00'), ('Pizza Party', '2026-09-04', '18:30')]
- no event matching {'date': '2026-09-04', 'start_time': '16:00', 'end_time': '17:00'} in DB [('Meeting', '2026-09-04', '13:00'), ('Pizza Party', '2026-09-04', '18:30')]

### tasks · multi/interleaved-clauses · `llm` · 11.2 s
- **Said:** [TASKS VIEW] i need to buy some groceries, i need rice and chicken, the chicken i need to get far away, the rice i can get at whole foods
- **Did:** ['create_todo', 'create_todo', 'create_todo'] — Added 'buy rice' and 'buy chicken' to Today tagged Groceries. Added 'get chicken far away' to Today tagged Groceries. Added 'buy rice at whole foods' to Today t
- extra actions ['create_todo', 'create_todo']
- expected 2 todos, got 4: ['buy rice', 'buy chicken', 'get chicken far away', 'buy rice at whole foods']

### from-chats · chat-phrasing · `hybrid` · 10.7 s
- **Said:** night shift tomorrow from 8 pm to 6 am
- **Did:** [] — I couldn't find an event matching 'night shift'.
- missing action create_event (got [])
- no event matching {'date': '2026-09-04', 'start_time': '20:00'} in DB []

### from-chats · chat-phrasing · `rule` · 6.4 s
- **Said:** meeting with Guri moved from 9:30 to 9 on wednesday
- **Did:** [] — I couldn't find an event matching 'guri'.
- missing action create_event|update_event (got [])
- no event matching {} in DB []

## Slowest 10

| s | path | command |
|---:|---|---|
| 22.4 | llm | tomorrow: Shacharit at 6:30, Haxaga TA at 12, dinner with Ezra at 8 pm, and remi |
| 16.7 | llm | set a meeting tomorrow at 1 pm, another one at 4 pm and then pizza at 6:30 pm to |
| 15.6 | hybrid | set lunch with Tal on monday at noon and coffee with Ezra on friday at 9 |
| 15.4 | llm | tomorrow gym at 7 am and a meeting with Tal at 11 |
| 15.3 | llm | gym tomorrow at 6 am, tuesday at 6 am and friday at 6 am |
| 14.4 | hybrid | two tasks due tomorrow: buy groceries and return the library book |
| 14.4 | llm | meeting with Ravid tomorrow at 2 pm and dentist on thursday at 9 am |
| 14.2 | hybrid | add buy a gift for Tamar due thursday and book the driving test due next monday |
| 14.1 | llm | a meeting for me tomorrow at two one sorry one pm and four pm and then another o |
| 13.7 | hybrid | book a haircut for tuesday at half past two |

## Raw

Full per-case JSON: `DOCUMENTATION/experiments/memory_scaling/A_k8.md.json`