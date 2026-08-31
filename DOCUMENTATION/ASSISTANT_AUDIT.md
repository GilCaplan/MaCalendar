# Assistant audit — accuracy, latency, self-check

_Generated 2026-08-31 15:16 · 89 commands · scratch DB · vocabulary 374 words · machine arm64. Re-run: `python -m scripts.audit_assistant`._

## Headline

- **Correct after the quick answer:** 93%  ·  **correct once settled (after self-check):** 93%
- **Time to first result:** p50 5.5 s · p95 13.9 s  ·  **time to settled:** p50 5.5 s · p95 13.9 s
- Parse paths: rule 39, hybrid 9, llm 41, error 0

## By area

| Area | n | quick ✓ | settled ✓ | first p50 | first p95 | settled p50 |
|---|---:|---:|---:|---:|---:|---:|
| adversarial | 5 | 100% | 100% | 5.5 s | 8.1 s | 5.5 s |
| events | 39 | 95% | 95% | 7.7 s | 15.4 s | 7.7 s |
| from-chats | 15 | 87% | 87% | 6.3 s | 10.7 s | 6.3 s |
| mixed | 3 | 100% | 100% | 0.0 s | 15.0 s | 0.0 s |
| query | 3 | 100% | 100% | 0.0 s | 0.0 s | 0.0 s |
| tasks | 17 | 88% | 88% | 0.0 s | 6.3 s | 0.0 s |
| update-delete | 7 | 100% | 100% | 0.0 s | 6.4 s | 0.0 s |

## By parse path

| Path | n | quick ✓ | settled ✓ | first p50 | first p95 | LLM ms p50 |
|---|---:|---:|---:|---:|---:|---:|
| rule | 39 | 97% | 97% | 0.0 s | 0.2 s | 0 |
| hybrid | 9 | 78% | 78% | 6.5 s | 13.8 s | 6446 |
| llm | 41 | 93% | 93% | 7.8 s | 15.2 s | 7743 |

## Quick answer vs self-check

- Self-check ran on 0 commands; it proposed a correction on 0 (0 applied).
- **Fixed by self-check:** 0  ·  **broken by self-check:** 0

## By shape (failures first)

| Shape | n | settled ✓ | first p50 |
|---|---:|---:|---:|
| multi/different-due-dates | 1 | 0% | 6.0 s |
| multi/same-due-date | 1 | 0% | 7.6 s |
| multi/same-day-3 | 2 | 50% | 16.1 s |
| multi/same-day-2 | 3 | 67% | 11.4 s |
| chat-phrasing | 15 | 87% | 6.3 s |
| single/inferred-tag | 1 | 100% | 0.0 s |
| single/duration | 1 | 100% | 0.1 s |
| single/place | 1 | 100% | 8.2 s |
| update/extend | 1 | 100% | 6.2 s |
| misheard-names | 1 | 100% | 8.2 s |
| update/move-day | 1 | 100% | 0.0 s |
| multi/same-list | 2 | 100% | 0.0 s |
| single/internal-and | 1 | 100% | 0.0 s |
| single/hebrew-name | 1 | 100% | 0.0 s |
| multi/shared-verb-3 | 1 | 100% | 0.0 s |
| multi/different-days | 2 | 100% | 14.9 s |
| update/move-by-title | 1 | 100% | 0.0 s |
| update/move-by-time | 1 | 100% | 6.5 s |
| single/explicit-time | 3 | 100% | 0.0 s |
| multi/different-days-3 | 1 | 100% | 15.2 s |
| recurring/daily | 1 | 100% | 5.1 s |
| single/disfluency | 1 | 100% | 11.6 s |
| multi/shared-verb-people | 1 | 100% | 0.0 s |
| task+event | 1 | 100% | 0.0 s |
| update/rename | 1 | 100% | 0.0 s |
| ambiguous/no-time | 1 | 100% | 5.5 s |
| task-not-event | 1 | 100% | 0.0 s |
| single/full-name | 1 | 100% | 0.2 s |
| query/week | 1 | 100% | 0.0 s |
| single/next-weekday | 1 | 100% | 0.2 s |
| delete/by-time | 1 | 100% | 0.0 s |
| event-not-task | 1 | 100% | 0.0 s |
| single/hebrew-term | 2 | 100% | 7.2 s |
| recurring/weekly | 2 | 100% | 7.0 s |
| generated/single | 12 | 100% | 7.6 s |
| past-tense-noise | 1 | 100% | 7.7 s |
| multi/tagged | 1 | 100% | 0.0 s |
| single/day-of-month | 1 | 100% | 6.5 s |
| single/general-list | 1 | 100% | 0.0 s |
| single/weekday | 1 | 100% | 6.5 s |
| query/tomorrow | 1 | 100% | 0.0 s |
| 3events+task | 1 | 100% | 16.6 s |
| single/spoken-time | 1 | 100% | 8.7 s |
| single | 2 | 100% | 0.0 s |
| query/today | 1 | 100% | 0.0 s |
| single/due-tomorrow | 1 | 100% | 0.0 s |
| single/due-weekday | 1 | 100% | 0.0 s |
| single/range | 1 | 100% | 7.7 s |
| multi/same-list-3 | 1 | 100% | 5.2 s |
| multi/shared-verb | 1 | 100% | 0.0 s |
| event+task | 1 | 100% | 0.0 s |
| single/terse | 1 | 100% | 8.4 s |
| single/stop-word | 1 | 100% | 0.3 s |
| delete/by-title | 1 | 100% | 0.0 s |

