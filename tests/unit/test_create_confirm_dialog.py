"""The confirm-create box, driven the way a person drives it.

Real button clicks, per this repo's hard-won rule that a UI test which never
sends a mouse event tests nothing — three HUD bugs shipped green because the
tests called handlers instead of clicking controls.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import Qt, QTimer                                  # noqa: E402
from PyQt6.QtTest import QTest                                       # noqa: E402
from PyQt6.QtWidgets import (                                        # noqa: E402
    QApplication, QDialogButtonBox, QLabel,
)

from assistant.calendar_ui.window import ask_create_confirm          # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _payload(prompt, items):
    return json.dumps({"prompt": prompt, "items": items})


def _drive(interact):
    """Schedule real interaction against the modal once it is up."""
    def _go():
        dlg = QApplication.activeModalWidget()
        if dlg is None:                      # not up yet — try again
            QTimer.singleShot(10, _go)
            return
        interact(dlg)
    QTimer.singleShot(0, _go)


def _click(dlg, standard_button):
    buttons = dlg.findChild(QDialogButtonBox, "create_confirm_buttons")
    QTest.mouseClick(buttons.button(standard_button), Qt.MouseButton.LeftButton)


def test_clicking_add_accepts(app):
    _drive(lambda dlg: _click(dlg, QDialogButtonBox.StandardButton.Ok))
    assert ask_create_confirm(
        None, _payload("Want me to add “Yoga” on Tuesday 7 AM–8 AM?",
                       ["“Yoga” on Tuesday, Sep 8, 2026 7 AM–8 AM"])) is True


def test_clicking_no_declines(app):
    _drive(lambda dlg: _click(dlg, QDialogButtonBox.StandardButton.Cancel))
    assert ask_create_confirm(
        None, _payload("Want me to add “Yoga”?", ["“Yoga”"])) is False


def test_the_box_shows_the_human_line_and_what_it_would_create(app):
    seen: dict = {}

    def interact(dlg):
        seen["prompt"] = dlg.findChild(QLabel, "create_confirm_prompt").text()
        seen["items"] = dlg.findChild(QLabel, "create_confirm_items").text()
        seen["add"] = dlg.findChild(
            QDialogButtonBox, "create_confirm_buttons").button(
                QDialogButtonBox.StandardButton.Ok).text()
        _click(dlg, QDialogButtonBox.StandardButton.Cancel)

    _drive(interact)
    ask_create_confirm(None, _payload("Want me to add “Town hall” on the 3rd?",
                                      ["“Town hall” on Thursday, Oct 3, 2026"]))

    assert seen["prompt"] == "Want me to add “Town hall” on the 3rd?"
    assert "Town hall" in seen["items"]
    assert seen["add"] == "Add"


def test_a_junk_payload_still_asks_rather_than_creating(app):
    """A malformed payload must not become an accept — declining is the safe
    default, which is the whole point of the gate."""
    _drive(lambda dlg: _click(dlg, QDialogButtonBox.StandardButton.Cancel))
    assert ask_create_confirm(None, "not json at all") is False
