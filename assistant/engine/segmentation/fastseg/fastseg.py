"""FastSeg — the deterministic half of the segment component.

    text  ->  [(action, time, tag), ...]

Three phases, in this order, and the order is measured rather than chosen:
DialogUSR's ablation (Findings of EMNLP 2022) reports Split -> (Delete +
Complete) beating the reverse by 9 exact-match points, which is exactly the
cut-then-assign shape below.

  1  CUT          delimiters, then the clause parse, looped to a fixed point
  2  ASSIGN TIME  reads the pieces AND the original string together
  3  TAG          event | task | review

It lives in `assistant/engine/segmentation/experiments/` rather than in `assistant/engine/` on purpose:
this is the thing being tuned, and the engine is serving a phone. It IMPORTS
the two stable readers it needs (the clause splitter and the ask guard) rather
than copying them, so a fix there is not made twice.

Why phase 2 exists as its own phase, in Gil's words: "given a string input we
need to break down to all the independent actions, then GIVEN THAT AND THE
ORIGINAL STRING adjust the time tag." Once a command has been cut, a splitter
working piece-by-piece can no longer see that a leading "tomorrow" covers the
second piece too. Holding both is what makes the distribution possible.
"""
from __future__ import annotations

import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from assistant.engine.segmentation.fastseg import invariant as _invariant   # noqa: E402

# ---------------------------------------------------------------------------
# TIME EXPRESSIONS
#
# The extractor answers one question: where in the string is a time reference,
# and what kind is it. It never RESOLVES — "next friday" stays "next friday".
# Gil: "the time will be friday. dont add more information that is not your
# job here." Resolution belongs to a later stage; doing it here would invent
# information the speaker did not give.
# ---------------------------------------------------------------------------

_WEEKDAY = (r"monday|tuesday|wednesday|thursday|friday|saturday|sunday"
            r"|mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun")
_MONTH = (r"january|february|march|april|may|june|july|august|september"
          r"|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept"
          r"|oct|nov|dec")

_HOURWORD = (r"one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve")
#: Minute words a spoken clock can end in. Deliberately a CLOSED list: an open
#: `\w+` would read "book three rooms" as 3:00-something.
_MINWORD = (r"o'?clock|fifteen|twenty[\s-]five|twenty|thirty[\s-]five|thirty|"
            r"forty[\s-]five|forty|fifty[\s-]five|fifty|ten|five")
_COUNTWORD = (r"a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve"
              r"|\d+")
#: One end of a spoken range. Bare numbers are allowed HERE and nowhere else,
#: because "between 2 and 4" is unambiguous while a loose "2" is not.
_RANGEEND = (rf"(?:\d{{1,2}}(?::\d{{2}})?\s*(?:am|pm|a\.m\.|p\.m\.)?"
             rf"|noon|midday|midnight|{_HOURWORD})")

