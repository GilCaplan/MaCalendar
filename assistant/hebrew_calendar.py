"""Hebrew calendar date formatting and Jewish/Israeli holiday enumeration.

Wraps `pyluach` (pure Python, fully offline — no network calls) so Hebrew
dates and the annual holiday cycle stay available without compromising this
app's local-first design. Modern Israeli national holidays that pyluach's
own dataset doesn't cover (Yom HaShoah, Yom HaZikaron, Yom Ha'atzmaut, Yom
Yerushalayim, Sigd) are computed here from their legislated Hebrew-calendar
dates, including the Knesset-mandated day shifts that avoid Yom HaZikaron /
Yom Ha'atzmaut / Yom HaShoah falling adjacent to Shabbat.

Every Jewish calendar day begins at sundown the evening before its named
Gregorian date. `enumerate_holidays()` reflects this: each `Holiday` spans
from `gregorian_erev_start` (the evening-before civil date) through
`gregorian_end` (the last full civil day) inclusive.
"""

from __future__ import annotations

import dataclasses
import datetime
import functools
from typing import Dict, List, Literal, Tuple

from pyluach.dates import HebrewDate
from pyluach.hebrewcal import to_hebrew_numeral

DisplayMode = Literal["english", "hebrew", "both"]
HolidayCategory = Literal["major", "minor", "fast", "modern"]

# Hebrew month numbers per pyluach's HebrewDate constructor (Nissan = 1).
_NISSAN = 1
_IYAR = 2
_CHESHVAN = 8

# pyluach's `.weekday()`: 1 = Sunday ... 7 = Saturday.
_SUNDAY, _MONDAY, _FRIDAY, _SATURDAY = 1, 2, 6, 7

_MAJOR_FESTIVALS = {
    "Rosh Hashana", "Yom Kippur", "Succos", "Shmini Atzeres",
    "Simchas Torah", "Pesach", "Shavuos",
}

_MODERN_ISRAELI = {
    "Yom HaShoah", "Yom HaZikaron", "Yom Ha'atzmaut", "Yom Yerushalayim", "Sigd",
}

_MODERN_HEBREW_NAMES: Dict[str, str] = {
    "Yom HaShoah": "יום השואה",
    "Yom HaZikaron": "יום הזיכרון",
    "Yom Ha'atzmaut": "יום העצמאות",
    "Yom Yerushalayim": "יום ירושלים",
    "Sigd": "סיגד",
}


@dataclasses.dataclass
class Holiday:
    name_en: str
    name_he: str
    category: HolidayCategory
    gregorian_erev_start: datetime.date
    gregorian_end: datetime.date


# Every function below is called directly from Qt slots (view refresh,
# navigation, settings save) on every render. PyQt aborts the whole app on
# an unhandled exception raised inside a slot, so a rare pyluach/date-math
# failure (e.g. OverflowError from `date - timedelta(...)` underflowing past
# datetime.date.min when a user navigates to year 1, or overflowing past
# date.max near year 9999) must degrade gracefully here rather than crash —
# this is the single place that guarantee is enforced for every caller.

def hebrew_date_string(date: datetime.date, mode: DisplayMode = "english") -> str:
    """Format *date* per the configured Hebrew-calendar display mode.

    'hebrew' mode always renders traditional Hebrew gematria letters (e.g.
    "כ״ט תשרי תשפ״ו"), never Arabic numerals.
    """
    try:
        hd = HebrewDate.from_pydate(date)
        if mode == "hebrew":
            return hd.hebrew_date_string()
        english = f"{hd.day} {hd.month_name()} {hd.year}"
        if mode == "english":
            return english
        return f"{english}  ({hd.hebrew_date_string()})"
    except Exception:
        return date.isoformat() if mode != "hebrew" else ""


def hebrew_day_label(date: datetime.date) -> str:
    """Compact per-cell subtitle for grid views: just the day in gematria
    (e.g. "י״ח"), since the month/year repeating on every cell in a Month or
    Week grid is redundant. On the 1st of a Hebrew month (Rosh Chodesh) the
    month name is included too, so month transitions are still visible.
    """
    try:
        hd = HebrewDate.from_pydate(date)
        if hd.day == 1:
            return f"{hd.hebrew_day()} {hd.month_name(hebrew=True)}"
        return hd.hebrew_day()
    except Exception:
        return ""


def hebrew_month_year_string(date: datetime.date) -> str:
    """Hebrew month + year (no day) — e.g. "תמוז תשפ״ו" — for view titles."""
    try:
        hd = HebrewDate.from_pydate(date)
        return f"{hd.month_name(hebrew=True)} {to_hebrew_numeral(hd.year)}"
    except Exception:
        return ""


def _category_for(name_en: str, is_fast: bool) -> HolidayCategory:
    if is_fast:
        return "fast"
    if name_en in _MAJOR_FESTIVALS:
        return "major"
    return "minor"


