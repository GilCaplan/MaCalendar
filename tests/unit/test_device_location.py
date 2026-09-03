"""Sundown has to be computed for where you are, not where you usually are.

Candle lighting moves by more than three hours across a year in one place, and
by hours again between places. A repeating event that skips Shabbat is wrong
the moment you travel: the boundary it is avoiding was computed for somewhere
you are not, and nothing about the wrong answer looks wrong.

The device that knows its position reports it, and everything downstream
follows without being told. The configured place stays as the fallback — it is
where you usually are, which is the right answer when nothing has said
otherwise.
"""
from __future__ import annotations

import datetime as dt
import json

import pytest

from assistant import observance as ob


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    """A location file of our own; the real one is never touched."""
    monkeypatch.setattr(ob, "LOCATION_PATH", str(tmp_path / "location.json"))
    ob.reload_settings()
    yield tmp_path / "location.json"
    ob.reload_settings()


def test_with_nothing_reported_the_configured_place_is_used(scratch):
    assert ob.get_location() is None
    assert ob.current_settings().city == ob.settings_from_config().city


def test_a_reported_position_takes_over(scratch):
    ob.set_location(latitude=51.5074, longitude=-0.1278,
                    timezone="Europe/London", city="London")
    s = ob.current_settings()
    assert (round(s.latitude, 4), round(s.longitude, 4)) == (51.5074, -0.1278)
    assert s.timezone == "Europe/London"


def test_sundown_actually_follows_the_device(scratch):
    """The assertion that matters: a new position changes the answer.

    Late June is close to midsummer in London and much later in the evening
    than at the default latitude, so this cannot pass while the position is
    being stored but ignored.
    """
    june = dt.date(2026, 6, 26)
    before = ob.sunset(june)
    ob.set_location(latitude=51.5074, longitude=-0.1278, timezone="Europe/London")
    after = ob.sunset(june)
    assert after is not None and before is not None
    assert after.hour - before.hour >= 1, (
        f"sunset barely moved ({before} -> {after}) — the position is being ignored")


def test_only_the_position_is_taken_from_the_device(scratch):
    """How long before candle lighting a session must end is a preference, not
    a fact about the sky, so a phone does not get to change it."""
    configured = ob.settings_from_config()
    ob.set_location(latitude=51.5074, longitude=-0.1278, timezone="Europe/London")
    moved = ob.current_settings()
    assert moved.candle_lighting_minutes == configured.candle_lighting_minutes
    assert moved.tzeit_depression == configured.tzeit_depression
    assert moved.erev_buffer_minutes == configured.erev_buffer_minutes


def test_clearing_it_goes_back_to_the_configured_place(scratch):
    ob.set_location(latitude=51.5074, longitude=-0.1278, timezone="Europe/London")
    ob.clear_location()
    assert ob.get_location() is None
    assert ob.current_settings().city == ob.settings_from_config().city


# ---------------------------------------------------------------------------
# What must be refused
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("lat, lon", [(200, 0), (-91, 0), (0, 181), (0, -181)])
def test_impossible_coordinates_are_refused(scratch, lat, lon):
    """A latitude of 200 does not fail loudly later — it quietly computes a
    sunset that never happens, and every day becomes available."""
    with pytest.raises(ValueError):
        ob.set_location(latitude=lat, longitude=lon, timezone="UTC")
    assert ob.get_location() is None


def test_a_position_with_no_timezone_is_refused(scratch):
    """Coordinates alone cannot say what time it is there."""
    with pytest.raises(ValueError):
        ob.set_location(latitude=51.5, longitude=-0.1, timezone="")


def test_a_refused_position_does_not_overwrite_a_good_one(scratch):
    ob.set_location(latitude=51.5074, longitude=-0.1278, timezone="Europe/London")
    with pytest.raises(ValueError):
        ob.set_location(latitude=999, longitude=0, timezone="UTC")
    assert round(ob.current_settings().latitude, 4) == 51.5074


def test_a_corrupt_location_file_falls_back_rather_than_raising(scratch):
    """A half-written file must not take the calendar down."""
    scratch.write_text("{not json at all")
    assert ob.get_location() is None
    ob.reload_settings()
    assert ob.candle_lighting(dt.date(2026, 9, 4)) is not None


def test_the_file_is_replaced_atomically(scratch):
    """Written to a temporary name and moved, so a crash mid-write cannot
    leave a location that parses but is wrong."""
    ob.set_location(latitude=51.5074, longitude=-0.1278, timezone="Europe/London")
    assert json.loads(scratch.read_text())["latitude"] == 51.5074
    assert not scratch.with_suffix(".json.tmp").exists()


# ---------------------------------------------------------------------------
# Through the API, which is what a phone talks to
# ---------------------------------------------------------------------------

@pytest.fixture
def client(scratch):
    from assistant.api import server
    app = server.create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def test_a_device_can_report_where_it_is(client):
    r = client.post("/observance/location", json={
        "latitude": 51.5074, "longitude": -0.1278, "timezone": "Europe/London",
        "city": "London"})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["timezone"] == "Europe/London"

    shown = client.get("/observance/location").get_json()
    assert shown["source"] == "device"
    assert shown["in_use"]["city"] == "London"


def test_the_api_refuses_an_impossible_position(client):
    r = client.post("/observance/location",
                    json={"latitude": 999, "longitude": 0, "timezone": "UTC"})
    assert r.status_code == 400


def test_the_api_refuses_an_incomplete_position(client):
    assert client.post("/observance/location", json={"latitude": 51.5}).status_code == 400


def test_the_api_can_forget_it(client):
    client.post("/observance/location", json={
        "latitude": 51.5074, "longitude": -0.1278, "timezone": "Europe/London"})
    assert client.delete("/observance/location").status_code == 200
    assert client.get("/observance/location").get_json()["source"] == "config"
