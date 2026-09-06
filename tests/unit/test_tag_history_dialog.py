"""The tag-suggestion history dialog (Mac), driven with real clicks.

Per this repo's hard-won rule, a UI test that never sends a mouse event tests
nothing — every interaction below goes through QTest.mouseClick against the
widgets `TagHistoryDialog` actually builds, using the same
QTimer-drives-the-modal pattern as test_settings_observance.py.

Seeds three rows directly into `tag_suggestion_state` (the table
assistant.actions.todo.tag_discovery owns — same store setup as
test_tag_discovery.py, scratch-isolated by tests/conftest.py) rather than
growing a themed todo list to earn a live candidate(): accepted, refused, and
a still-open one (status "asked" — the same status string the module's own
cooldown sentinel uses, since no per-name "asked" row is ever written by the
real code paths today). The dialog's job is to render and act on whatever
`history()` returns, not to reproduce the mining logic already covered there.
"""
from __future__ import annotations

import datetime

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import QPoint, Qt, QTimer                           # noqa: E402
from PyQt6.QtTest import QTest                                        # noqa: E402
from PyQt6.QtWidgets import (                                         # noqa: E402
    QApplication, QCheckBox, QLabel, QPushButton, QWidget,
)

import assistant.actions.todo.tag_discovery as disc                   # noqa: E402
from assistant.calendar_ui.tag_history_dialog import (                # noqa: E402
    TagHistoryDialog, _TagHistoryRow, open_tag_history,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _Window(QWidget):
    """The least a parent needs for open_tag_history(self)."""

    def __init__(self):
        super().__init__()
        self._dark = True


@pytest.fixture
def seeded_db():
    from assistant.db import get_db
    d = get_db()
    with d._conn() as conn:
        for table in ("todos", "tag_suggestion_state"):
            try:
                conn.execute(f"DELETE FROM {table}")
            except Exception:
                pass
        conn.execute("DELETE FROM todo_tags WHERE builtin = 0")
        disc._ensure(conn)
        now = datetime.datetime.now().isoformat()
        for name, status in (("terrarium", "accepted"),
                             ("pharmacy", "refused"),
                             ("scuba", "asked")):
            conn.execute(
                "INSERT INTO tag_suggestion_state (name, status, ts, hidden) "
                "VALUES (?, ?, ?, 0)", (name, status, now))
    # "Terrarium" being marked accepted only means something alongside a real
    # tag row — give a future retract something real to delete.
    d.create_tag("Terrarium")
    return d


def _drive(interact, failures):
    """Run real interaction against the modal once it is up.

    A failure inside the Qt callback would otherwise leave exec() spinning
    forever, so it is recorded and the dialog closed; the test re-raises it.
    """
    def _go():
        dlg = QApplication.activeModalWidget()
        if dlg is None:
            QTimer.singleShot(10, _go)
            return
        try:
            interact(dlg)
        except Exception as e:                 # noqa: BLE001 — re-raised below
            failures.append(e)
            dlg.reject()
    QTimer.singleShot(0, _go)


def _rows(dlg) -> dict:
    """entry name -> its row, for the rows currently rendered.

    reload() replaces rows via takeAt()+deleteLater(); the dialog hides a
    row before scheduling its deletion (see tag_history_dialog.reload's
    comment) specifically so a stale row can't still look "current" here —
    filtering on isVisible() is what actually excludes it.
    """
    return {row._entry["name"]: row for row in dlg.findChildren(_TagHistoryRow)
            if row.isVisible()}


def _badge(row) -> "str | None":
    for lbl in row.findChildren(QLabel):
        if lbl.text() in ("Accepted", "Declined", "Pending"):
            return lbl.text()
    return None


def _button(row, text: str) -> QPushButton:
    return next(b for b in row.findChildren(QPushButton) if b.text() == text)


def _click_checkbox(cb: QCheckBox) -> None:
    """QCheckBox restricts its clickable hit-region to the indicator+label
    box (QStyle::SE_CheckBoxClickable), not the widget's full stretched
    width — a default center click can land past it and silently do
    nothing. Same fix as test_settings_observance.py: click the leading
    edge, over the indicator."""
    QTest.mouseClick(cb, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     QPoint(8, cb.height() // 2))


# ------------------------------------------------------------------ render


def test_rows_render_with_the_right_statuses(app, seeded_db):
    failures: list = []
    seen: dict = {}

    def interact(dlg):
        rows = _rows(dlg)
        seen["names"] = set(rows)
        seen["badges"] = {name: _badge(row) for name, row in rows.items()}
        dlg.reject()

    _drive(interact, failures)
    win = _Window()
    open_tag_history(win)
    if failures:
        raise failures[0]

    assert seen["names"] == {"Terrarium", "Pharmacy", "Scuba"}
    assert seen["badges"] == {
        "Terrarium": "Accepted", "Pharmacy": "Declined", "Scuba": "Pending",
    }


# ------------------------------------------------------------- change answer


def test_accepting_a_declined_suggestion_updates_the_store(app, seeded_db):
    failures: list = []

    def interact(dlg):
        rows = _rows(dlg)
        accept_btn = _button(rows["Pharmacy"], "Accept")
        QTest.mouseClick(accept_btn, Qt.MouseButton.LeftButton)
        QApplication.processEvents()
        # the row rebuilds after reload() — re-fetch before checking its badge
        rows = _rows(dlg)
        assert _badge(rows["Pharmacy"]) == "Accepted"
        dlg.reject()

    _drive(interact, failures)
    dlg = TagHistoryDialog(dark=True)
    dlg.exec()
    if failures:
        raise failures[0]

    entries = {e["name"]: e for e in disc.history()}
    assert entries["Pharmacy"]["status"] == "accepted"
    assert "Pharmacy" in [t["name"] for t in seeded_db.get_tags()]


def test_retracting_an_accepted_suggestion_removes_the_tag(app, seeded_db):
    assert "Terrarium" in [t["name"] for t in seeded_db.get_tags()]
    failures: list = []

    def interact(dlg):
        rows = _rows(dlg)
        retract_btn = _button(rows["Terrarium"], "Retract")
        QTest.mouseClick(retract_btn, Qt.MouseButton.LeftButton)
        QApplication.processEvents()
        rows = _rows(dlg)
        assert _badge(rows["Terrarium"]) == "Declined"
        dlg.reject()

    _drive(interact, failures)
    dlg = TagHistoryDialog(dark=True)
    dlg.exec()
    if failures:
        raise failures[0]

    entries = {e["name"]: e for e in disc.history()}
    assert entries["Terrarium"]["status"] == "refused"
    assert "Terrarium" not in [t["name"] for t in seeded_db.get_tags()]


# ------------------------------------------------------------------- hiding


def test_hiding_a_row_drops_it_from_the_default_view_and_flags_the_store(app, seeded_db):
    failures: list = []
    seen: dict = {}

    def interact(dlg):
        rows = _rows(dlg)
        hide_btn = _button(rows["Scuba"], "Hide")
        QTest.mouseClick(hide_btn, Qt.MouseButton.LeftButton)
        QApplication.processEvents()

        seen["after_hide"] = set(_rows(dlg))

        show_hidden = dlg.findChild(QCheckBox, "tag_history_show_hidden")
        assert show_hidden is not None
        _click_checkbox(show_hidden)
        QApplication.processEvents()
        rows = _rows(dlg)
        seen["after_show_hidden"] = set(rows)
        seen["scuba_badge_when_shown"] = _badge(rows["Scuba"])
        dlg.reject()

    _drive(interact, failures)
    dlg = TagHistoryDialog(dark=True)
    dlg.exec()
    if failures:
        raise failures[0]

    assert "Scuba" not in seen["after_hide"]
    assert seen["after_hide"] == {"Terrarium", "Pharmacy"}
    assert "Scuba" in seen["after_show_hidden"]
    assert seen["scuba_badge_when_shown"] == "Pending"

    entries = {e["name"]: e for e in disc.history()}
    assert entries["Scuba"]["hidden"] is True