#: Ordered longest-first: a longer phrase must win over a fragment of itself,
#: or "every friday" is read as the bare date "friday" and the recurrence is
#: lost. Each entry is (pattern, kind).
_TIME_PATTERNS: "list[tuple[str, str]]" = [
    # --- recurrence. Temporal repetition IS the time (Gil's ruling), so it is
    #     captured whole rather than reduced to the weekday inside it.
    (rf"\bevery\s+other\s+(?:{_WEEKDAY}|day|week|month)\b", "recurrence"),
    (rf"\bevery\s+(?:{_WEEKDAY}|weekday|day|week|month|morning|evening|night)\b",
     "recurrence"),
    (r"\b(?:daily|weekly|monthly|nightly)\b", "recurrence"),
    (rf"\beach\s+(?:{_WEEKDAY}|day|week|month)\b", "recurrence"),

    # --- deadline markers. These are what distribute across a whole command
    #     ("submit the grades and prepare the slides BY FRIDAY").
    (rf"\b(?:by|before|due|until|till)\s+(?:the\s+)?"
     rf"(?:{_WEEKDAY}|{_MONTH}\s+\d{{1,2}}(?:st|nd|rd|th)?|today|tomorrow|tonight"
     rf"|next\s+\w+|this\s+\w+|the\s+\d{{1,2}}(?:st|nd|rd|th)|end\s+of\s+\w+)\b",
     "deadline"),

    # --- clock times
    (r"\bat\s+(?:around\s+|about\s+)?\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)?"
     r"(?:\s*o'?clock)?\b", "clock"),
    (r"\b\d{1,2}:\d{2}\s*(?:am|pm|a\.m\.|p\.m\.)?\b", "clock"),
    (r"\b\d{1,2}\s*(?:am|pm|a\.m\.|p\.m\.)\b", "clock"),
    (r"\b(?:half\s+past|quarter\s+past|quarter\s+to)\s+\w+\b", "clock"),
    (r"\b(?:noon|midday|midnight)\b", "clock"),
    (r"\bat\s+(?:first\s+thing|lunchtime|dinnertime)\b", "clock"),

    # --- dates
    (r"\b(?:the\s+)?day\s+after\s+tomorrow\b", "date"),
    (r"\b(?:today|tomorrow|tonight|yesterday)\b", "date"),
    (rf"\b(?:next|this|last|coming)\s+(?:{_WEEKDAY}|week|month|year|weekend)\b",
     "date"),
    (rf"\bthis\s+coming\s+(?:{_WEEKDAY})\b", "date"),
    (rf"\bon\s+(?:the\s+)?(?:{_WEEKDAY})\b", "date"),
    (rf"\b(?:{_WEEKDAY})\b", "date"),
    (rf"\b(?:{_MONTH})\s+\d{{1,2}}(?:st|nd|rd|th)?\b", "date"),
    (r"\bthe\s+\d{1,2}(?:st|nd|rd|th)\b", "date"),
    (r"\bin\s+(?:a|an|one|two|three|four|five|\d+)\s+(?:day|week|month)s?\b", "date"),
    # "two weeks from now", "a week from today". Generalised from the original
    # "a week from (today|tomorrow|now)": the bank renders counted variants too,
    # and the narrow pattern found only the bare "today" inside them.
    (r"\b(?:a|an|one|two|three|four|five|six|\d+)\s+(?:day|week|month)s?\s+"
     r"from\s+(?:today|tomorrow|now)\b", "date"),
    (r"\b(?:this|next)\s+(?:morning|afternoon|evening)\b", "date"),
    (r"\b(?:in\s+the\s+)?(?:morning|afternoon|evening)\b", "date"),
    (r"\bnew\s+year'?s\s+eve\b", "date"),
    (r"\bchristmas(?:\s+day)?\b", "date"),

    # ================= 2026-09-09 span vocabulary (PLAN.md Phase 1) ==========
    # Ordering in this list does NOT matter: `find_time_refs` collects every
    # candidate and takes them longest-first. These are entries, not placements.

    # --- LEAD TIME, a reference in its own right. The `lead_time` trap sat at
    #     0.0% on 72 rows because nothing here matched "15 minutes before".
    (rf"\b(?:half\s+an?|{_COUNTWORD})\s+(?:minute|min|hour|day|week)s?\s+"
     r"(?:before|beforehand|ahead|prior|in\s+advance)\b", "lead"),

    # --- RANGES as ONE reference. Matched as two ends (or not at all), which
    #     left "from 3" in the action and "to 4pm" as the whole time.
    (rf"\b(?:from|between)\s+{_RANGEEND}\s+(?:to|until|till|and|through|thru)\s+"
     rf"{_RANGEEND}\b", "range"),

    # --- CLOCK + half of day as ONE span. Two refs before this, so the digit
    #     stranded in the action AND "in the morning" read as a DAY, which
    #     suppressed the date floor. One entry, two symptoms.
    (rf"\b(?:\d{{1,2}}(?::\d{{2}})?\s*(?:am|pm)?|{_HOURWORD})\s+in\s+the\s+"
     r"(?:morning|afternoon|evening)\b", "clock"),

    # --- COARSE + MODIFIER. The bare word matched and the modifier stranded
    #     ("book yoga late" / "afternoon"). Clock-class because gold FLOORS it.
    (r"\b(?:early|late|mid)[\s-]*(?:morning|afternoon|evening|night)\b", "clock"),
    (r"\bfirst\s+thing(?:\s+in\s+the\s+morning)?\b", "clock"),
    (r"\b(?:around|about)?\s*(?:lunchtime|dinnertime|suppertime)\b", "clock"),

    # --- SPOKEN CLOCKS. Not matched at all before; Whisper writes what was said.
    (rf"\b(?:{_HOURWORD})\s+(?:{_MINWORD})\b", "clock"),
    (rf"\b(?:half|quarter|twenty[\s-]five|twenty|fifteen|ten|five)\s+"
     rf"(?:past|to)\s+(?:{_HOURWORD}|\d{{1,2}})\b", "clock"),

    # --- "12 noon": `noon` won and the 12 stranded — the `at late` bug again.
    (r"\b12\s*(?:noon|midday)\b", "clock"),

    # --- OFFSET IN HOURS. The offset pattern covers day/week/month and not hour,
    #     so "in two hours" produced no reference whatsoever (corpus 25x).
    (rf"\bin\s+(?:{_COUNTWORD})\s+hours?\b", "clock"),

    # --- END OF A MONTH / YEAR (corpus 74x), outside a deadline marker too.
    (rf"\b(?:the\s+)?end\s+of\s+(?:the\s+)?(?:month|year|week|{_MONTH})\b", "date"),

    # --- A PLURAL WEEKDAY IS A SERIES, not a date: "gym on sundays" is weekly.
    #     `\bsunday\b` cannot match "sundays" (corpus 31x, dataset had 0 rows).
    (rf"\b(?:on\s+)?(?:{_WEEKDAY})s\b", "recurrence"),

    # --- ONE-WORD and FREQUENCY cadences (corpus 79x).
    (r"\b(?:everyday|every\s+year|annually|yearly|biweekly|fortnightly)\b",
     "recurrence"),
    (r"\b(?:once|twice|thrice)\s+a\s+(?:day|week|month|year)\b", "recurrence"),
    (r"\bevery\s+(?:weekend|other\s+day)\b", "recurrence"),
    (r"\bevery\s+\w+\s+(?:days|weeks|months)\b", "recurrence"),

    # --- MONTH + ORDINAL in the "of" order. This is §8.2: the bare-ordinal
    #     pattern won and "of november" stranded, so the MONTH was never handed
    #     downstream at all.
    (rf"\b(?:the\s+)?\d{{1,2}}(?:st|nd|rd|th)?\s+of\s+(?:{_MONTH})\b", "date"),

    (r"\bthe\s+rest\s+of\s+the\s+day\b", "date"),

    # --- WEEKDAY + half of day as ONE span. As two refs, the trailing "morning"
    #     made the right-hand side of a conjunct look TIMED, and
    #     "a cut and blow dry on saturday morning" split into two items.
    (rf"\b(?:{_WEEKDAY})\s+(?:morning|afternoon|evening|night)\b", "date"),
    (rf"\b(?:tomorrow|today|tonight)\s+(?:morning|afternoon|evening|night)\b", "date"),

    # --- A MULTI-DAY SERIES is ONE reference: "every tuesday and thursday" is a
    #     weekly series naming two days (Gil, 2026-09-08), not two references
    #     with a joiner between them — read as two, the "and" split the series.
    (rf"\bevery\s+(?:{_WEEKDAY})(?:\s*,\s*(?:{_WEEKDAY}))*"
     rf"(?:\s+and\s+(?:{_WEEKDAY}))+\b", "recurrence"),
]

