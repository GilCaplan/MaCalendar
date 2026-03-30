import datetime
import os
import sqlite3
import sys

# Ensure assistant is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from assistant.actions import ActionRegistry
from assistant.actions.calendar.action import CreateEventAction, DeleteEventAction, UpdateEventAction
from assistant.config import OllamaConfig, AppConfig, load_config
from assistant.intent.parser import IntentParser
from assistant.db import CalendarDB

def clear_db():
    print("🧹 Clearing calendar DB for tests...")
    db = CalendarDB()
    with db._conn() as conn:
        conn.execute("DELETE FROM events")
    
    # Verify
    events = db.get_events_for_month(2026, 3) # Or any query
    assert len(events) == 0

def run_test(parser: IntentParser, config: AppConfig, transcript: str, expected_count: int, test_name: str, seed_data: list = None):
    print(f"\n==============================================")
    print(f"🎬 Test: {test_name}")
    print(f"Transcript: '{transcript}'")
    
    # 1. Clear DB before each test
    clear_db()
    
    # 1.5 Seed DB if provided
    if seed_data:
        db = CalendarDB()
        for seed in seed_data:
            db.create_event_from_dict(seed)

    # 2. Parse intents
    print("⏳ Parsing intents from Ollama...")
    actions_tuples = parser.parse(transcript)
    
    # Filter valid
    valid = [(name, intent) for name, intent in actions_tuples if name != "unknown"]
    print(f"🔍 Parsed {len(valid)} valid actions:")
    for n, i in valid:
        print(f"   -> {n}: {i}")
        
    # 3. Execute
    for action_name, intent in valid:
        action_cls = parser.registry.get(action_name)
        result = action_cls().execute(intent, config)
        print(f"✅ Executed: {result}")
        
    # 4. Verify DB state
    db = CalendarDB()
    with db._conn() as conn:
        rows = conn.execute("SELECT * FROM events").fetchall()
        
    print(f"📊 Final DB event count: {len(rows)}")
    for row in rows:
        print(f"   📅 [{row['date']}] {row['start_time']}-{row['end_time']} | {row['title']} | {row['description']}")
        
    # 5. Assertions
    assert len(rows) == expected_count, f"❌ Failed {test_name}: Expected {expected_count} events, got {len(rows)}"
    print(f"🟢 Passed {test_name}!")
    return rows


