# The segment dataset SPEC — the labelling bible

Anything that writes or scores a row obeys this file. If a command cannot be
labelled confidently from these rules, the rules are wrong: raise it rather
than guessing, and mark the row `"disputed": true`.

## The row

```json
{"id": "hw-0001",
 "text": "tomorrow gym at 7 and meeting at 11",
 "gold": [{"action": "gym",     "time": "tomorrow at 7",  "tag": "event"},
          {"action": "meeting", "time": "tomorrow at 11", "tag": "event"}],
 "family": "shared-date-leading-edge",
 "traps": ["edge-distribution"],
 "source": "handwritten",
 "split": "train",
 "disputed": false}
```

`text` is what segment receives — the transcript AFTER step-1 repair.
Lowercase, unpunctuated is normal; that is the register.

## The contract

Each item is exactly three strings.

- **action** — the item's words with the time reference removed. Keep
  EVERYTHING else: verb, object, people, places, quantities, and any
  repetition that is not temporal.
- **time** — the time reference for this item, **copied from the command AS
  SPOKEN**.
- **tag** — `event` | `task` | `review`.

### THE INVARIANT (checked mechanically; a row violating it is a bug)

For every item: `tokens(action) ∪ tokens(time)` contains every content token
of that item, and contains **nothing** that is not in `text`. Joiners
("and", "then", ",") may be dropped. A token MAY appear in more than one item
— that is what a shared modifier is.

### CAPTURE, DO NOT RESOLVE

`time` holds the words. Never a date, never a range, never a duration.

- "next friday" → `"next friday"` — NOT `"2026-09-18"`, NOT `"00:00-23:59"`
- "at 7" → `"at 7"` — NOT `"19:00"`
- Resolution is a later stage's job. Inventing it here is a labelling error.

## Time scoping — the rule

A time reference is either INSIDE one item, or at an EDGE of the whole command
(before the first item or after the last), belonging to no item on its own.

> **INTERIOR → binds to its own item.
> EDGE → applies to every item that has none of its own.**

| text | gold times | why |
|---|---|---|
| `tomorrow gym at 7 and meeting at 11` | `tomorrow at 7` · `tomorrow at 11` | leading edge covers both |
| `tomorrow meeting at 7, today gym session` | `tomorrow at 7` · `today` | each has its own |
| `gym session at 7, tomorrow meeting at 10` | `today at 7` · `tomorrow at 10` | interior — does NOT reach back |
| `submit the grades and prepare the slides by friday` | `by friday` · `by friday` | trailing edge covers both |
| `buy milk and book the dentist tomorrow` | `tomorrow` · `tomorrow` | trailing edge, crosses kinds |

**Default:** an item with no time reference at all gets `"today"`.

## Recurrence

| kind | example | where |
|---|---|---|
| temporal repetition | `every friday buy groceries` | **time** = `every friday` |
| quantity | `buy 5 apples` | **action** = `buy 5 apples` (untouched) |

## Tag

- **event** — goes on the calendar at a time
- **task** — goes on the to-do list
- **review** — asks what is scheduled; creates nothing

## THE TRAP INVENTORY

Every shape below has caused a real bug in this project. The set must cover
all of them, and each row lists which it exercises in `traps`.

### MUST SPLIT
| trap | example | gold items |
|---|---|---|
| `and-two-asks` | `book the gym and remind me to buy milk` | 2 |
| `then-sequencer` | `call mom then pick up the dry cleaning` | 2 |
| `comma-list` | `add gym tomorrow, buy milk, and call the dentist` | 3 |
| `three-ask` | `remind me to organize the garage, call the plumber, and book blood test friday` | 3 |
| `mixed-kind` | `add dentist tomorrow at 3 and put milk on the shopping list` | 2 (event+task) |
| `as-well-as` | `book school play at 6:45 as well as sales call at 8:30` | 2 |
| `remind-then-remind` | `remind me to call the plumber and then remind me to book a flight` | 2 |
| `verb-tagged-noun` | `remind me to wash the car and then book tennis lesson at 5` | 2 |
| `list-of-things` | `pick up folders and light bulbs from the store` | 2 (Q14: one per THING) |

### MUST NOT SPLIT
| trap | example | why |
|---|---|---|
| `name-coordination` | `meeting with Sam and Alex at 8` | two PEOPLE, one ask |
| `serial-verb` | `wash and fold the laundry` | two verbs, one object |
| `shared-object` | `clean and organize the garage` | same |
| `two-times-one-activity` | `walk the dog at 9 and 2:30` | decompose's job, not segment's |
| `lead-time` | `book the gym at 1pm and give me a nudge an hour before` | the tail is a MODIFIER |
| `anaphoric-tail` | `i have the podiatry appointment at 2, please put that in the diary` | the tail points back |
| `completion-marker` | `submit the report, wrapped up` | not an ask |
| `tag-question` | `mark take out the trash as done, does that seem right` | not an ask |
| `wrapper-phrase` | `add buy milk and buy bread to my list` | one verb + one destination over both |
| `enumeration-header` | `two tasks due tomorrow: buy groceries and return the book` | the header is not an ask |
| `idiom` | `buy fish and chips` | one thing |

### EDIT REQUIRED (the scoping cases)
`shared-date-leading-edge` · `shared-deadline-trailing-edge` ·
`interior-no-backscope` · `cross-kind-edge` · `recurrence-temporal` ·
`quantity-not-time` · `no-time-defaults-today`

## Splitting the corpus — THREE rules

1. **By FAMILY**, never by row.
2. **Item-string disjointness**: no gold `action` string in the test half may
   appear in the train half. Checked mechanically and REPORTED as a number.
3. **Prompt examples are training data.** Any example placed in an LLMSeg
   prompt must come from the train half. (Learned the hard way: 9 of 14
   commands in the first prompt-tuning set appeared verbatim in the prompt's
   own examples, inflating 11/14 to a true 3/5 on unseen shapes.)

## Distribution

Deliberately oversample **3+ ask rows**. A corpus with a characteristic
ask-count teaches the COUNT rather than the criterion. **Report the gold-count
distribution beside every score.**
