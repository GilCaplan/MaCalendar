"""The assistant's thinking HUD — its own app.

The trace used to be drawn inside the calendar window, which meant you only
saw what the assistant did if you happened to be looking at the calendar. But
a command spoken to the phone is usually given *while doing something else* —
the whole point of talking to it — and the calendar app may not even be
running. So this is a separate process: a small always-on-top card that floats
over whatever you are actually working in, fed by `assistant.trace_bus`.

    python -m assistant.thinking_hud

It is started alongside the API server by `Launch Calendar.command`. It draws
the same `ThinkingPanel` widget the calendar app used to embed, so the Mac's
timeline and the iPhone's stay identical.

Behaviour: it appears by itself when a command starts, fills in live, and
stays until you close it — a trace you glanced away from is still there when
you look back. Closing hides it until the next command; right-click quits.
"""

from __future__ import annotations

import json
import logging
import os
import sys

from PyQt6.QtCore import (
    QEasingCurve, QEvent, QObject, QPoint, QPropertyAnimation, Qt, QTimer,
)
from PyQt6.QtGui import QAction, QCursor
from PyQt6.QtWidgets import QApplication, QMenu, QVBoxLayout, QWidget

from assistant import trace_bus
from assistant.calendar_ui.thinking_panel import PANEL_WIDTH, ThinkingPanel

logger = logging.getLogger(__name__)

POLL_MS = 120                    # how often the bus is tailed
SHADOW_MARGIN = 26               # room around the panel for its drop shadow
SCREEN_MARGIN = 24               # gap from the screen edge

# It should read as "there, but not what you are on": slightly see-through
# while you carry on working, solid the moment you look at it. Kept high —
# at 0.86 a busy page behind it bled through the card and the trace became
# hard to read, which defeats the point of showing it.
IDLE_OPACITY = 0.94
HOVER_OPACITY = 1.0
FADE_MS = 140

# Where the user dragged it, if they did. Kept out of config.yaml: it is window
# state, not a setting, and it changes every time the card is moved.
STATE_PATH = os.environ.get("MACALENDAR_HUD_STATE") or os.path.expanduser(
    "~/.assistant_tools/hud_position.json")


def _load_position() -> tuple[int, int] | None:
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            d = json.load(f)
        return int(d["x"]), int(d["y"])
    except Exception:
        return None


def _save_position(x: int, y: int) -> None:
    try:
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        tmp = STATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"x": int(x), "y": int(y)}, f)
        os.replace(tmp, STATE_PATH)
    except Exception:
        pass


# A press that wanders less than this is a click, not a drag.
DRAG_SLOP = 4


class _DragFilter(QObject):
    """Drag the frameless window by its header, the way a title bar would."""

    def __init__(self, window: "ThinkingHUD") -> None:
        super().__init__(window)
        self._window = window
        self._grab: QPoint | None = None
        self._origin: QPoint | None = None

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.globalPosition().toPoint()
            self._grab = self._origin - self._window.frameGeometry().topLeft()
        elif event.type() == QEvent.Type.MouseMove and self._grab is not None:
            self._window.move(event.globalPosition().toPoint() - self._grab)
        elif event.type() == QEvent.Type.MouseButtonRelease and self._grab is not None:
            moved = (event.globalPosition().toPoint() - self._origin).manhattanLength()
            self._grab = self._origin = None
            # Only a real drag pins the card. A stray click on the header used
            # to save a position and silently opt out of corner parking for good.
            if moved >= DRAG_SLOP:
                pos = self._window.pos()
                _save_position(pos.x(), pos.y())
                self._window.mark_moved()
        return False


