# Assistant audit — accuracy, latency, self-check

_Generated 2026-09-02 11:47 · 89 commands · scratch DB · vocabulary 374 words · machine arm64. Re-run: `python -m scripts.audit_assistant`._

## Headline

- **Correct after the quick answer:** 97%  ·  **correct once settled (after self-check):** 96%
- **Time to first result:** p50 6.3 s · p95 18.3 s  ·  **time to settled:** p50 19.3 s · p95 40.2 s
- Parse paths: rule 39, hybrid 9, llm 41, error 0

## By area

| Area | n | quick ✓ | settled ✓ | first p50 | first p95 | settled p50 |
|---|---:|---:|---:|---:|---:|---:|
| adversarial | 5 | 100% | 100% | 6.9 s | 8.7 s | 19.3 s |
| events | 39 | 100% | 97% | 8.5 s | 19.2 s | 22.0 s |
| from-chats | 15 | 93% | 93% | 7.4 s | 11.6 s | 20.4 s |
| mixed | 3 | 100% | 100% | 0.2 s | 15.1 s | 8.7 s |
| query | 3 | 100% | 100% | 0.1 s | 0.1 s | 0.1 s |
| tasks | 17 | 88% | 88% | 0.3 s | 8.3 s | 7.2 s |
| update-delete | 7 | 100% | 100% | 0.2 s | 8.7 s | 7.8 s |

## By parse path

| Path | n | quick ✓ | settled ✓ | first p50 | first p95 | LLM ms p50 |
|---|---:|---:|---:|---:|---:|---:|
| rule | 39 | 97% | 97% | 0.1 s | 0.5 s | 0 |
| hybrid | 9 | 78% | 78% | 8.9 s | 20.4 s | 8603 |
| llm | 41 | 100% | 98% | 8.9 s | 18.7 s | 8755 |

## Quick answer vs self-check

- Self-check ran on 85 commands; it proposed a correction on 38 (29 applied).
- **Fixed by self-check:** 0  ·  **broken by self-check:** 1
  - broke: “meeting tomorrow at 2 sorry not 2, 3 pm with Adin for the project” → {'ok': False, 'severity': 'minor', 'applied': True, 'speech': 'Meeting time corrected to 2 pm', 'refresh': 'events'}

## By shape (failures first)

| Shape | n | settled ✓ | first p50 |
|---|---:|---:|---:|
| multi/same-due-date | 1 | 0% | 10.1 s |
| multi/different-due-dates | 1 | 0% | 7.3 s |
| single/disfluency | 1 | 0% | 11.0 s |
| chat-phrasing | 15 | 93% | 7.4 s |
| multi/shared-verb-3 | 1 | 100% | 0.3 s |
| multi/shared-verb-people | 1 | 100% | 0.1 s |
| single/duration | 1 | 100% | 0.1 s |
| single/stop-word | 1 | 100% | 0.1 s |
| single/due-weekday | 1 | 100% | 0.1 s |
| single/range | 1 | 100% | 12.1 s |
| query/tomorrow | 1 | 100% | 0.1 s |
| generated/single | 12 | 100% | 6.8 s |
| single/terse | 1 | 100% | 14.1 s |
| event+task | 1 | 100% | 0.2 s |
| single/place | 1 | 100% | 13.7 s |
| single/day-of-month | 1 | 100% | 7.7 s |
| ambiguous/no-time | 1 | 100% | 6.9 s |
| single/spoken-time | 1 | 100% | 16.6 s |
| multi/tagged | 1 | 100% | 0.3 s |
| multi/different-days | 2 | 100% | 19.5 s |
| update/move-by-title | 1 | 100% | 0.2 s |
| update/move-day | 1 | 100% | 0.2 s |
| multi/same-list | 2 | 100% | 0.3 s |
| recurring/daily | 1 | 100% | 14.1 s |
| multi/same-list-3 | 1 | 100% | 7.8 s |
| delete/by-time | 1 | 100% | 0.0 s |
| single/general-list | 1 | 100% | 0.2 s |
| recurring/weekly | 2 | 100% | 16.0 s |
| single/hebrew-name | 1 | 100% | 0.1 s |
| single/next-weekday | 1 | 100% | 0.1 s |
| update/move-by-time | 1 | 100% | 8.9 s |
| task-not-event | 1 | 100% | 0.1 s |
| 3events+task | 1 | 100% | 16.7 s |
| delete/by-title | 1 | 100% | 0.1 s |
| task+event | 1 | 100% | 0.1 s |
| single/internal-and | 1 | 100% | 0.3 s |
| query/today | 1 | 100% | 0.1 s |
| single/due-tomorrow | 1 | 100% | 0.2 s |
| multi/different-days-3 | 1 | 100% | 18.4 s |
| query/week | 1 | 100% | 0.1 s |
| multi/shared-verb | 1 | 100% | 0.2 s |
| event-not-task | 1 | 100% | 0.1 s |
| single/full-name | 1 | 100% | 0.1 s |
| multi/same-day-3 | 2 | 100% | 19.4 s |
| misheard-names | 1 | 100% | 8.8 s |
| single/explicit-time | 3 | 100% | 0.1 s |
| single/inferred-tag | 1 | 100% | 0.5 s |
| single/weekday | 1 | 100% | 6.6 s |
| single/hebrew-term | 2 | 100% | 14.7 s |
| single | 2 | 100% | 0.5 s |
| update/rename | 1 | 100% | 0.4 s |
| past-tense-noise | 1 | 100% | 8.0 s |
| multi/same-day-2 | 3 | 100% | 16.1 s |
| update/extend | 1 | 100% | 8.0 s |

