"""The settings dialog against the shapes Gil's Mac actually has.

The dialog crashed the live app on open — not with a traceback in a log, but
with SIGABRT: PyQt6 turns an unhandled exception inside a slot into qFatal(),
so an AttributeError raised while building the dialog takes the whole calendar
process (and, via the launcher, the API and the HUD) down with it.

    AttributeError: 'Pipeline' object has no attribute '_confirmer'

`Pipeline._confirmer` was deleted in e3ea4f6 ("Delete the Mac's dead half"),
when parsing and execution moved into the API process — but the dialog kept
reading it, and BOTH settings suites' `_Pipeline` doubles had invented one, so
the suites stayed green while the real app aborted. That is the whole lesson of
this file: **the doubles here are deliberately no more capable than the real
objects.** `_StrictPipeline` raises AttributeError for anything the real
Pipeline does not have, so the next attribute the dialog invents fails here
rather than on Gil's screen.

The rest is the same class of failure, from the other real store:

* his config.yaml predates the notifications and observance work, so it has
  NO `notifications:`, `observance:` or `engine:` section — the dialog must
  open against the pydantic defaults and the save must CREATE those sections;
* ~/.assistant_tools/categories.json is hand-editable and merged over the
  defaults, so a row can carry a null colour, a colour Qt cannot parse, a
  non-ascii name, or a duplicate of another row's name. A bad row must degrade
  to the default dot / Default lead, never abort the dialog.
"""
from __future__ import annotations

import json
import queue

import pytest

pytest.importorskip("PyQt6")

import yaml                                                          # noqa: E402
from PyQt6.QtCore import QPoint, Qt, QTimer                          # noqa: E402
from PyQt6.QtTest import QTest                                       # noqa: E402
from PyQt6.QtWidgets import (                                        # noqa: E402
    QApplication, QCheckBox, QComboBox, QPushButton, QWidget,
)

from assistant import config_store                                   # noqa: E402
from assistant.actions.calendar import categories as categories_mod  # noqa: E402
from assistant.calendar_ui.settings_dialog import open_settings      # noqa: E402
from assistant.config import load_config                             # noqa: E402
from assistant.tts.speaker import Speaker                            # noqa: E402

# A faithful trim of the live config.yaml: the sections it HAS, and none of the
# three it does not. Anything the dialog reads out of notifications/observance/
# engine therefore comes from the pydantic defaults, and saving has to create
# those sections rather than assume them.
REAL_SHAPED_CONFIG = """\
hotkey:
  modifiers: [ctrl]
  key: "j"

stt_engine: "mlx"

ollama:
  model: "llama3.1:8b"

confirmation_level: 0
verify_fast_path: true
self_check_apply: false

audio:
  review_before_send: true
  review_seconds: 3

tts:
  mute: false
  voice: "Samantha"
  rate: 200

nlu:
  event_keywords: [meeting, appointment, activity]

theme: "dark"  # "light" | "dark" - default theme on startup

ui:
  font_month: 19
  accent_color: "#f5a524"
  show_timer: true
  show_workout: false
  show_coursework: false
  thinking_auto_open: true  # a key pydantic does not declare — must be ignored

hebrew_calendar:
  display_mode: "both"
  show_holidays: true
  israel_holidays: true
"""

# Hand-edited categories.json, merged over the built-in defaults by
# categories._load(). Every entry here is a shape the dot-drawing or the
# per-category combo used to be assumed away.
ODD_CATEGORIES = {
    "categories": [
        # Overrides a BUILT-IN category's colour with null. QColor(None) raises
        # TypeError — this is the entry that would abort the dialog.
        {"name": "Work", "color": None},
        # A colour Qt cannot parse: QColor() is constructed but invalid, so the
        # brush would be drawn with an undefined colour.
        {"name": "Bad Colour", "color": "not-a-colour"},
        # Non-ascii, spaces and an emoji in a name used verbatim as a widget
        # objectName and as a YAML mapping key on save.
        {"name": "Café Meetings ☕", "color": "#ff8800"},
        # No colour key at all.
        {"name": "No Colour Key"},
        # Blank name — categories._load() drops it; asserted so a change there
        # does not quietly start producing a nameless row.
        {"name": "   ", "color": "#123456"},
        # The same new name twice: categories._load() snapshots its index
        # before the merge loop, so BOTH are appended and all_categories()
        # really does return two rows called "Duplicated".
        {"name": "Duplicated", "color": "#111111"},
        {"name": "Duplicated", "color": "#222222"},
    ]
    # …plus MANY more, appended below.
    + [{"name": f"Custom {i}", "color": "#3366aa"} for i in range(30)],
    "removed": [],
}


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def real_config(tmp_path):
    """A real AppConfig parsed from a real-shaped config.yaml (scratch copy)."""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(REAL_SHAPED_CONFIG)
    cfg = load_config(str(cfg_file))
    # The premise of every test below.
    raw = yaml.safe_load(REAL_SHAPED_CONFIG)
    assert "notifications" not in raw
    assert "observance" not in raw
    assert "engine" not in raw
    return cfg, cfg_file


