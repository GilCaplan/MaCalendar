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


@pytest.fixture
def client(registry_with_real_actions):
    """A server whose registry actually has the calendar action in it.

    conftest's autouse `isolated_registry` empties the shared registry for every
    test, so without this the parse returns no actions at all and every command
    comes back with an empty message.
    """
    from assistant.api.server import create_app
    app = create_app()
    app.config.update(TESTING=True)
    c = app.test_client()
    c.post("/voice/text", json={"transcript": "add warmup at 9am"})   # let the lazy models load
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
    message = _create(client, f"add gym on the {day}th at 6pm")["message"]
    assert str(day) in message, message


# ---------------------------------------------------------------------------
# "at X" is a start time
# ---------------------------------------------------------------------------

def test_a_time_said_with_at_becomes_the_start_not_the_end(client):
    """"dinner with Danny at 8 pm" was booked 18:00–20:00 — the stated time
    filed as the end, with an invented start two hours earlier."""
    message = _create(client, "on thursday I have Shacharit at 6:30 am, "
                              "a lecture at 10 and dinner with Danny at 8 pm")["message"]
    assert "8 PM to 9 PM" in message, message
