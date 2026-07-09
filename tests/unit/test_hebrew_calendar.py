"""Unit tests for assistant/hebrew_calendar.py — previously zero coverage despite
containing legislated Knesset date-shift rules (easy to get subtly wrong) and a
graceful-degradation contract (every function must return a safe fallback instead
of raising, since these run inside PyQt slots that abort the app on an unhandled
exception).
"""
from __future__ import annotations

import datetime

from assistant.hebrew_calendar import (
    enumerate_holidays,
    hebrew_date_string,
    hebrew_day_label,
    hebrew_month_year_string,
    _shift_yom_hashoah,
    _shift_yom_hazikaron_atzmaut,
)


# ---------------------------------------------------------------------------
# Date formatting
# ---------------------------------------------------------------------------

def test_hebrew_date_string_english_mode():
    result = hebrew_date_string(datetime.date(2026, 4, 1), mode="english")
    assert result == "14 Nissan 5786"


def test_hebrew_date_string_hebrew_mode_uses_gematria_not_digits():
    result = hebrew_date_string(datetime.date(2026, 4, 1), mode="hebrew")
    assert result
    assert not any(c.isdigit() for c in result)


def test_hebrew_date_string_both_mode_includes_english_and_hebrew():
    result = hebrew_date_string(datetime.date(2026, 4, 1), mode="both")
    assert "14 Nissan 5786" in result
    # Hebrew gematira portion is parenthesized and appended
    assert "(" in result and ")" in result


def test_hebrew_day_label_rosh_chodesh_includes_month_name():
    """1st of a Hebrew month should show the month name, not just the day."""
    # 1 Nissan 5786 = 2026-03-19
    label = hebrew_day_label(datetime.date(2026, 3, 19))
    assert "נ" in label  # Nissan's Hebrew name starts with nun


def test_hebrew_day_label_non_first_day_is_just_the_day():
    label = hebrew_day_label(datetime.date(2026, 4, 1))  # 14 Nissan, not Rosh Chodesh
    assert label == "י״ד"


def test_hebrew_month_year_string():
    result = hebrew_month_year_string(datetime.date(2026, 4, 1))
    assert "ניסן" in result


# ---------------------------------------------------------------------------
# Graceful degradation — must never raise, even at datetime extremes
# ---------------------------------------------------------------------------

def test_functions_never_raise_at_date_min():
    hebrew_date_string(datetime.date.min)
    hebrew_day_label(datetime.date.min)
    hebrew_month_year_string(datetime.date.min)
    enumerate_holidays(datetime.date.min, datetime.date.min + datetime.timedelta(days=2))


def test_functions_never_raise_at_date_max():
    hebrew_date_string(datetime.date.max)
    hebrew_day_label(datetime.date.max)
    hebrew_month_year_string(datetime.date.max)
    enumerate_holidays(datetime.date.max - datetime.timedelta(days=2), datetime.date.max)


# ---------------------------------------------------------------------------
# Holiday enumeration — multi-day holidays merge into one span
# ---------------------------------------------------------------------------

def test_pesach_2026_spans_full_eight_days_as_one_holiday():
    """Pesach is an 8-day holiday outside Israel's classical cycle handling —
    consecutive same-name days must merge into a single Holiday, not one per day.
    """
    holidays = enumerate_holidays(datetime.date(2026, 3, 25), datetime.date(2026, 4, 15))
    pesach = [h for h in holidays if h.name_en == "Pesach"]
    assert len(pesach) == 1
    assert pesach[0].gregorian_erev_start == datetime.date(2026, 4, 1)
    assert pesach[0].gregorian_end == datetime.date(2026, 4, 8)
    assert pesach[0].category == "major"


def test_purim_is_a_minor_holiday_taanis_esther_is_a_fast():
    holidays = enumerate_holidays(datetime.date(2026, 2, 25), datetime.date(2026, 3, 10))
    by_name = {h.name_en: h for h in holidays}
    assert by_name["Purim"].category == "minor"
    assert by_name["Taanis Esther"].category == "fast"


