"""Main calendar application window."""

from __future__ import annotations

import datetime
import queue
import threading
import time
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QCloseEvent, QColor, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QDialog,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QSpinBox,
    QGridLayout,
    QLineEdit,
)

from assistant.calendar_ui import icons
from assistant.calendar_ui.agenda_view import AgendaView, DAYS_AHEAD as _AGENDA_DAYS
from assistant.calendar_ui.day_view import DayView
from assistant.calendar_ui.event_dialog import EventDialog
from assistant.calendar_ui.month_view import MonthView
from assistant.calendar_ui.sidebar import Sidebar
from assistant.calendar_ui.undo import UndoManager
import assistant.calendar_ui.styles as _styles
from assistant.calendar_ui.styles import get_app_style, BLUE, GRAY_BORDER, GRAY_DARK, GRAY_TEXT, GRAY_BG
from assistant.calendar_ui.week_view import WeekView
from assistant.calendar_ui.importer import parse_ics, scan_macos_calendar, import_events
from assistant.db import CalendarDB
from assistant.pipeline import (
    STATUS_DONE,
    STATUS_EDIT,
    STATUS_ERROR,
    STATUS_IDLE,
    STATUS_LISTENING,
    STATUS_PROCESSING,
    STATUS_REVIEW,
)

STATUS_REFRESH = "refresh"
STATUS_SWITCH_TODAY = "switch_today"
STATUS_SWITCH_TODO = "switch_todo"


def _fmt_time(time_str: str) -> str:
    """Convert '14:30' → '2:30 PM'."""
    try:
        h, m = map(int, time_str.split(":"))
        period = "AM" if h < 12 else "PM"
        h12 = h % 12 or 12
        return f"{h12}:{m:02d} {period}" if m else f"{h12} {period}"
    except Exception:
        return time_str

_MIC_ICONS = {
    STATUS_IDLE: "🎙",
    STATUS_LISTENING: "🔴",
    STATUS_REVIEW: "📨",
    STATUS_EDIT: "✏️",
    STATUS_PROCESSING: "⚙️",
    STATUS_DONE: "✅",
    STATUS_ERROR: "⚠️",
    STATUS_REFRESH: "✅",
    STATUS_SWITCH_TODAY: "✅",
    STATUS_SWITCH_TODO: "✅",
}

_MIC_OBJ_NAMES = {
    STATUS_IDLE: "mic_idle",
    STATUS_LISTENING: "mic_listening",
    STATUS_REVIEW: "mic_processing",
    STATUS_EDIT: "mic_processing",
    STATUS_PROCESSING: "mic_processing",
    STATUS_DONE: "mic_idle",
    STATUS_ERROR: "mic_idle",
    STATUS_REFRESH: "mic_idle",
    STATUS_SWITCH_TODAY: "mic_idle",
    STATUS_SWITCH_TODO: "mic_idle",
}


