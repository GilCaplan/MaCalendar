"""The weekly review has to be trustworthy before anything is decided from it.

Two ways it lied. It reported "Accuracy on reviewed commands: 9%", which sent
me looking for a collapse that had not happened:

  • 24 of 32 rejections were registered inside two seconds — someone clearing a
    backlog, weighted identically to a considered verdict.
  • the ratio has approvals as its numerator, and a thumbs-up is work with no
    reward, so it goes unpressed while mistakes get flagged. With zero
    approvals the formula reads 0% however well the assistant did.
"""
from __future__ import annotations

import pytest

from scripts.weekly_review import BULK_MIN, BULK_WINDOW_S, _drop_bulk_runs


def _row(ts, feedback, path="rule"):
    return {"ts": ts, "feedback": feedback, "parse_path": path}


def test_a_burst_of_verdicts_is_not_a_review():
    """24 rejections in two seconds is clearing a queue, not judging it."""
    rows = [_row(1000.0 + i * 0.05, "rejected") for i in range(24)]
    considered, bulk = _drop_bulk_runs(rows)
    assert len(bulk) == 24
    assert considered == []


def test_verdicts_given_at_human_speed_are_kept():
    rows = [_row(1000.0 + i * 30, "rejected") for i in range(6)]
    considered, bulk = _drop_bulk_runs(rows)
    assert bulk == []
    assert len(considered) == 6


def test_a_short_run_is_not_a_burst():
    """Marking three in a row quickly is plausible; BULK_MIN guards against
    calling ordinary reviewing a bulk pass."""
    rows = [_row(1000.0 + i * 0.1, "rejected") for i in range(BULK_MIN - 1)]
    _, bulk = _drop_bulk_runs(rows)
    assert bulk == []


def test_unreviewed_rows_are_never_bulk():
    """"none" is the absence of a verdict, so it cannot be part of a burst —
    and it must survive into the considered set for the command counts."""
    rows = [_row(1000.0 + i * 0.01, "none") for i in range(30)]
    considered, bulk = _drop_bulk_runs(rows)
    assert bulk == []
    assert len(considered) == 30


def test_a_burst_is_dropped_without_taking_its_neighbours():
    """Real feedback either side of a bulk pass has to survive it."""
    rows = ([_row(500.0, "approved")]
            + [_row(1000.0 + i * 0.05, "rejected") for i in range(BULK_MIN + 2)]
            + [_row(9000.0, "corrected")])
    considered, bulk = _drop_bulk_runs(rows)
    assert len(bulk) == BULK_MIN + 2
    assert {r["feedback"] for r in considered} == {"approved", "corrected"}


def test_the_window_is_the_boundary():
    """Spread the same count just past the window and it is no longer a burst."""
    tight = [_row(1000.0 + i * (BULK_WINDOW_S / (BULK_MIN + 2)), "rejected")
             for i in range(BULK_MIN)]
    assert len(_drop_bulk_runs(tight)[1]) == BULK_MIN

    loose = [_row(1000.0 + i * (BULK_WINDOW_S + 1), "rejected") for i in range(BULK_MIN)]
    assert _drop_bulk_runs(loose)[1] == []
