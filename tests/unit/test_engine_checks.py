"""validate's rules, one test per rule, plus the property that matters most.

The headline test is `test_a_correct_item_is_left_alone`: a repair pass that
rewrites what was already right is worse than no repair pass, because it turns a
working command into a broken one. Board G's BROKE column measures it at scale;
this pins it per rule.
"""
from __future__ import annotations

import datetime as dt

import pytest

from assistant.engine.decompose_validate import checks


ANCHOR = dt.date(2026, 9, 8)          # a Tuesday


def _run(item, transcript=None):
    items, fixes, flags = checks.run([item], transcript or item.get("time", ""),
                                     ANCHOR)
    return items[0], fixes, flags


# ---------------------------------------------------------------------------
# The property that matters most
# ---------------------------------------------------------------------------

def test_a_correct_item_is_left_alone():
    """No fix, no flag, and not one field touched."""
    item = {"kind": "event", "text": "book the dentist", "time": "next friday at 10am",
            "date": "2026-09-18", "start_time": "10:00", "end_time": None,
            "recurrence": None, "recur_days": [], "recur_until": None,
            "quantity": None, "reminder_minutes": None}
    out, fixes, flags = _run(item)
    assert fixes == []
    assert flags == []
    assert out == item


def test_silence_is_not_evidence():
    """Where the words name NO value, whatever the item holds survives.

    A producer the resolver cannot parse — the LLM, a rewritten retry — must not
    have its answer deleted just because `resolve` had nothing to say.
    """
    item = {"kind": "event", "text": "book the thing", "time": "at some point",
            "date": "2026-11-02", "start_time": "14:00", "end_time": None,
            "recurrence": None, "recur_days": [], "recur_until": None,
            "quantity": None, "reminder_minutes": None}
    out, fixes, _flags = _run(item)
    assert out["date"] == "2026-11-02"
    assert out["start_time"] == "14:00"
    assert not any(f.field in ("date", "start_time") for f in fixes)


# ---------------------------------------------------------------------------
# One test per FIX rule
# ---------------------------------------------------------------------------

def test_date_disagreeing_with_the_words_is_repaired():
    item = {"kind": "event", "text": "book the dentist", "time": "next friday",
            "date": "2026-09-21", "start_time": None, "end_time": None,
            "recurrence": None, "recur_days": [], "recur_until": None,
            "quantity": None, "reminder_minutes": None}
    out, fixes, _ = _run(item)
    assert out["date"] == "2026-09-18"       # the Friday of the next week
    assert [f.rule for f in fixes] == ["agree_with_words"]


def test_a_clock_with_no_day_gets_the_floor():
    item = {"kind": "event", "text": "book the gym", "time": "at 6pm",
            "date": None, "start_time": "18:00", "end_time": None,
            "recurrence": None, "recur_days": [], "recur_until": None,
            "quantity": None, "reminder_minutes": None}
    out, fixes, _ = _run(item)
    assert out["date"] == ANCHOR.isoformat()
    assert "date_floor" in [f.rule for f in fixes]


def test_a_day_with_no_clock_does_not_acquire_one():
    """The floor works one way only. An invented time is worse than none."""
    item = {"kind": "task", "text": "call the plumber", "time": "tomorrow",
            "date": "2026-09-09", "start_time": None, "end_time": None,
            "recurrence": None, "recur_days": [], "recur_until": None,
            "quantity": None, "reminder_minutes": None}
    out, _fixes, _ = _run(item)
    assert out["start_time"] is None


def test_a_series_cannot_start_on_a_day_it_never_names():
    item = {"kind": "event", "text": "standup", "time": "every tuesday and thursday",
            "date": "2026-09-09", "start_time": None, "end_time": None,
            "recurrence": "weekly", "recur_days": ["tuesday", "thursday"],
            "recur_until": None, "quantity": None, "reminder_minutes": None}
    out, fixes, _ = _run(item)
    assert dt.date.fromisoformat(out["date"]).weekday() in (1, 3)
    assert any(f.rule in ("agree_with_words", "series_starts_on_a_named_day")
               for f in fixes)


def test_a_bare_end_hour_before_the_start_reads_as_pm():
    item = {"kind": "event", "text": "team meeting", "time": "from 3 to 4",
            "date": "2026-09-08", "start_time": "15:00", "end_time": "04:00",
            "recurrence": None, "recur_days": [], "recur_until": None,
            "quantity": None, "reminder_minutes": None}
    out, _fixes, flags = _run(item)
    assert out["end_time"] == "16:00"
    assert not [f for f in flags if f.rule == "end_after_start"]


