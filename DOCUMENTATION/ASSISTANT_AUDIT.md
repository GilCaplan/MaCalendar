# Assistant audit — accuracy, latency, self-check

_Generated 2026-09-02 12:26 · 89 commands · scratch DB · vocabulary 374 words · machine arm64. Re-run: `python -m scripts.audit_assistant`._

## Headline

- **Correct after the quick answer:** 97%  ·  **correct once settled (after self-check):** 97%
- **Time to first result:** p50 4.7 s · p95 19.4 s  ·  **time to settled:** p50 17.1 s · p95 39.2 s
- Parse paths: rule 39, hybrid 9, llm 41, error 0

## By area

| Area | n | quick ✓ | settled ✓ | first p50 | first p95 | settled p50 |
|---|---:|---:|---:|---:|---:|---:|
| adversarial | 5 | 100% | 100% | 6.8 s | 8.6 s | 17.7 s |
| events | 39 | 97% | 97% | 6.4 s | 20.2 s | 18.4 s |
| from-chats | 15 | 93% | 93% | 6.3 s | 11.1 s | 19.3 s |
| mixed | 3 | 100% | 100% | 0.1 s | 14.8 s | 9.2 s |
| query | 3 | 100% | 100% | 0.0 s | 0.0 s | 3.8 s |
| tasks | 17 | 94% | 94% | 0.1 s | 13.0 s | 6.4 s |
| update-delete | 7 | 100% | 100% | 0.0 s | 17.2 s | 7.4 s |

## By parse path

| Path | n | quick ✓ | settled ✓ | first p50 | first p95 | LLM ms p50 |
|---|---:|---:|---:|---:|---:|---:|
| rule | 39 | 97% | 97% | 0.0 s | 0.2 s | 0 |
| hybrid | 9 | 89% | 89% | 12.1 s | 17.6 s | 12019 |
| llm | 41 | 98% | 98% | 7.8 s | 19.9 s | 7786 |

## Quick answer vs self-check

- Self-check ran on 89 commands; it proposed a correction on 37 (0 applied).
- **Fixed by self-check:** 0  ·  **broken by self-check:** 0

## By shape (failures first)

| Shape | n | settled ✓ | first p50 |
|---|---:|---:|---:|
| multi/different-due-dates | 1 | 0% | 12.1 s |
| multi/same-day-2 | 3 | 67% | 19.6 s |
| chat-phrasing | 15 | 93% | 6.3 s |
| single/spoken-time | 1 | 100% | 8.9 s |
| generated/single | 12 | 100% | 7.7 s |
| multi/same-list | 2 | 100% | 0.1 s |
| single/due-weekday | 1 | 100% | 0.0 s |
| update/move-by-time | 1 | 100% | 15.3 s |
| delete/by-title | 1 | 100% | 0.0 s |
| update/extend | 1 | 100% | 18.0 s |
| update/rename | 1 | 100% | 0.0 s |
| single | 2 | 100% | 0.0 s |
| single/duration | 1 | 100% | 0.0 s |
| event-not-task | 1 | 100% | 0.2 s |
| query/today | 1 | 100% | 0.0 s |
| ambiguous/no-time | 1 | 100% | 8.8 s |
| query/week | 1 | 100% | 0.0 s |
| multi/same-day-3 | 2 | 100% | 21.8 s |
| update/move-by-title | 1 | 100% | 0.0 s |
| single/disfluency | 1 | 100% | 8.2 s |
| delete/by-time | 1 | 100% | 0.0 s |
| single/stop-word | 1 | 100% | 0.0 s |
| task-not-event | 1 | 100% | 0.0 s |
| update/move-day | 1 | 100% | 0.0 s |
| single/next-weekday | 1 | 100% | 0.1 s |
| multi/different-days-3 | 1 | 100% | 14.5 s |
| single/full-name | 1 | 100% | 0.1 s |
| single/day-of-month | 1 | 100% | 4.5 s |
| multi/tagged | 1 | 100% | 0.0 s |
| event+task | 1 | 100% | 0.1 s |
| multi/shared-verb | 1 | 100% | 0.0 s |
| single/internal-and | 1 | 100% | 0.1 s |
| single/general-list | 1 | 100% | 0.0 s |
| misheard-names | 1 | 100% | 6.8 s |
| single/terse | 1 | 100% | 4.2 s |
| single/inferred-tag | 1 | 100% | 0.1 s |
| single/range | 1 | 100% | 4.7 s |
| multi/shared-verb-3 | 1 | 100% | 0.2 s |
| recurring/weekly | 2 | 100% | 7.4 s |
| single/hebrew-name | 1 | 100% | 0.0 s |
| past-tense-noise | 1 | 100% | 7.8 s |
| multi/same-list-3 | 1 | 100% | 5.7 s |
| single/due-tomorrow | 1 | 100% | 0.1 s |
| single/place | 1 | 100% | 4.9 s |
| single/weekday | 1 | 100% | 4.0 s |
| single/hebrew-term | 2 | 100% | 3.8 s |
| query/tomorrow | 1 | 100% | 0.0 s |
| task+event | 1 | 100% | 0.1 s |
| multi/shared-verb-people | 1 | 100% | 0.1 s |
| 3events+task | 1 | 100% | 16.4 s |
| multi/different-days | 2 | 100% | 16.5 s |
| recurring/daily | 1 | 100% | 6.4 s |
| multi/same-due-date | 1 | 100% | 16.9 s |
| single/explicit-time | 3 | 100% | 0.0 s |

