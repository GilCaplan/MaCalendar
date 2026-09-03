"""Dates the user stated explicitly must survive the sanity-fix stage.

Lives in integration: each case drives the real rule parser through the API, so
the suite loads spaCy and (on a miss) Ollama. Slow, but it is the only level at
which these fixes are observable — `_relative_dates` and the past-date bump are
closures inside `create_app()`.

Two bugs this pins down, both of which silently rewrote what was said:

  * A date more than a week in the past was walked forward one day at a time
    until it reached today — so "August 12 2026", said on 27 August, produced
    an event *today*.
  * "the 12th of August" was claimed by the bare-ordinal reader ("the 19th"),
    which resolved it to the next 12th of any month — 12 September — ignoring
    the month that was named.
"""
from __future__ import annotations

import datetime as dt

import pytest
import requests


def _ollama_running() -> bool:
    try:
        return requests.get("http://localhost:11434/api/tags", timeout=3).status_code == 200
    except Exception:
        return False


# These drive the real parser end to end, which needs the model. Without it they
# would fail rather than skip, and CI has no Ollama.
pytestmark = pytest.mark.skipif(
    not _ollama_running(),
    reason="Ollama not running at localhost:11434 — skipping integration tests",
)


@pytest.fixture
def client(registry_with_real_actions, tmp_path, monkeypatch):
    """A server whose registry actually has the calendar action in it.

    conftest's autouse `isolated_registry` empties the shared registry for every
    test, so without this the parse returns no actions at all and every command
    comes back with an empty message.
    """
    # Own database and own command memory: recorded commands become few-shot
    # examples in the prompt, so without this the parse depends on which tests
    # ran first.
    monkeypatch.setenv("MACALENDAR_DB", str(tmp_path / "cal.db"))
    monkeypatch.setenv("MACALENDAR_MEMORY_DB", str(tmp_path / "memory.db"))
    import assistant.db as _db
    import assistant.intent.memory as _memory
    monkeypatch.setattr(_db, "_db_instance", None)
    monkeypatch.setattr(_memory, "_memory", None)

    from assistant.api.server import create_app
    app = create_app()
    app.config.update(TESTING=True)
    c = app.test_client()
    c.post("/voice/text", json={"transcript": "schedule a meeting tomorrow at 3pm"})  # load the lazy models
    return c


def _create(client, transcript: str) -> dict:
    r = client.post("/voice/text", json={"transcript": transcript})
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body.get("message"), f"no message for {transcript!r}: {body}"
    return body


def _only_event(client) -> dict:
    today = dt.date.today()
    events = client.get(f"/events?year={today.year}&month={today.month}").get_json()
    return events


@pytest.mark.parametrize("phrasing", [
    "add gym on the 12th of August at 6pm",
    "add gym on August 12th at 6pm",
    "add gym on August 12 2026 at 6pm",
])
def test_a_named_month_and_day_are_kept(client, phrasing):
    """Whatever the phrasing, the event lands on an August 12 — never on today
    and never in a month nobody mentioned."""
    message = _create(client, phrasing)["message"]
    assert "Aug 12" in message, message


def test_a_past_date_is_not_collapsed_onto_today(client):
    today = dt.date.today()
    past = today.replace(day=1) - dt.timedelta(days=20)     # comfortably >7 days back
    message = _create(client, f"add gym on {past.strftime('%B %-d')} at 6pm")["message"]
    assert today.strftime("%b %-d, %Y") not in message, f"collapsed onto today: {message}"


def test_a_bare_ordinal_still_resolves_within_the_month(client):
    """The bare-ordinal reader must keep working where no month is named."""
    today = dt.date.today()
    day = 28 if today.day < 28 else 2
    ordinal = {1: "st", 2: "nd", 3: "rd"}.get(day if day < 20 else day % 10, "th")
    message = _create(client, f"add gym on the {day}{ordinal} at 6pm")["message"]
    assert str(day) in message, message


# ---------------------------------------------------------------------------
# "at X" is a start time
# ---------------------------------------------------------------------------

def test_a_time_said_with_at_becomes_the_start_not_the_end(client):
    """"dinner with Danny at 8 pm" was booked 18:00–20:00 — the stated time
    filed as the end, with an invented start two hours earlier.

    One event, not the three-event sentence this came from: asking the model to
    parse three at once made the test about its multi-event accuracy rather than
    about this fix. `_at_times` itself is covered in tests/unit/test_at_times.py.
    """
    message = _create(client, "add dinner with Danny tomorrow at 8 pm")["message"]
    assert "8 PM to 9 PM" in message, message


def test_a_morning_event_is_not_dragged_into_the_afternoon(client):
    """"Shacharit at 6:30" was booked at 18:30. The morning-word guard only ever
    declined to add pm; it never took one away."""
    message = _create(client, "add shacharit tomorrow at 6:30")["message"]
    assert "6:30 AM" in message, message


def test_a_relative_date_repeated_for_two_events_does_not_swallow_a_third(client):
    """Real incident: "walk the dog Tuesday at 9am, walk the dog Tuesday at
    2:30pm, and [event] on the 17th of September" created all three on the
    same Tuesday. "Tuesday" (bare, no "next"/"this") was said twice, both
    resolving to the same date, which used to be read as "one relative
    phrase → apply to every event" — silently overwriting the third event's
    already-correct absolute date from a phrase the relative-date reader
    never even looks at (a month name skips its bare-ordinal branch on
    purpose). The fix: only collapse onto one date when the model itself
    also defaulted every event to the same date — not when it already told
    them apart via its own date parsing.
    """
    import datetime as _dt
    today = _dt.date.today()
    month_after_next = (today.replace(day=1) + _dt.timedelta(days=62)).strftime("%B")
    message = _create(
        client,
        f"add gym on tuesday at 6am and add yoga on tuesday at 7pm and "
        f"add my conference on the 20th of {month_after_next} at 9am",
    )["message"]
    assert f"{month_after_next[:3]} 20" in message, (
        f"the conference's absolute date got overwritten by the repeated 'tuesday': {message}")


def test_task_deadlines_get_the_same_date_resolution_as_events(client):
    """Only events had deterministic relative-date resolution, so "due next
    monday" was left as whatever the model guessed — a Sunday."""
    import datetime as _dt
    client.post("/voice/text", json={
        "transcript": "add buy a gift for Tamar due thursday "
                      "and book the driving test due next monday"})
    todos = client.get("/todos").get_json()
    rows = todos if isinstance(todos, list) else todos.get("todos", [])
    days = {t["title"].lower(): t.get("due_date", "") for t in rows}
    for title, due in days.items():
        if not due:
            continue
        weekday = _dt.date.fromisoformat(due).strftime("%A").lower()
        assert weekday in ("thursday", "monday"), f"{title} due on a {weekday}"
