# Assistant audit — accuracy, latency, self-check

_Generated 2026-09-03 13:30 · 92 commands · scratch DB · vocabulary 374 words · machine arm64. Re-run: `python -m scripts.audit_assistant`._

## Headline

- **Correct after the quick answer:** 93%  ·  **correct once settled (after self-check):** 93% — case-level exact match against this corpus's hand-written expectations, 92 cases, not a real-usage or human-judged figure
- **Recall 91%** (103/113 expected items produced correctly) · **precision 95%** (108/111 produced actions were expected, plus 3 extra task rows beyond what was expected) — accuracy alone doesn't distinguish missing something asked for from producing something extra
- **Time to first result:** p50 6.2 s · p95 14.8 s  ·  **time to settled:** p50 19.0 s · p95 30.1 s
- Parse paths: rule 39, hybrid 9, llm 44, error 0

## By area

| Area | n | quick ✓ | settled ✓ | recall | precision | first p50 | first p95 | settled p50 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| adversarial | 5 | 100% | 100% | 100% | 100% | 8.7 s | 12.9 s | 21.0 s |
| events | 41 | 95% | 95% | 93% | 100% | 6.9 s | 14.7 s | 19.6 s |
| from-chats | 15 | 93% | 93% | 94% | 100% | 7.4 s | 16.7 s | 20.7 s |
| mixed | 3 | 67% | 67% | 62% | 100% | 0.1 s | 10.8 s | 7.2 s |
| query | 3 | 100% | 100% | 100% | 100% | 0.0 s | 0.0 s | 3.1 s |
| tasks | 18 | 94% | 94% | 95% | 76% | 0.0 s | 10.8 s | 17.5 s |
| update-delete | 7 | 86% | 86% | 86% | 100% | 0.0 s | 9.6 s | 6.2 s |

## By parse path

| Path | n | quick ✓ | settled ✓ | recall | precision | first p50 | first p95 | LLM ms p50 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| rule | 39 | 97% | 97% | 98% | 100% | 0.0 s | 1.7 s | 0 |
| hybrid | 9 | 89% | 89% | 91% | 100% | 7.8 s | 11.4 s | 7763 |
| llm | 44 | 91% | 91% | 87% | 91% | 8.5 s | 16.5 s | 8382 |

## Quick answer vs self-check

- Self-check ran on 92 commands; it proposed a correction on 48 (0 applied).
- **Fixed by self-check:** 0  ·  **broken by self-check:** 0

## By shape (failures first)

| Shape | n | settled ✓ | first p50 |
|---|---:|---:|---:|
| multi/disfluent-duration | 1 | 0% | 14.7 s |
| 3events+task | 1 | 0% | 11.9 s |
| multi/self-correction-count | 1 | 0% | 12.2 s |
| multi/interleaved-clauses | 1 | 0% | 16.0 s |
| update/extend | 1 | 0% | 7.7 s |
| chat-phrasing | 15 | 93% | 7.4 s |
| recurring/daily | 1 | 100% | 6.0 s |
| single | 2 | 100% | 0.0 s |
| multi/shared-verb | 1 | 100% | 0.0 s |
| single/due-tomorrow | 1 | 100% | 0.0 s |
| multi/same-list | 2 | 100% | 0.0 s |
| multi/different-due-dates | 1 | 100% | 9.9 s |
| single/hebrew-term | 2 | 100% | 6.6 s |
| update/move-by-title | 1 | 100% | 0.0 s |
| query/tomorrow | 1 | 100% | 0.0 s |
| single/day-of-month | 1 | 100% | 4.9 s |
| event+task | 1 | 100% | 0.1 s |
| query/today | 1 | 100% | 0.0 s |
| multi/same-due-date | 1 | 100% | 7.8 s |
| delete/by-time | 1 | 100% | 0.0 s |
| single/internal-and | 1 | 100% | 0.1 s |
| single/spoken-time | 1 | 100% | 5.5 s |
| single/range | 1 | 100% | 6.7 s |
| event-not-task | 1 | 100% | 0.1 s |
| single/terse | 1 | 100% | 6.2 s |
| query/week | 1 | 100% | 0.0 s |
| ambiguous/no-time | 1 | 100% | 9.0 s |
| past-tense-noise | 1 | 100% | 13.9 s |
| single/next-weekday | 1 | 100% | 1.8 s |
| single/weekday | 1 | 100% | 6.3 s |
| multi/different-days-3 | 1 | 100% | 12.6 s |
| generated/single | 12 | 100% | 7.8 s |
| single/inferred-tag | 1 | 100% | 0.0 s |
| task+event | 1 | 100% | 0.1 s |
| single/duration | 1 | 100% | 0.0 s |
| update/rename | 1 | 100% | 0.0 s |
| single/general-list | 1 | 100% | 0.0 s |
| update/move-day | 1 | 100% | 0.0 s |
| single/full-name | 1 | 100% | 0.1 s |
| multi/same-day-2 | 3 | 100% | 8.6 s |
| multi/tagged | 1 | 100% | 0.0 s |
| single/hebrew-name | 1 | 100% | 0.0 s |
| recurring/weekly | 2 | 100% | 7.0 s |
| single/explicit-time | 3 | 100% | 0.0 s |
| multi/same-list-3 | 1 | 100% | 7.7 s |
| misheard-names | 1 | 100% | 8.7 s |
| single/place | 1 | 100% | 5.5 s |
| multi/shared-verb-3 | 1 | 100% | 0.0 s |
| single/disfluency | 1 | 100% | 6.3 s |
| single/due-weekday | 1 | 100% | 0.0 s |
| delete/by-title | 1 | 100% | 0.0 s |
| multi/shared-verb-people | 1 | 100% | 0.0 s |
| task-not-event | 1 | 100% | 0.0 s |
| multi/different-days | 2 | 100% | 12.1 s |
| update/move-by-time | 1 | 100% | 10.4 s |
| multi/same-day-3 | 2 | 100% | 17.3 s |
| single/stop-word | 1 | 100% | 1.7 s |

