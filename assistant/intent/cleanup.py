"""Spoken-noise cleanup — the words that carry no request.

Gil's architecture call (2026-09-07): the person-specific work belongs in
the INITIAL CLEANUP step — the personal vocabulary repairing what was
misheard, and the "mhmm"/"umm" filler coming off — so that everything
downstream is generic and works for anybody. Nothing after this stage
should need to know how a particular person talks.

It lives in `intent/` because BOTH readers need it and the layering runs one
way (engine → intent): the deep track's transcript stage cleans the whole
command once, and FastRule cleans again when it is handed raw text directly
(the sandbox, and any caller that skips the pipeline). Cleaning twice is
harmless — these patterns are idempotent — and the alternative, one copy per
caller, is how the lead-time reader ended up fixing only half the system.

Why it matters, measured: filler stripping used to live inside FastRule's
own normalisation, so the DEEP track never got it. Real-usage review showed
the LLM path failing 5 of 5 on rambling dictation that opened with exactly
these words.
"""
from __future__ import annotations

import re

#: Openers that announce speech rather than a request: "um", "so", "alright",
#: "okay so". Only stripped from the FRONT — "ok" inside a sentence can be
#: meaningful ("mark the ok as done").
_OPENERS = re.compile(
    r"^(?:(?:um+|uh+|erm+|mm+|mhm+|hmm+|so|well|ok(?:ay)?|alright|"
    r"right|hey|yeah|yep|look|listen|actually|basically)[,\s]+)+",
    re.I)

#: Courtesy wrappers that hide the command from anything anchored at ^.
_COURTESY = re.compile(
    r"^(?:can|could|would|will)\s+you\s+(?:please\s+)?"
    r"|^(?:please|kindly)\s+",
    re.I)

#: Mid-sentence self-corrections: "buy milk, I mean, buy bread". The speaker
#: replaced what came before, so the marker and what precedes it in that
#: clause are noise. Conservative: only after a comma, so it cannot eat a
#: sentence that merely contains the words.
_SELF_CORRECTION = re.compile(
    r",\s*(?:i mean|sorry|no wait|scratch that|rather)\b[,\s]*", re.I)

#: Trailing verbal shrug: "…tomorrow or something", "…at 6 or whatever".
_TRAILING_HEDGE = re.compile(
    r"\s+(?:or\s+(?:something|whatever|so)|you know|i guess)\s*[.!?]?$", re.I)


def strip_spoken_noise(text: str, drop_courtesy: bool = True) -> str:
    """Remove the words that carry no request. Idempotent and lossless in
    meaning: it never touches titles, dates, times or targets.

    `drop_courtesy` is False for readers that judge politeness themselves —
    FastRule's interrogative gate reads the RAW text to tell a question from
    a polite imperative, so the caller decides.
    """
    if not text:
        return text
    out = _OPENERS.sub("", text.strip())
    if drop_courtesy:
        out = _COURTESY.sub("", out)
    out = _TRAILING_HEDGE.sub("", out)
    # a self-correction replaces the clause before it
    m = _SELF_CORRECTION.search(out)
    if m:
        head, tail = out[:m.start()], out[m.end():]
        if len(tail.split()) >= 2:          # only if something survives
            # keep any leading imperative the speaker did not retract
            lead = re.match(r"^\s*(\w+)\s", head)
            out = tail if not lead else tail
    return out.strip(" ,;")
