"""Which parts of a day are available for training, given Shabbat and the chagim.

`hebrew_calendar.py` answers "what is today called?" for *display*. This module
answers a different question — "may I run, and when?" — and the two must not be
confused. `enumerate_holidays()` deliberately collapses consecutive days sharing
a name into one span, so Sukkot comes back as a single block from erev (25 Sep
2026) through Hoshana Rabbah (2 Oct). Scheduling against that span would blank
out all of chol hamoed, which is the single freest training week of the autumn.

The distinction that matters here is yom tov vs. chol hamoed, and pyluach draws
it precisely:

    HebrewDate.festival(israel=True, include_working_days=False)

returns the festival name only on days when work is forbidden, and `None` on
chol hamoed, Chanukah and Purim. That predicate — not `holiday()`, and not
`enumerate_holidays()` — is the one this module is built on.

# The evening belongs to the next day

A Jewish day runs sundown to sundown, so the evening *after* Saturday 12 Sep
2026 is not "Saturday night, free" — it is the start of Rosh Hashanah II, and
it is blocked. Every function here models a civil date as two independently
governed slots:

    daytime  — governed by this date's own status
    evening  — governed by the FOLLOWING date's status

That is why `availability()` looks at `date + 1` before it will hand back an
evening window, and it is the reason motzei-Shabbat is available on 3 Oct 2026
(Shmini Atzeret ends) but not on 12 Sep 2026 (a second day of chag follows).

# What is a rule and what is a training decision

Only observance lives here. "No running the day after a 25-hour fast" is a
sound coaching call but it is not halacha, so it belongs to the plan that
consumes this module, never to the module itself. Keeping that line sharp is
what lets the scheduler trust these answers absolutely: an LLM may *propose*
dates, but placement is validated here, deterministically, and halacha is
never left to a language model's judgement.
"""

from __future__ import annotations

import dataclasses
import datetime
import functools
from typing import List, Literal, Optional, Tuple

from astral import LocationInfo
from astral.sun import sun
from pyluach.dates import HebrewDate

# The two 25-hour fasts, which begin at sundown the evening before rather than
# at dawn. Every other fast (Tzom Gedalia, Asara B'Tevet, Ta'anit Esther, 17
# Tammuz) starts at first light, so the night before one is ordinary training
# time. pyluach spells Tisha B'Av "9 of Av"; the variants are listed so a
# spelling drift in a future release cannot silently reclassify it.
_MAJOR_FASTS = {"Yom Kippur", "Tisha B'Av", "Tishah B'Av", "9 of Av"}

# pyluach reports Yom Kippur through `festival()` and NOT through `fast_day()`,
# which returns None for it. That is a quirk of pyluach's taxonomy, not of the
# day: Yom Kippur is both a festival and a fast, and callers asking either
# question deserve a true answer. `fast_day_name()` normalises it back in.
_YOM_KIPPUR = "Yom Kippur"

Status = Literal["free", "daytime_only", "evening_only", "blocked"]

_SATURDAY = 5  # datetime.date.weekday(): Monday = 0


@dataclasses.dataclass(frozen=True)
class TimeWindow:
    """A run-able span on one civil date, in local wall-clock time."""

    start: datetime.time
    end: datetime.time
    label: str            # 'daytime' | 'morning' | 'evening'
    # True when this window is only reachable after Shabbat or a chag has
    # ended. The scheduler treats these as a last resort: a session lands
    # here only when a chag has squeezed the week and it would otherwise be
    # lost entirely.
    fallback: bool = False

    def duration_minutes(self) -> int:
        lo = self.start.hour * 60 + self.start.minute
        hi = self.end.hour * 60 + self.end.minute
        return max(0, hi - lo)


@dataclasses.dataclass(frozen=True)
class DayAvailability:
    """What a single civil date offers a training plan, and why."""

    date: datetime.date
    status: Status
    windows: Tuple[TimeWindow, ...]
    reason: str            # why the day is limited; '' when fully free
    holiday_name: str      # the yom tov / fast responsible, if any

    @property
    def is_blocked(self) -> bool:
        return self.status == "blocked"

    @property
    def has_ordinary_window(self) -> bool:
        """True if anything here is schedulable without spending the fallback."""
        return any(not w.fallback for w in self.windows)