def _classical_holidays(
    start: datetime.date, end: datetime.date, israel: bool
) -> List[Holiday]:
    """Enumerate pyluach's classical/rabbinic holiday cycle touching [start, end]."""
    scan_start = start - datetime.timedelta(days=1)
    scan_end = end + datetime.timedelta(days=1)

    occurrences: List[Tuple[str, str, bool, datetime.date]] = []
    cur = scan_start
    while cur <= scan_end:
        hd = HebrewDate.from_pydate(cur)
        name_en = hd.holiday(israel=israel)
        if name_en:
            name_he = hd.holiday(israel=israel, hebrew=True)
            occurrences.append((name_en, name_he, bool(hd.fast_day()), cur))
        cur += datetime.timedelta(days=1)

    holidays: List[Holiday] = []
    i = 0
    while i < len(occurrences):
        name_en, name_he, is_fast, first_day = occurrences[i]
        j = i
        while (
            j + 1 < len(occurrences)
            and occurrences[j + 1][0] == name_en
            and occurrences[j + 1][3] == occurrences[j][3] + datetime.timedelta(days=1)
        ):
            j += 1
        last_day = occurrences[j][3]
        erev_start = first_day - datetime.timedelta(days=1)
        if erev_start <= end and last_day >= start:
            holidays.append(Holiday(
                name_en=name_en,
                name_he=name_he,
                category=_category_for(name_en, is_fast),
                gregorian_erev_start=erev_start,
                gregorian_end=last_day,
            ))
        i = j + 1
    return holidays


def _shift_yom_hashoah(year: int) -> datetime.date:
    """27 Nissan, moved off Friday (-> Thursday) / Sunday (-> Monday)."""
    weekday = HebrewDate(year, _NISSAN, 27).weekday()
    if weekday == _FRIDAY:
        day = 26
    elif weekday == _SUNDAY:
        day = 28
    else:
        day = 27
    return HebrewDate(year, _NISSAN, day).to_pydate()


def _shift_yom_hazikaron_atzmaut(year: int) -> Tuple[datetime.date, datetime.date]:
    """Returns (Yom HaZikaron, Yom Ha'atzmaut). Base = 5 Iyar (Ha'atzmaut).

    Knesset-legislated shifts: 5 Iyar on Saturday -> Thursday (3 Iyar); on
    Friday -> Thursday (4 Iyar); on Monday -> Tuesday (6 Iyar); on Wednesday
    -> unchanged. Yom HaZikaron is always the day immediately before.
    """
    weekday = HebrewDate(year, _IYAR, 5).weekday()
    if weekday == _SATURDAY:
        atzmaut_day = 3
    elif weekday == _FRIDAY:
        atzmaut_day = 4
    elif weekday == _MONDAY:
        atzmaut_day = 6
    else:
        atzmaut_day = 5
    atzmaut = HebrewDate(year, _IYAR, atzmaut_day).to_pydate()
    zikaron = HebrewDate(year, _IYAR, atzmaut_day - 1).to_pydate()
    return zikaron, atzmaut


def _modern_israeli_holidays(start: datetime.date, end: datetime.date) -> List[Holiday]:
    lo_year = HebrewDate.from_pydate(start).year
    hi_year = HebrewDate.from_pydate(end).year

    holidays: List[Holiday] = []
    for year in range(lo_year, hi_year + 1):
        zikaron, atzmaut = _shift_yom_hazikaron_atzmaut(year)
        candidates = (
            ("Yom HaShoah", _shift_yom_hashoah(year)),
            ("Yom HaZikaron", zikaron),
            ("Yom Ha'atzmaut", atzmaut),
            ("Yom Yerushalayim", HebrewDate(year, _IYAR, 28).to_pydate()),
            ("Sigd", HebrewDate(year, _CHESHVAN, 29).to_pydate()),
        )
        for name_en, day in candidates:
            erev_start = day - datetime.timedelta(days=1)
            if erev_start <= end and day >= start:
                holidays.append(Holiday(
                    name_en=name_en,
                    name_he=_MODERN_HEBREW_NAMES[name_en],
                    category="modern",
                    gregorian_erev_start=erev_start,
                    gregorian_end=day,
                ))
    return holidays


@functools.lru_cache(maxsize=256)
def enumerate_holidays(
    start: datetime.date, end: datetime.date, israel: bool = True
) -> List[Holiday]:
    """Return all holidays whose display span touches [start, end] (inclusive).

    `gregorian_erev_start` is the evening-before civil date (when the holiday
    begins at sundown); `gregorian_end` is its last full civil day. Returns
    `[]` instead of raising if the computation fails for any reason (e.g. a
    date range up against datetime.date.min/max) — see the module-level note
    above `hebrew_date_string()` for why this must never propagate.

    Memoized: Month/Week/Day views each re-derive their visible date range
    and call this on every `refresh()` (event add/edit/delete/sync, not just
    navigation), so the same (start, end, israel) key is hit repeatedly
    between actual navigations — the day-by-day Hebrew<->Gregorian scan is
    pure given its inputs, so caching is exact, not an approximation.
    """
    try:
        holidays = _classical_holidays(start, end, israel)
        holidays += _modern_israeli_holidays(start, end)
        holidays.sort(key=lambda h: h.gregorian_erev_start)
        return holidays
    except Exception:
        return []
