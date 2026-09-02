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
