"""Every command the assistant has run, reachable from the card.

Keeping the previous few runs in the timeline was not what was asked for —
"access to see all iterations" means all of them, including the ones from
before this process started. The bus file already had them: 304 complete runs
on disk, each with its steps, its transcript and its answer, and nothing in
the UI could reach a single one.
"""
from __future__ import annotations

import json
import time

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from assistant import trace_bus  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def bus(tmp_path, monkeypatch):
    path = tmp_path / "trace_bus.jsonl"
    monkeypatch.setattr(trace_bus, "BUS_PATH", str(path))
    return path


def _write(bus, n: int) -> None:
    with open(bus, "w", encoding="utf-8") as f:
        for i in range(n):
            f.write(json.dumps({
                "kind": "trace", "run": f"r{i}", "source": "ios" if i % 2 else "mac",
                "ts": time.time() - (n - i) * 60,
                "steps": [{"stage": "rule", "title": f"Step {i}", "detail": "d",
                           "ms": 100, "at_ms": 0, "ok": True}],
                "result": {"transcript": f"command number {i}", "message": f"did {i}"},
            }) + "\n")


# ------------------------------------------------------------------ reading

def test_history_is_read_newest_first(bus):
    _write(bus, 5)
    got = trace_bus.read_history()
    assert [e["run"] for e in got] == ["r4", "r3", "r2", "r1", "r0"]


def test_history_respects_its_limit(bus):
    _write(bus, 50)
    assert len(trace_bus.read_history(limit=10)) == 10


def test_a_live_run_is_not_offered_as_history(bus):
    """A "begin" with loose steps may still be arriving — only a complete
    "trace" carries its steps and result together."""
    _write(bus, 2)
    with open(bus, "a", encoding="utf-8") as f:
        f.write(json.dumps({"kind": "begin", "run": "live", "source": "mac"}) + "\n")
    assert [e["run"] for e in trace_bus.read_history()] == ["r1", "r0"]


def test_a_corrupt_line_does_not_lose_the_rest(bus):
    _write(bus, 3)
    with open(bus, "a", encoding="utf-8") as f:
        f.write("{not json\n")
    assert len(trace_bus.read_history()) == 3


def test_a_missing_bus_file_is_survivable(bus):
    assert trace_bus.read_history() == []


# ------------------------------------------------------------------- the view

def test_the_history_view_lists_past_commands(qapp, bus):
    from assistant.thinking_hud import ThinkingHUD
    _write(bus, 6)
    hud = ThinkingHUD()
    try:
        hud.panel.toggle_history()
        assert hud.panel._showing_history
        assert len(hud.panel._hist_rows) == 6
    finally:
        hud.close()


def test_the_rows_are_actually_readable(qapp, bus):
    """Counting rows is not seeing them.

    _HistoryRow was first built as a QPushButton with a layout inside it. A
    button takes its size hint from its text, not from any layout it contains,
    so all 200 rows existed, reported themselves present, and rendered 15px
    tall — an empty panel with a full model behind it. The earlier tests
    counted rows and passed.
    """
    from assistant.thinking_hud import ThinkingHUD
    _write(bus, 4)
    hud = ThinkingHUD()
    try:
        hud.show()
        qapp.processEvents()
        hud.panel.toggle_history(True)
        qapp.processEvents()

        row = hud.panel._hist_rows[0]
        assert row.isVisible()
        assert row.geometry().height() > 40, \
            f"row collapsed to {row.geometry().height()}px — nothing to read"
        assert "command number 3" in row._said.text(), "the transcript is not shown"
        assert "did 3" in row._did.text(), "what it did is not shown"
    finally:
        hud.close()


