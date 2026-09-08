"""Step 2 — segment the transcript into independent items.

Contract (see DOCUMENTATION/ENGINE.md):
  reads   state.text
  writes  state.items (fresh list of Item: id, kind, text only),
          trace steps (RULE)

Deterministic delimiters first — they are free and cannot be wrong:

  • bracket batching:   "[gym tomorrow] [lunch with Tal]"   (queued phone commands)
  • ingest coalescing:  ("gym tomorrow")and("lunch with Tal")  (step 0's wrapper)
  • the configured event separator (config.audio.event_separator)

Only when none of those split anything may the LLM be consulted, and the bias
is to UNDER-split: a wrongly merged item gets two more chances (step 3 can
decompose it, step 6 notices the missing item), where a wrong split of
"meeting with Tal and Ravid" creates two garbage items immediately.

Kind here is a first reading ("review" for schedule questions, "task" for
to-do phrasing, "event" for the rest); step 5 settles the actual action.

Also exports one named reader — `is_interrogative_create(text)` — the same
kind of shared vocabulary `validate` exports: a pure function other stages may
call, never a channel to mutate state through.
"""

from __future__ import annotations

import re

from assistant.engine.state import EngineState, Item
from assistant.intent.asks import every_part_is_an_ask

# ("…")and("…") — the step-0 coalescing wrapper. Parentheses+quotes because a
# bare "and" very much can occur inside one command.
_COALESCE_RE = re.compile(r"\(\s*[\"“]([^\"“”]+)[\"”]\s*\)")
_BRACKET_RE = re.compile(r"\[([^\[\]]+)\]")

# A schedule question, not an instruction to create anything.
#
# The "my schedule" arm used to be UNANCHORED, so any command that merely
# mentioned the schedule was read as a question about it — "drop piano lesson
# from my schedule" is a DELETE, and it was scoring as a review (14 rows on
# the FastRule train half, every one of them a `drop … from my schedule`).
# It now needs a looking verb in front of it, which is what made it a question
# in the first place.
#
# The looking verbs also had a gap of their own: "check my calendar for this
# week" and "could you tell me what's on my calendar" are plainly reviews and
# matched nothing (50 rows read as events).
# Deliberately NOT here: "remind me of" and "give me" — the first is a
# reminder and the second opens a lead-time clause ("give me a heads up
# 30 minutes before"). Both read as questions and are not; including them
# turned 25 tasks into reviews.
# "check OFF mail the package" completes a to-do; only a bare "check" is a
# looking verb. Same trap as the schedule arm: a word that reads as a query
# in isolation is part of an action verb here.
_LOOK_VERB = (r"(?:what(?:'s| is| do| have| does)?|show|tell me|"
              r"check(?!\s*(?:off|out)\b)|see|"
              r"look at|pull up|read|bring up|"
              r"do i have|when is|when's|how many|list)")

_REVIEW_RE = re.compile(
    rf"^(?:please\s+|hey\s+|um+\s+|so\s+)?(?:can|could|would|will)?\s*"
    rf"(?:you\s+)?{_LOOK_VERB}\b"
    rf"|\b{_LOOK_VERB}\b[^.?!]{{0,40}}\bmy\s+"
    rf"(?:schedule|day|week|agenda|calendar|diary)\b",
    re.I)

# To-do phrasing. Only used as a first reading; step 5 decides the action.
#
# It used to recognise CREATE-shaped to-do wording and nothing else, so every
# way of COMPLETING, EDITING or UN-LISTING a task fell through to "event" —
# and because `decompose.run()` branches entirely on kind, that cost the
# decomposition as well as the label. Measured on the FastRule 7,200 train
# half: non-create to-do operations scored 8.8% (41 of 467), and task RECALL
# was 0.341 against event recall 0.978. The errors were almost all one
# direction: 730 tasks read as events, 41 events read as tasks.

#: The strongest signal there is, and the one that needed no verb: an explicit
#: to-do DESTINATION anywhere in the sentence. "get rid of cancel the
#: subscription ON MY LIST", "remove X FROM MY LIST", "drop X FROM MY TASKS"
#: name no create verb at all, and the destination is what makes them tasks.
#: "calendar" and "schedule" are deliberately absent — those are events.
_LIST_DEST = (
    r"\b(?:to-?do|task|shopping|grocery|errand)s?\s+list\b"
    # bare "list" belongs here: the commonest spoken form is "on my list" /
    # "from my list" with no qualifier at all, and requiring one missed every
    # such row ("just get rid of cancel the subscription ON MY LIST").
    r"|\b(?:on|to|off|from|in)\s+(?:my|the)\s+"
    r"(?:to-?do|task|shopping|grocery|errand|list)s?(?:\s+list)?\b"
    r"|\bmy\s+(?:to-?do|task|errand|list)s?\b"
)

