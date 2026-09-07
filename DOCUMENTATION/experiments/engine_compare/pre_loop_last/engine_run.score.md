# Dataset run score — `/var/folders/0f/nk3dnvrd54jbjz_qn40_ynwh0000gn/T/engine_compare_kkxys0bs/engine_run.db`

- **150 prompts** scored · count-correct **73%** · garbage-title rate **1%**
- total_ms p50 5108 · p95 37057
- parse paths: {'deep': 85, 'fast': 65}

## By complexity

| Tier | n | count-correct | garbage titles | total_ms p50 |
|---|---:|---:|---:|---:|
| simple | 48 | 90% | 0% | 4897 |
| medium | 50 | 94% | 0% | 3698 |
| complex | 52 | 38% | 4% | 12390 |

## By compound kind

| Kind | n | count-correct | garbage titles | dates collapsed |
|---|---:|---:|---:|---:|
| event+event | 17 | 47% | 6% | 0% |
| task+task | 10 | 40% | 0% | 0% |
| event+task | 25 | 32% | 4% | 0% |

## event+task: which half goes missing when it fails

- both present: 8 · event missing: 14 · task missing: 3 · both missing: 0

## Correctness by parse path

| Path | count-correct |
|---|---:|
| deep | 72% |
| fast | 75% |

## Count-mismatch failures (40)

- **can you schedule a meeting with Mr. Chen on next Monday 6:00pm, and then Set reminder in c** — event+event: got 1 events, 1 tasks (wanted ≥2/≥0)
- **give me the reminders** — simple: got 0 events, 2 tasks (wanted ≥0/≥0)
- **Add event, book club, Debbie's house, Wednesday night and set a list for....** — event+task: got 1 events, 0 tasks (wanted ≥1/≥1)
- **Olly, set a reminder for my meeting today and create a birthday wish reminder for tommorro** — event+event: got 0 events, 2 tasks (wanted ≥2/≥0)
- **get rid of this list** — simple: got 0 events, 1 tasks (wanted ≥0/≥0)
- **Set a event for the evening, and then get xxx on the list** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **Remind me to read book next week — and can you add Gloria to my list of clients?** — event+task: got 0 events, 3 tasks (wanted ≥1/≥1)
- **Open up a new list.** — simple: got 0 events, 0 tasks (wanted ≥0/≥0)
- **Will you send a calendar invite out to James and Alice for brunch at 11 am on Tuesday and ** — event+task: got 0 events, 2 tasks (wanted ≥1/≥1)
- **add a note to attend. Also, save the new list** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **add 'christmas' to calendar** — simple: got 0 events, 0 tasks (wanted ≥0/≥0)
- **pencil me in for sarahs birthday thing on the 12th, PDA. Also, Add eggs to my list** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **What are the list of things I need to buy today?** — medium: got 0 events, 2 tasks (wanted ≥0/≥0)
- **Add milk to my grocery list, and then update work out list with new items** — task+task: got 0 events, 1 tasks (wanted ≥0/≥2)
- **new scenario, time or calendar to new list and also please create a list of Due payment th** — task+task: got 0 events, 0 tasks (wanted ≥0/≥2)
- **please set event on Tuesday — and alexa remind me to go to my doctors at 4pm on tuesday** — event+event: got 0 events, 1 tasks (wanted ≥2/≥0)
- **remove 'table' from furniture** — simple: got 0 events, 1 tasks (wanted ≥0/≥0)
- **notify me about any festival occurring next month. Also, open grocery list and add milk** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **Can you sync my calendar with mark?** — medium: got 0 events, 0 tasks (wanted ≥0/≥0)
- **Please remind to get donuts for the meeting, and then new scenario, time or calendar to ne** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **Remind me the wedding on time to buy a present and create a new list of my due bills** — event+task: got 0 events, 2 tasks (wanted ≥1/≥1)
- **Mark reminder with these people, and then Pleas set a reminder for a meeting I have on Tue** — event+event: got 1 events, 0 tasks (wanted ≥2/≥0)
- **Create a new list for my birthday plans. Also, Start creating a new list** — task+task: got 0 events, 1 tasks (wanted ≥0/≥2)
- **Add Moong daal in grocery list, and then Give an entry to this list.** — task+task: got 0 events, 1 tasks (wanted ≥0/≥2)
- **set reminder for tomorrows meeting with {client name} and also add this one also.** — event+task: got 2 events, 0 tasks (wanted ≥1/≥1)
- **Before this event set notification and bring up a new shopping list.** — event+task: got 1 events, 0 tasks (wanted ≥1/≥1)
- **create a new list of . Also, get xxx on the list** — task+task: got 0 events, 1 tasks (wanted ≥0/≥2)
- **Add a party in NY city for this saturday — and on Monday, the 20th, I need to have a conve** — event+event: got 1 events, 0 tasks (wanted ≥2/≥0)
- **Olly, add lunch appointment with Lisa to January 2nd at 12:30pm. Also, Remind me at the 15** — event+event: got 1 events, 0 tasks (wanted ≥2/≥0)
- **Set me a reminder for the get-together with the women's club on Sunday after church — and ** — event+event: got 0 events, 1 tasks (wanted ≥2/≥0)

## Comparison

- 150 shared prompts (2849 only in A, 0 only in B)
- count-correct rate: 70% → 73%
- **8 got worse**, **13 got better**, 97 still pass, 32 still fail

### Got worse

- remove 'table' from furniture
- Will you send a calendar invite out to James and Alice for brunch at 11 am on Tuesday and also my ne
- Add a party in NY city for this saturday — and on Monday, the 20th, I need to have a conversation wi
- Mark reminder with these people, and then Pleas set a reminder for a meeting I have on Tuesday next 
- On the day project one is due, does my daughter have a recital?
- add 'christmas' to calendar
- set reminder for tomorrows meeting with {client name} and also add this one also.
- new scenario, time or calendar to new list and also please create a list of Due payment those who no

### Got better

- Please repeat this event. Also, Set up recurring date on my calendar
- Olly, please set dinner plans at 7pm for every Friday in April and pDA please set this event on repe
- Remind me at the 15th of every month and pUT MILK ON MY SHOPPING LIST
- Add event with these people and also add bread to my grocery list
- alexa set a meeting event reminder with mona on tuesday, and then Set a Thanks Giving event for Frid
- Please set a reminder for church services on Sundays for 11am.
- Add my co worker, Ann to submit project for work on Tuesday. Also, MAKE NEW SHCEDULE FOR TOMORROW ME
- Repeat this event every Friday on my calendar, and then add wine to list
- Remind me of the following event:
- Remember to pick me up by 12 noon from the Airport, I have a 3 pm meeting — and pDA please make a li
- Set reminder for three o'clock
- Please set recurring calendar event and set event in calandar.  repeat event every day
- Set this before event and also add apples to shopping list