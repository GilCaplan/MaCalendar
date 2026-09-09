# Assistant audit — accuracy, latency, self-check

_Generated 2026-09-08 23:11 · 25 commands · scratch DB · vocabulary 375 words · machine arm64. Re-run: `python -m scripts.audit_assistant`._

## Headline

- **Correct after the quick answer:** 72%  ·  **correct once settled (after self-check):** 72% — case-level exact match against this corpus's hand-written expectations, 25 cases, not a real-usage or human-judged figure
- **Recall 75%** (27/36 expected items produced correctly) · **precision 97%** (32/33 produced actions were expected) — accuracy alone doesn't distinguish missing something asked for from producing something extra
- **Time to first result:** p50 0.1 s · p95 15.7 s  ·  **time to settled:** p50 0.1 s · p95 15.7 s
- Parse paths: deep 11, fast 14

## By area

| Area | n | quick ✓ | settled ✓ | recall | precision | first p50 | first p95 | settled p50 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| events | 25 | 72% | 72% | 75% | 97% | 0.1 s | 15.7 s | 0.1 s |

## By parse path

| Path | n | quick ✓ | settled ✓ | recall | precision | first p50 | first p95 | LLM ms p50 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| deep | 11 | 73% | 73% | 76% | 95% | 6.0 s | 20.7 s | 2597 |
| fast | 14 | 71% | 71% | 73% | 100% | 0.0 s | 0.1 s | 0 |

## Quick answer vs self-check

- Self-check ran on 0 commands; it proposed a correction on 0 (0 applied).
- **Fixed by self-check:** 0  ·  **broken by self-check:** 0

## Engine stages (latency; a slow or misbehaving stage is fixed in ITS module)

| Stage | ran on | ms p50 | ms p95 |
|---|---:|---:|---:|
| vocab | 25/25 | 12 | 19 |
| rule | 25/25 | 25 | 81 |
| llm | 6/25 | 6717 | 20838 |
| validate | 6/25 | 8 | 29 |
| execute | 25/25 | 7 | 13 |
| verify | 11/25 | 2281 | 4997 |

## Named-rule fixes applied

| Rule | times |
|---|---:|
| resolve_from_own_words | 2 |
| observance_gate | 1 |

## Cross-check (step 6)

- Findings: 5 (extra, missing) across 2 command(s); loop-backs on 0 command(s) (0 re-entries total).
- Budget exhausted (answer flagged as unsure): 1.

## By shape (failures first)

| Shape | n | settled ✓ | first p50 |
|---|---:|---:|---:|
| single/terse | 1 | 0% | 0.0 s |
| multi/different-days-3 | 1 | 0% | 12.4 s |
| single/hebrew-term | 2 | 0% | 0.0 s |
| single/disfluency | 1 | 0% | 16.6 s |
| multi/different-days | 2 | 50% | 2.4 s |
| multi/same-day-2 | 3 | 67% | 2.2 s |
| single/stop-word | 1 | 100% | 0.0 s |
| single/spoken-time | 1 | 100% | 6.8 s |
| single/day-of-month | 1 | 100% | 24.9 s |
| single/explicit-time | 3 | 100% | 0.0 s |
| single/weekday | 1 | 100% | 0.0 s |
| single/range | 1 | 100% | 0.0 s |
| single/next-weekday | 1 | 100% | 1.8 s |
| single/duration | 1 | 100% | 0.1 s |
| single/place | 1 | 100% | 0.1 s |
| recurring/weekly | 1 | 100% | 0.2 s |
| multi/same-day-3 | 2 | 100% | 4.9 s |
| single/full-name | 1 | 100% | 0.1 s |

## Produced more than expected (precision failures)

Distinct from a wrong or missing answer: the system did something on top of what was asked for — an extra action, or extra rows from one action (a duplicated task from a misread clause is invisible to an action-count check, since the action count can still be right).

- **meeting tomorrow at 2 sorry not 2, 3 pm with Adin for the project** — 1 extra action(s) — got ['create_event', 'create_event']

## Failures

### events · single/hebrew-term · `fast` · 0.0 s
- **Said:** Mincha Maariv at shul tonight at 7:15
- **Did:** ['create_event'] — Created event 'shul' on Tuesday, Sep 8, 2026 from 7:15 PM to 8:15 PM.
- no event matching {'date': '2026-09-08', 'start_time': '19:15', 'title_contains': 'Mincha'} in DB [('shul', '2026-09-08', '19:15')]