@dataclasses.dataclass(frozen=True)
class ObservanceSettings:
    """Where sundown is computed for, and how much room to leave around it."""

    latitude: float = 31.7683          # Jerusalem
    longitude: float = 35.2137
    timezone: str = "Asia/Jerusalem"
    city: str = "Jerusalem"
    # Solar depression for tzeit hakochavim. 8.5 deg is the common Israeli
    # practice (~35-40 min after sunset here); astral's own default of 6 deg
    # is civil dusk and lands too early to rely on.
    tzeit_depression: float = 8.5
    # Candle lighting before sunset, and how long before candle lighting a
    # session must have finished — time to get home, shower and prepare.
    candle_lighting_minutes: int = 18
    erev_buffer_minutes: int = 90
    # How long after tzeit before an evening session may start.
    motzei_buffer_minutes: int = 30
    # Don't schedule before this hour even if the sun is up.
    earliest_hour: int = 5
    # Latest an evening session may start.
    latest_evening: datetime.time = datetime.time(22, 30)


#: The fallback, used only when config.yaml cannot be read at all. It is NOT
#: what the module normally uses — see `current_settings()`.
DEFAULT_SETTINGS = ObservanceSettings()

_settings_cache: "ObservanceSettings | None" = None


def settings_from_config(cfg=None) -> ObservanceSettings:
    """Build settings from config.yaml's `observance:` block.

    These fields used to exist in two places that merely happened to agree:
    the dataclass defaults above, and the config block. Nothing connected
    them, so `candle_lighting(date)` called without an explicit settings
    object silently ignored the configured location — and the recurrence
    skipping in db.py is exactly such a caller. Editing the coordinates would
    have moved the workout planner and left the calendar computing sundown
    for wherever the defaults were written.
    """
    try:
        if cfg is None:
            from assistant.config import load_config
            cfg = load_config()
        ob = cfg.observance
    except Exception:
        return DEFAULT_SETTINGS

    def _time(value, fallback):
        if isinstance(value, datetime.time):
            return value
        try:
            hh, _, mm = str(value).partition(":")
            return datetime.time(int(hh), int(mm or 0))
        except (TypeError, ValueError):
            return fallback

    d = DEFAULT_SETTINGS
    return ObservanceSettings(
        latitude=getattr(ob, "latitude", d.latitude),
        longitude=getattr(ob, "longitude", d.longitude),
        timezone=getattr(ob, "timezone", d.timezone),
        city=getattr(ob, "city", d.city),
        tzeit_depression=getattr(ob, "tzeit_depression", d.tzeit_depression),
        candle_lighting_minutes=getattr(ob, "candle_lighting_minutes", d.candle_lighting_minutes),
        erev_buffer_minutes=getattr(ob, "erev_buffer_minutes", d.erev_buffer_minutes),
        motzei_buffer_minutes=getattr(ob, "motzei_buffer_minutes", d.motzei_buffer_minutes),
        earliest_hour=getattr(ob, "earliest_hour", d.earliest_hour),
        latest_evening=_time(getattr(ob, "latest_evening", d.latest_evening), d.latest_evening),
    )


def current_settings() -> ObservanceSettings:
    """The settings every function here uses when not given one explicitly.

    Cached, because a six-week plan asks for the same handful of dates
    repeatedly; call `reload_settings()` after changing the configuration or
    the device location.
    """
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = settings_from_config()
    return _settings_cache


def reload_settings() -> ObservanceSettings:
    """Forget the cached settings so the next call re-reads the configuration."""
    global _settings_cache
    _settings_cache = None
    _sun_times.cache_clear()
    return current_settings()


# ---------------------------------------------------------------------------
# Sun times
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=2048)
def _sun_times(
    date: datetime.date, lat: float, lon: float, tz: str, depression: float
) -> Optional[Tuple[datetime.time, datetime.time, datetime.time]]:
    """(sunrise, sunset, tzeit) in local wall-clock time, or None if unavailable.

    Cached on the primitive arguments rather than the settings object so the
    key stays hashable and stable; a plan spanning six weeks asks for the same
    handful of dates repeatedly as it validates and re-validates placements.
    """
    try:
        loc = LocationInfo(latitude=lat, longitude=lon, timezone=tz)
        s = sun(loc.observer, date=date, tzinfo=loc.timezone)
        dusk = sun(loc.observer, date=date, tzinfo=loc.timezone, dawn_dusk_depression=depression)["dusk"]
        return (s["sunrise"].time(), s["sunset"].time(), dusk.time())
    except Exception:
        # Polar edge cases and out-of-range years must not take the caller
        # down; every consumer treats None as "assume an ordinary day".
        return None


