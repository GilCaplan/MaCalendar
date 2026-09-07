"""Spoken lead-times — "remind me 30 minutes before", "with a 15 minute
reminder" — pulled out of a command into a number of minutes.

Lives in `intent/` because BOTH readers need it and the layering runs one
way (engine → intent): the deep track's decompose stage strips it per item,
and FastRule strips it during normalization. It used to live only in
decompose, which is why FastRule failed 100% of the lead-time rows in the
7,200 dataset's train half — the clause ate the title and the command
routed as a bare "remind me" todo with nothing in it.

Stripping it early also protects a later rule: validate's until/through
logic would read the bare surviving "before" as a recurrence-end marker.
"""
from __future__ import annotations

import re

#: "…and give me a heads-up half an hour before" / "with a 15 minute
#: reminder" / "remind me 2 hours before/ahead" / "remind me 5 minutes
#: before about X" (the `about` form is what FastRule sees most).
CLAUSE = re.compile(
    r"[,;]?\s*(?:and\s+)?(?:(?:please\s+)?(?:give me|send me|i want|i'd like)\s+"
    r"(?:a\s+)?(?:heads[- ]?up|reminder|alert)\s+|remind me\s+|alert me\s+|"
    r"with\s+(?:a\s+)?)"
    r"(?:of it\s+|about it\s+)?"
    r"(?P<n>\d+|a|an|one|two|five|ten|fifteen|twenty|thirty|half an?|quarter of an?)?\s*"
    r"(?P<u>minutes?|mins?|hours?|hrs?)\s*"
    r"(?:(?:reminder|heads[- ]?up|alert)"
    r"(?:\s+(?:before|ahead(?:\s+of\s+(?:time|it))?|earlier|in advance))?"
    r"|(?:before|ahead(?:\s+of\s+(?:time|it))?|earlier|in advance))\b\.?",
    re.I)

_NUM_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "five": 5, "ten": 10,
              "fifteen": 15, "twenty": 20, "thirty": 30,
              "half a": 30, "half an": 30, "quarter of a": 15, "quarter of an": 15}

#: what's left after the clause is cut, when the speaker said "…before ABOUT x"
_LEADING_ABOUT = re.compile(r"^\s*(?:about|of|for)\s+", re.I)
_COURTESY = re.compile(r"^(?:please|kindly|can you|could you|hey)\s+", re.I)
#: does the remainder still open with something the router can key on?
_HAS_LEADING_VERB = re.compile(
    r"^\s*(?:add|book|schedule|create|put|set|plan|make|remind|buy|get|pick|"
    r"call|email|remove|delete|cancel|drop|clear|move|reschedule|update|"
    r"rename|change|mark|complete|finish|check|what|when|show|list)\b", re.I)


def split(text: str, restore_verb: bool = False) -> "tuple[str, int | None]":
    """(text without the lead-time clause, minutes) — or (text, None).

    Returns the ORIGINAL text unchanged when the clause IS the whole command
    ("remind me in 5 minutes" is a request, not a lead time on something
    else), so a caller can always use the returned text safely.

    `restore_verb` is FastRule's need, not decompose's: FastRule routes on a
    verb, so a remainder like "product demo tonight" has nothing to key on
    and gets the pinned convention's verb restored. Decompose wants the
    item's own words untouched — its kind was already decided upstream —
    so it leaves this off.
    """
    m = CLAUSE.search(text)
    if not m:
        return text, None
    raw = (m.group("n") or "one").lower().strip()
    unit = (m.group("u") or "").lower()
    if raw in _NUM_WORDS:
        n = _NUM_WORDS[raw]
        if raw.startswith(("half", "quarter")) and unit.startswith(("hour", "hr")):
            pass                                  # already minutes
        elif unit.startswith(("hour", "hr")):
            n *= 60
    else:
        try:
            n = int(raw)
        except ValueError:
            return text, None
        if unit.startswith(("hour", "hr")):
            n *= 60
    rest = (text[:m.start()] + " " + text[m.end():]).strip(" ,;")
    rest = _LEADING_ABOUT.sub("", rest).strip()
    rest = _COURTESY.sub("", rest).strip()
    if len(rest.split()) < 2:
        return text, None                          # the clause WAS the command
    # "remind me 15 minutes before about X" leaves a bare noun phrase with no
    # verb to route on. The pinned project convention is that a reminder
    # ABOUT an occasion is a CALENDAR entry, so say so explicitly rather than
    # leaving the router nothing to work with.
    if restore_verb and not _HAS_LEADING_VERB.match(rest):
        rest = "book " + rest
    return rest, max(1, min(1440, n))
