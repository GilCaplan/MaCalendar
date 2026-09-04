# Assistant audit — accuracy, latency, self-check

_Generated 2026-09-03 13:03 · 92 commands · scratch DB · vocabulary 374 words · machine arm64. Re-run: `python -m scripts.audit_assistant`._

## Headline

- **Correct after the quick answer:** 93%  ·  **correct once settled (after self-check):** 93%
- **Time to first result:** p50 5.4 s · p95 12.8 s  ·  **time to settled:** p50 14.9 s · p95 26.3 s
- Parse paths: rule 39, hybrid 10, llm 43, error 0

## By area

| Area | n | quick ✓ | settled ✓ | first p50 | first p95 | settled p50 |
|---|---:|---:|---:|---:|---:|---:|
| adversarial | 5 | 100% | 100% | 10.5 s | 13.3 s | 20.7 s |
| events | 41 | 95% | 95% | 6.1 s | 13.9 s | 15.3 s |
| from-chats | 15 | 87% | 87% | 5.5 s | 8.5 s | 15.5 s |
| mixed | 3 | 100% | 100% | 0.1 s | 17.7 s | 7.3 s |
| query | 3 | 100% | 100% | 0.0 s | 0.0 s | 3.1 s |
| tasks | 18 | 94% | 94% | 0.1 s | 10.9 s | 5.7 s |
| update-delete | 7 | 86% | 86% | 0.1 s | 7.2 s | 6.0 s |

## By parse path

| Path | n | quick ✓ | settled ✓ | first p50 | first p95 | LLM ms p50 |
|---|---:|---:|---:|---:|---:|---:|
| rule | 39 | 97% | 97% | 0.1 s | 2.3 s | 0 |
| hybrid | 10 | 80% | 80% | 7.3 s | 12.5 s | 7161 |
| llm | 43 | 93% | 93% | 6.3 s | 15.3 s | 6200 |

## Quick answer vs self-check

- Self-check ran on 92 commands; it proposed a correction on 56 (0 applied).
- **Fixed by self-check:** 0  ·  **broken by self-check:** 0

## By shape (failures first)

| Shape | n | settled ✓ | first p50 |
|---|---:|---:|---:|
| multi/disfluent-duration | 1 | 0% | 9.4 s |
| update/extend | 1 | 0% | 7.6 s |
| multi/interleaved-clauses | 1 | 0% | 11.8 s |
| multi/self-correction-count | 1 | 0% | 11.0 s |
| chat-phrasing | 15 | 87% | 5.5 s |
| multi/different-due-dates | 1 | 100% | 10.7 s |
| past-tense-noise | 1 | 100% | 13.6 s |
| multi/different-days-3 | 1 | 100% | 12.2 s |
| delete/by-time | 1 | 100% | 0.0 s |
| event-not-task | 1 | 100% | 0.0 s |
| single/range | 1 | 100% | 7.0 s |
| recurring/weekly | 2 | 100% | 6.1 s |
| multi/same-day-2 | 3 | 100% | 9.8 s |
| single/due-tomorrow | 1 | 100% | 0.1 s |
| 3events+task | 1 | 100% | 19.6 s |
| single/internal-and | 1 | 100% | 0.1 s |
| multi/tagged | 1 | 100% | 0.1 s |
| delete/by-title | 1 | 100% | 0.0 s |
| multi/same-day-3 | 2 | 100% | 15.5 s |
| query/week | 1 | 100% | 0.0 s |
| update/move-by-time | 1 | 100% | 6.4 s |
| single/hebrew-term | 2 | 100% | 6.3 s |
| multi/shared-verb-3 | 1 | 100% | 0.1 s |
| single | 2 | 100% | 0.1 s |
| recurring/daily | 1 | 100% | 5.6 s |
| query/tomorrow | 1 | 100% | 0.0 s |
| multi/different-days | 2 | 100% | 12.7 s |
| single/full-name | 1 | 100% | 0.2 s |
| single/next-weekday | 1 | 100% | 2.3 s |
| single/hebrew-name | 1 | 100% | 0.0 s |
| task+event | 1 | 100% | 0.1 s |
| query/today | 1 | 100% | 0.0 s |
| single/disfluency | 1 | 100% | 6.2 s |
| single/general-list | 1 | 100% | 0.0 s |
| update/move-day | 1 | 100% | 0.1 s |
| multi/same-due-date | 1 | 100% | 6.1 s |
| multi/same-list-3 | 1 | 100% | 7.0 s |
| single/due-weekday | 1 | 100% | 0.0 s |
| update/move-by-title | 1 | 100% | 0.0 s |
| multi/shared-verb-people | 1 | 100% | 0.1 s |
| single/inferred-tag | 1 | 100% | 0.0 s |
| single/terse | 1 | 100% | 5.2 s |
| single/day-of-month | 1 | 100% | 6.0 s |
| misheard-names | 1 | 100% | 12.1 s |
| single/explicit-time | 3 | 100% | 0.1 s |
| update/rename | 1 | 100% | 0.1 s |
| single/weekday | 1 | 100% | 5.4 s |
| task-not-event | 1 | 100% | 0.0 s |
| ambiguous/no-time | 1 | 100% | 10.5 s |
| single/stop-word | 1 | 100% | 2.3 s |
| single/place | 1 | 100% | 5.4 s |
| event+task | 1 | 100% | 0.1 s |
| multi/shared-verb | 1 | 100% | 0.0 s |
| multi/same-list | 2 | 100% | 0.1 s |
| single/duration | 1 | 100% | 0.1 s |
| generated/single | 12 | 100% | 6.1 s |
| single/spoken-time | 1 | 100% | 7.7 s |

