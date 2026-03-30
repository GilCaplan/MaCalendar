#!/usr/bin/env python3
"""
Component test: Microsoft Graph API calendar event creation

Creates a test event in your Outlook calendar and prints the result.
The event is titled "ASSISTANT TEST - DELETE ME" so you can find and
delete it easily.

Requires: setup_auth.py to have been run first.

Usage:
    python scripts/test_graph.py
    python scripts/test_graph.py --title "My Test Event" --date 2026-05-01 --time 14:00
"""

import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assistant.config import load_config
from assistant.actions.calendar.auth import MSALAuth
from assistant.actions.calendar.graph_client import GraphClient
from assistant.actions.calendar.intent import CalendarIntent
from assistant.actions.calendar.event_builder import build_event_payload
from assistant.exceptions import AuthExpiredError


def main():
    parser = argparse.ArgumentParser(description="Test Microsoft Graph calendar integration.")
    parser.add_argument("--title", default="ASSISTANT TEST - DELETE ME")
    parser.add_argument("--date", default=None, help="YYYY-MM-DD (default: tomorrow)")
    parser.add_argument("--time", default="23:30", help="HH:MM 24h (default: 23:30)")
    args = parser.parse_args()

    config = load_config("config.yaml")

    date = args.date or (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    start_time = args.time
    start_dt = datetime.datetime.strptime(f"{date}T{start_time}", "%Y-%mT%H:%M")
    end_time = (datetime.datetime.strptime(start_time, "%H:%M") + datetime.timedelta(hours=1)).strftime("%H:%M")

    intent = CalendarIntent(
        title=args.title,
        date=date,
        start_time=start_time,
        end_time=end_time,
    )

    print(f"Creating test event:")
    print(f"  Title: {intent.title}")
    print(f"  Date:  {intent.date}")
    print(f"  Time:  {intent.start_time} – {intent.end_time}")
    print()

    auth = MSALAuth(config.microsoft)
    try:
        token = auth.get_token()
    except AuthExpiredError:
        print("[Error] Token expired or missing. Run: python scripts/setup_auth.py")
        sys.exit(1)

    client = GraphClient(auth)

    tz = str(datetime.datetime.now().astimezone().tzname()) or "UTC"
    payload = build_event_payload(intent, tz)

    try:
        event = client.create_event(payload)
    except Exception as e:
        print(f"[Error] Graph API call failed: {e}")
        sys.exit(1)

    print(f"✅ Event created!")
    print(f"   ID:      {event.get('id', 'N/A')[:40]}...")
    print(f"   Subject: {event.get('subject')}")
    print(f"   Link:    {event.get('webLink', 'N/A')}")
    print()
    print("⚠️  Remember to delete this test event from your Outlook calendar.")


if __name__ == "__main__":
    main()
