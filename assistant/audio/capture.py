"""Microphone audio capture with voice-activity-based silence detection."""

import logging
import threading
from typing import Callable, List, Optional

import numpy as np
import sounddevice as sd

from assistant.config import AudioConfig
from assistant.exceptions import AudioCaptureError

logger = logging.getLogger(__name__)

# Calibration: sample this many seconds at the start to measure ambient noise
_CALIBRATION_SEC = 0.5

# Whisper always expects 16 kHz — resample to this if device runs at a different rate
_WHISPER_RATE = 16_000

# Global lock — only one InputStream may be open at a time
_audio_lock = threading.Lock()


def _resample(audio: np.ndarray, orig_rate: int, target_rate: int) -> np.ndarray:
    """Linear interpolation resample — good enough quality for speech."""
    if orig_rate == target_rate:
        return audio
    n_out = int(len(audio) * target_rate / orig_rate)
    return np.interp(
        np.linspace(0, len(audio) - 1, n_out),
        np.arange(len(audio)),
        audio,
    ).astype(np.float32)


def _resolve_sample_rate(configured_rate: int) -> int:
    """
    Return the rate to actually record at.
    Tries the configured rate first; if the device rejects it, falls back to
    the device's native rate so CoreAudio doesn't produce AUHAL errors.
    """
    try:
        sd.check_input_settings(samplerate=configured_rate, channels=1, dtype="float32")
        return configured_rate
    except Exception:
        pass
    try:
        info = sd.query_devices(kind="input")
        native = int(info["default_samplerate"])
        if native > 0:
            logger.info(
                "Audio device does not support %d Hz; recording at native %d Hz and resampling.",
                configured_rate, native,
            )
            return native
    except Exception:
        pass
    return 44_100  # safe universal fallback


class AudioCapture:
    """
    Records from the default microphone and stops automatically when:
      - Silence is detected (RMS < adaptive_threshold for silence_duration_sec), OR
      - stop() is called externally (button re-press), OR
      - The hard time cap (max_recording_sec) is reached.

    The silence threshold is automatically raised to 1.5× the ambient noise
    floor measured during the first 0.5 seconds, so fans and background noise
    don't prevent auto-stop.

    Audio is always returned at _WHISPER_RATE (16 kHz) regardless of the
    device's native sample rate.
    """

    def __init__(self, config: AudioConfig) -> None:
        self.config = config
        self._stop_event: threading.Event = threading.Event()

    def stop(self) -> None:
        """Signal the current recording to stop immediately."""
        self._stop_event.set()

    def _open_stream(self, sample_rate: int, chunk_size: int, callback) -> None:
        with sd.InputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
            blocksize=chunk_size,
            callback=callback,
        ):
            self._stop_event.wait(timeout=self.config.max_recording_sec + 1)

    def record_until_silence(
        self,
        streaming_callback: Optional[Callable[[np.ndarray], None]] = None,
        streaming_interval_sec: float = 2.0,
    ) -> np.ndarray:
        """
        Open the mic and accumulate audio chunks.
        Stops when RMS amplitude stays below the adaptive threshold
        for silence_duration_sec consecutive seconds, stop() is called,
        or after max_recording_sec.

        If streaming_callback is provided, it is called every streaming_interval_sec
        with the current recording buffer (already resampled to 16 kHz) on a
        background thread.

        Returns:
            float32 numpy array at _WHISPER_RATE (16 kHz), shape (N,).
        """
        self._stop_event.clear()

        record_rate = _resolve_sample_rate(self.config.sample_rate)

        frames: List[np.ndarray] = []
        silence_counter = [0.0]

        chunk_size = int(record_rate * 0.1)           # 100 ms chunks
        calibration_chunks = int(_CALIBRATION_SEC / 0.1)
        silence_chunks_needed = self.config.silence_duration_sec / 0.1
        max_chunks = int(self.config.max_recording_sec / 0.1)
        chunk_count = [0]

        adaptive_threshold = [self.config.silence_threshold]
        calibration_rms: List[float] = []

        def callback(indata: np.ndarray, frames_count: int, time_info, status) -> None:
            chunk = indata[:, 0].copy()  # mono
            frames.append(chunk)
            chunk_count[0] += 1

            rms = float(np.sqrt(np.mean(chunk ** 2)))

            # Calibration phase — measure ambient noise floor
            if chunk_count[0] <= calibration_chunks:
                calibration_rms.append(rms)
                if chunk_count[0] == calibration_chunks:
                    ambient = float(np.mean(calibration_rms))
                    adaptive_threshold[0] = max(
                        self.config.silence_threshold,
                        ambient * 1.5,
                    )
                return  # don't count calibration chunks as silence

            # Post-calibration silence detection
            if rms < adaptive_threshold[0]:
                silence_counter[0] += 1
            else:
                silence_counter[0] = 0

            if (
                silence_counter[0] >= silence_chunks_needed
                or chunk_count[0] >= max_chunks
            ):
                self._stop_event.set()

            # Streaming callback — pass resampled audio to STT checker
            if streaming_callback and chunk_count[0] % int(streaming_interval_sec / 0.1) == 0:
                raw = np.concatenate(frames).astype(np.float32)
                resampled = _resample(raw, record_rate, _WHISPER_RATE)
                threading.Thread(
                    target=streaming_callback, args=(resampled,), daemon=True
                ).start()

        if not _audio_lock.acquire(blocking=False):
            raise AudioCaptureError("Audio capture already in progress.")

        try:
            self._try_open(record_rate, chunk_size, callback)
        finally:
            _audio_lock.release()

        if not frames:
            raise AudioCaptureError("No audio recorded.")

        raw = np.concatenate(frames).astype(np.float32)
        return _resample(raw, record_rate, _WHISPER_RATE)

    def _try_open(self, sample_rate: int, chunk_size: int, callback) -> None:
        """Open stream, retrying once after a full PortAudio reinit if needed."""
        try:
            self._open_stream(sample_rate, chunk_size, callback)
        except sd.PortAudioError:
            logger.warning("PortAudio error on first open — reinitialising and retrying.")
            try:
                sd._terminate()
                sd._initialize()
                self._open_stream(sample_rate, chunk_size, callback)
            except sd.PortAudioError as e:
                raise AudioCaptureError(
                    f"Could not open microphone: {e}\n"
                    "Check System Preferences → Privacy & Security → Microphone."
                ) from e
