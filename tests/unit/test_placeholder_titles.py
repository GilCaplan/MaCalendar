"""An event called "meeting" cannot be read back.

The rule parser reaches for a contentless noun when it cannot find a better
one, so "set a meeting tomorrow at 2pm with Adin for the project" was filed as
"meeting". Across a week of flagged commands, 27 of 37 titles were a
placeholder and 22 were the bare word "meeting" — far and away the most common
complaint, and every one of them a correct time on an unreadable entry.

A background fixer existed and mostly worked; it just answered too late. The
reply said "Created event 'meeting'" and the better title arrived seconds
after the answer had been read and judged. It also matched keywords exactly,
so "event with yotem" — placeholder plus a preposition, the second most common
shape — slipped past it.
"""
from __future__ import annotations

import pytest

from assistant.engine.validate import is_placeholder_title as _is_placeholder_title


class _Cfg:
    class nlu:
        event_keywords = ["meeting", "appointment", "activity"]


@pytest.fixture
def cfg():
    return _Cfg()


@pytest.mark.parametrize("title", [
    "meeting",              # 22 of 37 flagged titles were exactly this
    "Meeting",
    "  meeting  ",
    "event",
    "appointment",
    "activity",
    "set meeting",
    "task",
    "",                     # no title at all is the same problem
])
def test_a_contentless_title_is_a_placeholder(cfg, title):
    assert _is_placeholder_title(title, cfg) is True


@pytest.mark.parametrize("title", [
    "event with yotem",     # the shape the exact-match check missed
    "event on the roof",
    "activity for the kids",
])
def test_an_empty_noun_disqualifies_the_title_it_leads(cfg, title):
    """"event with yotem" tells you as little as "event" does."""
    assert _is_placeholder_title(title, cfg) is True


@pytest.mark.parametrize("title", [
    "gym",
    "Threshold 9 km",
    "Visit with Tal",
    "pizza with ezra",
    "Dentist",
    "Walk Mark's dog",
    "Shacharit",
    "Meeting with Ravid at Kems",
    "meeting with adin",             # a meeting is a real kind of thing
    "meeting for the project",
    "appointment at the clinic",
])
def test_a_real_title_is_left_alone(cfg, title):
    """Naming these again risks replacing something good with something worse,
    and costs an LLM call for nothing."""
    assert _is_placeholder_title(title, cfg) is False


def test_configured_keywords_count_as_placeholders(cfg):
    """config.yaml's event_keywords are placeholders by definition — they are
    the words the fast path substitutes when it has no title."""
    cfg.nlu.event_keywords = ["huddle"]
    assert _is_placeholder_title("huddle", cfg) is True