## Failures

### events · multi/same-day-2 · `llm` · 22.9 s
- **Said:** two events tomorrow, one at four o'clock meeting with Rei and one at seven pm pizza with Ezra
- **Did:** ['create_event', 'create_event'] — Created event 'meeting' on Thursday, Sep 3, 2026 from 4 PM to 5 PM. Created event 'pizza with ezra' on Thursday, Sep 3, 2026 from 7 PM to 8 PM.
- no event matching {'date': '2026-09-03', 'start_time': '16:00', 'title_contains': 'Rei'} in DB [('meeting', '2026-09-03', '16:00'), ('pizza with ezra', '2026-09-03', '19:00')]

### tasks · multi/different-due-dates · `hybrid` · 12.1 s
- **Said:** add buy a gift for Tamar due thursday and book the driving test due next monday
- **Did:** ['create_todo'] — Added 'buy a gift for Tamar' and 'book the driving test' to Today.
- missing action create_todo (got ['create_todo'])
- todo 'book the driving test' due 2026-09-03 != 2026-09-07

### from-chats · chat-phrasing · `rule` · 5.2 s
- **Said:** meeting with Guri moved from 9:30 to 9 on wednesday
- **Did:** [] — I couldn't find an event matching 'guri'.
- missing action create_event|update_event (got [])
- no event matching {} in DB []

## Slowest 10

| s | path | command |
|---:|---|---|
| 23.6 | llm | set a meeting tomorrow at 1 pm, another one at 4 pm and then pizza at 6:30 pm to |
| 22.9 | llm | two events tomorrow, one at four o'clock meeting with Rei and one at seven pm pi |
| 19.9 | llm | on thursday I have Shacharit at 6:30 am, a lecture at 10 and dinner with Danny a |
| 19.6 | llm | walk Kyra the dog at 3:30 pm today and then go to shul for Mincha Maariv at 7:30 |
| 19.4 | llm | tomorrow gym at 7 am and a meeting with Tal at 11 |
| 19.3 | llm | meeting with Ravid tomorrow at 2 pm and dentist on thursday at 9 am |
| 18.0 | hybrid | extend the meeting with Tal tomorrow until 3 pm |
| 16.9 | hybrid | two tasks due tomorrow: buy groceries and return the library book |
| 16.4 | llm | tomorrow: Shacharit at 6:30, Haxaga TA at 12, dinner with Ezra at 8 pm, and remi |
| 15.3 | hybrid | move my 1pm meeting tomorrow to 3pm |

## Raw

Full per-case JSON: `DOCUMENTATION/ASSISTANT_AUDIT.md.json`