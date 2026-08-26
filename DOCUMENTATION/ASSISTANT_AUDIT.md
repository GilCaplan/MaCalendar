# Assistant audit — accuracy, latency, self-check

_Generated 2026-08-26 15:11 · 84 commands · scratch DB · vocabulary 372 words · machine arm64. Re-run: `python -m scripts.audit_assistant`._

## Headline

- **Correct after the quick answer:** 88%  ·  **correct once settled (after self-check):** 86%
- **Time to first result:** p50 7.9 s · p95 15.8 s  ·  **time to settled:** p50 24.1 s · p95 36.0 s
- Parse paths: rule 35, hybrid 8, llm 41, error 0

## By area

| Area | n | quick ✓ | settled ✓ | first p50 | first p95 | settled p50 |
|---|---:|---:|---:|---:|---:|---:|
| adversarial | 5 | 100% | 100% | 9.6 s | 11.2 s | 25.8 s |
| events | 39 | 90% | 85% | 9.2 s | 15.8 s | 26.9 s |
| from-chats | 15 | 80% | 80% | 9.2 s | 14.4 s | 26.2 s |
| mixed | 3 | 100% | 100% | 0.1 s | 19.9 s | 11.4 s |
| query | 3 | 100% | 100% | 0.1 s | 0.1 s | 0.1 s |
| tasks | 12 | 83% | 83% | 0.1 s | 15.0 s | 9.1 s |
| update-delete | 7 | 86% | 86% | 0.1 s | 10.4 s | 9.6 s |

## By parse path

| Path | n | quick ✓ | settled ✓ | first p50 | first p95 | LLM ms p50 |
|---|---:|---:|---:|---:|---:|---:|
| rule | 35 | 91% | 91% | 0.1 s | 0.1 s | 0 |
| hybrid | 8 | 75% | 75% | 10.5 s | 15.3 s | 10436 |
| llm | 41 | 88% | 83% | 10.2 s | 17.2 s | 10026 |

## Quick answer vs self-check

- Self-check ran on 81 commands; it proposed a correction on 80 (22 applied).
- **Fixed by self-check:** 0  ·  **broken by self-check:** 2
  - broke: “meeting tomorrow at 2 sorry not 2, 3 pm with Adin for the project” → {'ok': False, 'severity': 'minor', 'applied': True, 'speech': 'Meeting time corrected to 2 pm', 'refresh': 'events'}
  - broke: “meeting with Ravid tomorrow at 2 pm and dentist on thursday at 9 am” → {'ok': False, 'severity': 'minor', 'applied': True, 'speech': 'Please correct the dentist appointment time to Thursday at 9 am', 'refresh': 'events'}

## By shape (failures first)

| Shape | n | settled ✓ | first p50 |
|---|---:|---:|---:|
| single/day-of-month | 1 | 0% | 7.8 s |
| multi/same-day-3 | 2 | 0% | 15.7 s |
| multi/different-days | 2 | 0% | 7.2 s |
| update/rename | 1 | 0% | 0.1 s |
| multi/different-due-dates | 1 | 0% | 15.7 s |
| single/disfluency | 1 | 0% | 10.2 s |
| multi/same-due-date | 1 | 0% | 14.5 s |
| chat-phrasing | 15 | 80% | 9.2 s |
| single/stop-word | 1 | 100% | 0.1 s |
| multi/different-days-3 | 1 | 100% | 15.8 s |
| single/general-list | 1 | 100% | 0.1 s |
| single/range | 1 | 100% | 9.4 s |
| past-tense-noise | 1 | 100% | 9.6 s |
| single/hebrew-term | 2 | 100% | 6.8 s |
| update/move-by-time | 1 | 100% | 11.1 s |
| 3events+task | 1 | 100% | 22.1 s |
| update/extend | 1 | 100% | 8.8 s |
| single/due-weekday | 1 | 100% | 0.1 s |
| single/next-weekday | 1 | 100% | 0.2 s |
| update/move-day | 1 | 100% | 0.1 s |
| recurring/daily | 1 | 100% | 9.9 s |
| multi/same-list | 2 | 100% | 0.1 s |
| recurring/weekly | 2 | 100% | 10.9 s |
| task-not-event | 1 | 100% | 0.1 s |
| single/explicit-time | 3 | 100% | 0.1 s |
| event+task | 1 | 100% | 0.1 s |
| single/full-name | 1 | 100% | 0.2 s |
| multi/tagged | 1 | 100% | 0.1 s |
| single/hebrew-name | 1 | 100% | 0.1 s |
| generated/single | 12 | 100% | 10.2 s |
| task+event | 1 | 100% | 0.1 s |
| ambiguous/no-time | 1 | 100% | 9.9 s |
| misheard-names | 1 | 100% | 11.5 s |
| delete/by-time | 1 | 100% | 0.1 s |
| single/due-tomorrow | 1 | 100% | 0.1 s |
| update/move-by-title | 1 | 100% | 0.1 s |
| delete/by-title | 1 | 100% | 0.1 s |
| single/spoken-time | 1 | 100% | 8.9 s |
| query/tomorrow | 1 | 100% | 0.1 s |
| query/week | 1 | 100% | 0.1 s |
| single/place | 1 | 100% | 7.7 s |
| single | 2 | 100% | 0.1 s |
| multi/same-day-2 | 3 | 100% | 14.7 s |
| multi/same-list-3 | 1 | 100% | 8.1 s |
| event-not-task | 1 | 100% | 0.1 s |
| query/today | 1 | 100% | 0.1 s |
| single/duration | 1 | 100% | 0.1 s |
| single/weekday | 1 | 100% | 6.6 s |
| single/terse | 1 | 100% | 6.3 s |

