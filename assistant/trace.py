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
