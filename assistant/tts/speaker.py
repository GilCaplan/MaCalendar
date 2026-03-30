"""Text-to-speech via macOS `say` command."""

import subprocess

from assistant.config import TTSConfig


class Speaker:
    """Wraps the macOS `say` command for TTS output."""

    def __init__(self, config: TTSConfig) -> None:
        self.mute = config.mute
        self.voice = config.voice
        self.rate = config.rate

    def speak(self, text: str) -> None:
        """
        Non-blocking TTS — pipeline continues while speech plays.
        Use speak_sync() when you need to wait for speech to finish.
        """
        if self.mute:
            return
            
        subprocess.Popen(
            ["say", "-v", self.voice, "-r", str(self.rate), text],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def speak_sync(self, text: str) -> None:
        """Blocking TTS — waits until speech finishes."""
        if self.mute:
            return
            
        subprocess.run(
            ["say", "-v", self.voice, "-r", str(self.rate), text],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
