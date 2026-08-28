"""Cross-process channel for assistant traces.

The Mac runs two processes: the calendar GUI (`assistant.main`) and the API
server the phone talks to (`assistant.api`). Each builds its own Trace, so the
GUI's thinking panel only ever showed commands spoken *at the Mac* — anything
done from the phone was invisible there, even though the Mac is what ran it.

This is a small append-only file both sides can use: the API server publishes a
finished trace, the GUI tails the file and renders it in the same panel. It is
deliberately dumb — one JSON object per line, capped — because it carries
transient UI notifications, not data anyone needs to keep.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

BUS_PATH = os.environ.get("MACALENDAR_TRACE_BUS") or os.path.expanduser(
    "~/.assistant_tools/trace_bus.jsonl")

# Traces are only interesting for a few seconds after they happen; keep enough
# to survive a slow poll, not a history.
MAX_ENTRIES = 40


def publish(source: str, steps: list[dict[str, Any]], result: dict[str, Any] | None = None) -> None:
    """Append one finished trace. Never raises — this is a nicety, not a duty."""
    entry = {"ts": time.time(), "source": source, "steps": steps, "result": result or {}}
    try:
        os.makedirs(os.path.dirname(BUS_PATH), exist_ok=True)
        with open(BUS_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        _trim()
    except Exception as exc:                      # pragma: no cover - best effort
        logger.debug("trace bus publish failed: %s", exc)


def _trim() -> None:
    try:
        with open(BUS_PATH, encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > MAX_ENTRIES * 2:
            with open(BUS_PATH, "w", encoding="utf-8") as f:
                f.writelines(lines[-MAX_ENTRIES:])
    except Exception:
        pass


def size() -> int:
    """Current byte offset — the starting point for a reader that wants only
    what happens from now on."""
    try:
        return os.path.getsize(BUS_PATH)
    except OSError:
        return 0


def read_since(offset: int) -> tuple[list[dict[str, Any]], int]:
    """Entries written after `offset`, plus the new offset.

    A trim rewrites the file and shrinks it; when that is detected the reader
    is moved to the end rather than replaying old traces as if they were new.
    """
    try:
        current = os.path.getsize(BUS_PATH)
    except OSError:
        return [], 0
    if current < offset:                 # file was trimmed or replaced
        return [], current
    if current == offset:
        return [], offset
    out: list[dict[str, Any]] = []
    try:
        with open(BUS_PATH, encoding="utf-8") as f:
            f.seek(offset)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue            # a half-written line; it'll be re-read next time
            return out, f.tell()
    except OSError:
        return [], offset
