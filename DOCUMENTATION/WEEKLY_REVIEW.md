# Assistant weekly review — last 7 days (to 2026-09-02)

- **65 commands** (ios 20, mac 45) · 63 executed, 2 failed
- Parse paths: llm 30 (46%), rule 28 (43%), hybrid 7 (11%)
- Latency (executed): first result p50 0.0 s · p95 64.8 s · LLM-path only p50 32.8 s
- **Feedback:** 60/65 reviewed — 👍 4 · ✏️ corrected 7 · 👎 rejected 32 · unreviewed 5
- **Accuracy on reviewed commands: 9%** (approved ÷ approved+corrected+rejected)
  - by path: rule 2/21 (10%), llm 1/16 (6%), hybrid 1/6 (17%)

## Marked wrong / corrected

- [rule] “Walk Mark Stalk today at 230PM” → ['complete_todo']
- [llm] “[TASKS VIEW] i need to buy some groceries, i need rice and chicken, the chicken i need to get far away, the rice i can get at whole foods” → ['create_todo']
- [hybrid] “Add an event for 5 p.m” → ['create_event'] — corrected to ['create_event'] [{'title': 'event', 'date': '2026-08-28', 'start_time': '17:00', 'end_time': '22:00', 'attendees': '', 'location': ''}]
- [llm] “Sunday, set for 830, to go to Doven, pre-Shacharit, and then after that, there will be an event of of the training practice with Mark right after davening” → ['create_event'] — corrected to ['create_event'] [{'title': 'Daven and Leyning W Mark', 'date': '2026-08-30', 'start_time': '08:30', 'end_time': '09:30', 'location': 'pre-Shacharit', 'description': 'training practice with Mark right after davening', 'attendees': '', 'recurrence': '', 'recurrence_end': ''}]
- [llm] “Created event brought Znazh Badjolz in New York City on Thursday, August 27, IMPI, 26, Khronachat, Israel, Pooachat, Israel, Bedakah, Khat, Lifene, Yatsolayman.” → ['create_event'] — corrected to ['create_event'] [{'title': 'Znazh Badjolz in New York City', 'date': '2026-08-27', 'start_time': '00:02', 'end_time': '00:53', 'attendees': ['Badjolz'], 'location': 'New York City', 'description': 'IMPI, 26, Khronachat, Israel, Pooachat, Israel, Bedakah, Khat, Lifene, Yatsolayman'}]
- [llm] “set a date for tomorrow at 11 o'clock, in one second, one moment, one moment, bear with me, i want to be at one moment, is one moment, broads nosh bagels in new york city” → ['create_event'] — corrected to ['create_event'] [{'title': "Broad's Nosh Bagels in New York City", 'date': '2026-08-28', 'start_time': '11:02', 'end_time': '13:26', 'location': 'New York City', 'description': 'one second, one moment, one moment, bear with me, I want to be at one moment'}]
- [rule] “Set a meeting of his hours meeting on Sunday at 1 p.m. this coming Sunday with Noa” → ['create_event'] — corrected to ['create_event'] [{'title': 'Office Hours Meeting - Noa', 'date': '2026-08-30', 'start_time': '13:02', 'end_time': '13:53', 'attendees': 'noa', 'location': 'Zoom'}]
- [hybrid] “Set a meeting on this coming Sunday for 1 p.m. TA, Office Hour, meeting, excuse me.” → ['create_event']
- [llm] “The event you just made on Sunday, fix it, so is at 1pm to 2pm, it is a office meeting for the course I am the TA in, with Noa Bamburger” → ['update_event']
- [hybrid] “Set a meeting for me this coming Sunday at... Let's see, it is...” → ['create_event'] — corrected to ['create_event'] [{'title': 'Office Hour - Haxaga', 'date': '2026-08-30', 'start_time': '13:02', 'end_time': '15:22', 'location': '', 'attendees': 'with Noa Bamburger', 'description': '', 'recurrence': '', 'recurrence_end': ''}]
- [rule] “Edit today's date event from 10, instead of 10 it starts at 11, then it will go until...” → ['update_event']
- [llm] “I had an event on the 17th of September, from 7 p.m. to 10 p.m. going with Doran, who is my guest, to Kupare Shea event, yeah” → ['create_event'] — corrected to ['create_event'] [{'title': 'Kupat Resheit Premier Event', 'date': '2026-09-17', 'start_time': '19:00', 'end_time': '22:00', 'attendees': 'Doron', 'location': 'Kupa resheit', 'description': 'going with Doran'}]
- [llm] “Can you fix the meeting tomorrow, the one meeting with V-Code, so that just says, work meeting with V-Code. The one that is tomorrow morning at 9 a.m” → ['update_event']
- [rule] “Set a meeting for 10 a.m. tomorrow morning” → ['create_event'] — corrected to ['create_event'] [{'title': 'Date ❤️', 'date': '2026-08-27', 'start_time': '11:00', 'end_time': '15:00', 'location': '', 'attendees': ''}]
- [llm] “Right, set an event for today at 3.45 pm, which are already past, WalkJaydo the Dog, set for tomorrow at 8.40 am to WalkJaydo again, and then 9 am set a meeting with Rina for work, and then Saturday set for 10 am to relax” → ['create_event', 'create_event', 'create_event', 'create_event'] — corrected to ['create_event', 'create_event', 'create_event', 'create_event'] [{'title': 'Meeting with Rina for work', 'date': '2026-08-27', 'start_time': '09:02', 'end_time': '09:58', 'location': '', 'attendees': 'Rina', 'description': '', 'recurrence': '', 'recurrence_end': ''}]
- [llm] “a meeting for me tomorrow at two one sorry one pm and four pm and then another one a pizza party at 6.30 pm at edo's” → ['create_event', 'create_event']
- [rule] “set a meeting on thursday for 11 a.m. to” → ['create_event']
- [rule] “set meeting on thursday for three o'clock. thank you. is this why you made it?” → ['create_event']
- [rule] “set a meeting for me tomorrow at 5.30 p.m. with pelic sorry, i mean edo” → ['create_event']
- [hybrid] “set a meeting tomorrow. sorry, not tomorrow. set a meeting on tuesday.” → ['create_event']
- [rule] “please set a meeting for me tomorrow at 4pm with re for defense on homework” → ['create_event']
- [rule] “set a meeting for me tomorrow at 4pm” → ['create_event']
- [rule] “set tomorrow a meeting with nurit at 5pm” → ['create_event']
- [llm] “i had a meeting today at 8.30pm with nurit to work on project” → ['update_event']
- [llm] “set a meeting at 4pm today, but it is only 20 minutes meeting with one moment meeting with reards, okay, then let's do another meeting from 6 from 6 o'clock to 640 meetings with kids for project defense” → ['create_event', 'create_event']
- [llm] “set a meeting for me tomorrow at 11 a.m. and also set meeting for 5.30 p.m. to 6.30 p.m. tomorrow as well” → ['create_event', 'create_event']
- [rule] “create a meeting tomorrow at 2pm on wednesday meeting with adin for the project” → ['create_event']
- [rule] “set a meeting tomorrow at 2 o'clock meeting with adin for project” → ['create_event']
- [llm] “start emitting for me on wednesday at 6.30. excuse me. excuse me.” → ['create_event']
- [rule] “again, create an event tomorrow at 6pm with ofeer” → ['create_event']

## Failed outright

- “Execute a...” — Sorry, I didn't understand that.
- “No.” — Sorry, I didn't understand that.

## Vocabulary (374 words)

Words that corrected a transcript this period (all time counts): Ravid ×8, Naor ×5, Jerusalem ×5, Peleg ×4, Shacharit ×4, Edo's ×3, Park Jerusalem ×3, Nachman ×3, Tal ×3, Technion dorms ×3, Liora ×2, Meshulam ×1, Bagrut ×1, davening ×1, dentist appointment ×1, Ronny ×1, Guri Karpas ×1, Ofir ×1, Haxaga ×1, homework ×1, Rei ×1, Kikar ×1, Mincha Maariv ×1, Noa Bamburger ×1, readme ×1

## What to do with this

- Unreviewed commands: open the phone → Settings → *Review commands* and tap 👍/👎 — the memory only helps once it knows what was right.
- Anything under *Marked wrong*: say it again a different way, or add the word it missed to the vocabulary.
- Re-run the audit corpus against your real history: `python -m scripts.audit_assistant --history`.
