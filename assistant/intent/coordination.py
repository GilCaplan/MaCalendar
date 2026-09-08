"""Coordination-type check — is this "and" joining two THINGS or two ASKS?

The multi-intent literature's core finding (F5 / research sweep, see
DOCUMENTATION/experiments/FASTRULE_RESEARCH.md idea 1): splitting on the
position of conjunctions alone cannot tell "meeting with Tal and Sam"
(NP-coordination — one event, two guests) from "book the gym and remind me
to buy milk" (clause-coordination — two asks). The dependency parse can:
spaCy marks the second conjunct with dep_ == "conj", and the POS of what got
coordinated says which kind of join it is — a VERB conjunct is a second
clause, a NOUN/PROPN conjunct is a longer noun phrase.

One function, three intended call sites: FastRule's strong-compound gate
(wired in this batch), the segment stage's deterministic pre-split and the
compound-hint filter (later batches). Deterministic, ~ms on command-length
text, and honest about failure: if spaCy is unavailable or the parse is
degenerate, it reports NO clause-coordination — the caller's regexes remain
the floor, so a parse outage can never over-abstain.
"""

from __future__ import annotations

import functools
import re

#: One ASK-JOINER between two asks; N joiners announce N+1 asks. ", and" and
#: "and then" are ONE joiner, not two — the alternation is ordered longest-
#: first so the compound forms win, and a trailing comma is swallowed. A
#: comma inside a single ask ("friday, march 5th") over-counts, which is the
#: safe direction for both consumers: FastRule's `_parse_covers_the_compound`
#: then prefers to defer, and the `joiner-mid` feature then prefers "middle".
ASK_JOINER_RE = re.compile(
    r"(?:"
    r",?\s*\band\s+(?:then|also)\b"
    r"|,\s*(?:then|also|plus)\b"
    r"|[.;!?]\s+(?:also|then|plus|and)\b"
    r"|\s[—–]\s*and\b"
    r"|,?\s*\band\b"
    r"|[;,]"
    r"),?",
    re.I)


#: A `conj` dependency needs a coordinator, so a sentence with none cannot
#: have clause coordination and does not need to be parsed at all. 57% of
#: the two datasets' 9,899 utterances match nothing here, and the parse is
#: ~9 ms — the difference between the check being free on a simple command
#: and being the fast track's largest single cost. Deliberately WIDER than
#: `ASK_JOINER_RE` ("or", "but", "plus", "as well as"): a cheap pre-filter
#: must never be the thing that decides, and this one is verified lossless
#: over both datasets in full.
#: "then"/"after that" are SEQUENCERS, not coordinators, so they were absent
#: while this gate only fronted a `conj` search. They must be here now that a
#: second imperative joined by one is a candidate — the pre-filter is only
#: allowed to be cheap, never to be the thing that decides, and a joiner it
#: does not list is a compound the splitter can never see.
_COORDINATOR_RE = re.compile(
    r"\b(?:and|or|but|plus|then|also|as well as|along with|after that)\b|[,;]",
    re.I)


@functools.lru_cache(maxsize=256)
def parsed(text: str):
    """The spaCy doc for `text`, memoised.

    Two callers now want the same parse of the same utterance in the same
    ~50 ms: this check (layer 0's rules tier) and `AtomicityFeatures`'
    clause-coord signal (its model tier, F17). Without the cache the parse
    is paid twice per command. Returns None — never raises — when spaCy is
    unavailable or the parse fails, so every caller degrades to "saw
    nothing" rather than to an exception.
    """
    from assistant.intent import rule_parser as _rp

    _rp._ensure_nlp()
    nlp = _rp._NLP
    if nlp is None or not text or " " not in text:
        return None
    try:
        return nlp(text)
    except Exception:
        return None


class Boundary:
    """Where one ask ends and the next begins, as character offsets.

    `text[:ends]` is the first ask, `text[begins:]` the second; the span
    between them is the coordinator ("and", ", and then", ";") which belongs
    to neither. Keeping both offsets rather than one split point is what lets
    a caller drop the joiner without re-guessing how many words it was.
    """

    __slots__ = ("ends", "begins", "joiner")

    def __init__(self, ends: int, begins: int, joiner: str):
        self.ends = ends            # first ask ends here (exclusive)
        self.begins = begins        # second ask begins here
        self.joiner = joiner        # the words cut out, for the trace

    def __repr__(self) -> str:      # pragma: no cover - debugging aid
        return f"Boundary({self.ends}, {self.begins}, {self.joiner!r})"


#: Words that join two asks and belong to neither of them. Used only to widen
#: the cut once the PARSE has already decided there is a boundary here — it
#: never decides on its own.
_COORD_WORDS = frozenset({"and", "then", "also", "plus", "or", "but"})

#: A split is only worth making if both halves are substantive. One word on
#: either side is a parse artifact, not an ask — and an empty half would hand
#: the next stage a blank item to invent a title for.
_MIN_WORDS_PER_ASK = 2


