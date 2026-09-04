# Assistant audit — accuracy, latency, self-check

_Generated 2026-09-03 12:26 · 91 commands · scratch DB · vocabulary 374 words · machine arm64. Re-run: `python -m scripts.audit_assistant`._

## Headline

- **Correct after the quick answer:** 96%  ·  **correct once settled (after self-check):** 96%
- **Time to first result:** p50 6.3 s · p95 15.5 s  ·  **time to settled:** p50 17.3 s · p95 31.3 s
- Parse paths: rule 39, hybrid 9, llm 43, error 0

## By area

| Area | n | quick ✓ | settled ✓ | first p50 | first p95 | settled p50 |
|---|---:|---:|---:|---:|---:|---:|
| adversarial | 5 | 100% | 100% | 7.5 s | 9.2 s | 18.6 s |
| events | 41 | 95% | 95% | 7.8 s | 16.9 s | 18.7 s |
| from-chats | 15 | 93% | 93% | 7.4 s | 14.9 s | 20.7 s |
| mixed | 3 | 100% | 100% | 0.1 s | 19.5 s | 8.6 s |
| query | 3 | 100% | 100% | 0.0 s | 0.0 s | 3.4 s |
| tasks | 17 | 100% | 100% | 0.0 s | 8.5 s | 6.7 s |
| update-delete | 7 | 86% | 86% | 0.0 s | 6.5 s | 7.2 s |

## By parse path

| Path | n | quick ✓ | settled ✓ | first p50 | first p95 | LLM ms p50 |
|---|---:|---:|---:|---:|---:|---:|
| rule | 39 | 97% | 97% | 0.0 s | 1.8 s | 0 |
| hybrid | 9 | 89% | 89% | 8.2 s | 17.0 s | 8111 |
| llm | 43 | 95% | 95% | 8.2 s | 16.8 s | 8106 |

## Quick answer vs self-check

- Self-check ran on 91 commands; it proposed a correction on 42 (0 applied).
- **Fixed by self-check:** 0  ·  **broken by self-check:** 0

## By shape (failures first)

| Shape | n | settled ✓ | first p50 |
|---|---:|---:|---:|
| multi/disfluent-duration | 1 | 0% | 11.6 s |
| update/extend | 1 | 0% | 6.6 s |
| multi/self-correction-count | 1 | 0% | 13.1 s |
| chat-phrasing | 15 | 93% | 7.4 s |
| past-tense-noise | 1 | 100% | 7.5 s |
| task+event | 1 | 100% | 0.1 s |
| single/hebrew-term | 2 | 100% | 6.2 s |
| generated/single | 12 | 100% | 8.0 s |
| single | 2 | 100% | 0.1 s |
| task-not-event | 1 | 100% | 0.0 s |
| single/stop-word | 1 | 100% | 2.1 s |
| single/due-weekday | 1 | 100% | 0.0 s |
| multi/same-due-date | 1 | 100% | 8.2 s |
| recurring/weekly | 2 | 100% | 6.3 s |
| single/disfluency | 1 | 100% | 8.3 s |
| delete/by-title | 1 | 100% | 0.0 s |
| multi/different-days-3 | 1 | 100% | 17.0 s |
| event+task | 1 | 100% | 0.1 s |
| update/rename | 1 | 100% | 0.0 s |
| multi/different-days | 2 | 100% | 17.6 s |
| update/move-by-title | 1 | 100% | 0.0 s |
| multi/same-day-2 | 3 | 100% | 9.1 s |
| query/week | 1 | 100% | 0.0 s |
| multi/different-due-dates | 1 | 100% | 10.0 s |
| single/duration | 1 | 100% | 0.1 s |
| multi/same-list | 2 | 100% | 0.0 s |
| single/explicit-time | 3 | 100% | 0.0 s |
| single/range | 1 | 100% | 5.1 s |
| recurring/daily | 1 | 100% | 6.7 s |
| event-not-task | 1 | 100% | 0.0 s |
| multi/tagged | 1 | 100% | 0.0 s |
| multi/same-list-3 | 1 | 100% | 7.4 s |
| single/hebrew-name | 1 | 100% | 0.0 s |
| single/inferred-tag | 1 | 100% | 0.0 s |
| misheard-names | 1 | 100% | 9.5 s |
| single/day-of-month | 1 | 100% | 4.7 s |
| query/today | 1 | 100% | 0.0 s |
| query/tomorrow | 1 | 100% | 0.0 s |
| single/place | 1 | 100% | 7.2 s |
| update/move-by-time | 1 | 100% | 6.4 s |
| 3events+task | 1 | 100% | 21.6 s |
| delete/by-time | 1 | 100% | 0.0 s |
| multi/shared-verb | 1 | 100% | 0.0 s |
| update/move-day | 1 | 100% | 0.0 s |
| ambiguous/no-time | 1 | 100% | 8.3 s |
| single/next-weekday | 1 | 100% | 1.8 s |
| single/general-list | 1 | 100% | 0.0 s |
| multi/shared-verb-people | 1 | 100% | 0.0 s |
| multi/same-day-3 | 2 | 100% | 16.2 s |
| multi/shared-verb-3 | 1 | 100% | 0.0 s |
| single/weekday | 1 | 100% | 6.1 s |
| single/terse | 1 | 100% | 8.0 s |
| single/full-name | 1 | 100% | 0.1 s |
| single/spoken-time | 1 | 100% | 10.2 s |
| single/due-tomorrow | 1 | 100% | 0.0 s |
| single/internal-and | 1 | 100% | 0.1 s |