def _shift(t: datetime.time, minutes: int) -> datetime.time:
    base = datetime.datetime.combine(datetime.date(2000, 1, 1), t)
    return (base + datetime.timedelta(minutes=minutes)).time()


def sunset(date: datetime.date, settings: Optional[ObservanceSettings] = None) -> Optional[datetime.time]:
    settings = settings or current_settings()
    times = _sun_times(date, settings.latitude, settings.longitude,
                       settings.timezone, settings.tzeit_depression)
    return times[1] if times else None


def tzeit(date: datetime.date, settings: Optional[ObservanceSettings] = None) -> Optional[datetime.time]:
    settings = settings or current_settings()
    """Nightfall — when Shabbat or a chag ends on *date*."""
    times = _sun_times(date, settings.latitude, settings.longitude,
                       settings.timezone, settings.tzeit_depression)
    return times[2] if times else None


def candle_lighting(date: datetime.date, settings: Optional[ObservanceSettings] = None) -> Optional[datetime.time]:
    settings = settings or current_settings()
    ss = sunset(date, settings)
    return _shift(ss, -settings.candle_lighting_minutes) if ss else None


# ---------------------------------------------------------------------------
# Day classification
# ---------------------------------------------------------------------------

def is_shabbat(date: datetime.date) -> bool:
    return date.weekday() == _SATURDAY


def yom_tov_name(date: datetime.date, israel: bool = True) -> str:
    """The festival name if work is forbidden on *date*, else ''.

    Returns '' on chol hamoed, Chanukah and Purim — the whole point of using
    `include_working_days=False` rather than `holiday()`.
    """
    try:
        name = HebrewDate.from_pydate(date).festival(
            israel=israel, include_working_days=False
        )
        return name or ""
    except Exception:
        return ""


def is_yom_tov(date: datetime.date, israel: bool = True) -> bool:
    return bool(yom_tov_name(date, israel))


def is_chol_hamoed(date: datetime.date, israel: bool = True) -> bool:
    """A weekday of Pesach or Sukkot: named by `holiday()`, free per `festival()`."""
    try:
        hd = HebrewDate.from_pydate(date)
        if not hd.holiday(israel=israel):
            return False
        if hd.festival(israel=israel, include_working_days=False):
            return False
        return hd.holiday(israel=israel) in {"Succos", "Pesach"}
    except Exception:
        return False


def fast_day_name(date: datetime.date) -> str:
    """The fast falling on *date*, or ''.

    Yom Kippur is folded back in explicitly. pyluach files it under
    `festival()` and returns None from `fast_day()`, but it is a fast — the
    longest of the year — and code asking "is this a fast day?" must not be
    told otherwise merely because the day is also a festival.
    """
    try:
        hd = HebrewDate.from_pydate(date)
        if hd.festival(israel=True, include_working_days=False) == _YOM_KIPPUR:
            return _YOM_KIPPUR
        return hd.fast_day() or ""
    except Exception:
        return ""


def is_fast_day(date: datetime.date) -> bool:
    """Any fast, major or minor. True on Yom Kippur as well as Tzom Gedalia."""
    return bool(fast_day_name(date))


def is_major_fast(date: datetime.date) -> bool:
    """A 25-hour fast — Yom Kippur or Tisha B'Av — binding from the night before."""
    return fast_day_name(date) in _MAJOR_FASTS


def is_minor_fast(date: datetime.date) -> bool:
    """A dawn-to-nightfall fast. Treated as a full rest day by house rule.

    An unrecognised fast name falls here rather than being waved through: the
    safe default for a name we don't know is "don't schedule a run on it".
    """
    name = fast_day_name(date)
    return bool(name) and name not in _MAJOR_FASTS


def _starts_at_sundown(date: datetime.date, israel: bool) -> bool:
    """Does the restriction on *date* already bind from the previous evening?

    True for Shabbat, every yom tov, and the two 25-hour fasts. False for the
    minor fasts, which begin at first light — so the night before one is
    ordinary training time.
    """
    if is_shabbat(date) or is_yom_tov(date, israel):
        return True
    return is_major_fast(date)


def _daytime_blocked(date: datetime.date, israel: bool) -> Tuple[bool, str]:
    """(blocked?, reason) for the daylight hours of *date* itself."""
    yt = yom_tov_name(date, israel)
    if is_shabbat(date) and yt:
        return True, f"Shabbat & {yt}"
    if is_shabbat(date):
        return True, "Shabbat"
    if yt:
        return True, yt
    fast = fast_day_name(date)
    if fast:
        return True, fast
    return False, ""


