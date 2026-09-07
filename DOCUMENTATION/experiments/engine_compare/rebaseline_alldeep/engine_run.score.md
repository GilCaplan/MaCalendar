# Dataset run score — `/var/folders/0f/nk3dnvrd54jbjz_qn40_ynwh0000gn/T/engine_compare_ux34zvy5/engine_run.db`

- **250 prompts** scored · count-correct **79%** · garbage-title rate **0%**
- total_ms p50 12661 · p95 57795
- parse paths: {'deep': 250}

## By complexity

| Tier | n | count-correct | garbage titles | total_ms p50 |
|---|---:|---:|---:|---:|
| simple | 88 | 86% | 1% | 8222 |
| medium | 78 | 87% | 0% | 7828 |
| complex | 84 | 64% | 0% | 18593 |

## By compound kind

| Kind | n | count-correct | garbage titles | dates collapsed |
|---|---:|---:|---:|---:|
| event+event | 27 | 74% | 0% | 0% |
| task+task | 20 | 40% | 0% | 0% |
| event+task | 37 | 70% | 0% | 0% |

## event+task: which half goes missing when it fails

- both present: 26 · event missing: 4 · task missing: 5 · both missing: 2

## Correctness by parse path

| Path | count-correct |
|---|---:|
| deep | 79% |

## Count-mismatch failures (52)

- **Add event, book club, Debbie's house, Wednesday night and set a list for....** — event+task: got 1 events, 0 tasks (wanted ≥1/≥1)
- **get rid of this list** — simple: got 0 events, 2 tasks (wanted ≥0/≥0)
- **Olly, please set dinner plans at 7pm for every Friday in April and pDA please set this eve** — event+event: got 1 events, 0 tasks (wanted ≥2/≥0)
- **Remind me to read book next week — and can you add Gloria to my list of clients?** — event+task: got 0 events, 2 tasks (wanted ≥1/≥1)
- **Add 'event' to my calendar** — simple: got 0 events, 0 tasks (wanted ≥0/≥0)
- **Open up a new list.** — simple: got 0 events, 0 tasks (wanted ≥0/≥0)
- **add 'christmas' to calendar** — simple: got 0 events, 0 tasks (wanted ≥0/≥0)
- **pencil me in for sarahs birthday thing on the 12th, PDA. Also, Add eggs to my list** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **To-do list for today, please.** — simple: got 0 events, 1 tasks (wanted ≥0/≥0)
- **Add milk to my grocery list, and then update work out list with new items** — task+task: got 0 events, 1 tasks (wanted ≥0/≥2)
- **new scenario, time or calendar to new list and also please create a list of Due payment th** — task+task: got 1 events, 1 tasks (wanted ≥0/≥2)
- **remove 'table' from furniture** — simple: got 0 events, 1 tasks (wanted ≥0/≥0)
- **notify me about any festival occurring next month. Also, open grocery list and add milk** — event+task: got 0 events, 1 tasks (wanted ≥1/≥1)
- **Can you sync my calendar with mark?** — medium: got 0 events, 0 tasks (wanted ≥0/≥0)
- **Please remind to get donuts for the meeting, and then new scenario, time or calendar to ne** — event+task: got 0 events, 2 tasks (wanted ≥1/≥1)
- **reopen groceries and add milk** — simple: got 0 events, 0 tasks (wanted ≥0/≥0)
- **Mark reminder with these people, and then Pleas set a reminder for a meeting I have on Tue** — event+event: got 1 events, 1 tasks (wanted ≥2/≥0)
- **Create a new list for my birthday plans. Also, Start creating a new list** — task+task: got 0 events, 0 tasks (wanted ≥0/≥2)
- **Create a new list called Grocery Store, please.** — medium: got 0 events, 0 tasks (wanted ≥0/≥0)
- **create a new list of . Also, get xxx on the list** — task+task: got 0 events, 1 tasks (wanted ≥0/≥2)
- **Add a party in NY city for this saturday — and on Monday, the 20th, I need to have a conve** — event+event: got 1 events, 0 tasks (wanted ≥2/≥0)
- **Can you create a new list in my podcast?** — medium: got 0 events, 0 tasks (wanted ≥0/≥0)
- **Set me a reminder for the get-together with the women's club on Sunday after church — and ** — event+event: got 1 events, 0 tasks (wanted ≥2/≥0)
- **remind me about thing at time, and then I want you to remind me the next meeting with my g** — event+event: got 1 events, 0 tasks (wanted ≥2/≥0)
- **Church with Mom and Dad on Sunday.** — medium: got 0 events, 0 tasks (wanted ≥0/≥0)
- **Do I need to be reminded of any meetings on Monday?** — medium: got 0 events, 0 tasks (wanted ≥0/≥0)
- **Open me a new list — and please add milk to the grocery list** — task+task: got 0 events, 1 tasks (wanted ≥0/≥2)
- **On the day project one is due, does my daughter have a recital?** — medium: got 0 events, 1 tasks (wanted ≥0/≥0)
- **Please add an event to my schedule** — medium: got 0 events, 0 tasks (wanted ≥0/≥0)
- **I need to start a list called and pUT MILK ON MY SHOPPING LIST** — task+task: got 0 events, 1 tasks (wanted ≥0/≥2)

