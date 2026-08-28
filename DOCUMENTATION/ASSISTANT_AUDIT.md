# Assistant audit — accuracy, latency, self-check

_Generated 2026-08-28 06:53 · 84 commands · scratch DB · vocabulary 374 words · machine arm64. Re-run: `python -m scripts.audit_assistant`._

## Headline

- **Correct after the quick answer:** 94%  ·  **correct once settled (after self-check):** 94%
- **Time to first result:** p50 6.7 s · p95 15.6 s  ·  **time to settled:** p50 20.9 s · p95 33.5 s
- Parse paths: rule 34, hybrid 9, llm 41, error 0

## By area

| Area | n | quick ✓ | settled ✓ | first p50 | first p95 | settled p50 |
|---|---:|---:|---:|---:|---:|---:|
| adversarial | 5 | 100% | 100% | 7.4 s | 9.5 s | 22.8 s |
| events | 39 | 97% | 97% | 7.8 s | 16.0 s | 24.2 s |
| from-chats | 15 | 93% | 93% | 7.6 s | 13.8 s | 24.6 s |
| mixed | 3 | 100% | 100% | 0.1 s | 18.5 s | 11.7 s |
| query | 3 | 100% | 100% | 0.1 s | 0.1 s | 0.1 s |
| tasks | 12 | 83% | 83% | 0.1 s | 9.6 s | 5.9 s |
| update-delete | 7 | 86% | 86% | 0.1 s | 8.9 s | 9.3 s |

## By parse path

| Path | n | quick ✓ | settled ✓ | first p50 | first p95 | LLM ms p50 |
|---|---:|---:|---:|---:|---:|---:|
| rule | 34 | 94% | 94% | 0.1 s | 0.1 s | 0 |
| hybrid | 9 | 78% | 78% | 9.0 s | 13.6 s | 8889 |
| llm | 41 | 98% | 98% | 9.0 s | 18.3 s | 8900 |

## Quick answer vs self-check

- Self-check ran on 81 commands; it proposed a correction on 78 (0 applied).
- **Fixed by self-check:** 0  ·  **broken by self-check:** 0

## By shape (failures first)

| Shape | n | settled ✓ | first p50 |
|---|---:|---:|---:|
| update/rename | 1 | 0% | 0.1 s |
| multi/different-due-dates | 1 | 0% | 10.4 s |
| multi/same-due-date | 1 | 0% | 9.0 s |
| multi/same-day-3 | 2 | 50% | 16.4 s |
| chat-phrasing | 15 | 93% | 7.6 s |
| generated/single | 12 | 100% | 8.6 s |
| multi/different-days | 2 | 100% | 14.8 s |
| recurring/weekly | 2 | 100% | 8.5 s |
| ambiguous/no-time | 1 | 100% | 7.4 s |
| update/move-by-title | 1 | 100% | 0.1 s |
| single/spoken-time | 1 | 100% | 8.5 s |
| delete/by-title | 1 | 100% | 0.1 s |
| query/today | 1 | 100% | 0.1 s |
| single/hebrew-name | 1 | 100% | 0.1 s |
| past-tense-noise | 1 | 100% | 8.5 s |
| multi/same-list-3 | 1 | 100% | 7.1 s |
| single/place | 1 | 100% | 7.8 s |
| single/due-weekday | 1 | 100% | 0.1 s |
| single/next-weekday | 1 | 100% | 0.1 s |
| single/full-name | 1 | 100% | 0.2 s |
| query/week | 1 | 100% | 0.0 s |
| task-not-event | 1 | 100% | 0.1 s |
| 3events+task | 1 | 100% | 20.5 s |
| single | 2 | 100% | 0.1 s |
| task+event | 1 | 100% | 0.1 s |
| single/range | 1 | 100% | 8.0 s |
| multi/same-list | 2 | 100% | 0.1 s |
| multi/different-days-3 | 1 | 100% | 17.4 s |
| event+task | 1 | 100% | 0.1 s |
| update/move-by-time | 1 | 100% | 9.0 s |
| update/extend | 1 | 100% | 8.6 s |
| multi/tagged | 1 | 100% | 0.1 s |
| update/move-day | 1 | 100% | 0.1 s |
| single/due-tomorrow | 1 | 100% | 0.1 s |
| single/day-of-month | 1 | 100% | 7.1 s |
| single/hebrew-term | 2 | 100% | 6.2 s |
| single/stop-word | 1 | 100% | 0.1 s |
| single/disfluency | 1 | 100% | 9.0 s |
| recurring/daily | 1 | 100% | 7.1 s |
| multi/same-day-2 | 3 | 100% | 13.1 s |
| query/tomorrow | 1 | 100% | 0.1 s |
| single/duration | 1 | 100% | 0.1 s |
| event-not-task | 1 | 100% | 0.1 s |
| misheard-names | 1 | 100% | 9.7 s |
| single/terse | 1 | 100% | 5.9 s |
| single/weekday | 1 | 100% | 6.3 s |
| single/general-list | 1 | 100% | 0.1 s |
| single/explicit-time | 3 | 100% | 0.1 s |
| delete/by-time | 1 | 100% | 0.1 s |

