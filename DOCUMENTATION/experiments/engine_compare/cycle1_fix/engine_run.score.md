# Dataset run score — `/var/folders/0f/nk3dnvrd54jbjz_qn40_ynwh0000gn/T/engine_compare_bdq3mb87/engine_run.db`

- **250 prompts** scored · count-correct **76%** · garbage-title rate **1%**
- total_ms p50 5702 · p95 31317
- parse paths: {'deep': 135, 'fast': 115}

## By complexity

| Tier | n | count-correct | garbage titles | total_ms p50 |
|---|---:|---:|---:|---:|
| simple | 88 | 91% | 0% | 5078 |
| medium | 78 | 92% | 0% | 4079 |
| complex | 84 | 44% | 2% | 12044 |

## By compound kind

| Kind | n | count-correct | garbage titles | dates collapsed |
|---|---:|---:|---:|---:|
| event+event | 27 | 56% | 4% | 0% |
| task+task | 20 | 35% | 0% | 0% |
| event+task | 37 | 41% | 3% | 0% |

## event+task: which half goes missing when it fails

- both present: 15 · event missing: 18 · task missing: 4 · both missing: 0

## Correctness by parse path

| Path | count-correct |
|---|---:|
| deep | 79% |
| fast | 71% |

## Count-mismatch failures (61)

- **can you schedule a meeting with Mr. Chen on next Monday 6:00pm, and then Set reminder in c** — event+event: got 1 events, 1 tasks (wanted ≥2/≥0)
- **Add event, book club, Debbie's house, Wednesday night and set a list for....** — event+task: got 1 events, 0 tasks (wanted ≥1/≥1)
- **Olly, set a reminder for my meeting today and create a birthday wish reminder for tommorro** — event+event: got 1 events, 1 tasks (wanted ≥2/≥0)
- **get rid of this list** — simple: got 0 events, 1 tasks (wanted ≥0/≥0)
- **Set a event for the evening, and then get xxx on the list** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **Remind me to read book next week — and can you add Gloria to my list of clients?** — event+task: got 0 events, 3 tasks (wanted ≥1/≥1)
- **Open up a new list.** — simple: got 0 events, 0 tasks (wanted ≥0/≥0)
- **Will you send a calendar invite out to James and Alice for brunch at 11 am on Tuesday and ** — event+task: got 0 events, 2 tasks (wanted ≥1/≥1)
- **add a note to attend. Also, save the new list** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **pencil me in for sarahs birthday thing on the 12th, PDA. Also, Add eggs to my list** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **Add milk to my grocery list, and then update work out list with new items** — task+task: got 0 events, 1 tasks (wanted ≥0/≥2)
- **new scenario, time or calendar to new list and also please create a list of Due payment th** — task+task: got 1 events, 1 tasks (wanted ≥0/≥2)
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
- **Can you create a new list in my podcast?** — medium: got 0 events, 0 tasks (wanted ≥0/≥0)
- **Olly, add lunch appointment with Lisa to January 2nd at 12:30pm. Also, Remind me at the 15** — event+event: got 1 events, 0 tasks (wanted ≥2/≥0)
- **Set me a reminder for the get-together with the women's club on Sunday after church — and ** — event+event: got 1 events, 0 tasks (wanted ≥2/≥0)
- **Remind me the wedding on time to buy a present — and grocery list add eggs** — event+task: got 0 events, 2 tasks (wanted ≥1/≥1)
- **Remind me to meet James at work tomorrow at 9am, and then Remind me of my meeting tomorrow** — event+event: got 1 events, 2 tasks (wanted ≥2/≥0)
- **remind me about thing at time, and then I want you to remind me the next meeting with my g** — event+event: got 1 events, 0 tasks (wanted ≥2/≥0)

## Comparison

- 250 shared prompts (2749 only in A, 0 only in B)
- count-correct rate: 70% → 76%
- **12 got worse**, **33 got better**, 156 still pass, 49 still fail

### Got worse

- AAJ MARCH KI 5TH DAY HAI, HAI KI NAHI?
- new scenario, time or calendar to new list and also please create a list of Due payment those who no
- Favorite places to eat
- remove 'table' from furniture
- set reminder for tomorrows meeting with {client name} and also add this one also.
- Is 23 december sunday
- Do I need to be reminded of any meetings on Monday?
- Please earse the next birthday event
- Will you send a calendar invite out to James and Alice for brunch at 11 am on Tuesday and also my ne
- Can you create a new list in my podcast?
- Add a party in NY city for this saturday — and on Monday, the 20th, I need to have a conversation wi
- Mark reminder with these people, and then Pleas set a reminder for a meeting I have on Tuesday next 

### Got better

- Set a reminder for the meeting every Monday at 2pm. Also, Make a new list of dog breeds.
- Add to calendar a home visit everyday this week and also make new list of recent workouts
- Remind me of the following event:
- What are the list of things I need to buy today?
- Set reminder for three o'clock
- set reminder at 3 pm
- alexa set a meeting event reminder with mona on tuesday, and then Set a Thanks Giving event for Frid
- Add dates without me having to tell to, like tv schedules. Also, Please remind me about the 11am bus
- Remember to pick me up by 12 noon from the Airport, I have a 3 pm meeting — and pDA please make a li
- PDA, mark sarahs b-day party on the 12th. Also, I need to set up a recurring event in my calendar pl
- Add dentist appointment for Friday at 5 and please add meeting at work to calander
- Set this before event and also add apples to shopping list
- COULD YOU PLEASE TELL WHEN WE HAVE TO PAY FOR CAR INSURANCE?
- Make a note of an event  'exhibition 2017 mass' on Mar 25 and also add to the list
- On the fifth of November, I need to go to Washington, D.C, and then I'd like to set a date for this 
- please set event on Tuesday — and alexa remind me to go to my doctors at 4pm on tuesday
- Set a reminder for a meeting at 2pm tomorrow between myself and John.
- Please set recurring calendar event and set event in calandar.  repeat event every day
- PDA, I want to make a list and this should be automatically saved as a text file with the title, lis
- Schedule my 'event' with 'person' at 'time' and 'place' and i want to know could an extra item be ad