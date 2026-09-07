# Dataset run score — `/var/folders/0f/nk3dnvrd54jbjz_qn40_ynwh0000gn/T/engine_compare_4j6kzhwi/engine_run.db`

- product-adjusted count-correct **80%** (16 overridden rows; raw below is the comparable number)
- **250 prompts** scored · count-correct **78%** · garbage-title rate **0%**
- total_ms p50 8524 · p95 49364
- parse paths: {'deep': 163, 'fast': 87}

## By complexity

| Tier | n | count-correct | garbage titles | total_ms p50 |
|---|---:|---:|---:|---:|
| simple | 88 | 92% | 0% | 5196 |
| medium | 78 | 88% | 0% | 6690 |
| complex | 84 | 52% | 1% | 17382 |

## By compound kind

| Kind | n | count-correct | garbage titles | dates collapsed |
|---|---:|---:|---:|---:|
| event+event | 27 | 67% | 4% | 4% |
| task+task | 20 | 45% | 0% | 0% |
| event+task | 37 | 46% | 0% | 0% |

## event+task: which half goes missing when it fails

- both present: 17 · event missing: 13 · task missing: 7 · both missing: 0

## Correctness by parse path

| Path | count-correct |
|---|---:|
| deep | 71% |
| fast | 90% |

## Count-mismatch failures (56)

- **can you schedule a meeting with Mr. Chen on next Monday 6:00pm, and then Set reminder in c** — event+event: got 1 events, 0 tasks (wanted ≥2/≥0)
- **Add event, book club, Debbie's house, Wednesday night and set a list for....** — event+task: got 1 events, 0 tasks (wanted ≥1/≥1)
- **get rid of this list** — simple: got 0 events, 2 tasks (wanted ≥0/≥0)
- **Set a event for the evening, and then get xxx on the list** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **Remind me to read book next week — and can you add Gloria to my list of clients?** — event+task: got 0 events, 2 tasks (wanted ≥1/≥1)
- **Open up a new list.** — simple: got 0 events, 0 tasks (wanted ≥0/≥0)
- **please remind me 1 hour before the meeting I hace tomorrow morning** — medium: got 0 events, 0 tasks (wanted ≥0/≥0)
- **add a note to attend. Also, save the new list** — event+task: got 1 events, 0 tasks (wanted ≥1/≥1)
- **pencil me in for sarahs birthday thing on the 12th, PDA. Also, Add eggs to my list** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **Add milk to my grocery list, and then update work out list with new items** — task+task: got 0 events, 1 tasks (wanted ≥0/≥2)
- **new scenario, time or calendar to new list and also please create a list of Due payment th** — task+task: got 1 events, 0 tasks (wanted ≥0/≥2)
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
- **13 got worse**, **39 got better**, 155 still pass, 43 still fail

### Got worse

- please remind me 1 hour before the meeting I hace tomorrow morning
- AAJ MARCH KI 5TH DAY HAI, HAI KI NAHI?
- On the day project one is due, does my daughter have a recital?
- set reminder for tomorrows meeting with {client name} and also add this one also.
- Can you create a new list in my podcast?
- Church with Mom and Dad on Sunday.
- new scenario, time or calendar to new list and also please create a list of Due payment those who no
- remove 'table' from furniture
- Favorite places to eat
- Do I need to be reminded of any meetings on Monday?
- Mark reminder with these people, and then Pleas set a reminder for a meeting I have on Tuesday next 
- Is 23 december sunday
- Add a party in NY city for this saturday — and on Monday, the 20th, I need to have a conversation wi

### Got better

- Create a new list for my birthday plans. Also, Start creating a new list
- Add dentist appointment for Friday at 5 and please add meeting at work to calander
- remind me at 5:00pm that I have a meeting, and then Please create a new list
- Add event with these people and also add bread to my grocery list
- Notify me when my rent due?
- Add dates without me having to tell to, like tv schedules. Also, Please remind me about the 11am bus
- Make a note of an event  'exhibition 2017 mass' on Mar 25 and also add to the list
- Remember to pick me up by 12 noon from the Airport, I have a 3 pm meeting — and pDA please make a li
- Set reminder for three o'clock
- Please set recurring calendar event and set event in calandar.  repeat event every day
- COULD YOU PLEASE TELL WHEN WE HAVE TO PAY FOR CAR INSURANCE?
- Add Event on Ausgut 21 at 9am and please add an event to my calendar.
- set reminder at 3 pm
- Remind me to send the presentation today at 1:00pm. Also, Go to Stripes at 5pm on 3 April.
- Add my co worker, Ann to submit project for work on Tuesday. Also, MAKE NEW SHCEDULE FOR TOMORROW ME
- Every Wednesday night at 5pm remind me to meet Phil and also make a new list for me, please.
- Olly, please set dinner plans at 7pm for every Friday in April and pDA please set this event on repe
- please add this event — and schedule a meeting on Tuesday
- What are the list of things I need to buy today?
- Add to calendar a home visit everyday this week and also make new list of recent workouts