## Failures

### events · multi/disfluent-duration · `llm` · 9.4 s
- **Said:** set a meeting at 4pm today, but it is only 20 minutes meeting with one moment meeting with reards, okay, then let's do another meeting from 6 from 6 o'clock to 640 meetings with kids for project defense
- **Did:** ['create_event', 'create_event'] — Created event 'Meeting with Reards' on Thursday, Sep 3, 2026 from 4 PM to 4:20 PM. Created event 'Meetings with Kids for Project Defense' on Thursday, Sep 3, 20
- no event matching {'date': '2026-09-03', 'start_time': '18:00', 'end_time': '18:40'} in DB [('Meeting with Reards', '2026-09-03', '16:00'), ('Meetings with Kids for Project Defense', '2026-09-03', '18:00')]

### events · multi/self-correction-count · `llm` · 11.0 s
- **Said:** a meeting for me tomorrow at two one sorry one pm and four pm and then another one a pizza party at 6.30 pm at edo's
- **Did:** ['create_event', 'create_event'] — Created event 'Meeting' on Friday, Sep 4, 2026 from 1 PM to 4 PM. Created event 'Pizza Party' on Friday, Sep 4, 2026 from 6:30 PM to 7:30 PM.
- missing action create_event (got ['create_event', 'create_event'])
- no event matching {'date': '2026-09-04', 'start_time': '13:00', 'end_time': '14:00'} in DB [('Meeting', '2026-09-04', '13:00'), ('Pizza Party', '2026-09-04', '18:30')]
- no event matching {'date': '2026-09-04', 'start_time': '16:00', 'end_time': '17:00'} in DB [('Meeting', '2026-09-04', '13:00'), ('Pizza Party', '2026-09-04', '18:30')]

### tasks · multi/interleaved-clauses · `llm` · 11.8 s
- **Said:** [TASKS VIEW] i need to buy some groceries, i need rice and chicken, the chicken i need to get far away, the rice i can get at whole foods
- **Did:** ['create_todo', 'create_todo'] — Added 'buy rice' to Today tagged Groceries. Added 'get far away' and 'chicken' to Today.
- extra actions ['create_todo']
- expected 2 todos, got 3: ['buy rice', 'get far away', 'chicken']

### update-delete · update/extend · `hybrid` · 7.6 s
- **Said:** extend the meeting with Tal tomorrow until 3 pm
- **Did:** [] — I couldn't find an event at 14:00 on 2026-09-04.
- missing action update_event (got [])
- expected 'Meeting with Tal' ending 15:00; have [('Meeting with Tal', '14:00')]

### from-chats · chat-phrasing · `hybrid` · 5.5 s
- **Said:** night shift tomorrow from 8 pm to 6 am
- **Did:** [] — I couldn't find an event matching 'night shift'.
- missing action create_event (got [])
- no event matching {'date': '2026-09-04', 'start_time': '20:00'} in DB []

### from-chats · chat-phrasing · `rule` · 3.1 s
- **Said:** meeting with Guri moved from 9:30 to 9 on wednesday
- **Did:** [] — I couldn't find an event matching 'guri'.
- missing action create_event|update_event (got [])
- no event matching {} in DB []

## Slowest 10

| s | path | command |
|---:|---|---|
| 19.6 | llm | tomorrow: Shacharit at 6:30, Haxaga TA at 12, dinner with Ezra at 8 pm, and remi |
| 15.5 | llm | set a meeting tomorrow at 1 pm, another one at 4 pm and then pizza at 6:30 pm to |
| 15.5 | llm | on thursday I have Shacharit at 6:30 am, a lecture at 10 and dinner with Danny a |
| 13.9 | hybrid | set lunch with Tal on monday at noon and coffee with Ezra on friday at 9 |
| 13.6 | llm | I had a meeting today at 8:30 pm with Nurit to work on the project |
| 12.2 | llm | gym tomorrow at 6 am, tuesday at 6 am and friday at 6 am |
| 12.1 | llm | meet Ravid at the french bakery in Jerusalem after shacharis at 9 am tomorrow |
| 11.8 | llm | [TASKS VIEW] i need to buy some groceries, i need rice and chicken, the chicken  |
| 11.5 | llm | meeting with Ravid tomorrow at 2 pm and dentist on thursday at 9 am |
| 11.2 | llm | walk Kyra the dog at 3:30 pm today and then go to shul for Mincha Maariv at 7:30 |

## Raw

Full per-case JSON: `DOCUMENTATION/experiments/memory_scaling/A_k1.md.json`