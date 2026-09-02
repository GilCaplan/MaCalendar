"""Only a real client may claim to be one.

An afternoon of testing this assistant with curl left 328 entries in the trace
bus that were indistinguishable from commands actually given to the phone,
because /voice/text defaulted an unlabelled caller to "ios". The history the
thinking card shows was then mostly noise, and there was nothing in the file to
tell the two apart afterwards.

Defaulting the other way makes the failure modes asymmetric in the right
direction: forgetting to label a test is harmless, and forgetting to label a
real client is immediately visible.
"""
from __future__ import annotations

import json

import pytest

import assistant.api.server as server


@pytest.fixture
def bus(tmp_path, monkeypatch):
    path = tmp_path / "bus.jsonl"
    monkeypatch.setattr("assistant.trace_bus.BUS_PATH", str(path))
    return path


@pytest.fixture
def client():
    """The real rule parser, deliberately.

    Stubbing it out forces the LLM path, and CI has no Ollama — the parse then
    errors before anything is written to the bus and every assertion here fails
    for a reason that has nothing to do with what is being tested. The commands
    below are ones the rules answer on their own.
    """
    app = server.create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def _sources(bus):
    if not bus.exists():
        return []
    return [json.loads(line)["source"] for line in bus.read_text().splitlines() if line.strip()]


@pytest.mark.parametrize("body, expected", [
    ({"transcript": "book gym tomorrow at 7am"}, "test"),                  # curl
    ({"transcript": "book gym tomorrow at 7am", "source": "mac"}, "mac"),  # the GUI
    ({"transcript": "book gym tomorrow at 7am", "source": "ios"}, "ios"),  # the phone
    ({"transcript": "book gym tomorrow at 7am", "source": "hax"}, "test"), # nonsense
    ({"transcript": "book gym tomorrow at 7am", "source": "  MAC  "}, "mac"),
])
def test_the_source_is_recorded_from_the_caller(client, bus, body, expected):
    client.post("/voice/text", json=body)
    assert _sources(bus) == [expected]


def test_an_unlabelled_caller_never_passes_as_a_phone(client, bus):
    """The specific regression: this used to default to "ios"."""
    client.post("/voice/text", json={"transcript": "remind me to buy milk"})
    assert "ios" not in _sources(bus)