_COMPILED = [(re.compile(p, re.I), kind) for p, kind in _TIME_PATTERNS]


class TimeRef:
    """One time expression, and where it sits in the command."""

    __slots__ = ("start", "end", "text", "kind")

    def __init__(self, start: int, end: int, text: str, kind: str):
        self.start, self.end, self.text, self.kind = start, end, text, kind

    def __repr__(self) -> str:                     # pragma: no cover
        return f"TimeRef({self.text!r}@{self.start}:{self.end},{self.kind})"


def find_time_refs(text: str) -> "list[TimeRef]":
    """Every time expression in the command, left to right, non-overlapping.

    Longest match wins at a given position, which is what keeps "every friday"
    whole instead of yielding the bare date "friday".

    That used to be a claim in this docstring rather than a property of the
    code: the pattern list is grouped by KIND, and within the date group the
    bare `today` sits above `a week from today`, so "plan lunch a week from
    today" yielded `today` and left "a week from" stranded in the action. It
    cost 31 of the 66 content-loss rows and mis-assigned the time on every one
    of them. Now the matches are collected first and taken longest-first, so
    the ordering of `_TIME_PATTERNS` cannot silently decide the answer.
    """
    candidates: list[tuple[int, int, str]] = []
    for rx, kind in _COMPILED:
        for m in rx.finditer(text):
            candidates.append((m.start(), m.end(), kind))
    candidates.sort(key=lambda c: (-(c[1] - c[0]), c[0]))

    refs: list[TimeRef] = []
    taken = [False] * (len(text) + 1)
    for start, end, kind in candidates:
        if any(taken[start:end]):
            continue                               # inside something already taken
        # Trim trailing whitespace the pattern swallowed. "at 7 " ended one
        # character past its own piece, so the reference fell OUTSIDE the
        # piece that owned it and was treated as an edge — which silently
        # distributed a clock time across the whole command.
        s, e = start, end
        while e > s and text[e - 1].isspace():
            e -= 1
        s = _absorb_preposition(text, s, taken)
        refs.append(TimeRef(s, e, text[s:e].strip(), kind))
        for i in range(s, e):
            taken[i] = True
    refs.sort(key=lambda r: r.start)
    return refs


