#!/usr/bin/env python3
"""
Component test: Ollama intent parsing

Sends a hardcoded (or custom) transcript to Ollama and prints
the parsed CalendarIntent. Use this to verify intent parsing
before testing the full pipeline.

Usage:
    python scripts/test_ollama.py
    python scripts/test_ollama.py "Book a call with Sarah next Monday at 3pm"
    python scripts/test_ollama.py --model mistral:7b-instruct-q4_K_M
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import assistant.actions.calendar  # noqa — registers CreateEventAction

from assistant.actions import registry
from assistant.config import load_config
from assistant.intent.parser import OllamaIntentParser, UnknownIntent


DEFAULT_PHRASE = "Schedule a team standup tomorrow at 10am for 30 minutes"


def main():
    parser = argparse.ArgumentParser(description="Test Ollama intent parsing.")
    parser.add_argument("phrase", nargs="?", default=DEFAULT_PHRASE)
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    config = load_config("config.yaml")
    if args.model:
        config.ollama.model = args.model

    print(f"Ollama URL: {config.ollama.base_url}")
    print(f"Model: {config.ollama.model}")
    print(f"\nTranscript: \"{args.phrase}\"\n")

    intent_parser = OllamaIntentParser(config.ollama, registry)

    if not intent_parser.health_check():
        print("[Error] Ollama is not running. Start it with: ollama serve")
        sys.exit(1)

    print("Parsing intent...")
    try:
        action_name, intent = intent_parser.parse(args.phrase)
    except Exception as e:
        print(f"[Error] {e}")
        sys.exit(1)

    print(f"\n✅ Action: {action_name}")

    if isinstance(intent, UnknownIntent):
        print("   (No matching action found)")
    else:
        fields = intent.model_dump()
        for key, value in fields.items():
            print(f"   {key}: {value}")

    print()


if __name__ == "__main__":
    main()
