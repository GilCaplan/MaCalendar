"""Whisper on Apple Silicon GPU via MLX (mlx-whisper).

faster-whisper (CTranslate2) has no Metal/MPS backend, so it runs on CPU.
mlx-whisper runs the same Whisper weights on the M-series GPU through Apple's
MLX framework. Select with ``stt_engine: "mlx"`` in config.yaml.

Models are pulled from Hugging Face on first use (e.g.
``mlx-community/whisper-base-mlx``, ``…/whisper-small-mlx``,
``…/whisper-large-v3-turbo``) and cached in ~/.cache/huggingface.
"""

from __future__ import annotations

import logging
import os

import numpy as np

from assistant.exceptions import WhisperError
from assistant.stt.base import STTProvider

logger = logging.getLogger(__name__)


class MlxWhisperSTT(STTProvider):
    def __init__(self, config) -> None:
        try:
            import mlx_whisper  # noqa: F401
        except ImportError as e:
            raise WhisperError(
                "mlx-whisper is not installed. Run: pip install mlx-whisper"
            ) from e
        self._model = self._resolve_local(config.model)
        self._language = config.language
        # Load weights now so the first command doesn't pay the download/compile cost.
        try:
            self.transcribe(np.zeros(16000, dtype=np.float32))
        except Exception as e:  # pragma: no cover — surfaced on first real call instead
            logger.warning("MLX whisper warm-up failed: %s", e)

    @staticmethod
    def _resolve_local(model: str) -> str:
        """Turn a HF repo id into the cached directory on disk, once.

        Handed a repo id, mlx_whisper asks huggingface.co to resolve the
        revision on every single load — a network round trip that downloads
        0 bytes because the weights are already cached. It made every server
        restart slower, printed a download bar for a download that was not
        happening, and meant an assistant that is otherwise entirely local
        could not start without the internet.

        Resolving to the local snapshot path skips the hub completely.
        Anything that already looks like a path is passed straight through,
        and if the model is genuinely not cached yet the repo id is returned so
        the first run can still fetch it.
        """
        if os.path.isdir(model):
            return model
        try:
            from huggingface_hub import snapshot_download
            path = snapshot_download(model, local_files_only=True)
            logger.info("Whisper model resolved from cache: %s", path)
            return path
        except Exception as exc:
            logger.info("Whisper model %s not in the local cache (%s) — "
                        "fetching it this once", model, type(exc).__name__)
            return model

    def transcribe(self, audio: np.ndarray) -> str:
        import mlx_whisper

        initial_prompt = None
        try:
            from assistant.stt.vocab import get_vocab
            initial_prompt = get_vocab().whisper_prompt()
        except Exception:
            initial_prompt = None
        try:
            result = mlx_whisper.transcribe(
                audio.astype(np.float32),
                path_or_hf_repo=self._model,
                language=self._language,
                initial_prompt=initial_prompt,
                fp16=True,
                condition_on_previous_text=False,
                no_speech_threshold=0.6,
            )
            return (result.get("text") or "").strip()
        except Exception as e:
            raise WhisperError(f"MLX Whisper transcription failed: {e}") from e
