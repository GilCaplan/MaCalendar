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


def has_clause_coordination(text: str) -> bool:
    """True when the parse shows two coordinated CLAUSES (two asks).

    NP-coordination ("Tal and Sam", "chicken and rice") returns False — those
    joins are part of one ask. Imperatives are the common shape here, and
    spaCy tags an imperative's verb as the sentence ROOT with the second
    command attached as its VERB conjunct ("book the gym and remind me…" —
    remind is conj of book, both VERB). STT text is lowercase and unpunctuated,
    which spaCy's small model handles well enough for POS at this coarseness;
    the NOUN/PROPN check is the guard against splitting names.
    """
    from assistant.intent import rule_parser as _rp

    _rp._ensure_nlp()
    nlp = _rp._NLP
    if nlp is None or not text or " " not in text:
        return False
    try:
        doc = nlp(text)
    except Exception:
        return False
    OWN_ARG = ("dobj", "obj", "ccomp", "xcomp", "dative", "attr", "oprd",
               "npadvmod", "appos", "compound", "prep", "prt", "advcl")
    for tok in doc:
        if tok.dep_ != "conj":
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
        head_has_own = any(c.dep_ in OWN_ARG for c in tok.head.children
                           if c is not tok)
        if conj_has_own and head_has_own:
            return True
    return False


def _is_command_verb(tok) -> bool:
    """Is this token one of the parser's own routing verbs?"""
    from assistant.intent.rule_parser import INTENT_MAP
    word = (tok.lemma_ or tok.text).lower()
    return any(word == verb for verb, _ in INTENT_MAP)
