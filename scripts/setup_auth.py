#!/usr/bin/env python3
"""
One-time Microsoft OAuth setup via device-code flow.

Run this before using the assistant for the first time:
    python scripts/setup_auth.py

You'll be given a URL and a short code to enter. Sign in with your
Microsoft 365 account and grant the requested permissions.
"""

import os
import sys

# Allow running from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assistant.config import load_config
from assistant.actions.calendar.auth import MSALAuth


def main():
    print("Loading config...")
    try:
        config = load_config("config.yaml")
    except Exception as e:
        print(f"\n[Error] {e}")
        sys.exit(1)

    if config.microsoft.client_id == "YOUR_AZURE_APP_CLIENT_ID":
        print(
            "\n[Error] You need to set your Azure App client_id in config.yaml.\n"
            "See the README for instructions on registering an Azure app."
        )
        sys.exit(1)

    print(f"\nClient ID: {config.microsoft.client_id}")
    print(f"Tenant: {config.microsoft.tenant_id}")
    print(f"Token cache: {config.microsoft.token_cache_path}\n")

    auth = MSALAuth(config.microsoft)

    print("Starting device-code authentication flow...")
    print("─" * 60)
    try:
        token = auth.device_code_flow()
        print("─" * 60)
        print("\n✅ Authentication successful!")
        cache_path = os.path.expanduser(config.microsoft.token_cache_path)
        print(f"   Token saved to: {cache_path}")
        print("\nYou can now run the assistant. Tokens will refresh automatically.")
    except Exception as e:
        print(f"\n[Error] Authentication failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
