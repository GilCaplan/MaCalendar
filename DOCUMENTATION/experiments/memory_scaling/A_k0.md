# Assistant audit — accuracy, latency, self-check

_Generated 2026-09-03 12:42 · 92 commands · scratch DB · vocabulary 374 words · machine arm64. Re-run: `python -m scripts.audit_assistant`._

## Headline

- **Correct after the quick answer:** 92%  ·  **correct once settled (after self-check):** 92%
- **Time to first result:** p50 4.5 s · p95 12.6 s  ·  **time to settled:** p50 12.8 s · p95 22.0 s
- Parse paths: rule 39, hybrid 8, llm 45, error 0

## By area

| Area | n | quick ✓ | settled ✓ | first p50 | first p95 | settled p50 |
|---|---:|---:|---:|---:|---:|---:|
| adversarial | 5 | 100% | 100% | 6.0 s | 7.7 s | 14.4 s |
| events | 41 | 95% | 95% | 5.3 s | 13.6 s | 13.1 s |
| from-chats | 15 | 87% | 87% | 5.1 s | 11.0 s | 14.1 s |
| mixed | 3 | 100% | 100% | 0.1 s | 19.0 s | 1.6 s |
| query | 3 | 100% | 100% | 0.0 s | 0.0 s | 0.8 s |
| tasks | 18 | 89% | 89% | 0.0 s | 7.6 s | 1.3 s |
| update-delete | 7 | 86% | 86% | 0.1 s | 5.9 s | 1.3 s |

## By parse path

| Path | n | quick ✓ | settled ✓ | first p50 | first p95 | LLM ms p50 |
|---|---:|---:|---:|---:|---:|---:|
| rule | 39 | 97% | 97% | 0.1 s | 1.7 s | 0 |
| hybrid | 8 | 75% | 75% | 5.9 s | 11.7 s | 5768 |
| llm | 45 | 91% | 91% | 5.8 s | 13.5 s | 5748 |

## Quick answer vs self-check

- Self-check ran on 92 commands; it proposed a correction on 5 (0 applied).
- **Fixed by self-check:** 0  ·  **broken by self-check:** 0

## By shape (failures first)

| Shape | n | settled ✓ | first p50 |
|---|---:|---:|---:|
| multi/same-due-date | 1 | 0% | 7.0 s |
| update/move-by-time | 1 | 0% | 5.1 s |
| multi/disfluent-duration | 1 | 0% | 11.3 s |
| multi/interleaved-clauses | 1 | 0% | 10.9 s |
| multi/self-correction-count | 1 | 0% | 13.8 s |
| chat-phrasing | 15 | 87% | 5.1 s |
| multi/same-list | 2 | 100% | 0.0 s |
| single/hebrew-name | 1 | 100% | 0.0 s |
| ambiguous/no-time | 1 | 100% | 8.0 s |
| single/weekday | 1 | 100% | 4.5 s |
| past-tense-noise | 1 | 100% | 6.0 s |
| multi/shared-verb-3 | 1 | 100% | 0.1 s |
| update/move-by-title | 1 | 100% | 0.1 s |
| recurring/daily | 1 | 100% | 5.7 s |
| single/day-of-month | 1 | 100% | 5.3 s |
| update/move-day | 1 | 100% | 0.0 s |
| 3events+task | 1 | 100% | 21.1 s |
| delete/by-title | 1 | 100% | 0.0 s |
| single/spoken-time | 1 | 100% | 4.0 s |
| single/next-weekday | 1 | 100% | 1.9 s |
| single | 2 | 100% | 0.1 s |
| single/internal-and | 1 | 100% | 0.0 s |
| event-not-task | 1 | 100% | 0.1 s |
| multi/tagged | 1 | 100% | 0.1 s |
| update/extend | 1 | 100% | 6.2 s |
| task+event | 1 | 100% | 0.1 s |
| single/place | 1 | 100% | 4.4 s |
| multi/same-day-2 | 3 | 100% | 8.9 s |
| single/explicit-time | 3 | 100% | 0.1 s |
| multi/shared-verb | 1 | 100% | 0.0 s |
| query/tomorrow | 1 | 100% | 0.0 s |
| event+task | 1 | 100% | 0.1 s |
| single/inferred-tag | 1 | 100% | 0.0 s |
| single/due-tomorrow | 1 | 100% | 0.0 s |
| multi/shared-verb-people | 1 | 100% | 0.0 s |
| single/full-name | 1 | 100% | 0.1 s |
| recurring/weekly | 2 | 100% | 4.4 s |
| update/rename | 1 | 100% | 0.1 s |
| single/stop-word | 1 | 100% | 1.7 s |
| query/today | 1 | 100% | 0.0 s |
| single/duration | 1 | 100% | 0.0 s |
| single/terse | 1 | 100% | 3.7 s |
| multi/different-due-dates | 1 | 100% | 6.7 s |
| multi/different-days-3 | 1 | 100% | 12.0 s |
| multi/same-day-3 | 2 | 100% | 13.4 s |
| single/hebrew-term | 2 | 100% | 4.1 s |
| query/week | 1 | 100% | 0.0 s |
| delete/by-time | 1 | 100% | 0.0 s |
| misheard-names | 1 | 100% | 6.3 s |
| single/due-weekday | 1 | 100% | 0.0 s |
| single/range | 1 | 100% | 5.2 s |
| multi/different-days | 2 | 100% | 11.6 s |
| single/general-list | 1 | 100% | 0.0 s |
| generated/single | 12 | 100% | 5.3 s |
| multi/same-list-3 | 1 | 100% | 4.7 s |
| single/disfluency | 1 | 100% | 5.4 s |
| task-not-event | 1 | 100% | 0.1 s |

