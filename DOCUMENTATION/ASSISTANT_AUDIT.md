# Assistant audit — accuracy, latency, self-check

_Generated 2026-08-28 10:01 · 84 commands · scratch DB · vocabulary 374 words · machine arm64. Re-run: `python -m scripts.audit_assistant`._

## Headline

- **Correct after the quick answer:** 95%  ·  **correct once settled (after self-check):** 95%
- **Time to first result:** p50 7.2 s · p95 16.0 s  ·  **time to settled:** p50 7.2 s · p95 16.0 s
- Parse paths: rule 34, hybrid 9, llm 41, error 0

## By area

| Area | n | quick ✓ | settled ✓ | first p50 | first p95 | settled p50 |
|---|---:|---:|---:|---:|---:|---:|
| adversarial | 5 | 100% | 100% | 8.0 s | 9.6 s | 8.0 s |
| events | 39 | 97% | 97% | 8.5 s | 16.4 s | 8.5 s |
| from-chats | 15 | 93% | 93% | 8.0 s | 13.6 s | 8.0 s |
| mixed | 3 | 100% | 100% | 0.1 s | 16.2 s | 0.1 s |
| query | 3 | 100% | 100% | 0.1 s | 0.1 s | 0.1 s |
| tasks | 12 | 83% | 83% | 0.1 s | 8.5 s | 0.1 s |
| update-delete | 7 | 100% | 100% | 0.1 s | 9.1 s | 0.1 s |

## By parse path

| Path | n | quick ✓ | settled ✓ | first p50 | first p95 | LLM ms p50 |
|---|---:|---:|---:|---:|---:|---:|
| rule | 34 | 97% | 97% | 0.1 s | 0.1 s | 0 |
| hybrid | 9 | 78% | 78% | 8.7 s | 14.2 s | 8597 |
| llm | 41 | 98% | 98% | 9.5 s | 18.0 s | 9386 |

## Quick answer vs self-check

- Self-check ran on 0 commands; it proposed a correction on 0 (0 applied).
- **Fixed by self-check:** 0  ·  **broken by self-check:** 0

## By shape (failures first)

| Shape | n | settled ✓ | first p50 |
|---|---:|---:|---:|
| multi/same-due-date | 1 | 0% | 10.1 s |
| multi/different-due-dates | 1 | 0% | 6.8 s |
| multi/same-day-2 | 3 | 67% | 13.2 s |
| chat-phrasing | 15 | 93% | 8.0 s |
| update/move-by-title | 1 | 100% | 0.1 s |
| multi/same-list | 2 | 100% | 0.1 s |
| single/spoken-time | 1 | 100% | 8.7 s |
| misheard-names | 1 | 100% | 9.8 s |
| past-tense-noise | 1 | 100% | 8.9 s |
| update/move-day | 1 | 100% | 0.1 s |
| recurring/daily | 1 | 100% | 7.6 s |
| multi/tagged | 1 | 100% | 0.1 s |
| single/due-tomorrow | 1 | 100% | 0.1 s |
| single/weekday | 1 | 100% | 6.6 s |
| task-not-event | 1 | 100% | 0.1 s |
| event+task | 1 | 100% | 0.1 s |
| multi/same-list-3 | 1 | 100% | 7.2 s |
| single/day-of-month | 1 | 100% | 7.5 s |
| single/due-weekday | 1 | 100% | 0.1 s |
| task+event | 1 | 100% | 0.1 s |
| single/hebrew-name | 1 | 100% | 0.1 s |
| single | 2 | 100% | 0.1 s |
| delete/by-title | 1 | 100% | 0.1 s |
| multi/different-days | 2 | 100% | 15.2 s |
| event-not-task | 1 | 100% | 0.1 s |
| 3events+task | 1 | 100% | 18.0 s |
| single/duration | 1 | 100% | 0.1 s |
| single/place | 1 | 100% | 8.1 s |
| delete/by-time | 1 | 100% | 0.1 s |
| single/general-list | 1 | 100% | 0.1 s |
| single/next-weekday | 1 | 100% | 0.1 s |
| update/extend | 1 | 100% | 8.6 s |
| single/full-name | 1 | 100% | 0.1 s |
| query/tomorrow | 1 | 100% | 0.1 s |
| single/stop-word | 1 | 100% | 0.1 s |
| single/disfluency | 1 | 100% | 12.2 s |
| recurring/weekly | 2 | 100% | 9.3 s |
| single/hebrew-term | 2 | 100% | 8.1 s |
| single/explicit-time | 3 | 100% | 0.1 s |
| single/range | 1 | 100% | 8.5 s |
| query/today | 1 | 100% | 0.1 s |
| query/week | 1 | 100% | 0.1 s |
| ambiguous/no-time | 1 | 100% | 8.0 s |
| update/move-by-time | 1 | 100% | 9.3 s |
| update/rename | 1 | 100% | 0.1 s |
| multi/different-days-3 | 1 | 100% | 18.4 s |
| generated/single | 12 | 100% | 8.9 s |
| single/terse | 1 | 100% | 6.3 s |
| multi/same-day-3 | 2 | 100% | 16.4 s |

