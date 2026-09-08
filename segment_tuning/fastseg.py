"""FastSeg — the deterministic half of the segment component.

    text  ->  [(action, time, tag), ...]

Three phases, in this order, and the order is measured rather than chosen:
DialogUSR's ablation (Findings of EMNLP 2022) reports Split -> (Delete +
Complete) beating the reverse by 9 exact-match points, which is exactly the
cut-then-assign shape below.

  1  CUT          delimiters, then the clause parse, looped to a fixed point
  2  ASSIGN TIME  reads the pieces AND the original string together
  3  TAG          event | task | review

It lives in `segment_tuning/` rather than in `assistant/engine/` on purpose:
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

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

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
    (r"\ba\s+week\s+from\s+(?:today|tomorrow|now)\b", "date"),
    (r"\b(?:this|next)\s+(?:morning|afternoon|evening)\b", "date"),
    (r"\b(?:in\s+the\s+)?(?:morning|afternoon|evening)\b", "date"),
    (r"\bnew\s+year'?s\s+eve\b", "date"),
    (r"\bchristmas(?:\s+day)?\b", "date"),
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
    """
    refs: list[TimeRef] = []
    taken = [False] * (len(text) + 1)
    for rx, kind in _COMPILED:                     # already longest-first
        for m in rx.finditer(text):
            if any(taken[m.start():m.end()]):
                continue                           # inside something already taken
            # Trim trailing whitespace the pattern swallowed. "at 7 " ended one
            # character past its own piece, so the reference fell OUTSIDE the
            # piece that owned it and was treated as an edge — which silently
            # distributed a clock time across the whole command.
            s, e = m.start(), m.end()
            while e > s and text[e - 1].isspace():
                e -= 1
            refs.append(TimeRef(s, e, text[s:e].strip(), kind))
            for i in range(s, e):
                taken[i] = True
    refs.sort(key=lambda r: r.start)
    return refs


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
            return [piece]
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
    edge: "list[TimeRef]" = []
    last = len(pieces) - 1
    for ref in refs:
        for i, (s, e) in enumerate(spans):
            if s <= ref.start and ref.end <= e:
                owned[i].append(ref)
                # EDGE means at the boundary of the whole COMMAND, not outside
                # every piece — a trailing reference is textually inside the
                # last piece. So: opening the first piece, or closing the last.
                opens_command = i == 0 and ref.start <= s + 1
                closes_command = i == last and ref.end >= e - 1
                if len(pieces) > 1 and (opens_command or closes_command):
                    edge.append(ref)
                break
        else:
            edge.append(ref)

    out: "list[tuple[str, str]]" = []
    for i, piece in enumerate(pieces):
        mine = list(owned[i])
        # An edge reference fills a SLOT the piece left empty, not merely a
        # piece that named nothing at all. "tomorrow gym at 7 and meeting at
        # 11": the second piece has a clock but no DATE, so the leading
        # "tomorrow" still reaches it. Distributing only to time-less pieces
        # would leave that meeting today.
        have = {_slot(r) for r in mine}
        for r in edge:
            if _slot(r) not in have and r not in mine:
                mine.append(r)
                have.add(_slot(r))
        time_str = " ".join(r.text for r in sorted(mine, key=lambda r: r.start))
        action = _strip_spans(piece, [(r.start - spans[i][0], r.end - spans[i][0])
                                      for r in owned[i]])
        out.append((action, time_str or "today"))
    return out


def _slot(ref: "TimeRef") -> str:
    """Which slot a reference fills. A day and a clock time are different
    slots, so one does not block the other from being distributed."""
    return "clock" if ref.kind == "clock" else "day"


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

def tag(action: str, time_str: str) -> str:
    """event | task | review, reusing segment's own readers so the tuning
    module and the engine cannot disagree about what a review looks like."""
    from assistant.engine.segment import _enforce_pinned_kinds, _kind_of

    kind = _enforce_pinned_kinds(_kind_of(action), action)
    return kind if kind in ("event", "task", "review") else "event"


# ---------------------------------------------------------------------------
# the component
# ---------------------------------------------------------------------------

def fastseg(text: str) -> "list[dict]":
    """text -> [{"action", "time", "tag"}, ...]"""
    from assistant.intent.cleanup import strip_spoken_noise

    clean = strip_spoken_noise(text or "")
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