class ThinkingHUD(QWidget):
    """Top-level, always on top, and never steals focus.

    `WA_ShowWithoutActivating` is what makes it usable: the card appearing must
    not take the keyboard away from whatever you were typing in when you spoke
    to the assistant.
    """

    def __init__(self, config=None) -> None:
        super().__init__(None)
        self._config = config
        self._dark = (getattr(config, "theme", "dark") == "dark") if config else True
        self._moved = _load_position() is not None
        self._current_run: str | None = None
        self._dismissed_run: str | None = None

        # Deliberately NOT Qt.Tool: on macOS a tool window hides whenever its
        # application is not the active one, and this app is never active (it
        # is an accessory with no Dock icon), so a Tool window is invisible in
        # exactly the situation the HUD exists for.
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle("Assistant thinking")
        # Read-only until you deliberately use it. The card is something you
        # glance at while working in something else, so nothing inside it may
        # accept the keyboard: its buttons still take clicks, but a click never
        # moves the caret out of whatever you were typing in. Without this,
        # clicking anywhere on the card — or the card merely appearing under a
        # pointer — pulled focus and the next keystroke went into the void.
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN)
        self.panel = ThinkingPanel(self, dark=self._dark)
        self.panel.closed.connect(self._on_panel_closed)
        self.panel.retry_requested.connect(self._on_retry)
        self.panel.resized.connect(self._fit)
        lay.addWidget(self.panel)
        self.panel.show()          # the panel hides itself on construction
        self._make_read_only()

        self._drag = _DragFilter(self)
        self.panel.header_widget.installEventFilter(self._drag)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)

        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(FADE_MS)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.setWindowOpacity(IDLE_OPACITY)

        self._fit()
        self.hide()

    # ------------------------------------------------------------- presence

    def _follow_every_space(self) -> None:
        """Show on every Space, including over another app's full-screen window.

        Without this the card belongs to the Space it was created on: switch to
        a full-screen app — which is exactly when you are working in something
        else and want to see what the assistant did — and it is simply not
        there. Cocoa-only, so it is best effort; without pyobjc the HUD still
        works, it just stays on its own Space.
        """
        # winId() is a real NSView pointer only under the Cocoa platform. Under
        # the offscreen platform the tests use there is no NSWindow behind it,
        # and handing that pointer to pyobjc segfaults the interpreter.
        if QApplication.platformName() != "cocoa":
            return
        try:
            import ctypes

            import objc
            from AppKit import (
                NSWindowCollectionBehaviorCanJoinAllSpaces,
                NSWindowCollectionBehaviorFullScreenAuxiliary,
                NSWindowCollectionBehaviorStationary,
            )
            view = objc.objc_object(c_void_p=ctypes.c_void_p(int(self.winId())))
            window = view.window()
            if window is None:
                return
            window.setCollectionBehavior_(
                NSWindowCollectionBehaviorCanJoinAllSpaces
                | NSWindowCollectionBehaviorFullScreenAuxiliary
                | NSWindowCollectionBehaviorStationary
            )
        except Exception as exc:
            logger.debug("Could not make the HUD span Spaces: %s", exc)

    def _order_front_without_activating(self) -> None:
        """Put the card in front without making this app frontmost.

        Cocoa's orderFront_ does exactly that; Qt's raise_() goes through
        makeKeyAndOrderFront on some paths and takes the keyboard with it.
        Best effort — without pyobjc the window is already top-most from
        WindowStaysOnTopHint, it simply may not jump above a sibling.
        """
        if QApplication.platformName() != "cocoa":
            return
        try:
            import ctypes

            import objc
            from AppKit import NSFloatingWindowLevel

            view = objc.objc_object(c_void_p=ctypes.c_void_p(int(self.winId())))
            window = view.window()
            if window is None:
                return
            window.setLevel_(NSFloatingWindowLevel)
            window.orderFront_(None)
        except Exception as exc:
            logger.debug("Could not order the HUD front without activating: %s", exc)

    def _fade_to(self, opacity: float) -> None:
        self._fade.stop()
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(opacity)
        self._fade.start()

    def enterEvent(self, event):            # noqa: N802 - Qt naming
        self._fade_to(HOVER_OPACITY)
        super().enterEvent(event)

    def leaveEvent(self, event):            # noqa: N802 - Qt naming
        self._fade_to(IDLE_OPACITY)
        super().leaveEvent(event)

    # ----------------------------------------------------------- geometry

    def mark_moved(self) -> None:
        self._moved = True

    def _fits(self, pos: tuple[int, int], area) -> bool:
        """Is there room for the card anywhere near where it was left?"""
        return area.width() >= self.width() and area.height() >= self.height()

    def _make_read_only(self) -> None:
        """Stop anything inside the card from accepting the keyboard.

        setFocusPolicy on the window alone does not reach its children, and a
        QPushButton defaults to StrongFocus — so clicking Close or Retry took
        the caret out of whatever was being typed. Buttons still receive their
        clicks; they just never become the focus widget.

        Re-run whenever the panel grows, because trace steps are added as they
        arrive and a widget built after construction would miss the sweep.
        """
        self.panel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for child in self.panel.findChildren(QWidget):
            child.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def _fit(self) -> None:
        self.setFixedSize(self.panel.width() + 2 * SHADOW_MARGIN,
                          self.panel.height() + 2 * SHADOW_MARGIN)
        self._make_read_only()
        self._park()

    def _park(self) -> None:
        """Sit in the configured screen corner — unless the user moved it,
        in which case leave it where they put it, as far as the screen allows."""
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        if self._moved:
            saved = _load_position()
            if saved and self._fits(saved, area):
                # Clamped, not trusted: a position saved against a screen you no
                # longer have — an unplugged monitor, a resolution change — left
                # the card drawn off the edge, invisible, with nothing to say so.
                x = min(max(saved[0], area.left()), area.right() + 1 - self.width())
                y = min(max(saved[1], area.top()), area.bottom() + 1 - self.height())
                self.move(int(x), int(y))
                return
            self._moved = False        # it cannot fit at all — back to the corner
        corner = getattr(getattr(self._config, "ui", None), "thinking_corner", "bottom-right")
        # The shadow margin is already transparent padding inside the window, so
        # it counts toward the gap from the edge — but never let it push the
        # window off the screen, which a margin smaller than the shadow would.
        m = max(0, SCREEN_MARGIN - SHADOW_MARGIN)
        x = area.left() + m if corner.endswith("left") else area.right() + 1 - self.width() - m
        y = area.top() + m if corner.startswith("top") else area.bottom() + 1 - self.height() - m
        self.move(max(area.left(), int(x)), max(area.top(), int(y)))

    # -------------------------------------------------------------- feeding

    def apply_entry(self, entry: dict) -> None:
        """Render one bus line. See assistant/trace_bus.py for the shapes."""
        kind = entry.get("kind", "trace")
        run = entry.get("run")
        if kind == "trace":
            self.panel.begin(source=entry.get("source") or "Mac")
            for step in entry.get("steps") or []:
                self.panel.add_step(step)
            self.panel.finish(entry.get("result") or {})
            self._start(run)
        elif kind == "begin":
            self.panel.begin(source=entry.get("source") or "Mac")
            self._start(run)
        elif kind == "step":
            # A trim can rewrite the file between the producer's begin and our
            # poll, so a step for a run we never saw open starts one.
            if run != self._current_run:
                self.panel.begin(source=entry.get("source") or "Mac")
                self._start(run)
            self.panel.add_step(entry.get("step") or {})
        elif kind == "result":
            if run == self._current_run:
                self.panel.finish(entry.get("result") or {})

    def _start(self, run: str | None) -> None:
        """A new run: show the card, even if the last one was closed."""
        self._current_run = run
        if not self._enabled():
            return
        self._park()
        self.setWindowOpacity(0.0)
        self.show()
        # The NSWindow only exists once shown, and macOS resets the behaviour
        # when a window is re-shown, so this is re-applied on every appearance.
        self._follow_every_space()
        # Deliberately NOT raise_(). On macOS raising a window from an app that
        # is not frontmost pulls the whole app forward, which is what made the
        # card steal the keyboard mid-sentence: you speak a command, the card
        # appears, and the next thing you type goes nowhere. WindowStaysOnTopHint
        # already keeps it above everything, so raising bought nothing and cost
        # the thing the class docstring promises.
        self._order_front_without_activating()
        self.panel.show()
        # Under the pointer already? Then the user is looking at it; otherwise
        # it settles at the idle translucency and stays out of the way.
        self._fade_to(HOVER_OPACITY if self.underMouse() else IDLE_OPACITY)

    def _enabled(self) -> bool:
        ui = getattr(self._config, "ui", None)
        return bool(getattr(ui, "show_thinking", True)) if ui else True

    # -------------------------------------------------------------- actions

    def _on_panel_closed(self) -> None:
        self._dismissed_run = self._current_run
        self.hide()

    def _on_retry(self, pending_id: int) -> None:
        """Re-run a command that was queued while the assistant was offline.

        The pipeline that can run it lives in another process, so this goes
        through the API server the phone already uses.
        """
        import threading

        def _post() -> None:
            try:
                import requests
                port = os.environ.get("MACALENDAR_API_PORT") or str(
                    getattr(getattr(self._config, "api", None), "port", 8080))
                key = getattr(getattr(self._config, "api", None), "key", None)
                requests.post(
                    f"http://127.0.0.1:{port}/pending/{pending_id}/retry",
                    headers={"X-API-Key": key} if key else {},
                    timeout=60,
                )
            except Exception as exc:
                logger.warning("Retry of pending command %s failed: %s", pending_id, exc)

        threading.Thread(target=_post, daemon=True, name="hud-retry").start()

    def _show_menu(self, pos) -> None:
        menu = QMenu(self)
        hide = QAction("Hide", menu)
        hide.triggered.connect(self._on_panel_closed)
        menu.addAction(hide)
        reset = QAction("Reset position", menu)

        def _reset() -> None:
            self._moved = False
            try:
                os.remove(STATE_PATH)
            except OSError:
                pass
            self._park()
        reset.triggered.connect(_reset)
        menu.addAction(reset)
        menu.addSeparator()
        quit_action = QAction("Quit thinking HUD", menu)
        quit_action.triggered.connect(QApplication.quit)
        menu.addAction(quit_action)
        menu.exec(QCursor.pos())

    # ---------------------------------------------------------------- theme

    def set_dark(self, dark: bool) -> None:
        if dark != self._dark:
            self._dark = dark
            self.panel.apply_theme(dark)


