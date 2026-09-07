# Dataset run score — `/var/folders/0f/nk3dnvrd54jbjz_qn40_ynwh0000gn/T/engine_compare_5ytb1g88/engine_run.db`

- product-adjusted count-correct **81%** (16 overridden rows; raw below is the comparable number)
- **250 prompts** scored · count-correct **79%** · garbage-title rate **0%**
- total_ms p50 8056 · p95 48517
- parse paths: {'deep': 164, 'fast': 86}

## By complexity

| Tier | n | count-correct | garbage titles | total_ms p50 |
|---|---:|---:|---:|---:|
| simple | 88 | 91% | 0% | 5428 |
| medium | 78 | 90% | 0% | 6563 |
| complex | 84 | 56% | 1% | 16909 |

## By compound kind

| Kind | n | count-correct | garbage titles | dates collapsed |
|---|---:|---:|---:|---:|
| event+event | 27 | 67% | 4% | 4% |
| task+task | 20 | 50% | 0% | 0% |
| event+task | 37 | 51% | 0% | 0% |

## event+task: which half goes missing when it fails

- both present: 19 · event missing: 10 · task missing: 7 · both missing: 1

## Correctness by parse path

| Path | count-correct |
|---|---:|
| deep | 73% |
| fast | 91% |

## Count-mismatch failures (53)

- **can you schedule a meeting with Mr. Chen on next Monday 6:00pm, and then Set reminder in c** — event+event: got 1 events, 0 tasks (wanted ≥2/≥0)
- **Add event, book club, Debbie's house, Wednesday night and set a list for....** — event+task: got 1 events, 0 tasks (wanted ≥1/≥1)
- **get rid of this list** — simple: got 0 events, 2 tasks (wanted ≥0/≥0)
- **Olly, please set dinner plans at 7pm for every Friday in April and pDA please set this eve** — event+event: got 1 events, 0 tasks (wanted ≥2/≥0)
- **Set a event for the evening, and then get xxx on the list** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **Remind me to read book next week — and can you add Gloria to my list of clients?** — event+task: got 0 events, 2 tasks (wanted ≥1/≥1)
- **Open up a new list.** — simple: got 0 events, 0 tasks (wanted ≥0/≥0)
- **please remind me 1 hour before the meeting I hace tomorrow morning** — medium: got 0 events, 0 tasks (wanted ≥0/≥0)
- **add a note to attend. Also, save the new list** — event+task: got 1 events, 0 tasks (wanted ≥1/≥1)
- **pencil me in for sarahs birthday thing on the 12th, PDA. Also, Add eggs to my list** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **Add milk to my grocery list, and then update work out list with new items** — task+task: got 0 events, 1 tasks (wanted ≥0/≥2)
- **remove 'table' from furniture** — simple: got 0 events, 1 tasks (wanted ≥0/≥0)
- **notify me about any festival occurring next month. Also, open grocery list and add milk** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **Can you sync my calendar with mark?** — medium: got 0 events, 0 tasks (wanted ≥0/≥0)
- **Remind me the wedding on time to buy a present and create a new list of my due bills** — event+task: got 0 events, 2 tasks (wanted ≥1/≥1)
- **Mark reminder with these people, and then Pleas set a reminder for a meeting I have on Tue** — event+event: got 1 events, 0 tasks (wanted ≥2/≥0)
- **Add Moong daal in grocery list, and then Give an entry to this list.** — task+task: got 0 events, 1 tasks (wanted ≥0/≥2)
- **set reminder for tomorrows meeting with {client name} and also add this one also.** — event+task: got 2 events, 0 tasks (wanted ≥1/≥1)
- **Before this event set notification and bring up a new shopping list.** — event+task: got 1 events, 0 tasks (wanted ≥1/≥1)
- **Can you create a new list in my podcast?** — medium: got 0 events, 0 tasks (wanted ≥0/≥0)
- **Set me a reminder for the get-together with the women's club on Sunday after church — and ** — event+event: got 1 events, 0 tasks (wanted ≥2/≥0)
- **Remind me the wedding on time to buy a present — and grocery list add eggs** — event+task: got 0 events, 2 tasks (wanted ≥1/≥1)
- **Remind me to meet James at work tomorrow at 9am, and then Remind me of my meeting tomorrow** — event+event: got 1 events, 2 tasks (wanted ≥2/≥0)
- **remind me about thing at time, and then I want you to remind me the next meeting with my g** — event+event: got 1 events, 1 tasks (wanted ≥2/≥0)
- **Church with Mom and Dad on Sunday.** — medium: got 0 events, 0 tasks (wanted ≥0/≥0)
- **Do I need to be reminded of any meetings on Monday?** — medium: got 0 events, 0 tasks (wanted ≥0/≥0)
- **Open me a new list — and please add milk to the grocery list** — task+task: got 0 events, 1 tasks (wanted ≥0/≥2)
- **On the day project one is due, does my daughter have a recital?** — medium: got 0 events, 1 tasks (wanted ≥0/≥0)
- **Today is 5th Mar?** — simple: got 1 events, 0 tasks (wanted ≥0/≥0)
- **add an event to my calendar — and can you create new list for me?** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)

## Comparison

- 250 shared prompts (2749 only in A, 0 only in B)
- count-correct rate: 70% → 79%
- **12 got worse**, **41 got better**, 156 still pass, 41 still fail

### Got worse

- On the day project one is due, does my daughter have a recital?
- please remind me 1 hour before the meeting I hace tomorrow morning
- AAJ MARCH KI 5TH DAY HAI, HAI KI NAHI?
- Can you create a new list in my podcast?
- Favorite places to eat
- Today is 5th Mar?
- Church with Mom and Dad on Sunday.
- Do I need to be reminded of any meetings on Monday?
- remove 'table' from furniture
- set reminder for tomorrows meeting with {client name} and also add this one also.
- Is 23 december sunday
- Mark reminder with these people, and then Pleas set a reminder for a meeting I have on Tuesday next 

### Got better

- PDA, mark sarahs b-day party on the 12th. Also, I need to set up a recurring event in my calendar pl
- Add Event on Ausgut 21 at 9am and please add an event to my calendar.
- Add to calendar a home visit everyday this week and also make new list of recent workouts
- Add event with these people and also add bread to my grocery list
- Remind me at the 15th of every month and pUT MILK ON MY SHOPPING LIST
- Set this before event and also add apples to shopping list
- Olly remind me about the picnic at Regent park — and add paper towels to the grocery list.
- Remind me to send the presentation today at 1:00pm. Also, Go to Stripes at 5pm on 3 April.
- Please set recurring calendar event and set event in calandar.  repeat event every day
- Repeat this event every Friday on my calendar, and then add wine to list
- Olly, set a reminder for my meeting today and create a birthday wish reminder for tommorrow at 10 AM
- Remind me on 5th March of every year to arrange wedding anniversary presents and put this on my list
- mark 13 october of this year as my birthday
- Create a new list for my birthday plans. Also, Start creating a new list
- remind me at 5:00pm that I have a meeting, and then Please create a new list
- Add paper towels to the grocery list and also pDA can you create a list for me.
- COULD YOU PLEASE TELL WHEN WE HAVE TO PAY FOR CAR INSURANCE?
- create a new list of . Also, get xxx on the list
- Set reminder for three o'clock
- alexa set a meeting event reminder with mona on tuesday, and then Set a Thanks Giving event for Frid