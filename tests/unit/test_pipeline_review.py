"""Tests for the Redo / Add more / Send review pause.

The bar exists so a recording that stopped on silence (or a stray mic tap) can
be redone before anything happens. But a *spoken* stop word — "execute", "done",
… — is the user saying "go", so waiting three more seconds is exactly wrong.
These tests pin that distinction, and the wiring of the bar's answers.

As elsewhere in this suite, the unbound methods are called against a minimal
double rather than a real Pipeline (which would pull in a live mic and Whisper).
"""
from __future__ import annotations

import queue
import threading
import time
from typing import Any

import pytest

from assistant.pipeline import (
    STATUS_REVIEW,
    Pipeline,
    _build_stop_re,
    _strip_stop_keyword,
)


class _AudioCfg:
    stop_phrases: list = []
    review_before_send = True
    review_seconds = 2


class _Cfg:
    audio = _AudioCfg()


class _FakePipeline:
    def __init__(self) -> None:
        self.config = _Cfg()
        self.status_queue: queue.Queue = queue.Queue()
        self._review_event = threading.Event()
        self._review_choice = None
        self._phase = "idle"

    def _set_status(self, status: str, message: str = "") -> None:
        self.status_queue.put((status, message))

    _await_review = Pipeline._await_review
    review_choice = Pipeline.review_choice


# ---------------------------------------------------------------------------
# The rule the user asked for: saying a stop word skips the wait entirely
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("transcript", [
    "add lunch tomorrow at one execute",
    "add lunch tomorrow at one, done",
    "remind me to call Noa stop",
])
def test_stop_word_is_recognised_in_the_final_transcript(transcript):
    """Short commands can finish before the stream-checker ever runs, so the
    stop word has to be caught in the transcript too — not only mid-stream."""
    assert _build_stop_re([]).search(transcript)


def test_stop_word_is_stripped_before_parsing():
    assert _strip_stop_keyword("add lunch tomorrow at one execute", []) == "add lunch tomorrow at one"


def test_ordinary_transcript_is_not_treated_as_a_stop_word():
    assert not _build_stop_re([]).search("add lunch with Shaul tomorrow at one")


# ---------------------------------------------------------------------------
# The review pause itself
# ---------------------------------------------------------------------------

def test_review_auto_sends_when_nobody_answers():
    p = _FakePipeline()
    p.config.audio.review_seconds = 1
    started = time.monotonic()
    assert p._await_review("add lunch tomorrow") == "send"
    assert time.monotonic() - started >= 0.9      # it really waited


@pytest.mark.parametrize("choice", ["redo", "add", "cancel", "send"])
def test_review_returns_the_users_choice_without_waiting(choice):
    p = _FakePipeline()
    p.config.audio.review_seconds = 10            # would hang if the answer were ignored
    threading.Timer(0.05, lambda: p.review_choice(choice)).start()
    started = time.monotonic()
    assert p._await_review("add lunch tomorrow") == choice
    assert time.monotonic() - started < 2         # answered, not timed out


def test_review_publishes_the_countdown_and_transcript_for_the_bar():
    p = _FakePipeline()
    p.config.audio.review_seconds = 1
    p._await_review("add lunch with Shaul tomorrow at one")
    status, message = p.status_queue.get_nowait()
    assert status == STATUS_REVIEW
    seconds, _, snippet = message.partition("|")
    assert int(seconds) == 1
    assert snippet == "add lunch with Shaul tomorrow at one"
    assert p._phase == STATUS_REVIEW


def test_review_snippet_is_truncated_for_a_long_transcript():
    p = _FakePipeline()
    p.config.audio.review_seconds = 1
    p._await_review("word " * 60)
    _, message = p.status_queue.get_nowait()
    assert len(message.partition("|")[2]) <= 61   # 60 chars + the ellipsis
