# Dataset run score — `/var/folders/0f/nk3dnvrd54jbjz_qn40_ynwh0000gn/T/engine_compare_ddy0aiyv/engine_run.db`

- **600 prompts** scored · count-correct **74%** · garbage-title rate **0%**
- total_ms p50 5833 · p95 40470
- parse paths: {'deep': 329, 'fast': 271}

## By complexity

| Tier | n | count-correct | garbage titles | total_ms p50 |
|---|---:|---:|---:|---:|
| simple | 208 | 91% | 0% | 4887 |
| medium | 210 | 89% | 0% | 4647 |
| complex | 182 | 38% | 1% | 11228 |

## By compound kind

| Kind | n | count-correct | garbage titles | dates collapsed |
|---|---:|---:|---:|---:|
| event+event | 59 | 39% | 2% | 2% |
| task+task | 47 | 49% | 0% | 0% |
| event+task | 76 | 30% | 1% | 1% |

## event+task: which half goes missing when it fails

- both present: 23 · event missing: 36 · task missing: 13 · both missing: 4

## Correctness by parse path

| Path | count-correct |
|---|---:|
| deep | 74% |
| fast | 75% |

## Count-mismatch failures (155)

- **can you schedule a meeting with Mr. Chen on next Monday 6:00pm, and then Set reminder in c** — event+event: got 1 events, 1 tasks (wanted ≥2/≥0)
- **Add event, book club, Debbie's house, Wednesday night and set a list for....** — event+task: got 1 events, 0 tasks (wanted ≥1/≥1)
- **Olly, set a reminder for my meeting today and create a birthday wish reminder for tommorro** — event+event: got 0 events, 2 tasks (wanted ≥2/≥0)
- **get rid of this list** — simple: got 0 events, 1 tasks (wanted ≥0/≥0)
- **Set a event for the evening, and then get xxx on the list** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **Remind me to read book next week — and can you add Gloria to my list of clients?** — event+task: got 0 events, 3 tasks (wanted ≥1/≥1)
- **Open up a new list.** — simple: got 0 events, 0 tasks (wanted ≥0/≥0)
- **Will you send a calendar invite out to James and Alice for brunch at 11 am on Tuesday and ** — event+task: got 0 events, 2 tasks (wanted ≥1/≥1)
- **add a note to attend. Also, save the new list** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **pencil me in for sarahs birthday thing on the 12th, PDA. Also, Add eggs to my list** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **Add milk to my grocery list, and then update work out list with new items** — task+task: got 0 events, 1 tasks (wanted ≥0/≥2)
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
- **Remind me the wedding on time to buy a present — and grocery list add eggs** — event+task: got 0 events, 2 tasks (wanted ≥1/≥1)
- **Remind me to meet James at work tomorrow at 9am, and then Remind me of my meeting tomorrow** — event+event: got 1 events, 2 tasks (wanted ≥2/≥0)
- **remind me about thing at time, and then I want you to remind me the next meeting with my g** — event+event: got 1 events, 0 tasks (wanted ≥2/≥0)

## Comparison

- 600 shared prompts (2399 only in A, 0 only in B)
- count-correct rate: 70% → 74%
- **32 got worse**, **52 got better**, 393 still pass, 123 still fail

### Got worse

- Remind me an hour ahead of 4pm that the happy hour for marlows on colonial is from 5-6 and also sche
- Can you make an event for friday night with Emi, Maya, and Mackensie?
- Will you send a calendar invite out to James and Alice for brunch at 11 am on Tuesday and also my ne
- Can you create a new list in my podcast?
- On my sisters birthday send her flowers — and hey Olly, I need you to make a list of cricket players
- Add a party in NY city for this saturday — and on Monday, the 20th, I need to have a conversation wi
- add 'valentine's day' with her tomorrow
- give me a reminder at 8pm for the game
- Will you put in my calendar that John C. and his wife are meeting with us at four p.m. tomorrow?
- REMOVE ICECREAM FROM GROCERY
- Get me the details of upcoming Oscar 2017.
- Hey Olly, make a list of names starting with vowels and ending with vowels, and then Start a new gro
- Remind me about my next meeting with joe one hour before and schedule a meeting with Brian Billings 
- Remove bananas from my shopping list
- remove milk from my grocery list
- Set lunch every day at 12:30, and then I want to start a new list of power tools on sale at True Wren
- AAJ MARCH KI 5TH DAY HAI, HAI KI NAHI?
- Can you remind me to order the Turkey three weeks before Thanksgiving?
- Tell me to go to the grocery store after work.
- Favorite places to eat

### Got better

- PDA, I want to make a list and this should be automatically saved as a text file with the title, lis
- Add dentist appointment for Friday at 5 and please add meeting at work to calander
- What are the list of things I need to buy today?
- PDA, mark sarahs b-day party on the 12th. Also, I need to set up a recurring event in my calendar pl
- Set a reminder for a meeting at 2pm tomorrow between myself and John.
- Remind me at the 15th of every month and pUT MILK ON MY SHOPPING LIST
- Olly, please set dinner plans at 7pm for every Friday in April and pDA please set this event on repe
- Schedule and appointment with Mike for next Thursday morning.
- Set a reminder to call my mom at 3pm — and olly, can you please add my dinner reservations to my cal
- Remind me about my business meeting at 3:45pm — and get me with new list.
- Add Event on Ausgut 21 at 9am and please add an event to my calendar.
- please set a reminder for the office party next saturday?
- Please set a reminder for Tuesdays at nine a.m.
- Repeat this event every Friday on my calendar, and then add wine to list
- set a list for....
- Please add brunch with Erin to my calendar at the Diner. Also, add a new list
- Set a reminder for tomorrow evening
- Set this before event and also add apples to shopping list
- Please set recurring calendar event and set event in calandar.  repeat event every day
- Set a reminder for the meeting every Monday at 2pm. Also, Make a new list of dog breeds.