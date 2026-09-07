

def test_all_day_speak_becomes_a_day_block_not_a_dropped_event():
    from assistant.actions.calendar.intent import CalendarIntent
    """Era-2 cycle 2: the LLM answers a dated-no-clock ask with the WORDS
    ('all day') and the HH:MM rule threw the whole event away — "Add a party
    in NY city for this saturday" died on start_time='all day'. All-day-speak
    is a 00:00 start (fill_defaults completes the block); vague non-times
    fall back to missing and take the normal defaults."""
    it = CalendarIntent(title="party in NY city", date="2026-09-12",
                        start_time="all day", end_time="all day")
    assert it.start_time == "00:00" and it.end_time == "23:59"
    it2 = CalendarIntent(title="conversation with Greg", date="2026-09-21",
                         start_time="any time")
    assert it2.start_time is not None  # defaulted, not rejected