def has_clause_coordination(text: str) -> bool:
    """True when the parse shows two coordinated CLAUSES (two asks).

    NP-coordination ("Tal and Sam", "chicken and rice") returns False — those
    joins are part of one ask. See `clause_boundaries` for the reasoning; this
    is the same judgement reported as a yes/no for callers that only gate on it.
    """
    return bool(clause_boundaries(text))


def clause_boundaries(text: str) -> "list[Boundary]":
    """Every place two coordinated CLAUSES meet, in order.

    This is the same judgement `has_clause_coordination` reports, but keeping
    the POSITION it found instead of discarding it. The check already had to
    locate the second clause to decide the question; throwing that away meant
    the project could DETECT compounds well (87.9% recall in the atomicity
    model) and still never SPLIT one — segment's deterministic tier looked for
    brackets and separators, which the phone inserts and speech never does, so
    it split nothing in 4,920 rows.

    Imperatives are the common shape, and spaCy tags an imperative's verb as
    the sentence ROOT with the second command attached as its VERB conjunct
    ("book the gym and remind me…" — remind is conj of book, both VERB). STT
    text is lowercase and unpunctuated, which spaCy's small model handles well
    enough for POS at this coarseness; the NOUN/PROPN check is the guard
    against splitting names.

    Under-split bias is preserved: a boundary is reported only for the
    signature below, and only when both halves survive `_MIN_WORDS_PER_ASK` —
    a wrongly merged item gets two more chances downstream, a wrongly split
    one becomes two garbage items immediately.
    """
    if not _COORDINATOR_RE.search(text):
        return []                    # no coordinator ⇒ no `conj` ⇒ nothing to see
    doc = parsed(text)
    if doc is None:
        return []
    OWN_ARG = ("dobj", "obj", "ccomp", "xcomp", "dative", "attr", "oprd",
               "npadvmod", "appos", "compound", "prep", "prt", "advcl")
    found: list[Boundary] = []
    for tok in doc:
        # "dep" is spaCy's I-don't-know label, and it is where a second
        # imperative lands when the joiner is a sequencer rather than a
        # coordinator — "call mom THEN pick up the dry cleaning" tags `pick`
        # dep, not conj, so the conj-only loop never saw it. It is admitted
        # only as a VERB, and everything below still has to hold.
        if tok.dep_ != "conj" and not (tok.dep_ == "dep" and tok.pos_ == "VERB"):
            continue
        # The head's POS is UNRELIABLE on lowercase STT imperatives — spaCy
        # tags "book the gym…" ROOT as PROPN and "schedule lunch…" as a NOUN
        # compound — so the head's verb-ness must not be required. The
        # reliable second-ask signature (measured on the canonical cases) is:
        #   • the conjunct IS a verb, AND carries its own argument
        #     ("remind ME", "delete THE GYM SESSION"), AND
        #   • the head carries its own content too ("book THE GYM",
        #     "lunch WITH MARK") — a bare head sharing the conjunct's object
        #     ("wash and fold the laundry") is a serial verb, one ask.
        if tok.pos_ not in ("VERB", "AUX") and not _is_command_verb(tok):
            # the conjunct side suffers the same lowercase mis-tag ("…and
            # book a haircut" tags book NOUN): the domain's own verb
            # inventory (INTENT_MAP) resolves what POS cannot — but only a
            # conjunct WITH its own arguments below counts, so a bare name
            # that collides with a verb ("…with Tal and Mark") stays safe.
            continue
        # F15 (corrected): a SERIAL VERB shares the head's object — "wash
        # and fold THE LAUNDRY", "clean and organize THE GARAGE" — one ask.
        # The tell is positional, not the mere absence of an object: the
        # conjunct has no object of its own AND the head's object sits
        # AFTER the conjunct, i.e. both verbs govern the same later noun.
        # (The first cut just required a dobj on the conjunct, which also
        # blinded the check to real compounds — violations rose 100→141.)
        conj_obj = [c for c in tok.children if c.dep_ in ("dobj", "obj", "ccomp", "xcomp")]
        if not conj_obj:
            head_obj = [c for c in tok.head.children
                        if c.dep_ in ("dobj", "obj") and c.i > tok.i]
            if head_obj:
                continue          # shared object → serial verb → one ask
        conj_has_own = any(c.dep_ in OWN_ARG for c in tok.children)
        # When the head is a DATE rather than a verb, spaCy has mis-attached
        # the second ask's object to the first clause — "…on friday and book
        # a haircut" hangs `book` off `friday` with no children at all, so
        # the argument test cannot see the object that is plainly there. A
        # determiner immediately after a command verb is that object opening,
        # and it is what separates "…and BOOK A haircut" from the name
        # collision "…with tal and MARK tomorrow", where no determiner follows.
        if not conj_has_own and _is_command_verb(tok) and tok.i + 1 < len(doc):
            nxt = doc[tok.i + 1]
            # …but a determiner opening a DATE is not an object — "with Reese
            # and Drew THIS coming saturday" is an attendee list whose second
            # name happens to be a past-tense verb, and "this saturday" is
            # when the one event happens, not what a second ask acts on.
            conj_has_own = (nxt.pos_ in ("DET", "PRON")
                            and not _opens_a_date(doc, nxt.i))
        head_has_own = any(c.dep_ in OWN_ARG for c in tok.head.children
                           if c is not tok)
        if not head_has_own and tok.head.dep_ != "ROOT":
            # The conjunct hangs off a token buried INSIDE the first clause —
            # typically its date ("…on friday and book a haircut" makes
            # `friday` the head, whose only children are the coordinator and
            # the conjunct). The first ask's content sits upstream of that
            # head rather than under it, so the argument test cannot see it.
            # The serial-verb case this guard defends against ("wash and fold
            # the laundry") only arises when both verbs hang off the ROOT.
            head_has_own = True
        if conj_has_own and head_has_own:
            b = _boundary_at(doc, tok, text)
            if b is not None:
                found.append(b)
    return found


