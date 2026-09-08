

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


# --- "now" is a time the speaker gave (real usage, 2026-09-08) --------------
#
# The same shape the all-day test above pins: the model answers with WORDS
# where the schema wants HH:MM, and the strict validator throws the whole
# event away rather than reading them.

def test_now_resolves_to_the_clock_instead_of_failing_validation():
    """"go out for a run NOW" is a command with a time in it.

    It used to be rejected: the model returned start_time="now", the HH:MM
    validator raised, the item was discarded, and the engine blamed
    SEGMENTATION — re-running it three times to the same answer before
    apologising after 30 seconds, for a command it had understood.
    """
    import datetime as _dt
    import re as _re
    from assistant.actions.calendar.intent import CalendarIntent

    now = _dt.datetime.now()
    for word in ("now", "right now", "immediately", "asap",
                 "straight away", "at once"):
        it = CalendarIntent(title="Run", start_time=word)
        assert _re.fullmatch(r"\d{2}:\d{2}", it.start_time), (word, it.start_time)
        hh, mm = map(int, it.start_time.split(":"))
        assert abs((hh * 60 + mm) - (now.hour * 60 + now.minute)) <= 2, word


def test_an_event_that_starts_and_ends_at_the_same_moment_gets_a_duration():
    """Both ends of "a run now" resolve to the same clock reading, and a
    zero-length event is not something a speaker asks for."""
    from assistant.actions.calendar.intent import CalendarIntent

    it = CalendarIntent(title="Run", start_time="now", end_time="now")
    assert it.end_time != it.start_time
    sh, sm = map(int, it.start_time.split(":"))
    eh, em = map(int, it.end_time.split(":"))
    assert (eh * 60 + em) - (sh * 60 + sm) == 60 or it.end_time == "23:59"


def test_a_real_clock_time_is_still_taken_literally():
    """The `now` shortcut must not swallow ordinary times."""
    from assistant.actions.calendar.intent import CalendarIntent

    assert CalendarIntent(title="Gym", start_time="7pm").start_time == "19:00"
    assert CalendarIntent(title="Gym", start_time="07:15").start_time == "07:15"
