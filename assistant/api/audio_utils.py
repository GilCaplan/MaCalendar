"""Decode incoming audio bytes (WAV / m4a) into a float32 numpy array at 16 kHz."""

from __future__ import annotations

import io

import numpy as np

WHISPER_RATE = 16_000


def _resample(audio: np.ndarray, orig_rate: int, target_rate: int) -> np.ndarray:
    """Linear-interpolation resample — sufficient quality for speech."""
    if orig_rate == target_rate:
        return audio
    n_out = int(len(audio) * target_rate / orig_rate)
    return np.interp(
        np.linspace(0, len(audio) - 1, n_out),
        np.arange(len(audio)),
        audio,
    ).astype(np.float32)


def audio_bytes_to_numpy(data: bytes) -> np.ndarray:
    """
    Decode WAV or m4a bytes to a float32 mono array at 16 kHz.

    Relies on soundfile for WAV/FLAC and ffmpeg (via soundfile/pydub fallback)
    for m4a/AAC. Raises ValueError if the audio cannot be decoded.
    """
    try:
        import soundfile as sf
        audio, sr = sf.read(io.BytesIO(data), dtype="float32", always_2d=False)
    except Exception as sf_err:
        # Fallback: try pydub (requires ffmpeg installed)
        try:
            from pydub import AudioSegment
            seg = AudioSegment.from_file(io.BytesIO(data))
            seg = seg.set_channels(1).set_sample_width(2)  # mono, 16-bit
            samples = np.frombuffer(seg.raw_data, dtype=np.int16).astype(np.float32) / 32768.0
            sr = seg.frame_rate
            audio = samples
        except Exception as pydub_err:
            raise ValueError(
                f"Cannot decode audio — soundfile: {sf_err}; pydub: {pydub_err}"
            ) from sf_err

    # Ensure mono
    if audio.ndim == 2:
        audio = audio.mean(axis=1)

    return _resample(audio, sr, WHISPER_RATE)
