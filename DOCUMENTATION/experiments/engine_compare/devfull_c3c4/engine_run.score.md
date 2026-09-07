# Dataset run score — `/var/folders/0f/nk3dnvrd54jbjz_qn40_ynwh0000gn/T/engine_compare_ytmy1npf/engine_run.db`

- **600 prompts** scored · count-correct **78%** · garbage-title rate **0%**
- total_ms p50 6078 · p95 36931
- parse paths: {'deep': 349, 'error': 2, 'fast': 249}

## By complexity

| Tier | n | count-correct | garbage titles | total_ms p50 |
|---|---:|---:|---:|---:|
| simple | 208 | 91% | 0% | 4194 |
| medium | 210 | 89% | 0% | 4429 |
| complex | 182 | 51% | 2% | 13012 |

## By compound kind

| Kind | n | count-correct | garbage titles | dates collapsed |
|---|---:|---:|---:|---:|
| event+event | 59 | 56% | 2% | 0% |
| task+task | 47 | 57% | 2% | 0% |
| event+task | 76 | 42% | 1% | 0% |

## event+task: which half goes missing when it fails

- both present: 32 · event missing: 25 · task missing: 16 · both missing: 3

## Correctness by parse path

| Path | count-correct |
|---|---:|
| deep | 76% |
| error | 0% |
| fast | 82% |

## Count-mismatch failures (132)

- **can you schedule a meeting with Mr. Chen on next Monday 6:00pm, and then Set reminder in c** — event+event: got 1 events, 1 tasks (wanted ≥2/≥0)
- **Add event, book club, Debbie's house, Wednesday night and set a list for....** — event+task: got 1 events, 0 tasks (wanted ≥1/≥1)
- **get rid of this list** — simple: got 0 events, 1 tasks (wanted ≥0/≥0)
- **Set a event for the evening, and then get xxx on the list** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **Remind me to read book next week — and can you add Gloria to my list of clients?** — event+task: got 0 events, 3 tasks (wanted ≥1/≥1)
- **Open up a new list.** — simple: got 0 events, 0 tasks (wanted ≥0/≥0)
- **add a note to attend. Also, save the new list** — event+task: got 1 events, 0 tasks (wanted ≥1/≥1)
- **pencil me in for sarahs birthday thing on the 12th, PDA. Also, Add eggs to my list** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
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
- **On the day project one is due, does my daughter have a recital?** — medium: got 0 events, 1 tasks (wanted ≥0/≥0)
- **add an event to my calendar — and can you create new list for me?** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **Make a reminder at 1PM every Monday until I I remove it, and then Start a new grocery list** — event+task: got 0 events, 2 tasks (wanted ≥1/≥1)

## Comparison

- 600 shared prompts (2399 only in A, 0 only in B)
- count-correct rate: 70% → 78%
- **31 got worse**, **74 got better**, 394 still pass, 101 still fail

### Got worse

- Remind me about my next meeting with joe one hour before and schedule a meeting with Brian Billings 
- Tell me to go to the grocery store after work.
- Hey Olly, make a list of names starting with vowels and ending with vowels, and then Start a new gro
- Name off all the lists I own.
- Add a party in NY city for this saturday — and on Monday, the 20th, I need to have a conversation wi
- remove 'table' from furniture
- Don't let me forget Rover's vet appointment on the 25th and pDA add Sally's Birthday to Calander for
- On the day project one is due, does my daughter have a recital?
- Will you put in my calendar that John C. and his wife are meeting with us at four p.m. tomorrow?
- AAJ MARCH KI 5TH DAY HAI, HAI KI NAHI?
- Mark reminder with these people, and then Pleas set a reminder for a meeting I have on Tuesday next 
- remove milk from my grocery list
- give me a reminder at 8pm for the game
- REMOVE ICECREAM FROM GROCERY
- Remove bananas from my shopping list
- Save this afternoon for my date, and then I would like to start a new list
- set reminder for tomorrows meeting with {client name} and also add this one also.
- On my sisters birthday send her flowers — and hey Olly, I need you to make a list of cricket players
- Put working out on my calendar for 8 a.m. every day this week. Also, I want to start a new list.
- Do I need to be reminded of any meetings on Monday?

### Got better

- Make a note of an event  'exhibition 2017 mass' on Mar 25 and also add to the list
- Add event with these people and also add bread to my grocery list
- Let me know later.
- please set event on Tuesday — and alexa remind me to go to my doctors at 4pm on tuesday
- Please set recurring calendar event and set event in calandar.  repeat event every day
- Schedule and appointment with Mike for next Thursday morning.
- Create a meeting thursday afternoon for budget review. Also, create a new list of my pending bills
- Set up a reoccurring grocery store trip for every Sunday
- Create a list for the following. Also, I want to make this week's shopping list
- Please set a reminder for church services on Sundays for 11am.
- Repeat this event every Friday on my calendar, and then add wine to list
- Please set a reminder for Tuesdays at nine a.m.
- create a new list of . Also, get xxx on the list
- I need you to add this event to my calendar. Also, Be sure to remind me of this
- Remember to pick me up by 12 noon from the Airport, I have a 3 pm meeting — and pDA please make a li
- Remind me of the following event:
- Please add brunch with Erin to my calendar at the Diner. Also, add a new list
- Save event for 5pm to 6pm on March 18th — and remind me to take my medicine at 9am
- Olly, add lunch appointment with Lisa to January 2nd at 12:30pm. Also, Remind me at the 15th of ever
- Notify me when my rent due?