#: SPEC captures the time AS SPOKEN — "by friday", "on the 15th", "for
#: christmas day" — but only some patterns spell their preposition out, so
#: `the 15th` and `christmas day` came back bare. That cost twice over: the
#: preposition was missing from the time AND left stranded in the action
#: ("schedule flight to Chicago for"). Absorbing it here fixes both at once,
#: and keeps this list identical to the generator's `_PREP`, so gold and
#: prediction cannot disagree by convention.
_LEADING_PREP = re.compile(
    r"\b(at|on|for|by|from|in|to|starting|until|through|around)\s+$", re.I)


def _absorb_preposition(text: str, start: int, taken: "list[bool]") -> int:
    """Extend a reference left over the preposition it was spoken with."""
    m = _LEADING_PREP.search(text, 0, start)
    if not m or any(taken[m.start():start]):
        return start
    return m.start()


# ---------------------------------------------------------------------------
# PHASE 1 — CUT
# ---------------------------------------------------------------------------

def cut(text: str, max_rounds: int = 3) -> "list[str]":
    """The command split into independent asks, as substrings.

    Looped to a FIXED POINT rather than run once. Measured before building:
    re-running the splitter on its own output changes the count on 2 of 5,014
    FastRule rows and 8 of 847 real-speech rows, and the rows it fixes are the
    three-ask ones — the splitter can leave a boundary on the table. The loop
    is free (no model, microseconds) and collects that whole ceiling.

    A fixed point is also the stopping test the literature uses: DisSim
    recurses a rule set until no rule fires, ADaPT recurses on executor
    failure, DecomP on a size check. None of them train an "is this atomic?"
    model, and the one paper that did reports 54-66% on the decision.
    """
    from assistant.intent.asks import every_part_is_an_ask
    from assistant.intent.coordination import split_clauses

    def once(piece: str) -> "list[str]":
        parts = [q.strip() for q in split_clauses(piece) if q.strip()]
        if len(parts) < 2 or not every_part_is_an_ask(parts):
            return _split_verbless_conjuncts(piece)
        return parts

    pieces = [text.strip()]
    for _ in range(max_rounds):
        nxt: list[str] = []
        for piece in pieces:
            nxt.extend(once(piece))
        if len(nxt) == len(pieces):
            break                                   # fixed point reached
        pieces = nxt
    return [p for p in pieces if p.strip()]


_CUT_JOINER = re.compile(r"\s*,\s*(?:and then|and also|and|then|also|plus)\s+"
                         r"|\s+(?:and then|and also|as well as|and|then|also|plus)\s+"
                         r"|\s*,\s*")