#: Completing a to-do. These say nothing about a calendar and cannot be
#: confused with booking something: "mark X as done", "i already did X",
#: "check off X", "i finished X", "i'm done with X".
#: `complet(?:e|ed)?` rather than `complete` because the corpus carries the
#: truncation the recogniser actually produces ("mark X as complet").

_TODO_DONE = (
    r"\bmark\b[^.?!]{0,40}\b(?:as\s+)?(?:done|complet(?:e|ed)?|finished)\b"
    r"|\b(?:check|cross|tick)\s+(?:it\s+|that\s+|this\s+)?off\b"
    r"|^(?:complete|finish|finished)\s+\w"
    r"|\bi\s+(?:already\s+)?(?:did|finished|completed)\b"
    r"|\bi'?m\s+done\s+with\b"
    r"|\balready\s+(?:did|done|finished|handled)\b"
)

#: Naming a to-do outright, and the errand openers the original list missed
#: ("i gotta pack for the trip", "create a task to water the plants").
_TODO_NAMED = (
    r"^(?:create|add|make|set)\s+(?:a|an)\s+(?:new\s+)?(?:task|to-?do)\b"
    # "set a reminder TO <verb>" is an errand; "set a reminder 2 hours before
    # FOR standup" is a calendar entry with a lead time. Only the first is a
    # to-do, and the "to" is what tells them apart.
    r"|^(?:create|add|make|set)\s+(?:a|an)\s+remind\w*\s+to\b"
    r"|^i\s+(?:gotta|have to|got to|must|should|need to)\b"
    r"|^(?:don'?t let me forget|do not forget|dont forget)\b"
)

#: CHORE verbs in the imperative — the errands a to-do list is for. Nothing
#: here can book anything: the calendar verbs (book, schedule, meet, plan,
#: invite) are deliberately absent, and so is "call", which is genuinely
#: ambiguous between an errand and an appointment and is left to the model.
_CHORE_VERB = (
    r"^(?:file|wash|fold|print|clean|organi[sz]e|pack|water|vacuum|hoover|"
    r"restock|refill|renew|mail|post|submit|charge|feed|sweep|mow|iron|dust|"
    r"declutter|tidy|empty|defrost|sort out|drop off|take out|back up|"
    r"wrap|donate|recycle|shred|scan|photocopy)\b"
)

_TASK_RE = re.compile(
    r"^(?:add|put)\s+.*\b(?:to|on)\s+(?:my\s+)?(?:to-?do|task|shopping)|"
    r"^(?:remind me to|i need to|remember to|buy|get(?!\s+rid\b)|pick up)\b|"
    rf"{_LIST_DEST}|{_TODO_DONE}|{_TODO_NAMED}|{_CHORE_VERB}",
    re.I)


# A clock time inside a "remind" phrasing flips it to the calendar: the
# product rule (pinned in the corpus) is "remind me to call Ravid" = task,
# "remind me about the dentist tomorrow at 9 am" = event.
_CLOCKISH_RE = re.compile(
    r"\b\d{1,2}(:\d{2})?\s*(am|pm|a\.m\.|p\.m\.)\b|\b\d{1,2}:\d{2}\b|\bat\s+\d{1,2}\b|"
    r"\b(noon|midnight|tonight|morning|evening|afternoon)\b", re.I)

# Any remind-flavoured wording — the verb or the noun ("a birthday wish
# reminder for tomorrow at 10 AM" carries no "remind me to").
_REMINDISH_RE = re.compile(r"\b(?:remind(?:er)?s?|notify)\b", re.I)   # notify: cycle 4

# The "remind me to <verb> …" errand form — stays a task unless clock-timed.
_REMIND_TO_VERB_RE = re.compile(r"\bremind\s+\w+\s+to\b", re.I)

# "I need to <meet/talk/…>" — an encounter being arranged, not an errand.
_NEED_ENCOUNTER_RE = re.compile(
    r"\bi\s+(?:need to|should|want to|would like to|gotta|have to|must)\s+"
    r"(?:meet|talk|speak|see|catch up|sit down|"
    r"have\s+a\s+(?:conversation|chat|word|meeting|call))\b", re.I)

# An occasion someone attends (not an errand someone does) …
_OCCASION_RE = re.compile(
    r"\b(meeting|appointment|party|get-?together|dinner|lunch|brunch|breakfast|"
    r"birthday|anniversary|wedding|funeral|concert|recital|interview|class|"
    r"lesson|shiur|conference|ceremony|festival|event)\b", re.I)   # festival: cycle 4