## Failures

### events · single/disfluency · `llm` · 11.0 s
- **Said:** meeting tomorrow at 2 sorry not 2, 3 pm with Adin for the project
- **Did:** ['create_event'] — Created event 'meeting with adin' on Thursday, Sep 3, 2026 from 3 PM to 4 PM.
- no event matching {'date': '2026-09-03', 'start_time': '15:00', 'title_contains': 'Adin'} in DB [('meeting with adin', '2026-09-03', '14:00')]

### tasks · multi/same-due-date · `hybrid` · 10.1 s
- **Said:** two tasks due tomorrow: buy groceries and return the library book
- **Did:** ['create_todo', 'create_todo'] — Added 'buy groceries' and 'return the library book' to Today. Added 'return the library book' to Today tagged Errands.
- extra actions ['create_todo']

### tasks · multi/different-due-dates · `hybrid` · 7.3 s
- **Said:** add buy a gift for Tamar due thursday and book the driving test due next monday
- **Did:** ['create_todo'] — Added 'buy a gift for Tamar' and 'book the driving test' to Today.
- missing action create_todo (got ['create_todo'])
- todo 'book the driving test' due 2026-09-03 != 2026-09-07

### from-chats · chat-phrasing · `rule` · 5.4 s
- **Said:** meeting with Guri moved from 9:30 to 9 on wednesday
- **Did:** [] — I couldn't find an event matching 'guri'.
- missing action create_event|update_event (got [])
- no event matching {} in DB []

## Slowest 10

| s | path | command |
|---:|---|---|
| 22.1 | hybrid | set lunch with Tal on monday at noon and coffee with Ezra on friday at 9 |
| 19.7 | llm | on thursday I have Shacharit at 6:30 am, a lecture at 10 and dinner with Danny a |
| 19.1 | llm | set a meeting tomorrow at 1 pm, another one at 4 pm and then pizza at 6:30 pm to |
| 18.7 | llm | Limud Torah at Ohel Ari on tuesday at 9 pm |
| 18.4 | llm | gym tomorrow at 6 am, tuesday at 6 am and friday at 6 am |
| 18.2 | llm | two events tomorrow, one at four o'clock meeting with Rei and one at seven pm pi |
| 17.9 | hybrid | schedule gym every monday at 6 am |
| 17.0 | llm | meeting with Ravid tomorrow at 2 pm and dentist on thursday at 9 am |
| 16.7 | llm | tomorrow: Shacharit at 6:30, Haxaga TA at 12, dinner with Ezra at 8 pm, and remi |
| 16.6 | hybrid | book a haircut for tuesday at half past two |

## Raw

Full per-case JSON: `DOCUMENTATION/ASSISTANT_AUDIT.md.json`