def _split_verbless_conjuncts(piece: str) -> "list[str]":
    """Split "set up physical therapy at 9:15 and birthday dinner at midnight".

    The clause splitter cannot see this boundary: the second conjunct is a bare
    NOUN PHRASE with no verb of its own, so nothing marks it as a clause. It is
    the single largest cut failure in the corpus — 29 of the 189 under-split
    rows sit on a plain "and", and another 24 on a bare comma.

    The evidence used instead of a verb is that **both sides carry their own
    time reference, and the right side has content that is not part of its
    time**. That second condition is what keeps the must-not-split decoys
    intact, and it is doing real work:

        set up physical therapy at 9:15 and birthday dinner at midnight
            right = "birthday dinner at midnight" -> "birthday dinner" left
            over once its time is removed                        -> SPLIT
        walk the dog at 9 and 2:30
            right = "2:30" -> nothing left over                  -> keep
        take the tablets at noon and at six
            right = "at six" -> nothing left over                -> keep
        meeting with Sam and Alex at 8
            LEFT carries no time at all                          -> keep

    A joiner sitting INSIDE a time reference is never a boundary — "book gym
    between 2 and 4" would otherwise cut its own range in half.
    """
    refs = find_time_refs(piece)
    if len(refs) < 2:
        return [piece]

    def timed(span: str) -> bool:
        """Does this side carry a time of its OWN?

        A LEAD TIME does not count. "book the gym at 1pm and give me a nudge an
        hour before" is ONE ask: the lead time modifies the same event rather than
        timing a second one, and counting it made the reminder clause look like an
        independent ask — 20 rows of over-split the moment lead times became
        visible (2026-09-09).
        """
        return any(r.kind != "lead" for r in find_time_refs(span))

    def has_own_content(span: str) -> bool:
        """Content left in the span once its time expressions are removed."""
        rest = span
        for ref in sorted(find_time_refs(span), key=lambda r: -r.start):
            rest = rest[:ref.start] + " " + rest[ref.end:]
        return bool(_invariant.content(rest))

    out: "list[str]" = []
    start = 0
    for m in _CUT_JOINER.finditer(piece):
        if any(r.start < m.end() and m.start() < r.end for r in refs):
            continue                                # joiner inside a time span
        left, right = piece[start:m.start()], piece[m.end():]
        if not left.strip() or not right.strip():
            continue
        if timed(left) and timed(right) and has_own_content(right):
            out.append(left.strip())
            start = m.end()
    out.append(piece[start:].strip())
    out = [p for p in out if p]
    return out if len(out) > 1 else [piece]


# ---------------------------------------------------------------------------
# PHASE 2 — ASSIGN TIME
# ---------------------------------------------------------------------------

