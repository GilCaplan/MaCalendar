# Dataset run score — `DOCUMENTATION/experiments/memory_scaling/output/dummy_1000.db`

- **1000 prompts** scored · count-correct **70%** · garbage-title rate **0%**
- total_ms p50 5471 · p95 13122
- parse paths: {'hybrid': 308, 'llm': 242, 'rule': 450}

## By complexity

| Tier | n | count-correct | garbage titles | total_ms p50 |
|---|---:|---:|---:|---:|
| simple | 347 | 91% | 0% | 3111 |
| medium | 325 | 89% | 0% | 4351 |
| complex | 328 | 28% | 1% | 9036 |

## By compound kind

| Kind | n | count-correct | garbage titles | dates collapsed |
|---|---:|---:|---:|---:|
| event+event | 114 | 25% | 1% | 3% |
| task+task | 90 | 52% | 1% | 0% |
| event+task | 124 | 15% | 1% | 1% |

## event+task: which half goes missing when it fails

- both present: 18 · event missing: 84 · task missing: 9 · both missing: 13

## Correctness by parse path

| Path | count-correct |
|---|---:|
| hybrid | 57% |
| llm | 77% |
| rule | 75% |

## Count-mismatch failures (300)

- **can you schedule a meeting with Mr. Chen on next Monday 6:00pm, and then Set reminder in c** — event+event: got 1 events, 1 tasks (wanted ≥2/≥0)
- **Add event with these people and also add bread to my grocery list** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **give me the reminders** — simple: got 0 events, 2 tasks (wanted ≥0/≥0)
- **Add event, book club, Debbie's house, Wednesday night and set a list for....** — event+task: got 0 events, 0 tasks (wanted ≥1/≥1)
- **Olly, set a reminder for my meeting today and create a birthday wish reminder for tommorro** — event+event: got 0 events, 1 tasks (wanted ≥2/≥0)
- **Remember to pick me up by 12 noon from the Airport, I have a 3 pm meeting — and pDA please** — event+task: got 0 events, 2 tasks (wanted ≥1/≥1)
- **get rid of this list** — simple: got 0 events, 1 tasks (wanted ≥0/≥0)
- **Olly, please set dinner plans at 7pm for every Friday in April and pDA please set this eve** — event+event: got 1 events, 0 tasks (wanted ≥2/≥0)
- **Please repeat this event. Also, Set up recurring date on my calendar** — event+event: got 1 events, 0 tasks (wanted ≥2/≥0)
- **Set a event for the evening, and then get xxx on the list** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **Remind me to read book next week — and can you add Gloria to my list of clients?** — event+task: got 0 events, 3 tasks (wanted ≥1/≥1)
- **Open up a new list.** — simple: got 0 events, 0 tasks (wanted ≥0/≥0)
- **alexa set a meeting event reminder with mona on tuesday, and then Set a Thanks Giving even** — event+event: got 1 events, 0 tasks (wanted ≥2/≥0)
- **add a note to attend. Also, save the new list** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **pencil me in for sarahs birthday thing on the 12th, PDA. Also, Add eggs to my list** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **What are the list of things I need to buy today?** — medium: got 0 events, 3 tasks (wanted ≥0/≥0)
- **Remind me of the following event:** — simple: got 0 events, 0 tasks (wanted ≥0/≥0)
- **Add milk to my grocery list, and then update work out list with new items** — task+task: got 0 events, 1 tasks (wanted ≥0/≥2)
- **Set reminder for three o'clock** — simple: got 0 events, 0 tasks (wanted ≥0/≥0)
- **please set event on Tuesday — and alexa remind me to go to my doctors at 4pm on tuesday** — event+event: got 0 events, 1 tasks (wanted ≥2/≥0)
- **notify me about any festival occurring next month. Also, open grocery list and add milk** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **Can you sync my calendar with mark?** — medium: got 0 events, 0 tasks (wanted ≥0/≥0)
- **Please remind to get donuts for the meeting, and then new scenario, time or calendar to ne** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **Remind me the wedding on time to buy a present and create a new list of my due bills** — event+task: got 0 events, 2 tasks (wanted ≥1/≥1)
- **Set this before event and also add apples to shopping list** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **Create a new list for my birthday plans. Also, Start creating a new list** — task+task: got 0 events, 1 tasks (wanted ≥0/≥2)
- **Add Moong daal in grocery list, and then Give an entry to this list.** — task+task: got 0 events, 1 tasks (wanted ≥0/≥2)
- **Before this event set notification and bring up a new shopping list.** — event+task: got 0 events, 2 tasks (wanted ≥1/≥1)
- **create a new list of . Also, get xxx on the list** — task+task: got 0 events, 1 tasks (wanted ≥0/≥2)
- **Please set recurring calendar event and set event in calandar.  repeat event every day** — event+event: got 1 events, 0 tasks (wanted ≥2/≥0)