"""Colour-coded server logs, so a skim shows the flow at a glance.

The API server narrates every command it handles. Coloured by *what kind of
event* each line is, the log reads as a rhythm — cyan a command arriving,
green the answer going back, red a problem — instead of a wall of grey. The
scheme is documented in `DOCUMENTATION/LOGGING.md`.

Colour is applied only when a human is watching (stderr is a TTY) and
`NO_COLOR` is unset, so a log redirected to a file stays plain text.
"""

from __future__ import annotations

import logging
import os
import sys

_RESET = "\033[0m"
_C = {
    "in": "\033[36m",       # cyan   — a command / transcript / audio arriving
    "out": "\033[32m",      # green  — a response going back
    "learn": "\033[35m",    # magenta— vocabulary / memory / location learning
    "warn": "\033[33m",     # yellow — warnings, warm-up, retries
    "error": "\033[31m",    # red    — parse/action failures, unknown intents
}

_FORMAT = "%(asctime)s  %(levelname)-8s  %(name)s — %(message)s"

_IN = ("Text command", "Transcript:", "Audio received", "Retrying", "Audio decode")
_LEARN = ("Learned", "Whitelisted", "Location set", "Memory")
_ERR_WORDS = ("error", "failed", "unknown intent", "no action class", "no such action")


def category(record: logging.LogRecord) -> "str | None":
    """Which colour band a line belongs to — None means leave it plain (the
    processing middle: rule/llm/validate/execute chatter you skim past)."""
    if record.levelno >= logging.ERROR:
        return "error"
    if record.levelno >= logging.WARNING:
        return "warn"
    msg = record.getMessage()
    low = msg.lower()
    if "response:" in low:
        return "out"
    if any(k in msg for k in _IN):
        return "in"
    if any(k in low for k in _ERR_WORDS):
        return "error"
    if any(k in msg for k in _LEARN):
        return "learn"
    if "Warm-up" in msg:
        return "warn"
    return None


class ColorFormatter(logging.Formatter):
    def __init__(self) -> None:
        super().__init__(_FORMAT)

    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        band = category(record)
        return f"{_C[band]}{line}{_RESET}" if band else line


def install(*, force: bool = False) -> bool:
    """Wrap the root logger's handlers with the colour formatter. No-op (and
    returns False) when output is not a terminal or NO_COLOR is set — so file
    logs and CI stay clean. `force` overrides both guards (used by the test)."""
    if not force:
        if os.environ.get("NO_COLOR"):
            return False
        if not (sys.stderr and sys.stderr.isatty()):
            return False
    fmt = ColorFormatter()
    handlers = logging.getLogger().handlers or []
    if not handlers:
        return False
    for h in handlers:
        h.setFormatter(fmt)
    return True
