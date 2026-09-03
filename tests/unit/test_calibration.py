"""The routing threshold has to be answerable, not just arguable.

Everything scoring 0.85 or more is answered without consulting the model. That
number was picked by hand and never checked, because the score was computed,
used for the decision, and discarded — you cannot bucket outcomes by a number
you never wrote down.

The column that fixes that is only worth adding if something reads it, so this
tests the readout as much as the storage. The behaviour that matters most is
the refusal: with a handful of commands the honest output is "not enough yet",
because a calibration curve drawn from a dozen samples is worse than no curve
at all — it looks like evidence.
"""
from __future__ import annotations

import subprocess
import sys

import pytest

from assistant.intent.memory import CommandMemory


@pytest.fixture
def memory(tmp_path):
    return CommandMemory(str(tmp_path / "m.db"))


def _rows(db):
    import sqlite3
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    return [dict(r) for r in c.execute("SELECT * FROM examples ORDER BY id")]


# ---------------------------------------------------------------------------
# Storing it
# ---------------------------------------------------------------------------

def test_the_score_is_kept(memory, tmp_path):
    memory.record(transcript="book gym tomorrow", parse_path="rule", confidence=0.93)
    assert _rows(str(tmp_path / "m.db"))[0]["confidence"] == pytest.approx(0.93)


def test_a_command_the_rules_never_scored_is_marked_as_such(memory, tmp_path):
    """-1 rather than 0: never scored is a different thing from scored zero,
    and averaging the two together would drag every bucket down."""
    memory.record(transcript="something long and strange", parse_path="llm")
    assert _rows(str(tmp_path / "m.db"))[0]["confidence"] == -1


def test_an_older_database_gains_the_column_without_losing_rows(tmp_path):
    """Every existing machine has this table already, filled with real history."""
    import sqlite3
    path = str(tmp_path / "old.db")
    c = sqlite3.connect(path)
    c.executescript("""
        CREATE TABLE examples (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL,
            source TEXT NOT NULL DEFAULT 'mac', raw_transcript TEXT NOT NULL DEFAULT '',
            transcript TEXT NOT NULL, parse_path TEXT NOT NULL DEFAULT '',
            actions_json TEXT NOT NULL DEFAULT '[]', result TEXT NOT NULL DEFAULT '',
            success INTEGER NOT NULL DEFAULT 1, feedback TEXT NOT NULL DEFAULT 'none',
            correction_json TEXT, notes TEXT NOT NULL DEFAULT '',
            llm_ms INTEGER NOT NULL DEFAULT 0, total_ms INTEGER NOT NULL DEFAULT 0);
    """)
    c.execute("INSERT INTO examples (ts, transcript) VALUES (1.0, 'an old command')")
    c.commit(); c.close()

    CommandMemory(path)                      # opening it runs the migration
    rows = _rows(path)
    assert len(rows) == 1, "migration lost a row"
    assert rows[0]["transcript"] == "an old command"
    assert rows[0]["confidence"] == -1, "existing rows must read as never-scored"


# ---------------------------------------------------------------------------
# Reading it back — the part that makes the column worth having
# ---------------------------------------------------------------------------

def _run(db: str) -> str:
    out = subprocess.run([sys.executable, "-m", "scripts.calibration", "--db", db],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_with_almost_no_data_it_refuses_rather_than_guesses(memory, tmp_path):
    """The important behaviour. Two commands must not produce a percentage."""
    for score in (0.90, 0.60):
        memory.record(transcript="x", parse_path="rule", confidence=score)
    report = _run(str(tmp_path / "m.db"))
    assert "%" not in report.split("A verdict here")[0] or "too few" in report


def test_it_reports_by_score_once_there_is_enough(memory, tmp_path):
    """Seeded so the confident side is visibly worse than the threshold claims —
    which is exactly the finding the threshold question exists to surface."""
    db = str(tmp_path / "m.db")
    for i in range(6):                        # confident, but wrong half the time
        eid = memory.record(transcript=f"confident {i}", parse_path="rule", confidence=0.95)
        memory.set_feedback(eid, "approved" if i % 2 == 0 else "rejected")
    for i in range(4):                        # unsure, and mostly right
        eid = memory.record(transcript=f"unsure {i}", parse_path="llm", confidence=0.55)
        memory.set_feedback(eid, "approved" if i < 3 else "rejected")

    report = _run(db)
    assert "0.95" in report and "0.55" in report, "scores are not bucketed"
    assert "50%" in report, "the confident side's real accuracy is not reported"
    assert "raising the threshold" in report, (
        "a confident side that is wrong half the time should say so plainly")


def test_unjudged_commands_are_excluded(memory, tmp_path):
    """success=1 only means nothing threw; it is not a verdict about meaning."""
    db = str(tmp_path / "m.db")
    for i in range(20):
        memory.record(transcript=f"never judged {i}", parse_path="rule", confidence=0.95)
    report = _run(db)
    assert "0 of those also carry a confidence" in report or "Nothing to calibrate" in report


def test_test_traffic_is_excluded(memory, tmp_path):
    """Scripted commands would otherwise swamp a week of real use."""
    db = str(tmp_path / "m.db")
    for i in range(30):
        eid = memory.record(transcript=f"scripted {i}", source="test",
                            parse_path="rule", confidence=0.95)
        memory.set_feedback(eid, "approved")
    report = _run(db)
    assert "0 real commands" in report or "Nothing to calibrate" in report