class _BusReader:
    """Tails the bus, and notices when config.yaml changes underneath it.

    The calendar app's Settings dialog writes the theme and the HUD's corner;
    re-reading them here is what makes those settings take effect without
    restarting a second app the user did not know they were running.
    """

    def __init__(self, hud: ThinkingHUD, config_path: str) -> None:
        self._hud = hud
        self._path = config_path
        self._offset = trace_bus.size()      # only what happens from now on
        self._cfg_mtime = self._mtime()

    def _mtime(self) -> float:
        try:
            return os.path.getmtime(self._path)
        except OSError:
            return -1.0

    def poll(self) -> None:
        entries, self._offset = trace_bus.read_since(self._offset)
        for entry in entries:
            try:
                self._hud.apply_entry(entry)
            except Exception as exc:         # a malformed line must not kill the HUD
                logger.debug("bad trace entry: %s", exc)

        m = self._mtime()
        if m != self._cfg_mtime:
            self._cfg_mtime = m
            try:
                from assistant.config import load_config
                cfg = load_config(self._path)
            except Exception:
                return
            self._hud._config = cfg
            self._hud.set_dark(cfg.theme == "dark")
            if not self._hud._enabled():
                self._hud.hide()


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Assistant thinking HUD")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s")

    try:
        from assistant.config import load_config
        config = load_config(args.config)
    except Exception as exc:
        logger.warning("Running with defaults — could not read %s: %s", args.config, exc)
        config = None

    app = QApplication(sys.argv if argv is None else [sys.argv[0]])
    # No Dock icon and no menu bar: this is an overlay, not something you
    # switch to. Best effort — without pyobjc it simply shows up in the Dock.
    try:
        from AppKit import NSApp, NSApplicationActivationPolicyAccessory
        NSApp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    except Exception:
        pass
    app.setQuitOnLastWindowClosed(False)

    hud = ThinkingHUD(config)
    reader = _BusReader(hud, args.config)
    timer = QTimer()
    timer.timeout.connect(reader.poll)
    timer.start(POLL_MS)

    logger.info("🪟 Thinking HUD listening on %s", trace_bus.BUS_PATH)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