# … said with a date reference (a weekday, a relative day, an ordinal, a month).
_DATED_RE = re.compile(
    r"\b(today|tomorrow|tonight)\b|"
    r"\b(next|this|on)\s+(week|month|monday|tuesday|wednesday|thursday|friday|"
    r"saturday|sunday|weekend)\b|"
    r"\bthe\s+\d{1,2}(st|nd|rd|th)?\b|"
    r"\b(january|february|march|april|may|june|july|august|september|october|"
    r"november|december)\b", re.I)


# --- interrogative creates (the confirm-create gate) -----------------------
#
# A public reader, in the ENGINE.md sense: shared vocabulary other stages may
# call, never a channel to mutate state through. It lives here because "what
# shape of utterance is this" is step 2's question — step 4 (which sees the
# question AND the create-shaped object) and step 5's fast-track gate both ask
# it, and one regex read two ways is what keeps them agreeing.
#
# Gil's ruling (2026-09-07, DEVQA Q9): "should i add yoga to my calendar
# tomorrow?" must neither auto-create nor be silently dropped. Both halves
# happened: "should i …" sailed past `_rule_question_creates_nothing` (its
# `_QUESTION_START` has no "should") and booked yoga, while "what if i booked
# town hall for the 3rd?" matched it and vanished without a word.

#: The speaker WEIGHING an action of their own — "should I", "what if we",
#: "do you think", "how about I". First person on purpose: "can you add yoga?"
#: is a request and must still execute, "can I add yoga?" is a musing.
_PROPOSAL_RE = re.compile(
    r"\b(?:should|shall|could|can|would|might|ought(?:\s+to)?)\s+(?:i|we)\b"
    r"|\b(?:what|how)\s+(?:if|about)\s+(?:i|we)\b"
    r"|\bdo\s+you\s+(?:think|reckon)\b"
    r"|\b(?:is|would)\s+it\s+(?:be\s+)?(?:worth|better|a\s+good\s+idea)\b"
    r"|\bdo\s+i\s+need\s+to\b",
    re.I)

#: An opener that is a question even when the transcript lost its "?" —
#: speech recognition drops the mark often enough to matter.
_PROPOSAL_OPENER_RE = re.compile(
    r"^(?:so\s+|ok(?:ay)?\s+|hey\s+|hmm\s+)?"
    r"(?:should|shall|what\s+if|how\s+about|what\s+about|do\s+you\s+think)\b", re.I)

#: The verbs that put something on the calendar or the list, in whatever tense
#: the hypothetical takes it — "what if I BOOKED", "should I be ADDING".
_CREATE_VERBISH_RE = re.compile(
    r"\b(?:add(?:ed|ing)?|book(?:ed|ing)?|schedul(?:e|ed|ing)|creat(?:e|ed|ing)|"
    r"mak(?:e|ing)|made|put(?:ting)?|set(?:ting)?|pencil(?:led|ed|ling|ing)?|"
    r"slot(?:ted|ting)?|block(?:ed|ing)?\s+(?:out|off)|plan(?:ned|ning)?)\b", re.I)


def is_interrogative_create(text: str) -> bool:
    """Is this the speaker ASKING whether to create something, rather than
    telling the assistant to?

    All three have to hold, which is what keeps it off ordinary commands:
      • it reads as a question (a "?" or a question opener),
      • the speaker is weighing their OWN action ("should I", "what if we"),
      • and there is a create verb in the same words.

    "add yoga tomorrow" (no question), "can you add yoga?" (not first person)
    and "what's on friday?" (no create verb) all return False.
    """
    t = (text or "").strip()
    if not t:
        return False
    if not (t.endswith("?") or _PROPOSAL_OPENER_RE.match(t)):
        return False
    return bool(_PROPOSAL_RE.search(t) and _CREATE_VERBISH_RE.search(t))


