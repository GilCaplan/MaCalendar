# Dataset run score — `/var/folders/0f/nk3dnvrd54jbjz_qn40_ynwh0000gn/T/engine_compare_mj2fpktx/engine_run.db`

- **3000 prompts** scored · count-correct **74%** · garbage-title rate **0%**
- total_ms p50 5212 · p95 30396
- parse paths: {'deep': 1635, 'fast': 1365}

## By complexity

| Tier | n | count-correct | garbage titles | total_ms p50 |
|---|---:|---:|---:|---:|
| simple | 1000 | 92% | 0% | 3534 |
| medium | 999 | 91% | 0% | 5035 |
| complex | 1001 | 39% | 1% | 10315 |

## By compound kind

| Kind | n | count-correct | garbage titles | dates collapsed |
|---|---:|---:|---:|---:|
| event+event | 335 | 36% | 1% | 2% |
| task+task | 333 | 46% | 1% | 0% |
| event+task | 333 | 35% | 1% | 0% |

## event+task: which half goes missing when it fails

- both present: 115 · event missing: 158 · task missing: 37 · both missing: 23

## Correctness by parse path

| Path | count-correct |
|---|---:|
| deep | 71% |
| fast | 76% |

## Count-mismatch failures (791)

- **can you schedule a meeting with Mr. Chen on next Monday 6:00pm, and then Set reminder in c** — event+event: got 1 events, 1 tasks (wanted ≥2/≥0)
- **give me the reminders** — simple: got 1 events, 0 tasks (wanted ≥0/≥0)
- **Add event, book club, Debbie's house, Wednesday night and set a list for....** — event+task: got 1 events, 0 tasks (wanted ≥1/≥1)
- **Olly, set a reminder for my meeting today and create a birthday wish reminder for tommorro** — event+event: got 1 events, 1 tasks (wanted ≥2/≥0)
- **get rid of this list** — simple: got 0 events, 1 tasks (wanted ≥0/≥0)
- **Set a event for the evening, and then get xxx on the list** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **Remind me to read book next week — and can you add Gloria to my list of clients?** — event+task: got 0 events, 3 tasks (wanted ≥1/≥1)
- **Open up a new list.** — simple: got 0 events, 0 tasks (wanted ≥0/≥0)
- **alexa set a meeting event reminder with mona on tuesday, and then Set a Thanks Giving even** — event+event: got 1 events, 0 tasks (wanted ≥2/≥0)
- **Will you send a calendar invite out to James and Alice for brunch at 11 am on Tuesday and ** — event+task: got 0 events, 2 tasks (wanted ≥1/≥1)
- **add a note to attend. Also, save the new list** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **pencil me in for sarahs birthday thing on the 12th, PDA. Also, Add eggs to my list** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
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
- **Can you create a new list in my podcast?** — medium: got 0 events, 0 tasks (wanted ≥0/≥0)
- **Olly, add lunch appointment with Lisa to January 2nd at 12:30pm. Also, Remind me at the 15** — event+event: got 1 events, 0 tasks (wanted ≥2/≥0)
- **Set me a reminder for the get-together with the women's club on Sunday after church — and ** — event+event: got 0 events, 1 tasks (wanted ≥2/≥0)

## Comparison

- 2999 shared prompts (0 only in A, 0 only in B)
- count-correct rate: 70% → 74%
- **135 got worse**, **252 got better**, 1956 still pass, 656 still fail

### Got worse

- Remind me an hour ahead of 4pm that the happy hour for marlows on colonial is from 5-6 and also sche
- on 3rd april we will go to watch jolly llb movie set it
- Remind me of my sister's birthday party tomorrow an hour before it starts. Also, alexa event calenda
- 12th July is Bola's birthday and my calender to be updated with this date — and let me know in two h
- Set a reminder alert for Saturday 9:00 a.m. towards payment of electricity bill and also olly, pleas
- PDA please order me this months groceries and add Paav Bhaji in Menu card
- where the meeting will be
- Please earse the next birthday event
- can you add this event with karl?
- Create a list of monthly groceries to be bought. Also, I want to start a new list of power tools on 
- remind me about Games of Thrones at seven pm each Sunday for the next three months and also make a n
- reopen groceries and add milk, and then show a new list
- March 5th is John's birthday, please place this on the calendar.
- Remind me to take my medicine at 9am. Also, Please make a list of thing I have to shop tomorrow
- Remind me 30 minutes before my meeting at 3pm tomorrow. Also, Please set a reminder for church servi
- Open my grocery list and add bananas to it, and then Make new playlist from recent songs
- Daily, Monthly, or Yearly event if necessary.Choose the interval between events.
- REMOVE ICECREAM FROM GROCERY
- Add a party in NY city for this saturday — and on Monday, the 20th, I need to have a conversation wi
- enter this to a list — and open grocery list and add milk

### Got better

- Create a list for today's tasks and add mop to hardware store list
- Could you please schedule a meeting with this person and also add a meeting with architect to my new
- Add soup to my shopping list and can you please create a list for me
- set a reminder up next month to get my oil changed
- Set a reminder for a meeting at 2pm tomorrow between myself and John.
- Set reminder for three o'clock
- write down these items and also i need to make a grocery list.
- PDA please schedule a meeting for me, and then Set a reminder for my meeting at 5:00pm
- Set meeting witch jack on 10 march and create a new list called Grocery Store, please.
- Set a monthly event. Also, Mike and Jack should be added to festival calender
- set new reminder to every day
- I want 5 hours freed up for Jenn's birthday this Saturday
- notification of meeting on Wednesday — and alert me when my anniversary is
- Can you set the event for monday at 6 at mcdonalds, and then Please add supervision to my calendar
- add appointment to list, and then Creat a new to-do list
- Schedule an event in my calendar for the pool party at Jack's place this Saturday, and then Add the 
- Can you add Name/Location to calendar and add a movie name to the wish list
- remind me in 50minutes and also please add calendar event
- Repeat this event every Friday on my calendar — and add car service to my list of things to do today
- Please put my birthday party on the calendar. Also, write this event to my calender