## Failures

### events · single/day-of-month · `llm` · 7.8 s
- **Said:** lunch with Tal at noon on the 19th
- **Did:** ['create_event'] — Created event 'Lunch with Tal' on Saturday, Sep 19, 2026 from 12 PM to 1 PM.
- no event matching {'start_time': '12:00', 'title_contains': 'Tal'} in DB []

### events · single/disfluency · `llm` · 10.2 s
- **Said:** meeting tomorrow at 2 sorry not 2, 3 pm with Adin for the project
- **Did:** ['create_event'] — Created event 'Meeting with Adin for the project' on Thursday, Aug 27, 2026 from 3 PM to 4 PM.
- no event matching {'date': '2026-08-27', 'start_time': '15:00', 'title_contains': 'Adin'} in DB [('Meeting with Adin for the project', '2026-08-27', '14:00')]

### events · multi/same-day-3 · `llm` · 17.2 s
- **Said:** set a meeting tomorrow at 1 pm, another one at 4 pm and then pizza at 6:30 pm tomorrow
- **Did:** ['create_event', 'create_event', 'create_event'] — Created event 'Meeting Tomorrow at 1pm' on Wednesday, Aug 26, 2026 from 1 PM to 2 PM. Created event 'Meeting Tomorrow at 4pm' on Wednesday, Aug 26, 2026 from 4 
- no event matching {'date': '2026-08-27', 'start_time': '13:00'} in DB [('Meeting Tomorrow at 1pm', '2026-08-26', '13:00'), ('Meeting Tomorrow at 4pm', '2026-08-26', '16:00'), ('Pizza Tomorrow at 6:30pm', '2026-08-26', '18:30')]
- no event matching {'date': '2026-08-27', 'start_time': '16:00'} in DB [('Meeting Tomorrow at 1pm', '2026-08-26', '13:00'), ('Meeting Tomorrow at 4pm', '2026-08-26', '16:00'), ('Pizza Tomorrow at 6:30pm', '2026-08-26', '18:30')]
- no event matching {'date': '2026-08-27', 'start_time': '18:30', 'title_contains': 'pizza'} in DB [('Meeting Tomorrow at 1pm', '2026-08-26', '13:00'), ('Meeting Tomorrow at 4pm', '2026-08-26', '16:00'), ('Pizza Tomorrow at 6:30pm', '2026-08-26', '18:30')]

### events · multi/same-day-3 · `llm` · 14.3 s
- **Said:** on thursday I have Shacharit at 6:30 am, a lecture at 10 and dinner with Danny at 8 pm
- **Did:** ['create_event', 'create_event', 'create_event'] — Created event 'Shacharit' on Thursday, Aug 27, 2026 from 6:30 AM to 7:30 AM. Created event 'Lecture' on Thursday, Aug 27, 2026 from 10 AM to 11 AM. Created even
- no event matching {'date': '2026-08-27', 'start_time': '20:00', 'title_contains': 'Danny'} in DB [('Shacharit', '2026-08-27', '06:30'), ('Lecture', '2026-08-27', '10:00'), ('Dinner with Danny', '2026-08-27', '14:00')]

### events · multi/different-days · `llm` · 14.3 s
- **Said:** meeting with Ravid tomorrow at 2 pm and dentist on thursday at 9 am
- **Did:** ['create_event', 'create_event'] — Created event 'meeting with Ravid' on Thursday, Aug 27, 2026 from 2 PM to 3 PM. Created event 'dentist' on Thursday, Aug 27, 2026 from 9 AM to 10 AM.
- no event matching {'date': '2026-08-27', 'start_time': '14:00', 'title_contains': 'Ravid'} in DB [('meeting with Ravid', '2026-08-27', '09:00'), ('dentist', '2026-08-27', '09:00')]

### events · multi/different-days · `rule` · 0.1 s
- **Said:** set lunch with Tal on monday at noon and coffee with Ezra on friday at 9
- **Did:** ['create_event'] — Created event 'lunch with tal' on Monday, Aug 31, 2026 from 12 PM to 1 PM.
- missing action create_event (got ['create_event'])
- no event matching {'date': '2026-08-28', 'start_time': '09:00'} in DB [('lunch with tal', '2026-08-31', '12:00')]

