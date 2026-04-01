"""Microphone audio capture with voice-activity-based silence detection."""

import logging
import threading
from typing import Callable, List, Optional

import numpy as np
import sounddevice as sd

from assistant.audio.probe import WHISPER_RATE, probe_audio
from assistant.config import AudioConfig
from assistant.exceptions import AudioCaptureError

logger = logging.getLogger(__name__)

# Global lock — only one InputStream may be open at a time
_audio_lock = threading.Lock()

# Calibration: sample this many seconds at the start to measure ambient noise
_CALIBRATION_SEC = 0.5


def _resample(audio: np.ndarray, orig_rate: int, target_rate: int) -> np.ndarray:
    """Linear interpolation resample — sufficient quality for speech."""
    if orig_rate == target_rate:
        return audio
    n_out = int(len(audio) * target_rate / orig_rate)
    return np.interp(
        np.linspace(0, len(audio) - 1, n_out),
        np.arange(len(audio)),
        audio,
    ).astype(np.float32)


class AudioCapture:
    """
    Records from the default microphone and stops automatically when:
      - Silence is detected (RMS < adaptive_threshold for silence_duration_sec), OR
      - stop() is called externally (button re-press), OR
      - The hard time cap (max_recording_sec) is reached.

    Uses the AudioDeviceProfile from probe.py (cached at startup) so the
    sample rate, dtype and channel count are always compatible with this Mac.
    Audio is always returned at WHISPER_RATE (16 kHz) regardless of the
    device's native rate.
    """

    def __init__(self, config: AudioConfig) -> None:
        self.config = config
        self._stop_event = threading.Event()
        # Profile is already cached by main.py; this is just a fast read
        self._profile = probe_audio()

    def stop(self) -> None:
        """Signal the current recording to stop immediately."""
        self._stop_event.set()

    def record_until_silence(
        self,
        streaming_callback: Optional[Callable[[np.ndarray], None]] = None,
        streaming_interval_sec: float = 2.0,
    ) -> np.ndarray:
        """
        Open the mic and accumulate audio chunks.
        Stops when RMS amplitude stays below the adaptive threshold
        for silence_duration_sec, stop() is called, or after max_recording_sec.

        streaming_callback receives already-resampled 16 kHz audio every
        streaming_interval_sec so the stream-checker STT always gets valid input.

        Returns: float32 numpy array at WHISPER_RATE (16 kHz), shape (N,).
        """
        if not self._profile.permission_ok:
            raise AudioCaptureError(
                "Microphone access denied. "
                "Open System Settings → Privacy & Security → Microphone and allow this app."
            )

        self._stop_event.clear()

        rate = self._profile.record_rate
        dtype = self._profile.dtype
        channels = self._profile.channels

        frames: List[np.ndarray] = []
        silence_counter = [0.0]

        chunk_size = int(rate * 0.1)                        # 100 ms chunks
        calibration_chunks = int(_CALIBRATION_SEC / 0.1)
        silence_chunks_needed = self.config.silence_duration_sec / 0.1
        max_chunks = int(self.config.max_recording_sec / 0.1)
        chunk_count = [0]

        adaptive_threshold = [self.config.silence_threshold]
        calibration_rms: List[float] = []

        def callback(indata: np.ndarray, _frames_count: int, _time_info, _status) -> None:  # noqa: ARG001
            # Normalise int16 → float32 so RMS maths is always consistent
            chunk = indata[:, 0].copy().astype(np.float32)
            if dtype == "int16":
                chunk = chunk / 32768.0
            frames.append(chunk)
            chunk_count[0] += 1

            rms = float(np.sqrt(np.mean(chunk ** 2)))

            if chunk_count[0] <= calibration_chunks:
                calibration_rms.append(rms)
                if chunk_count[0] == calibration_chunks:
                    ambient = float(np.mean(calibration_rms))
                    adaptive_threshold[0] = max(self.config.silence_threshold, ambient * 1.5)
                return

            if rms < adaptive_threshold[0]:
                silence_counter[0] += 1
            else:
                silence_counter[0] = 0

            if silence_counter[0] >= silence_chunks_needed or chunk_count[0] >= max_chunks:
                self._stop_event.set()

            interval_chunks = int(streaming_interval_sec / 0.1)
            if streaming_callback and chunk_count[0] % interval_chunks == 0:
                raw = np.concatenate(frames).astype(np.float32)
                resampled = _resample(raw, rate, WHISPER_RATE)
                threading.Thread(
                    target=streaming_callback, args=(resampled,), daemon=True
                ).start()

        if not _audio_lock.acquire(blocking=False):
            raise AudioCaptureError("Audio capture already in progress.")

        try:
            self._try_open(rate, channels, dtype, chunk_size, callback)
        finally:
            _audio_lock.release()

        if not frames:
            raise AudioCaptureError("No audio recorded.")

        raw = np.concatenate(frames).astype(np.float32)
        return _resample(raw, rate, WHISPER_RATE)

    def _try_open(
        self,
        rate: int,
        channels: int,
        dtype: str,
        chunk_size: int,
        callback,
    ) -> None:
        """Open the InputStream, retrying once after a full PortAudio reinit."""
        try:
            self._open_stream(rate, channels, dtype, chunk_size, callback)
        except sd.PortAudioError:
            logger.warning("PortAudio error on stream open — reinitialising and retrying.")
            try:
                sd._terminate()
                sd._initialize()
                # Re-probe so the next recording also gets fresh settings
                from assistant.audio.probe import probe_audio as _probe
                self._profile = _probe(force=True)
            except Exception:
                pass
            try:
                self._open_stream(rate, channels, dtype, chunk_size, callback)
            except sd.PortAudioError as exc:
                raise AudioCaptureError(
                    f"Could not open microphone after reinit: {exc}\n"
                    "Check System Settings → Privacy & Security → Microphone."
                ) from exc

    def _open_stream(
        self,
        rate: int,
        channels: int,
        dtype: str,
        chunk_size: int,
        callback,
    ) -> None:
        with sd.InputStream(
            samplerate=rate,
            channels=channels,
            dtype=dtype,
            blocksize=chunk_size,
            callback=callback,
        ):
            self._stop_event.wait(timeout=self.config.max_recording_sec + 1)
