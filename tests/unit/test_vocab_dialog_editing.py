"""The vocabulary screen, driven the way a person drives it.

Three bugs in this codebase shipped with green tests because the tests called
the handler instead of operating the control: a signal that passed a bool as
the first argument, rows built from a widget that collapsed to 15px, and a
search box that could never receive focus. Every one of them would have been
caught by a mouse event and was not caught by a function call.

So these use QTest. The search box is typed into with keyClicks, and the row
is opened with a double-click on the actual item, which is what exercises the
signal wiring rather than the method it happens to be connected to.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import Qt, QTimer                                 # noqa: E402
from PyQt6.QtTest import QTest                                      # noqa: E402
from PyQt6.QtWidgets import QApplication, QDialog, QLineEdit        # noqa: E402


def _double_click(dlg, prefix: str) -> None:
    """Actually double-click the row, on the viewport, where it is drawn.

    Emitting itemDoubleClicked would prove the handler works and nothing about
    whether a person can reach it — which is the exact gap that let three UI
    bugs ship green here.
    """
    row = next(i for i in range(dlg._list.count())
               if dlg._list.item(i).text().startswith(prefix))
    dlg._list.scrollToItem(dlg._list.item(row))
    QApplication.processEvents()
    centre = dlg._list.visualItemRect(dlg._list.item(row)).center()
    viewport = dlg._list.viewport()
    # A bare mouseDClick does not raise itemDoubleClicked on macOS: the view
    # wants the item selected by a preceding press before it treats the second
    # click as a double. Measured, not guessed — dclick alone fires nothing.
    QTest.mouseClick(viewport, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, centre)
    QTest.mouseDClick(viewport, Qt.MouseButton.LeftButton,
                      Qt.KeyboardModifier.NoModifier, centre)

from assistant.stt.vocab import VocabStore                          # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def dialog(app, tmp_path, monkeypatch):
    """The real dialog, against a scratch word list with three words in it."""
    store = VocabStore(str(tmp_path / "vocab.json"))
    store.add_word("Trig", ["trigger"], label="Coursework")
    store.add_word("pset", expands_to="problem set")
    store.add_word("Dana")

    from assistant.calendar_ui import vocab_dialog as vd
    monkeypatch.setattr(vd, "get_vocab", lambda: store, raising=False)

    dlg = vd.VocabDialog()
    if getattr(dlg, "_vocab", None) is not store:
        dlg._vocab = store
        dlg._refresh_vocab()
    # A hidden widget has no on-screen geometry, so visualItemRect comes back
    # empty and a synthetic click lands nowhere. Showing it is the difference
    # between testing the wiring and testing nothing.
    dlg.show()
    QTest.qWaitForWindowExposed(dlg, 2000)
    QApplication.processEvents()
    yield dlg, store
    dlg.close()


def _rows(dlg):
    return [dlg._list.item(i).text() for i in range(dlg._list.count())]


# ---------------------------------------------------------------------------
# What the list shows
# ---------------------------------------------------------------------------

def test_the_list_shows_what_each_word_does(dialog):
    dlg, _ = dialog
    rows = " | ".join(_rows(dlg))
    assert "[Coursework]" in rows, "a label is not shown"
    assert "problem set" in rows, "an expansion is not shown"
    assert "heard as: trigger" in rows, "an alias is not shown"


# ---------------------------------------------------------------------------
# The search box — typed into, not set programmatically
# ---------------------------------------------------------------------------

def test_typing_in_the_search_box_filters_the_list(dialog):
    dlg, _ = dialog
    assert len(_rows(dlg)) == 3

    dlg._search.setFocus()
    QTest.keyClicks(dlg._search, "Dana")
    QApplication.processEvents()

    rows = _rows(dlg)
    assert len(rows) == 1 and rows[0].startswith("Dana"), rows


def test_search_matches_a_label_not_only_the_word(dialog):
    """You are as likely to want everything tagged Coursework as one word."""
    dlg, _ = dialog
    dlg._search.setFocus()
    QTest.keyClicks(dlg._search, "coursework")
    QApplication.processEvents()
    assert [r.split()[0] for r in _rows(dlg)] == ["Trig"]


def test_clearing_the_search_brings_every_word_back(dialog):
    dlg, _ = dialog
    QTest.keyClicks(dlg._search, "Dana")
    QApplication.processEvents()
    dlg._search.clear()
    QApplication.processEvents()
    assert len(_rows(dlg)) == 3


def test_the_search_box_can_actually_take_focus(dialog):
    """The bug that shipped last time: a read-only pass had made it unfocusable."""
    dlg, _ = dialog
    assert dlg._search.focusPolicy() != Qt.FocusPolicy.NoFocus
    assert not dlg._search.isReadOnly()


# ---------------------------------------------------------------------------
# Editing, opened by a real double-click
# ---------------------------------------------------------------------------

def _answer_editor(fill: dict, accept: bool = True):
    """Fill in the modal editor the next time one appears, then close it."""
    def run():
        dlg = next((w for w in QApplication.topLevelWidgets()
                    if isinstance(w, QDialog) and w.isVisible()
                    and w.windowTitle() in fill.get("_titles", fill.get("_title", ""))), None)
        if dlg is None:
            return
        fields = dlg.findChildren(QLineEdit)
        for idx, value in fill.get("fields", {}).items():
            fields[idx].setText(value)
        dlg.accept() if accept else dlg.reject()
    # Not 0: the double-click pumps events synchronously, so a zero-delay
    # timer fires before the modal's own event loop has started and finds no
    # dialog to fill in. This must land inside exec(), not before it.
    QTimer.singleShot(150, run)


def test_double_clicking_a_word_opens_an_editor_that_saves(dialog):
    dlg, store = dialog
    # 0 = label, 1 = expansion, 2 = aliases, in the order the form builds them.
    _answer_editor({"_title": "Dana", "_titles": ["Dana"],
                    "fields": {0: "Personal"}})
    _double_click(dlg, "Dana")
    QTest.qWait(400)

    entry = next(e for e in store.entries if e.word == "Dana")
    assert entry.label == "Personal", "the edit did not reach the word list"


def test_cancelling_the_editor_changes_nothing(dialog):
    dlg, store = dialog
    _answer_editor({"_title": "Trig", "_titles": ["Trig"],
                    "fields": {0: "Wrong"}}, accept=False)
    _double_click(dlg, "Trig")
    QTest.qWait(400)

    entry = next(e for e in store.entries if e.word == "Trig")
    assert entry.label == "Coursework", "cancel still wrote the change"


def test_the_double_click_signal_is_connected_at_all(dialog):
    """The failure mode this whole file exists for: a control wired to nothing."""
    dlg, _ = dialog
    assert dlg._list.receivers(dlg._list.itemDoubleClicked) > 0, \
        "double-clicking a word is connected to nothing"