### tasks · multi/same-due-date · `hybrid` · 14.5 s
- **Said:** two tasks due tomorrow: buy groceries and return the library book
- **Did:** ['create_todo', 'create_event'] — Added 2 tasks to Today. Created event 'library book' on Thursday, Aug 27, 2026 from 9 AM to 5 PM.
- extra actions ['create_event']

### tasks · multi/different-due-dates · `hybrid` · 15.7 s
- **Said:** add buy a gift for Tamar due thursday and book the driving test due next monday
- **Did:** ['create_event', 'create_event'] — Created event 'Buy a gift for Tamar' on Thursday, Aug 27, 2026 from 9 AM to 5 PM. Created event 'Driving test' on Monday, Aug 31, 2026 from 9 AM to 5 PM.
- missing action create_todo (got ['create_event', 'create_event'])
- missing action create_todo (got ['create_event', 'create_event'])
- extra actions ['create_event', 'create_event']

### update-delete · update/rename · `rule` · 0.1 s
- **Said:** rename the meeting with Tal to robotics sync
- **Did:** ['update_event'] — No changes specified for 'Meeting with Tal'.
- expected event titled ~'robotics' at 13:00; have [('Meeting with Tal', '13:00')]

### from-chats · chat-phrasing · `llm` · 11.1 s
- **Said:** Kems tomorrow at 8 with Ravid and Ezra
- **Did:** ['create_event'] — Created event 'meeting with Ravid and Ezra' on Thursday, Aug 27, 2026 from 8 AM to 9 AM.
- no event matching {'date': '2026-08-27', 'start_time': '20:00'} in DB [('meeting with Ravid and Ezra', '2026-08-27', '08:00')]

### from-chats · chat-phrasing · `rule` · 0.1 s
- **Said:** meeting with Guri moved from 9:30 to 9 on wednesday
- **Did:** ['update_event'] — I couldn't find an event matching 'guri'.
- no event matching {} in DB []

### from-chats · chat-phrasing · `llm` · 12.5 s
- **Said:** sadna on sunday the 15th at 9 am then driving lesson at 8 am
- **Did:** ['create_event', 'create_event'] — Created event 'sadna' on Sunday, Aug 30, 2026 from 9 AM to 10 AM. Created event 'driving lesson' on Tuesday, Sep 15, 2026 from 8 AM to 9 AM.
- no event matching {'start_time': '08:00'} in DB [('sadna', '2026-08-30', '09:00')]

## Slowest 10

| s | path | command |
|---:|---|---|
| 22.1 | llm | tomorrow: Shacharit at 6:30, Haxaga TA at 12, dinner with Ezra at 8 pm, and remi |
| 18.7 | llm | night shift tomorrow from 8 pm to 6 am |
| 17.2 | llm | set a meeting tomorrow at 1 pm, another one at 4 pm and then pizza at 6:30 pm to |
| 15.8 | llm | walk Kyra the dog at 3:30 pm today and then go to shul for Mincha Maariv at 7:30 |
| 15.8 | llm | gym tomorrow at 6 am, tuesday at 6 am and friday at 6 am |
| 15.7 | hybrid | add buy a gift for Tamar due thursday and book the driving test due next monday |
| 14.7 | llm | two events tomorrow, one at four o'clock meeting with Rei and one at seven pm pi |
| 14.5 | hybrid | two tasks due tomorrow: buy groceries and return the library book |
| 14.3 | llm | on thursday I have Shacharit at 6:30 am, a lecture at 10 and dinner with Danny a |
| 14.3 | llm | meeting with Ravid tomorrow at 2 pm and dentist on thursday at 9 am |

## Audio (macOS `say` → Whisper → vocab)

3/8 correct end-to-end · STT p50 1.4 s

| ✓ | voice | said | heard | fixes |
|---|---|---|---|---|
| ✗ | Daniel | set a meeting tomorrow at 2 pm with Ravid at Kems | Set a meeting tomorrow at 2pm with Giddy and Adjems. |  |
| ✗ | Samantha | set a meeting tomorrow at 9:30 am with Tal at the  | Set a meeting tomorrow at 9.30am with Tal at the French bake |  |
| ✗ | Karen | set a meeting tomorrow at 6:15 pm with Rei at Gold | Set a meeting tomorrow at 6.15 pm with Naor et Golda. |  |
| ✓ | Daniel | dentist appointment on thursday at 9 am | Dentist appointment on Thursday at 9 a.m. |  |
| ✗ | Samantha | lunch with Tal at noon on the 19th | Lunch with Talat noon on the 19th. |  |
| ✗ | Karen | add gym at 6 am for one hour tomorrow | Adjim at 6am for 1 hour tomorrow. |  |
| ✓ | Daniel | meeting with Ravid from 3 to 4:30 pm today | Meeting with Ravid from 3-4 30 p.m. today. |  |
| ✓ | Samantha | set an event next wednesday at 2pm technion talk r | Set an event next Wednesday at 2 p.m. Technion Talk regardin |  |

## Raw

Full per-case JSON: `DOCUMENTATION/ASSISTANT_AUDIT.md.json`