### events · single/hebrew-term · `fast` · 0.1 s
- **Said:** Limud Torah at Ohel Ari on tuesday at 9 pm
- **Did:** ['create_event'] — Created event 'ohel' on Tuesday, Sep 8, 2026 from 9 PM to 10 PM.
- no event matching {'date': '2026-09-08', 'start_time': '21:00', 'title_contains': 'Limud'} in DB [('ohel', '2026-09-08', '21:00')]

### events · single/terse · `fast` · 0.0 s
- **Said:** driving lesson thursday 8 am
- **Did:** ['create_event'] — Created event 'lesson' on Thursday, Sep 10, 2026 from 8 AM to 9 AM.
- no event matching {'date': '2026-09-10', 'start_time': '08:00', 'title_contains': 'driving'} in DB [('lesson', '2026-09-10', '08:00')]

### events · single/disfluency · `deep` · 16.6 s
- **Said:** meeting tomorrow at 2 sorry not 2, 3 pm with Adin for the project
- **Did:** ['create_event', 'create_event'] — Created event 'Meeting' on Wednesday, Sep 9, 2026 from 2 PM to 4 PM. Created event 'Project meeting' on Wednesday, Sep 9, 2026 from 3 PM to 4 PM.
- extra actions ['create_event']
- no event matching {'date': '2026-09-09', 'start_time': '15:00', 'title_contains': 'Adin'} in DB [('Meeting', '2026-09-09', '14:00'), ('Project meeting', '2026-09-09', '15:00')]

### events · multi/same-day-2 · `fast` · 0.1 s
- **Said:** two events tomorrow, one at four o'clock meeting with Rei and one at seven pm pizza with Ezra
- **Did:** ['create_event'] — Created event 'rei' on Wednesday, Sep 9, 2026 from 4 PM to 5 PM.
- missing action create_event (got ['create_event'])
- no event matching {'date': '2026-09-09', 'start_time': '19:00', 'title_contains': 'Ezra'} in DB [('rei', '2026-09-09', '16:00')]

### events · multi/different-days · `deep` · 2.4 s
- **Said:** set lunch with Tal on monday at noon and coffee with Ezra on friday at 9
- **Did:** ['create_event'] — I didn't book 'lunch with tal': that's a meal on a fast day (Monday, Sep 14) — it ends at 19:24. Created event 'ezra' on Friday, Sep 11, 2026 from 9 AM to 10 AM
- missing action create_event (got ['create_event'])
- no event matching {'date': '2026-09-14', 'start_time': '12:00'} in DB [('ezra', '2026-09-11', '09:00')]

### events · multi/different-days-3 · `deep` · 12.4 s
- **Said:** gym tomorrow at 6 am, tuesday at 6 am and friday at 6 am
- **Did:** ['create_event'] — I'm not sure I caught every part of that — worth a glance. Created event 'gym' on Wednesday, Sep 9, 2026 from 6 AM to 7 AM.
- missing action create_event (got ['create_event'])
- missing action create_event (got ['create_event'])
- no event matching {'date': '2026-09-08', 'start_time': '06:00'} in DB [('gym', '2026-09-09', '06:00')]

## Slowest 10

| s | path | command |
|---:|---|---|
| 24.9 | deep | lunch with Tal at noon on the 19th |
| 16.6 | deep | meeting tomorrow at 2 sorry not 2, 3 pm with Adin for the project |
| 12.4 | deep | gym tomorrow at 6 am, tuesday at 6 am and friday at 6 am |
| 10.6 | deep | walk Kyra the dog at 3:30 pm today and then go to shul for Mincha Maariv at 7:30 |
| 6.8 | deep | book a haircut for tuesday at half past two |
| 6.0 | deep | set a meeting tomorrow at 1 pm, another one at 4 pm and then pizza at 6:30 pm to |
| 3.9 | deep | on thursday I have Shacharit at 6:30 am, a lecture at 10 and dinner with Danny a |
| 2.4 | deep | meeting with Ravid tomorrow at 2 pm and dentist on thursday at 9 am |
| 2.4 | deep | set lunch with Tal on monday at noon and coffee with Ezra on friday at 9 |
| 2.2 | deep | tomorrow gym at 7 am and a meeting with Tal at 11 |

## Raw

Full per-case JSON: `DOCUMENTATION/ASSISTANT_AUDIT.md.json`