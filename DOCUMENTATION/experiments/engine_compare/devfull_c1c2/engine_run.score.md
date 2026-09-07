# Dataset run score — `/var/folders/0f/nk3dnvrd54jbjz_qn40_ynwh0000gn/T/engine_compare_4bo1yclu/engine_run.db`

- **600 prompts** scored · count-correct **76%** · garbage-title rate **0%**
- total_ms p50 5522 · p95 36046
- parse paths: {'deep': 329, 'fast': 271}

## By complexity

| Tier | n | count-correct | garbage titles | total_ms p50 |
|---|---:|---:|---:|---:|
| simple | 208 | 90% | 0% | 4472 |
| medium | 210 | 89% | 0% | 4372 |
| complex | 182 | 45% | 1% | 11086 |

## By compound kind

| Kind | n | count-correct | garbage titles | dates collapsed |
|---|---:|---:|---:|---:|
| event+event | 59 | 53% | 2% | 2% |
| task+task | 47 | 47% | 0% | 0% |
| event+task | 76 | 38% | 1% | 0% |

## event+task: which half goes missing when it fails

- both present: 29 · event missing: 30 · task missing: 13 · both missing: 4

## Correctness by parse path

| Path | count-correct |
|---|---:|
| deep | 77% |
| fast | 75% |

## Count-mismatch failures (143)

- **can you schedule a meeting with Mr. Chen on next Monday 6:00pm, and then Set reminder in c** — event+event: got 1 events, 1 tasks (wanted ≥2/≥0)
- **Add event, book club, Debbie's house, Wednesday night and set a list for....** — event+task: got 1 events, 0 tasks (wanted ≥1/≥1)
- **get rid of this list** — simple: got 0 events, 1 tasks (wanted ≥0/≥0)
- **Set a event for the evening, and then get xxx on the list** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **Remind me to read book next week — and can you add Gloria to my list of clients?** — event+task: got 0 events, 3 tasks (wanted ≥1/≥1)
- **Open up a new list.** — simple: got 0 events, 0 tasks (wanted ≥0/≥0)
- **Will you send a calendar invite out to James and Alice for brunch at 11 am on Tuesday and ** — event+task: got 0 events, 2 tasks (wanted ≥1/≥1)
- **add a note to attend. Also, save the new list** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **add 'christmas' to calendar** — simple: got 0 events, 0 tasks (wanted ≥0/≥0)
- **pencil me in for sarahs birthday thing on the 12th, PDA. Also, Add eggs to my list** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **Add milk to my grocery list, and then update work out list with new items** — task+task: got 0 events, 1 tasks (wanted ≥0/≥2)
- **new scenario, time or calendar to new list and also please create a list of Due payment th** — task+task: got 0 events, 1 tasks (wanted ≥0/≥2)
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

- 600 shared prompts (2399 only in A, 0 only in B)
- count-correct rate: 70% → 76%
- **32 got worse**, **64 got better**, 393 still pass, 111 still fail

### Got worse

- Name off all the lists I own.
- On the day project one is due, does my daughter have a recital?
- AAJ MARCH KI 5TH DAY HAI, HAI KI NAHI?
- Can you create a new list in my podcast?
- Favorite places to eat
- give me a reminder at 8pm for the game
- Put working out on my calendar for 8 a.m. every day this week. Also, I want to start a new list.
- Mark reminder with these people, and then Pleas set a reminder for a meeting I have on Tuesday next 
- Tell me to go to the grocery store after work.
- add 'valentine's day' with her tomorrow
- Can you add an event with John and Mary?
- Can you remind me to order the Turkey three weeks before Thanksgiving?
- add 'christmas' to calendar
- On my sisters birthday send her flowers — and hey Olly, I need you to make a list of cricket players
- Add a party in NY city for this saturday — and on Monday, the 20th, I need to have a conversation wi
- set reminder for tomorrows meeting with {client name} and also add this one also.
- remove 'table' from furniture
- Will you put in my calendar that John C. and his wife are meeting with us at four p.m. tomorrow?
- new scenario, time or calendar to new list and also please create a list of Due payment those who no
- Hey Olly, make a list of names starting with vowels and ending with vowels, and then Start a new gro

### Got better

- Please add brunch with Erin to my calendar at the Diner. Also, add a new list
- Set a reminder to call my mom at 3pm — and olly, can you please add my dinner reservations to my cal
- Schedule my 'event' with 'person' at 'time' and 'place' and i want to know could an extra item be ad
- Remind me of the following event:
- Add dentist appointment for Friday at 5 and please add meeting at work to calander
- can you add to my calendar an event for next friday and put xxx on the list
- Who is coming to the meeting tomorrow at 10 AM?
- Set this before event and also add apples to shopping list
- Repeat this event every Friday on my calendar, and then add wine to list
- Please repeat this event. Also, Set up recurring date on my calendar
- PLZ REMIND TO SLEEP AT 9 P.M. Also, add to calendar and repeat
- Set a reminder for the meeting every Monday at 2pm. Also, Make a new list of dog breeds.
- Remind me about my business meeting at 3:45pm — and get me with new list.
- On the fifth of November, I need to go to Washington, D.C, and then I'd like to set a date for this 
- Notify me when my rent due?
- Remind me to pick up John from the airport tonight at 8, and then add this to the list
- please add party at chucky cheese to calander — and i need to add pasta and milk to the grocery list
- Remember to pick me up by 12 noon from the Airport, I have a 3 pm meeting — and pDA please make a li
- alexa set a meeting event reminder with mona on tuesday, and then Set a Thanks Giving event for Frid
- Olly, will you mark that I am busy for an event tomorrow at 2 pm?