"""The needs_edit round-trip must be reachable from a real voice command.

`supports_edit` is how a client says it can show the "edit the transcription"
sheet; the engine only returns a `needs_edit` response when it is set. It was
read on `/voice/text` only — but the phone speaks, so its commands arrive as
audio on `/voice/stream` (and `/voice`), and both routes called the engine
without the flag. The edit gate could therefore never fire on anything anyone
actually said. These pin that all three routes forward it.

Model-free: the STT and the engine are stubbed, so the only thing under test is
whether the route hands the flag through.
"""
from __future__ import annotations

import io
import types

import pytest

import assistant.api.server as server


@pytest.fixture
def seen(monkeypatch):
    """Capture the `supports_edit` value the engine is called with.

    The wrapper does `from assistant.engine import run_transcript` at call time,
    so patching the module attribute intercepts every route's call."""
    captured: list[bool] = []
    import assistant.engine as engine

    def fake_run(transcript, **kw):
        captured.append(kw.get("supports_edit"))
        return {"message": "ok", "actions": [], "refresh": "",
                "parse": "rule", "trace": [], "brain": "engine-v2"}

    monkeypatch.setattr(engine, "run_transcript", fake_run)
    # A stub Whisper so the audio routes don't need a model.
    monkeypatch.setattr(server, "_get_stt",
                        lambda: types.SimpleNamespace(transcribe=lambda _np: "book gym at 7"))
    monkeypatch.setattr("assistant.api.audio_utils.audio_bytes_to_numpy",
                        lambda _b: [0.0])
    return captured


@pytest.fixture
def client():
    app = server.create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def _audio_data(**extra):
    data = {"audio": (io.BytesIO(b"RIFFfake"), "audio.wav")}
    data.update(extra)
    return data


def test_voice_audio_forwards_supports_edit(client, seen):
    client.post("/voice", data=_audio_data(supports_edit="true"),
                content_type="multipart/form-data")
    assert seen == [True]


def test_voice_audio_defaults_edit_off(client, seen):
    client.post("/voice", data=_audio_data(), content_type="multipart/form-data")
    assert seen == [False]


def test_voice_stream_audio_forwards_supports_edit(client, seen):
    resp = client.post("/voice/stream", data=_audio_data(supports_edit="true"),
                       content_type="multipart/form-data")
    resp.get_data()   # drain the NDJSON stream so the worker thread finishes
    assert seen == [True]


def test_voice_stream_audio_defaults_edit_off(client, seen):
    resp = client.post("/voice/stream", data=_audio_data(),
                       content_type="multipart/form-data")
    resp.get_data()
    assert seen == [False]


def test_voice_stream_text_branch_forwards_supports_edit(client, seen):
    resp = client.post("/voice/stream",
                       json={"transcript": "book gym at 7", "supports_edit": True})
    resp.get_data()
    assert seen == [True]
