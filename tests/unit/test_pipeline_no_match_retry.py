"""Escalating to the LLM when a confident rule parse matches nothing.

The fast path decides whether to call the LLM *before* anything runs, on
confidence and missing slots alone. A parse can clear both bars and still be
the wrong action entirely: "Walk Mark Stalk today at 2:30PM" scores as
complete_todo because "mark" is a completion verb, fills match_title with
"walk mark stalk", and only then discovers there is no such task. The old code
reported "I couldn't find a task matching…" and stopped, having never asked
the LLM — which reads the sentence as an event without difficulty.

TargetNotFound is what makes that visible: actions used to *return* the
not-found sentence, indistinguishable at the pipeline from a string meaning
work was done.

The guards are as much of the behaviour as the retry. We don't construct a
real Pipeline() (live mic, Whisper, TTS) — same minimal-double approach as
test_pipeline_background_verify.py.
"""
from __future__ import annotations

from typing import Any

import pytest

from assistant.actions.calendar.intent import CalendarIntent
from assistant.actions.todo.intent import CompleteTodoIntent
from assistant.exceptions import LLMUnavailableError, ParseError
from assistant.pipeline import Pipeline


class _Trace:
    """Records steps so a test can assert what the thinking panel would show."""

    def __init__(self) -> None:
        self.steps: list[tuple[str, str]] = []

    def step(self, _kind: Any, title: str, detail: str = "", ok: bool = True) -> None:
        self.steps.append((title, detail))

    @property
    def text(self) -> str:
        return " | ".join(f"{t}: {d}" for t, d in self.steps)


class _Parser:
    def __init__(self, result: Any = None, raises: Exception | None = None) -> None:
        self._result, self._raises = result, raises
        self.calls: list[str] = []

    def parse(self, transcript: str):
        self.calls.append(transcript)
        if self._raises:
            raise self._raises
        return self._result


def _pipeline(parser: Any) -> Pipeline:
    p = Pipeline.__new__(Pipeline)          # no mic, no model, no speaker
    p._parser = parser
    p.config = type("C", (), {"llm_engine": "ollama"})()
    p._set_status = lambda *a, **k: None
    return p


SAID = "Walk Mark Stalk today at 230PM"
_EVENT = ("create_event", CalendarIntent(title="Walk Mark Stalk", date="2026-09-02",
                                         start_time="14:30", end_time="15:30"))
_TODO = ("complete_todo", CompleteTodoIntent(match_title="walk mark stalk"))


def _retry(parser, **kw):
    defaults = dict(eligible=True, failed_action="complete_todo",
                    message="I couldn't find a task matching 'walk mark stalk'.")
    trace = _Trace()
    got = Pipeline._retry_after_no_match(_pipeline(parser), SAID, trace, **{**defaults, **kw})
    return got, trace


# ---------------------------------------------------------------------------
# The case from the report
# ---------------------------------------------------------------------------

def test_a_wrong_action_is_re_read_by_the_llm():
    parser = _Parser([_EVENT])
    got, trace = _retry(parser)
    assert got == [_EVENT]
    assert parser.calls == [SAID]          # the whole sentence, not the slots
    assert "create event" in trace.text


# ---------------------------------------------------------------------------
# Guards — each one exists to stop a specific bad outcome
# ---------------------------------------------------------------------------

def test_the_llm_path_is_never_retried():
    """Asking the same model the same question twice buys nothing."""
    parser = _Parser([_EVENT])
    got, _ = _retry(parser, eligible=False)
    assert got is None
    assert parser.calls == []              # not even called


def test_agreement_means_the_target_really_is_missing():
    """If the LLM also says complete_todo, "I couldn't find it" was correct."""
    got, trace = _retry(_Parser([_TODO]))
    assert got is None
    assert "really is missing" in trace.text


def test_an_unrecognisable_retry_keeps_the_original_answer():
    got, _ = _retry(_Parser([]))
    assert got is None


@pytest.mark.parametrize("boom", [
    LLMUnavailableError("ollama down"),
    ParseError("bad json"),
])
def test_a_broken_llm_keeps_the_original_answer(boom):
    """Ollama being down must not turn a clean "not found" into a crash."""
    got, trace = _retry(_Parser(raises=boom))
    assert got is None
    assert "keeping the original answer" in trace.text


def test_no_parser_at_all_is_survivable():
    p = _pipeline(None)
    got = Pipeline._retry_after_no_match(
        p, SAID, _Trace(), eligible=True, failed_action="complete_todo", message="x")
    assert got is None


def test_a_multi_action_retry_is_returned_whole():
    """A sentence the LLM reads as two things is still better than nothing."""
    second = ("create_todo", None)
    parser = _Parser([_EVENT, second])
    got, _ = _retry(parser)
    assert got is not None and len(got) == 2
