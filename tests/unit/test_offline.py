"""The assistant must work with the internet switched off.

Everything that decides anything runs on this machine: Whisper on the GPU,
llama3.1 in Ollama on localhost, spaCy, the Hebrew calendar, and a SQLite file.
Nothing about that is enforced by the design, though — it is a property that
holds until someone adds a library that phones home, and it breaks silently
because development happens with wifi on.

It had already broken. mlx_whisper was handed a Hugging Face repo id, so every
single start asked huggingface.co to resolve the revision — cached weights,
zero bytes transferred, and a hard dependency on the internet to boot an
assistant that is otherwise entirely local. Nothing failed, because wifi was
always on.

These tests blow up on any outbound connection that is not loopback. Loopback
is allowed: Ollama is a local process reached over a socket, and treating that
as "the network" would make the rule meaningless.
"""
from __future__ import annotations

import datetime as dt
import socket

import pytest


class OutboundBlocked(OSError):
    """Raised instead of connecting anywhere off this machine."""


def _is_local(addr) -> bool:
    host = addr[0] if isinstance(addr, (tuple, list)) and addr else ""
    if not isinstance(host, str):
        return False
    return (host.startswith("127.") or host.startswith("::1")
            or host in ("localhost", "0.0.0.0", "::"))


@pytest.fixture
def no_network(monkeypatch):
    """Every non-loopback connect() raises for the duration of the test."""
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def guard(self, addr):
        if not _is_local(addr):
            raise OutboundBlocked(f"outbound connection attempted to {addr!r}")
        return real_connect(self, addr)

    def guard_ex(self, addr):
        if not _is_local(addr):
            raise OutboundBlocked(f"outbound connection attempted to {addr!r}")
        return real_connect_ex(self, addr)

    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket.socket, "connect_ex", guard_ex)
    # getaddrinfo for a remote host is already a leak of intent, and blocking it
    # gives a clearer failure than waiting for the connect.
    real_gai = socket.getaddrinfo

    def guard_gai(host, *a, **k):
        if isinstance(host, str) and host not in ("localhost", "127.0.0.1", "::1", "", None):
            raise OutboundBlocked(f"DNS lookup attempted for {host!r}")
        return real_gai(host, *a, **k)

    monkeypatch.setattr(socket, "getaddrinfo", guard_gai)
    return guard


# ---------------------------------------------------------------------------
# The guard itself has to work, or every test below passes for nothing
# ---------------------------------------------------------------------------

def test_the_guard_blocks_the_internet(no_network):
    with pytest.raises(OutboundBlocked):
        socket.create_connection(("example.com", 80), timeout=1)


def test_the_guard_still_allows_loopback(no_network):
    """Ollama is a local process on a socket, not the internet."""
    s = socket.socket()
    try:
        s.connect_ex(("127.0.0.1", 1))     # refused is fine; blocked is not
    except OutboundBlocked:
        pytest.fail("loopback was blocked — Ollama would be unreachable")
    finally:
        s.close()


# ---------------------------------------------------------------------------
# The pieces that must never need the internet
# ---------------------------------------------------------------------------

def test_config_loads_offline(no_network):
    """Reads config.example.yaml, not config.yaml.

    config.yaml is gitignored, so CI has none and load_config() raises there —
    which is how this test went red on a machine that was otherwise fine. The
    example is the checked-in one, and it is what the assertion is really
    about: the shipped default points the LLM at this machine.
    """
    from assistant.config import load_config
    cfg = load_config("config.example.yaml")
    assert cfg.ollama.base_url.startswith("http://localhost") or \
           cfg.ollama.base_url.startswith("http://127.0.0.1"), \
        "the shipped default must reach the LLM without leaving this machine"


def test_the_rule_parser_works_offline(no_network, registry_with_real_actions):
    from assistant.intent.rule_parser import RuleBasedParser
    got = RuleBasedParser(registry_with_real_actions).analyze(
        "book gym tomorrow at 7am", current_view="month")
    assert [n for n, _ in got.intents] == ["create_event"]


def test_the_hebrew_calendar_works_offline(no_network):
    """pyluach and astral are pure Python — no lookup, no almanac service."""
    from assistant.observance import availability
    assert availability(dt.date(2026, 9, 12)) is not None


def test_the_database_works_offline(no_network, tmp_path, monkeypatch):
    monkeypatch.setenv("MACALENDAR_DB", str(tmp_path / "c.db"))
    from assistant.actions.calendar.intent import CalendarIntent
    from assistant.db import get_db
    db = get_db()
    db.create_event(CalendarIntent(title="Offline event", date="2026-09-04",
                                   start_time="09:00", end_time="10:00"))
    assert [e["title"] for e in db.get_events_for_day(dt.date(2026, 9, 4))] == ["Offline event"]


# ---------------------------------------------------------------------------
# The one that actually regressed
# ---------------------------------------------------------------------------

def test_a_cached_whisper_model_resolves_without_the_network(no_network, monkeypatch):
    """The regression: a repo id sent mlx_whisper to huggingface.co every load."""
    # huggingface_hub arrives with the optional [mlx] extra, so a Linux CI box
    # has no such module and monkeypatching it by name would raise on import.
    # The code under test already degrades to the repo id without it.
    pytest.importorskip("huggingface_hub")
    from assistant.stt import mlx_whisper_stt as m

    calls = {}

    def fake_snapshot(repo, **kw):
        calls.update(kw)
        return "/somewhere/in/the/hf/cache"

    monkeypatch.setattr("huggingface_hub.snapshot_download", fake_snapshot)
    got = m.MlxWhisperSTT._resolve_local("mlx-community/whisper-base-mlx")

    assert got == "/somewhere/in/the/hf/cache"
    assert calls.get("local_files_only") is True, \
        "resolution must be cache-only, or it is a network call again"


def test_an_uncached_model_falls_back_without_raising(no_network, monkeypatch):
    """A model that was never downloaded still has to leave the app startable —
    it degrades to the repo id so a first online run can fetch it."""
    pytest.importorskip("huggingface_hub")
    from assistant.stt import mlx_whisper_stt as m

    def boom(repo, **kw):
        raise FileNotFoundError("not in cache")

    monkeypatch.setattr("huggingface_hub.snapshot_download", boom)
    assert m.MlxWhisperSTT._resolve_local("mlx-community/nope") == "mlx-community/nope"


def test_a_local_directory_is_passed_straight_through(no_network, tmp_path):
    from assistant.stt import mlx_whisper_stt as m
    assert m.MlxWhisperSTT._resolve_local(str(tmp_path)) == str(tmp_path)
