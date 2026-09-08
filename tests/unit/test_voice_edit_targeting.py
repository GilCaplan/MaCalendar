"""Editing by voice must hit the event the user referred to, not a random 'meeting'."""

import datetime
from types import SimpleNamespace

import pytest

from assistant.actions.calendar.action import _find_event
from assistant.db import CalendarDB
from assistant.intent.context import context_memory


@pytest.fixture
def db(tmp_path):
    return CalendarDB(path=str(tmp_path / "t.db"))


def _add(db, title, date, start):
    return db.create_event_from_dict({"title": title, "date": date, "start_time": start, "end_time": "23:00"})


def test_generic_word_alone_does_not_pick_an_arbitrary_event(db):
    _add(db, "Team meeting", "2026-08-25", "10:00")
    _add(db, "Meeting with Rina", "2026-08-26", "09:00")
    # "office meeting for the course" shares only the generic word "meeting"
    assert _find_event(db, "office meeting for the course I am the TA in", None) is None


def test_distinctive_word_wins_over_generic_overlap(db):
    _add(db, "Team meeting", "2026-08-25", "10:00")
    wanted = _add(db, "Meeting with Rina", "2026-08-26", "09:00")
    assert _find_event(db, "meeting with rina", None)["id"] == wanted


def test_date_pin_restricts_to_that_day(db):
    _add(db, "Meeting with Rina", "2026-08-26", "09:00")
    sunday = _add(db, "Office meeting", "2026-08-30", "13:00")
    assert _find_event(db, "meeting", "2026-08-30")["id"] == sunday


@pytest.fixture
def normalise():
    """The anaphor/date-pin rules live in the engine's validate stage now;
    drive them through its public object pass, same shapes as before."""
    from assistant.engine import load_config
    from assistant.engine.decompose_validate import validate
    from assistant.engine.state import EngineState, Item

    cfg = load_config()

    def _run(parsed, transcript, rule_actions):
        st = EngineState(raw_text=transcript, text=transcript)
        st.items = [Item(id=f"item_{i + 1}", kind="event", text=transcript,
                         action=name, intent=intent)
                    for i, (name, intent) in enumerate(parsed)]
        validate.run_objects(st, cfg)
        out = [(it.action, it.intent) for it in st.items if it.intent is not None]
        return out, [f.human() for f in st.fixes]

    return _run


def _upd(**kw):
    base = dict(match_title=None, match_date=None, match_start_time=None, new_date=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_just_made_becomes_anaphor(normalise):
    intent = _upd(match_title="office meeting for the course")
    out, fixes = normalise([("update_event", intent)], "The event you just made on Sunday, fix it so it is at 1pm", [])
    assert out[0][1].match_title == "it"
    assert any("last event" in f for f in fixes)


def test_weekday_in_sentence_pins_match_date(normalise):
    intent = _upd(match_title="meeting")
    out, _ = normalise([("update_event", intent)], "move the meeting on sunday to monday", [])
    d = datetime.date.fromisoformat(out[0][1].match_date)
    assert d.weekday() == 6                          # Sunday
    assert datetime.date.fromisoformat(out[0][1].new_date).weekday() == 0   # Monday


def test_explicit_match_date_is_kept(normalise):
    intent = _upd(match_title="dentist", match_date="2026-09-17")
    out, fixes = normalise([("update_event", intent)], "the one I just made, move it", [])
    assert out[0][1].match_date == "2026-09-17" and out[0][1].match_title == "dentist"
