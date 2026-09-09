# decompose_validate — what it is now, and what Gil wants it to be

Planning doc, 2026-09-08. Nothing here is built. `ARCHITECTURE.md` describes the
stage as it stands; this is the argument for changing it.

---

## 1 · Gil's specification

> **X2 = (Segmentation(X1), X1)** — the item list **and** the original fixed
> transcript, a string.
>
> **decompose** completes the other features an item should have: if a
> recurrence, or a number of units, needs resolving, that happens here.
>
> **validate** takes the item list after decompose, compares it to the original
> string, and sees what needs fixing.

Two things in that are sharper than what exists, and both matter:

- **the transcript is a declared INPUT**, not something a rule reaches for
- **validate compares ITEMS to the STRING** — so it runs on items, before any
  object exists

---

## 2 · What exists

```
decompose.py   194 lines   split times · split task lists · quantity · lead time
validate.py    854 lines   TWO entry points, 17 named rules
```

`validate` has **two unrelated jobs under one name**:

| entry | when | what it does | size |
|---|---|---|---|
| `run()` | before FastRule | whitespace/quote tidy, `_repair_text` | ~25 lines |
| `run_objects()` | **after** FastRule | 17 named rules over `item.intent` | ~800 lines |

---

## 3 · Why it is convoluted — five specific things

**1 · It runs twice, at two points in the chain, doing unrelated work.** Text
hygiene and field repair share a module and a name but nothing else. The chain
diagram has one box; the code has two passes straddling FastRule.

**2 · The field rules operate on `intent`, not on items.** So it is not
"validate the items" — it is "patch the objects FastRule produced". That is
*why* it must run after FastRule, and why it cannot sit where Gil drew it.

**3 · It re-derives what upstream already knew.** 93 references to the
transcript. `relative_dates()` recomputes every date from the raw string, then
`_rule_relative_date_pin(..., ev_idx, n_events, orig_event_dates)` guesses which
event each belongs to **by index**.