def test_modern_israeli_holidays_present_and_correctly_ordered():
    """Yom HaShoah -> Yom HaZikaron -> Yom Ha'atzmaut, in that chronological order."""
    holidays = enumerate_holidays(datetime.date(2026, 4, 10), datetime.date(2026, 4, 25))
    names_in_order = [h.name_en for h in holidays if h.category == "modern"]
    assert names_in_order == ["Yom HaShoah", "Yom HaZikaron", "Yom Ha'atzmaut"]


def test_holidays_outside_range_are_excluded():
    holidays = enumerate_holidays(datetime.date(2026, 6, 1), datetime.date(2026, 6, 2))
    assert holidays == []


def test_enumerate_holidays_is_cached_and_returns_equal_results():
    """lru_cache-backed — repeated calls with identical args must be safe (no
    accidental in-place mutation of the cached list by a caller).
    """
    a = enumerate_holidays(datetime.date(2026, 1, 1), datetime.date(2026, 12, 31))
    b = enumerate_holidays(datetime.date(2026, 1, 1), datetime.date(2026, 12, 31))
    assert a == b


# ---------------------------------------------------------------------------
# Knesset-legislated day-shift rules — every branch of the weekday logic
# ---------------------------------------------------------------------------

def test_yom_hazikaron_atzmaut_saturday_shifts_to_thursday():
    """5 Iyar falling on Saturday -> Ha'atzmaut moves to 3 Iyar (Thursday)."""
    zikaron, atzmaut = _shift_yom_hazikaron_atzmaut(5781)
    assert atzmaut == datetime.date(2021, 4, 15)
    assert zikaron == datetime.date(2021, 4, 14)


def test_yom_hazikaron_atzmaut_friday_shifts_to_thursday():
    """5 Iyar falling on Friday -> Ha'atzmaut moves to 4 Iyar (Thursday)."""
    zikaron, atzmaut = _shift_yom_hazikaron_atzmaut(5782)
    assert atzmaut == datetime.date(2022, 5, 5)
    assert zikaron == datetime.date(2022, 5, 4)


def test_yom_hazikaron_atzmaut_monday_shifts_to_tuesday():
    """5 Iyar falling on Monday -> Ha'atzmaut moves to 6 Iyar (Tuesday)."""
    zikaron, atzmaut = _shift_yom_hazikaron_atzmaut(5784)
    assert atzmaut == datetime.date(2024, 5, 14)
    assert zikaron == datetime.date(2024, 5, 13)


def test_yom_hazikaron_atzmaut_wednesday_unchanged():
    """5 Iyar falling on Wednesday -> no shift needed, stays 5 Iyar."""
    zikaron, atzmaut = _shift_yom_hazikaron_atzmaut(5786)
    assert atzmaut == datetime.date(2026, 4, 22)
    assert zikaron == datetime.date(2026, 4, 21)


def test_yom_hazikaron_is_always_the_day_before_atzmaut():
    for year in (5781, 5782, 5784, 5786, 5788, 5792):
        zikaron, atzmaut = _shift_yom_hazikaron_atzmaut(year)
        assert atzmaut - zikaron == datetime.timedelta(days=1)


def test_yom_hashoah_friday_shifts_to_thursday():
    """27 Nissan falling on Friday -> moves to 26 Nissan (Thursday)."""
    assert _shift_yom_hashoah(5781) == datetime.date(2021, 4, 8)


def test_yom_hashoah_sunday_shifts_to_monday():
    """27 Nissan falling on Sunday -> moves to 28 Nissan (Monday)."""
    assert _shift_yom_hashoah(5784) == datetime.date(2024, 5, 6)


def test_yom_hashoah_weekday_unchanged():
    """27 Nissan on an ordinary weekday -> no shift."""
    assert _shift_yom_hashoah(5786) == datetime.date(2026, 4, 14)
