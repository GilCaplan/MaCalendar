# Dataset run score — `/var/folders/0f/nk3dnvrd54jbjz_qn40_ynwh0000gn/T/engine_compare_n_82lsw0/engine_run.db`

- **250 prompts** scored · count-correct **78%** · garbage-title rate **1%**
- total_ms p50 7186 · p95 47244
- parse paths: {'deep': 147, 'fast': 103}

## By complexity

| Tier | n | count-correct | garbage titles | total_ms p50 |
|---|---:|---:|---:|---:|
| simple | 88 | 92% | 0% | 4932 |
| medium | 78 | 91% | 0% | 4500 |
| complex | 84 | 52% | 2% | 15250 |

## By compound kind

| Kind | n | count-correct | garbage titles | dates collapsed |
|---|---:|---:|---:|---:|
| event+event | 27 | 63% | 4% | 4% |
| task+task | 20 | 50% | 0% | 0% |
| event+task | 37 | 46% | 3% | 0% |

## event+task: which half goes missing when it fails

- both present: 17 · event missing: 14 · task missing: 6 · both missing: 0

## Correctness by parse path

| Path | count-correct |
|---|---:|
| deep | 78% |
| fast | 80% |

## Count-mismatch failures (54)

- **can you schedule a meeting with Mr. Chen on next Monday 6:00pm, and then Set reminder in c** — event+event: got 1 events, 1 tasks (wanted ≥2/≥0)
- **Add event, book club, Debbie's house, Wednesday night and set a list for....** — event+task: got 1 events, 0 tasks (wanted ≥1/≥1)
- **get rid of this list** — simple: got 0 events, 1 tasks (wanted ≥0/≥0)
- **Olly, please set dinner plans at 7pm for every Friday in April and pDA please set this eve** — event+event: got 1 events, 0 tasks (wanted ≥2/≥0)
- **Set a event for the evening, and then get xxx on the list** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **Remind me to read book next week — and can you add Gloria to my list of clients?** — event+task: got 0 events, 3 tasks (wanted ≥1/≥1)
- **Open up a new list.** — simple: got 0 events, 0 tasks (wanted ≥0/≥0)
- **add a note to attend. Also, save the new list** — event+task: got 1 events, 0 tasks (wanted ≥1/≥1)
- **pencil me in for sarahs birthday thing on the 12th, PDA. Also, Add eggs to my list** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **Add milk to my grocery list, and then update work out list with new items** — task+task: got 0 events, 1 tasks (wanted ≥0/≥2)
- **new scenario, time or calendar to new list and also please create a list of Due payment th** — task+task: got 0 events, 0 tasks (wanted ≥0/≥2)
- **remove 'table' from furniture** — simple: got 0 events, 1 tasks (wanted ≥0/≥0)
- **notify me about any festival occurring next month. Also, open grocery list and add milk** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **Can you sync my calendar with mark?** — medium: got 0 events, 0 tasks (wanted ≥0/≥0)
- **Please remind to get donuts for the meeting, and then new scenario, time or calendar to ne** — event+task: got 0 events, 2 tasks (wanted ≥1/≥1)
- **Remind me the wedding on time to buy a present and create a new list of my due bills** — event+task: got 0 events, 2 tasks (wanted ≥1/≥1)
- **Mark reminder with these people, and then Pleas set a reminder for a meeting I have on Tue** — event+event: got 1 events, 0 tasks (wanted ≥2/≥0)
- **Add Moong daal in grocery list, and then Give an entry to this list.** — task+task: got 0 events, 1 tasks (wanted ≥0/≥2)
- **set reminder for tomorrows meeting with {client name} and also add this one also.** — event+task: got 2 events, 0 tasks (wanted ≥1/≥1)
- **Before this event set notification and bring up a new shopping list.** — event+task: got 1 events, 0 tasks (wanted ≥1/≥1)
- **Add a party in NY city for this saturday — and on Monday, the 20th, I need to have a conve** — event+event: got 1 events, 0 tasks (wanted ≥2/≥0)
- **Can you create a new list in my podcast?** — medium: got 0 events, 0 tasks (wanted ≥0/≥0)
- **Set me a reminder for the get-together with the women's club on Sunday after church — and ** — event+event: got 1 events, 0 tasks (wanted ≥2/≥0)
- **Remind me the wedding on time to buy a present — and grocery list add eggs** — event+task: got 0 events, 2 tasks (wanted ≥1/≥1)
- **Remind me to meet James at work tomorrow at 9am, and then Remind me of my meeting tomorrow** — event+event: got 1 events, 2 tasks (wanted ≥2/≥0)
- **remind me about thing at time, and then I want you to remind me the next meeting with my g** — event+event: got 1 events, 1 tasks (wanted ≥2/≥0)
- **Church with Mom and Dad on Sunday.** — medium: got 0 events, 0 tasks (wanted ≥0/≥0)
- **Do I need to be reminded of any meetings on Monday?** — medium: got 0 events, 0 tasks (wanted ≥0/≥0)
- **Open me a new list — and please add milk to the grocery list** — task+task: got 0 events, 1 tasks (wanted ≥0/≥2)
- **On the day project one is due, does my daughter have a recital?** — medium: got 0 events, 1 tasks (wanted ≥0/≥0)

## Comparison

- 250 shared prompts (2749 only in A, 0 only in B)
- count-correct rate: 70% → 78%
- **11 got worse**, **39 got better**, 157 still pass, 43 still fail

### Got worse

- Is 23 december sunday
- Church with Mom and Dad on Sunday.
- new scenario, time or calendar to new list and also please create a list of Due payment those who no
- On the day project one is due, does my daughter have a recital?
- Mark reminder with these people, and then Pleas set a reminder for a meeting I have on Tuesday next 
- remove 'table' from furniture
- Add a party in NY city for this saturday — and on Monday, the 20th, I need to have a conversation wi
- Favorite places to eat
- Can you create a new list in my podcast?
- set reminder for tomorrows meeting with {client name} and also add this one also.
- Do I need to be reminded of any meetings on Monday?

### Got better

- alexa set a meeting event reminder with mona on tuesday, and then Set a Thanks Giving event for Frid
- Olly, set a reminder for my meeting today and create a birthday wish reminder for tommorrow at 10 AM
- Set a reminder for the meeting every Monday at 2pm. Also, Make a new list of dog breeds.
- Set a reminder for a meeting at 2pm tomorrow between myself and John.
- Remind me on 5th March of every year to arrange wedding anniversary presents and put this on my list
- Repeat this event every Friday on my calendar, and then add wine to list
- Please set a reminder for church services on Sundays for 11am.
- Remember to pick me up by 12 noon from the Airport, I have a 3 pm meeting — and pDA please make a li
- Add Event on Ausgut 21 at 9am and please add an event to my calendar.
- Every Wednesday night at 5pm remind me to meet Phil and also make a new list for me, please.
- set reminder at 3 pm
- Create a new list for my birthday plans. Also, Start creating a new list
- Olly, add lunch appointment with Lisa to January 2nd at 12:30pm. Also, Remind me at the 15th of ever
- Schedule my 'event' with 'person' at 'time' and 'place' and i want to know could an extra item be ad
- Add dates without me having to tell to, like tv schedules. Also, Please remind me about the 11am bus
- Make a note of an event  'exhibition 2017 mass' on Mar 25 and also add to the list
- Add dentist appointment for Friday at 5 and please add meeting at work to calander
- please set event on Tuesday — and alexa remind me to go to my doctors at 4pm on tuesday
- Set this before event and also add apples to shopping list
- Please repeat this event. Also, Set up recurring date on my calendar