@pytest.fixture
def odd_categories(tmp_path, monkeypatch):
    """Point the category store at the hand-edited file and clear its cache.

    CATEGORIES_PATH is a module constant read at import time (see
    tests/conftest.py), so the env var is too late here — the attribute is
    patched instead, and the mtime cache reset either side.
    """
    path = tmp_path / "categories.json"
    path.write_text(json.dumps(ODD_CATEGORIES, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(categories_mod, "CATEGORIES_PATH", str(path))
    monkeypatch.setattr(categories_mod, "_cache", None)
    monkeypatch.setattr(categories_mod, "_mtime", -1.0)
    yield path
    categories_mod._cache, categories_mod._mtime = None, -1.0


# ── doubles that are no more capable than the real objects ───────────


class _StrictPipeline:
    """assistant.pipeline.Pipeline's surface, and nothing the real one lacks.

    `_tts` is the REAL Speaker. Everything the window merely wires up is a
    no-op callable — but any *attribute* the dialog reaches for that the real
    Pipeline does not define raises, exactly as it does on Gil's Mac.
    """

    #: what the real Pipeline has and the dialog is allowed to touch
    _REAL_ATTRS = {"_tts", "status_queue", "config", "registry", "trigger",
                   "health_check", "speak"}

    def __init__(self, cfg):
        self._tts = Speaker(cfg.tts)
        self.status_queue: queue.Queue = queue.Queue()

    def __getattr__(self, name):
        if name in self._REAL_ATTRS:
            return lambda *a, **k: None
        raise AttributeError(f"'Pipeline' object has no attribute {name!r}")


class _Btn:
    def __init__(self):
        self.visible = True

    def setVisible(self, visible):
        self.visible = visible


class _Window(QWidget):
    def __init__(self, cfg):
        super().__init__()
        self._pipeline = _StrictPipeline(cfg)
        self._config = cfg
        self._dark = cfg.theme == "dark"
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
    """Run interaction against the modal once it is up (see the sibling suites)."""
    def _go():
        dlg = QApplication.activeModalWidget()
        if dlg is None:
            QTimer.singleShot(10, _go)
            return
        try:
            interact(dlg)
        except Exception as e:                # noqa: BLE001 — re-raised below
            failures.append(e)
            dlg.reject()
    QTimer.singleShot(0, _go)


def _click(widget):
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier,
                     QPoint(8, widget.height() // 2))


# ── the tests ────────────────────────────────────────────────────────


def test_the_odd_category_file_really_is_odd(odd_categories):
    """The fixture only means something if the loader passes the mess through."""
    cats = categories_mod.all_categories()
    by_name: dict[str, list] = {}
    for c in cats:
        by_name.setdefault(c["name"], []).append(c)
    assert by_name["Work"][0]["color"] is None          # the aborting entry
    assert by_name["Bad Colour"][0]["color"] == "not-a-colour"
    assert "Café Meetings ☕" in by_name
    assert len(by_name["Duplicated"]) == 2              # a genuine duplicate
    assert "   " not in by_name and "" not in by_name   # blank name dropped
    assert len(cats) > 40                               # MANY categories


def test_dialog_opens_with_the_real_pipeline_and_a_sectionless_config(
        app, real_config, odd_categories):
    """The crash, as a test: no `_confirmer`, no notifications/observance
    sections, and a category file full of bad rows — the dialog still opens."""
    cfg, _ = real_config
    window = _Window(cfg)
    failures: list = []
    seen: dict = {}

    def interact(dlg):
        auto = next(cb for cb in dlg.findChildren(QCheckBox)
                    if cb.text().startswith("Auto-approve"))
        # Sourced from config.confirmation_level (0), NOT from the pipeline.
        seen["auto"] = auto.isChecked()
        # Defaults stood in for the three absent sections.
        seen["observance"] = dlg.findChild(QCheckBox, "observance_enabled_cb").isChecked()
        seen["notif"] = dlg.findChild(QCheckBox, "notif_enabled_cb").isChecked()
        lead = dlg.findChild(QComboBox, "notif_default_lead_combo")
        seen["lead"] = (lead.currentText(), lead.currentData())
        # Every odd row still rendered, at Default.
        for name in ("Work", "Bad Colour", "Café Meetings ☕", "No Colour Key",
                     "Duplicated", "Custom 29"):
            combo = dlg.findChild(QComboBox, f"notif_cat_lead_{name}")
            assert combo is not None, f"category row {name!r} missing"
            seen[f"row:{name}"] = combo.currentText()
        # The duplicate collapsed to a single row rather than two combos
        # fighting over one objectName.
        seen["dup_rows"] = len(dlg.findChildren(QComboBox, "notif_cat_lead_Duplicated"))
        dlg.reject()

    _drive(interact, failures)
    open_settings(window)                    # must not raise → must not qFatal
    if failures:
        raise failures[0]

    assert seen["auto"] is True              # confirmation_level: 0
    assert seen["observance"] is True        # ObservanceConfig default
    assert seen["notif"] is True             # NotificationsConfig default
    assert seen["lead"] == ("Off", 0)        # default_lead_minutes: 0
    assert seen["dup_rows"] == 1
    for name in ("Work", "Bad Colour", "Café Meetings ☕", "No Colour Key",
                 "Duplicated", "Custom 29"):
        assert seen[f"row:{name}"] == "Default"


def test_saving_creates_the_sections_the_live_config_never_had(
        app, real_config, odd_categories, monkeypatch):
    """Save against a config with no notifications/observance section: both are
    created, category_leads lands as a mapping, and a non-ascii category name
    survives the round-trip as a YAML key."""
    cfg, cfg_file = real_config
    real = config_store.set_values
    monkeypatch.setattr(config_store, "set_values",
                        lambda updates, path=str(cfg_file): real(updates, path))
    monkeypatch.setattr(config_store, "CONFIG_PATH", str(cfg_file))

    window = _Window(cfg)
    failures: list = []
    seen: dict = {}

    def interact(dlg):
        cafe = dlg.findChild(QComboBox, "notif_cat_lead_Café Meetings ☕")
        assert cafe is not None, "the non-ascii category has no row"
        QTest.keyClicks(cafe, "M")                  # → "Muted" (0)
        seen["cafe"] = (cafe.currentText(), cafe.currentData())
        auto = next(cb for cb in dlg.findChildren(QCheckBox)
                    if cb.text().startswith("Auto-approve"))
        _click(auto)                                # on → off
        seen["auto_after_click"] = auto.isChecked()
        save = next(b for b in dlg.findChildren(QPushButton)
                    if b.text() == "Save Config")
        QTest.mouseClick(save, Qt.MouseButton.LeftButton)

    _drive(interact, failures)
    open_settings(window)
    if failures:
        raise failures[0]

    assert seen["cafe"] == ("Muted", 0)
    assert seen["auto_after_click"] is False

    data = yaml.safe_load(cfg_file.read_text())
    # Sections that did not exist before the save.
    assert data["notifications"]["enabled"] is True
    assert data["notifications"]["default_lead_minutes"] == 0
    assert data["notifications"]["category_leads"] == {"Café Meetings ☕": 0}
    assert data["observance"]["enabled"] is True
    assert data["engine"]["confirm_transcript"] is False
    # The one setting the auto-approve checkbox really drives.
    assert data["confirmation_level"] == 1
    assert cfg.confirmation_level == 1            # and in memory
    # Untouched neighbours and comments survive.
    assert data["hebrew_calendar"]["display_mode"] == "both"
    assert '# "light" | "dark" - default theme on startup' in cfg_file.read_text()


def test_a_pathological_category_list_does_not_abort_the_dialog(
        app, real_config, monkeypatch):
    """Entries categories._load() would never emit, in case something else
    does: a non-dict row, a None name, a name that is only whitespace."""
    cfg, _ = real_config
    monkeypatch.setattr(categories_mod, "all_categories", lambda: [
        "not a dict",
        None,
        {"name": None, "color": "#ffffff"},
        {"name": "  ", "color": "#ffffff"},
        {"color": "#ffffff"},                       # no name key at all
        {"name": "Survivor", "color": "#00ff00"},
    ])

    window = _Window(cfg)
    failures: list = []
    seen: dict = {}

    def interact(dlg):
        seen["survivor"] = dlg.findChild(QComboBox, "notif_cat_lead_Survivor") is not None
        seen["rows"] = len([c for c in dlg.findChildren(QComboBox)
                            if (c.objectName() or "").startswith("notif_cat_lead_")])
        dlg.reject()

    _drive(interact, failures)
    open_settings(window)
    if failures:
        raise failures[0]

    assert seen["survivor"] is True
    assert seen["rows"] == 1        # only the one usable entry got a row
