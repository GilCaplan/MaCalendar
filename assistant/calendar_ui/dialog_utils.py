"""Shared dialog keyboard-confirmation helper.

QDialogButtonBox's "default button" (the one Enter triggers) is supposed to
be pinned by calling button.setDefault(True) — but that state gets silently
reset by Qt whenever the app's global QSS stylesheet is (re)applied (e.g. on
theme/accent changes), because QSS changes trigger a style-polish pass that
recomputes QDialogButtonBox's own idea of the default button, overriding
whatever was set explicitly before. Confirmed by direct reproduction: with
the app stylesheet applied, Save.isDefault() reports True right after
setDefault(True), but pressing Return still calls reject() — Cancel had
silently become the real default. Bypass the flaky mechanism entirely by
handling Return explicitly at the dialog level.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QPushButton, QTextEdit


def install_enter_confirms(dialog: QDialog, confirm_button: QPushButton) -> None:
    """Make Return/Enter reliably click *confirm_button*, regardless of
    QDialogButtonBox's own (unreliable) default-button state. Multi-line
    QTextEdit fields keep Return as a literal newline, matching normal
    text-editing expectations. Escape is left untouched — QDialog's built-in
    Key_Escape → reject() handling doesn't depend on default-button state,
    so it isn't affected by this bug.
    """
    original_key_press = dialog.keyPressEvent

    def keyPressEvent(event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            focus_widget = dialog.focusWidget()
            if not isinstance(focus_widget, QTextEdit):
                if confirm_button.isEnabled():
                    confirm_button.click()
                event.accept()
                return
        original_key_press(event)

    dialog.keyPressEvent = keyPressEvent