## Failures

### events · multi/same-day-3 · `llm` · 12.5 s
- **Said:** on thursday I have Shacharit at 6:30 am, a lecture at 10 and dinner with Danny at 8 pm
- **Did:** ['create_event', 'create_event', 'create_event'] — Created event 'Dinner with Danny' on Thursday, Sep 3, 2026 from 6:30 AM to 8 PM. Created event 'Lecture' on Thursday, Sep 3, 2026 from 10 AM to 11 AM. Created e
- no event matching {'date': '2026-09-03', 'start_time': '20:00', 'title_contains': 'Danny'} in DB [('Dinner with Danny', '2026-09-03', '06:30'), ('Shacharit', '2026-09-03', '06:30'), ('Lecture', '2026-09-03', '10:00')]

### events · multi/same-day-2 · `llm` · 11.4 s
- **Said:** two events tomorrow, one at four o'clock meeting with Rei and one at seven pm pizza with Ezra
- **Did:** ['create_event', 'create_event'] — Created event 'meeting' on Tuesday, Sep 1, 2026 from 4 PM to 5 PM. Created event 'pizza with ezra' on Tuesday, Sep 1, 2026 from 7 PM to 8 PM.
- no event matching {'date': '2026-09-01', 'start_time': '16:00', 'title_contains': 'Rei'} in DB [('meeting', '2026-09-01', '16:00'), ('pizza with ezra', '2026-09-01', '19:00')]

### tasks · multi/same-due-date · `hybrid` · 7.6 s
- **Said:** two tasks due tomorrow: buy groceries and return the library book
- **Did:** ['create_todo', 'create_todo'] — Added 'buy groceries' and 'return the library book' to Today. Added 'return the library book' to Today tagged Errands.
- extra actions ['create_todo']

### tasks · multi/different-due-dates · `hybrid` · 6.0 s
- **Said:** add buy a gift for Tamar due thursday and book the driving test due next monday
- **Did:** ['create_todo'] — Added 'buy a gift for Tamar' and 'book the driving test' to Today.
- missing action create_todo (got ['create_todo'])
- todo 'buy a gift for Tamar' due 2026-09-07 != 2026-09-03
- todo 'book the driving test' due 2026-09-07 != 2026-08-31

### from-chats · chat-phrasing · `rule` · 0.0 s
- **Said:** meeting with Guri moved from 9:30 to 9 on wednesday
- **Did:** ['update_event'] — I couldn't find an event matching 'guri'.
- no event matching {} in DB []

### from-chats · chat-phrasing · `llm` · 7.4 s
- **Said:** sadna on sunday the 15th at 9 am then driving lesson at 8 am
- **Did:** ['create_event'] — Created event 'Sadna' on Sunday, Sep 6, 2026 from 9 AM to 10 AM.
- missing action create_event (got ['create_event'])
- no event matching {'start_time': '08:00'} in DB [('Sadna', '2026-09-06', '09:00')]

## Slowest 10

| s | path | command |
|---:|---|---|
| 19.7 | llm | set a meeting tomorrow at 1 pm, another one at 4 pm and then pizza at 6:30 pm to |
| 17.2 | hybrid | set lunch with Tal on monday at noon and coffee with Ezra on friday at 9 |
| 16.6 | llm | tomorrow: Shacharit at 6:30, Haxaga TA at 12, dinner with Ezra at 8 pm, and remi |
| 15.2 | llm | gym tomorrow at 6 am, tuesday at 6 am and friday at 6 am |
| 14.6 | llm | night shift tomorrow from 8 pm to 6 am |
| 12.7 | llm | walk Kyra the dog at 3:30 pm today and then go to shul for Mincha Maariv at 7:30 |
| 12.6 | llm | meeting with Ravid tomorrow at 2 pm and dentist on thursday at 9 am |
| 12.5 | llm | on thursday I have Shacharit at 6:30 am, a lecture at 10 and dinner with Danny a |
| 11.6 | llm | meeting tomorrow at 2 sorry not 2, 3 pm with Adin for the project |
| 11.4 | llm | two events tomorrow, one at four o'clock meeting with Rei and one at seven pm pi |

## Raw

Full per-case JSON: `DOCUMENTATION/ASSISTANT_AUDIT.md.json`