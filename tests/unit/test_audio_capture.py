"""Unit tests for audio capture (sounddevice mocked)."""

import threading
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from assistant.audio.capture import AudioCapture
from assistant.config import AudioConfig
from assistant.exceptions import AudioCaptureError


def _config(**kwargs) -> AudioConfig:
    defaults = dict(sample_rate=16000, silence_threshold=0.5, silence_duration_sec=0.2, max_recording_sec=2)
    defaults.update(kwargs)
    return AudioConfig(**defaults)


def test_record_returns_numpy_float32(monkeypatch):
    """Mock sounddevice and check the return type."""
    capture = AudioCapture(_config())

    def fake_input_stream(samplerate, channels, dtype, blocksize, callback):
        # Simulate two chunks of audio then silence
        chunk = np.zeros(blocksize, dtype=np.float32)
        # Call callback a few times
        for _ in range(5):
            callback(chunk.reshape(-1, 1), blocksize, None, None)
        return MagicMock(__enter__=lambda s: s, __exit__=MagicMock(return_value=False))

    monkeypatch.setattr("sounddevice.InputStream", fake_input_stream)
    # The stop_event needs to fire quickly; use a short silence_duration
    result = capture.record_until_silence()
    assert isinstance(result, np.ndarray)
    assert result.dtype == np.float32


def test_portaudio_error_raises_audio_capture_error(monkeypatch):
    import sounddevice as sd
    capture = AudioCapture(_config())

    def fake_bad_stream(*a, **kw):
        raise sd.PortAudioError("no device")

    monkeypatch.setattr("sounddevice.InputStream", fake_bad_stream)
    with pytest.raises(AudioCaptureError, match="microphone"):
        capture.record_until_silence()
