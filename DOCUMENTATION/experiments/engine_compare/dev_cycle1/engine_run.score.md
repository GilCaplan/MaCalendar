# Dataset run score — `/var/folders/0f/nk3dnvrd54jbjz_qn40_ynwh0000gn/T/engine_compare_nb888uch/engine_run.db`

- **600 prompts** scored · count-correct **74%** · garbage-title rate **0%**
- total_ms p50 5580 · p95 38293
- parse paths: {'deep': 329, 'fast': 271}

## By complexity

| Tier | n | count-correct | garbage titles | total_ms p50 |
|---|---:|---:|---:|---:|
| simple | 208 | 89% | 0% | 4720 |
| medium | 210 | 90% | 0% | 4422 |
| complex | 182 | 38% | 1% | 11002 |

## By compound kind

| Kind | n | count-correct | garbage titles | dates collapsed |
|---|---:|---:|---:|---:|
| event+event | 59 | 37% | 2% | 2% |
| task+task | 47 | 49% | 0% | 0% |
| event+task | 76 | 32% | 1% | 1% |

## event+task: which half goes missing when it fails

- both present: 24 · event missing: 35 · task missing: 13 · both missing: 4

## Correctness by parse path

| Path | count-correct |
|---|---:|
| deep | 73% |
| fast | 75% |

## Count-mismatch failures (157)

- **can you schedule a meeting with Mr. Chen on next Monday 6:00pm, and then Set reminder in c** — event+event: got 1 events, 1 tasks (wanted ≥2/≥0)
- **give me the reminders** — simple: got 1 events, 0 tasks (wanted ≥0/≥0)
- **Add event, book club, Debbie's house, Wednesday night and set a list for....** — event+task: got 1 events, 0 tasks (wanted ≥1/≥1)
- **Olly, set a reminder for my meeting today and create a birthday wish reminder for tommorro** — event+event: got 1 events, 1 tasks (wanted ≥2/≥0)
- **get rid of this list** — simple: got 0 events, 1 tasks (wanted ≥0/≥0)
- **Set a event for the evening, and then get xxx on the list** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **Remind me to read book next week — and can you add Gloria to my list of clients?** — event+task: got 0 events, 3 tasks (wanted ≥1/≥1)
- **Open up a new list.** — simple: got 0 events, 0 tasks (wanted ≥0/≥0)
- **Will you send a calendar invite out to James and Alice for brunch at 11 am on Tuesday and ** — event+task: got 0 events, 2 tasks (wanted ≥1/≥1)
- **add a note to attend. Also, save the new list** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **add 'christmas' to calendar** — simple: got 0 events, 0 tasks (wanted ≥0/≥0)
- **pencil me in for sarahs birthday thing on the 12th, PDA. Also, Add eggs to my list** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **Please remove the list.** — simple: got 1 events, 0 tasks (wanted ≥0/≥0)
- **Add milk to my grocery list, and then update work out list with new items** — task+task: got 0 events, 1 tasks (wanted ≥0/≥2)
- **new scenario, time or calendar to new list and also please create a list of Due payment th** — task+task: got 1 events, 1 tasks (wanted ≥0/≥2)
- **please set event on Tuesday — and alexa remind me to go to my doctors at 4pm on tuesday** — event+event: got 0 events, 1 tasks (wanted ≥2/≥0)
- **remove 'table' from furniture** — simple: got 1 events, 0 tasks (wanted ≥0/≥0)
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

## Comparison

- 600 shared prompts (2399 only in A, 0 only in B)
- count-correct rate: 70% → 74%
- **34 got worse**, **52 got better**, 391 still pass, 123 still fail

### Got worse

- Please remove the list.
- add 'christmas' to calendar
- remove milk from my grocery list
- Do I need to be reminded of any meetings on Monday?
- add 'valentine's day' with her tomorrow
- remove 'table' from furniture
- Can you add an event with John and Mary?
- Hey Olly, make a list of names starting with vowels and ending with vowels, and then Start a new gro
- Remind me about my next meeting with joe one hour before and schedule a meeting with Brian Billings 
- Save this afternoon for my date, and then I would like to start a new list
- new scenario, time or calendar to new list and also please create a list of Due payment those who no
- AAJ MARCH KI 5TH DAY HAI, HAI KI NAHI?
- Please earse the next birthday event
- Get me the details of upcoming Oscar 2017.
- Remind me 30 minutes before my meeting at 3pm tomorrow. Also, Please set a reminder for church servi
- Name off all the lists I own.
- Can you remind me to order the Turkey three weeks before Thanksgiving?
- Favorite places to eat
- Will you put in my calendar that John C. and his wife are meeting with us at four p.m. tomorrow?
- Is 23 december sunday

### Got better

- add a meeting with my mother for next sunday and reopen groceries and add milk
- set a list for....
- What are the list of things I need to buy today?
- alexa set a meeting event reminder with mona on tuesday, and then Set a Thanks Giving event for Frid
- Remind me about my business meeting at 3:45pm — and get me with new list.
- Set a reminder for tomorrow evening
- Who is coming to the meeting tomorrow at 10 AM?
- Set a reminder to call my mom at 3pm — and olly, can you please add my dinner reservations to my cal
- the location is _____
- Set a reminder for the meeting every Monday at 2pm. Also, Make a new list of dog breeds.
- Set a reminder for a meeting at 2pm tomorrow between myself and John.
- please add this event — and schedule a meeting on Tuesday
- Every Wednesday night at 5pm remind me to meet Phil and also make a new list for me, please.
- Remind me at the 15th of every month and pUT MILK ON MY SHOPPING LIST
- please set a reminder for the office party next saturday?
- PDA, I want to make a list and this should be automatically saved as a text file with the title, lis
- Make a note of an event  'exhibition 2017 mass' on Mar 25 and also add to the list
- add 'birthday' wth mom for next month, and then Create a list of books to be ordered
- Set this before event and also add apples to shopping list
- COULD YOU PLEASE TELL WHEN WE HAVE TO PAY FOR CAR INSURANCE?