def assign_times(text: str, pieces: "list[str]") -> "list[tuple[str, str]]":
    """(action, time) per piece, from the pieces AND the original together.

    The rule, from Gil's five worked cases:

        INTERIOR reference  -> binds to its own piece
        EDGE reference      -> covers every piece that has none of its own

    "Edge" means the reference sits before the first piece's content or after
    the last piece's, belonging to no piece on its own. That single rule gets
    all five cases right, including the two that look contradictory: a leading
    "tomorrow" covers both pieces, a trailing "by friday" covers both, and a
    "tomorrow" sitting INSIDE the second piece does not reach back to the
    first.
    """
    spans = _locate(text, pieces)
    refs = find_time_refs(text)

    owned: "list[list[TimeRef]]" = [[] for _ in pieces]
    lead: "list[TimeRef]" = []
    trail: "list[TimeRef]" = []
    last = len(pieces) - 1
    for ref in refs:
        for i, (s, e) in enumerate(spans):
            if s <= ref.start and ref.end <= e:
                owned[i].append(ref)
                # EDGE means at the boundary of the whole COMMAND, not outside
                # every piece — a trailing reference is textually inside the
                # last piece. So: opening the first piece, or closing the last.
                if len(pieces) > 1:
                    if i == 0 and ref.start <= s + 1:
                        lead.append(ref)
                    elif i == last and ref.end >= e - 1:
                        trail.append(ref)
                break
        else:
            lead.append(ref)

    out: "list[tuple[str, str]]" = []
    for i, piece in enumerate(pieces):
        mine = list(owned[i])
        # The two edges do NOT distribute the same way.
        #
        # LEADING fills a SLOT the piece left empty, not merely a piece that
        # named nothing at all: "tomorrow gym at 7 and meeting at 11" — the
        # second piece has a clock but no DAY, so "tomorrow" still reaches it.
        # Distributing only to time-less pieces would leave that meeting today.
        #
        # TRAILING reaches only a piece with NO time whatsoever. "submit the
        # grades and prepare the slides by friday" — the first piece has
        # nothing, so it takes "by friday". But in "do i have anything this
        # weekend and book the haircut at 3:45" the trailing clock must stay
        # with the haircut; per-slot distribution gave the question "this
        # weekend at 3:45", which is wrong. Found by generating gold from the
        # templates, not by reasoning — see generate.py.
        have = {_slot(r) for r in mine}
        for r in lead:
            if _slot(r) not in have and r not in mine:
                mine.append(r)
                have.add(_slot(r))
        if not mine:
            mine = list(trail)
        # BY SLOT CLASS, then position — the order gold uses
        # (`order = {"day": 0, "clock": 1}`, stable). Joining by position alone
        # scored "every week at 8 o'clock until next tuesday" against gold's
        # "every week until next tuesday at 8 o'clock": same tokens, wrong order.
        time_str = " ".join(r.text for r in sorted(
            mine, key=lambda r: (_SLOT_ORDER[_slot(r)], r.start)))
        action = _strip_spans(piece, [(r.start - spans[i][0], r.end - spans[i][0])
                                      for r in owned[i]])
        # THE DATE FLOOR (SPEC): the day defaults to today, the clock never
        # does. An item with a clock and no day is "today at 7", not "at 7".
        # FastSeg emitted the bare form while the tuned LLMSeg prompt taught
        # the floored one, so the two halves disagreed on every clock-only
        # item and the accept step paid for it on each.
        if not any(_slot(r) == "day" for r in mine):
            time_str = f"today {time_str}".strip()
        out.append((action, time_str))
    return out


#: The gold's own two classes (`experiments/generate.py`: `_DAY_SLOTS` /
#: `_CLOCK_SLOTS`), and the order it joins them in. Matched rather than invented —
#: gold puts `lead_time` and `time_range` on the CLOCK side, so a lead falling to
#: "day" here would both collide with a real date and satisfy the
#: `any(_slot(r) == "day")` test that guards the date floor, silently switching the
#: floor off.
_SLOT_ORDER = {"day": 0, "clock": 1}


def _slot(ref: "TimeRef") -> str:
    """Which slot a reference fills. A day and a clock time are different
    slots, so one does not block the other from being distributed."""
    return "clock" if ref.kind in ("clock", "range", "lead") else "day"


def _locate(text: str, pieces: "list[str]") -> "list[tuple[int, int]]":
    """Where each piece sits in the original. Pieces are substrings by
    construction (the cut only ever removes joiners), so a forward scan is
    exact; a piece that cannot be found falls back to a zero-width span at the
    cursor, which simply means it owns no time reference."""
    spans, cursor = [], 0
    for p in pieces:
        idx = text.find(p, cursor)
        if idx < 0:
            idx = text.find(p)
        if idx < 0:
            spans.append((cursor, cursor))
            continue
        spans.append((idx, idx + len(p)))
        cursor = idx + len(p)
    return spans


def _strip_spans(piece: str, spans: "list[tuple[int, int]]") -> str:
    """The piece with its own time expressions removed — this is `action`.

    Everything else stays, which is the point: the verb, the object, people,
    places, and any quantity ("buy 5 apples"). Gil: "make sure the action
    includes all the text for that item that is not related to time so we dont
    lose information like occurences etc which the decompose step is suppose
    to deal with."
    """
    if not spans:
        return _tidy(piece)
    keep, cursor = [], 0
    for s, e in sorted(spans):
        s, e = max(0, s), min(len(piece), e)
        if s > cursor:
            keep.append(piece[cursor:s])
        cursor = max(cursor, e)
    keep.append(piece[cursor:])
    return _tidy(" ".join(keep))


#: Prepositions left dangling when the time they governed is cut out — "book
#: the gym ON" reads as damage, and the token carries no information once its
#: object is gone.
_DANGLING = re.compile(r"\s+(?:on|at|for|in|by|from|to|of|this|next)\s*$", re.I)


