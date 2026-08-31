"""Splitting one spoken phrase into the several things it actually asks for.

"buy chicken and rice" is two tasks, not one called "buy chicken and rice" —
and certainly not one called "buy groceries". The hard part is the conjunctions
that *aren't* separators: "buy a gift for mom and dad" is one errand, and "fish
and chips" is one thing to buy. So the rules here are:

  * commas and semicolons always separate;
  * "and" separates unless a preposition already opened a phrase it could be
    joining, or the pair is a known idiom;
  * the leading verb is handed down to conjuncts that have none, so the second
    task is "buy rice" rather than "rice".

Pure string work, no spaCy — the rule parser (`assistant/intent/rule_parser.py`)
and the todo actions both use it.
"""

from __future__ import annotations

import re
from typing import Container

# Verbs that can head a task title. Used both to recognise that a conjunct
# already carries its own verb ("wash the dishes and call mom") and to hand the
# shared one down to conjuncts that don't ("buy chicken and rice").
ACTION_VERBS = frozenset({
    "buy", "get", "grab", "order", "pick", "collect", "call", "phone", "email",
    "text", "message", "write", "send", "reply", "answer", "book", "schedule",
    "pay", "renew", "cancel", "return", "print", "submit", "finish", "start",
    "read", "watch", "review", "check", "clean", "wash", "cook", "bake",
    "prepare", "pack", "fix", "repair", "install", "update", "download",
    "upload", "backup", "charge", "water", "feed", "take", "bring", "drop",
    "sign", "fill", "confirm", "ask", "tell", "remind", "visit", "go", "make",
})
# Multi-word verbs: the particle belongs to the verb, so the whole thing is what
# gets handed down ("pick up the laundry and the dry cleaning").
ACTION_PHRASES = frozenset({
    "pick up", "drop off", "take out", "sign up", "check out", "fill out",
    "print out", "set up", "clean up", "follow up", "call up", "bring back",
})

# A preposition before the "and" means the conjunction is joining that
# preposition's object, not two tasks: "buy a gift for mom and dad" is one
# errand, not an errand called "buy dad".
_BLOCKING_PREPS = re.compile(
    r"\b(?:for|to|with|from|about|of|into|onto|toward|towards)\b", re.IGNORECASE)

# Pairs where the "and" is part of the name of one thing.
_AND_IDIOMS = frozenset({
    "fish and chips", "mac and cheese", "macaroni and cheese",
    "peanut butter and jelly", "salt and pepper", "cream and sugar",
    "milk and honey", "bed and breakfast", "rock and roll", "pen and paper",
})

_DANGLING_CONJ = re.compile(r"^(?:and|or|then|plus)\s+|\s+(?:and|or|then|plus)$", re.IGNORECASE)


def lead_verb(part: str) -> str | None:
    """The action verb heading a title, particle included, or None."""
    words = part.split()
    if not words:
        return None
    if len(words) > 1 and f"{words[0].lower()} {words[1].lower()}" in ACTION_PHRASES:
        return f"{words[0]} {words[1]}"
    if words[0].lower() in ACTION_VERBS:
        return words[0]
    return None


def split_on_and(segment: str) -> list[str]:
    """Split a comma-free segment at task-separating 'and's only."""
    out: list[str] = []
    rest = segment
    while True:
        m = re.search(r"\s+and\s+(?=\w)", rest)
        if not m:
            break
        head, tail = rest[:m.start()], rest[m.end():]
        pair = " ".join(head.split()[-1:] + ["and"] + tail.split()[:2]).lower()
        if (_BLOCKING_PREPS.search(head)
                or any(pair.startswith(i) or i.startswith(pair) for i in _AND_IDIOMS)):
            break            # the 'and' is internal — keep the segment whole
        out.append(head.strip(" ."))
        rest = tail
    out.append(rest.strip(" ."))
    return [p for p in out if p]


def distribute_lead_verb(parts: list[str]) -> list[str]:
    """'buy chicken' + 'rice' → 'buy chicken' + 'buy rice'.

    Without this, "buy chicken and rice" produced a task literally called
    "rice", which reads like a note to self rather than a thing to do.
    """
    if len(parts) < 2:
        return parts
    verb = lead_verb(parts[0])
    if not verb or len(parts[0].split()) <= len(verb.split()):
        return parts        # nothing to share, or the first part is only the verb
    out = [parts[0]]
    for p in parts[1:]:
        out.append(p if lead_verb(p) else f"{verb} {p}")
    return out


def split_items(body: str, drop: Container[str] = frozenset()) -> list[str]:
    """One phrase → the list of things it names, verb shared out.

    `drop` is a set of lower-case titles to discard before the verb is shared
    (the rule parser drops bare pronouns that its dependency heuristics leak).
    """
    parts: list[str] = []
    for segment in re.split(r"\s*[,;]\s*", body or ""):
        segment = segment.strip(" .")
        if segment:
            parts.extend(split_on_and(segment))
    # Phase-1 span splitting cuts before the conjunction, so a part can end on a
    # dangling "and" ("remind me to wash the dishes and | call the dentist").
    parts = [_DANGLING_CONJ.sub("", p.strip(" .,")).strip(" .,") for p in parts]
    parts = [p for p in parts if p and p.lower() not in drop]
    return distribute_lead_verb(parts)
