"""Liveness heartbeats for the disconnected surfaces.

The thinking HUD, the calendar GUI and the phone are separate processes (and,
for the phone, a separate device) that expose nothing for the health CLI to
probe. Each writes a small timestamped beat here; `assistant doctor` reads
"last seen" to tell *connected and healthy* from *merely maybe running*.

A beat is best-effort and must never break its host — every write is guarded.
Stores under `~/.assistant_tools/heartbeats/` (overridable with
`MACALENDAR_HEARTBEATS`, which the tests point at a scratch dir).
"""

from __future__ import annotations

import json
import os
import time

_DIR = os.environ.get("MACALENDAR_HEARTBEATS") or \
    os.path.expanduser("~/.assistant_tools/heartbeats")

# How stale a beat may be before a surface is considered disconnected. A HUD
# polls every ~120ms and a GUI every few seconds, so 30s of silence means it
# has stopped beating, not merely idle.
FRESH_SECONDS = 30.0


def beat(name: str, **extra) -> None:
    """Record that `name` is alive right now. Never raises."""
    try:
        os.makedirs(_DIR, exist_ok=True)
        path = os.path.join(_DIR, f"{name}.json")
        tmp = f"{path}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"name": name, "ts": time.time(), "pid": os.getpid(), **extra}, f)
        os.replace(tmp, path)
    except Exception:
        pass


def last_seen(name: str) -> "dict | None":
    """The most recent beat for `name` with its `age` in seconds, or None if it
    has never beaten."""
    try:
        with open(os.path.join(_DIR, f"{name}.json"), encoding="utf-8") as f:
            d = json.load(f)
        d["age"] = time.time() - float(d.get("ts", 0))
        return d
    except Exception:
        return None


def is_fresh(name: str, within: float = FRESH_SECONDS) -> bool:
    d = last_seen(name)
    return bool(d and d["age"] <= within)
