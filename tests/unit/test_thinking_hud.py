"""The thinking HUD — a separate app fed by the trace bus.

The trace used to be drawn inside the calendar window, so you only saw what the
assistant did if you happened to be looking at the calendar — which you rarely
are when you speak to it from the phone. These cover the two halves of moving
it out: the bus carrying a run as it happens (it used to carry only finished
ones, published by the API server), and the HUD rendering both shapes.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture
def bus(tmp_path, monkeypatch):
    monkeypatch.setenv("MACALENDAR_TRACE_BUS", str(tmp_path / "bus.jsonl"))
    from assistant import trace_bus
    monkeypatch.setattr(trace_bus, "BUS_PATH", str(tmp_path / "bus.jsonl"))
    return trace_bus


def _enter_event():
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QEnterEvent
    from PyQt6.QtCore import Qt
    return QEnterEvent(QPointF(1, 1), QPointF(1, 1), QPointF(1, 1))


def _leave_event():
    from PyQt6.QtCore import QEvent
    return QEvent(QEvent.Type.Leave)


def _step(stage="stt", title="Heard", detail=""):
    return {"stage": stage, "title": title, "detail": detail, "ms": 5, "at_ms": 5, "ok": True}


# ---------------------------------------------------------------------------
# The bus
# ---------------------------------------------------------------------------

def test_a_streaming_run_arrives_line_by_line(bus):
    offset = bus.size()
    run = bus.publish_begin("Mac")
    bus.publish_step(run, _step())
    bus.publish_result(run, {"message": "done"})

    entries, offset = bus.read_since(offset)
    assert [e["kind"] for e in entries] == ["begin", "step", "result"]
    assert all(e["run"] == run for e in entries)
    assert entries[0]["source"] == "Mac"
    assert entries[2]["result"] == {"message": "done"}


def test_a_reader_that_polls_late_still_gets_the_whole_run(bus):
    offset = bus.size()
    run = bus.publish_begin("Mac")
    for _ in range(3):
        bus.publish_step(run, _step())
    bus.publish_result(run)
    entries, _ = bus.read_since(offset)
    assert len(entries) == 5


def test_read_since_returns_nothing_new_when_nothing_happened(bus):
    run = bus.publish_begin("Mac")
    bus.publish_result(run)
    offset = bus.size()
    assert bus.read_since(offset) == ([], offset)


def test_a_whole_finished_run_still_publishes_in_one_line(bus):
    # This is what the API server does for the phone; it must keep working.
    offset = bus.size()
    bus.publish("iPhone", [_step()], {"message": "Two events"})
    entries, _ = bus.read_since(offset)
    assert len(entries) == 1
    assert entries[0]["kind"] == "trace"
    assert entries[0]["source"] == "iPhone"


def test_a_line_written_before_streaming_existed_reads_as_a_finished_run(bus):
    # Entries already on disk from the previous format have no "kind".
    with open(bus.BUS_PATH, "w", encoding="utf-8") as f:
        f.write('{"ts": 1, "source": "iPhone", "steps": [], "result": {}}\n')
    entries, _ = bus.read_since(0)
    assert entries[0]["kind"] == "trace"


def test_a_trim_never_lands_inside_a_run(bus, monkeypatch):
    monkeypatch.setattr(bus, "MAX_ENTRIES", 4)
    for _ in range(20):                     # plenty to trigger trimming
        run = bus.publish_begin("Mac")
        bus.publish_step(run, _step())
        bus.publish_result(run)
    with open(bus.BUS_PATH, encoding="utf-8") as f:
        kinds = [__import__("json").loads(line)["kind"] for line in f]
    # However the file was cut, the last run is whole: it began after the trim.
    assert kinds[-3:] == ["begin", "step", "result"]


# ---------------------------------------------------------------------------
# The HUD
# ---------------------------------------------------------------------------

@pytest.fixture
def hud(bus, tmp_path, monkeypatch):
    # PyQt6 itself imports fine without the system GL libraries; QtWidgets is
    # what raises (libEGL.so.1 on a bare CI runner), so that is what to probe.
    pytest.importorskip("PyQt6.QtWidgets")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("MACALENDAR_HUD_STATE", str(tmp_path / "pos.json"))
    from PyQt6.QtWidgets import QApplication
    import assistant.thinking_hud as hud_mod
    monkeypatch.setattr(hud_mod, "STATE_PATH", str(tmp_path / "pos.json"))
    app = QApplication.instance() or QApplication([])
    widget = hud_mod.ThinkingHUD(None)
    reader = hud_mod._BusReader(widget, str(tmp_path / "no-such-config.yaml"))
    yield widget, reader, app
    widget.close()
    widget.deleteLater()


def test_it_stays_out_of_the_way_until_something_happens(hud):
    widget, _, _ = hud
    assert not widget.isVisible()


def test_a_streaming_run_shows_it_and_fills_in(hud, bus):
    widget, reader, _ = hud
    run = bus.publish_begin("Mac")
    reader.poll()
    assert widget.isVisible()
    assert widget.panel.running and widget.panel.step_count == 0

    bus.publish_step(run, _step("stt", "Heard", "buy chicken and rice"))
    bus.publish_step(run, _step("execute", "Create Todo"))
    reader.poll()
    assert widget.panel.step_count == 2

    bus.publish_result(run, {"message": "Added 2 tasks"})
    reader.poll()
    assert not widget.panel.running


def test_a_late_self_check_step_reopens_the_timeline(hud, bus):
    widget, reader, _ = hud
    run = bus.publish_begin("Mac")
    bus.publish_step(run, _step())
    bus.publish_result(run, {"message": "ok"})
    reader.poll()
    assert not widget.panel.running

    bus.publish_step(run, _step("verify", "Self-check"))
    reader.poll()
    assert widget.panel.running and widget.panel.step_count == 2


def test_a_phone_run_is_labelled_as_the_phone(hud, bus):
    widget, reader, _ = hud
    bus.publish("iPhone", [_step(), _step("execute", "Create Todo")], {"message": "Added"})
    reader.poll()
    assert widget.isVisible()
    assert widget.panel.step_count == 2
    assert "iPhone" in widget.panel._title.text()


def test_closing_it_hides_it_and_the_next_command_brings_it_back(hud, bus):
    widget, reader, _ = hud
    bus.publish("iPhone", [_step()], {})
    reader.poll()
    widget.panel._on_close()
    assert not widget.isVisible()

    bus.publish("iPhone", [_step()], {})
    reader.poll()
    assert widget.isVisible()


def test_a_step_whose_begin_was_trimmed_away_still_opens_a_run(hud, bus):
    widget, reader, _ = hud
    bus.publish_step("a-run-we-never-saw", _step("stt", "Heard", "orphan"))
    reader.poll()
    assert widget.isVisible()
    assert widget.panel.step_count == 1


def test_show_thinking_off_keeps_it_hidden(hud, bus):
    widget, reader, _ = hud
    from assistant.config import UIConfig

    class _Cfg:
        ui = UIConfig(show_thinking=False)
    widget._config = _Cfg()

    bus.publish("iPhone", [_step()], {})
    reader.poll()
    assert not widget.isVisible()


@pytest.mark.parametrize("corner", ["bottom-right", "bottom-left", "top-right", "top-left"])
def test_it_parks_on_screen_in_every_corner(hud, corner):
    widget, _, app = hud
    from assistant.config import UIConfig

    class _Cfg:
        ui = UIConfig(thinking_corner=corner)
    widget._config = _Cfg()
    widget._park()

    area = app.primaryScreen().availableGeometry()
    assert area.contains(widget.geometry()), f"{corner} put it off screen"


def test_a_dragged_position_is_remembered_and_overrides_the_corner(hud):
    widget, _, _ = hud
    import assistant.thinking_hud as hud_mod

    hud_mod._save_position(120, 240)
    widget.mark_moved()
    widget._park()
    assert (widget.pos().x(), widget.pos().y()) == (120, 240)
    assert os.path.exists(hud_mod.STATE_PATH)


def test_it_sits_translucent_until_you_look_at_it(hud, bus):
    """"There, but not what you're on": it settles below full opacity.

    The animation's target is what's asserted, not the window's actual
    opacity — the offscreen platform used in tests cannot set one.
    """
    widget, reader, _ = hud
    import assistant.thinking_hud as hud_mod

    assert hud_mod.IDLE_OPACITY < hud_mod.HOVER_OPACITY

    bus.publish("iPhone", [_step()], {})
    reader.poll()
    assert widget._fade.endValue() == pytest.approx(hud_mod.IDLE_OPACITY)

    widget.enterEvent(_enter_event())        # pointer moves over it
    assert widget._fade.endValue() == pytest.approx(hud_mod.HOVER_OPACITY)

    widget.leaveEvent(_leave_event())        # …and away again
    assert widget._fade.endValue() == pytest.approx(hud_mod.IDLE_OPACITY)


def test_it_never_takes_the_keyboard(hud):
    # WA_ShowWithoutActivating is the whole reason this is usable: the card
    # appearing must not pull focus out of whatever you were typing in.
    from PyQt6.QtCore import Qt
    widget, _, _ = hud
    assert widget.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    assert widget.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
    # …and not Qt.Tool, which macOS hides whenever the owning app is inactive —
    # which, for a Dock-less accessory app, is always.
    assert not (widget.windowFlags() & Qt.WindowType.Tool == Qt.WindowType.Tool)


# ---------------------------------------------------------------------------
# Which device it says the command came from
# ---------------------------------------------------------------------------

def test_a_command_spoken_at_the_mac_is_not_labelled_as_the_phone(hud, bus):
    widget, reader, _ = hud
    # A phone run first, so a stale label would be visible if it didn't reset.
    bus.publish("ios", [_step()], {})
    reader.poll()
    assert "iPhone" in widget.panel._title.text()

    run = bus.publish_begin("Mac")
    bus.publish_step(run, _step())
    reader.poll()
    assert widget.panel._title.text() == "Thinking"


@pytest.mark.parametrize("published,shown", [
    ("ios", "Thinking · from your iPhone"),     # what the API server publishes
    ("iPhone", "Thinking · from your iPhone"),
    ("mac", "Thinking"),                        # what Pipeline._trace_begin publishes
    ("Mac", "Thinking"),
    ("ipad", "Thinking · from your iPad"),
])
def test_the_source_is_named_the_way_a_person_would(hud, bus, published, shown):
    widget, reader, _ = hud
    bus.publish(published, [_step()], {})
    reader.poll()
    assert widget.panel._title.text() == shown


# ---------------------------------------------------------------------------
# Where it puts itself
# ---------------------------------------------------------------------------

def test_a_saved_position_off_the_current_screen_is_pulled_back_on(hud):
    """A position saved against a screen you no longer have must not hide it.

    This is how the HUD went missing: a stale `hud_position.json` put it a few
    pixels below the usable area, so it was drawn — on screen, right size, full
    opacity — with only its top edge showing, and nothing said why.
    """
    widget, _, app = hud
    import assistant.thinking_hud as hud_mod

    area = app.primaryScreen().availableGeometry()
    hud_mod._save_position(area.left() + 40, area.bottom() + 500)   # way off the bottom
    widget.mark_moved()
    widget._park()

    assert area.contains(widget.geometry())


def test_a_click_on_the_header_is_not_a_drag(hud):
    """Pressing and releasing without moving must not pin the card.

    It used to save a position and mark it moved, which silently opted out of
    corner parking for good — on the next launch it reappeared wherever that
    stray click happened to leave it.
    """
    from PyQt6.QtCore import QEvent, QPointF, Qt
    from PyQt6.QtGui import QMouseEvent
    widget, _, _ = hud
    import assistant.thinking_hud as hud_mod

    def _mouse(kind, x, y):
        return QMouseEvent(kind, QPointF(x, y), QPointF(x, y), QPointF(x, y),
                           Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                           Qt.KeyboardModifier.NoModifier)

    drag = widget._drag
    drag.eventFilter(None, _mouse(QEvent.Type.MouseButtonPress, 100, 100))
    drag.eventFilter(None, _mouse(QEvent.Type.MouseButtonRelease, 101, 100))   # 1px

    assert not widget._moved
    assert not os.path.exists(hud_mod.STATE_PATH)


def test_minimising_collapses_the_card_and_the_window_with_it(hud, bus):
    """The – button did nothing at all.

    `clicked` carries the checked state, so connecting it straight to
    `toggle_minimised` passed a bool into that method's `minimised` parameter —
    always False, always "restore", never a toggle.
    """
    widget, reader, app = hud
    bus.publish("mac", [_step()], {"message": "ok"})
    reader.poll()
    panel = widget.panel
    open_height = widget.height()

    panel._min_btn.click()
    app.processEvents()
    assert panel.minimised
    assert not panel._scroll.isVisible()          # body hidden, header still there
    assert panel._min_btn.text() == "+"
    assert widget.height() < open_height          # the window shrank with it

    panel._min_btn.click()
    app.processEvents()
    assert not panel.minimised
    assert panel._scroll.isVisible()
    assert panel._min_btn.text() == "–"
    assert widget.height() == open_height


def test_a_minimised_card_stays_minimised_for_the_next_command(hud, bus):
    # Minimising it means "keep it out of my way"; the header goes on counting.
    widget, reader, app = hud
    bus.publish("mac", [_step()], {})
    reader.poll()
    widget.panel._min_btn.click()
    app.processEvents()

    bus.publish("mac", [_step(), _step("execute", "Create Todo")], {})
    reader.poll()
    assert widget.panel.minimised
    assert widget.panel.step_count == 2