def test_clicking_a_row_opens_that_command(qapp, bus):
    """The rows have to be clickable, not merely present."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest

    from assistant.thinking_hud import ThinkingHUD
    _write(bus, 4)
    hud = ThinkingHUD()
    try:
        hud.show()
        qapp.processEvents()
        hud.panel.toggle_history(True)
        qapp.processEvents()

        QTest.mouseClick(hud.panel._hist_rows[1], Qt.MouseButton.LeftButton)
        qapp.processEvents()
        assert not hud.panel._showing_history, "clicking a row did not open it"
        assert hud.panel.step_count == 1
    finally:
        hud.close()


def test_opening_a_past_command_replays_its_steps(qapp, bus):
    from assistant.thinking_hud import ThinkingHUD
    _write(bus, 3)
    hud = ThinkingHUD()
    try:
        hud.panel.toggle_history()
        hud.panel._open_history_entry(hud.panel._hist_rows[0].entry)
        assert hud.panel.step_count == 1
        assert not hud.panel._showing_history, "it should return to the timeline"
    finally:
        hud.close()


def test_clicking_the_button_actually_toggles(qapp, bus):
    """Clicked, not called.

    Every other test here drove toggle_history() directly and passed while the
    button did nothing at all: QPushButton.clicked emits a `checked` bool, and
    connecting it straight to toggle_history bound that False to the `on`
    argument — so every click meant "hide history". Only a real mouse event
    goes through the signal, so only a real mouse event catches it.
    """
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest

    from assistant.thinking_hud import ThinkingHUD
    _write(bus, 3)
    hud = ThinkingHUD()
    try:
        hud.show()
        qapp.processEvents()
        btn = hud.panel._hist_btn

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        assert hud.panel._showing_history, "the button did not open history"
        assert btn.text() == "Back"

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        assert not hud.panel._showing_history, "the button did not close history"
        assert btn.text() == "History"
    finally:
        hud.close()


def test_the_two_views_are_never_both_visible(qapp, bus):
    from assistant.thinking_hud import ThinkingHUD
    _write(bus, 2)
    hud = ThinkingHUD()
    try:
        hud.show()
        hud.panel.toggle_history(True)
        assert hud.panel._hist_scroll.isVisible() and not hud.panel._scroll.isVisible()
        hud.panel.toggle_history(False)
        assert hud.panel._scroll.isVisible() and not hud.panel._hist_scroll.isVisible()
        # and minimising hides whichever is up
        hud.panel.toggle_minimised(True)
        assert not hud.panel._scroll.isVisible()
        assert not hud.panel._hist_scroll.isVisible()
    finally:
        hud.close()


# ------------------------------------------------------------ search + filters

def _open_history(qapp, bus, n=6):
    from assistant.thinking_hud import ThinkingHUD
    _write(bus, n)
    hud = ThinkingHUD()
    hud.show()
    qapp.processEvents()
    hud.panel.toggle_history(True)
    qapp.processEvents()
    return hud


def _visible(panel):
    return [r for r in panel._hist_rows if r.isVisible()]


def test_typing_narrows_the_list(qapp, bus):
    """Driven through the widget, because the last two bugs here were both
    wiring the model never touches."""
    from PyQt6.QtTest import QTest
    hud = _open_history(qapp, bus)
    try:
        p = hud.panel
        assert len(_visible(p)) == 6
        QTest.keyClicks(p._hist_search, "number 3")
        qapp.processEvents()
        assert len(_visible(p)) == 1
        assert "3" in _visible(p)[0]._said.text()
    finally:
        hud.close()


def test_search_matches_the_answer_too_not_just_the_question(qapp, bus):
    from PyQt6.QtTest import QTest
    hud = _open_history(qapp, bus)
    try:
        p = hud.panel
        QTest.keyClicks(p._hist_search, "did 4")
        qapp.processEvents()
        assert len(_visible(p)) == 1
    finally:
        hud.close()


def test_clearing_the_search_restores_everything(qapp, bus):
    from PyQt6.QtTest import QTest
    hud = _open_history(qapp, bus)
    try:
        p = hud.panel
        QTest.keyClicks(p._hist_search, "number 3")
        qapp.processEvents()
        p._hist_search.clear()
        qapp.processEvents()
        assert len(_visible(p)) == 6
    finally:
        hud.close()


def test_a_source_chip_filters_by_device(qapp, bus):
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    hud = _open_history(qapp, bus)          # _write alternates mac / ios
    try:
        p = hud.panel
        QTest.mouseClick(p._hist_chips["ios"], Qt.MouseButton.LeftButton)
        qapp.processEvents()
        assert _visible(p), "the iPhone chip hid everything"
        assert all((r.entry.get("source") == "ios") for r in _visible(p))
    finally:
        hud.close()


def test_chips_combine_with_the_search(qapp, bus):
    """A chip and a search term are both constraints, not alternatives."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    hud = _open_history(qapp, bus)
    try:
        p = hud.panel
        QTest.mouseClick(p._hist_chips["ios"], Qt.MouseButton.LeftButton)
        QTest.keyClicks(p._hist_search, "number 1")
        qapp.processEvents()
        for r in _visible(p):
            assert r.entry.get("source") == "ios"
            assert "number 1" in r._said.text()
    finally:
        hud.close()


def test_no_matches_says_so(qapp, bus):
    from PyQt6.QtTest import QTest
    hud = _open_history(qapp, bus)
    try:
        p = hud.panel
        QTest.keyClicks(p._hist_search, "zzzzz nothing like this")
        qapp.processEvents()
        assert _visible(p) == []
        assert p._hist_empty.isVisible()
        assert "match" in p._hist_empty.text().lower()
    finally:
        hud.close()


def test_the_count_reports_the_filtering(qapp, bus):
    from PyQt6.QtTest import QTest
    hud = _open_history(qapp, bus)
    try:
        p = hud.panel
        assert p._hist_count.text() == "6 commands"
        QTest.keyClicks(p._hist_search, "number 3")
        qapp.processEvents()
        assert p._hist_count.text() == "1 of 6"
    finally:
        hud.close()


def test_the_tools_hide_with_the_list(qapp, bus):
    hud = _open_history(qapp, bus)
    try:
        p = hud.panel
        assert p._hist_tools.isVisible()
        p.toggle_history(False)
        assert not p._hist_tools.isVisible()
        p.toggle_history(True)
        p.toggle_minimised(True)
        assert not p._hist_tools.isVisible()
    finally:
        hud.close()
