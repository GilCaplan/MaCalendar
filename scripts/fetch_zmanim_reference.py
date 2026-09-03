"""Fetch authoritative sundown times once, so the offline computation can be checked.

The assistant computes sunset, candle lighting and nightfall itself, from solar
geometry, because it has to work with no network. That is the right design and
it is also unfalsifiable on its own: a wrong sundown looks exactly like a right
one until something independent disagrees.

So this script — and ONLY this script — goes to the network. It asks hebcal.com
for the same times at the same coordinates on the same dates, and writes them to
`tests/fixtures/zmanim_reference.json`. `tests/unit/test_zmanim_accuracy.py`
then compares our arithmetic against that file, offline, for ever.

Hebcal is the reference because it publishes `tzeit85deg` — nightfall at 8.5
degrees of solar depression, which is exactly the definition `observance.py`
uses — so the comparison is like for like rather than against some other
opinion about when the stars come out. Its content is CC-BY-4.0 licensed.

    python -m scripts.fetch_zmanim_reference            # refresh the fixture
    python -m scripts.fetch_zmanim_reference --check    # compare, write nothing

Run it when the computation changes, when a location is added, or never — the
fixture is checked in and the tests do not need it re-fetched.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://www.hebcal.com/zmanim"
FIXTURE = pathlib.Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "zmanim_reference.json"

#: Israel is the default the assistant ships with; the others are there so a
#: mistake that only shows up far from home — a timezone applied twice, a
#: longitude sign dropped, a hemisphere assumption — cannot hide.
LOCATIONS = [
    {"name": "Jerusalem",  "latitude": 31.7683,  "longitude": 35.2137,   "tz": "Asia/Jerusalem"},
    {"name": "Jerusalem", "latitude": 31.7683,  "longitude": 35.2137,   "tz": "Asia/Jerusalem"},
    {"name": "New York",  "latitude": 40.7128,  "longitude": -74.0060,  "tz": "America/New_York"},
    {"name": "London",    "latitude": 51.5074,  "longitude": -0.1278,   "tz": "Europe/London"},
    {"name": "Sydney",    "latitude": -33.8688, "longitude": 151.2093,  "tz": "Australia/Sydney"},
]

#: Solstices and equinoxes, either side of the daylight-saving changeovers, plus
#: the shortest and longest Fridays. Sundown drifts by over three hours across a
#: year, so a fixture of convenient dates would prove very little.
DATES = [
    "2026-01-02",   # deep winter, earliest candle lighting
    "2026-03-20",   # equinox
    "2026-03-27",   # Israel DST begins the day before — the classic off-by-an-hour
    "2026-06-19",   # near the solstice, latest sunset
    "2026-09-04",   # equinox-ish; the date the artifact quotes
    "2026-10-30",   # after the northern clocks go back
    "2026-12-18",   # near the solstice, earliest sunset
]

FIELDS = ("sunrise", "sunset", "tzeit85deg", "tzeit7083deg")


def fetch_one(loc: dict, date: str, *, retries: int = 3) -> dict:
    query = urllib.parse.urlencode({
        "cfg": "json", "sec": 1, "date": date,
        "latitude": loc["latitude"], "longitude": loc["longitude"], "tzid": loc["tz"],
    })
    url = f"{API}?{query}"
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "MACalendar-zmanim-check/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.load(resp)
            break
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
            if attempt == retries - 1:
                raise RuntimeError(f"{loc['name']} {date}: {exc}") from exc
            time.sleep(1.5 * (attempt + 1))
    else:                                              # pragma: no cover
        raise RuntimeError(str(last))

    times = payload.get("times") or {}
    missing = [f for f in FIELDS if f not in times]
    if missing:
        raise RuntimeError(f"{loc['name']} {date}: response is missing {missing}")

    # Keep the local wall-clock time only. The offsets are what we are checking
    # against, so storing them as instants would make a timezone bug invisible.
    return {f: times[f][11:19] for f in FIELDS}


def build() -> dict:
    out = {
        "_source": "https://www.hebcal.com/home/1663/zmanim-halachic-times-api",
        "_licence": "Hebcal content is CC-BY-4.0",
        "_fetched": dt.date.today().isoformat(),
        "_note": ("Local wall-clock times. tzeit85deg is nightfall at 8.5 degrees of "
                  "solar depression, the same definition assistant/observance.py uses."),
        "locations": {},
    }
    for loc in LOCATIONS:
        rows = {}
        for date in DATES:
            rows[date] = fetch_one(loc, date)
            print(f"  {loc['name']:<10} {date}  {rows[date]['sunset']}")
            time.sleep(0.4)                     # be a considerate client
        out["locations"][loc["name"]] = {
            "latitude": loc["latitude"], "longitude": loc["longitude"],
            "timezone": loc["tz"], "times": rows,
        }
    return out


def add_location(spec: str) -> int:
    """Fetch one more place and merge it in, leaving the rest of the file alone.

    Adding a location is a one-off: once its times are here they are here for
    good, and nothing at runtime ever goes looking for them again. Removing one
    means deleting its block from the fixture.
    """
    try:
        name, lat, lon, tz = [part.strip() for part in spec.split(",", 3)]
        loc = {"name": name, "latitude": float(lat), "longitude": float(lon), "tz": tz}
    except ValueError:
        print("--add wants NAME,LAT,LON,TZ — e.g. "
              "'Toronto,43.6532,-79.3832,America/Toronto'", file=sys.stderr)
        return 2

    data = json.loads(FIXTURE.read_text()) if FIXTURE.exists() else {"locations": {}}
    if name in data["locations"]:
        print(f"{name} is already in the reference; refetching it.")

    print(f"Fetching {name} ({loc['latitude']}, {loc['longitude']}) for {len(DATES)} dates\n")
    rows = {}
    for date in DATES:
        try:
            rows[date] = fetch_one(loc, date)
        except RuntimeError as exc:
            print(f"\nFAILED: {exc}", file=sys.stderr)
            print("Nothing was written; the existing reference is untouched.", file=sys.stderr)
            return 1
        print(f"  {date}  sunset {rows[date]['sunset']}")
        time.sleep(0.4)

    data["locations"][name] = {
        "latitude": loc["latitude"], "longitude": loc["longitude"],
        "timezone": loc["tz"], "times": rows,
    }
    data["_fetched"] = dt.date.today().isoformat()
    FIXTURE.write_text(json.dumps(data, indent=2) + "\n")
    print(f"\nAdded {name}. {len(data['locations'])} locations in the reference. "
          "Run the tests to check the computation against it.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="fetch and report differences without writing the fixture")
    ap.add_argument("--add", metavar="NAME,LAT,LON,TZ",
                    help="fetch one more location and merge it into the fixture, "
                         "e.g. --add 'Toronto,43.6532,-79.3832,America/Toronto'")
    args = ap.parse_args()

    if args.add:
        return add_location(args.add)

    print(f"Fetching {len(LOCATIONS)} locations × {len(DATES)} dates from hebcal.com\n")
    try:
        fresh = build()
    except RuntimeError as exc:
        print(f"\nFAILED: {exc}", file=sys.stderr)
        print("The fixture is checked in, so the tests still run. Try again later.",
              file=sys.stderr)
        return 1

    if args.check and FIXTURE.exists():
        old = json.loads(FIXTURE.read_text())
        drift = [
            f"{name} {date} {field}: {vals[field]} → {fresh['locations'][name]['times'][date][field]}"
            for name, loc in old.get("locations", {}).items()
            for date, vals in loc.get("times", {}).items()
            for field in FIELDS
            if fresh["locations"].get(name, {}).get("times", {}).get(date, {}).get(field) != vals[field]
        ]
        print("\n" + ("\n".join(f"  changed: {d}" for d in drift) if drift
                      else "  the reference is unchanged"))
        return 0

    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(json.dumps(fresh, indent=2) + "\n")
    print(f"\nWrote {FIXTURE.relative_to(pathlib.Path.cwd())} "
          f"({len(LOCATIONS) * len(DATES)} days)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
