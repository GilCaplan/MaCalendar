"""The audit ran against an empty history, so personalisation was unmeasurable.

Every claim about the memory — whether the four retrieved examples help at
all, whether four is the right number, whether a corrected example beats a
recent one — has been an argument rather than a result, because the harness
pointed the history at a fresh temporary file on every run. There was nothing
to retrieve, so nothing to measure.

Two things are checked here. That the memory-aware mode exists and is wired
before the app is imported, since these paths are read at import time and a
flag parsed later would arrive far too late to matter. And that the real
history is still never written to — the mode copies it, which is the same rule
the vocabulary already follows.
"""
from __future__ import annotations

import os
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
AUDIT = ROOT / "scripts" / "audit_assistant.py"


@pytest.fixture(scope="module")
def source() -> str:
    return AUDIT.read_text()


def test_the_flag_is_read_before_the_app_is_imported(source):
    """argparse runs at the bottom of the file; these paths are read at the top.

    A flag handled by argparse would be parsed long after `assistant` had been
    imported and the store locations fixed, so it would silently do nothing.
    """
    peek = source.index('"--memory" in sys.argv')
    first_app_import = min(
        (source.index(m) for m in ("from assistant", "import assistant")
         if m in source), default=len(source))
    assert peek < first_app_import, (
        "the memory flag is read after the app is imported, which is too late "
        "for it to change where the history is read from")


def test_the_real_history_is_copied_and_never_used_directly(source):
    """The same rule the vocabulary follows: measure the real thing, change nothing."""
    block = source[source.index("_WANT_MEMORY"):source.index("os.chdir(ROOT)")]
    assert "copyfile" in block, "the real history must be copied, not opened"
    assert 'os.environ["MACALENDAR_MEMORY_DB"]' in block, (
        "the copy must be what the app is pointed at")
    assert "nlu_memory.db" in block


def test_a_missing_history_is_not_an_error(source):
    """A fresh machine has none, and the audit still has to run."""
    block = source[source.index("_WANT_MEMORY"):source.index("os.chdir(ROOT)")]
    assert "os.path.exists" in block


def test_both_flags_are_declared_so_help_describes_them(source):
    assert '"--memory"' in source and '"--memory-k"' in source


# ---------------------------------------------------------------------------
# The k override, which is what makes the comparison a one-liner
# ---------------------------------------------------------------------------

def test_the_parser_honours_the_k_override(monkeypatch, sample_config):
    """k=0 answers "is the memory helping at all", which is the question to
    settle before "is four the right number" means anything."""
    from assistant.intent.parser import IntentParser
    import assistant.actions.calendar  # noqa: F401
    from assistant.actions import registry

    parser = IntentParser(sample_config, registry)
    captured = {}

    class _Memory:
        def few_shot_block(self, transcript, k=4):
            captured["k"] = k
            return ""

    monkeypatch.setattr("assistant.intent.memory.get_memory", lambda: _Memory())

    # k=0 does not retrieve zero examples — it does not retrieve at all, and
    # returns an empty block. That is the "is the memory helping" arm.
    monkeypatch.setenv("MACALENDAR_MEMORY_K", "0")
    assert parser._few_shot_for("book gym tomorrow") == ""
    assert "k" not in captured, "k=0 should skip retrieval entirely, not ask for none"

    monkeypatch.setenv("MACALENDAR_MEMORY_K", "8")
    parser._few_shot_for("book gym tomorrow")
    assert captured.get("k") == 8, "the override did not reach the retrieval"


def test_a_nonsense_override_is_ignored_rather_than_crashing(monkeypatch, sample_config):
    from assistant.intent.parser import IntentParser
    import assistant.actions.calendar  # noqa: F401
    from assistant.actions import registry

    monkeypatch.setenv("MACALENDAR_MEMORY_K", "not a number")
    parser = IntentParser(sample_config, registry)
    parser._few_shot_for("book gym tomorrow")   # must not raise