def split_clauses(text: str) -> "list[str]":
    """`text` cut into one string per ask — or `[text]` when it is one ask.

    The convenience segment wants: a caller that only needs the pieces should
    not have to know about offsets. Never returns an empty part, and never
    returns parts that lose words — the only thing dropped is the joiner.
    """
    bounds = clause_boundaries(text)
    if not bounds:
        return [text]
    parts, cursor = [], 0
    for b in bounds:
        piece = text[cursor:b.ends].strip(" ,;")
        if piece:
            parts.append(piece)
        cursor = b.begins
    tail = text[cursor:].strip(" ,;")
    if tail:
        parts.append(tail)
    return parts or [text]


def _boundary_at(doc, tok, text: str) -> "Boundary | None":
    """Character offsets around the coordinator that introduces `tok`.

    The second ask starts at the leftmost token of the conjunct's subtree
    (clamped to after the head, since a degenerate parse can hang an earlier
    token off it), and the coordinator is the run of joiner words and
    punctuation immediately before that. Both halves must be substantive or
    there is no boundary worth reporting.
    """
    left = min((t.i for t in tok.subtree), default=tok.i)
    left = max(left, tok.head.i + 1)
    if left >= len(doc) or left == 0:
        return None
    # The joiner is sometimes INSIDE the conjunct's subtree rather than before
    # it ("coffee with mark and then head to the office" hangs `then` under
    # `head`), which would leave the second ask opening with the word that
    # joined it. Walk the tail forward past any joiner run first.
    while (left + 1 < len(doc) and left <= tok.i
           and (doc[left].dep_ == "cc" or doc[left].lower_ in _COORD_WORDS
                or doc[left].is_punct)):
        left += 1
    # walk back over the joiner run: "and", ", and then", ";"
    first = left
    i = left - 1
    while i > tok.head.i and (doc[i].dep_ == "cc"
                              or doc[i].lower_ in _COORD_WORDS
                              or doc[i].is_punct):
        first = i
        i -= 1
    if first == 0 or first == left:
        # Nothing joined these two — no "and", no "then", not even a comma.
        # Speech always marks the seam between two asks, so a boundary with
        # no joiner is a cut through the middle of one ask, not between two.
        return None
    prev = doc[first - 1]
    ends = prev.idx + len(prev.text)
    begins = doc[left].idx
    if begins <= ends:
        return None
    head, tail = text[:ends], text[begins:]
    if (len(head.split()) < _MIN_WORDS_PER_ASK
            or len(tail.split()) < _MIN_WORDS_PER_ASK):
        return None                  # one-word half ⇒ parse artifact, not an ask
    return Boundary(ends, begins, text[ends:begins].strip())


#: Words that make a determiner phrase a DATE rather than an object —
#: "this saturday", "the 3rd", "that evening". Checked a few tokens past the
#: determiner because "this COMING saturday" puts a modifier in between.
_TEMPORAL_WORDS = frozenset(
    "monday tuesday wednesday thursday friday saturday sunday morning "
    "afternoon evening night noon midnight today tomorrow tonight yesterday "
    "week weekend month year day january february march april may june july "
    "august september october november december".split())


def _opens_a_date(doc, i: int) -> bool:
    """Does the phrase starting at token `i` name a time rather than a thing?

    Decided by the phrase's HEAD NOUN, not by any temporal word nearby: "a
    haircut for tuesday" is an object that happens to carry a date, while
    "this coming saturday" is the date itself. Scanning a fixed window instead
    conflates the two and blocks a real split.
    """
    for tok in doc[i:i + 5]:
        if tok.pos_ in ("NOUN", "PROPN", "NUM"):
            word = (tok.lemma_ or tok.text).lower()
            return word in _TEMPORAL_WORDS or bool(
                tok.like_num and len(tok.text) <= 4)   # "the 3rd"
    return False


def _is_command_verb(tok) -> bool:
    """Is this token one of the parser's own routing verbs?"""
    from assistant.intent.rule_parser import INTENT_MAP
    word = (tok.lemma_ or tok.text).lower()
    return any(word == verb for verb, _ in INTENT_MAP)