## Comparison

- 250 shared prompts (2749 only in A, 0 only in B)
- count-correct rate: 70% → 79%
- **22 got worse**, **52 got better**, 146 still pass, 30 still fail

### Got worse

- Add red wine to my shopping list and i need to create a new to do list.
- remind me about thing at time
- Do I need to be reminded of any meetings on Monday?
- Create a new list called Grocery Store, please.
- AAJ MARCH KI 5TH DAY HAI, HAI KI NAHI?
- To-do list for today, please.
- Add 'event' to my calendar
- Mark reminder with these people, and then Pleas set a reminder for a meeting I have on Tuesday next 
- 13th june is a day of election result.plz. set it.
- Can you create a new list in my podcast?
- Please add an event to my schedule
- reopen groceries and add milk
- remove 'table' from furniture
- alexa add shoes to my list, and then Could you create a new list for me
- Add a party in NY city for this saturday — and on Monday, the 20th, I need to have a conversation wi
- add 'christmas' to calendar
- Is 23 december sunday
- Favorite places to eat
- Church with Mom and Dad on Sunday.
- I need to start a list called and pUT MILK ON MY SHOPPING LIST

### Got better

- Give an entry to this list — and make a note of this on the list
- Make a reminder at 1PM every Monday until I I remove it, and then Start a new grocery list.
- Olly remind me about the picnic at Regent park — and add paper towels to the grocery list.
- Add my co worker, Ann to submit project for work on Tuesday. Also, MAKE NEW SHCEDULE FOR TOMORROW ME
- I need to set up a meeting with Peter Francis on Monday — and refresh the list with new one.
- give me the reminders
- please set event on Tuesday — and alexa remind me to go to my doctors at 4pm on tuesday
- remind me when a contact calls, and then Please set up a meeting with Becky at 3 pm on Tuesday
- can you schedule a meeting with Mr. Chen on next Monday 6:00pm, and then Set reminder in calendar.
- please add this event — and schedule a meeting on Tuesday
- Alexa add bananas to my shopping list. Also, alexa put shoes on my list
- Remind me at the 15th of every month and pUT MILK ON MY SHOPPING LIST
- Make a note of an event  'exhibition 2017 mass' on Mar 25 and also add to the list
- Add event with these people and also add bread to my grocery list
- add a note to attend. Also, save the new list
- Set a reminder for the meeting every Monday at 2pm. Also, Make a new list of dog breeds.
- Please set a reminder for church services on Sundays for 11am.
- Set reminder for three o'clock
- PDA, mark sarahs b-day party on the 12th. Also, I need to set up a recurring event in my calendar pl
- Set reminder for meeting with Mitushree on 04/04/2017 — and remember me to send the presentation tod