def test_quantity_and_lead_time_are_read_from_their_own_source():
    """Concatenating them broke the lead time: the action's words landed after
    "prior", and a lead time whose tail names something else is not one."""
    item = {"kind": "task", "text": "call the plumber", "time": "next friday two days prior",
            "date": None, "start_time": None, "end_time": None,
            "recurrence": None, "recur_days": [], "recur_until": None,
            "quantity": None, "reminder_minutes": 45}
    out, _fixes, _ = _run(item)
    assert out["reminder_minutes"] == 2880


# ---------------------------------------------------------------------------
# One test per FLAG rule — and every one of them still COMMITS
# ---------------------------------------------------------------------------

def test_a_series_ending_before_it_starts_is_flagged_not_fixed():
    """Either end could be the wrong one, so guessing is not available."""
    item = {"kind": "event", "text": "standup", "time": "every monday",
            "date": "2026-09-14", "start_time": None, "end_time": None,
            "recurrence": "weekly", "recur_days": ["monday"],
            "recur_until": "2026-09-09", "quantity": None,
            "reminder_minutes": None}
    out, _fixes, flags = _run(item)
    assert "until_after_start" in [f.rule for f in flags]
    assert out["recur_until"] == "2026-09-09"     # kept, not deleted


def test_a_bound_with_no_series_is_flagged():
    item = {"kind": "event", "text": "standup", "time": "at 9am",
            "date": "2026-09-08", "start_time": "09:00", "end_time": None,
            "recurrence": None, "recur_days": [], "recur_until": "2026-09-30",
            "quantity": None, "reminder_minutes": None}
    _out, _fixes, flags = _run(item)
    assert "until_needs_recurrence" in [f.rule for f in flags]


def test_a_phrase_with_no_ruling_is_flagged_rather_than_dropped():
    """"next week" has no agreed value. Saying so beats silently choosing one."""
    item = {"kind": "event", "text": "book the dentist", "time": "next week",
            "date": None, "start_time": None, "end_time": None,
            "recurrence": None, "recur_days": [], "recur_until": None,
            "quantity": None, "reminder_minutes": None}
    _out, _fixes, flags = _run(item)
    assert "every_phrase_honoured" in [f.rule for f in flags]


def test_nothing_is_ever_blocked():
    """Flags notify; they do not refuse (Gil, 2026-09-08)."""
    item = {"kind": "event", "text": "gym", "time": "next week",
            "date": "2026-09-14", "start_time": "09:00", "end_time": "08:00",
            "recurrence": None, "recur_days": [], "recur_until": "2026-09-01",
            "quantity": None, "reminder_minutes": None}
    out, _fixes, flags = _run(item)
    assert len(flags) >= 2
    assert "blocked" not in out
    assert out["date"]           # still committable


# ---------------------------------------------------------------------------
# The perturbation dataset agrees with itself
# ---------------------------------------------------------------------------

def test_every_defect_class_is_actually_a_defect():
    """A perturbation that changes nothing would inflate board G's 'improved'."""
    from assistant.engine.decompose_validate.datasets import perturb

    item = {"kind": "event", "text": "book yoga class", "time": "every monday at 9am",
            "date": "2026-09-14", "start_time": "09:00", "end_time": "10:00",
            "recurrence": "weekly", "recur_days": ["monday"],
            "recur_until": "2026-10-12", "quantity": 3, "reminder_minutes": 30}
    for kind in perturb.KINDS:
        if kind == "none":
            assert perturb.perturb(item, kind) == item
            continue
        assert perturb.applicable(item, kind), kind
        assert perturb.perturb(item, kind) != item, kind


def test_a_third_of_items_are_left_as_controls():
    """Controls are what make the BROKE column able to see anything."""
    from assistant.engine.decompose_validate.datasets import perturb

    item = {"date": "2026-09-14", "start_time": "09:00", "end_time": "10:00",
            "recurrence": "weekly", "recur_days": ["monday"],
            "recur_until": "2026-10-12", "quantity": 3, "reminder_minutes": 30}
    kinds = [perturb.kind_for(f"row_{i}", 0, item) for i in range(400)]
    share = kinds.count("none") / len(kinds)
    assert 0.25 < share < 0.45, share


@pytest.mark.parametrize("kind", ["quantity_wrong", "lead_time_wrong",
                                  "series_day_mismatch", "until_before_date"])
def test_a_defect_that_cannot_apply_falls_back_to_a_control(kind):
    bare = {"kind": "event", "text": "gym", "time": "tomorrow",
            "date": "2026-09-09"}
    assert not perturb_applicable(kind, bare)


def perturb_applicable(kind, item):
    from assistant.engine.decompose_validate.datasets import perturb
    return perturb.applicable(item, kind)
