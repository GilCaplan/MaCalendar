"""Abstract base class for speech-to-text providers."""

from abc import ABC, abstractmethod

import numpy as np


class STTProvider(ABC):
    @abstractmethod
    def transcribe(self, audio: np.ndarray) -> str:
        """
        Transcribe audio to text.

        Args:
            audio: float32 numpy array, shape (N,), values in [-1, 1], 16kHz mono.

        Returns:
            Transcript string. Empty string if nothing was recognised.
        """
        ...
