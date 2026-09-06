"""The settings dialog's observance checkbox, driven with real clicks.

Per this repo's hard-won rule, a UI test that never sends a mouse event tests
nothing — so the checkbox is toggled with QTest.mouseClick on the widget and
the save happens by clicking the actual "Save Config" button, using the same
QTimer-drives-the-modal pattern as test_transcript_edit_dialog.py.

What must hold: unchecking "Skip Shabbat && yom tov in series (observance)"
and saving writes `enabled: false` into config.yaml's `observance:` section
through assistant/config_store — which means the file's comments (including
the inline one on the rewritten line) survive, and neighbouring keys are left
alone.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import QPoint, Qt, QTimer                          # noqa: E402
from PyQt6.QtTest import QTest                                       # noqa: E402
from PyQt6.QtWidgets import (                                        # noqa: E402
    QApplication, QCheckBox, QPushButton, QWidget,
)

from assistant import config_store                                   # noqa: E402
from assistant.calendar_ui.settings_dialog import open_settings      # noqa: E402
from assistant.config import (                                       # noqa: E402
    AudioConfig, HebrewCalendarConfig, NLUConfig, UIConfig,
)

SAMPLE = """\
# hand-written config — comments must survive a save
theme: "dark"   # startup theme

observance:
  # where sundown is computed for
  latitude: 31.7683
  enabled: true   # skip Shabbat & yom tov in series
"""


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


# ── the least window that open_settings(self) needs ──────────────────


class _Tts:
    mute, voice, rate = False, "Samantha", 200


class _Confirmer:
    level = 0


class _Pipeline:
    def __init__(self):
        self._tts = _Tts()
        self._confirmer = _Confirmer()


class _Observance:
    enabled = True


class _Config:
    def __init__(self):
        self.theme = "dark"
        self.ui = UIConfig()
        self.audio = AudioConfig()
        self.nlu = NLUConfig()
        self.hebrew_calendar = HebrewCalendarConfig()
        self.observance = _Observance()


class _Btn:
    def setVisible(self, _visible):
        pass


class _Window(QWidget):
    def __init__(self):
        super().__init__()
        self._pipeline = _Pipeline()
        self._config = _Config()
        self._dark = True
        self._view_mode = "month"
        self._view_btn_coursework = _Btn()
        self._view_btn_workout = _Btn()
        self._view_btn_timer = _Btn()

    def show_toast(self, *_):
        pass

    def refresh_calendar(self):
        pass

    def _apply_ui_config(self):
        pass

    def _apply_theme(self, _dark):
        pass

    def _set_view(self, _mode):
        pass


def _drive(interact, failures):
    """Run real interaction against the modal once it is up.

    A failure inside the Qt callback would otherwise leave the dialog's
    exec() spinning forever — so it is recorded and the dialog closed, and
    the test re-raises it afterwards.
    """
    def _go():
        dlg = QApplication.activeModalWidget()
        if dlg is None:                      # not up yet — try again
            QTimer.singleShot(10, _go)
            return
        try:
            interact(dlg)
        except Exception as e:               # noqa: BLE001 — re-raised below
            failures.append(e)
            dlg.reject()
    QTimer.singleShot(0, _go)


def _click(widget):
    """Left-click over the widget's leading edge (a checkbox's indicator)."""
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier,
                     QPoint(8, widget.height() // 2))


# ── the tests ────────────────────────────────────────────────────────


def test_unchecking_and_saving_writes_enabled_false(app, tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(SAMPLE)
    # The dialog saves through config_store.set_values with its default path
    # (the repo's real config.yaml); aim the same comment-preserving writer
    # at the scratch file instead.
    real = config_store.set_values
    monkeypatch.setattr(config_store, "set_values",
                        lambda updates, path=str(cfg): real(updates, path))

    window = _Window()
    failures: list = []
    seen: dict = {}

    def interact(dlg):
        cb = dlg.findChild(QCheckBox, "observance_enabled_cb")
        assert cb is not None, "observance checkbox missing from the dialog"
        seen["initially"] = cb.isChecked()
        _click(cb)
        seen["after_click"] = cb.isChecked()
        save = next(b for b in dlg.findChildren(QPushButton)
                    if b.text() == "Save Config")
        QTest.mouseClick(save, Qt.MouseButton.LeftButton)

    _drive(interact, failures)
    open_settings(window)
    if failures:
        raise failures[0]

    assert seen["initially"] is True          # reflects observance.enabled
    assert seen["after_click"] is False       # the click really toggled it

    out = cfg.read_text()
    section = out.split("observance:")[1]
    assert "enabled: false" in section
    assert "latitude: 31.7683" in section     # neighbouring key untouched
    # Comments survive — the whole point of config_store — including the
    # inline one on the very line that was rewritten.
    assert "# hand-written config — comments must survive a save" in out
    assert "# where sundown is computed for" in out
    assert "enabled: false   # skip Shabbat & yom tov in series" in out


def test_checkbox_reflects_a_disabled_config(app):
    window = _Window()
    window._config.observance = type("O", (), {"enabled": False})()
    failures: list = []
    seen: dict = {}

    def interact(dlg):
        cb = dlg.findChild(QCheckBox, "observance_enabled_cb")
        assert cb is not None, "observance checkbox missing from the dialog"
        seen["initially"] = cb.isChecked()
        dlg.reject()                          # look, don't save

    _drive(interact, failures)
    open_settings(window)
    if failures:
        raise failures[0]

    assert seen["initially"] is False