def _enforce_pinned_kinds(kind: str, text: str) -> str:
    """The pinned reminder rules, enforced over the LLM's own labels.

    Cycle 1 (dataset loop): `_kind_of` flips remind + clock-time to the
    calendar, but on the deep path the LLM's kind label won unchecked — so
    "create a birthday wish reminder for tomorrow at 10 AM" landed as a todo
    and generate's event-kind retry (which keys off kind == "event") never
    fired. The event half of a compound was mis-kinded, not dropped.

    Cycle 2 (product convention, Gil 2026-09-04): a reminder ABOUT an occasion
    with a date is a calendar entry even without a clock time — "set a
    reminder for my meeting today", "remind me of my meeting tomorrow" — while
    the errand form "remind me to <verb> …" stays a task unless clock-timed
    (cycle 1's rule)."""
    if kind != "task":
        return kind
    # "send a calendar invite …" names the calendar outright — no remind-word
    # needed (cycle 4: "…calendar invite out to James and Alice for brunch at
    # 11 am" was labelled task and produced no event).
    if re.search(r"\bcalendar\s+invite\b", text, re.I):
        return "event"
    # Q1 (product convention, Gil 2026-09-06): a dated "I need to <meet/
    # talk/have a conversation> …" is an appointment being made — "on Monday,
    # the 20th, I need to have a conversation with Greg" is a calendar event,
    # no remind-word required. Encounter verbs only: "I need to buy …" is
    # still an errand, and an undated encounter stays a task.
    if (_NEED_ENCOUNTER_RE.search(text)
            and (_DATED_RE.search(text) or _CLOCKISH_RE.search(text))):
        return "event"
    if not _REMINDISH_RE.search(text):
        return kind
    if _CLOCKISH_RE.search(text):
        return "event"
    if (not _REMIND_TO_VERB_RE.search(text)
            and _OCCASION_RE.search(text) and _DATED_RE.search(text)):
        return "event"
    return kind


#: The calendar named as the destination. It OUTRANKS every to-do signal:
#: "get rid of that task on my calendar the 3rd" says "task" and means an
#: event, and the destination is the speaker being explicit about which of
#: the two lists they mean.
_CALENDAR_DEST_RE = re.compile(
    r"\b(?:on|to|in|from|off)\s+(?:my|the)\s+"
    r"(?:calendar|schedule|diary|agenda)\b", re.I)


#: Arranging to be in the same place as someone — "get Blake and me TOGETHER
#: for staff meeting", "meet up with Sage", "catch up with Jordan". These open
#: with `get`, which the errand list claims, but nobody puts a gathering on a
#: to-do list; it is an appointment being made.
_GATHERING_RE = re.compile(
    r"\bget\s+[\w' ]{0,30}\btogether\b"
    r"|\bmeet(?:\s+up)?\s+with\b"
    r"|\bcatch\s+up\s+with\b"
    r"|\bsit\s+down\s+with\b", re.I)


def _kind_of(text: str) -> str:
    t = text.strip()
    if _REVIEW_RE.search(t):
        return "review"
    if _CALENDAR_DEST_RE.search(t) or _GATHERING_RE.search(t):
        return "event"
    if _TASK_RE.search(t):
        # The pinned convention distinguishes "remind me TO <verb> …" (an
        # errand — stays a task) from "remind me ABOUT <occasion> …" (a
        # calendar entry). `_enforce_pinned_kinds` already honours that split;
        # this call site did not, and flipped ANY remind-worded row carrying a
        # clock time to the calendar. "remind me to feed the cat at 14:00" is
        # a to-do with a time on it, not a meeting with the cat.
        if (re.search(r"\bremind", t, re.I) and _CLOCKISH_RE.search(t)
                and not _REMIND_TO_VERB_RE.search(t)):
            return "event"
        return "task"
    return "event"


def _deterministic_segments(text: str, cfg) -> "tuple[list[str], str | None]":
    """Split on delimiters that cannot occur inside a command. Returns
    (segments, how) — how is None when nothing split."""
    hits = _COALESCE_RE.findall(text)
    if len(hits) > 1:
        return [s.strip() for s in hits if s.strip()], "coalesced"
    hits = _BRACKET_RE.findall(text)
    if len(hits) > 1:
        return [s.strip() for s in hits if s.strip()], "batched"
    separator = (cfg.audio.event_separator or "").strip()
    if separator:
        parts = [s.strip() for s in
                 re.split(re.escape(separator), text, flags=re.IGNORECASE)
                 if s.strip()]
        if len(parts) > 1:
            return parts, "separator"
    parts = _clause_segments(text)
    if len(parts) > 1:
        return parts, "clauses"
    return [text.strip()], None


