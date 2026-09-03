"""Step 1 — transcript repair.

Contract (see DOCUMENTATION/ENGINE.md):
  reads   state.raw_text, state.source, state.supports_edit
  writes  state.text, state.corrections, state.needs_edit, state.ignored,
          trace steps (VOCAB)

The stage owns everything between "what Whisper wrote" and "words worth
parsing": trailing stop keywords go, false starts are declared trivial (and
never remembered — recording one teaches the model junk is normal), the
personal vocabulary repairs what it is confident about, and what it is *not*
confident about is surfaced — as `needs_edit` when the client can show an
editor and the setting asks for one, as advisory `uncertain_words` otherwise.
"""

from __future__ import annotations

import re

from assistant.engine.state import EngineState

# ---------------------------------------------------------------------------
# Stop keywords ("execute", "done" …) end a recording; they are not content.
# These lived in pipeline.py while the GUI parsed for itself; the engine owns
# them now and the GUI imports from here.
# ---------------------------------------------------------------------------

# Longest first so "set events" beats "set event".
_BUILTIN_STOP_PATTERNS = [
    r"\bset\s+events?\b",
    r"\bexecute\b",
    r"\bxq\b",        # STT mishearing of "execute"
    r"\bdone\b",
    r"\bstop\b",
    r"\bsubmit\b",
    r"\bconfirm\b",
    r"\bthat'?s?\s+it\b",
    r"\bok\s+go\b",
]


def build_stop_re(extra_phrases: "list[str] | None" = None) -> "re.Pattern[str]":
    """Stop-keyword regex from built-ins plus user-configured phrases."""
    patterns = list(_BUILTIN_STOP_PATTERNS)
    for phrase in (extra_phrases or []):
        phrase = phrase.strip()
        if not phrase:
            continue
        escaped = r"\s+".join(re.escape(w) for w in phrase.split())
        patterns.append(r"\b" + escaped + r"\b")
    combined = r"[\s,.!?]*(?:" + "|".join(patterns) + r")[\s,.!?]*$"
    return re.compile(combined, re.IGNORECASE)


_STOP_RE = build_stop_re()


def strip_stop_keyword(transcript: str, extra_phrases: "list[str] | None" = None) -> str:
    """Remove trailing stop keywords from the transcript."""
    stop_re = build_stop_re(extra_phrases) if extra_phrases else _STOP_RE
    cleaned = stop_re.sub("", transcript).strip()
    return cleaned if cleaned else transcript


# ---------------------------------------------------------------------------
# False starts. Four of these were once parsed, executed and remembered as
# real commands ("Execute.", "No.", "I need a b-"), teaching the model that
# junk is normal. Trivial means: not parsed, not executed, not remembered.
# ---------------------------------------------------------------------------

_FILLER = frozenset({
    "a", "an", "the", "um", "uh", "er", "hmm", "ok", "okay", "yes", "yeah",
    "no", "nope", "yep", "so", "and", "but", "well", "just", "please",
})


def is_trivial_transcript(text: str) -> bool:
    """True when there is nothing here to act on."""
    words = [w for w in re.findall(r"[a-z0-9']+", (text or "").lower()) if w]
    if not words:
        return True
    meaningful = [w for w in words if w not in _FILLER and len(w) > 1]
    # One meaningful word is an instruction only if it names something to do,
    # and by this point the stop words are already gone — so it does not.
    return len(meaningful) < 2


def run(state: EngineState, cfg) -> EngineState:
    from assistant.stt.vocab import apply_vocab, get_vocab
    from assistant.trace import VOCAB, DONE

    text = strip_stop_keyword(state.raw_text, cfg.audio.stop_phrases)

    if is_trivial_transcript(text):
        state.ignored = True
        state.text = text
        state.parse_path = "ignored"
        if state.trace:
            state.trace.step(DONE, "Nothing to do",
                             "Heard a stop word or a false start, nothing to act on.")
        return state

    text, vocab_fixes = apply_vocab(text, source=state.source)
    state.text = text
    state.corrections = [c.to_dict() for c in vocab_fixes]

    # Words the vocabulary is *not* sure about. With a capable client and the
    # setting on, these gate execution behind a "please edit the transcription"
    # round-trip; otherwise they ride along as advisory `uncertain_words`, the
    # existing tap-a-word affordance.
    doubtful: list = []
    try:
        doubtful = get_vocab().suggestions(text)
    except Exception:
        doubtful = []
    confirm = bool(getattr(getattr(cfg, "engine", None), "confirm_transcript", False))
    if doubtful and confirm and state.supports_edit:
        state.needs_edit = list(doubtful)

    if state.trace:
        state.trace.step(
            VOCAB, "Vocabulary",
            ("Fixed " + ", ".join(f"{c.original}→{c.replacement}" for c in vocab_fixes))
            if vocab_fixes else "No corrections needed",
            transcript=text, corrections=state.corrections or None,
        )
    return state


def uncertain_words(text: str) -> list:
    """Advisory low-confidence words for the client's tap-a-word UI."""
    try:
        from assistant.stt.vocab import get_vocab
        return get_vocab().suggestions(text)
    except Exception:
        return []