## Failures

### events · multi/same-day-2 · `llm` · 13.2 s
- **Said:** two events tomorrow, one at four o'clock meeting with Rei and one at seven pm pizza with Ezra
- **Did:** ['create_event', 'create_event'] — Created event 'meeting' on Saturday, Aug 29, 2026 from 4 PM to 5 PM. Created event 'pizza with ezra' on Saturday, Aug 29, 2026 from 7 PM to 8 PM.
- no event matching {'date': '2026-08-29', 'start_time': '16:00', 'title_contains': 'Rei'} in DB [('meeting', '2026-08-29', '16:00'), ('pizza with ezra', '2026-08-29', '19:00')]

### tasks · multi/same-due-date · `hybrid` · 10.1 s
- **Said:** two tasks due tomorrow: buy groceries and return the library book
- **Did:** ['create_todo', 'create_todo'] — Added 'buy groceries' to Today. Added 'return the library book' to Today.
- extra actions ['create_todo']

### tasks · multi/different-due-dates · `hybrid` · 6.8 s
- **Said:** add buy a gift for Tamar due thursday and book the driving test due next monday
- **Did:** ['create_todo'] — Added 'Buy a gift for Tamar' to Today.
- missing action create_todo (got ['create_todo'])
- no todo containing 'driving' (todos=['Buy a gift for Tamar'])

### from-chats · chat-phrasing · `rule` · 0.1 s
- **Said:** meeting with Guri moved from 9:30 to 9 on wednesday
- **Did:** ['update_event'] — I couldn't find an event matching 'guri'.
- no event matching {} in DB []

## Slowest 10

| s | path | command |
|---:|---|---|
| 19.1 | llm | night shift tomorrow from 8 pm to 6 am |
| 18.4 | llm | gym tomorrow at 6 am, tuesday at 6 am and friday at 6 am |
| 18.0 | llm | tomorrow: Shacharit at 6:30, Haxaga TA at 12, dinner with Ezra at 8 pm, and remi |
| 17.7 | llm | set a meeting tomorrow at 1 pm, another one at 4 pm and then pizza at 6:30 pm to |
| 16.2 | hybrid | set lunch with Tal on monday at noon and coffee with Ezra on friday at 9 |
| 15.0 | llm | on thursday I have Shacharit at 6:30 am, a lecture at 10 and dinner with Danny a |
| 14.2 | llm | meeting with Ravid tomorrow at 2 pm and dentist on thursday at 9 am |
| 13.5 | llm | tomorrow gym at 7 am and a meeting with Tal at 11 |
| 13.2 | llm | two events tomorrow, one at four o'clock meeting with Rei and one at seven pm pi |
| 12.8 | llm | walk Kyra the dog at 3:30 pm today and then go to shul for Mincha Maariv at 7:30 |

## Raw

Full per-case JSON: `DOCUMENTATION/ASSISTANT_AUDIT.md.json`