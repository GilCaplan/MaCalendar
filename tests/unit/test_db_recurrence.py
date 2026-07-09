"""Unit tests for recurring-event logic in assistant/db.py — series creation,
root re-rooting on delete, series-wide field propagation, and external-source
locking. This is the most behaviorally subtle part of db.py (1400+ lines, almost
no prior dedicated test coverage) and the easiest to silently regress: root
re-rooting bugs mean "delete one instance" can orphan the rest of a series.

Uses a real temp-file SQLite DB (real schema/migrations via CalendarDB), not
mocks — recurrence correctness depends on actual SQL WHERE-clause behavior
across series_id / id, which a mock can't meaningfully verify.
"""
from __future__ import annotations

import datetime

import pytest

from assistant.db import CalendarDB


@pytest.fixture
def db(tmp_path) -> CalendarDB:
    return CalendarDB(path=str(tmp_path / "recurrence_test.db"))


def _weekly_event(**overrides) -> dict:
    data = {
        "title": "Standup",
        "date": "2026-01-05",  # a Monday
        "start_time": "09:00",
        "end_time": "09:30",
        "recurrence": "weekly",
        "recurrence_end": "2026-01-26",  # 4 Mondays: 5, 12, 19, 26
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# Series creation
# ---------------------------------------------------------------------------

def test_create_recurring_event_generates_all_instances(db):
    root_id = db.create_event_from_dict(_weekly_event())
    root = db.get_event(root_id)
    assert root["series_id"] == root_id

    series = db.get_series_events(root_id)
    dates = sorted(e["date"] for e in series)
    assert dates == ["2026-01-05", "2026-01-12", "2026-01-19", "2026-01-26"]
    assert all(e["series_id"] == root_id for e in series)


def test_create_non_recurring_event_has_no_series(db):
    event_id = db.create_event_from_dict({
        "title": "One-off", "date": "2026-01-05", "start_time": "10:00", "end_time": "11:00",
    })
    event = db.get_event(event_id)
    assert event["series_id"] is None


def test_monthly_recurrence_clamps_to_last_valid_day(db):
    """31st of Jan -> Feb has no 31st, clamps to Feb 28 (2026 is not a leap year) —
    but March, which does have a 31st, must return to the original anchor day
    rather than staying stuck at 28. Each instance is computed from the series'
    original day-of-month (anchor_day in _next_date), not chained from the
    previous (possibly clamped) instance, so a short month doesn't permanently
    drag every later month down with it.
    """
    root_id = db.create_event_from_dict({
        "title": "Month-end review", "date": "2026-01-31",
        "start_time": "09:00", "end_time": "10:00",
        "recurrence": "monthly", "recurrence_end": "2026-04-30",
    })
    series = db.get_series_events(root_id)
    dates = sorted(e["date"] for e in series)
    assert dates == ["2026-01-31", "2026-02-28", "2026-03-31", "2026-04-30"]


def test_promote_to_series_generates_future_instances(db):
    """A standalone event that gets recurrence added via edit becomes a series root."""
    event_id = db.create_event_from_dict(_weekly_event(recurrence="", recurrence_end=""))
    assert db.get_event(event_id)["series_id"] is None

    db.update_event(event_id, recurrence="weekly", recurrence_end="2026-01-26")
    db.promote_to_series(event_id)

    series = db.get_series_events(event_id)
    assert len(series) == 4


def test_promote_to_series_is_noop_if_already_in_series(db):
    root_id = db.create_event_from_dict(_weekly_event())
    before = len(db.get_series_events(root_id))
    db.promote_to_series(root_id)  # already a series — must not double-generate
    after = len(db.get_series_events(root_id))
    assert before == after


# ---------------------------------------------------------------------------
# Deleting the series root re-roots to the next chronological instance
# ---------------------------------------------------------------------------

def test_delete_root_reroots_series_to_next_instance(db):
    root_id = db.create_event_from_dict(_weekly_event())
    series_before = db.get_series_events(root_id)
    next_instance_id = sorted(series_before, key=lambda e: e["date"])[1]["id"]

    db.delete_event(root_id)

    assert db.get_event(root_id) is None
    new_root = db.get_event(next_instance_id)
    assert new_root["series_id"] == next_instance_id  # self-referential, now the root

    remaining = db.get_series_events(next_instance_id)
    assert len(remaining) == 3
    assert all(e["series_id"] == next_instance_id for e in remaining)


def test_delete_non_root_instance_does_not_reroot(db):
    root_id = db.create_event_from_dict(_weekly_event())
    series = sorted(db.get_series_events(root_id), key=lambda e: e["date"])
    middle_instance_id = series[1]["id"]

    db.delete_event(middle_instance_id)

    assert db.get_event(root_id)["series_id"] == root_id  # unchanged
    remaining = db.get_series_events(root_id)
    assert len(remaining) == 3
    assert middle_instance_id not in [e["id"] for e in remaining]


def test_delete_last_remaining_instance_leaves_no_orphans(db):
    """Deleting the root of a series with no other instances (recurrence_end same
    as start date -> only the root exists) must not crash looking for a next root.
    """
    root_id = db.create_event_from_dict(_weekly_event(recurrence_end="2026-01-05"))
    assert len(db.get_series_events(root_id)) == 1
    db.delete_event(root_id)
    assert db.get_event(root_id) is None


# ---------------------------------------------------------------------------
# update_series: propagate to all instances, regenerate future ones
# ---------------------------------------------------------------------------

def test_update_series_title_propagates_to_all_instances_past_and_future(db):
    root_id = db.create_event_from_dict(_weekly_event())
    series = sorted(db.get_series_events(root_id), key=lambda e: e["date"])
    third_instance_id = series[2]["id"]  # 2026-01-19

    db.update_series(root_id, start_from_instance_id=third_instance_id, title="Renamed Standup")

    all_titles = [e["title"] for e in db.get_series_events(root_id)]
    assert all(t == "Renamed Standup" for t in all_titles), (
        "Series-wide fields (title) must propagate to every instance, not just future ones"
    )


def test_update_series_time_change_regenerates_future_instances(db):
    root_id = db.create_event_from_dict(_weekly_event())
    series = sorted(db.get_series_events(root_id), key=lambda e: e["date"])
    second_instance_id = series[1]["id"]  # 2026-01-12

    db.update_series(
        root_id, start_from_instance_id=second_instance_id,
        start_time="14:00", end_time="14:30",
    )

    updated = sorted(db.get_series_events(root_id), key=lambda e: e["date"])
    # Instances from the edited one forward carry the new time.
    for e in updated:
        if e["date"] >= "2026-01-12":
            assert e["start_time"] == "14:00"


def test_update_series_extending_recurrence_end_adds_instances(db):
    root_id = db.create_event_from_dict(_weekly_event())
    assert len(db.get_series_events(root_id)) == 4

    db.update_series(root_id, start_from_instance_id=root_id, recurrence_end="2026-02-09")

    series = db.get_series_events(root_id)
    dates = sorted(e["date"] for e in series)
    assert "2026-02-02" in dates
    assert "2026-02-09" in dates


# ---------------------------------------------------------------------------
# delete_series / delete_series_from
# ---------------------------------------------------------------------------

def test_delete_series_removes_all_instances(db):
    root_id = db.create_event_from_dict(_weekly_event())
    deleted_count = db.delete_series(root_id)
    assert deleted_count == 4
    assert db.get_series_events(root_id) == []


def test_delete_series_from_keeps_past_instances(db):
    root_id = db.create_event_from_dict(_weekly_event())
    deleted_count = db.delete_series_from(root_id, from_date="2026-01-19")

    assert deleted_count == 2  # 01-19 and 01-26
    remaining = sorted(e["date"] for e in db.get_series_events(root_id))
    assert remaining == ["2026-01-05", "2026-01-12"]


def test_delete_series_from_reroots_when_root_is_in_deleted_range(db):
    """Deleting from the root's own date forward must re-root to the latest
    remaining PAST instance — but there is none before the root here, so the
    whole series is removed with nothing left to re-root to.
    """
    root_id = db.create_event_from_dict(_weekly_event())
    deleted_count = db.delete_series_from(root_id, from_date="2026-01-05")
    assert deleted_count == 4
    assert db.get_series_events(root_id) == []


def test_delete_series_from_reroots_to_latest_past_instance(db):
    """Delete from the 3rd instance forward, after first re-rooting the series to
    the 2nd instance via a prior partial delete — confirms two-step re-rooting
    chains correctly instead of losing the link.
    """
    root_id = db.create_event_from_dict(_weekly_event())
    # First, delete the root itself so the series re-roots to instance 2 (01-12).
    db.delete_event(root_id)
    new_root = next(e for e in db.get_events_for_day(datetime.date(2026, 1, 12)))
    new_root_id = new_root["id"]
    assert new_root_id != root_id

    deleted_count = db.delete_series_from(new_root_id, from_date="2026-01-19")
    assert deleted_count == 2
    remaining = sorted(e["date"] for e in db.get_series_events(new_root_id))
    assert remaining == ["2026-01-12"]


# ---------------------------------------------------------------------------
# Locking — external sources (ics, one-way outlook) can't be edited/deleted
# ---------------------------------------------------------------------------

def test_ics_sourced_event_is_always_locked(db):
    assert db.is_event_locked({"source": "ics"}) is True


def test_manual_event_is_never_locked(db):
    assert db.is_event_locked({"source": "manual"}) is False
    assert db.is_event_locked({}) is False


def test_outlook_locked_when_two_way_sync_off(db):
    """No calendar_sources row for outlook at all -> two_way is falsy -> locked."""
    assert db.is_event_locked({"source": "outlook"}) is True


def test_update_event_silently_no_ops_on_locked_event(db):
    """update_event must not raise on a locked event — it just doesn't apply."""
    event_id = db.create_event_from_dict({
        "title": "Imported", "date": "2026-01-05", "start_time": "09:00", "end_time": "10:00",
    })
    with db._conn() as conn:
        conn.execute("UPDATE events SET source = 'ics' WHERE id = ?", (event_id,))

    db.update_event(event_id, title="Should not apply")
    assert db.get_event(event_id)["title"] == "Imported"


def test_delete_event_silently_no_ops_on_locked_event(db):
    event_id = db.create_event_from_dict({
        "title": "Imported", "date": "2026-01-05", "start_time": "09:00", "end_time": "10:00",
    })
    with db._conn() as conn:
        conn.execute("UPDATE events SET source = 'ics' WHERE id = ?", (event_id,))

    db.delete_event(event_id)
    assert db.get_event(event_id) is not None  # not deleted
