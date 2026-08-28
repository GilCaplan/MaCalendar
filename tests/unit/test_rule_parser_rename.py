"""Renaming an event by voice.

"rename the meeting with Tal to robotics sync" answered "No changes specified"
— the new name was pulled from the dependency parse, which "with Tal" derailed
and which lost the second word of a two-word name. When the sentence says
"rename X to Y" outright it is now read literally.
"""
from __future__ import annotations

import pytest

from assistant.intent.rule_parser import RuleBasedParser


@pytest.fixture(scope="module")
def parser():
    import assistant.actions.calendar  # noqa: F401
    import assistant.actions.todo      # noqa: F401
    from assistant.actions import registry
    return RuleBasedParser(registry)


def slots(parser, transcript: str) -> dict:
    return parser.analyze(transcript, current_view="month").raw_slots.get("update_event", {})


@pytest.mark.parametrize("said, matches, new_title", [
    ("rename the meeting with Tal to robotics sync",   "tal",      "robotics sync"),
    ("rename the meeting with Tal as robotics sync",   "tal",      "robotics sync"),
    ("rename gym to workout",                          "gym",      "workout"),
    ("rename the meeting to robotics sync",            "meeting",  "robotics sync"),
    ("rename my dentist appointment to dentist checkup", "dentist", "dentist checkup"),
])
def test_rename_gives_both_the_old_and_the_new_name(parser, said, matches, new_title):
    got = slots(parser, said)
    assert got.get("new_title", "").lower() == new_title
    assert matches in got.get("match_title", "").lower()


def test_a_time_after_to_is_a_reschedule_not_a_rename(parser):
    got = slots(parser, "rename the meeting to 3pm")
    assert got.get("new_start_time") == "15:00"
    assert not got.get("new_title")
