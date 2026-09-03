"""Our sundown must agree with an independent authority.

The assistant computes sunset, candle lighting and nightfall from solar
geometry rather than fetching them, because it has to work with no network.
That is the right design and it is also unfalsifiable on its own: a wrong
sundown looks exactly like a right one until something independent disagrees,
and by then a season of Friday evenings has been filed on the wrong side of
the boundary.

So the times were fetched once from hebcal.com and checked in as
`tests/fixtures/zmanim_reference.json`. These tests never touch the network —
they compare our arithmetic against that file. Refresh it, or add a location,
with `python -m scripts.fetch_zmanim_reference`.

Hebcal is the right reference specifically because it publishes `tzeit85deg`:
nightfall at 8.5 degrees of solar depression, which is exactly the definition
`observance.py` uses. Comparing against a source that used a different opinion
would measure the disagreement between two rulings rather than an error in the
arithmetic.

The reference deliberately includes the southern hemisphere, a negative
longitude, and both daylight-saving changeovers. A fixture of convenient dates
near home would pass with a dropped longitude sign or a timezone applied twice.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib

import pytest

from assistant import observance as ob

FIXTURE = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "zmanim_reference.json"

#: Seconds do not matter — every one of these times is displayed, and acted on,
#: to the minute. One minute of tolerance is therefore exactly the precision the
#: system actually uses; it is not slack. Measured agreement is well inside it
#: (worst case 27 seconds over 105 comparisons), so this catches a real error
#: rather than ordinary rounding.
TOLERANCE_MINUTES = 1.0


def _reference() -> dict:
    if not FIXTURE.exists():
        pytest.skip(f"{FIXTURE.name} not present — run scripts.fetch_zmanim_reference")
    return json.loads(FIXTURE.read_text())


def _cases():
    if not FIXTURE.exists():
        return []
    ref = json.loads(FIXTURE.read_text())
    return [
        pytest.param(name, loc, date, want, id=f"{name.replace(' ', '-')}-{date}")
        for name, loc in ref["locations"].items()
        for date, want in loc["times"].items()
    ]


def _settings(name: str, loc: dict) -> ob.ObservanceSettings:
    return ob.ObservanceSettings(
        latitude=loc["latitude"], longitude=loc["longitude"],
        timezone=loc["timezone"], city=name,
    )


def _gap_minutes(ours: dt.time, theirs: str) -> float:
    a = dt.datetime.combine(dt.date(2000, 1, 1), ours)
    b = dt.datetime.strptime(theirs, "%H:%M:%S").replace(year=2000, month=1, day=1)
    return abs((a - b).total_seconds()) / 60


@pytest.mark.parametrize("name, loc, date, want", _cases())
def test_our_sundown_matches_the_published_times(name, loc, date, want):
    """Sunrise, sunset and nightfall, at five places across a year."""
    settings = _settings(name, loc)
    day = dt.date.fromisoformat(date)

    times = ob._sun_times(day, settings.latitude, settings.longitude,
                          settings.timezone, settings.tzeit_depression)
    assert times is not None, f"no solar times computed for {name} on {date}"
    sunrise, sunset, nightfall = times

    for label, ours, theirs in (
        ("sunrise",    sunrise,   want["sunrise"]),
        ("sunset",     sunset,    want["sunset"]),
        ("nightfall",  nightfall, want["tzeit85deg"]),
    ):
        gap = _gap_minutes(ours, theirs)
        assert gap <= TOLERANCE_MINUTES, (
            f"{name} {date} {label}: we say {ours:%H:%M:%S}, "
            f"the reference says {theirs} — {gap:.1f} min apart")


@pytest.mark.parametrize("name, loc, date, want", _cases())
def test_candle_lighting_is_the_configured_offset_before_that_sunset(name, loc, date, want):
    """Candle lighting is not fetched — it is derived, and the derivation is the claim."""
    settings = _settings(name, loc)
    day = dt.date.fromisoformat(date)
    lighting = ob.candle_lighting(day, settings)
    assert lighting is not None
    gap = _gap_minutes(lighting, want["sunset"])
    assert abs(gap - settings.candle_lighting_minutes) <= TOLERANCE_MINUTES, (
        f"{name} {date}: candle lighting is {gap:.1f} min before the published "
        f"sunset, expected {settings.candle_lighting_minutes}")


# ---------------------------------------------------------------------------
# The properties the fixture exists to protect
# ---------------------------------------------------------------------------

def test_the_reference_covers_more_than_one_hemisphere():
    """A southern latitude is what catches a hemisphere assumption."""
    lats = [loc["latitude"] for loc in _reference()["locations"].values()]
    assert any(l < 0 for l in lats), "no southern-hemisphere location in the reference"
    assert any(l > 0 for l in lats)


def test_the_reference_covers_a_negative_longitude():
    """A dropped sign west of Greenwich is otherwise invisible from Israel."""
    lons = [loc["longitude"] for loc in _reference()["locations"].values()]
    assert any(l < 0 for l in lons), "no western location in the reference"


def test_the_reference_spans_the_year_not_one_season():
    """Sundown drifts over three hours; a fixture of one season proves little."""
    for name, loc in _reference()["locations"].items():
        sunsets = sorted(t["sunset"] for t in loc["times"].values())
        earliest = dt.datetime.strptime(sunsets[0], "%H:%M:%S")
        latest = dt.datetime.strptime(sunsets[-1], "%H:%M:%S")
        spread = (latest - earliest).total_seconds() / 3600
        assert spread >= 2.0, f"{name}: only {spread:.1f}h of sunset spread in the reference"


def test_these_tests_do_not_touch_the_network():
    """The point of the fixture. If this file ever grows a fetch, this fails.

    Scans everything above itself: naming the forbidden calls in an assertion
    means this function's own text contains them, and a naive scan of the whole
    file fails on its own error message — which it did, first time.
    """
    source = pathlib.Path(__file__).read_text()
    body = source.split("def test_these_tests_do_not_touch_the_network")[0]
    for forbidden in ("urlopen", "requests.", "httpx", "socket.create_connection"):
        assert forbidden not in body, (
            f"{forbidden} appeared in an offline test — the reference is checked in "
            "precisely so this file never needs it")
