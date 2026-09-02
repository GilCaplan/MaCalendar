"""Repeating events, and the cadences that cannot be represented.

recurrence is one of daily, weekly or monthly. Anything else the speaker says
gets rounded to one of those, and the rounding was happening silently — which
is fine when it is right and dangerous when it is not:

    "standup every sunday and tuesday at 9am"
        two weekly series, both starting on a Wednesday. 106 events, not one
        of them on a Sunday or a Tuesday.
    "therapy every other tuesday at 5pm"
        one event. Not a fortnightly series, not a weekly one — one.
    "daven mincha every weekday at 1:30pm"
        366 daily events, including every Shabbat.

The anchor bug is fixed. The rounding is not — it cannot be, without a richer
model — so it is announced instead.
"""
from __future__ import annotations

import pytest

from assistant.api.server import _named_weekdays, _unsupported_cadence


@pytest.mark.parametrize("text, expected", [
    ("gym every monday at 6am", {0}),
    ("standup every sunday and tuesday at 9am", {1, 6}),
    ("lunch with Tal every friday at noon", {4}),
    ("therapy every other tuesday at 5pm", {1}),
    ("shacharit every morning at 6:30", set()),
    ("go pray mincha every day at 1900", set()),
])
def test_the_weekdays_a_sentence_names(text, expected):
    assert _named_weekdays(text) == expected


def test_a_weekday_inside_another_word_is_not_a_weekday(text=None):
    """"sunday" must not be found inside "sundays" only by accident, nor a
    stray "sat" inside "satisfied"."""
    assert _named_weekdays("i am satisfied with mondays") == {0}


@pytest.mark.parametrize("text, label", [
    ("therapy every other tuesday at 5pm", "every other week"),
    ("standup fortnightly at 9am", "every other week"),
    ("gym twice a week at 6am", "more than once a period"),
    ("daven mincha every weekday at 1:30pm", "weekdays only"),
    ("standup every sunday and tuesday at 9am", "two days a week"),
])
def test_cadences_the_model_cannot_express_are_detected(text, label):
    assert _unsupported_cadence(text) == label


@pytest.mark.parametrize("text", [
    "gym every monday at 6am",
    "go pray mincha-maariv every day at 1900 until oct 6th",
    "pay rent every month on the 1st",
    "lunch with Tal every friday at noon",
    "dentist on thursday at 9am",
])
def test_expressible_cadences_are_not_flagged(text):
    """A false warning on a series it handled correctly is noise, and noise on
    every event is how a warning stops being read."""
    assert _unsupported_cadence(text) is None
