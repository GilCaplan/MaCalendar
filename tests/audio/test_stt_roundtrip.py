"""Automated audio→text accuracy tests.

Manual STT testing (scripts/test_stt.py) requires a human to talk into a mic
every time — it can't run in CI and doesn't produce a repeatable signal. This
file closes that gap using macOS's built-in `say` command as a synthetic speech
source: it renders known reference text to 16kHz mono WAV (no resampling
needed — `say --data-format=LEI16@16000` outputs the exact sample rate Whisper
expects), feeds it through the *real* production STT engine
(`assistant.stt.whisper_stt.WhisperSTT`, same "base" model as config.example.yaml),
and checks the transcript against the reference with word error rate (WER).

This is deliberately layered on top of (not a replacement for) the NLU regression
suites in test_historical_corpus.py / test_multi_action_scenarios.py, which use
*real* garbled human transcripts as text input. This file isolates the STT
component itself: given clean speech, how accurate is transcription? And then,
given that transcription (with whatever synthetic-voice artifacts it produces),
does the rule parser still recover the right action?

Skipped entirely off macOS or without the `say` binary (CI Linux runners, etc).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin" or shutil.which("say") is None,
    reason="Requires macOS `say` for synthetic speech generation",
)


# ---------------------------------------------------------------------------
# Synthesis + STT fixtures
# ---------------------------------------------------------------------------

def _synthesize(text: str, voice: str = "Samantha", rate: int = 175) -> np.ndarray:
    """Render text to a 16kHz mono float32 array via macOS `say`."""
    import soundfile as sf

    with tempfile.TemporaryDirectory() as tmp:
        wav_path = os.path.join(tmp, "speech.wav")
        subprocess.run(
            [
                "say", "-v", voice, "-r", str(rate), "-o", wav_path,
                "--data-format=LEI16@16000", "--file-format=WAVE", text,
            ],
            check=True, capture_output=True,
        )
        data, sr = sf.read(wav_path)
        assert sr == 16000
        return data.astype(np.float32)


@pytest.fixture(scope="module")
def whisper_stt():
    """Load the production-default 'base' Whisper model once for the whole module."""
    from assistant.config import WhisperConfig
    from assistant.stt.whisper_stt import WhisperSTT

    return WhisperSTT(WhisperConfig(model_size="base", compute_type="int8", device="cpu"))


def _normalize_words(text: str) -> list[str]:
    """Lowercase, strip punctuation, and merge "3 pm" / "3 PM" into "3pm" —
    Whisper always emits the merged form regardless of spacing in the reference,
    so comparing word-for-word would otherwise penalize correct transcription.
    """
    import re
    lowered = text.lower()
    lowered = re.sub(r"(\d+)\s*(am|pm)\b", r"\1\2", lowered)
    return re.findall(r"[a-z0-9]+", lowered)


def _word_error_rate(reference: str, hypothesis: str) -> float:
    """Classic WER via word-level Levenshtein edit distance / len(reference)."""
    ref = _normalize_words(reference)
    hyp = _normalize_words(hypothesis)
    n, m = len(ref), len(hyp)
    if n == 0:
        return 0.0 if m == 0 else 1.0
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if ref[i - 1] == hyp[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
    return dp[n][m] / n


# ---------------------------------------------------------------------------
# Raw STT accuracy — calibrated against the 'base' model's real behavior
# ---------------------------------------------------------------------------

# WER threshold of 0.3 was calibrated empirically against the 'base' model:
# clean synthetic speech typically comes back at 0.0-0.15 WER, with occasional
# homophone/punctuation artifacts (e.g. "Add" -> "Ad") pushing short phrases
# higher. This catches real STT regressions (wrong model, broken resampling,
# language misconfiguration) without being flaky on synthetic-voice noise.
WER_THRESHOLD = 0.3

STT_ACCURACY_CASES = [
    "Schedule a meeting tomorrow at 3 PM",
    "Delete my grocery list",
    "What do I have today",
    "Cancel my dentist appointment",
    "Complete the grocery task and delete the laundry task",
    "Reschedule my meeting with John from 3 PM to 5 PM",
    "Add urgent task submit report",
]


@pytest.mark.parametrize("reference", STT_ACCURACY_CASES)
def test_stt_word_error_rate_within_threshold(whisper_stt, reference):
    audio = _synthesize(reference)
    hypothesis = whisper_stt.transcribe(audio)
    wer = _word_error_rate(reference, hypothesis)
    assert wer <= WER_THRESHOLD, (
        f"WER {wer:.2f} exceeds threshold for {reference!r} -> {hypothesis!r}"
    )


# ---------------------------------------------------------------------------
# Full audio → text → action pipeline (excludes rule_parser step from the mic,
# but exercises the real STT engine feeding the real rule parser)
# ---------------------------------------------------------------------------

@pytest.fixture
def rule_parser(isolated_registry):
    from assistant.actions.calendar.action import (
        CreateEventAction, UpdateEventAction, DeleteEventAction, QueryScheduleAction
    )
    from assistant.actions.todo.action import (
        CreateTodoAction, CompleteTodoAction, DeleteTodoAction, UpdateTodoAction,
        QueryTodoAction, AddSubtaskAction, CompleteSubtaskAction, DeleteSubtaskAction,
    )
    from assistant.actions.clarify import ClarifyAction
    from assistant.intent.rule_parser import RuleBasedParser

    for cls in [
        CreateEventAction, UpdateEventAction, DeleteEventAction, QueryScheduleAction,
        CreateTodoAction, CompleteTodoAction, DeleteTodoAction, UpdateTodoAction,
        QueryTodoAction, AddSubtaskAction, CompleteSubtaskAction, DeleteSubtaskAction,
        ClarifyAction,
    ]:
        isolated_registry._actions[cls.action_name] = cls

    return RuleBasedParser(isolated_registry)


AUDIO_TO_ACTION_CASES = [
    ("Schedule a meeting tomorrow at three PM", "create_event"),
    ("Delete my grocery list", "delete_todo"),
    ("What do I have today", "query_schedule"),
    ("Cancel my dentist appointment", "delete_event"),
]


@pytest.mark.parametrize("reference,expected_action", AUDIO_TO_ACTION_CASES)
def test_audio_to_action_end_to_end(whisper_stt, rule_parser, reference, expected_action):
    """Speak it, transcribe it with the real STT engine, parse it with the real
    rule parser — the full path a Mac voice command actually takes, minus the mic.
    """
    from assistant.intent.context import context_memory
    context_memory.reset()

    audio = _synthesize(reference)
    transcript = whisper_stt.transcribe(audio)
    result = rule_parser.analyze(transcript, current_view="month")

    action_names = [name for name, _ in result.intents]
    assert expected_action in action_names, (
        f"{reference!r} -> STT {transcript!r} -> actions {action_names}, "
        f"expected {expected_action!r} among them"
    )


# ---------------------------------------------------------------------------
# STT homophone handling: Whisper 'base' commonly transcribes sentence-initial
# "Buy" as "by"/"bye". rule_parser._route_intent now has a narrow Pass 5 fallback
# (_STT_HOMOPHONE_VERBS) that recognizes "by"/"bye" as "buy" — but *only* when
# spaCy has already tagged it as the span's ROOT (a preposition/adverb can't
# legitimately be a well-formed sentence's ROOT, so landing there is itself the
# signal something was misheard). This recovers routing to create_todo, but
# doesn't fix the *split* — "milk and calm mom" (a second STT error, "call" ->
# "calm") stays one todo instead of two, since the multi-intent splitter never
# saw two separate verb tokens to split on. Full 2-todo recovery from this
# doubly-corrupted transcript would need much deeper repair and isn't attempted.
# ---------------------------------------------------------------------------

def test_audio_buy_homophone_routes_to_create_todo(whisper_stt, rule_parser):
    """Homophone fallback recovers the action even though Whisper mishears "buy"."""
    from assistant.intent.context import context_memory
    from assistant.intent.rule_parser import RuleParserSkip
    context_memory.reset()

    audio = _synthesize("Buy milk and call mom")
    transcript = whisper_stt.transcribe(audio)
    try:
        result = rule_parser.analyze(transcript, current_view="month")
        action_names = [name for name, _ in result.intents]
    except RuleParserSkip:
        action_names = []
    assert "create_todo" in action_names, (
        f"'Buy milk and call mom' -> STT {transcript!r} -> actions {action_names}; "
        f"homophone fallback should have routed this to create_todo"
    )
