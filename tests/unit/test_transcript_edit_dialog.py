"""The gate's dialog, driven the way a person drives it — real key events and
real button clicks, per this repo's hard-won rule that a UI test which never
sends a mouse event tests nothing.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import Qt, QTimer                                  # noqa: E402
from PyQt6.QtTest import QTest                                       # noqa: E402
from PyQt6.QtWidgets import (                                        # noqa: E402
    QApplication, QDialogButtonBox, QLineEdit,
)

from assistant.calendar_ui.window import ask_transcript_edit         # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _payload(text, words):
    return json.dumps({"transcript": text, "words": words})


def _drive(interact):
    """Schedule real interaction against the modal once it is up."""
    def _go():
        dlg = QApplication.activeModalWidget()
        if dlg is None:                      # not up yet — try again
            QTimer.singleShot(10, _go)
            return
        interact(dlg)
    QTimer.singleShot(0, _go)


def test_fixing_a_word_and_clicking_send(app):
    def interact(dlg):
        field = dlg.findChild(QLineEdit, "transcript_edit_field")
        field.selectAll()
        QTest.keyClicks(field, "call Noa tomorrow at nine")
        buttons = dlg.findChild(QDialogButtonBox, "transcript_edit_buttons")
        QTest.mouseClick(buttons.button(QDialogButtonBox.StandardButton.Ok),
                         Qt.MouseButton.LeftButton)

    _drive(interact)
    got = ask_transcript_edit(None, _payload("call noga tomorrow at nine", ["noga"]))
    assert got == "call Noa tomorrow at nine"


def test_sending_untouched_is_a_confirmation(app):
    def interact(dlg):
        buttons = dlg.findChild(QDialogButtonBox, "transcript_edit_buttons")
        QTest.mouseClick(buttons.button(QDialogButtonBox.StandardButton.Ok),
                         Qt.MouseButton.LeftButton)

    _drive(interact)
    got = ask_transcript_edit(None, _payload("meet Moxie at the park", ["Moxie"]))
    assert got == "meet Moxie at the park"


def test_cancel_returns_none(app):
    def interact(dlg):
        buttons = dlg.findChild(QDialogButtonBox, "transcript_edit_buttons")
        QTest.mouseClick(buttons.button(QDialogButtonBox.StandardButton.Cancel),
                         Qt.MouseButton.LeftButton)

    _drive(interact)
    got = ask_transcript_edit(None, _payload("call noga", ["noga"]))
    assert got is None
