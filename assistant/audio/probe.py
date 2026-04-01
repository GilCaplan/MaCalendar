"""
Audio device probe — runs once at startup to find settings that actually work
on this Mac, so the first recording never hits a PortAudio / AUHAL error.

Usage
-----
    from assistant.audio.probe import probe_audio, AudioDeviceProfile
    profile = probe_audio()   # cached after first call
    print(profile)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Rates to try, in preference order.
# CoreAudio / AUHAL natively converts between hardware rates, but some
# USB/Bluetooth devices or software loopbacks only accept specific values.
_CANDIDATE_RATES = [16_000, 44_100, 48_000, 22_050, 8_000]

# Whisper always wants 16 kHz — we resample to this after recording
WHISPER_RATE = 16_000


@dataclass
class AudioDeviceProfile:
    """Everything AudioCapture needs to open the mic without errors."""
    device_name: str = "unknown"
    record_rate: int = 16_000       # rate to actually open the stream at
    needs_resample: bool = False    # True when record_rate != WHISPER_RATE
    channels: int = 1
    dtype: str = "float32"
    permission_ok: bool = True
    warnings: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        lines = [
            f"  Device      : {self.device_name}",
            f"  Record rate : {self.record_rate} Hz"
            + (" (resampled → 16 kHz for Whisper)" if self.needs_resample else ""),
            f"  Channels    : {self.channels}",
            f"  dtype       : {self.dtype}",
            f"  Mic access  : {'✓' if self.permission_ok else '✗ DENIED'}",
        ]
        for w in self.warnings:
            lines.append(f"  ⚠  {w}")
        return "\n".join(lines)


# Module-level cache — probe_audio() only runs the full detection once
_cached_profile: Optional[AudioDeviceProfile] = None


def probe_audio(force: bool = False) -> AudioDeviceProfile:
    """
    Detect the best audio settings for this machine.

    Tries each candidate sample rate with a real (silent) InputStream to
    confirm CoreAudio will accept it — not just a settings check, which can
    lie on some AUHAL paths.  Caches the result so subsequent calls are free.

    Args:
        force: Re-run even if a cached profile exists.
    """
    global _cached_profile
    if _cached_profile is not None and not force:
        return _cached_profile

    profile = _run_probe()
    _cached_profile = profile
    return profile


def _run_probe() -> AudioDeviceProfile:
    import sounddevice as sd

    profile = AudioDeviceProfile()

    # --- 1. Get device info ---
    try:
        info = sd.query_devices(kind="input")
        profile.device_name = info.get("name", "unknown")
        native_rate = int(info.get("default_samplerate", 44_100))
        max_ch = int(info.get("max_input_channels", 1))
        profile.channels = min(max_ch, 1)  # always mono for STT
    except Exception as exc:
        profile.warnings.append(f"Could not query device info: {exc}")
        native_rate = 44_100

    # Put native rate first so it's preferred when multiple rates work
    candidates = [native_rate] + [r for r in _CANDIDATE_RATES if r != native_rate]

    # --- 2. Find first working sample rate ---
    working_rate: Optional[int] = None
    for rate in candidates:
        if _can_open_stream(sd, rate, profile.channels, profile.dtype):
            working_rate = rate
            break

    if working_rate is None:
        # Last-ditch: try int16 at native rate (some USB mics refuse float32)
        profile.dtype = "int16"
        if _can_open_stream(sd, native_rate, profile.channels, "int16"):
            working_rate = native_rate
            profile.warnings.append(
                "Device only accepts int16; audio will be converted to float32."
            )

    if working_rate is None:
        profile.permission_ok = False
        profile.warnings.append(
            "No working sample rate found. Check System Settings → Privacy & Security → Microphone."
        )
        working_rate = WHISPER_RATE  # store a sane default even if broken

    profile.record_rate = working_rate
    profile.needs_resample = working_rate != WHISPER_RATE

    # --- 3. Quick mic-permission sanity check ---
    # Attempt a very short real recording — catches macOS permission denial
    # which only shows up at stream-open time, not at query time.
    try:
        import numpy as np
        buf: list = []

        def _cb(indata, frames, t, status):
            buf.append(indata.copy())

        with sd.InputStream(
            samplerate=working_rate,
            channels=profile.channels,
            dtype=profile.dtype,
            blocksize=int(working_rate * 0.1),
            callback=_cb,
        ):
            time.sleep(0.15)   # capture ~1 chunk

        if not buf:
            profile.warnings.append("Stream opened but no audio frames received.")
    except sd.PortAudioError as exc:
        err = str(exc)
        if "-10851" in err or "InvalidProperty" in err.replace(" ", ""):
            # Retry after full reinit — common after wake-from-sleep
            try:
                sd._terminate()
                sd._initialize()
            except Exception:
                pass
            profile.warnings.append("AUHAL error on first open; PortAudio reinitialized.")
        else:
            profile.permission_ok = False
            profile.warnings.append(f"Microphone permission denied or unavailable: {exc}")
    except Exception as exc:
        profile.warnings.append(f"Probe recording failed: {exc}")

    return profile


def _can_open_stream(sd, rate: int, channels: int, dtype: str) -> bool:
    """Return True if sounddevice accepts these settings without error."""
    try:
        sd.check_input_settings(samplerate=rate, channels=channels, dtype=dtype)
        return True
    except Exception:
        return False
