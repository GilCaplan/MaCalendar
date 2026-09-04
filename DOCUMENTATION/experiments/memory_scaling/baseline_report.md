# Assistant audit — accuracy, latency, self-check

_Generated 2026-09-03 13:35 · 92 commands · scratch DB · vocabulary 374 words · machine arm64. Re-run: `python -m scripts.audit_assistant`._

## Headline

- **Correct after the quick answer:** 92%  ·  **correct once settled (after self-check):** 92% — case-level exact match against this corpus's hand-written expectations, 92 cases, not a real-usage or human-judged figure
- **Recall 93%** (105/113 expected items produced correctly) · **precision 96%** (111/114 produced actions were expected, plus 2 extra task rows beyond what was expected) — accuracy alone doesn't distinguish missing something asked for from producing something extra
- **Time to first result:** p50 8.9 s · p95 18.9 s  ·  **time to settled:** p50 21.6 s · p95 33.5 s
- Parse paths: rule 39, hybrid 8, llm 45, error 0

## By area

| Area | n | quick ✓ | settled ✓ | recall | precision | first p50 | first p95 | settled p50 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| adversarial | 5 | 100% | 100% | 100% | 100% | 9.1 s | 9.9 s | 20.7 s |
| events | 41 | 95% | 95% | 93% | 100% | 10.0 s | 18.8 s | 25.9 s |
| from-chats | 15 | 87% | 87% | 88% | 100% | 10.7 s | 15.7 s | 21.9 s |
| mixed | 3 | 100% | 100% | 100% | 100% | 0.1 s | 20.1 s | 11.9 s |
| query | 3 | 100% | 100% | 100% | 100% | 0.0 s | 0.0 s | 5.2 s |
| tasks | 18 | 89% | 89% | 95% | 79% | 0.0 s | 14.2 s | 6.2 s |
| update-delete | 7 | 86% | 86% | 86% | 100% | 0.0 s | 18.5 s | 12.4 s |

## By parse path

| Path | n | quick ✓ | settled ✓ | recall | precision | first p50 | first p95 | LLM ms p50 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| rule | 39 | 97% | 97% | 98% | 100% | 0.0 s | 3.4 s | 0 |
| hybrid | 8 | 75% | 75% | 90% | 91% | 10.5 s | 20.0 s | 10423 |
| llm | 45 | 91% | 91% | 90% | 94% | 11.2 s | 21.7 s | 11097 |

## Quick answer vs self-check

- Self-check ran on 92 commands; it proposed a correction on 5 (0 applied).
- **Fixed by self-check:** 0  ·  **broken by self-check:** 0

## By shape (failures first)

| Shape | n | settled ✓ | first p50 |
|---|---:|---:|---:|
| multi/self-correction-count | 1 | 0% | 13.4 s |
| multi/interleaved-clauses | 1 | 0% | 10.4 s |
| multi/disfluent-duration | 1 | 0% | 15.7 s |
| update/move-by-time | 1 | 0% | 9.2 s |
| multi/same-due-date | 1 | 0% | 11.0 s |
| chat-phrasing | 15 | 87% | 10.7 s |
| recurring/daily | 1 | 100% | 9.2 s |
| recurring/weekly | 2 | 100% | 10.0 s |
| update/move-day | 1 | 100% | 0.0 s |
| misheard-names | 1 | 100% | 9.1 s |
| multi/same-list-3 | 1 | 100% | 14.9 s |
| single/explicit-time | 3 | 100% | 0.0 s |
| multi/different-days | 2 | 100% | 18.5 s |
| multi/same-list | 2 | 100% | 0.0 s |
| multi/shared-verb-3 | 1 | 100% | 0.0 s |
| query/today | 1 | 100% | 0.0 s |
| multi/tagged | 1 | 100% | 0.0 s |
| multi/different-due-dates | 1 | 100% | 14.1 s |
| single/general-list | 1 | 100% | 0.0 s |
| past-tense-noise | 1 | 100% | 9.8 s |
| generated/single | 12 | 100% | 9.1 s |
| multi/different-days-3 | 1 | 100% | 19.0 s |
| delete/by-time | 1 | 100% | 0.0 s |
| single/stop-word | 1 | 100% | 8.5 s |
| query/tomorrow | 1 | 100% | 0.0 s |
| single/day-of-month | 1 | 100% | 11.0 s |
| multi/same-day-3 | 2 | 100% | 18.1 s |
| single/duration | 1 | 100% | 0.0 s |
| delete/by-title | 1 | 100% | 0.0 s |
| event-not-task | 1 | 100% | 0.1 s |
| single/disfluency | 1 | 100% | 9.1 s |
| multi/same-day-2 | 3 | 100% | 13.0 s |
| single/terse | 1 | 100% | 8.5 s |
| single/range | 1 | 100% | 12.2 s |
| single/due-weekday | 1 | 100% | 0.0 s |
| update/rename | 1 | 100% | 0.0 s |
| single/full-name | 1 | 100% | 0.1 s |
| multi/shared-verb | 1 | 100% | 0.0 s |
| single | 2 | 100% | 0.0 s |
| single/inferred-tag | 1 | 100% | 0.0 s |
| query/week | 1 | 100% | 0.0 s |
| task-not-event | 1 | 100% | 0.0 s |
| multi/shared-verb-people | 1 | 100% | 0.0 s |
| single/due-tomorrow | 1 | 100% | 0.0 s |
| single/next-weekday | 1 | 100% | 13.5 s |
| task+event | 1 | 100% | 0.1 s |
| event+task | 1 | 100% | 0.1 s |
| single/hebrew-name | 1 | 100% | 0.0 s |
| single/hebrew-term | 2 | 100% | 14.8 s |
| single/weekday | 1 | 100% | 8.0 s |
| single/internal-and | 1 | 100% | 0.0 s |
| ambiguous/no-time | 1 | 100% | 9.9 s |
| update/extend | 1 | 100% | 22.4 s |
| update/move-by-title | 1 | 100% | 0.0 s |
| single/place | 1 | 100% | 9.6 s |
| 3events+task | 1 | 100% | 22.3 s |
| single/spoken-time | 1 | 100% | 9.3 s |

