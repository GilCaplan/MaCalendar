"""Times introduced by "at" are start times.

"dinner with Danny at 8 pm" was booked 18:00–20:00: the model filed the stated
time as the END and invented a start two hours earlier. Knowing which times were
spoken as "at X" lets that be undone — but only those, so a range like
"from 3 to 4:30" is left alone.
"""
from __future__ import annotations

import pytest

from assistant.api.server import _at_times


@pytest.mark.parametrize("said, expected", [
    ("dinner with Danny at 8 pm",  {"20:00"}),
    ("shacharit at 6:30 am",       {"06:30"}),
    ("gym at around 6",            {"06:00", "18:00"}),   # bare hour: both readings
    ("call at 9:15am",             {"09:15"}),
])
def test_times_said_with_at_are_collected(said, expected):
    assert _at_times(said) == expected


@pytest.mark.parametrize("said", [
    "meeting from 3 to 4:30 pm",
    "gym for an hour tomorrow",
    "lunch with Tal",
])
def test_times_not_said_with_at_are_ignored(said):
    assert _at_times(said) == set()


def test_a_range_that_starts_with_at_keeps_only_the_start():
    assert _at_times("lunch at 12 until 2") == {"12:00", "00:00"}