def _tidy(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip(" ,;.")
    prev = None
    while prev != s:                                # "…for on" needs two passes
        prev = s
        s = _DANGLING.sub("", s).strip(" ,;.")
    return s


# ---------------------------------------------------------------------------
# PHASE 3 — TAG
# ---------------------------------------------------------------------------

#: Verbs that put something on the CALENDAR, and verbs that put something on
#: the TO-DO LIST. Read off TRAIN failures, so this is a train-derived lexicon
#: and carries the usual overfitting risk — the sealed half is what confirms
#: it. It is deliberately SMALL: it only has to beat the engine tagger on the
#: cases that tagger already gets wrong.
_CALENDAR_VERBS = frozenset("""
    book schedule plan arrange reschedule rebook cancel move postpone
    delete clear block
""".split())

_TASK_VERBS = frozenset("""
    remind buy call email text pick collect grab wash clean fold pack sort
    file pay submit prepare print water walk take change top order renew
    return drop send finish write update fix charge vacuum feed refill
    restock organize review back
""".split())


def _lexicon_kind(action: str) -> "str | None":
    for word in action.lower().replace(",", " ").split():
        word = word.strip(".!?")
        if word in _CALENDAR_VERBS:
            return "event"
        if word in _TASK_VERBS:
            return "task"
    return None


def tag(action: str, time_str: str) -> str:
    """event | task | review.

    The engine's own reader decides first, so the tuning module and the engine
    cannot disagree about what a review looks like. Then ONE correction is
    applied, and only in one direction.

    MEASURED, not assumed (1,383 matched TRAIN items). The engine tagger's
    `task` verdicts are already good — 89.3% precision — but its `event`
    verdicts are where the errors live: 159 tasks were being called events, and
    that number had not moved all session. So the lexicon is consulted ONLY to
    talk it out of `event`, never into it:

        engine tagger alone            84.7%   task recall 70.7%
        lexicon overrides everywhere   82.4%   task recall 78.5%   (worse)
        lexicon only over `event`      87.5%   task recall 87.1%   <- this

    Overriding in both directions loses more events than it gains tasks, which
    is why the asymmetry is the whole point rather than an implementation
    detail. A parser was tried here first and was much worse (65.0%) — see
    `pos_sizing.py`; calendar commands are VERB-rooted imperatives, so a
    root-POS signal is anti-correlated with the answer.
    """
    from assistant.engine.segmentation.old_seg.segment import _enforce_pinned_kinds, _kind_of

    kind = _enforce_pinned_kinds(_kind_of(action), action)
    if kind not in ("event", "task", "review"):
        kind = "event"
    if kind == "event":
        return _lexicon_kind(action) or kind
    return kind


# ---------------------------------------------------------------------------
# the component
# ---------------------------------------------------------------------------

def fastseg(text: str) -> "list[dict]":
    """text -> [{"action", "time", "tag"}, ...]"""
    from assistant.intent.cleanup import strip_spoken_noise

    # A TRAILING CONFIRMATION is discourse about the command, not part of it
    # (Gil, 2026-09-09) -- "cross off take out the trash does that seem right".
    # Stripped HERE so it never enters the pipeline, and using the invariant's own
    # function so the guard and the segmenter cannot disagree about whether those
    # words are content. Safe before `cut` because the tail is at the end, so no
    # earlier offset moves.
    clean = _invariant.strip_discourse_tail(strip_spoken_noise(text or ""))
    pieces = cut(clean)
    return [{"action": a, "time": t, "tag": tag(a, t)}
            for a, t in assign_times(clean, pieces)]


if __name__ == "__main__":                          # pragma: no cover
    for probe in ("tomorrow gym at 7 and meeting at 11",
                  "gym session at 7, tomorrow meeting at 10",
                  "submit the grades and prepare the slides by friday",
                  "every friday buy groceries",
                  "buy 5 apples",
                  "meeting with Sam and Alex at 8",
                  "book the gym and remind me to buy milk"):
        print(f"\n{probe!r}")
        for it in fastseg(probe):
            print(f"   action={it['action']!r:38s} time={it['time']!r:22s} {it['tag']}")