def main():
    # 1. Setup config and parser
    registry = ActionRegistry()
    
    config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'config.yaml'))
    config = load_config(config_path)
    
    # Force use the specified test model
    config.ollama.model = "llama3.1:8b"
    config.ollama.timeout_seconds = 180
    parser = IntentParser(config, registry)
    
    print("Checking Ollama backend connection at", config.ollama.base_url)
    if not parser.health_check():
        print("❌ Ollama is offline or not responding. Ensure `ollama serve` is running.\n")
        sys.exit(1)

    print("✅ Ollama is online. Starting tests...\n")
    
    tomorrow = datetime.date.today() + datetime.timedelta(days=1)
    
    # --- SCENARIO 1: The user's exact complex phrase ---
    t1 = ("Set an event for tomorrow at 10 a.m., 2 p.m., and 3 p.m. "
          "For now, while the first one is, I'll meet up with a friend. "
          "The second one is, I'm going to Tel Aviv. "
          "And the third one is, doing some activity. Thanks.")
    # Expecting 3 distinct events created based on multi-action parser
    rows_1 = run_test(parser, config, transcript=t1, expected_count=3, test_name="Complex Multi-Event Creation")
    
    # Further validation for Scenario 1
    titles = [r["title"].lower() for r in rows_1]
    descriptions = [r["description"].lower() for r in rows_1]
    
    assert any("friend" in d for d in descriptions) or any("friend" in t for t in titles), "Failed to find 'friend' in resulting events"
    assert any("tel aviv" in d for d in descriptions) or any("tel aviv" in t for t in titles), "Failed to find 'Tel Aviv' in resulting events"


    # --- SCENARIO 2: Single simple event ---
    t2 = "Schedule a daily standup for 10am tomorrow, repeating daily."
    # Since it repeats, testing how many instances the DB created (up to 365 days max)
    # Let's just recount from DB because my test logic executes to real DB.
    # The default for "daily" in db.py generates up to 1 year if recur_until is missing
    # or max_instances = 365/500 depending on hard cap. The DB code limits instance generations.
    print(f"\n==============================================")
    print(f"🎬 Test: Simple Recurring Event")
    clear_db()
    
    valid = parser.parse(t2)
    valid = [(n, i) for n, i in valid if n != "unknown"]
    print(f"🔍 SCENARIO 2 PARSED:")
    for n, i in valid:
        print(f"   -> {n}: {i}")
        parser.registry.get(n)().execute(i, config)
        
    db = CalendarDB()
    with db._conn() as conn:
        all_rows = conn.execute("SELECT * FROM events").fetchall()
        count = len(all_rows)
        if count == 1:
            r = dict(all_rows[0])
            print("ONLY 1 ROW IN DB. Row data:", r)
        
    print(f"Recurring single action generated {count} events in DB.")
    assert count > 100, f"Recurring event didn't generate instances, built only {count}"
    print(f"🟢 Passed Simple Recurring Event!")


    # --- SCENARIO 3: Update + Delete mix (Difficulty: Hard) ---
    t3 = ("First, create a meeting on Friday at noon called 'Lunch Pitch'. "
          "Then, delete the Daily Standup. "
          "Finally, update the 'Lunch Pitch' to start at 1 PM instead.")
    seed3 = [{
        "title": "Daily Standup",
        "date": tomorrow.isoformat(),
        "start_time": "10:00",
        "end_time": "10:15"
    }]
    run_test(parser, config, transcript=t3, expected_count=1, test_name="Mixed Create, Update, and Delete", seed_data=seed3)
    # Only "Lunch Pitch" should remain (modified to 13:00)
    with db._conn() as conn:
        final_ev = conn.execute("SELECT * FROM events").fetchone()
        
    assert final_ev["start_time"] == "13:00", f"Failed update. Found time {final_ev['start_time']} instead of 13:00"
    assert "lunch pitch" in final_ev["title"].lower(), f"Wrong title: {final_ev['title']}"

    # --- SCENARIO 4: Recurring with explicit End Date ---
    t4 = "Add a weekly team sync for 9am every Monday, but only until June 1st."
    print(f"\n==============================================")
    print(f"🎬 Test: Recurring with End Date")
    clear_db()
    valid = parser.parse(t4)
    valid = [(n, i) for n, i in valid if n != "unknown"]
    print("🔍 SCENARIO 4 PARSED:")
    for n, i in valid:
        print(f"   -> {n}: {i}")
        parser.registry.get(n)().execute(i, config)
    with CalendarDB()._conn() as conn:
        s4_rows = conn.execute("SELECT * FROM events").fetchall()
    print(f"Recurring action with end date generated {len(s4_rows)} events.")
    assert len(s4_rows) > 0, "Failed to generate any events for Scenario 4"
    if len(s4_rows) > 0:
        print(f"Last event is on: {s4_rows[-1]['date']}")

    # --- SCENARIO 5: Vague Multiple Actions ---
    t5 = "I have a dentist appointment tomorrow at 8am, and cancel my 'Daily Standup'."
    seed5 = [{
        "title": "Daily Standup", "date": tomorrow.isoformat(), "start_time": "09:00", "end_time": "09:30"
    }]
    run_test(parser, config, transcript=t5, expected_count=1, test_name="Mixed Create and Delete", seed_data=seed5)

    # --- SCENARIO 6: Multi-Update ---
    t6 = "Move my 8am dentist appointment to 9am and change the title to 'Dental Surgery'."
    seed6 = [{
        "title": "Dentist Appointment", "date": tomorrow.isoformat(), "start_time": "08:00", "end_time": "09:00"
    }]
    run_test(parser, config, transcript=t6, expected_count=1, test_name="Multi-field Update", seed_data=seed6)
    with CalendarDB()._conn() as conn:
        s6_final = conn.execute("SELECT * FROM events").fetchone()
    assert s6_final["start_time"] == "09:00", "Failed to update start time"
    assert "surgery" in s6_final["title"].lower(), "Failed to update title"

    # --- SCENARIO 7: Very Simple Create ---
    t7 = "Create a workout session for today at 5 PM."
    run_test(parser, config, transcript=t7, expected_count=1, test_name="Simple Create Event")

    # --- SCENARIO 8: Very Simple Delete ---
    t8 = "Delete my dentist appointment for tomorrow."
    seed8 = [{
        "title": "Dentist Appointment", "date": tomorrow.isoformat(), "start_time": "14:00", "end_time": "15:00"
    }]
    run_test(parser, config, transcript=t8, expected_count=0, test_name="Simple Delete Event", seed_data=seed8)

    print("\n🎉 ALL TESTS PASSED SUCCESSFULLY! 🎉")

if __name__ == "__main__":
    main()
