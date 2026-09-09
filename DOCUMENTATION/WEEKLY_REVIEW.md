# Assistant weekly review — last 7 days (to 2026-09-09)

_(66 test commands excluded — this report is real usage only.)_

- **23 commands** (ios 18, mac 5) · 21 executed, 2 failed
- Parse paths: rule 10 (43%), deep 5 (22%), llm 5 (22%), fast 3 (13%)
- Latency (executed): first result p50 1.6 s · p95 34.2 s · LLM-path only p50 17.0 s
- **Feedback:** 21/23 reviewed — 👍 10 · ✏️ corrected 6 · 👎 rejected 5 · unreviewed 2
- **Flagged wrong or corrected: 11/23 commands** (48% of everything run this period)
- **Accuracy on reviewed commands: 48%** (10/21 — approved ÷ approved+corrected+rejected)
  - by path: fast 2/3 (67%), deep 1/3 (33%), rule 7/10 (70%), llm 0/5 (0%)

## Marked wrong / corrected

- [fast] “Create an event now to go out for a run” → ['create_event'] — corrected to ['create_event'] [{'title': 'Run with Ravid', 'date': '2026-09-08', 'start_time': '00:00', 'end_time': '01:00'}]
- [deep] “WalkMoxDog today at 2pm, and also WalkMoxDog tomorrow at 8.30am, and I also have an interview at 9am tomorrow” → ['create_event', 'create_event', 'create_event'] — corrected to ['create_event', 'create_event', 'create_event'] [{'title': 'Walk Marks Dog', 'date': '2026-09-08', 'start_time': '14:00', 'end_time': '15:00', 'description': '', 'attendees': '', 'location': ''}]
- [deep] “Set for 2 p.m. tomorrow, CC event” → ['create_event'] — corrected to ['create_event'] [{'title': 'CC Event', 'date': '2026-09-07', 'start_time': '14:00', 'end_time': '15:00', 'location': '', 'attendees': '', 'description': ''}]
- [llm] “Alright, we have a few events set for Tuesday to walk Moxdog at 9 a.m. next week, as well as walk Moxdog at 2.30 p.m. on Tuesday as well. In addition to that, on the 17th of September, there is a Kupahre sheet event that Doron and I are going to, so put down the calendars in the evening that day. And then in addition to that, we have my bar mitzvah parashel, which I'm leaning on the 19th of September, which is Shabbat. the Jewish Center. So do that as well” → ['create_event', 'create_event', 'create_event', 'create_event'] — corrected to ['create_event', 'create_event', 'create_event', 'create_event'] [{'title': 'Walk marks dog', 'date': '2026-09-08', 'start_time': '09:00', 'end_time': '10:00', 'location': '', 'attendees': '', 'description': ''}]
- [llm] “Have a movie today from 3pm to 6pm” → ['create_event']
- [llm] “I need to buy some groceries, which includes pasta times 5” → ['create_todo']
- [llm] “Fix on the tasks, the groceries to tag them as groceries, like the zucchini, the by Colbro, Canelo Oil, Gatorade, up the Roundham Pepsi” → ['create_todo'] — corrected to ['create_todo'] [{'titles': ['buy zucchini', 'buy Colbro', 'buy Canelo Oil', 'buy Gatorade', 'buy Roundham Pepsi'], 'tags': ['Groceries'], 'title': 'buy diet Pepsi'}]
- [rule] “10,000, you'd buy Gatorade and Dr. Brown” → ['create_todo']
- [rule] “I need to buy cold brew, and I need to also buy, Cornell oil, can” → ['create_todo', 'create_todo'] — corrected to ['create_todo', 'create_todo'] [{'titles': ['buy cold brew'], 'title': 'Canola oil', 'tags': []}]
- [rule] “Groceries, I need to buy zucchini, cold brew” → ['create_todo']
- [llm] “I need a b-” → ['create_event']

## Failed outright

- “Let an event to go out for a run now” — Sorry, I couldn't read this part: “Let an event to go out for a run now”. I'm not sure I caught every part of that — wor
- “Set an event to go out for now” — Sorry, I couldn't read this part: “Set an event to go out for now”. I'm not sure I caught every part of that — worth a g

## Vocabulary (375 words)

Words that corrected a transcript this period (all time counts): Ravid ×8, Naor ×5, Jerusalem ×5, Peleg ×4, Shacharit ×4, Edo's ×3, Park Jerusalem ×3, Nachman ×3, Tal ×3, Technion dorms ×3, Liora ×2, Meshulam ×1, Bagrut ×1, Doron ×1, Cornell ×1, davening ×1, dentist appointment ×1, Ronny ×1, Guri Karpas ×1, Ofir ×1, Haxaga ×1, homework ×1, Rei ×1, Kikar ×1, Mincha Maariv ×1

## What to do with this

- Unreviewed commands: open the phone → Settings → *Review commands* and tap 👍/👎 — the memory only helps once it knows what was right.
- Anything under *Marked wrong*: say it again a different way, or add the word it missed to the vocabulary.
- Re-run the audit corpus against your real history: `python -m scripts.audit_assistant --history`.
