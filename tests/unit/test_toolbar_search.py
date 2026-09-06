"""The toolbar search box's jump-to-date parsing (pure; the class is not
instantiated — CalendarWindow construction needs the full app stack, which
no unit test builds today)."""

from __future__ import annotations

import datetime

import pytest

pytest.importorskip("PyQt6")

from assistant.calendar_ui.window import CalendarWindow  # noqa: E402

parse = CalendarWindow._parse_jump_date


def test_iso_date():
    assert parse("2026-10-14") == datetime.date(2026, 10, 14)


def test_day_month_defaults_to_current_year():
    assert parse("14/10") == datetime.date(datetime.date.today().year, 10, 14)


def test_day_month_year_and_two_digit_year():
    assert parse("14/10/2027") == datetime.date(2027, 10, 14)
    assert parse("14/10/27") == datetime.date(2027, 10, 14)


def test_text_is_not_a_date():
    assert parse("dentist") is None
    assert parse("32/13") is None
    assert parse("14/10/x") is None