class ElidingLabel(QLabel):
    """QLabel that elides its text with '…' when the toolbar doesn't have
    room for it, instead of silently clipping mid-character — the plain
    QLabel used for the title bar hard-cut the Hebrew month/year suffix
    with no visual indication text was missing. The full text is always
    available via tooltip."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._full_text = ""
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

    def setText(self, text: str) -> None:  # noqa: N802 — overriding QLabel's API
        self._full_text = text
        self.setToolTip(text)
        self._update_elided()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_elided()

    def _update_elided(self) -> None:
        if not self._full_text:
            return
        fm = self.fontMetrics()
        elided = fm.elidedText(self._full_text, Qt.TextElideMode.ElideRight, self.width())
        super().setText(elided)


class ToastLabel(QLabel):
    """Brief notification that fades out after a few seconds."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            f"""
            QLabel {{
                background-color: {BLUE};
                color: white;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
            }}
            """
        )
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_message(self, text: str, duration_ms: int = 3000) -> None:
        self.setText(text)
        self.adjustSize()
        self.show()
        self._timer.start(duration_ms)


class ReviewBar(QFrame):
    """Redo / Add more / Send, shown for a few seconds after a recording stops.

    The Mac twin of the bar the iPhone floats above its mic. It never appears
    when a spoken stop word ended the recording — saying "execute" already
    settled it, so the pipeline sends without asking (see Pipeline._await_review).
    """

    chose = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        # QFrame, not QWidget: a plain QWidget subclass ignores a stylesheet
        # background, which left the bar transparent over the calendar.
        super().__init__(parent)
        self._remaining = 0
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 140))
        self.setGraphicsEffect(shadow)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(6)

        self._heard = QLabel("")
        self._heard.setMaximumWidth(320)
        lay.addWidget(self._heard)

        self._redo = QPushButton("Redo")
        self._redo.setToolTip("Throw that away and record again")
        self._more = QPushButton("Add more")
        self._more.setToolTip("Keep what you said and carry on")
        self._send = QPushButton("Send")
        self._cancel = QPushButton("×")
        self._cancel.setToolTip("Discard")
        self._cancel.setFixedWidth(26)
        for btn, choice in ((self._redo, "redo"), (self._more, "add"),
                            (self._send, "send"), (self._cancel, "cancel")):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(26)
            btn.clicked.connect(lambda _=False, c=choice: self._answer(c))
            lay.addWidget(btn)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self.hide()

    def start(self, seconds: int, heard: str) -> None:
        self._remaining = seconds
        self._heard.setText(f"“{heard}”" if heard else "")
        self._heard.setVisible(bool(heard))
        self._send.setText(f"Send {seconds}")
        self.show()
        self.adjustSize()          # after show(), so the label has its real width
        self.raise_()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def _tick(self) -> None:
        self._remaining -= 1
        # The pipeline owns the real deadline; this just counts it down on screen.
        self._send.setText(f"Send {self._remaining}" if self._remaining > 0 else "Send")

    def _answer(self, choice: str) -> None:
        self.stop()
        self.chose.emit(choice)

    def apply_theme(self, dark: bool) -> None:
        bg = _styles.D_GRAY_BG if dark else _styles.GRAY_BG
        border = _styles.D_GRAY_BORDER if dark else GRAY_BORDER
        text2 = _styles.D_GRAY_TEXT if dark else GRAY_TEXT
        accent = _styles.get_accent()
        self.setStyleSheet(
            f"ReviewBar {{ background-color: {bg}; border: 1px solid {border};"
            f" border-radius: {_styles.RADIUS_LG}px; }}"
            f"QLabel {{ color: {text2}; border: none; background: transparent; }}"
        )
        # Explicit inline styling — the app stylesheet's #primary rule has been
        # seen to apply `color` without `background-color` on nested widgets.
        self._send.setStyleSheet(
            f"QPushButton {{ background-color: {accent}; color: {_styles.on_color(accent)};"
            f" border: 1px solid {accent}; border-radius: {_styles.RADIUS_SM}px;"
            f" padding: 3px 10px; font-weight: 700; }}"
        )


def ask_transcript_edit(parent, payload_json: str) -> "str | None":
    """The gate's dialog, on its own so a test can drive it with real clicks.

    Shows the doubted transcript in an editable field. Returns the text to run
    (possibly untouched — that is a confirmation), or None for cancel.
    """
    import json as _json

    from PyQt6.QtWidgets import (
        QDialog, QDialogButtonBox, QLabel, QLineEdit, QVBoxLayout,
    )

    try:
        payload = _json.loads(payload_json or "{}")
    except ValueError:
        payload = {}
    transcript = payload.get("transcript") or ""
    words = [w for w in (payload.get("words") or []) if w]

    dlg = QDialog(parent)
    dlg.setWindowTitle("Check the transcription")
    dlg.setObjectName("transcript_edit_dialog")
    lay = QVBoxLayout(dlg)
    doubt = ", ".join(f"“{w}”" for w in words) or "some words"
    label = QLabel(f"I'm not sure I heard {doubt} right. Fix anything that's "
                   "wrong, then Send — or Send as-is if it's fine.")
    label.setWordWrap(True)
    lay.addWidget(label)
    edit = QLineEdit(transcript)
    edit.setObjectName("transcript_edit_field")
    lay.addWidget(edit)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                               | QDialogButtonBox.StandardButton.Cancel)
    buttons.setObjectName("transcript_edit_buttons")
    buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Send")
    buttons.accepted.connect(lambda: dlg.accept())
    buttons.rejected.connect(lambda: dlg.reject())
    lay.addWidget(buttons)
    edit.setFocus()

    accepted = dlg.exec() == QDialog.DialogCode.Accepted
    text = edit.text().strip()
    dlg.deleteLater()
    return text if (accepted and text) else None


class CalendarWindow(QMainWindow):
    """
    Main Outlook-style calendar window.

    Voice pipeline updates come in via pipeline.status_queue (thread-safe).
    A QTimer drains the queue on the main thread every 100ms.
    """

    # A mined new-tag proposal arrived from the API (fetched on a worker
    # thread; dialogs must run on the GUI thread, and a cross-thread signal
    # is the safe hand-off).
    _tag_suggestion_ready = pyqtSignal(dict)

    def __init__(self, pipeline=None, config=None, parent=None):
        super().__init__(parent)
        self._pipeline = pipeline
        self._config = config
        self._db = CalendarDB()
        self._current_date = datetime.date.today()
        self._view_mode = "month"  # "month" | "week" | "day" | "agenda" | "todo" | "timer" | "coursework" | "workout"
        self._undo_manager = UndoManager()

        self._dark = (config.theme == "dark") if config else False

        self.setWindowTitle("Calendar")
        self.setMinimumSize(900, 640)
        self.resize(1100, 720)

        self._build_ui()
        self._apply_theme(self._dark, show_toast=False)
        self._apply_ui_config()

        # Cmd+Z on macOS (Ctrl+Z elsewhere) — undoes the last direct UI edit
        # (create/update/delete/drag-reschedule/resize of an event). Separate
        # from the voice pipeline's own background-verification undo+redo.
        QShortcut(QKeySequence.StandardKey.Undo, self, activated=self._on_undo)
        # Shift+Cmd+Z (Ctrl+Shift+Z elsewhere) — redoes an undone action.
        QShortcut(QKeySequence.StandardKey.Redo, self, activated=self._on_redo)

        # Auto-sync todos from calendar on open if configured
        if config and config.todo.sync.auto_sync_on_open and config.todo.sync.mode != "off":
            self._db.sync_calendar_to_todos(list_name=config.todo.sync.mode)

        # Poll pipeline status queue
        if pipeline is not None:
            self._poll_timer = QTimer(self)
            self._poll_timer.setInterval(100)
            self._poll_timer.timeout.connect(self._poll_status)
            self._poll_timer.start()

        # Tag discovery (Gil, 2026-09-05): once per launch, a minute in — the
        # user is demonstrably at the app by then — ask the API whether the
        # history has earned a new tag class. All the politeness (evidence
        # bar, weekly cooldown, refusals-forever) is server-side; this client
        # only pulls and shows. See actions/todo/tag_discovery.py.
        self._tag_suggestion_ready.connect(self._on_tag_suggestion)
        QTimer.singleShot(60_000, self._fetch_tag_suggestion)

        # Changes made from the phone land in the same SQLite file via the API server;
        # pick them up without a manual refresh by watching the file's mtime.
        import os as _os
        self._db_mtime = 0.0
        try:
            self._db_mtime = _os.path.getmtime(self._db.path)
        except OSError:
            pass
        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(5000)
        self._sync_timer.timeout.connect(self._auto_refresh_if_db_changed)
        self._sync_timer.start()

        # Periodic background sync for connected calendars (ICS subscriptions +
        # two-way Outlook). Independent of the pipeline status timer above.
        self._sync_results_queue: queue.Queue = queue.Queue()
        self._sync_running = False
        self._sync_result_timer = QTimer(self)
        self._sync_result_timer.setInterval(500)
        self._sync_result_timer.timeout.connect(self._drain_sync_results)
        self._sync_result_timer.start()

        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(15 * 60 * 1000)  # 15 minutes
        self._sync_timer.timeout.connect(self._start_background_sync)
        self._sync_timer.start()
        # Kick off one sync shortly after launch so connected calendars show
        # up without waiting a full 15 minutes.
        QTimer.singleShot(5000, self._start_background_sync)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Standard window close event — keeps persistence."""
        event.accept()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_toolbar())

        # Splitter: sidebar | main view
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)

        self._sidebar = Sidebar()
        self._sidebar.new_event_clicked.connect(self._on_new_event)
        self._sidebar.date_selected.connect(self._on_sidebar_date)
        splitter.addWidget(self._sidebar)

        # Stacked: month / week / day / todo / timer
        from assistant.calendar_ui.todo_view import TodoView
        from assistant.calendar_ui.timer_view import TimerView as _TimerView
        from assistant.calendar_ui.coursework_view import CourseworkView as _CourseworkView
        from assistant.calendar_ui.workout_view import WorkoutView as _WorkoutView
        self._stack = QStackedWidget()
        self._month_view = MonthView(self._db)
        self._week_view = WeekView(self._db)
        self._day_view = DayView(self._db)
        self._agenda_view = AgendaView(self._db)
        self._todo_view = TodoView(self._db, config=self._config)
        self._timer_view = _TimerView(self._db)
        self._coursework_view = _CourseworkView(self._db, dark=self._dark)
        self._workout_view = _WorkoutView(self._db)
        self._stack.addWidget(self._month_view)
        self._stack.addWidget(self._week_view)
        self._stack.addWidget(self._day_view)
        self._stack.addWidget(self._agenda_view)
        self._stack.addWidget(self._todo_view)
        self._stack.addWidget(self._timer_view)
        self._stack.addWidget(self._coursework_view)
        self._stack.addWidget(self._workout_view)
        self._month_view.date_selected.connect(self._on_day_selected)
        self._month_view.date_double_clicked.connect(self._on_day_double_clicked)
        self._month_view.event_clicked.connect(self._on_event_clicked)
        self._week_view.datetime_double_clicked.connect(self._on_datetime_double_clicked)
        self._week_view.event_clicked.connect(self._on_event_clicked)
        self._day_view.datetime_double_clicked.connect(self._on_datetime_double_clicked)
        self._day_view.event_clicked.connect(self._on_event_clicked)
        self._agenda_view.event_clicked.connect(self._on_event_clicked)
        self._day_view.briefing_requested.connect(self._on_briefing_requested)
        self._month_view.event_rescheduled.connect(self._on_event_rescheduled)
        self._week_view.event_rescheduled.connect(self._on_event_rescheduled)
        self._day_view.event_rescheduled.connect(self._on_event_rescheduled)
        splitter.addWidget(self._stack)

        splitter.setSizes([200, 900])
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, stretch=1)

        # Toast notification (overlaid)
        self._toast = ToastLabel(central)
        self._toast.raise_()

        # Redo / Add more / Send bar (overlaid) — the desktop twin of the chip
        # the iPhone floats over its mic after a recording stops.
        self._review_bar = ReviewBar(central)
        self._review_bar.chose.connect(self._on_review_choice)
        self._review_bar.hide()

        self._update_title()

    def _build_toolbar(self) -> QWidget:
        from PyQt6.QtWidgets import QFrame
        bar = QWidget()
        self._toolbar_bar = bar
        bar.setFixedHeight(54)
        bar.setStyleSheet(f"background-color: {GRAY_BG}; border-bottom: 1px solid {GRAY_BORDER};")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(2)
        # Every widget below is added with AlignVCenter explicitly — mixed
        # fixed-height buttons, an auto-height label, and spacer items in
        # one row previously let some drift toward the top of the bar
        # instead of sitting centered in the available 30px content height.
        v_center = Qt.AlignmentFlag.AlignVCenter

        # ── Group 1: nav arrows ──────────────────────────────────────
        prev_btn = QPushButton("‹")
        prev_btn.setObjectName("nav")
        prev_btn.setFixedSize(28, 28)
        prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        prev_btn.clicked.connect(self._on_prev)
        layout.addWidget(prev_btn, alignment=v_center)

        next_btn = QPushButton("›")
        next_btn.setObjectName("nav")
        next_btn.setFixedSize(28, 28)
        next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        next_btn.clicked.connect(self._on_next)
        layout.addWidget(next_btn, alignment=v_center)

        layout.addSpacing(4)

        today_btn = QPushButton("Today")
        today_btn.setObjectName("flat")
        today_btn.setFixedHeight(30)
        today_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        today_btn.clicked.connect(self._on_today)
        layout.addWidget(today_btn, alignment=v_center)

        layout.addSpacing(6)
        self._search_box = QLineEdit()
        self._search_box.setObjectName("toolbar_search")
        self._search_box.setPlaceholderText("Search, or a date…")
        self._search_box.setFixedSize(180, 30)
        self._search_box.setClearButtonEnabled(True)
        self._search_box.returnPressed.connect(lambda: self._on_search())
        layout.addWidget(self._search_box, alignment=v_center)

        # ── Title ────────────────────────────────────────────────────
        layout.addSpacing(6)
        self._title_label = ElidingLabel()
        self._title_label.setObjectName("month_title")
        font = QFont()
        font.setPointSize(15)
        font.setWeight(QFont.Weight.DemiBold)
        self._title_label.setFont(font)
        layout.addWidget(self._title_label, alignment=v_center)

        layout.addStretch()

        # ── Group 2: view toggle tabs ────────────────────────────────
        for label, mode in [("Month", "month"), ("Week", "week"), ("Day", "day"), ("Agenda", "agenda"), ("Tasks", "todo"), ("Timer", "timer"), ("Coursework", "coursework"), ("Workout", "workout")]:
            btn = QPushButton(label)
            btn.setObjectName("seg_btn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(30)
            btn.clicked.connect(lambda _, m=mode: self._set_view(m))
            if self._config and mode in ("coursework", "timer", "workout"):
                btn.setVisible(getattr(self._config.ui, f"show_{mode}", True))
            layout.addWidget(btn, alignment=v_center)
            setattr(self, f"_view_btn_{mode}", btn)
            # Styled by _apply_theme(), always called right after _build_ui()
            # in __init__ — no need to style twice here.

        # ── Separator ────────────────────────────────────────────────
        layout.addSpacing(8)
        sep = QFrame()
        self._toolbar_sep = sep
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedHeight(22)
        sep.setStyleSheet(f"color: {GRAY_BORDER};")
        layout.addWidget(sep, alignment=v_center)
        layout.addSpacing(6)

        # ── Group 3: tools ───────────────────────────────────────────
        import_btn = QPushButton("Import")
        import_btn.setObjectName("flat")
        import_btn.setFixedHeight(30)
        import_btn.setToolTip("Import events from an .ics file or macOS Calendar")
        import_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        import_btn.clicked.connect(self._on_import)
        layout.addWidget(import_btn, alignment=v_center)

        connected_btn = QPushButton("🔗")
        connected_btn.setObjectName("icon_btn")
        connected_btn.setFixedSize(30, 30)
        connected_btn.setToolTip("Connected Calendars — Gmail/Outlook/iCloud subscribe by link or connect Outlook")
        connected_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        connected_btn.clicked.connect(self._on_connected_calendars)
        layout.addWidget(connected_btn, alignment=v_center)

        tag_history_btn = QPushButton("🏷")
        tag_history_btn.setObjectName("icon_btn")
        tag_history_btn.setFixedSize(30, 30)
        tag_history_btn.setToolTip("Tag Suggestion History — review, reverse or hide "
                                   "past tag suggestions")
        tag_history_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        tag_history_btn.clicked.connect(self._on_tag_history)
        layout.addWidget(tag_history_btn, alignment=v_center)

        self._settings_btn = QPushButton("⚙")
        self._settings_btn.setObjectName("icon_btn")
        self._settings_btn.setFixedSize(30, 30)
        self._settings_btn.setToolTip("Assistant Settings")
        self._settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._settings_btn.clicked.connect(self._on_settings_popup)
        layout.addWidget(self._settings_btn, alignment=v_center)

        self._theme_btn = QPushButton("○")
        self._theme_btn.setObjectName("icon_btn")
        self._theme_btn.setFixedSize(30, 30)
        self._theme_btn.setToolTip("Toggle dark / light mode")
        self._theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._theme_btn.clicked.connect(self._on_toggle_theme)
        layout.addWidget(self._theme_btn, alignment=v_center)
        self._update_theme_btn()

        layout.addSpacing(2)

        self._mic_btn = QPushButton("🎙")
        self._mic_btn.setObjectName("mic_idle")
        self._mic_btn.setFixedSize(30, 30)
        self._mic_btn.setToolTip("Click or press Ctrl+J to toggle the microphone")
        self._mic_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if self._pipeline is not None:
            self._mic_btn.clicked.connect(self._pipeline.trigger)
        layout.addWidget(self._mic_btn, alignment=v_center)

        return bar

    def _style_seg_btn(self, btn: QPushButton, active: bool) -> None:
        # Always set a complete inline stylesheet for both states rather than
        # toggling the `[active="true"]` dynamic-property selector or ever
        # clearing back to "": PyQt6's QSS engine was observed to only apply
        # part of a rule (e.g. `color` but not `background-color`) after
        # unpolish()/polish(), AND separately to only partially revert a
        # previous inline override when cleared with setStyleSheet("":) —
        # in both cases leaving stale, mismatched paint state on whichever
        # button last changed. Explicitly stating every property for both
        # states every time avoids relying on any cache invalidation.
        dark = self._dark
        text2 = _styles.D_GRAY_TEXT if dark else GRAY_TEXT
        text = _styles.D_GRAY_DARK if dark else GRAY_DARK
        hover = _styles.D_GRAY_LIGHT if dark else _styles.GRAY_LIGHT
        if active:
            btn.setStyleSheet(
                f"QPushButton#seg_btn {{ background-color: {_styles.BLUE}; "
                f"color: {_styles.ON_ACCENT}; font-weight: 700; border: none; }}"
            )
        else:
            btn.setStyleSheet(
                f"QPushButton#seg_btn {{ background-color: transparent; color: {text2}; "
                f"font-weight: 500; border: none; }}"
                f"QPushButton#seg_btn:hover {{ background-color: {hover}; color: {text}; }}"
            )
        btn.setProperty("active", active)

    def _update_theme_btn(self) -> None:
        # Show the icon for what the mode will switch TO
        self._theme_btn.setText("☀" if self._dark else "☾")
        self._theme_btn.setToolTip("Switch to light mode" if self._dark else "Switch to dark mode")

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _on_prev(self) -> None:
        if self._view_mode in ("todo", "timer", "coursework", "workout"):
            return
        if self._view_mode == "month":
            d = self._current_date.replace(day=1) - datetime.timedelta(days=1)
            self._current_date = d.replace(day=1)
        elif self._view_mode in ("week", "agenda"):
            self._current_date -= datetime.timedelta(weeks=1)
        else:  # day
            self._current_date -= datetime.timedelta(days=1)
        self._navigate()

    def _on_next(self) -> None:
        if self._view_mode in ("todo", "timer", "coursework", "workout"):
            return
        if self._view_mode == "month":
            d = self._current_date.replace(day=28) + datetime.timedelta(days=4)
            self._current_date = d.replace(day=1)
        elif self._view_mode in ("week", "agenda"):
            self._current_date += datetime.timedelta(weeks=1)
        else:  # day
            self._current_date += datetime.timedelta(days=1)
        self._navigate()

    def _on_today(self) -> None:
        self._current_date = datetime.date.today()
        self._navigate()

    def _on_sidebar_date(self, date: datetime.date) -> None:
        self._current_date = date
        self._navigate()

    # ── Toolbar search: find events/tasks, or jump straight to a date ────

    @staticmethod
    def _parse_jump_date(q: str) -> "datetime.date | None":
        """'2026-10-14', '14/10' or '14/10/2026' → that date; else None."""
        try:
            return datetime.date.fromisoformat(q)
        except ValueError:
            pass
        parts = q.split("/")
        if len(parts) in (2, 3) and all(p.isdigit() for p in parts):
            try:
                day, month = int(parts[0]), int(parts[1])
                year = int(parts[2]) if len(parts) == 3 else datetime.date.today().year
                if year < 100:
                    year += 2000
                return datetime.date(year, month, day)
            except ValueError:
                return None
        return None

    def _on_search(self) -> None:
        q = self._search_box.text().strip()
        if not q:
            return
        jump = self._parse_jump_date(q)
        if jump is not None:
            self._search_box.clear()
            if self._view_mode not in ("month", "week", "day", "agenda"):
                self._set_view("day")
            self._current_date = jump
            self._navigate()
            return
        if len(q) < 2:
            return
        events = self._db.search_events(q, limit=10)
        todos = self._db.search_todos(q, limit=6)
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self._search_box)
        if not events and not todos:
            menu.addAction("No matches").setEnabled(False)
        for e in events:
            act = menu.addAction(f"{e['date']} {e['start_time']}  ·  {e['title'][:44]}")
            act.triggered.connect(
                lambda _, d=e["date"]: self._on_search_pick_event(d))
        if events and todos:
            menu.addSeparator()
        for t in todos:
            mark = "✓ " if t.get("completed") else ""
            act = menu.addAction(f"task  ·  {mark}{t['title'][:44]}")
            act.triggered.connect(lambda _: self._set_view("todo"))
        menu.exec(self._search_box.mapToGlobal(
            self._search_box.rect().bottomLeft()))

    def _on_search_pick_event(self, date_str: str) -> None:
        self._search_box.clear()
        if self._view_mode not in ("month", "week", "day", "agenda"):
            self._set_view("day")
        self._current_date = datetime.date.fromisoformat(date_str)
        self._navigate()

    def _on_day_selected(self, date: datetime.date) -> None:
        self._current_date = date
        self._update_title()

    def _navigate(self) -> None:
        if self._view_mode in ("todo", "timer", "coursework", "workout"):
            self._update_title()
            return
        if self._view_mode == "month":
            self._month_view.navigate(self._current_date.year, self._current_date.month)
        elif self._view_mode == "week":
            week_start = self._current_date - datetime.timedelta(days=(self._current_date.weekday() + 1) % 7)
            self._week_view.navigate(week_start)
        elif self._view_mode == "agenda":
            self._agenda_view.set_start_date(self._current_date)
        else:  # day
            self._day_view.navigate(self._current_date)
        self._update_title()

    def _set_view(self, mode: str) -> None:
        self._view_mode = mode
        widget = {
            "month":      self._month_view,
            "week":       self._week_view,
            "day":        self._day_view,
            "agenda":     self._agenda_view,
            "todo":       self._todo_view,
            "timer":      self._timer_view,
            "coursework": self._coursework_view,
            "workout":    self._workout_view,
        }.get(mode, self._month_view)
        self._stack.setCurrentWidget(widget)
        for m in ("month", "week", "day", "agenda", "todo", "timer", "coursework", "workout"):
            btn = getattr(self, f"_view_btn_{m}", None)
            if btn:
                self._style_seg_btn(btn, m == mode)
        # Keep pipeline context-aware of current view for voice routing
        if self._pipeline is not None:
            self._pipeline.current_view = mode
            if mode == "todo":
                self._mic_btn.setToolTip(
                    "Tasks mode — voice commands will create/manage tasks\n"
                    "Click or press Ctrl+J to speak"
                )
            else:
                self._mic_btn.setToolTip(
                    "Click or press Ctrl+J to toggle the microphone"
                )
        self._navigate()

    def _title_with_hebrew(self, base: str, representative_date: datetime.date) -> str:
        """Append/replace *base* with the Hebrew month+year per the configured
        display mode. Uses a single representative date (not every visible
        day) since the Hebrew month+year would otherwise repeat redundantly
        across a whole month/week grid."""
        mode = self._config.hebrew_calendar.display_mode if self._config else "english"
        if mode == "english":
            return base
        from assistant.hebrew_calendar import hebrew_month_year_string
        heb = hebrew_month_year_string(representative_date)
        return heb if mode == "hebrew" else f"{base}   ·   {heb}"

    def _update_title(self) -> None:
        if self._view_mode == "timer":
            self._title_label.setText("Timer")
            return
        if self._view_mode == "coursework":
            self._title_label.setText("Coursework")
            return
        if self._view_mode == "workout":
            self._title_label.setText("Workout")
            return
        if self._view_mode == "todo":
            self._title_label.setText("Tasks")
        elif self._view_mode == "month":
            base = self._current_date.strftime("%B %Y")
            # Mid-month as the representative date — the 1st can fall right
            # at a Hebrew month boundary and misrepresent most of the grid.
            mid = self._current_date.replace(day=15)
            self._title_label.setText(self._title_with_hebrew(base, mid))
        elif self._view_mode == "week":
            week_start = self._current_date - datetime.timedelta(days=(self._current_date.weekday() + 1) % 7)
            week_end = week_start + datetime.timedelta(days=6)
            if week_start.month == week_end.month:
                base = f"{week_start.strftime('%B %-d')} – {week_end.day}, {week_end.year}"
            else:
                base = f"{week_start.strftime('%b %-d')} – {week_end.strftime('%b %-d, %Y')}"
            mid = week_start + datetime.timedelta(days=3)
            self._title_label.setText(self._title_with_hebrew(base, mid))
        elif self._view_mode == "agenda":
            start = self._current_date
            end = start + datetime.timedelta(days=_AGENDA_DAYS - 1)
            if start.month == end.month:
                base = f"{start.strftime('%B %-d')} – {end.day}, {end.year}"
            else:
                base = f"{start.strftime('%b %-d')} – {end.strftime('%b %-d, %Y')}"
            mid = start + datetime.timedelta(days=_AGENDA_DAYS // 2)
            self._title_label.setText(self._title_with_hebrew(base, mid))
        else:  # day
            base = self._current_date.strftime("%A, %B %-d, %Y")
            self._title_label.setText(self._title_with_hebrew(base, self._current_date))

    # ------------------------------------------------------------------
    # Event actions
    # ------------------------------------------------------------------

    def _on_undo(self) -> None:
        desc = self._undo_manager.undo()
        if desc:
            self.refresh_calendar()
            self.show_toast(f"Undid: {desc}")
        else:
            self.show_toast("Nothing to undo")

    def _on_redo(self) -> None:
        desc = self._undo_manager.redo()
        if desc:
            self.refresh_calendar()
            self.show_toast(f"Redid: {desc}")
        else:
            self.show_toast("Nothing to redo")

    @staticmethod
    def _event_content_fields(event: dict) -> dict:
        """Strip an event dict down to the fields create/update accept —
        excludes id/series_id/source/timestamps so a recreate never
        accidentally regenerates a whole series or collides on id.
        Includes recurrence/recurrence_end so an undo that reverts a
        recurring-vs-not change restores the field, not just the visible
        title/date/time — see the promotion guard in _on_event_clicked for
        why promoting to a series is excluded from the undo stack entirely
        rather than relying on this alone."""
        keys = ("title", "date", "start_time", "end_time", "attendees",
                "location", "description", "color", "recurrence", "recurrence_end")
        return {k: event.get(k, "") for k in keys}

    def _create_event_and_refresh(self, dialog: EventDialog) -> None:
        data = dict(dialog.event_data)
        title = data.get("title", "event")
        is_recurring = bool(data.get("recurrence"))
        # Mutable holder: redo re-creates the row under a NEW id each time,
        # so undo (which deletes "the current copy") must always read the
        # latest id rather than one frozen at push() time.
        id_holder = {"id": self._db.create_event_from_dict(data)}

        def undo():
            # A recurring create generates a whole series (create_event_from_dict
            # -> _create_series_instances) — delete_event alone would only remove
            # the root and re-root the series to the next instance, leaving the
            # rest behind. delete_series removes every generated instance.
            if is_recurring:
                self._db.delete_series(id_holder["id"])
            else:
                self._db.delete_event(id_holder["id"])

        def redo():
            id_holder["id"] = self._db.create_event_from_dict(data)

        self._undo_manager.push(f'Create "{title}"', undo, redo)
        self.refresh_calendar()

    def _on_new_event(self, default_date: Optional[datetime.date] = None) -> None:
        dialog = EventDialog(self, default_date=default_date or self._current_date, db=self._db)
        if dialog.exec() and dialog.event_data:
            self._create_event_and_refresh(dialog)

    def _on_day_double_clicked(self, date: datetime.date) -> None:
        self._on_new_event(default_date=date)

    def _on_datetime_double_clicked(self, dt: datetime.datetime) -> None:
        dialog = EventDialog(self, default_date=dt.date(), default_time=dt.time(), db=self._db)
        if dialog.exec() and dialog.event_data:
            self._create_event_and_refresh(dialog)

    def _on_event_clicked(self, event: dict) -> None:
        dialog = EventDialog(self, event=event, db=self._db)
        if dialog.exec():
            ev_id = event.get("id")
            series_id = event.get("series_id")

            if dialog.delete_series_requested and series_id:
                # Series-wide delete isn't captured for undo (would require
                # snapshotting every instance) — Cmd+Z after this reaches
                # further back to the last undoable action instead.
                count = self._db.delete_series(series_id)
                self.refresh_calendar()
                self.show_toast(f"Deleted {count} events in series")
            elif dialog.delete_requested and ev_id:
                restore_data = self._event_content_fields(event)
                # If this instance belonged to a series, it inherited that
                # series' recurrence/recurrence_end fields too — but restoring
                # it via create_event_from_dict() treats a non-empty
                # recurrence as "generate a brand new series", which would
                # spawn a second, parallel series of future instances rather
                # than just bringing back this one deleted occurrence. Clear
                # it so undo restores the row's content without side effects;
                # the restored instance just won't carry its old series
                # membership/badge — same "series identity isn't fully
                # undoable" boundary already accepted for the other cases above.
                if event.get("series_id"):
                    restore_data["recurrence"] = ""
                    restore_data["recurrence_end"] = ""
                id_holder = {"id": ev_id}
                self._db.delete_event(id_holder["id"])

                def undo():
                    id_holder["id"] = self._db.create_event_from_dict(restore_data)

                def redo():
                    self._db.delete_event(id_holder["id"])

                self._undo_manager.push(f'Delete "{event["title"]}"', undo, redo)
                self.refresh_calendar()
                self.show_toast(f"Deleted \"{event['title']}\"")
            elif dialog.duplicate_requested and ev_id:
                copy_data = self._event_content_fields(event)
                # A duplicated series instance becomes a one-off: a non-empty
                # recurrence in create_event_from_dict() would spawn a whole
                # second series (same boundary as undo-restore above).
                copy_data["recurrence"] = ""
                copy_data["recurrence_end"] = ""
                id_holder = {"id": self._db.create_event_from_dict(copy_data)}

                def undo_dup():
                    self._db.delete_event(id_holder["id"])

                def redo_dup():
                    id_holder["id"] = self._db.create_event_from_dict(copy_data)

                self._undo_manager.push(f'Duplicate "{event["title"]}"',
                                        undo_dup, redo_dup)
                self.refresh_calendar()
                self.show_toast(f"Duplicated \"{event['title']}\"")
            elif dialog.event_data:
                ev_id = dialog.event_data.pop("id", None)
                series_id = dialog.event_data.pop("series_id", None)

                if ev_id:
                    if series_id:
                        msg = QMessageBox(self)
                        msg.setWindowTitle("Update Recurring Event")
                        msg.setText("This is a repeating event.")
                        msg.setInformativeText("Do you want to update only this instance, or the entire series?")
                        btn_only_this = msg.addButton("Only this instance", QMessageBox.ButtonRole.ActionRole)
                        btn_series = msg.addButton("Entire series", QMessageBox.ButtonRole.AcceptRole)
                        msg.addButton(QMessageBox.StandardButton.Cancel)
                        msg.setDefaultButton(btn_only_this)
                        msg.exec()

                        if msg.clickedButton() == btn_only_this:
                            before = self._event_content_fields(event)
                            after = dict(dialog.event_data)
                            self._db.update_event(ev_id, **after)
                            self._undo_manager.push(
                                f'Update "{after["title"]}"',
                                lambda: self._db.update_event(ev_id, **before),
                                lambda: self._db.update_event(ev_id, **after),
                            )
                            self.refresh_calendar()
                            self.show_toast(f"Updated this instance of \"{dialog.event_data['title']}\"")
                        elif msg.clickedButton() == btn_series:
                            # Series-wide update isn't captured for undo either.
                            self._db.update_series(series_id, ev_id, **dialog.event_data)
                            self.refresh_calendar()
                            self.show_toast(f"Updated series \"{dialog.event_data['title']}\"")
                    else:
                        before = self._event_content_fields(event)
                        after = dict(dialog.event_data)
                        promotes_to_series = bool(after.get("recurrence")) and not before.get("recurrence")
                        self._db.update_event(ev_id, **after)
                        # If recurrence was added to a previously non-recurring event,
                        # promote it to a series root and generate future instances.
                        if after.get("recurrence"):
                            self._db.promote_to_series(ev_id)
                        if promotes_to_series:
                            # Reverting update_event alone wouldn't clean up the
                            # series instances promote_to_series just generated —
                            # same undo boundary as the series-wide branches above:
                            # don't push a record that would silently under-undo.
                            pass
                        else:
                            self._undo_manager.push(
                                f'Update "{after["title"]}"',
                                lambda: self._db.update_event(ev_id, **before),
                                lambda: self._db.update_event(ev_id, **after),
                            )
                        self.refresh_calendar()
                        self.show_toast(f"Updated \"{dialog.event_data['title']}\"")

    def _on_event_rescheduled(self, event_id: int, updates: dict) -> None:
        event = self._db.get_event(event_id)
        if event and self._db.is_event_locked(event):
            self.refresh_calendar()  # snap the drag back to its DB position
            self.show_toast("This event is read-only and can't be moved")
            return
        if "start_time" in updates and "end_time" not in updates:
            if event:
                try:
                    orig_sh, orig_sm = map(int, event["start_time"].split(":"))
                    orig_eh, orig_em = map(int, event["end_time"].split(":"))
                    duration_min = (orig_eh * 60 + orig_em) - (orig_sh * 60 + orig_sm)
                    if duration_min > 0:
                        new_sh, new_sm = map(int, updates["start_time"].split(":"))
                        end_min = min(new_sh * 60 + new_sm + duration_min, 23 * 60 + 59)
                        updates["end_time"] = f"{end_min // 60:02d}:{end_min % 60:02d}"
                except Exception:
                    pass
        if event:
            before = {k: event.get(k, "") for k in ("date", "start_time", "end_time")}
            after = dict(updates)
            self._undo_manager.push(
                f'Move "{event["title"]}"',
                lambda: self._db.update_event(event_id, **before),
                lambda: self._db.update_event(event_id, **after),
            )
        self._db.update_event(event_id, **updates)
        self.refresh_calendar()
        action = "Event resized" if ("start_time" in updates and "end_time" in updates) else "Event moved"
        self.show_toast(action)

    # ------------------------------------------------------------------
    # Voice assistant integration
    # ------------------------------------------------------------------

    def _poll_status(self) -> None:
        import time as _t
        if _t.time() - getattr(self, "_last_beat", 0) > 5:
            self._last_beat = _t.time()
            try:
                from assistant.heartbeat import beat
                beat("gui")
            except Exception:
                pass
        """Drain pipeline.status_queue on the main thread (called by QTimer)."""
        if self._pipeline is None:
            return
        try:
            while True:
                item = self._pipeline.status_queue.get_nowait()
                # Pipeline now sends (status, message) tuples
                if isinstance(item, tuple):
                    status, message = item
                else:
                    status, message = item, ""
                self._handle_status(status, message)
        except queue.Empty:
            pass

    def _fetch_tag_suggestion(self) -> None:
        import json as _json
        import threading
        import urllib.request

        def _work() -> None:
            try:
                port = getattr(getattr(self._config, "api", None), "port", 8080)
                req = urllib.request.Request(f"http://127.0.0.1:{port}/tags/suggestion")
                key = getattr(getattr(self._config, "api", None), "key", None)
                if key:
                    req.add_header("X-API-Key", key)
                with urllib.request.urlopen(req, timeout=5) as r:
                    c = _json.loads(r.read().decode())
                if c and c.get("name"):
                    self._tag_suggestion_ready.emit(c)
            except Exception:
                pass                      # a quiet feature: never bother anyone

        threading.Thread(target=_work, daemon=True, name="tag-suggest").start()

    def _on_tag_suggestion(self, c: dict) -> None:
        from PyQt6.QtWidgets import QMessageBox
        samples = "\n  • ".join(c.get("samples") or [])
        box = QMessageBox(self)
        box.setWindowTitle("New tag idea")
        box.setText(f"Add “{c['name']}” as a tag?")
        box.setInformativeText(
            f"{c.get('evidence', '?')} of your tasks share this theme and no "
            f"existing tag covers them, e.g.:\n  • {samples}\n\n"
            "You can review or reverse this later in the tag history.")
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        accept = box.exec() == QMessageBox.StandardButton.Yes

        import json as _json
        import threading
        import urllib.request

        def _post() -> None:
            try:
                port = getattr(getattr(self._config, "api", None), "port", 8080)
                req = urllib.request.Request(
                    f"http://127.0.0.1:{port}/tags/suggestion/answer",
                    data=_json.dumps({"name": c["name"], "accept": accept}).encode(),
                    headers={"Content-Type": "application/json"}, method="POST")
                key = getattr(getattr(self._config, "api", None), "key", None)
                if key:
                    req.add_header("X-API-Key", key)
                urllib.request.urlopen(req, timeout=5).read()
            except Exception:
                pass

        threading.Thread(target=_post, daemon=True, name="tag-suggest-answer").start()

    def _on_review_choice(self, choice: str) -> None:
        """Redo / Add more / Send / Cancel from the review bar."""
        if self._pipeline is not None:
            self._pipeline.review_choice(choice)

    def _position_review_bar(self) -> None:
        """Just above the mic button, right-aligned like the iPhone's chip."""
        bar = getattr(self, "_review_bar", None)
        if bar is None or not bar.isVisible():
            return
        parent = bar.parentWidget()
        bar.adjustSize()
        x = max(8, parent.width() - bar.width() - 16)
        bar.move(x, 58)
        bar.raise_()

    def _handle_status(self, status: str, message: str = "") -> None:
        icon = _MIC_ICONS.get(status, "🎙")
        obj_name = _MIC_OBJ_NAMES.get(status, "mic_idle")
        self._mic_btn.setText(icon)
        self._mic_btn.setObjectName(obj_name)
        self._mic_btn.style().unpolish(self._mic_btn)
        self._mic_btn.style().polish(self._mic_btn)

        if status == STATUS_REVIEW:
            # The message is "<seconds>|<transcript snippet>" for the review bar,
            # which shows the transcript itself — so no toast (it was leaking the
            # raw "3|add lunch…" string across the bottom of the window).
            secs, _, snippet = message.partition("|")
            self._review_bar.start(int(secs or 3), snippet)
            self._position_review_bar()
            return
        self._review_bar.stop()

        if status == STATUS_EDIT:
            # The message is a JSON payload, not a toast: the engine's gate is
            # holding execution until the doubted words are checked.
            self._show_transcript_edit(message)
            return

        if message:
            self.show_toast(message)

        if status == STATUS_REFRESH:
            self.refresh_calendar()
            self.refresh_todos()
        elif status == STATUS_SWITCH_TODAY:
            self._current_date = datetime.date.today()
            self._set_view("day")
        elif status == STATUS_SWITCH_TODO:
            self._set_view("todo")
            self.refresh_todos()

    def _show_transcript_edit(self, payload_json: str) -> None:
        """The engine's transcript gate: show what was heard, let the speaker
        fix it, and hand the verdict back to the pipeline's worker thread.
        Sending it back untouched is itself an answer (a confirmation the
        server counts toward whitelisting the word)."""
        verdict = ask_transcript_edit(self, payload_json)
        if self._pipeline is not None:
            self._pipeline.submit_transcript_edit(verdict)

    def _auto_refresh_if_db_changed(self) -> None:
        import os as _os
        try:
            m = _os.path.getmtime(self._db.path)
        except OSError:
            return
        if m != self._db_mtime:
            self._db_mtime = m
            self.refresh_todos()   # refreshes calendar views too
            tv = getattr(self, "_timer_view", None)
            if tv is not None:
                try:
                    tv.reload()    # timers started/stopped from the phone
                except Exception:
                    pass

    def refresh_calendar(self) -> None:
        """Reload events from DB in all calendar views."""
        self._month_view.refresh()
        self._week_view.refresh()
        self._day_view.refresh()
        self._agenda_view.refresh()

    def refresh_todos(self) -> None:
        """Reload todos from DB in the TodoView and calendar (for deadline pills)."""
        if hasattr(self, "_todo_view"):
            self._todo_view.refresh()
        self.refresh_calendar()

    def show_toast(self, message: str) -> None:
        self._toast.show_message(message)
        # Centre the toast at the bottom of the window
        self._toast.adjustSize()
        x = (self.width() - self._toast.width()) // 2
        y = self.height() - self._toast.height() - 24
        self._toast.move(x, y)

    # ------------------------------------------------------------------
    # Resize: keep toast centred
    # ------------------------------------------------------------------

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_review_bar"):
            self._position_review_bar()
        if hasattr(self, "_toast"):
            self._toast.adjustSize()
            x = (self.width() - self._toast.width()) // 2
            y = self.height() - self._toast.height() - 24
            self._toast.move(x, y)

    # ------------------------------------------------------------------
    # Dark mode
    # ------------------------------------------------------------------

    def _on_toggle_theme(self) -> None:
        self._dark = not self._dark
        self._apply_theme(self._dark, show_toast=True)

    def _apply_theme(self, dark: bool, show_toast: bool = False) -> None:
        accent = self._config.ui.accent_color if self._config else None
        self.setStyleSheet(get_app_style(dark, accent))
        self._month_view.apply_theme(dark)
        self._week_view.apply_theme(dark)
        self._day_view.apply_theme(dark)
        self._agenda_view.apply_theme(dark)
        self._sidebar.apply_theme(dark)
        if hasattr(self, "_todo_view"):
            self._todo_view.apply_theme(dark)
        if hasattr(self, "_timer_view"):
            self._timer_view.apply_theme(dark)
        if hasattr(self, "_coursework_view"):
            self._coursework_view.apply_theme(dark)
        if hasattr(self, "_workout_view"):
            self._workout_view.apply_theme(dark)
        if hasattr(self, "_review_bar"):
            self._review_bar.apply_theme(dark)

        # Re-style toolbar
        bg = _styles.D_GRAY_BG if dark else _styles.GRAY_BG
        border = _styles.D_GRAY_BORDER if dark else GRAY_BORDER
        if hasattr(self, "_toolbar_bar"):
            self._toolbar_bar.setStyleSheet(
                f"background-color: {bg}; border-bottom: 1px solid {border};"
            )
        if hasattr(self, "_toolbar_sep"):
            self._toolbar_sep.setStyleSheet(f"color: {border};")
        # Re-apply segmented button styling (colors depend on theme + accent)
        for m in ("month", "week", "day", "agenda", "todo", "timer", "coursework", "workout"):
            btn = getattr(self, f"_view_btn_{m}", None)
            if btn:
                self._style_seg_btn(btn, m == self._view_mode)
        self._update_theme_btn()
        if show_toast:
            self.show_toast("Dark mode on" if dark else "Light mode on")

    def _apply_ui_config(self) -> None:
        """Apply font sizes and other UI constants from config."""
        ui = self._config.ui
        self._month_view.apply_ui_config(ui)
        self._week_view.apply_ui_config(ui)
        self._day_view.apply_ui_config(ui)
        self._agenda_view.apply_ui_config(ui)
        if hasattr(self, "_todo_view"):
            self._todo_view.apply_ui_config(ui)
        if hasattr(self, "_timer_view"):
            self._timer_view.apply_ui_config(ui)
        if hasattr(self, "_coursework_view"):
            self._coursework_view.apply_ui_config(ui)
        if hasattr(self, "_workout_view"):
            self._workout_view.apply_ui_config(ui)
        hebrew = self._config.hebrew_calendar
        self._month_view.apply_hebrew_config(hebrew)
        self._week_view.apply_hebrew_config(hebrew)
        self._day_view.apply_hebrew_config(hebrew)
        self._agenda_view.apply_hebrew_config(hebrew)
        self._update_title()
        self.refresh_calendar()

    def _on_briefing_requested(self) -> None:
        """Query today's events and read them aloud via TTS."""
        import threading as _threading
        events = self._db.get_events_for_day(datetime.date.today())
        events = sorted(events, key=lambda e: e.get("start_time", ""))
        n = len(events)

        if n == 0:
            summary = "Your schedule is clear today. Nothing planned."
        elif n == 1:
            ev = events[0]
            t = _fmt_time(ev.get("start_time", ""))
            summary = f"You have one event today: {ev['title']} at {t}."
        else:
            parts = [f"{ev['title']} at {_fmt_time(ev.get('start_time', ''))}" for ev in events]
            if len(parts) == 2:
                schedule = f"{parts[0]} and {parts[1]}"
            else:
                schedule = ", ".join(parts[:-1]) + f", and {parts[-1]}"
            summary = f"You have {n} events today: {schedule}."

        self.show_toast(summary[:80])
        if self._pipeline:
            _threading.Thread(
                target=lambda: self._pipeline._tts.speak(summary), daemon=True
            ).start()

    def _on_settings_popup(self) -> None:
        from assistant.calendar_ui.settings_dialog import open_settings
        open_settings(self)

    def _on_tag_history(self) -> None:
        from assistant.calendar_ui.tag_history_dialog import open_tag_history
        open_tag_history(self)

    def _on_import(self) -> None:
        """Show an import dialog: choose .ics file OR scan macOS Calendar."""
        msg = QMessageBox(self)
        msg.setWindowTitle("Import Calendar Events")
        msg.setText("How would you like to import events?")
        ics_btn = msg.addButton("📂 Open .ics file", QMessageBox.ButtonRole.ActionRole)
        mac_btn = msg.addButton("🗓 Scan macOS Calendar", QMessageBox.ButtonRole.ActionRole)
        msg.addButton(QMessageBox.StandardButton.Cancel)
        msg.exec()

        clicked = msg.clickedButton()
        if clicked == ics_btn:
            self._import_ics_file()
        elif clicked == mac_btn:
            self._import_macos_calendar()

    def _import_ics_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open ICS File",
            "",
            "iCalendar Files (*.ics *.ical);;All Files (*)",
        )
        if not path:
            return
        try:
            events = parse_ics(path)
            inserted, skipped = import_events(self._db, events)
            self.refresh_calendar()
            self.show_toast(f"Imported {inserted} event(s), {skipped} skipped")
        except Exception as e:
            QMessageBox.critical(self, "Import Error", str(e))

    def _import_macos_calendar(self) -> None:
        try:
            events = scan_macos_calendar()
            if not events:
                QMessageBox.information(
                    self,
                    "macOS Calendar",
                    "No events found. Make sure Calendar.app has events and "
                    "that you have granted Full Disk Access if prompted.",
                )
                return
            inserted, skipped = import_events(self._db, events)
            self.refresh_calendar()
            self.show_toast(f"Imported {inserted} event(s) from macOS Calendar, {skipped} skipped")
        except Exception as e:
            QMessageBox.critical(self, "Import Error", str(e))

    # ------------------------------------------------------------------
    # Connected calendars — ICS/webcal subscriptions + two-way Outlook sync
    # ------------------------------------------------------------------

    def _start_background_sync(self) -> None:
        """Refresh all connected calendars on a worker thread. Safe to call
        from the periodic QTimer, the manual 'Sync Now' button, or right
        after adding/connecting a new source."""
        if self._sync_running or self._config is None:
            return
        self._sync_running = True

        def worker() -> None:
            from assistant.calendar_sync.outlook_sync import run_full_sync
            try:
                results = run_full_sync(self._db, self._config)
            except Exception as e:  # noqa: BLE001 — surface any failure as a toast, don't crash the thread
                results = {"errors": [str(e)]}
            self._sync_results_queue.put(results)

        threading.Thread(target=worker, daemon=True).start()

    def _drain_sync_results(self) -> None:
        """Runs on the main-thread QTimer; picks up finished sync results."""
        try:
            while True:
                results = self._sync_results_queue.get_nowait()
                self._sync_running = False
                self.refresh_calendar()
                refresh_dialog = getattr(self, "_connected_dialog_refresh", None)
                if refresh_dialog:
                    refresh_dialog()
                pulled = results.get("ics_synced", 0) + results.get("outlook_pulled", 0)
                pushed = results.get("outlook_pushed", 0)
                if results.get("errors"):
                    self.show_toast("Calendar sync had errors — see Connected Calendars")
                elif pulled or pushed:
                    self.show_toast(f"Calendars synced ({pulled} pulled, {pushed} pushed)")
        except queue.Empty:
            pass

    def _on_connected_calendars(self) -> None:
        from PyQt6.QtWidgets import QListWidget, QListWidgetItem

        dialog = QDialog(self)
        dialog.setWindowTitle("Connected Calendars")
        dialog.setMinimumSize(500, 460)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        intro = QLabel(
            "Subscribe to any calendar's private ICS/webcal link (Gmail, Outlook.com, "
            "iCloud, Yahoo…) for a read-only feed that auto-refreshes. Connect Outlook "
            "directly below for two-way sync instead."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        list_widget = QListWidget()
        list_widget.setAlternatingRowColors(True)
        layout.addWidget(list_widget, 1)

        def refresh_list() -> None:
            list_widget.clear()
            for source in self._db.get_calendar_sources():
                if source["kind"] == "outlook":
                    kind_label = "Outlook (two-way)" if source["two_way"] else "Outlook (read-only pull)"
                else:
                    kind_label = "ICS link"
                label = source["label"] or source["url"] or "Outlook"
                status = f"last synced {source['last_synced'][:16].replace('T', ' ')}" if source["last_synced"] else "not yet synced"
                state = "" if source["enabled"] else "  (disabled)"
                item = QListWidgetItem(f"{label}  —  {kind_label}  —  {status}{state}")
                item.setData(Qt.ItemDataRole.UserRole, source["id"])
                list_widget.addItem(item)

        self._connected_dialog_refresh = refresh_list
        refresh_list()

        remove_btn = QPushButton("Remove Selected")

        def remove_selected() -> None:
            item = list_widget.currentItem()
            if not item:
                return
            self._db.delete_calendar_source(item.data(Qt.ItemDataRole.UserRole))
            refresh_list()
            self.refresh_calendar()

        remove_btn.clicked.connect(remove_selected)
        layout.addWidget(remove_btn)

        layout.addWidget(QLabel("Add a calendar link (ICS / webcal URL):"))
        add_row = QHBoxLayout()
        label_edit = QLineEdit()
        label_edit.setPlaceholderText("Label (e.g. \"My Gmail\")")
        url_edit = QLineEdit()
        url_edit.setPlaceholderText("https://calendar.google.com/.../basic.ics")
        add_row.addWidget(label_edit, 1)
        add_row.addWidget(url_edit, 2)
        add_btn = QPushButton("Add")

        def add_ics() -> None:
            url = url_edit.text().strip()
            if not url:
                return
            self._db.create_calendar_source(kind="ics_url", label=label_edit.text().strip(), url=url)
            label_edit.clear()
            url_edit.clear()
            refresh_list()
            self._start_background_sync()

        add_btn.clicked.connect(add_ics)
        add_row.addWidget(add_btn)
        layout.addLayout(add_row)
        # Enter while typing a label/URL adds the calendar (the contextually
        # obvious action) rather than falling through to the dialog's Close
        # default below.
        label_edit.returnPressed.connect(add_ics)
        url_edit.returnPressed.connect(add_ics)

        layout.addSpacing(6)

        outlook_row = QHBoxLayout()
        connect_outlook_btn = QPushButton("Connect Outlook…")

        def connect_outlook() -> None:
            if self._config.microsoft is None:
                QMessageBox.warning(
                    dialog, "Outlook Not Configured",
                    "Add a \"microsoft:\" section (client_id) to config.yaml first — "
                    "see README for registering a free Azure AD app.",
                )
                return
            self._start_outlook_connect(dialog, refresh_list)

        connect_outlook_btn.clicked.connect(connect_outlook)
        outlook_row.addWidget(connect_outlook_btn)

        two_way_cb = QCheckBox("Two-way sync (push my edits/deletes back to Outlook)")
        existing_outlook = self._db.get_calendar_source_by_kind("outlook")
        two_way_cb.setChecked(bool(existing_outlook and existing_outlook["two_way"]))

        def toggle_two_way(checked: bool) -> None:
            src = self._db.get_calendar_source_by_kind("outlook")
            if src:
                self._db.update_calendar_source(src["id"], two_way=int(checked))
            else:
                QMessageBox.information(dialog, "Not Connected", "Connect Outlook first.")
                two_way_cb.setChecked(False)

        two_way_cb.toggled.connect(toggle_two_way)
        outlook_row.addWidget(two_way_cb)
        layout.addLayout(outlook_row)

        sync_now_btn = QPushButton("Sync Now")
        sync_now_btn.clicked.connect(self._start_background_sync)
        layout.addWidget(sync_now_btn)

        close_btn = QPushButton("Close")
        close_btn.setDefault(True)
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)

        dialog.exec()
        self._connected_dialog_refresh = None

    def _start_outlook_connect(self, parent_dialog: QDialog, on_done) -> None:
        """Runs MSAL's device-code flow with a small modal instead of the
        console-only UX the menu-bar 'Re-authenticate' item uses."""
        from assistant.actions.calendar.auth import MSALAuth

        try:
            auth = MSALAuth(self._config.microsoft)
            flow = auth.start_device_flow()
        except Exception as e:
            QMessageBox.critical(parent_dialog, "Outlook Connect Failed", str(e))
            return

        code_dialog = QDialog(parent_dialog)
        code_dialog.setWindowTitle("Connect Outlook")
        code_dialog.setMinimumWidth(380)
        v = QVBoxLayout(code_dialog)

        msg = QLabel(flow.get("message", ""))
        msg.setWordWrap(True)
        v.addWidget(msg)
        status_lbl = QLabel("Waiting for you to complete sign-in in your browser…")
        status_lbl.setWordWrap(True)
        v.addWidget(status_lbl)

        open_btn = QPushButton("Open Browser")

        def open_browser() -> None:
            from PyQt6.QtCore import QUrl
            from PyQt6.QtGui import QDesktopServices
            url = flow.get("verification_uri") or flow.get("verification_uri_complete", "")
            if url:
                QDesktopServices.openUrl(QUrl(url))

        open_btn.clicked.connect(open_browser)
        open_btn.setDefault(True)
        v.addWidget(open_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(code_dialog.reject)
        v.addWidget(cancel_btn)

        result_queue: queue.Queue = queue.Queue()

        def worker() -> None:
            try:
                auth.complete_device_flow(flow)
                result_queue.put(("ok", None))
            except Exception as e:  # noqa: BLE001
                result_queue.put(("error", str(e)))

        threading.Thread(target=worker, daemon=True).start()

        poll_timer = QTimer(code_dialog)
        poll_timer.setInterval(500)

        def poll() -> None:
            try:
                status, err = result_queue.get_nowait()
            except queue.Empty:
                return
            poll_timer.stop()
            if status == "ok":
                existing = self._db.get_calendar_source_by_kind("outlook")
                if not existing:
                    self._db.create_calendar_source(kind="outlook", label="Outlook")
                code_dialog.accept()
                self.show_toast("Outlook connected")
                on_done()
                self._start_background_sync()
            else:
                status_lbl.setText(f"Failed: {err}")

        poll_timer.timeout.connect(poll)
        poll_timer.start()
        code_dialog.finished.connect(poll_timer.stop)

        code_dialog.exec()