> This is not a hypothetical. It produced the `a987aba` bug (a repeated relative
> date overwriting a third event's real date) and it produces the one today:
> `relative_dates` returns **2 dates for 3 events** on
> `"add gym on tuesday … and add yoga on tuesday … and add my conference on the
> 20th of November"`, because the bare-ordinal branch correctly refuses to claim
> a month-named ordinal. The conference lands in September.

**Segmentation already answered this question.** `Item.time` holds
`"on tuesday at 6am"` for item 1 and `"on the 20th at 9am"` for item 3, assigned
by the edge-distribution rules we measured. The index-pinning exists only
because the rules were written before items carried their own time.

**4 · Index counters threaded through a flat rule sequence.** `ev_idx`,
`td_idx`, `n_events`, `n_todos`, `orig_event_dates` — all bookkeeping that
exists *only* to answer "which item is this rule talking about", which the item
already knows.

**5 · Four of the "rules" are not repairs at all.** They are decisions, and they
change control flow:

| | what it really does |
|---|---|
| `_rule_junk_event_drop` | **deletes** an item |
| `_rule_question_creates_nothing` | changes routing |
| `_rule_interrogative_create_asks_first` | returns a proposal, gating the whole run |
| `_observance_verdict` | a policy gate (Shabbat / yom tov / fasts) |

A module that repairs, drops, re-routes and gates has no single contract, which
is what makes it hard to reason about and impossible to score.

---

## 4 · The change Gil's spec actually requires

**You cannot validate an item against the string unless the item carries the
fields to be validated.** Today `Item` is `(kind, text, time, slots)`; the date,
start/end times and recurrence live on the *intent*, which does not exist yet.

So the spec implies:

> **decompose ENRICHES the item until it is complete**, and validate then checks
> that complete item against the transcript.

The channel already exists — `Item.slots` is documented as "structured hints:
quantity, recurrence, attendees, times" and decompose already writes
`slots["quantity"]` and `slots["reminder_minutes"]`, which `fastrule/objects.py`
reads back. **The mechanism is there and under-used.** The work is extending it
to the fields the 17 rules currently patch after the fact.

That change dissolves problems 1–4 at once:

- one entry point, one pass, in the position Gil drew
- rules read `item.time` / `item.slots`, not `intent`
- no re-derivation, no index-pinning, no counters
- FastRule receives complete items and only builds objects from them

---

## 4b · X3 — the output structure

X3 is **the item list, complete — and X1 rides along** (Gil, 2026-09-08).
LLMJudge needs the original words to compare the produced objects against, so
the transcript is carried the whole way rather than re-fetched:

```
X2 = ( [Item, …], X1 )        items + the fixed transcript
X3 = ( [Item, …], X1 )        items COMPLETE, transcript still carried
X4 = ( [object, …], X1 )      objects + the words to judge them against
```

X1 is **read-only from segmentation onward**. Every stage may look at it; none
may rewrite it. The single exception is LLMJudge's loop, whose entire job is to
produce a NEW X1 (`X1'`) and start again — which is why the rewrite belongs
there and nowhere else.

### The fields, derived from what FastRule builds

`CalendarIntent` needs `title · date · start_time · end_time · recurrence ·
recur_until · attendees · location · description · reminder_minutes`.
`CreateTodoIntent` needs `titles · quantities · due_date · list_name · priority
· tags`. So an item at X3 carries the union, per kind:

| field | filled by | example |
|---|---|---|
| `kind` | segmentation | `event` \| `task` \| `review` |
| `text` | segmentation | the action words, time removed |
| `time` | segmentation | **as spoken**, unresolved — `"on the 20th of November at 9am"` |
| `date` | **decompose** | `"2026-11-20"` — RESOLVED here, once, per item |
| `start_time` / `end_time` | **decompose** | `"09:00"` / `"10:00"` |
| `recurrence` | **decompose** | `daily` \| `weekly` \| `monthly`, already rounded |
| `recur_until` | **decompose** | ISO date, until/through applied |
| `quantity` | decompose *(exists)* | `5` |
| `reminder_minutes` | decompose *(exists)* | `30` |
| `attendees` | decompose | `["Sam"]` |
| `fixes` | **validate** | what it changed and why — a trace record, not a gate |

### Three properties X3 must have

**1 · RESOLVED, exactly once.** `time` stays the spoken words; `date` and the
clock fields are the resolution of it. Both are present, so a later stage can
always check the resolution against what was said — which is what makes
validate's job possible at all.

**2 · Every field TRACEABLE to the transcript.** A date, a recurrence or a
quantity that no words support is an invention, and that is validate's
invariant (§5c). This is the same shape of contract segmentation already has,
which means it can be scored the same way.

**3 · COMPLETE, and never silently refused.** `blocked` is dropped (Gil): an
item that validate cannot satisfy is not killed here. Validate fixes what it
can and RECORDS what it could not, and the item goes on with its finding
attached — LLMJudge has X1 and a model and is the stage equipped to decide.
Refusing at this stage means refusing on a deterministic rule's say-so, before
anything has looked at the whole picture.

### What this buys

`run_objects` and its 17 rules exist because items arrive at FastRule
incomplete, so the fields get patched after the object is made. Fill them at X3
and the second pass has nothing to do. **That is the finish line in §6: delete
`run_objects`.**

It also settles today's bug by construction. `date` is resolved per item from
that item's own `time`, so there is no flat list of dates to pin by index, and
"which event does this date belong to" is never asked.

---

## 4c · What validate does that segmentation CANNOT (Gil's question)

> *"I don't want to repeat what segmentation does — what can validate do
> differently?"*

**Segmentation works on WORDS. Validate works on RESOLVED VALUES.** That is the
whole distinction, and it means the two cannot overlap.

Segmentation can guarantee *"the words `next friday` went to item 2"*. It can
NEVER check whether `next friday` resolved to the right date, because it does
not resolve — "capture, do not resolve" is its contract. **Validate is the only
stage that holds both the words and the value**, so it is the only one that can
check them against each other.

### The deterministic checks, all of them impossible upstream

| check | a failure it catches |
|---|---|
| resolved date matches the words | `time="next friday"` → `date` is a Wednesday |
| ordinal agreement | `time="the 20th"` → `date` ends `-15` |
| weekday agreement for a series | `recurrence=weekly`, `time="every tuesday"`, `date` is a Thursday |
| numbers agree | `"5 apples"` → `quantity=3`; `"half an hour before"` → `reminder_minutes=45` |
| cross-field arithmetic | `end_time <= start_time`; `recur_until < date`; a past date |
| completeness | a clock with no day; `recur_until` with no `recurrence` |
| **every time-phrase in X1 was honoured** | `"the 20th of November"` half-resolved — **today's bug** |

The last one is the prize: it is the **value-level analogue of segmentation's
invariant**. Segmentation guarantees no word is LOST; validate guarantees no
word went UNHONOURED. Same shape of contract, different level, so it can be
scored the same way and the two boards cannot be confused.

### Where an LLM helps — and where it does not

**Not for any of the above.** Those are arithmetic and set comparison; a model
would be slower, non-deterministic and worse at them. That is also the measured
lesson from segmentation, where every LLM variant lost (`segmentation/
ARCHITECTURE.md` §6).

A model is only interesting for genuine AMBIGUITY that rules cannot settle —
`"book it for the weekend"` (Saturday or Sunday?), `"early next week"`. But
those are not contradictions, they are underspecification, and they are a
different problem from the checks above.

**Proposal: validate stays fully deterministic and emits a FINDING.** LLMJudge
already holds X1 and already makes a model call; it is the stage equipped to
settle doubt. That keeps ONE model call in the chain instead of two, keeps
validate fast and scoreable, and keeps the division clean:

> **validate finds contradictions. LLMJudge settles doubt.**

## 5 · What needs research before building

**a · Which of the 17 rules are genuinely item-level?** Some are
(`until_exclusive`, `weekly_start_day`, `bare_hour_pm`, `at_time_is_start` —
all readable from `item.time` + the transcript). Others may need the object.
Each has to be classified, not assumed.

**b · Where do the four non-repair rules go?** Candidates: the drop and the
routing decisions belong to segmentation or to a gate of their own; the
observance verdict is a policy check that arguably belongs beside commit, since
it decides whether something may be written at all.

**c · What is validate's actual contract?** "Compare to the original string and
fix" needs a testable statement. The obvious candidate, and it mirrors
segmentation's invariant:

> every field on an item must be **traceable to the transcript** — a date, a
> time, a recurrence or a quantity that no words support is an invention.

That is checkable mechanically, which means it can have a board.

**d · It needs a dataset and metrics of its own**, the way segmentation got
`datasets/` + six boards. Without one, "is this better" is unanswerable. The
rules already encode the failures worth measuring — every `_rule_*` name is a
bug that happened once.

---

## 6 · Proposed order

1. **Classify the 17 rules** — item-level, object-level, or not-a-rule.
2. **Write the contract** for validate (§5c), and the invariant it enforces.
3. **Build the dataset + board** before changing behaviour, so the rewrite is
   measured rather than asserted. Segmentation's cycle is the template.
4. **Extend `Item`** with the fields decompose must fill.
5. **Move the rules**, one at a time, against the board.
6. **Delete `run_objects`** once nothing needs it — that is the finish line.

## 7 · The bug this would fix, as the first test case

```
add gym on tuesday at 6am and add yoga on tuesday at 7pm
and add my conference on the 20th of November at 9am

  now:      conference → Sun Sep 20      (index-pinning misassigns)
  should:   conference → Fri Nov 20
```

It needs a second fix in Segmentation too (§6b there: `the 20th of November`
must be captured as one span), which is why it is a good first case — it
exercises the seam between the two stages.
