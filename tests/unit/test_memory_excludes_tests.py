"""What the parser is allowed to learn from.

Retrieved examples are injected into the LLM prompt as evidence of how *this
user* speaks — "USER HISTORY — how this user's past commands were (correctly)
interpreted. Match their phrasing, names and habits." A command typed by a
developer with curl is not that, and ten of mine were sitting in there eligible
to teach the parser.

Rejected commands were already excluded. Synthetic ones are excluded now for
the same reason: both are examples of what the assistant should not do.
"""
from __future__ import annotations

import pytest

from assistant.intent.memory import CommandMemory


@pytest.fixture
def memory(tmp_path, monkeypatch):
    monkeypatch.setenv("MACALENDAR_MEMORY_DB", str(tmp_path / "m.db"))
    import assistant.intent.memory as mod
    monkeypatch.setattr(mod, "MEMORY_PATH", str(tmp_path / "m.db"), raising=False)
    return CommandMemory(str(tmp_path / "m.db"))


def _record(memory, transcript, source, actions=None):
    return memory.record(
        transcript=transcript, raw_transcript=transcript, source=source,
        parse_path="rule", result="ok", success=True,
        actions=actions or [("create_event", {"title": "x"})],
    )


def test_a_test_command_is_never_offered_as_an_example(memory):
    _record(memory, "book gym tomorrow at seven", source="test")
    got = memory.retrieve("book gym tomorrow at eight")
    assert got == [], "a synthetic command was offered as user history"


def test_real_commands_are_still_offered(memory):
    _record(memory, "book gym tomorrow at seven", source="mac")
    assert memory.retrieve("book gym tomorrow at eight"), \
        "a real command should be available as an example"


def test_the_phone_counts_as_real(memory):
    _record(memory, "book gym tomorrow at seven", source="ios")
    assert memory.retrieve("book gym tomorrow at eight")


def test_a_missing_source_is_not_treated_as_a_test(memory):
    """Older rows predate the column being set and are the user's own."""
    _record(memory, "book gym tomorrow at seven", source="")
    assert memory.retrieve("book gym tomorrow at eight")


def test_tests_and_rejections_are_excluded_for_the_same_reason(memory):
    """Both are examples of what not to do; neither may reach the prompt."""
    from assistant.intent.memory import FEEDBACK_REJECTED
    good = _record(memory, "book gym tomorrow at seven", source="mac")
    bad = _record(memory, "book gym tomorrow at seven thirty", source="mac")
    memory.set_feedback(bad, FEEDBACK_REJECTED)
    _record(memory, "book gym tomorrow at eight fifteen", source="test")

    ids = {e["id"] for e in memory.retrieve("book gym tomorrow at eight")}
    assert ids == {good}
