"""Local Whisper STT via faster-whisper (CTranslate2 int8 — fast on Apple Silicon)."""

import numpy as np

from assistant.config import WhisperConfig
from assistant.exceptions import WhisperError
from assistant.stt.base import STTProvider


class WhisperSTT(STTProvider):
    """
    Uses faster-whisper with CTranslate2 backend.

    On Apple Silicon (M-series), device="cpu" with compute_type="int8" is
    recommended. CTranslate2's int8 CPU kernels are extremely fast on M-series
    chips (~0.1x real-time factor for the 'base' model), and MPS backend support
    in CTranslate2 is limited as of faster-whisper 1.x.
    """

    def __init__(self, config: WhisperConfig) -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as e:
            raise WhisperError(
                "faster-whisper is not installed. Run: pip install faster-whisper"
            ) from e

        self._language = config.language
        try:
            self._model = WhisperModel(
                config.model_size,
                device=config.device,
                compute_type=config.compute_type,
            )
        except Exception as e:
            raise WhisperError(f"Failed to load Whisper model '{config.model_size}': {e}") from e

    def transcribe(self, audio: np.ndarray) -> str:
        try:
            segments, _ = self._model.transcribe(
                audio,
                language=self._language,
                beam_size=5,
                vad_filter=True,  # built-in VAD strips silence
            )
            return " ".join(seg.text.strip() for seg in segments).strip()
        except Exception as e:
            raise WhisperError(f"Whisper transcription failed: {e}") from e