## Failures

### events · multi/disfluent-duration · `llm` · 11.6 s
- **Said:** set a meeting at 4pm today, but it is only 20 minutes meeting with one moment meeting with reards, okay, then let's do another meeting from 6 from 6 o'clock to 640 meetings with kids for project defense
- **Did:** ['create_event', 'create_event'] — Created event 'Meeting with Reards' on Thursday, Sep 3, 2026 from 4 PM to 4:20 PM. Created event 'Meetings with Kids for Project Defense' on Thursday, Sep 3, 20
- no event matching {'date': '2026-09-03', 'start_time': '18:00', 'end_time': '18:40'} in DB [('Meeting with Reards', '2026-09-03', '16:00'), ('Meetings with Kids for Project Defense', '2026-09-03', '18:00')]

### events · multi/self-correction-count · `llm` · 13.1 s
- **Said:** a meeting for me tomorrow at two one sorry one pm and four pm and then another one a pizza party at 6.30 pm at edo's
- **Did:** ['create_event', 'create_event'] — Created event 'A meeting' on Friday, Sep 4, 2026 from 2 PM to 4 PM. Created event 'A pizza party' on Friday, Sep 4, 2026 from 6:30 PM to 7 PM.
- missing action create_event (got ['create_event', 'create_event'])
- no event matching {'date': '2026-09-04', 'start_time': '13:00', 'end_time': '14:00'} in DB [('A meeting', '2026-09-04', '14:00'), ('A pizza party', '2026-09-04', '18:30')]
- no event matching {'date': '2026-09-04', 'start_time': '16:00', 'end_time': '17:00'} in DB [('A meeting', '2026-09-04', '14:00'), ('A pizza party', '2026-09-04', '18:30')]

### update-delete · update/extend · `hybrid` · 6.6 s
- **Said:** extend the meeting with Tal tomorrow until 3 pm
- **Did:** [] — I couldn't find an event at 15:00 on 2026-09-04.
- missing action update_event (got [])
- expected 'Meeting with Tal' ending 15:00; have [('Meeting with Tal', '14:00')]

### from-chats · chat-phrasing · `rule` · 7.4 s
- **Said:** meeting with Guri moved from 9:30 to 9 on wednesday
- **Did:** [] — I couldn't find an event matching 'guri'.
- missing action create_event|update_event (got [])
- no event matching {} in DB []

## Slowest 10

| s | path | command |
|---:|---|---|
| 21.6 | llm | tomorrow: Shacharit at 6:30, Haxaga TA at 12, dinner with Ezra at 8 pm, and remi |
| 21.4 | hybrid | set lunch with Tal on monday at noon and coffee with Ezra on friday at 9 |
| 17.0 | llm | gym tomorrow at 6 am, tuesday at 6 am and friday at 6 am |
| 16.9 | llm | on thursday I have Shacharit at 6:30 am, a lecture at 10 and dinner with Danny a |
| 15.5 | llm | sadna on sunday the 15th at 9 am then driving lesson at 8 am |
| 15.5 | llm | set a meeting tomorrow at 1 pm, another one at 4 pm and then pizza at 6:30 pm to |
| 14.6 | llm | night shift tomorrow from 8 pm to 6 am |
| 13.9 | llm | meeting with Ravid tomorrow at 2 pm and dentist on thursday at 9 am |
| 13.8 | llm | tomorrow gym at 7 am and a meeting with Tal at 11 |
| 13.1 | llm | a meeting for me tomorrow at two one sorry one pm and four pm and then another o |

## Raw

Full per-case JSON: `/private/tmp/claude-501/-Users-USER-Desktop-Personal-Projects-MACalendar/af0f8e17-96e3-4682-ad9e-f2c765866559/scratchpad/run8-k4.md.json`