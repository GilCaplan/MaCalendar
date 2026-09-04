"""Step 4 — one test per named rule. The rules are survivors of real bugs;
each test carries its row number so the story is findable.
"""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest

import assistant.engine.llm as engine_llm
import assistant.engine.validate as validate
from assistant.engine import load_config
from assistant.engine.state import EngineState, Item


@pytest.fixture
def cfg():
    return load_config()


def _state(text, items):
    st = EngineState(raw_text=text, text=text)
    st.items = items
    return st


def _event_intent(**kw):
    base = dict(title="x", date=None, start_time=None, end_time=None,
                recurrence=None, recur_until=None, description="")
    base.update(kw)
    return SimpleNamespace(**base)


def _item(action, intent, id="item_1", kind="event", text=""):
    return Item(id=id, kind=kind, text=text, action=action, intent=intent)


def _rules_applied(st):
    return [f.rule for f in st.fixes]


# --- text repair (run pass) -------------------------------------------------

def test_text_repair_collapses_stutters_for_free(cfg, monkeypatch):
    monkeypatch.setattr(engine_llm, "call_json",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no LLM")))
    st = _state("x", [Item(id="item_1", kind="event", text="book the the meeting tomorrow")])
    validate.run(st, cfg)
    assert st.items[0].text == "book the meeting tomorrow"
    assert "text_repair" in _rules_applied(st)


def test_text_repair_llm_only_for_genuinely_mangled(cfg, monkeypatch):
    monkeypatch.setattr(engine_llm, "call_json",
                        lambda *a, **k: ({"text": "book squash tomorrow"}, 3))
    st = _state("x", [Item(id="item_1", kind="event", text="book squa- book squash tomorrow")])
    validate.run(st, cfg)
    assert st.items[0].text == "book squash tomorrow"


def test_text_repair_rejects_a_rewrite_that_grew(cfg, monkeypatch):
    monkeypatch.setattr(engine_llm, "call_json",
                        lambda *a, **k: ({"text": "book squash tomorrow at nine with David maybe"}, 3))
    st = _state("x", [Item(id="item_1", kind="event", text="book squa- tomorrow")])
    validate.run(st, cfg)
    assert st.items[0].text == "book squa- tomorrow"   # invention refused


# --- past_date_bump (row 29) ------------------------------------------------

def test_past_date_bump_recent_weekday_rolls_a_week(cfg):
    past = (dt.date.today() - dt.timedelta(days=3)).isoformat()
    it = _item("create_event", _event_intent(date=past))
    st = _state("meeting", [it])
    validate.run_objects(st, cfg)
    bumped = dt.date.fromisoformat(it.intent.date)
    assert bumped >= dt.date.today()
    assert bumped.weekday() == dt.date.fromisoformat(past).weekday()


def test_past_date_bump_old_calendar_day_moves_a_year(cfg):
    it = _item("create_event", _event_intent(date="2026-01-15"))
    st = _state("meeting on January 15", [it])
    validate.run_objects(st, cfg)
    assert it.intent.date == "2027-01-15"


# --- until_exclusive (row 53) ----------------------------------------------

def test_until_excludes_the_day_it_names(cfg):
    it = _item("create_event", _event_intent(
        date="2026-10-01", recurrence="daily", recur_until="2026-10-06"))
    st = _state("every day at 7pm until Oct 6", [it])
    validate.run_objects(st, cfg)
    assert it.intent.recur_until == "2026-10-05"


def test_through_keeps_the_day_it_names(cfg):
    it = _item("create_event", _event_intent(
        date="2026-10-01", recurrence="daily", recur_until="2026-10-06"))
    st = _state("every day at 7pm through Oct 6", [it])
    validate.run_objects(st, cfg)
    assert it.intent.recur_until == "2026-10-06"


# --- weekly_start_day (row 53) ----------------------------------------------

def test_weekly_series_anchors_on_the_named_day(cfg):
    wrong_day = dt.date.today()
    while wrong_day.weekday() == 6:        # any date that is not a Sunday
        wrong_day += dt.timedelta(days=1)
    it = _item("create_event", _event_intent(
        date=wrong_day.isoformat(), recurrence="weekly"))
    st = _state("standup every sunday at 9am", [it])
    validate.run_objects(st, cfg)
    assert dt.date.fromisoformat(it.intent.date).weekday() == 6


# --- at_time_is_start --------------------------------------------------------

def test_at_time_is_a_start_not_an_end(cfg):
    it = _item("create_event", _event_intent(
        title="dinner with Danny", start_time="18:00", end_time="20:00"))
    st = _state("dinner with Danny at 8 pm", [it])
    validate.run_objects(st, cfg)
    assert it.intent.start_time == "20:00"
    assert it.intent.end_time == "21:00"


# --- morning_title_guard (row 41 family) ------------------------------------

def test_shacharit_is_a_morning_event(cfg):
    it = _item("create_event", _event_intent(
        title="Shacharit", start_time="18:30", end_time="19:30"))
    st = _state("Shacharit at 6:30", [it])
    validate.run_objects(st, cfg)
    assert it.intent.start_time == "06:30"


# --- bare_hour_pm ------------------------------------------------------------

def test_bare_evening_hour_reads_pm(cfg):
    it = _item("create_event", _event_intent(
        title="Kems", date="2026-09-10", start_time="04:00"))
    st = _state("Kems tomorrow at 4", [it])
    validate.run_objects(st, cfg)
    assert it.intent.start_time == "16:00"


def test_explicit_am_is_left_alone(cfg):
    it = _item("create_event", _event_intent(
        title="gym", date="2026-09-10", start_time="07:00"))
    st = _state("book gym tomorrow at 7am", [it])
    validate.run_objects(st, cfg)
    assert it.intent.start_time == "07:00"


# --- junk_event_drop ---------------------------------------------------------

def test_generic_event_beside_real_todos_is_dropped(cfg):
    ev = _item("create_event", _event_intent(title="reminder"), id="item_1")
    td = _item("create_todo", SimpleNamespace(title="buy milk", due_date=None),
               id="item_2", kind="task")
    st = _state("remind me to buy milk", [ev, td])
    validate.run_objects(st, cfg)
    assert ev.intent is None                 # dropped as parser noise
    assert td.intent is not None


# --- due_date_pin ------------------------------------------------------------

def test_due_next_monday_is_deterministic(cfg):
    it = _item("create_todo", SimpleNamespace(title="pay rent", due_date="2026-01-01"),
               kind="task")
    st = _state("pay rent due next monday", [it])
    validate.run_objects(st, cfg)
    got = dt.date.fromisoformat(it.intent.due_date)
    assert got.weekday() == 0 and got > dt.date.today()


# --- cadence_round_and_announce (rows 53/64 family) --------------------------

def test_unsupported_cadence_is_announced_not_silent(cfg):
    it = _item("create_event", _event_intent(
        title="pilates", date="2026-09-08", recurrence="weekly"))
    st = _state("pilates every other tuesday at 6pm", [it])
    validate.run_objects(st, cfg)
    assert any("every other week" in m for m in st.messages)


# --- observance gate (engine rule — AI-created events only) ------------------

def _next_saturday() -> dt.date:
    d = dt.date.today() + dt.timedelta(days=1)
    while d.weekday() != 5:
        d += dt.timedelta(days=1)
    return d


def test_shabbat_meal_is_allowed(cfg):
    it = _item("create_event", _event_intent(
        title="Shabbat lunch", date=_next_saturday().isoformat(), start_time="12:00"))
    st = _state("shabbat lunch", [it])
    validate.run_objects(st, cfg)
    assert it.blocked is None


def test_shabbat_davening_is_allowed(cfg):
    it = _item("create_event", _event_intent(
        title="Shacharit at shul", date=_next_saturday().isoformat(), start_time="08:30"))
    st = _state("shacharit", [it])
    validate.run_objects(st, cfg)
    assert it.blocked is None


def test_shabbat_gym_is_refused_with_a_reason(cfg):
    it = _item("create_event", _event_intent(
        title="gym session", date=_next_saturday().isoformat(), start_time="10:00"))
    st = _state("gym on saturday morning", [it])
    validate.run_objects(st, cfg)
    assert it.blocked and "Shabbat" in it.blocked


def test_motzei_shabbat_is_fine(cfg):
    it = _item("create_event", _event_intent(
        title="movie night", date=_next_saturday().isoformat(), start_time="22:30"))
    st = _state("movie saturday night", [it])
    validate.run_objects(st, cfg)
    assert it.blocked is None


def test_a_series_is_left_to_db_level_skipping(cfg):
    it = _item("create_event", _event_intent(
        title="gym", date=_next_saturday().isoformat(), start_time="10:00",
        recurrence="weekly"))
    st = _state("gym every saturday", [it])
    validate.run_objects(st, cfg)
    assert it.blocked is None


# --- move_time_fill (run 9: "updated successfully" while changing nothing) ---

def _upd_intent(**kw):
    base = dict(match_title="meeting", match_date=None, match_start_time=None,
                new_title=None, new_date=None, new_start_time=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_move_time_fill_takes_the_other_spoken_time(cfg):
    it = _item("update_event", _upd_intent(match_start_time="13:00"))
    st = _state("move my 1pm meeting tomorrow to 3pm", [it])
    validate.run_objects(st, cfg)
    assert it.intent.new_start_time == "15:00"
    assert "move_time_fill" in [f.rule for f in st.fixes]


def test_move_time_fill_is_minute_aware(cfg):
    """"from 9:30 to 9" — same hour, different minutes — must fill 09:00."""
    it = _item("update_event", _upd_intent(match_start_time="09:30"))
    st = _state("meeting with Guri moved from 9:30 to 9 on wednesday", [it])
    validate.run_objects(st, cfg)
    assert it.intent.new_start_time == "09:00"


def test_move_time_fill_reads_from_to_over_the_model(cfg):
    """Run 10: the parser filed "from 9:30" as the DESTINATION. The explicit
    from/to words override whatever the model filled, both sides."""
    it = _item("update_event", _upd_intent(new_date="2026-09-09",
                                           new_start_time="09:30"))
    st = _state("meeting with Guri moved from 9:30 to 9 on wednesday", [it])
    validate.run_objects(st, cfg)
    assert it.intent.match_start_time == "09:30"
    assert it.intent.new_start_time == "09:00"


def test_move_time_fill_to_phrase_beats_a_wrong_fill(cfg):
    it = _item("update_event", _upd_intent(match_start_time="13:00",
                                           new_start_time="16:00"))
    st = _state("move my 1pm meeting to 3pm", [it])
    validate.run_objects(st, cfg)
    assert it.intent.new_start_time == "15:00"   # the spoken "to 3pm" wins


def test_move_time_fill_sets_the_match_from_the_other_time(cfg):
    it = _item("update_event", _upd_intent())
    st = _state("move my 1pm meeting tomorrow to 3pm", [it])
    validate.run_objects(st, cfg)
    assert it.intent.match_start_time == "13:00"
    assert it.intent.new_start_time == "15:00"


# --- guards from the real-utterance triage (2026-09-03) ----------------------

def test_a_remove_instruction_becomes_the_delete_it_says(cfg):
    it = _item("create_todo", SimpleNamespace(title="remove table from furniture",
                                              due_date=None), kind="task")
    st = _state("remove 'table' from furniture", [it])
    validate.run_objects(st, cfg)
    assert it.action == "delete_todo"
    assert it.intent.match_title == "table"
    assert "create_from_remove_guard" in [f.rule for f in st.fixes]


def test_a_question_item_never_creates(cfg):
    q = _item("query_schedule", SimpleNamespace(), id="item_1-1", kind="review",
              text="On the day project one is due, does my daughter have a recital?")
    junk = _item("create_todo", SimpleNamespace(title="project one", due_date=None),
                 id="item_1-2", kind="task",
                 text="On the day project one is due, does my daughter have a recital?")
    st = _state("On the day project one is due, does my daughter have a recital?",
                [q, junk])
    validate.run_objects(st, cfg)
    assert junk.intent is None
    assert q.intent is not None


def test_a_booking_next_to_a_question_survives(cfg):
    ev = _item("create_event", _event_intent(title="gym", date="2026-09-08",
                                             start_time="07:00"),
               id="item_1", text="book gym tuesday at 7am")
    q = _item("query_schedule", SimpleNamespace(), id="item_2", kind="review",
              text="what do I have on friday?")
    st = _state("book gym tuesday at 7am and what do I have on friday?", [ev, q])
    validate.run_objects(st, cfg)
    assert ev.intent is not None


def test_from_less_removes_become_deletes(cfg):
    it = _item("create_todo", SimpleNamespace(title="get rid of this list",
                                              due_date=None), kind="task")
    st = _state("get rid of this list", [it])
    validate.run_objects(st, cfg)
    assert it.action == "delete_todo"


def test_a_misheard_erase_still_guards(cfg):
    it = _item("create_event", _event_intent(title="earse the next birthday event"))
    st = _state("Please earse the next birthday event", [it])
    validate.run_objects(st, cfg)
    assert it.action == "delete_todo" or it.intent is None


def test_an_imperative_query_creates_nothing(cfg):
    it = _item("create_event", _event_intent(title="Reminder: meeting"),
               text="give me the reminders")
    st = _state("give me the reminders", [it])
    validate.run_objects(st, cfg)
    assert it.intent is None


def test_open_a_new_list_is_not_a_query(cfg):
    it = _item("create_todo", SimpleNamespace(title="new list", due_date=None),
               kind="task", text="Open up a new list")
    st = _state("Open up a new list", [it])
    validate.run_objects(st, cfg)
    assert it.intent is not None


def test_stray_quotes_are_shed_before_parsing(cfg, monkeypatch):
    monkeypatch.setattr(engine_llm, "call_json",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no LLM")))
    st = _state("x", [Item(id="item_1", kind="event", text="add 'christmas' to calendar")])
    validate.run(st, cfg)
    assert st.items[0].text == "add christmas to calendar"
