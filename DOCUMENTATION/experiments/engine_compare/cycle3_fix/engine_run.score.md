# Dataset run score — `/var/folders/0f/nk3dnvrd54jbjz_qn40_ynwh0000gn/T/engine_compare_t3y16t4b/engine_run.db`

- **250 prompts** scored · count-correct **78%** · garbage-title rate **1%**
- total_ms p50 6216 · p95 34936
- parse paths: {'deep': 147, 'fast': 103}

## By complexity

| Tier | n | count-correct | garbage titles | total_ms p50 |
|---|---:|---:|---:|---:|
| simple | 88 | 90% | 0% | 4348 |
| medium | 78 | 92% | 0% | 3765 |
| complex | 84 | 51% | 2% | 12954 |

## By compound kind

| Kind | n | count-correct | garbage titles | dates collapsed |
|---|---:|---:|---:|---:|
| event+event | 27 | 63% | 4% | 0% |
| task+task | 20 | 55% | 0% | 0% |
| event+task | 37 | 41% | 3% | 0% |

## event+task: which half goes missing when it fails

- both present: 15 · event missing: 16 · task missing: 6 · both missing: 0

## Correctness by parse path

| Path | count-correct |
|---|---:|
| deep | 77% |
| fast | 79% |

## Count-mismatch failures (56)

- **can you schedule a meeting with Mr. Chen on next Monday 6:00pm, and then Set reminder in c** — event+event: got 1 events, 1 tasks (wanted ≥2/≥0)
- **Add event, book club, Debbie's house, Wednesday night and set a list for....** — event+task: got 1 events, 0 tasks (wanted ≥1/≥1)
- **get rid of this list** — simple: got 0 events, 1 tasks (wanted ≥0/≥0)
- **Set a event for the evening, and then get xxx on the list** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **Remind me to read book next week — and can you add Gloria to my list of clients?** — event+task: got 0 events, 3 tasks (wanted ≥1/≥1)
- **Open up a new list.** — simple: got 0 events, 0 tasks (wanted ≥0/≥0)
- **Will you send a calendar invite out to James and Alice for brunch at 11 am on Tuesday and ** — event+task: got 0 events, 2 tasks (wanted ≥1/≥1)
- **add a note to attend. Also, save the new list** — event+task: got 1 events, 0 tasks (wanted ≥1/≥1)
- **pencil me in for sarahs birthday thing on the 12th, PDA. Also, Add eggs to my list** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **Remind me of the following event:** — simple: got 0 events, 0 tasks (wanted ≥0/≥0)
- **Add milk to my grocery list, and then update work out list with new items** — task+task: got 0 events, 1 tasks (wanted ≥0/≥2)
- **new scenario, time or calendar to new list and also please create a list of Due payment th** — task+task: got 1 events, 1 tasks (wanted ≥0/≥2)
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
- **Do I need to be reminded of any meetings on Monday?** — medium: got 0 events, 0 tasks (wanted ≥0/≥0)
- **Open me a new list — and please add milk to the grocery list** — task+task: got 0 events, 1 tasks (wanted ≥0/≥2)
- **Remind me at the 15th of every month and pUT MILK ON MY SHOPPING LIST** — event+task: got 0 events, 2 tasks (wanted ≥1/≥1)

## Comparison

- 250 shared prompts (2749 only in A, 0 only in B)
- count-correct rate: 70% → 78%
- **11 got worse**, **37 got better**, 157 still pass, 45 still fail

### Got worse

- Do I need to be reminded of any meetings on Monday?
- AAJ MARCH KI 5TH DAY HAI, HAI KI NAHI?
- Favorite places to eat
- Can you create a new list in my podcast?
- new scenario, time or calendar to new list and also please create a list of Due payment those who no
- Will you send a calendar invite out to James and Alice for brunch at 11 am on Tuesday and also my ne
- Mark reminder with these people, and then Pleas set a reminder for a meeting I have on Tuesday next 
- Is 23 december sunday
- remove 'table' from furniture
- set reminder for tomorrows meeting with {client name} and also add this one also.
- Add a party in NY city for this saturday — and on Monday, the 20th, I need to have a conversation wi

### Got better

- Set reminder for three o'clock
- Make a note of an event  'exhibition 2017 mass' on Mar 25 and also add to the list
- Add event with these people and also add bread to my grocery list
- Notify me when my rent due?
- Olly, set a reminder for my meeting today and create a birthday wish reminder for tommorrow at 10 AM
- please add this event — and schedule a meeting on Tuesday
- Schedule my 'event' with 'person' at 'time' and 'place' and i want to know could an extra item be ad
- Please repeat this event. Also, Set up recurring date on my calendar
- remind me at 5:00pm that I have a meeting, and then Please create a new list
- Add to calendar a home visit everyday this week and also make new list of recent workouts
- give me the reminders
- Create a new list for my birthday plans. Also, Start creating a new list
- Remind me on 5th March of every year to arrange wedding anniversary presents and put this on my list
- Every Wednesday night at 5pm remind me to meet Phil and also make a new list for me, please.
- Set a reminder for a meeting at 2pm tomorrow between myself and John.
- Olly, please set dinner plans at 7pm for every Friday in April and pDA please set this event on repe
- COULD YOU PLEASE TELL WHEN WE HAVE TO PAY FOR CAR INSURANCE?
- Repeat this event every Friday on my calendar, and then add wine to list
- Please set recurring calendar event and set event in calandar.  repeat event every day
- PDA, mark sarahs b-day party on the 12th. Also, I need to set up a recurring event in my calendar pl