"""Is this fragment an ASK, or is it something the speaker said around one?

Every splitter in this project keeps rediscovering the same failure. Cut a
command at a plausible seam and some of the pieces are not requests at all —
they are the words a person wraps a request in:

    "wash the car, done and dusted"        → "wash done" · "wash dusted"
    "submit the report, wrapped up"        → "submit wrapped up"
    "pack and label the boxes"             → "pack" · "label the boxes"
    "mark X as done, the one from friday"  → … · "the one from friday"
    "should i mark X as done, does that seem right"  → … · "does that seem right"

Each of those second pieces becomes an item, gets a title invented for it, and
lands on the user's list. Segment learned this the hard way when its clause
splitter manufactured 139 items out of atomic commands; `list_split` has the
same hole, and it surfaced the moment the kind fix started routing many more
items through the task splitter.

It lives in `intent/` because the layering runs one way (engine → intent) and
BOTH readers need it: segment's clause tier and decompose's list tier. One
copy, so the two cannot drift — the same reason `cleanup`, `lead_time` and
`coordination` live here.

The rule underneath all of it: **an ask names something and asks for it.**
A fragment that only refers back, only closes the sentence, or only carries a
verb with nothing to act on is one ask still being spoken.
"""
from __future__ import annotations

import re

#: The speaker closing the sentence they just said — "done and dusted",
#: "wrapped up", "sorted", "that's it". Never a request.
_CLOSER_RE = re.compile(
    r"^(?:and\s+|,\s*)?(?:done(?:\s+and\s+dusted)?|dusted|wrapped\s+up|"
    r"sorted|finished|complete[d]?|all\s+set|that'?s\s+it|that'?s\s+all|"
    r"no\s+more|nothing\s+else)\s*[.!?]?$", re.I)

#: A tag question checking the request just made — "does that seem right",
#: "is that ok", "right?". It is conversation, not a second request.
_TAG_QUESTION_RE = re.compile(
    r"^(?:and\s+)?(?:does|do|is|are|isn'?t|doesn'?t|don'?t|can|could|would|"
    r"will|won'?t|right|ok(?:ay)?|correct|sound\s+good|make\s+sense)\b"
    r"[^.?!]{0,40}[.?!]?$", re.I)

#: A trailing clarifier pointing back at the thing already named — "the one
#: from friday", "not sure which one", "the second one".
_CLARIFIER_RE = re.compile(
    r"^(?:the\s+(?:one|first|second|third|last|other)\b"
    r"|not\s+sure\s+which"
    r"|i\s+think\s+so"
    r"|you\s+know\s+the\s+one)", re.I)

#: A bare verb with nothing to act on — what "pack and label the boxes"
#: leaves behind when the conjunction is treated as a separator.
_BARE_VERB_RE = re.compile(
    r"^(?:please\s+|just\s+|do\s+)?[a-z]+(?:\s+(?:up|out|off|in|on|over|"
    r"back|through|away))?\s*[.!?]?$", re.I)

#: Words that cannot BE the thing asked for, only describe when or where.
_FUNCTIONAL = frozenset(
    "the a an my your our this that these those it them today tomorrow "
    "tonight yesterday now later soon then there here due by at on in for "
    "from to of and or but so please just do done all any some more".split())


def is_an_ask(text: str, verbs: "frozenset[str] | None" = None) -> bool:
    """Does this fragment ask for something?

    `verbs` is the caller's own action-verb inventory when it has one
    (`list_split.ACTION_VERBS`); it is used only to recognise a BARE verb —
    a piece that is nothing but the verb the splitter handed down.

    Deliberately generous: it answers False only for shapes that are clearly
    not requests, because refusing a real ask loses the user's words while
    accepting a stray one merely leaves a merged item that two later stages
    can still recover.
    """
    t = (text or "").strip(" ,;.")
    if not t:
        return False
    if _CLOSER_RE.match(t) or _TAG_QUESTION_RE.match(t) or _CLARIFIER_RE.match(t):
        return False

    words = t.split()
    # The splitter HANDS THE VERB DOWN, which hides the closer behind it:
    # "wash the car, done and dusted" is cut into "wash the car" and "done
    # and dusted", and the second piece then becomes "wash done". So the
    # remainder after a handed-down verb has to be tested too, or every
    # closer survives its own guard.
    if verbs and len(words) > 1:
        head = words[0].lower().strip(".,;:")
        if head in verbs:
            rest = " ".join(words[1:])
            # a particle belongs to the verb, not to the remainder
            if len(words) > 2 and words[1].lower() in (
                    "up", "out", "off", "in", "on", "over", "back", "away"):
                rest = " ".join(words[2:])
            if (_CLOSER_RE.match(rest) or _TAG_QUESTION_RE.match(rest)
                    or _CLARIFIER_RE.match(rest)):
                return False

    # A bare verb, or a verb plus its particle, with no object.
    if len(words) <= 2 and _BARE_VERB_RE.match(t):
        head = words[0].lower()
        if verbs and head in verbs:
            return False
        if len(words) == 1:
            return False

    # Something has to be named: a word that is not purely functional.
    return any(w.strip(".,;:'\"").lower() not in _FUNCTIONAL for w in words)


def every_part_is_an_ask(parts: "list[str]",
                         verbs: "frozenset[str] | None" = None) -> bool:
    """True when a proposed split is safe to take.

    Callers reject the WHOLE split rather than dropping the offending part:
    those words still belong to the command, and a stage that can weigh them
    (or the model) gets a second chance at it. Dropping them is the one
    outcome that cannot be recovered.
    """
    return bool(parts) and all(is_an_ask(p, verbs) for p in parts)