## Failures

### events · multi/same-day-3 · `llm` · 14.5 s
- **Said:** on thursday I have Shacharit at 6:30 am, a lecture at 10 and dinner with Danny at 8 pm
- **Did:** ['create_event', 'create_event', 'create_event'] — Created event 'Dinner with Danny' on Thursday, Sep 3, 2026 from 6 PM to 8 PM. Created event 'Lecture' on Thursday, Sep 3, 2026 from 10 AM to 11 AM. Created even
- no event matching {'date': '2026-09-03', 'start_time': '20:00', 'title_contains': 'Danny'} in DB [('Shacharit', '2026-09-03', '06:30'), ('Lecture', '2026-09-03', '10:00'), ('Dinner with Danny', '2026-09-03', '18:00')]

### tasks · multi/same-due-date · `hybrid` · 9.0 s
- **Said:** two tasks due tomorrow: buy groceries and return the library book
- **Did:** ['create_todo', 'create_todo'] — Added 'buy groceries' to Today. Added 'return the library book' to Today.
- extra actions ['create_todo']

### tasks · multi/different-due-dates · `hybrid` · 10.4 s
- **Said:** add buy a gift for Tamar due thursday and book the driving test due next monday
- **Did:** ['create_event', 'create_todo'] — Created event 'Driving Test' on Monday, Aug 31, 2026 from 9 AM to 10 AM. Added 'Buy a gift for Tamar' to Today.
- missing action create_todo (got ['create_event', 'create_todo'])
- extra actions ['create_event']
- no todo containing 'driving' (todos=['Buy a gift for Tamar'])

### update-delete · update/rename · `rule` · 0.1 s
- **Said:** rename the meeting with Tal to robotics sync
- **Did:** ['update_event'] — No changes specified for 'Meeting with Tal'.
- expected event titled ~'robotics' at 13:00; have [('Meeting with Tal', '13:00')]

### from-chats · chat-phrasing · `rule` · 0.1 s
- **Said:** meeting with Guri moved from 9:30 to 9 on wednesday
- **Did:** ['update_event'] — I couldn't find an event matching 'guri'.
- no event matching {} in DB []

## Slowest 10

| s | path | command |
|---:|---|---|
| 20.5 | llm | tomorrow: Shacharit at 6:30, Haxaga TA at 12, dinner with Ezra at 8 pm, and remi |
| 18.3 | llm | set a meeting tomorrow at 1 pm, another one at 4 pm and then pizza at 6:30 pm to |
| 18.3 | llm | night shift tomorrow from 8 pm to 6 am |
| 17.4 | llm | gym tomorrow at 6 am, tuesday at 6 am and friday at 6 am |
| 15.8 | hybrid | set lunch with Tal on monday at noon and coffee with Ezra on friday at 9 |
| 14.5 | llm | on thursday I have Shacharit at 6:30 am, a lecture at 10 and dinner with Danny a |
| 13.8 | llm | meeting with Ravid tomorrow at 2 pm and dentist on thursday at 9 am |
| 13.7 | llm | two events tomorrow, one at four o'clock meeting with Rei and one at seven pm pi |
| 13.1 | llm | tomorrow gym at 7 am and a meeting with Tal at 11 |
| 11.9 | llm | Kems tomorrow at 8 with Ravid and Ezra |

## Raw

Full per-case JSON: `DOCUMENTATION/ASSISTANT_AUDIT.md.json`