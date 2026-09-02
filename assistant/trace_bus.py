"""Cross-process channel for assistant traces.

The Mac runs three processes: the calendar GUI (`assistant.main`), the API
server the phone talks to (`assistant.api`), and the thinking HUD
(`assistant.thinking_hud`) that renders what the assistant is doing. Whoever
ran the command — you at the Mac, or you on the phone — the HUD is a different
process from the one that ran it, so the trace has to leave the process it was
built in.

This is a small append-only file all three can use: producers publish, the HUD
tails it. It is deliberately dumb — one JSON object per line, capped — because
it carries transient UI notifications, not data anyone needs to keep.

Lines come in two shapes. A whole finished run at once:

    {"kind": "trace", "run": …, "source": "iPhone", "steps": [...], "result": {}}

or a run streaming as it happens, which is what the Mac's own pipeline does so
the HUD fills in live rather than appearing all at once when the command ends:

    {"kind": "begin",  "run": …, "source": "Mac"}
    {"kind": "step",   "run": …, "step": {...}}      (repeated)
    {"kind": "result", "run": …, "result": {...}}

Readers must tolerate a run whose `begin` they missed — a trim can rewrite the
file between a producer's write and a reader's poll — so a `step` for an
unknown run starts one.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)

BUS_PATH = os.environ.get("MACALENDAR_TRACE_BUS") or os.path.expanduser(
    "~/.assistant_tools/trace_bus.jsonl")

# Traces are only interesting for a few seconds after they happen; keep enough
# to survive a slow poll, not a history. A streaming run is many lines, so this
# counts lines rather than runs.
MAX_ENTRIES = 200


def new_run() -> str:
    """An id tying the lines of one streaming run together."""
    return uuid.uuid4().hex[:12]


def _append(entry: dict[str, Any]) -> None:
    """Write one line. Never raises — this is a nicety, not a duty."""
    entry["ts"] = time.time()
    try:
        os.makedirs(os.path.dirname(BUS_PATH), exist_ok=True)
        with open(BUS_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:                      # pragma: no cover - best effort
        logger.debug("trace bus publish failed: %s", exc)


def publish(source: str, steps: list[dict[str, Any]], result: dict[str, Any] | None = None) -> str:
    """Append one finished run, all at once. Returns its id."""
    run = new_run()
    _trim()                       # only ever between runs, never mid-run
    _append({"kind": "trace", "run": run, "source": source,
             "steps": steps, "result": result or {}})
    return run


def publish_begin(source: str) -> str:
    """Open a streaming run. Returns the id the steps and result must carry."""
    run = new_run()
    _trim()
    _append({"kind": "begin", "run": run, "source": source})
    return run


def publish_step(run: str, step: dict[str, Any]) -> None:
    _append({"kind": "step", "run": run, "step": step})


def publish_result(run: str, result: dict[str, Any] | None = None) -> None:
    _append({"kind": "result", "run": run, "result": result or {}})


def _trim() -> None:
    """Drop old lines. Called only when a run starts, so no run is ever cut
    in half by a trim that lands between its own lines."""
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
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue            # a half-written line; it'll be re-read next time
                entry.setdefault("kind", "trace")    # entries written before streaming
                out.append(entry)
            return out, f.tell()
    except OSError:
        return [], offset


def read_history(limit: int = 200) -> list[dict[str, Any]]:
    """The most recent finished runs, newest first.

    The bus file is the only durable record of what the assistant has done —
    the HUD holds a handful of runs in memory and loses them on restart, and
    everything before it started is only here. Reading it back is what lets the
    card show more than the command you just gave.

    Only complete runs are returned: a "trace" carries its steps and its result
    together, where a live run is a "begin" followed by loose steps that may
    still be arriving.
    """
    try:
        with open(BUS_PATH, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return []

    out: list[dict[str, Any]] = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("kind", "trace") != "trace":
            continue
        out.append(entry)
        if len(out) >= limit:
            break
    return out
