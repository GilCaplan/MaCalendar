# Assistant audit — accuracy, latency, self-check

_Generated 2026-09-03 15:39 · 92 commands · scratch DB · vocabulary 374 words · machine arm64. Re-run: `python -m scripts.audit_assistant`._

## Headline

- **Correct after the quick answer:** 95%  ·  **correct once settled (after self-check):** 95% — case-level exact match against this corpus's hand-written expectations, 92 cases, not a real-usage or human-judged figure
- **Recall 94%** (106/113 expected items produced correctly) · **precision 96%** (110/112 produced actions were expected, plus 2 extra task rows beyond what was expected) — accuracy alone doesn't distinguish missing something asked for from producing something extra
- **Time to first result:** p50 10.5 s · p95 31.2 s  ·  **time to settled:** p50 28.1 s · p95 68.4 s
- Parse paths: rule 39, hybrid 10, llm 43, error 0

## By area

| Area | n | quick ✓ | settled ✓ | recall | precision | first p50 | first p95 | settled p50 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| adversarial | 5 | 100% | 100% | 100% | 100% | 10.3 s | 11.8 s | 25.0 s |
| events | 41 | 95% | 95% | 93% | 100% | 13.0 s | 34.4 s | 29.2 s |
| from-chats | 15 | 87% | 87% | 88% | 100% | 12.0 s | 14.3 s | 27.8 s |
| mixed | 3 | 100% | 100% | 100% | 100% | 0.1 s | 24.5 s | 20.4 s |
| query | 3 | 100% | 100% | 100% | 100% | 0.0 s | 0.0 s | 15.5 s |
| tasks | 18 | 94% | 94% | 95% | 83% | 0.1 s | 23.1 s | 30.1 s |
| update-delete | 7 | 100% | 100% | 100% | 100% | 0.1 s | 9.3 s | 17.1 s |

## By parse path

| Path | n | quick ✓ | settled ✓ | recall | precision | first p50 | first p95 | LLM ms p50 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| rule | 39 | 97% | 97% | 98% | 100% | 0.1 s | 4.9 s | 0 |
| hybrid | 10 | 90% | 90% | 92% | 100% | 18.1 s | 32.5 s | 18067 |
| llm | 43 | 93% | 93% | 92% | 94% | 13.1 s | 34.1 s | 12966 |

## Quick answer vs self-check

- Self-check ran on 92 commands; it proposed a correction on 49 (0 applied).
- **Fixed by self-check:** 0  ·  **broken by self-check:** 0

## By shape (failures first)

| Shape | n | settled ✓ | first p50 |
|---|---:|---:|---:|
| multi/interleaved-clauses | 1 | 0% | 15.1 s |
| multi/disfluent-duration | 1 | 0% | 15.6 s |
| multi/self-correction-count | 1 | 0% | 34.6 s |
| chat-phrasing | 15 | 87% | 12.0 s |
| single/spoken-time | 1 | 100% | 16.0 s |
| delete/by-title | 1 | 100% | 0.0 s |
| update/move-day | 1 | 100% | 0.1 s |
| multi/same-day-3 | 2 | 100% | 25.5 s |
| single/inferred-tag | 1 | 100% | 0.0 s |
| task+event | 1 | 100% | 0.1 s |
| single | 2 | 100% | 0.1 s |
| multi/same-day-2 | 3 | 100% | 17.2 s |
| multi/same-list-3 | 1 | 100% | 22.4 s |
| single/internal-and | 1 | 100% | 0.1 s |
| misheard-names | 1 | 100% | 11.1 s |
| query/week | 1 | 100% | 0.1 s |
| single/duration | 1 | 100% | 0.1 s |
| single/disfluency | 1 | 100% | 15.7 s |
| single/due-weekday | 1 | 100% | 0.1 s |
| multi/different-due-dates | 1 | 100% | 27.3 s |
| query/today | 1 | 100% | 0.0 s |
| task-not-event | 1 | 100% | 0.0 s |
| multi/different-days-3 | 1 | 100% | 34.4 s |
| single/weekday | 1 | 100% | 9.6 s |
| single/full-name | 1 | 100% | 0.2 s |
| multi/shared-verb | 1 | 100% | 0.1 s |
| multi/different-days | 2 | 100% | 33.2 s |
| 3events+task | 1 | 100% | 27.2 s |
| single/hebrew-term | 2 | 100% | 11.4 s |
| single/explicit-time | 3 | 100% | 0.1 s |
| update/extend | 1 | 100% | 10.5 s |
| single/place | 1 | 100% | 13.2 s |
| query/tomorrow | 1 | 100% | 0.0 s |
| single/stop-word | 1 | 100% | 6.8 s |
| recurring/weekly | 2 | 100% | 21.2 s |
| update/move-by-title | 1 | 100% | 0.0 s |
| update/move-by-time | 1 | 100% | 6.5 s |
| single/terse | 1 | 100% | 26.2 s |
| multi/same-due-date | 1 | 100% | 20.3 s |
| event+task | 1 | 100% | 0.1 s |
| generated/single | 12 | 100% | 11.9 s |
| single/next-weekday | 1 | 100% | 4.7 s |
| multi/same-list | 2 | 100% | 0.1 s |
| single/day-of-month | 1 | 100% | 12.5 s |
| delete/by-time | 1 | 100% | 0.0 s |
| multi/tagged | 1 | 100% | 0.1 s |
| single/hebrew-name | 1 | 100% | 0.0 s |
| update/rename | 1 | 100% | 0.1 s |
| multi/shared-verb-people | 1 | 100% | 0.1 s |
| event-not-task | 1 | 100% | 0.1 s |
| single/range | 1 | 100% | 12.4 s |
| recurring/daily | 1 | 100% | 13.1 s |
| past-tense-noise | 1 | 100% | 11.9 s |
| multi/shared-verb-3 | 1 | 100% | 0.1 s |
| single/due-tomorrow | 1 | 100% | 0.1 s |
| single/general-list | 1 | 100% | 0.1 s |
| ambiguous/no-time | 1 | 100% | 10.3 s |

