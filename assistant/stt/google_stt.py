"""Google Cloud STT via the SpeechRecognition library (free tier)."""

import numpy as np

from assistant.config import GoogleSTTConfig
from assistant.exceptions import GoogleSTTError
from assistant.stt.base import STTProvider


class GoogleSTT(STTProvider):
    """
    Uses the SpeechRecognition library with Google's free STT endpoint.

    Free tier limitations: ~60 requests/min, internet required.
    For higher volume, supply a Google Cloud API key in config.yaml.
    """

    def __init__(self, config: GoogleSTTConfig) -> None:
        try:
            import speech_recognition as sr
            self._sr = sr
        except ImportError as e:
            raise GoogleSTTError(
                "SpeechRecognition is not installed. Run: pip install SpeechRecognition"
            ) from e

        self._recognizer = self._sr.Recognizer()
        self._api_key = config.api_key

    def transcribe(self, audio: np.ndarray) -> str:
        # Convert float32 [-1, 1] → int16 bytes for SpeechRecognition
        audio_int16 = (audio * 32767).astype(np.int16)
        audio_data = self._sr.AudioData(
            audio_int16.tobytes(),
            sample_rate=16000,
            sample_width=2,
        )

        try:
            if self._api_key:
                return self._recognizer.recognize_google_cloud(
                    audio_data, credentials_json=self._api_key
                )
            else:
                return self._recognizer.recognize_google(audio_data)
        except self._sr.UnknownValueError:
            return ""
        except self._sr.RequestError as e:
            raise GoogleSTTError(f"Google STT request failed: {e}") from e
