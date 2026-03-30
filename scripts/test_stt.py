#!/usr/bin/env python3
"""
Component test: Speech-to-Text

Records audio from your microphone and prints the transcript.
Use this to verify Whisper (or Google STT) is working before
testing the full pipeline.

Usage:
    python scripts/test_stt.py
    python scripts/test_stt.py --engine google
    python scripts/test_stt.py --model small   # larger = more accurate
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assistant.config import load_config, WhisperConfig, GoogleSTTConfig
from assistant.audio.capture import AudioCapture


def main():
    parser = argparse.ArgumentParser(description="Test speech-to-text.")
    parser.add_argument("--engine", choices=["whisper", "google"], default=None)
    parser.add_argument("--model", default=None, help="Whisper model size (tiny/base/small/medium)")
    args = parser.parse_args()

    config = load_config("config.yaml")

    engine = args.engine or config.stt_engine
    if args.model:
        config.whisper.model_size = args.model

    print(f"STT engine: {engine}")
    if engine == "whisper":
        print(f"Model: {config.whisper.model_size} ({config.whisper.compute_type} on {config.whisper.device})")
        print("Loading Whisper model (first run downloads it)...")
        from assistant.stt.whisper_stt import WhisperSTT
        stt = WhisperSTT(config.whisper)
    else:
        print("Using Google STT (free tier)...")
        from assistant.stt.google_stt import GoogleSTT
        stt = GoogleSTT(config.google_stt)

    audio_capture = AudioCapture(config.audio)

    print("\n🎙  Speak now... (stops automatically after silence)\n")
    try:
        start = time.time()
        audio = audio_capture.record_until_silence()
        duration = time.time() - start
        print(f"Recorded {duration:.1f}s of audio ({len(audio)} samples)\n")
    except Exception as e:
        print(f"[Error] Recording failed: {e}")
        sys.exit(1)

    print("Transcribing...")
    try:
        transcript = stt.transcribe(audio)
    except Exception as e:
        print(f"[Error] Transcription failed: {e}")
        sys.exit(1)

    if transcript:
        print(f"\n✅ Transcript: \"{transcript}\"")
    else:
        print("\n⚠️  No speech detected.")
        sys.exit(1)


if __name__ == "__main__":
    main()
