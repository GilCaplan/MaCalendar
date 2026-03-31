"""Microphone audio capture with voice-activity-based silence detection."""

import threading
from typing import List

import numpy as np
import sounddevice as sd

from assistant.config import AudioConfig
from assistant.exceptions import AudioCaptureError

# Calibration: sample this many seconds at the start to measure ambient noise
_CALIBRATION_SEC = 0.5

# Global lock — only one InputStream may be open at a time
_audio_lock = threading.Lock()


class AudioCapture:
    """
    Records from the default microphone and stops automatically when:
      - Silence is detected (RMS < adaptive_threshold for silence_duration_sec), OR
      - stop() is called externally (button re-press), OR
      - The hard time cap (max_recording_sec) is reached.

    The silence threshold is automatically raised to 1.5× the ambient noise
    floor measured during the first 0.5 seconds, so fans and background noise
    don't prevent auto-stop.
    """

    def __init__(self, config: AudioConfig) -> None:
        self.config = config
        self._stop_event: threading.Event = threading.Event()

    def stop(self) -> None:
        """Signal the current recording to stop immediately."""
        self._stop_event.set()

    def _open_stream(self, chunk_size: int, callback) -> None:
        with sd.InputStream(
            samplerate=self.config.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=chunk_size,
            callback=callback,
        ):
            self._stop_event.wait(timeout=self.config.max_recording_sec + 1)

    def record_until_silence(
        self,
        streaming_callback: "Optional[Callable[[np.ndarray], None]]" = None,
        streaming_interval_sec: float = 2.0,
    ) -> np.ndarray:
        """
        Open the mic and accumulate audio chunks.
        Stops when RMS amplitude stays below the adaptive threshold
        for silence_duration_sec consecutive seconds, stop() is called,
        or after max_recording_sec.

        If streaming_callback is provided, it is called every streaming_interval_sec
        with the current recording buffer on a background thread.

        Returns:
            float32 numpy array of shape (N,), values in [-1, 1].
        """
        self._stop_event.clear()
        frames: List[np.ndarray] = []
        silence_counter = [0.0]

        chunk_size = int(self.config.sample_rate * 0.1)  # 100ms chunks
        calibration_chunks = int(_CALIBRATION_SEC / 0.1)  # first N chunks = calibration
        silence_chunks_needed = self.config.silence_duration_sec / 0.1
        max_chunks = int(self.config.max_recording_sec / 0.1)
        chunk_count = [0]

        # Adaptive threshold — starts at config value, raised after calibration
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
                    # Raise threshold to 1.5× ambient, but never below config minimum
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

            # Handle streaming chunk transcription on a background thread
            if streaming_callback and chunk_count[0] % int(streaming_interval_sec / 0.1) == 0:
                # Copy current frames to avoid thread mutation
                current_audio = np.concatenate(frames).astype(np.float32)
                threading.Thread(target=streaming_callback, args=(current_audio,), daemon=True).start()

        if not _audio_lock.acquire(blocking=False):
            raise AudioCaptureError("Audio capture already in progress.")

        try:
            self._open_stream(chunk_size, callback)
        except sd.PortAudioError:
            # PortAudio sometimes needs a full reinitialize after a device change
            # or macOS revokes the audio unit. Terminate, reinit, and retry once.
            try:
                sd._terminate()
                sd._initialize()
                self._open_stream(chunk_size, callback)
            except sd.PortAudioError as e:
                raise AudioCaptureError(
                    f"Could not open microphone: {e}\n"
                    "Check System Preferences → Security & Privacy → Microphone."
                ) from e
        finally:
            _audio_lock.release()

        if not frames:
            raise AudioCaptureError("No audio recorded.")

        return np.concatenate(frames).astype(np.float32)
