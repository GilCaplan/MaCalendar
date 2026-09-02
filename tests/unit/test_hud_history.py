"""The thinking card keeps what it did, and stops shoving itself forward.

Two complaints, one cause: every command tore the card down and rebuilt it.
The timeline was wiped, so the only thing you could ever see was the command
running right now — glance away and the answer was gone, along with any chance
of noticing that something three commands back was wrong. And it re-showed,
re-parked and faded in over whatever you were working in, every single time,
"even if the last one was closed" as _start's docstring used to put it.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from assistant.thinking_hud import ThinkingHUD  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def hud(qapp):
    h = ThinkingHUD()
    yield h
    h.close()


def _command(hud, run: str, steps: int = 2) -> None:
    hud.apply_entry({"kind": "begin", "run": run, "source": "mac"})
    for i in range(steps):
        hud.panel.add_step({"stage": "rule", "title": f"Step {i}", "detail": "d",
                            "ms": 120, "at_ms": 0, "ok": True})
    hud.apply_entry({"kind": "result", "run": run, "result": {"message": f"done {run}"}})


# ---------------------------------------------------------------- history

def test_an_earlier_command_survives_the_next_one(hud):
    _command(hud, "r1", steps=3)
    _command(hud, "r2", steps=2)
    assert hud.panel._history, "the first command was wiped by the second"
    assert len(hud.panel._rows) == 2, "the current command should be the live rows"


def test_history_is_capped(hud):
    from assistant.calendar_ui.thinking_panel import MAX_HISTORY_WIDGETS
    for i in range(30):
        _command(hud, f"r{i}", steps=5)
    assert len(hud.panel._history) <= MAX_HISTORY_WIDGETS


def test_the_panel_does_not_grow_with_history(hud):
    """It is a fixed card with a scroll area — history must scroll, not stretch."""
    before = hud.panel.size()
    for i in range(10):
        _command(hud, f"r{i}", steps=6)
    assert hud.panel.size() == before


# ---------------------------------------------------------------- appearing

def test_the_first_command_opens_the_card(hud):
    assert not hud.isVisible()
    _command(hud, "r1")
    assert hud.isVisible()


def test_a_later_command_does_not_move_the_card(hud):
    """Updating in place: no re-park, so a card you dragged stays where it is."""
    _command(hud, "r1")
    where = hud.pos()
    _command(hud, "r2")
    assert hud.pos() == where


def test_closing_it_keeps_it_closed(hud):
    """Closing is an instruction, not a per-command dismissal. It used to
    suppress only the run on screen, so the next command popped it back up."""
    _command(hud, "r1")
    hud._on_panel_closed()
    assert not hud.isVisible()
    _command(hud, "r2")
    assert not hud.isVisible()


def test_a_command_run_while_hidden_is_still_recorded(hud):
    """So that opening it later shows what you missed."""
    _command(hud, "r1")
    hud._on_panel_closed()
    _command(hud, "r2", steps=4)
    assert len(hud.panel._rows) == 4


def test_reopening_restores_it_with_its_history(hud):
    _command(hud, "r1")
    hud._on_panel_closed()
    _command(hud, "r2")
    hud.reopen()
    assert hud.isVisible()
    assert hud.panel._history


def test_without_a_menu_bar_item_hiding_cannot_be_permanent(hud):
    """Sticky hiding is only safe while something can un-hide it. If the tray
    fails to start there is no Dock icon and no menu, so it must revert."""
    hud.allow_reappear_without_tray()
    _command(hud, "r1")
    hud._on_panel_closed()
    assert not hud.isVisible()
    _command(hud, "r2")
    assert hud.isVisible(), "with no way to reopen, it has to come back on its own"
