"""Field-level quality metric (Gil, 2026-09-05) — worked examples per component.

Objective components (when / quantity / tag / extras-groundedness) hard-fail
only where the transcript pins the truth; a component the words don't pin is
uncovered, never guessed. Titles score as similarity (short-and-similar wins).
The when is paramount (weight 0.5 on events).
"""
from __future__ import annotations

import datetime

from scripts import field_quality as fq

TS = datetime.datetime(2026, 3, 10, 9, 0).timestamp()   # a Tuesday


def _event(**p):
    return {"action": "create_event", "parameters": p}


def _todo(titles, quantities=None, tags=None):
    return {"action": "create_todo", "parameters": {
        "titles": titles, "quantities": quantities or [1] * len(titles),
        "tags": tags or []}}


# --- the paramount when ----------------------------------------------------

def test_right_time_and_day_scores_full_when():
    s = fq.score_item(_event(title="gym", date="2026-03-11", start_time="07:00"),
                      "book gym tomorrow at 7", TS)
    assert s["parts"]["when"] == 1.0


def test_wrong_day_fails_when_even_with_a_perfect_title():
    s = fq.score_item(_event(title="gym", date="2026-03-13", start_time="07:00"),
                      "book gym tomorrow at 7", TS)
    assert s["parts"]["when"] == 0.5          # time right, day wrong
    good = fq.score_item(_event(title="gym", date="2026-03-11", start_time="07:00"),
                         "book gym tomorrow at 7", TS)
    assert s["score"] < good["score"]


def test_wrong_clock_time_fails():
    s = fq.score_item(_event(title="meeting", date="2026-03-10", start_time="10:00"),
                      "meeting today at 3pm", TS)
    assert s["parts"]["when"] == 0.5          # day right, time wrong


def test_no_when_in_the_words_means_uncovered_not_failed():
    s = fq.score_item(_event(title="dentist", date="2026-03-20", start_time="10:00"),
                      "book the dentist", TS)
    assert "when" not in s["parts"]           # excluded, not punished


def test_weekday_wording_checks_the_weekday():
    ok = fq.score_item(_event(title="shiur", date="2026-03-15", start_time="18:00"),
                       "shiur on sunday at 6", TS)      # 2026-03-15 is a Sunday
    bad = fq.score_item(_event(title="shiur", date="2026-03-16", start_time="18:00"),
                        "shiur on sunday at 6", TS)
    assert ok["parts"]["when"] == 1.0 and bad["parts"]["when"] == 0.5


# --- subjective title ------------------------------------------------------

def test_short_similar_title_scores_high_verbatim_not_required():
    a = fq.score_item(_event(title="Gym session", date="2026-03-11", start_time="07:00"),
                      "book gym tomorrow at 7", TS)
    assert a["parts"]["title"] >= 0.5          # "gym" grounded, "session" not


def test_invented_title_scores_low():
    s = fq.score_item(_event(title="Quarterly budget review", date="2026-03-11",
                             start_time="07:00"),
                      "book gym tomorrow at 7", TS)
    assert s["parts"]["title"] == 0.0


# --- extras: grounded or absent -------------------------------------------

def test_invented_location_costs_extras():
    s = fq.score_item(_event(title="meeting", date="2026-03-10", start_time="15:00",
                             location="Conference Room B"),
                      "meeting today at 3pm", TS)
    assert s["parts"]["extras"] == 0.0
    absent = fq.score_item(_event(title="meeting", date="2026-03-10",
                                  start_time="15:00"),
                           "meeting today at 3pm", TS)
    assert "extras" not in absent["parts"]     # absent = fine, uncovered


# --- tasks -----------------------------------------------------------------

def test_quantity_matches_the_spoken_number():
    ok = fq.score_item(_todo(["apples"], [5]), "buy 5 apples", TS)
    bad = fq.score_item(_todo(["apples"], [2]), "buy 5 apples", TS)
    assert ok["parts"]["qty"] == 1.0 and bad["parts"]["qty"] == 0.0


def test_clock_digits_are_not_quantities():
    s = fq.score_item(_todo(["milk"], [1]), "buy milk at 5pm", TS)
    assert s["parts"]["qty"] == 1.0           # the 5 is a time, default 1 is right


def test_grocery_wording_wants_a_grocery_tag():
    ok = fq.score_item(_todo(["milk"], [1], tags=["grocery"]),
                       "add milk to my grocery list", TS)
    bad = fq.score_item(_todo(["milk"], [1], tags=["work"]),
                        "add milk to my grocery list", TS)
    assert ok["parts"]["tag"] == 1.0 and bad["parts"]["tag"] == 0.0


# --- aggregation -----------------------------------------------------------

def test_run_aggregation_weights_complex_double():
    prov = {"a": {"complexity": "simple"}, "b": {"complexity": "complex"}}
    rows = [("a", '[{"action": "create_event", "parameters": {"title": "gym", '
                  '"date": "2026-03-11", "start_time": "07:00"}}]', TS),
            ("b", '[{"action": "create_event", "parameters": {"title": "budget", '
                  '"date": "2026-03-13", "start_time": "07:00"}}]', TS)]
    # both rows say "gym tomorrow at 7" semantics? use matching transcripts:
    rows = [("book gym tomorrow at 7", rows[0][1], TS),
            ("book gym tomorrow at 7", rows[1][1], TS)]
    prov = {"book gym tomorrow at 7": {"complexity": "simple"}}
    out = fq.score_run(rows, prov)
    assert 0.0 <= out["field_quality"] <= 1.0
    assert out["items"] == 2 and out["when_coverage"] == 2