## Produced more than expected (precision failures)

Distinct from a wrong or missing answer: the system did something on top of what was asked for — an extra action, or extra rows from one action (a duplicated task from a misread clause is invisible to an action-count check, since the action count can still be right).

- **[TASKS VIEW] i need to buy some groceries, i need rice and chicken, the chicken i need to get far away, the rice i can get at whole foods** — 3 extra action(s), 3 extra task row(s) — got ['create_todo', 'create_todo', 'create_todo', 'create_todo']

## Failures

### events · multi/disfluent-duration · `llm` · 14.7 s
- **Said:** set a meeting at 4pm today, but it is only 20 minutes meeting with one moment meeting with reards, okay, then let's do another meeting from 6 from 6 o'clock to 640 meetings with kids for project defense
- **Did:** ['create_event', 'create_event'] — Created event 'Meeting with Reards' on Thursday, Sep 3, 2026 from 4 PM to 4:20 PM. Created event 'Meetings with Kids for Project Defense' on Thursday, Sep 3, 20
- no event matching {'date': '2026-09-03', 'start_time': '18:00', 'end_time': '18:40'} in DB [('Meeting with Reards', '2026-09-03', '16:00'), ('Meetings with Kids for Project Defense', '2026-09-03', '18:00')]

### events · multi/self-correction-count · `llm` · 12.2 s
- **Said:** a meeting for me tomorrow at two one sorry one pm and four pm and then another one a pizza party at 6.30 pm at edo's
- **Did:** ['create_event', 'create_event'] — Created event 'Meeting' on Friday, Sep 4, 2026 from 1 PM to 4 PM. Created event 'Pizza Party' on Friday, Sep 4, 2026 from 6:30 PM to 7:30 PM.
- missing action create_event (got ['create_event', 'create_event'])
- no event matching {'date': '2026-09-04', 'start_time': '13:00', 'end_time': '14:00'} in DB [('Meeting', '2026-09-04', '13:00'), ('Pizza Party', '2026-09-04', '18:30')]
- no event matching {'date': '2026-09-04', 'start_time': '16:00', 'end_time': '17:00'} in DB [('Meeting', '2026-09-04', '13:00'), ('Pizza Party', '2026-09-04', '18:30')]

### tasks · multi/interleaved-clauses · `llm` · 16.0 s
- **Said:** [TASKS VIEW] i need to buy some groceries, i need rice and chicken, the chicken i need to get far away, the rice i can get at whole foods
- **Did:** ['create_todo', 'create_todo', 'create_todo', 'create_todo'] — Added 'buy rice' and 'buy chicken' to Today tagged Groceries. Added 'get chicken far away' to Today tagged Groceries. Added 'buy rice' to Today tagged Groceries
- extra actions ['create_todo', 'create_todo', 'create_todo']
- expected 2 todos, got 5: ['buy rice', 'buy chicken', 'get chicken far away', 'buy rice', 'buy at whole foods']

### update-delete · update/extend · `hybrid` · 7.7 s
- **Said:** extend the meeting with Tal tomorrow until 3 pm
- **Did:** [] — I couldn't find an event at 15:00 on 2026-09-04.
- missing action update_event (got [])
- expected 'Meeting with Tal' ending 15:00; have [('Meeting with Tal', '14:00')]

### mixed · 3events+task · `llm` · 11.9 s
- **Said:** tomorrow: Shacharit at 6:30, Haxaga TA at 12, dinner with Ezra at 8 pm, and remind me to pay rent
- **Did:** ['create_event', 'create_todo'] — Created event 'Dinner with Ezra' on Friday, Sep 4, 2026 from 8 PM to 10 PM. Added 'Pay rent' to Today.
- missing action create_event (got ['create_event', 'create_todo'])
- missing action create_event (got ['create_event', 'create_todo'])
- no event matching {'date': '2026-09-04', 'start_time': '06:30'} in DB [('Dinner with Ezra', '2026-09-04', '20:00')]

### from-chats · chat-phrasing · `rule` · 5.0 s
- **Said:** meeting with Guri moved from 9:30 to 9 on wednesday
- **Did:** [] — I couldn't find an event matching 'guri'.
- missing action create_event|update_event (got [])
- no event matching {} in DB []

## Slowest 10

| s | path | command |
|---:|---|---|
| 20.6 | llm | on thursday I have Shacharit at 6:30 am, a lecture at 10 and dinner with Danny a |
| 17.1 | llm | night shift tomorrow from 8 pm to 6 am |
| 16.5 | llm | sadna on sunday the 15th at 9 am then driving lesson at 8 am |
| 16.0 | llm | [TASKS VIEW] i need to buy some groceries, i need rice and chicken, the chicken  |
| 14.9 | llm | tomorrow gym at 7 am and a meeting with Tal at 11 |
| 14.7 | llm | set a meeting at 4pm today, but it is only 20 minutes meeting with one moment me |
| 14.1 | llm | set a meeting tomorrow at 1 pm, another one at 4 pm and then pizza at 6:30 pm to |
| 13.9 | llm | I had a meeting today at 8:30 pm with Nurit to work on the project |
| 13.3 | llm | Kems tomorrow at 8 with Ravid and Ezra |
| 12.6 | llm | gym tomorrow at 6 am, tuesday at 6 am and friday at 6 am |

## Raw

Full per-case JSON: `DOCUMENTATION/experiments/memory_scaling/A_k2.md.json`