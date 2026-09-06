"""The settings dialog's Notifications section, driven with real input events.

Per this repo's hard-won rule, a UI test that never sends a mouse event tests
nothing — checkboxes are toggled with QTest.mouseClick, the combo boxes are
changed with QTest.keyClicks (a closed QComboBox's incremental search: typing
"3" selects "30 minutes", "M" selects "Muted" — verified real key events),
and the save happens by clicking the actual "Save Config" button, using the
same QTimer-drives-the-modal pattern as test_settings_observance.py.

What must hold:

* the widgets reflect self._config.notifications on open — including a
  per-category row whose combo shows the category's lead from
  category_leads, and "Default" for a category absent from that map;
* unchecking "Pre-event notifications", picking a 30-minute default lead and
  muting one category, then saving, writes `enabled: false`,
  `default_lead_minutes: 30` and `category_leads: {Work: 0}` into the
  `notifications:` section (0 = category MUTED — Gil's rule; "Default" rows
  never land in the map) — with the file's comments preserved, including the
  inline one on a rewritten line, and neighbouring sections left alone.

The scalar keys go through assistant/config_store.set_values; category_leads
is a mapping, which config_store._literal cannot render, so it goes through
settings_dialog._persist_category_leads — the same section-scoped,
comment-preserving surgery, collapsing the sample's block-style mapping into
a one-line flow mapping.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

import yaml                                                          # noqa: E402
from PyQt6.QtCore import QPoint, Qt, QTimer                          # noqa: E402
from PyQt6.QtTest import QTest                                       # noqa: E402
from PyQt6.QtWidgets import (                                        # noqa: E402
    QApplication, QCheckBox, QComboBox, QPushButton, QWidget,
)

from assistant import config_store                                   # noqa: E402
from assistant.calendar_ui.settings_dialog import open_settings      # noqa: E402
from assistant.config import (                                       # noqa: E402
    AudioConfig, HebrewCalendarConfig, NLUConfig, NotificationsConfig, UIConfig,
)

# Block-style category_leads on purpose — the harder shape the persistence
# helper must collapse into a flow mapping without touching the comments.
SAMPLE = """\
# hand-written config — comments must survive a save
theme: "dark"   # startup theme

notifications:
  # pre-event reminders
  enabled: true   # master switch
  default_lead_minutes: 10
  category_leads:
    Work: 15
  respect_observance: true
  speak: false
  sound: true
  catch_up_minutes: 10

observance:
  # where sundown is computed for
  latitude: 31.7683
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
        # Mirrors SAMPLE — the dialog reads this object; the save writes the
        # yaml file, and the two must agree for the test to mean anything.
        self.notifications = NotificationsConfig(
            enabled=True, default_lead_minutes=10, category_leads={"Work": 15},
            respect_observance=True, speak=False, sound=True)


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


def _combo(dlg, name: str) -> QComboBox:
    combo = dlg.findChild(QComboBox, name)
    assert combo is not None, f"combo {name!r} missing from the dialog"
    return combo


# ── the tests ────────────────────────────────────────────────────────


def test_widgets_reflect_the_notifications_config(app):
    window = _Window()
    failures: list = []
    seen: dict = {}

    def interact(dlg):
        for cb_name in ("notif_enabled_cb", "notif_speak_cb", "notif_observance_cb"):
            cb = dlg.findChild(QCheckBox, cb_name)
            assert cb is not None, f"checkbox {cb_name!r} missing from the dialog"
            seen[cb_name] = cb.isChecked()
        lead = _combo(dlg, "notif_default_lead_combo")
        seen["lead"] = (lead.currentText(), lead.currentData())
        work = _combo(dlg, "notif_cat_lead_Work")
        seen["work"] = (work.currentText(), work.currentData())
        # A category with no entry in category_leads shows Default.
        study = _combo(dlg, "notif_cat_lead_Study")
        seen["study"] = (study.currentText(), study.currentData())
        dlg.reject()                          # look, don't save

    _drive(interact, failures)
    open_settings(window)
    if failures:
        raise failures[0]

    assert seen["notif_enabled_cb"] is True
    assert seen["notif_speak_cb"] is False
    assert seen["notif_observance_cb"] is True
    assert seen["lead"] == ("10 minutes", 10)
    assert seen["work"] == ("15 minutes", 15)
    assert seen["study"] == ("Default", None)


def test_interacting_and_saving_writes_the_notifications_section(app, tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(SAMPLE)
    # The dialog saves through config_store.set_values with its default path
    # (the repo's real config.yaml); aim the same comment-preserving writer
    # at the scratch file instead. _persist_category_leads reads
    # config_store.CONFIG_PATH at call time, so patching the module
    # attribute redirects it too.
    real = config_store.set_values
    monkeypatch.setattr(config_store, "set_values",
                        lambda updates, path=str(cfg): real(updates, path))
    monkeypatch.setattr(config_store, "CONFIG_PATH", str(cfg))

    window = _Window()
    failures: list = []
    seen: dict = {}

    def interact(dlg):
        cb = dlg.findChild(QCheckBox, "notif_enabled_cb")
        assert cb is not None, "notifications checkbox missing from the dialog"
        _click(cb)                            # on → off
        seen["enabled_after_click"] = cb.isChecked()
        lead = _combo(dlg, "notif_default_lead_combo")
        QTest.keyClicks(lead, "3")            # incremental search → "30 minutes"
        seen["lead_after_keys"] = lead.currentData()
        work = _combo(dlg, "notif_cat_lead_Work")
        QTest.keyClicks(work, "M")            # → "Muted" (0)
        seen["work_after_keys"] = (work.currentText(), work.currentData())
        save = next(b for b in dlg.findChildren(QPushButton)
                    if b.text() == "Save Config")
        QTest.mouseClick(save, Qt.MouseButton.LeftButton)

    _drive(interact, failures)
    open_settings(window)
    if failures:
        raise failures[0]

    assert seen["enabled_after_click"] is False    # the click really toggled it
    assert seen["lead_after_keys"] == 30           # the keys really selected it
    assert seen["work_after_keys"] == ("Muted", 0)

    out = cfg.read_text()
    data = yaml.safe_load(out)
    notif = data["notifications"]
    assert notif["enabled"] is False
    assert notif["default_lead_minutes"] == 30
    # Muted Work = 0 in the map, and it is a *mapping* again — not the quoted
    # repr string config_store._literal would have produced for a dict.
    assert notif["category_leads"] == {"Work": 0}
    assert notif["catch_up_minutes"] == 10         # untouched key survives
    assert data["observance"]["latitude"] == 31.7683   # neighbouring section

    # Comments survive — the whole point of config_store and of the helper —
    # including the inline one on a rewritten line.
    assert "# hand-written config — comments must survive a save" in out
    assert "# pre-event reminders" in out
    assert "# where sundown is computed for" in out
    assert "enabled: false   # master switch" in out
    # The block-style mapping was collapsed into one flow line.
    assert "category_leads: {Work: 0}" in out
    assert "    Work: 15" not in out