def _clause_segments(text: str) -> "list[str]":
    """Split where the PARSE shows two asks meeting — "book the gym and remind
    me to buy milk" — and nowhere else.

    Why this tier had to exist: every delimiter above is something the PHONE
    inserts (brackets, the coalescing wrapper, a configured separator), not
    anything a person says. On dictated speech none of them can ever fire, and
    the board measured the consequence — 0 splits in 4,920 rows, so 6.2% of
    compounds were atomized correctly and every real compound fell through to
    the LLM tier or stayed merged.

    `coordination.split_clauses` is the judgement (dependency parse: a VERB
    conjunct with its own argument is a second ask; a NOUN conjunct is a longer
    noun phrase), so names, lists and shared objects are never split — "meeting
    with Tal and Ravid", "buy chicken and rice", "wash and fold the laundry"
    all come back whole. The under-split bias is preserved: no confident
    boundary means no split, and the LLM tier still gets its turn.
    """
    from assistant.intent.coordination import split_clauses

    # An enumeration with a header ("two tasks due tomorrow: A and B") is the
    # LLM tier's specialty and not this one's: the header has to be recognised
    # and dropped, and its shared deadline distributed into each item. A clause
    # split cuts at the "and" but not at the colon, which glues the header onto
    # the first item and loses the deadline from the rest. Leave it alone.
    if _HEADER_PREFIX_RE.match(text) or _WRAPPED_RE.search(text):
        return [text.strip()]

    parts = [p.strip() for p in split_clauses(text) if p.strip()]
    if len(parts) < 2:
        return [text.strip()]
    # A modifier is not an ask — refuse the whole split rather than dropping
    # it, because its words (the reminder offset, the destination, the
    # annotation) still belong to the command the later stages read. Checked
    # on EVERY part, not just the trailing ones: the modifier leads as often
    # as it follows ("flag this, restock the pantry").
    if any(_is_modifier_not_ask(p) for p in parts):
        return [text.strip()]
    # Residue guards, the same two the LLM tier applies to its own output: a
    # fragment is the splitter imagining structure, and a part that is only
    # scheduling words ("due tomorrow") is phrasing left over, not a request.
    if any(len(p.split()) < 2 for p in parts) or any(_schedule_only(p) for p in parts):
        return [text.strip()]
    return _share_leading_date(parts)


def _share_leading_date(parts: "list[str]") -> "list[str]":
    """Carry a date said ONCE at the front into the parts that have none.

    "tomorrow gym at 7 am and a meeting with Tal at 11" is two events, both
    tomorrow — but a clause split leaves the second one dateless, and a
    dateless create lands today. The LLM tier's prompt already distributes a
    shared date this way; the deterministic tier has to do it too or splitting
    would trade a merge bug for a date bug.

    Deliberately LEADING only, and leading means the utterance OPENS with it.
    A date sitting inside the first ask belongs to that ask — "book gym
    tomorrow at 7am and remind me to buy milk" is a gym session tomorrow and a
    milk errand with no date at all, so copying "tomorrow" onto the milk would
    invent a deadline the speaker never gave. That is the same failure as a
    repeated relative date overwriting other events' real dates, which this
    project has already had once. A trailing date is ambiguous for the mirror
    reason ("buy milk and call the dentist tomorrow" may or may not date the
    milk), so it is left to a stage that can weigh it.
    """
    if not _DATED_RE.match(parts[0]):
        return parts                      # the date is not the opening words
    dated = [bool(_DATED_RE.search(p)) for p in parts]
    if any(dated[1:]):
        return parts                      # a later part names its own date
    phrase = _DATED_RE.match(parts[0]).group(0).strip()
    return [parts[0]] + [f"{p} {phrase}" for p in parts[1:]]


# Words that can (but very often do not) join two independent requests. Their
# absence is a free proof the input is one item — the LLM is never consulted.
_COMPOUND_HINT = re.compile(r"\b(and|then|also|plus|after that)\b|,|;", re.I)

# "add tasks", "two tasks due tomorrow", "3 reminders" — announces a list,
# requests nothing.
_HEADER_RE = re.compile(
    r"^(?:please\s+)?(?:add|set|create|make|new|two|three|four|\d+)\s+"
    r"(?:tasks?|events?|reminders?|things?)(?:\s+due\s+\w+)?\s*:?$", re.I)

# The same header, still ATTACHED to the list it introduces — "two tasks due
# tomorrow: buy groceries and …". Only the deterministic clause tier needs
# this form, to recognise an enumeration it should not touch.
_HEADER_PREFIX_RE = re.compile(
    r"^(?:please\s+)?(?:add|set|create|make|new|two|three|four|\d+)\s+"
    r"(?:tasks?|events?|reminders?|things?)\b[^:]{0,30}:", re.I)

