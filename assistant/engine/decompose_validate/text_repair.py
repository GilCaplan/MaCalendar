"""Repair the WORDS of an item before anything reads them.

Format hygiene, not value resolution: doubled whitespace Whisper leaves around
cut words, brackets, and dictation quotes — `"add 'christmas' to calendar"` died
on every attempt because the quotes broke intent validation, and quotes around a
single word carry no meaning the words do not.

RETIRED FROM `validate.py` (Gil, 2026-09-08) with the rest of it, but this half
was never replaced — `resolve.py` and `checks.py` deal in values, and something
still has to tidy the text. Dropping it silently regressed three tests, which is
how it was noticed; see `retired/decompose-validate-v1/README.md`.
"""
from __future__ import annotations

import re

from assistant.engine.state import EngineState

_REPAIR_SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
}


_REPAIR_SYSTEM = """A speech transcriber garbled part of a voice command to a \
calendar assistant. Clean it MINIMALLY: remove cut-off fragments and \
stutters, fix obvious transcription grammar. Never add words, names, dates, \
times or meaning that are not already there — if unsure, leave it exactly as \
is. Return JSON: {"text": ...}"""

# Signs of a genuinely mangled transcript: a cut-off fragment ("I need a b-"),
# a stuttered word ("the the meeting"), stray non-word runs. Ordinary casual
# grammar is NOT mangled and must not be "improved".


# Signs of a genuinely mangled transcript: a cut-off fragment ("I need a b-"),
# a stuttered word ("the the meeting"), stray non-word runs. Ordinary casual
# grammar is NOT mangled and must not be "improved".
_MANGLED_RE = re.compile(r"\b\w+-(?:\s|$)|\b(\w+)\s+\1\b", re.IGNORECASE)


def _repair_text(item, state: EngineState, cfg) -> None:
    """rule: text_repair — deterministic cleanup first, one LLM rewrite only
    when the words are clearly damaged."""
    # Stutters collapse for free: "the the meeting" → "the meeting".
    dedoubled = re.sub(r"\b(\w+)(\s+\1\b)+", r"\1", item.text, flags=re.IGNORECASE)
    if dedoubled != item.text:
        state.add_fix("validate", "text_repair", item.text, dedoubled, note="stutter")
        item.text = dedoubled
    if not _MANGLED_RE.search(item.text):
        return
    from assistant.engine import llm as _llm
    try:
        out, ms = _llm.call_json(cfg, _REPAIR_SYSTEM,
                                 f"The garbled command: {item.text}", _REPAIR_SCHEMA)
        state.llm_ms += ms
    except Exception:
        return
    fixed = str(out.get("text", "")).strip()
    # A rewrite that grew the text invented content; one that emptied it ate
    # the command. Either way the original stands.
    if fixed and fixed != item.text and \
            len(fixed.split()) <= len(item.text.split()):
        state.add_fix("validate", "text_repair", item.text, fixed, note="garbled")
        item.text = fixed


def tidy(state: EngineState, cfg) -> EngineState:
    """Pre-generation, item level: format hygiene and text repair.

    Was `validate.run`'s whole job. It is NOT value resolution and it is not a
    check — it repairs the WORDS before anything reads them, which is why it kept
    its place in the text pass when the rest of that module was retired.
    """
    from assistant.trace import VALIDATE

    fixes_before = len(state.fixes)
    for item in state.items:
        cleaned = item.text.strip().strip("[]").strip()
        # Collapse doubled whitespace Whisper leaves around cut words.
        cleaned = re.sub(r"\s{2,}", " ", cleaned)
        # Stray quotes around a single word break intent validation ("add
        # 'christmas' to calendar" died on every attempt) — dictation quotes
        # carry no meaning the words don't.
        cleaned = re.sub(r"['\"](\w[\w ]{0,40}?)['\"]", r"\1", cleaned)
        if cleaned != item.text:
            state.add_fix("validate", "text_tidy", item.text, cleaned)
            item.text = cleaned
        _repair_text(item, state, cfg)
    repaired = len(state.fixes) - fixes_before
    if state.trace and repaired:
        state.trace.step(VALIDATE, "Tidied", f"{repaired} repair(s): "
                         + "; ".join(f.human() for f in state.fixes[fixes_before:]),
                         rules=[f.rule for f in state.fixes[fixes_before:]])
    return state