## Produced more than expected (precision failures)

Distinct from a wrong or missing answer: the system did something on top of what was asked for — an extra action, or extra rows from one action (a duplicated task from a misread clause is invisible to an action-count check, since the action count can still be right).

- **two tasks due tomorrow: buy groceries and return the library book** — 1 extra action(s) — got ['create_todo', 'create_todo']
- **[TASKS VIEW] i need to buy some groceries, i need rice and chicken, the chicken i need to get far away, the rice i can get at whole foods** — 2 extra action(s), 2 extra task row(s) — got ['create_todo', 'create_todo', 'create_todo']

## Failures

### events · multi/disfluent-duration · `llm` · 15.7 s
- **Said:** set a meeting at 4pm today, but it is only 20 minutes meeting with one moment meeting with reards, okay, then let's do another meeting from 6 from 6 o'clock to 640 meetings with kids for project defense
- **Did:** ['create_event', 'create_event'] — Created event 'Meeting with Reards' on Thursday, Sep 3, 2026 from 4 PM to 4:20 PM. Created event 'Meeting with kids for project defense' on Thursday, Sep 3, 202
- no event matching {'date': '2026-09-03', 'start_time': '18:00', 'end_time': '18:40'} in DB [('Meeting with Reards', '2026-09-03', '16:00'), ('Meeting with kids for project defense', '2026-09-03', '18:00')]

### events · multi/self-correction-count · `llm` · 13.4 s
- **Said:** a meeting for me tomorrow at two one sorry one pm and four pm and then another one a pizza party at 6.30 pm at edo's
- **Did:** ['create_event', 'create_event'] — Created event 'Meeting' on Friday, Sep 4, 2026 from 1 PM to 4 PM. Created event 'Pizza Party' on Friday, Sep 4, 2026 from 6:30 PM to 7:30 PM.
- missing action create_event (got ['create_event', 'create_event'])
- no event matching {'date': '2026-09-04', 'start_time': '13:00', 'end_time': '14:00'} in DB [('Meeting', '2026-09-04', '13:00'), ('Pizza Party', '2026-09-04', '18:30')]
- no event matching {'date': '2026-09-04', 'start_time': '16:00', 'end_time': '17:00'} in DB [('Meeting', '2026-09-04', '13:00'), ('Pizza Party', '2026-09-04', '18:30')]

### tasks · multi/same-due-date · `hybrid` · 11.0 s
- **Said:** two tasks due tomorrow: buy groceries and return the library book
- **Did:** ['create_todo', 'create_todo'] — Added 'buy groceries' to Today tagged Groceries. Added 'return the library book' to Today tagged Errands.
- extra actions ['create_todo']

### tasks · multi/interleaved-clauses · `llm` · 10.4 s
- **Said:** [TASKS VIEW] i need to buy some groceries, i need rice and chicken, the chicken i need to get far away, the rice i can get at whole foods
- **Did:** ['create_todo', 'create_todo', 'create_todo'] — Added 'buy rice' and 'buy chicken' to Today tagged Groceries. Added 'get chicken far away' to Today tagged Groceries. Added 'get rice at whole foods' to Today t
- extra actions ['create_todo', 'create_todo']
- expected 2 todos, got 4: ['buy rice', 'buy chicken', 'get chicken far away', 'get rice at whole foods']

### update-delete · update/move-by-time · `hybrid` · 9.2 s
- **Said:** move my 1pm meeting tomorrow to 3pm
- **Did:** ['update_event'] — Updated 'Meeting with Tal' successfully.
- expected 'Meeting with Tal' at 15:00; have [('Meeting with Tal', '2026-09-04', '13:00')]

### from-chats · chat-phrasing · `llm` · 11.6 s
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
| 23.5 | llm | night shift tomorrow from 8 pm to 6 am |
| 22.8 | hybrid | set lunch with Tal on monday at noon and coffee with Ezra on friday at 9 |
| 22.4 | llm | extend the meeting with Tal tomorrow until 3 pm |
| 22.3 | llm | tomorrow: Shacharit at 6:30, Haxaga TA at 12, dinner with Ezra at 8 pm, and remi |
| 19.0 | llm | gym tomorrow at 6 am, tuesday at 6 am and friday at 6 am |
| 18.8 | llm | on thursday I have Shacharit at 6:30 am, a lecture at 10 and dinner with Danny a |
| 17.4 | llm | set a meeting tomorrow at 1 pm, another one at 4 pm and then pizza at 6:30 pm to |
| 15.7 | llm | set a meeting at 4pm today, but it is only 20 minutes meeting with one moment me |
| 15.4 | llm | Limud Torah at Ohel Ari on tuesday at 9 pm |
| 15.2 | llm | meeting with Ravid on monday at 9:30 am about Bagrut prep |

## Raw

Full per-case JSON: `DOCUMENTATION/experiments/memory_scaling/baseline_report.md.json`