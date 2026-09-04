"""Per-request "thinking" trace — one entry per pipeline stage, with timings.

Both the Mac pipeline and the iOS API build a Trace as a request flows
through STT → vocab → rule parse → LLM → validate → execute. It's returned
to the iPhone in the /voice response (rendered as a timeline) and pushed to
the Mac status log, so you can see *why* the assistant did what it did.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


# The brain that produced a trace, and the shape its chain of thought reads in.
# ONE source of truth, imported by the engine (which stamps BRAIN_VERSION onto
# every trace and response), by the thinking panel (which renders by it), and
# by the explorer diagram's claim-check. Bump this when the pipeline's shape
# changes so the panel can render an old trace in its old format and a new one
# in the new — the version is the key the panel matches its output format to.
BRAIN_VERSION = "engine-v2"

# Per-version display spec: the ordered chain of thought the panel should show
# for that brain, as (stage, short label) pairs matching the explorer diagram.
# A brain version the panel does not know falls back to raw stage titles.
CHAINS = {
    "engine-v2": [
        ("vocab",    "fix words"),
        ("rule",     "rules first"),
        ("rule",     "split \u00b7 split again"),
        ("validate", "repair \u00b7 rules"),
        ("llm",      "make each item"),
        ("execute",  "write \u00b7 label"),
        ("verify",   "compare"),
        ("done",     "done"),
    ],
}


# The \u24d8 copy behind each step of the chain \u2014 what that step actually does, at
# the depth of the published explorer page (DOCUMENTATION/artifacts/explorer.html,
# whose per-stage aria-labels this mirrors). Keyed (version \u2192 chain label) so it
# stays matched to CHAINS; `test_panel_agreement` fails the build if a chain
# slot has no entry. Both the Mac review panel and the iOS ThinkingView read
# these; the Swift copy in `ThinkingView.stageInfo` is kept identical and pinned
# by `tests/unit/test_stage_info_parity.py`.
STAGE_INFO = {
    "engine-v2": {
        "fix words": (
            "Fix words",
            "The transcript is corrected against your personal vocabulary \u2014 the "
            "names, places and phrases the speech model mishears. A word the "
            "vocabulary itself doubts can be checked with you before anything "
            "runs, so a mishearing never becomes a wrong event."),
        "rules first": (
            "Rules first",
            "A deterministic rule parser reads the command first \u2014 76 verb "
            "mappings \u2014 and scores its own confidence. When it is sure it answers "
            "in milliseconds without ever calling the language model. That is the "
            "fast lane; the deep track keeps checking behind it."),
        "split \u00b7 split again": (
            "Split, then split again",
            "The command is broken into its independent items, then each item is "
            "broken down again \u2014 two times in a sentence is two events, a list is "
            "one task per thing, a recurrence becomes a series. Deterministic "
            "where it can be; the model only when an item is genuinely ambiguous."),
        "repair \u00b7 rules": (
            "Repair & validate",
            "Named deterministic rules repair each item and guard the calendar \u2014 "
            "dates, am/pm, end-before-start, until/through, and rounding a "
            "recurrence to daily, weekly or monthly (announced, never silent). The "
            "observance gate lives here: what the assistant may book on Shabbat, "
            "yom tov and fast days."),
        "make each item": (
            "Make each item",
            "Per item, the rules \u2014 or one schema-constrained model call when the "
            "rules cannot \u2014 produce the actual action: create this event, add "
            "that task, answer this question. Every model call is grounded on the "
            "raw words and can only return a valid shape."),
        "write \u00b7 label": (
            "Write & label",
            "The action runs against the local database, and the result is "
            "labelled \u2014 an event gets its category and colour, a task its tags. "
            "Nothing here reaches the internet; the database is a file on the "
            "machine."),
        "compare": (
            "Cross-check",
            "The cross-check compares what was produced against what you actually "
            "said, and loops a wrong stage back to fix it \u2014 at most three times. "
            "Behind a fast answer it proposes rather than rewrites, so an instant "
            "answer is never silently changed under you."),
        "done": (
            "Done",
            "The command is finished. A fast-lane answer committed instantly and "
            "the deep track keeps checking behind it; a deep-track answer ran the "
            "whole pipeline in front of you. Every step above, and its timing, is "
            "this run."),
    },
}


def stage_info(version: str, label: str) -> "tuple[str, str] | None":
    """(heading, body) for a chain slot's \u24d8, or None if unknown."""
    return STAGE_INFO.get(version, {}).get(label)


# Stage names (stable — the iOS timeline keys icons off these)
STT = "stt"
VOCAB = "vocab"
RULE = "rule"
MEMORY = "memory"
LLM = "llm"
VALIDATE = "validate"
EXECUTE = "execute"
VERIFY = "verify"
DONE = "done"
ERROR = "error"


@dataclass
class TraceStep:
    stage: str
    title: str
    detail: str = ""
    ms: int = 0            # duration of this step
    at_ms: int = 0         # offset from trace start
    ok: bool = True
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = {"stage": self.stage, "title": self.title, "detail": self.detail,
             "ms": self.ms, "at_ms": self.at_ms, "ok": self.ok}
        if self.data:
            d["data"] = self.data
        return d


class Trace:
    def __init__(self, source: str = "mac") -> None:
        self.source = source
        self._t0 = time.perf_counter()
        self._last = self._t0
        self.steps: list[TraceStep] = []
        self._listeners: list = []

    def on_step(self, fn) -> None:
        """Register a callback invoked with each TraceStep as it's added."""
        self._listeners.append(fn)

    def step(self, stage: str, title: str, detail: str = "", *, ok: bool = True,
             **data: Any) -> TraceStep:
        """Record a step. Its duration is the time since the previous step."""
        now = time.perf_counter()
        s = TraceStep(
            stage=stage, title=title, detail=detail,
            ms=int((now - self._last) * 1000),
            at_ms=int((now - self._t0) * 1000),
            ok=ok, data={k: v for k, v in data.items() if v is not None},
        )
        self._last = now
        self.steps.append(s)
        for fn in self._listeners:
            try:
                fn(s)
            except Exception:
                pass
        return s

    def mark(self) -> None:
        """Reset the step timer without recording (e.g. after a wait)."""
        self._last = time.perf_counter()

    @property
    def total_ms(self) -> int:
        return int((time.perf_counter() - self._t0) * 1000)

    def to_list(self) -> list[dict[str, Any]]:
        return [s.to_dict() for s in self.steps]

    def summary(self) -> str:
        return " → ".join(f"{s.title} ({s.ms}ms)" for s in self.steps)
