# Dataset run score — `/var/folders/0f/nk3dnvrd54jbjz_qn40_ynwh0000gn/T/engine_compare_fkmyg1xx/engine_run.db`

- **250 prompts** scored · count-correct **73%** · garbage-title rate **1%**
- total_ms p50 9542 · p95 74211
- parse paths: {'deep': 135, 'fast': 115}

## By complexity

| Tier | n | count-correct | garbage titles | total_ms p50 |
|---|---:|---:|---:|---:|
| simple | 88 | 89% | 0% | 8070 |
| medium | 78 | 91% | 0% | 5180 |
| complex | 84 | 40% | 2% | 15936 |

## By compound kind

| Kind | n | count-correct | garbage titles | dates collapsed |
|---|---:|---:|---:|---:|
| event+event | 27 | 52% | 4% | 0% |
| task+task | 20 | 35% | 0% | 0% |
| event+task | 37 | 35% | 3% | 0% |

## event+task: which half goes missing when it fails

- both present: 13 · event missing: 20 · task missing: 4 · both missing: 0

## Correctness by parse path

| Path | count-correct |
|---|---:|
| deep | 76% |
| fast | 70% |

## Count-mismatch failures (67)

- **can you schedule a meeting with Mr. Chen on next Monday 6:00pm, and then Set reminder in c** — event+event: got 1 events, 1 tasks (wanted ≥2/≥0)
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
- **Add milk to my grocery list, and then update work out list with new items** — task+task: got 0 events, 1 tasks (wanted ≥0/≥2)
- **Set reminder for three o'clock** — simple: got 0 events, 0 tasks (wanted ≥0/≥0)
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
- **Can you create a new list in my podcast?** — medium: got 0 events, 0 tasks (wanted ≥0/≥0)
- **Olly, add lunch appointment with Lisa to January 2nd at 12:30pm. Also, Remind me at the 15** — event+event: got 1 events, 0 tasks (wanted ≥2/≥0)
- **Set me a reminder for the get-together with the women's club on Sunday after church — and ** — event+event: got 0 events, 1 tasks (wanted ≥2/≥0)

## Comparison

- 250 shared prompts (2749 only in A, 0 only in B)
- count-correct rate: 70% → 73%
- **14 got worse**, **29 got better**, 154 still pass, 53 still fail

### Got worse

- Favorite places to eat
- Is 23 december sunday
- Mark reminder with these people, and then Pleas set a reminder for a meeting I have on Tuesday next 
- Add a party in NY city for this saturday — and on Monday, the 20th, I need to have a conversation wi
- Can you create a new list in my podcast?
- AAJ MARCH KI 5TH DAY HAI, HAI KI NAHI?
- new scenario, time or calendar to new list and also please create a list of Due payment those who no
- remove 'table' from furniture
- set reminder for tomorrows meeting with {client name} and also add this one also.
- Will you send a calendar invite out to James and Alice for brunch at 11 am on Tuesday and also my ne
- Please earse the next birthday event
- add 'christmas' to calendar
- On the day project one is due, does my daughter have a recital?
- Do I need to be reminded of any meetings on Monday?

### Got better

- Please repeat this event. Also, Set up recurring date on my calendar
- Repeat this event every Friday on my calendar, and then add wine to list
- Notify me when my rent due?
- Add dates without me having to tell to, like tv schedules. Also, Please remind me about the 11am bus
- Make a note of an event  'exhibition 2017 mass' on Mar 25 and also add to the list
- Remind me of the following event:
- Every Wednesday night at 5pm remind me to meet Phil and also make a new list for me, please.
- Set a reminder for a meeting at 2pm tomorrow between myself and John.
- Add dentist appointment for Friday at 5 and please add meeting at work to calander
- Add Event on Ausgut 21 at 9am and please add an event to my calendar.
- COULD YOU PLEASE TELL WHEN WE HAVE TO PAY FOR CAR INSURANCE?
- On the fifth of November, I need to go to Washington, D.C, and then I'd like to set a date for this 
- Set a reminder for the meeting every Monday at 2pm. Also, Make a new list of dog breeds.
- Add my co worker, Ann to submit project for work on Tuesday. Also, MAKE NEW SHCEDULE FOR TOMORROW ME
- Please set recurring calendar event and set event in calandar.  repeat event every day
- Set this before event and also add apples to shopping list
- Olly, please set dinner plans at 7pm for every Friday in April and pDA please set this event on repe
- PDA, mark sarahs b-day party on the 12th. Also, I need to set up a recurring event in my calendar pl
- Schedule my 'event' with 'person' at 'time' and 'place' and i want to know could an extra item be ad
- Please set a reminder for church services on Sundays for 11am.