## Failures

### events · multi/disfluent-duration · `llm` · 11.3 s
- **Said:** set a meeting at 4pm today, but it is only 20 minutes meeting with one moment meeting with reards, okay, then let's do another meeting from 6 from 6 o'clock to 640 meetings with kids for project defense
- **Did:** ['create_event', 'create_event'] — Created event 'Meeting with Reards' on Thursday, Sep 3, 2026 from 4 PM to 4:20 PM. Created event 'Meeting with kids for project defense' on Thursday, Sep 3, 202
- no event matching {'date': '2026-09-03', 'start_time': '18:00', 'end_time': '18:40'} in DB [('Meeting with Reards', '2026-09-03', '16:00'), ('Meeting with kids for project defense', '2026-09-03', '18:00')]

### events · multi/self-correction-count · `llm` · 13.8 s
- **Said:** a meeting for me tomorrow at two one sorry one pm and four pm and then another one a pizza party at 6.30 pm at edo's
- **Did:** ['create_event', 'create_event'] — Created event 'Meeting' on Friday, Sep 4, 2026 from 1 PM to 4 PM. Created event 'Pizza Party' on Friday, Sep 4, 2026 from 6:30 PM to 7:30 PM.
- missing action create_event (got ['create_event', 'create_event'])
- no event matching {'date': '2026-09-04', 'start_time': '13:00', 'end_time': '14:00'} in DB [('Meeting', '2026-09-04', '13:00'), ('Pizza Party', '2026-09-04', '18:30')]
- no event matching {'date': '2026-09-04', 'start_time': '16:00', 'end_time': '17:00'} in DB [('Meeting', '2026-09-04', '13:00'), ('Pizza Party', '2026-09-04', '18:30')]

### tasks · multi/same-due-date · `hybrid` · 7.0 s
- **Said:** two tasks due tomorrow: buy groceries and return the library book
- **Did:** ['create_todo', 'create_todo'] — Added 'buy groceries' to Today tagged Groceries. Added 'return the library book' to Today tagged Errands.
- extra actions ['create_todo']

### tasks · multi/interleaved-clauses · `llm` · 10.9 s
- **Said:** [TASKS VIEW] i need to buy some groceries, i need rice and chicken, the chicken i need to get far away, the rice i can get at whole foods
- **Did:** ['create_todo', 'create_todo', 'create_todo'] — Added 'buy rice' and 'buy chicken' to Today tagged Groceries. Added 'get chicken far away' to Today tagged Groceries. Added 'buy rice at whole foods' to Today t
- extra actions ['create_todo', 'create_todo']
- expected 2 todos, got 4: ['buy rice', 'buy chicken', 'get chicken far away', 'buy rice at whole foods']

### update-delete · update/move-by-time · `hybrid` · 5.1 s
- **Said:** move my 1pm meeting tomorrow to 3pm
- **Did:** ['update_event'] — Updated 'Meeting with Tal' successfully.
- expected 'Meeting with Tal' at 15:00; have [('Meeting with Tal', '2026-09-04', '13:00')]

### from-chats · chat-phrasing · `llm` · 6.4 s
- **Said:** bowling tuesday night for Rei's birthday
- **Did:** ['create_event'] — Created event 'Edo's Birthday' on Tuesday, Sep 8, 2026 from 6 PM to 9 PM.
- no event matching {'date': '2026-09-08', 'title_contains': 'bowling'} in DB [("Edo's Birthday", '2026-09-08', '18:00')]
- vocab corrections: [{'from': "Rei's", 'reason': 'alias', 'score': 1.0, 'to': "Edo's"}]

### from-chats · chat-phrasing · `rule` · 2.8 s
- **Said:** meeting with Guri moved from 9:30 to 9 on wednesday
- **Did:** [] — I couldn't find an event matching 'guri'.
- missing action create_event|update_event (got [])
- no event matching {} in DB []

## Slowest 10

| s | path | command |
|---:|---|---|
| 21.1 | llm | tomorrow: Shacharit at 6:30, Haxaga TA at 12, dinner with Ezra at 8 pm, and remi |
| 13.8 | llm | a meeting for me tomorrow at two one sorry one pm and four pm and then another o |
| 13.7 | hybrid | set lunch with Tal on monday at noon and coffee with Ezra on friday at 9 |
| 13.6 | llm | set a meeting tomorrow at 1 pm, another one at 4 pm and then pizza at 6:30 pm to |
| 13.3 | llm | on thursday I have Shacharit at 6:30 am, a lecture at 10 and dinner with Danny a |
| 12.0 | llm | gym tomorrow at 6 am, tuesday at 6 am and friday at 6 am |
| 11.3 | llm | set a meeting at 4pm today, but it is only 20 minutes meeting with one moment me |
| 11.1 | llm | sadna on sunday the 15th at 9 am then driving lesson at 8 am |
| 10.9 | llm | [TASKS VIEW] i need to buy some groceries, i need rice and chicken, the chicken  |
| 10.9 | llm | night shift tomorrow from 8 pm to 6 am |

## Raw

Full per-case JSON: `DOCUMENTATION/experiments/memory_scaling/A_k0.md.json`