## Produced more than expected (precision failures)

Distinct from a wrong or missing answer: the system did something on top of what was asked for — an extra action, or extra rows from one action (a duplicated task from a misread clause is invisible to an action-count check, since the action count can still be right).

- **[TASKS VIEW] i need to buy some groceries, i need rice and chicken, the chicken i need to get far away, the rice i can get at whole foods** — 2 extra action(s), 2 extra task row(s) — got ['create_todo', 'create_todo', 'create_todo']

## Failures

### events · multi/disfluent-duration · `llm` · 15.6 s
- **Said:** set a meeting at 4pm today, but it is only 20 minutes meeting with one moment meeting with reards, okay, then let's do another meeting from 6 from 6 o'clock to 640 meetings with kids for project defense
- **Did:** ['create_event', 'create_event'] — Created event 'Meeting with Reards' on Thursday, Sep 3, 2026 from 4 PM to 4:20 PM. Created event 'Meetings with Kids for Project Defense' on Thursday, Sep 3, 20
- no event matching {'date': '2026-09-03', 'start_time': '18:00', 'end_time': '18:40'} in DB [('Meeting with Reards', '2026-09-03', '16:00'), ('Meetings with Kids for Project Defense', '2026-09-03', '18:00')]

### events · multi/self-correction-count · `llm` · 34.6 s
- **Said:** a meeting for me tomorrow at two one sorry one pm and four pm and then another one a pizza party at 6.30 pm at edo's
- **Did:** ['create_event', 'create_event'] — Created event 'Meeting' on Friday, Sep 4, 2026 from 2 PM to 4 PM. Created event 'Pizza Party' on Friday, Sep 4, 2026 from 6:30 PM to 7:30 PM.
- missing action create_event (got ['create_event', 'create_event'])
- no event matching {'date': '2026-09-04', 'start_time': '13:00', 'end_time': '14:00'} in DB [('Meeting', '2026-09-04', '14:00'), ('Pizza Party', '2026-09-04', '18:30')]
- no event matching {'date': '2026-09-04', 'start_time': '16:00', 'end_time': '17:00'} in DB [('Meeting', '2026-09-04', '14:00'), ('Pizza Party', '2026-09-04', '18:30')]

### tasks · multi/interleaved-clauses · `llm` · 15.1 s
- **Said:** [TASKS VIEW] i need to buy some groceries, i need rice and chicken, the chicken i need to get far away, the rice i can get at whole foods
- **Did:** ['create_todo', 'create_todo', 'create_todo'] — Added 'buy rice' and 'buy chicken' to Today tagged Groceries. Added 'get chicken far away' to Today tagged Groceries. Added 'buy rice at whole foods' to Today t
- extra actions ['create_todo', 'create_todo']
- expected 2 todos, got 4: ['buy rice', 'buy chicken', 'get chicken far away', 'buy rice at whole foods']

### from-chats · chat-phrasing · `hybrid` · 10.6 s
- **Said:** night shift tomorrow from 8 pm to 6 am
- **Did:** [] — I couldn't find an event matching 'night shift'.
- missing action create_event (got [])
- no event matching {'date': '2026-09-04', 'start_time': '20:00'} in DB []

### from-chats · chat-phrasing · `rule` · 14.0 s
- **Said:** meeting with Guri moved from 9:30 to 9 on wednesday
- **Did:** [] — I couldn't find an event matching 'guri'.
- missing action create_event|update_event (got [])
- no event matching {} in DB []

## Slowest 10

| s | path | command |
|---:|---|---|
| 34.8 | llm | meeting with Ravid tomorrow at 2 pm and dentist on thursday at 9 am |
| 34.6 | llm | a meeting for me tomorrow at two one sorry one pm and four pm and then another o |
| 34.4 | llm | gym tomorrow at 6 am, tuesday at 6 am and friday at 6 am |
| 33.3 | hybrid | schedule gym every monday at 6 am |
| 31.5 | hybrid | set lunch with Tal on monday at noon and coffee with Ezra on friday at 9 |
| 30.9 | llm | two events tomorrow, one at four o'clock meeting with Rei and one at seven pm pi |
| 27.3 | hybrid | add buy a gift for Tamar due thursday and book the driving test due next monday |
| 27.2 | llm | tomorrow: Shacharit at 6:30, Haxaga TA at 12, dinner with Ezra at 8 pm, and remi |
| 26.9 | llm | on thursday I have Shacharit at 6:30 am, a lecture at 10 and dinner with Danny a |
| 26.2 | llm | driving lesson thursday 8 am |

## Raw

Full per-case JSON: `DOCUMENTATION/experiments/memory_scaling/B_k4.md.json`