# A trailing clause that MODIFIES the ask before it rather than being a second
# ask. Both shapes measured on the persona test half, where a naive clause
# split manufactured 139 items out of atomic commands:
#
#   • a lead-time offset — "…at 1pm and give me a nudge an hour before" (51 of
#     the 139). A reminder offset is a SLOT of the event it follows; there is
#     nothing for it to be an ask ABOUT on its own.
#   • an anaphoric commit — "…, put that in the diary", "…, do cross it off",
#     "…, sorry put in calendar". The speaker is naming where the FIRST ask
#     goes, using a pronoun to point back at it.
#
# The unifying rule, and why these are safe to refuse: an ask has to name
# something of its own. A tail that only points back at what was already said
# is one ask still being spoken.
_LEAD_TIME_TAIL_RE = re.compile(
    r"\b(?:before|ahead(?:\s+of\s+(?:time|it))?|in\s+advance|earlier)\s*[.!?]?$",
    re.I)

_BACKREF_RE = re.compile(r"\b(?:it|that|this|them|those|these)\b", re.I)

#: Command verbs that act on a thing rather than naming one. Paired with a
#: back-reference below — "please change IT", "do cross IT off", "put THAT in
#: the diary" — they are the speaker saying what to do with the ask they just
#: made. The edit and delete verbs matter as much as the filing ones: the
#: persona board's `ue_move` and `de_named` families end almost every command
#: this way ("…has been moved to 8:30am, please change it").
_FILE_VERB_RE = re.compile(
    r"\b(?:put|add|stick|pop|note|jot|log|save|enter|cross|tick|check|mark|"
    r"flag|cancel|change|delete|remove|move|reschedule|update|rename|drop|"
    r"clear|scratch|bin|shift)\b", re.I)

#: "put in calendar" — a destination with nothing to put in it. Also "add a
#: note", "add a reminder": an ANNOTATION on the ask just made, carrying no
#: content of its own ("change the due date of X to friday AND ADD A NOTE" is
#: one edit, and was 14 of the FastRule half's 28 atomic over-splits).
_DESTINATION_ONLY_RE = re.compile(
    r"^(?:(?:so|sorry|please|do|and|then|also|just|now|ok(?:ay)?)\s+)*"
    r"(?:put|add|stick|pop|note|save|enter)\s+"
    r"(?:it|that|this|them)?\s*(?:in|on|onto|into|to)?\s*"
    r"(?:a|an|my|the)?\s*(?:calendar|diary|schedule|list|to-?do|tasks?|agenda|"
    r"planner|note|reminder|comment|label|flag|tag)?"
    r"\s*[.!?]?$", re.I)


def _names_something(part: str) -> bool:
    """Does this part name a thing, or is it only a verb?

    An ask has a subject. "wrapped up", "sorted", "done with that" are the
    speaker closing the sentence they just said, and a clause split turns them
    into items that then get a title invented for them. Parsing is affordable
    here — the doc is memoised and segment is not the latency-critical path.
    """
    from assistant.intent.coordination import parsed

    doc = parsed(part)
    if doc is None:
        return True                # cannot tell ⇒ do not block on this ground
    return any(t.pos_ in ("NOUN", "PROPN", "PRON", "NUM") for t in doc)


def _is_modifier_not_ask(part: str) -> bool:
    """Is this part a modifier of the ask beside it, rather than its own ask?"""
    if _LEAD_TIME_TAIL_RE.search(part):
        return True
    if _FILE_VERB_RE.search(part) and _BACKREF_RE.search(part):
        return True
    if _DESTINATION_ONLY_RE.match(part):
        return True
    return not _names_something(part)


# "add X and Y to my list" — one verb and one destination WRAPPING both items.
# A clause split cuts at the "and" and tears the wrapper in half, leaving an
# unroutable "add buy milk" and a "buy bread to my list" carrying words that
# were never a title. Decompose owns this shape (it knows to distribute the
# verb and drop the destination), so the clause tier must not touch it.
_WRAPPED_RE = re.compile(
    r"^(?:please\s+)?(?:add|put|stick|throw|chuck)\b.*\b(?:to|on|onto|in)\s+"
    r"(?:my|the)\s+(?:to-?do|task|shopping|grocery|groceries|errand|"
    r"calendar|list|schedule)\b", re.I)

_SEGMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["event", "task", "review"]},
                    "text": {"type": "string"},
                },
                "required": ["kind", "text"],
            },
        },
    },
    "required": ["items"],
}

