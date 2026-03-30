#!/usr/bin/env python3
"""
Component test: Full pipeline from text → Outlook calendar event

Skips microphone and STT — you type (or pass) the transcript directly.
Use this to test the Ollama → confirmation → Graph API chain end-to-end
without needing to speak.

Usage:
    python scripts/test_pipeline.py
    python scripts/test_pipeline.py "Schedule a call with Alice tomorrow at 3pm"
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import assistant.actions.calendar  # noqa

from assistant.actions import registry
from assistant.config import load_config
from assistant.intent.parser import OllamaIntentParser, UnknownIntent
from assistant.actions.calendar.handler import CalendarHandler
from assistant.confirmation.handler import ConfirmationHandler
from assistant.tts.speaker import Speaker
from assistant.exceptions import AuthExpiredError


DEFAULT = "Schedule a meeting called Weekly Sync tomorrow at 10am"


def main():
    transcript = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    print(f"\nTranscript: \"{transcript}\"\n")

    config = load_config("config.yaml")
    speaker = Speaker(config.tts)

    # 1. Parse intent
    parser = OllamaIntentParser(config.ollama, registry)
    if not parser.health_check():
        print("[Error] Ollama is not running. Start it with: ollama serve")
        sys.exit(1)

    print("Parsing intent with Ollama...")
    action_name, intent = parser.parse(transcript)
    print(f"Action: {action_name}")

    if action_name == "unknown" or isinstance(intent, UnknownIntent):
        print("No matching action found.")
        sys.exit(0)

    print("Intent fields:")
    for k, v in intent.model_dump().items():
        print(f"  {k}: {v}")
    print()

    # 2. Confirmation
    confirmer = ConfirmationHandler(config.confirmation_level)
    if not confirmer.check(action_name, intent):
        print("Cancelled by user.")
        sys.exit(0)

    # 3. Execute
    print("Creating calendar event...")
    action_cls = registry.get(action_name)
    if action_cls is None:
        print(f"[Error] No handler for action '{action_name}'")
        sys.exit(1)

    try:
        action = action_cls()
        result_text = action.execute(intent, config)
        print(f"\n✅ {result_text}")
        speaker.speak_sync(result_text)
    except AuthExpiredError:
        print("[Error] Microsoft token expired. Run: python scripts/setup_auth.py")
        sys.exit(1)
    except Exception as e:
        print(f"[Error] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