# ---------------------------------------------------------------------------
# The public answer
# ---------------------------------------------------------------------------

def availability(
    date: datetime.date,
    settings: Optional[ObservanceSettings] = None,
    israel: bool = True,
) -> DayAvailability:
    """What *date* offers: its daylight hours, and the evening that follows it.

    The evening slot is governed by `date + 1`, not by `date` — see the module
    docstring. An evening that opens only once Shabbat or a chag has ended is
    marked `fallback=True` so the scheduler can prefer ordinary days and reach
    for motzei Shabbat only when a chag would otherwise cost a session.
    """
    settings = settings or current_settings()
    windows: List[TimeWindow] = []

    day_blocked, day_reason = _daytime_blocked(date, israel)
    try:
        tomorrow = date + datetime.timedelta(days=1)
    except OverflowError:
        # date.max: there is no following day to consult. Treat the evening as
        # ordinary rather than letting the arithmetic take the caller down —
        # the same degrade-never-raise guarantee hebrew_calendar makes.
        tomorrow = date
    eve_blocked = _starts_at_sundown(tomorrow, israel) if tomorrow != date else False
    _, tomorrow_reason = _daytime_blocked(tomorrow, israel) if tomorrow != date else (False, "")

    times = _sun_times(date, settings.latitude, settings.longitude,
                       settings.timezone, settings.tzeit_depression)
    if times is None:
        # No solar data: fall back to fixed civil hours rather than refusing
        # to schedule at all.
        sunrise_t, sunset_t, tzeit_t = (
            datetime.time(6, 30), datetime.time(18, 30), datetime.time(19, 10)
        )
    else:
        sunrise_t, sunset_t, tzeit_t = times

    # --- the day itself ---------------------------------------------------
    if not day_blocked:
        start = max(sunrise_t, datetime.time(settings.earliest_hour, 0))
        if eve_blocked:
            # Erev Shabbat / erev chag: finish, and be home, well before candle
            # lighting. This is what turns Friday 11 Sep 2026 into a morning-only
            # day rather than a lost one.
            cl = _shift(sunset_t, -settings.candle_lighting_minutes)
            end = _shift(cl, -settings.erev_buffer_minutes)
            label = "morning"
        else:
            # An ordinary day runs from first light to a civil cut-off, not to
            # sunset: an 18:30 weeknight run in October is the norm here, not an
            # exception, and stopping the window at sunset would make the
            # post-18-October evening plan unschedulable.
            end = settings.latest_evening
            label = "daytime"
        if end > start:
            windows.append(TimeWindow(start=start, end=end, label=label))

    # --- the evening on the far side of a blocked day -----------------------
    # Only reachable when the day just ended was blocked and the next one is
    # not itself bound from sundown: motzei Shabbat, or motzei chag. Always
    # marked fallback so the scheduler spends it only to save a lost session.
    elif not eve_blocked:
        eve_start = _shift(tzeit_t, settings.motzei_buffer_minutes)
        if eve_start < settings.latest_evening:
            windows.append(TimeWindow(
                start=eve_start, end=settings.latest_evening,
                label="evening", fallback=True,
            ))

    # --- summarise ---------------------------------------------------------
    labels = {w.label for w in windows}
    if not windows:
        status: Status = "blocked"
    elif labels == {"evening"}:
        status = "evening_only"
    elif labels == {"morning"}:
        status = "daytime_only"
    else:
        status = "free"

    reason = day_reason
    if not reason and status == "daytime_only":
        reason = f"Erev {tomorrow_reason}" if tomorrow_reason else "Erev Shabbat"

    return DayAvailability(
        date=date,
        status=status,
        windows=tuple(windows),
        reason=reason,
        holiday_name=day_reason or "",
    )


def blocked_days(
    start: datetime.date,
    end: datetime.date,
    settings: Optional[ObservanceSettings] = None,
    israel: bool = True,
) -> List[DayAvailability]:
    """Every day in [start, end] that is not fully free — for prompts and previews."""
    settings = settings or current_settings()
    out: List[DayAvailability] = []
    cur = start
    while cur <= end:
        av = availability(cur, settings, israel)
        if av.status != "free":
            out.append(av)
        cur += datetime.timedelta(days=1)
    return out