_SEGMENT_SYSTEM = """You split ONE voice command to a calendar assistant into its independent requests, if it contains more than one.

Rules, in order of importance:
1. When in doubt, DO NOT SPLIT. Return the whole command as one item. A wrong
   merge is recoverable; a wrong split is not.
2. Never split people joined by "and": "meeting with Tal and Ravid" is ONE
   event with two guests.
3. Never split a thing and its description: "fish and chips" is one dish,
   "buy a gift for mom and dad" is one errand.
4. Split only when two independent requests are joined: "book gym at 7 and
   remind me to buy milk" is two.
5. Copy the speaker's own words into each item's text. A date or deadline
   said once for the whole list may be repeated into each item; beyond that,
   never rephrase, summarise or invent words.
6. kind: "event" books or changes something on the calendar, "task" is a
   to-do, "review" asks what is scheduled.
7. A list of tasks after a colon or "and" IS several items when each part is
   its own instruction: "add tasks: submit the grades, prepare the slides"
   is two tasks. But a list of THINGS for one verb stays one item ("buy
   milk, eggs and bread" — the assistant splits shopping lists itself).

Examples:
"book gym tomorrow at 7am and remind me to buy milk"
→ {"items": [{"kind": "event", "text": "book gym tomorrow at 7am"},
             {"kind": "task", "text": "remind me to buy milk"}]}
"add tasks: submit the Haxaga grades, prepare Netivim slides"
→ {"items": [{"kind": "task", "text": "submit the Haxaga grades"},
             {"kind": "task", "text": "prepare Netivim slides"}]}
"meeting with Tal and Ravid at Kems tomorrow evening"
→ {"items": [{"kind": "event", "text": "meeting with Tal and Ravid at Kems tomorrow evening"}]}
"two tasks due tomorrow: buy groceries and return the library book"
→ {"items": [{"kind": "task", "text": "buy groceries due tomorrow"},
             {"kind": "task", "text": "return the library book due tomorrow"}]}
"set a meeting tomorrow at 1 pm, another one at 4 pm and then pizza at 6:30 at edo's"
→ {"items": [{"kind": "event", "text": "set a meeting tomorrow at 1 pm"},
             {"kind": "event", "text": "a meeting tomorrow at 4 pm"},
             {"kind": "event", "text": "pizza at 6:30 at edo's tomorrow"}]}
"tomorrow gym at 7 am and a meeting with Tal at 11"
→ {"items": [{"kind": "event", "text": "gym at 7 am tomorrow"},
             {"kind": "event", "text": "a meeting with Tal at 11 tomorrow"}]}
"two events tomorrow, one at four o'clock meeting with Rei and one at 7 pm pizza with Ezra"
→ {"items": [{"kind": "event", "text": "meeting with Rei at four o'clock tomorrow"},
             {"kind": "event", "text": "pizza with Ezra at 7 pm tomorrow"}]}

An event chain ("another one at X", "then Y at Z", "one at A and one at B")
is one event PER time-and-activity — and a date said once for the chain
("tomorrow") is repeated into each item, like a shared deadline.

But do NOT split finer than the requests themselves:
"i need to buy some groceries, i need rice and chicken"
→ {"items": [{"kind": "task", "text": "buy some groceries"},
             {"kind": "task", "text": "buy rice and chicken"}]}
(two "i need" clauses = two items; "rice and chicken" stays together — the
assistant splits shopping lists itself, and a list of THINGS is never split
here.) Likewise "add tasks: A, B, pay C" is exactly three items, never more.

Return JSON: {"items": [{"kind": ..., "text": ...}, ...]}"""


_SCHEDULE_WORDS = frozenset(
    "due today tomorrow tonight next this on at am pm oclock o'clock the a an "
    "of in for by until till week month monday tuesday wednesday thursday "
    "friday saturday sunday morning afternoon evening night".split())


def _schedule_only(text: str) -> bool:
    """"due tomorrow", "at 5 pm" — scheduling words with nothing scheduled.
    As a split part it is residue of the phrasing, not a request (run 12: a
    stray "due tomorrow" part became a phantom create)."""
    words = [w for w in re.findall(r"[a-z0-9':]+", text.lower()) if w]
    return bool(words) and all(w in _SCHEDULE_WORDS or w.replace(":", "").isdigit()
                               for w in words)


def _llm_segments(state: EngineState, cfg) -> "list[Item] | None":
    """One schema-constrained call, only when the words even suggest compounding
    — and biased to under-split (see module docstring). None = keep one item."""
    from assistant.engine import llm as _llm

    text = state.text
    # FastRule already read this command and may have concluded it is more
    # than one item (Gil: pass its work to the next stage). A STRUCTURE
    # verdict is stronger evidence than the cue-word regex below — the
    # atomicity model reaches ~88% compound recall on the FastRule test half,
    # where the regex only knows announced joiners ("and then", "; also").
    verdict = state.fastrule_verdict or {}
    fastrule_says_compound = verdict.get("reason_class") == "structure"
    if len(text.split()) < 6:
        return None
    if not fastrule_says_compound and not _COMPOUND_HINT.search(text):
        return None
    system = _SEGMENT_SYSTEM
    if fastrule_says_compound:
        # ground the call in WHY the deterministic reader declined, rather
        # than asking the model to rediscover it from the raw words
        system += ("\n\nA deterministic parser read this command and concluded "
                   f"it is more than one request ({verdict.get('reason')}). "
                   "Trust that it contains at least two, and find the split.")
    if state.mistakes:
        # A loop-back from step 6 carries what went wrong last time — the
        # retried attempt must not repeat it.
        system += "\n\nOn a previous attempt at THIS command you made these " \
                  "mistakes — do not repeat them:\n- " + "\n- ".join(state.mistakes)
    try:
        out, ms = _llm.call_json(cfg, system, f"The command: {text}", _SEGMENT_SCHEMA)
        state.llm_ms += ms
    except Exception:
        # Segmentation must never lose the command: one item is always a
        # legitimate reading, and if the model is truly offline step 5 will
        # say so through the pending queue.
        return None
    raw_items = out.get("items") or []
    parts = [(str(d.get("kind", "")).strip(), str(d.get("text", "")).strip())
             for d in raw_items if isinstance(d, dict)]
    parts = [(k if k in ("event", "task", "review") else _kind_of(t), t)
             for k, t in parts if t]
    parts = [(_enforce_pinned_kinds(k, t), t) for k, t in parts]
    # An enumeration HEADER ("add tasks", "two tasks due tomorrow") is not a
    # request — it announces the list. Kept as an item it parses to unknown
    # or a phantom row (run 11: one header ate a real task, another became a
    # third create). Drop headers; their due-phrase is already distributed
    # into the real items by the prompt's shared-deadline policy.
    parts = [(k, t) for k, t in parts if not _HEADER_RE.match(t)
             and not _schedule_only(t)]
    if len(parts) <= 1:
        return None
    # Under-split bias, enforced: a "split" that produced a fragment (a lone
    # word with no verb or time) is the model imagining structure — refuse it.
    if any(len(t.split()) < 2 for _, t in parts):
        return None
    # …and the same discipline the deterministic tiers carry. Measured on the
    # FastRule test half, the `--llm` lane splits compounds far better than the
    # parse (bleed 55.8% → 7.3%) and INVENTS structure where there is none:
    # OVER 12.8% on the complex tier, and atomic rows kept-at-1 falling from
    # 99.8% to 95.1%. The families say what it is doing — generic_target
    # 62.7% OVER, date_marking 34.8%, all_day 33.3%, propose_confirm 27.1%:
    # every one a shape with no second ask to find. The model has no
    # under-split bias of its own, so the bias stays enforced in code here,
    # exactly as it is for the clause tier and the list tier.
    if not every_part_is_an_ask([t for _, t in parts]):
        return None
    return [Item(id=f"item_{i + 1}", kind=k, text=t)
            for i, (k, t) in enumerate(parts)]


def run(state: EngineState, cfg) -> EngineState:
    from assistant.trace import LLM, RULE

    segments, how = _deterministic_segments(state.text, cfg)

    # The delimiters must not survive into titles — an event called "[gym]"
    # helps nobody. The working transcript becomes the joined segments.
    #
    # A CLAUSE split is exempt: it cuts at a joiner the speaker actually said,
    # so there is no delimiter to strip, and rejoining the parts would drop
    # that "and" from the text every later stage grounds itself on.
    if how and how != "clauses":
        state.text = " ".join(segments)

    # `_enforce_pinned_kinds` used to be reachable ONLY from `_llm_segments`,
    # so every item the deterministic tiers produced bypassed the pinned
    # product conventions — the reminder-about-an-occasion rule, the "i need
    # to meet" encounter rule, the calendar-invite rule. That was survivable
    # while the deterministic tiers split almost nothing; the clause splitter
    # made this path carry most of the traffic, and the conventions have to
    # hold wherever the item came from.
    state.items = [
        Item(id=f"item_{i + 1}",
             kind=_enforce_pinned_kinds(_kind_of(seg), seg), text=seg)
        for i, seg in enumerate(segments)
    ]

    if how:
        if state.trace:
            state.trace.step(RULE, "Split into commands",
                             f"{len(segments)} {how}: "
                             + " · ".join(s[:40] for s in segments))
        return state

    llm_items = _llm_segments(state, cfg)
    if llm_items:
        state.items = llm_items
        if state.trace:
            state.trace.step(LLM, "Split into commands",
                             f"{len(llm_items)} items: "
                             + " · ".join(it.text[:40] for it in llm_items))
        return state

    if state.trace:
        state.trace.step(RULE, "Segmented", f"1 item ({state.items[0].kind})")
    return state
