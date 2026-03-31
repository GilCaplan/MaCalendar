"""Main calendar application window."""

from __future__ import annotations

import datetime
import queue
import threading
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QCloseEvent
from PyQt6.QtWidgets import (
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
    QComboBox,
    QSpinBox,
)

from assistant.calendar_ui.day_view import DayView
from assistant.calendar_ui.event_dialog import EventDialog
from assistant.calendar_ui.month_view import MonthView
from assistant.calendar_ui.sidebar import Sidebar
import assistant.calendar_ui.styles as _styles
from assistant.calendar_ui.styles import get_app_style, BLUE, GRAY_BORDER, GRAY_DARK, GRAY_TEXT, WHITE
from assistant.calendar_ui.week_view import WeekView
from assistant.calendar_ui.importer import parse_ics, scan_macos_calendar, import_events
from assistant.db import CalendarDB
from assistant.pipeline import (
    STATUS_DONE,
    STATUS_ERROR,
    STATUS_IDLE,
    STATUS_LISTENING,
    STATUS_PROCESSING,
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
    STATUS_PROCESSING: "mic_processing",
    STATUS_DONE: "mic_idle",
    STATUS_ERROR: "mic_idle",
    STATUS_REFRESH: "mic_idle",
    STATUS_SWITCH_TODAY: "mic_idle",
    STATUS_SWITCH_TODO: "mic_idle",
}


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


class CalendarWindow(QMainWindow):
    """
    Main Outlook-style calendar window.

    Voice pipeline updates come in via pipeline.status_queue (thread-safe).
    A QTimer drains the queue on the main thread every 100ms.
    """

    def __init__(self, pipeline=None, config=None, parent=None):
        super().__init__(parent)
        self._pipeline = pipeline
        self._config = config
        self._db = CalendarDB()
        self._current_date = datetime.date.today()
        self._view_mode = "month"  # "month" | "week" | "day" | "todo"

        self._dark = False

        self.setWindowTitle("Calendar")
        self.setMinimumSize(900, 640)
        self.resize(1100, 720)
        self.setStyleSheet(get_app_style(False))

        self._build_ui()

        # Auto-sync todos from calendar on open if configured
        if config and config.todo.sync.auto_sync_on_open and config.todo.sync.mode != "off":
            self._db.sync_calendar_to_todos(list_name=config.todo.sync.mode)

        # Poll pipeline status queue
        if pipeline is not None:
            self._poll_timer = QTimer(self)
            self._poll_timer.setInterval(100)
            self._poll_timer.timeout.connect(self._poll_status)
            self._poll_timer.start()

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

        # Stacked: month / week / day / todo
        from assistant.calendar_ui.todo_view import TodoView
        self._stack = QStackedWidget()
        self._month_view = MonthView(self._db)
        self._week_view = WeekView(self._db)
        self._day_view = DayView(self._db)
        self._todo_view = TodoView(self._db, config=self._config)
        self._stack.addWidget(self._month_view)
        self._stack.addWidget(self._week_view)
        self._stack.addWidget(self._day_view)
        self._stack.addWidget(self._todo_view)
        self._month_view.date_selected.connect(self._on_day_selected)
        self._month_view.date_double_clicked.connect(self._on_day_double_clicked)
        self._month_view.event_clicked.connect(self._on_event_clicked)
        self._week_view.datetime_double_clicked.connect(self._on_datetime_double_clicked)
        self._week_view.event_clicked.connect(self._on_event_clicked)
        self._day_view.datetime_double_clicked.connect(self._on_datetime_double_clicked)
        self._day_view.event_clicked.connect(self._on_event_clicked)
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

        self._update_title()

    def _build_toolbar(self) -> QWidget:
        from PyQt6.QtWidgets import QFrame
        bar = QWidget()
        self._toolbar_bar = bar
        bar.setFixedHeight(54)
        bar.setStyleSheet(f"background-color: {WHITE}; border-bottom: 1px solid {GRAY_BORDER};")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(2)

        # ── Group 1: nav arrows ──────────────────────────────────────
        prev_btn = QPushButton("‹")
        prev_btn.setObjectName("nav")
        prev_btn.setFixedSize(28, 28)
        prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        prev_btn.clicked.connect(self._on_prev)
        layout.addWidget(prev_btn)

        next_btn = QPushButton("›")
        next_btn.setObjectName("nav")
        next_btn.setFixedSize(28, 28)
        next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        next_btn.clicked.connect(self._on_next)
        layout.addWidget(next_btn)

        layout.addSpacing(4)

        today_btn = QPushButton("Today")
        today_btn.setObjectName("flat")
        today_btn.setFixedHeight(30)
        today_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        today_btn.clicked.connect(self._on_today)
        layout.addWidget(today_btn)

        # ── Title ────────────────────────────────────────────────────
        layout.addSpacing(6)
        self._title_label = QLabel()
        self._title_label.setObjectName("month_title")
        font = QFont()
        font.setPointSize(15)
        font.setWeight(QFont.Weight.DemiBold)
        self._title_label.setFont(font)
        layout.addWidget(self._title_label)

        layout.addStretch()

        # ── Group 2: view toggle tabs ────────────────────────────────
        for label, mode in [("Month", "month"), ("Week", "week"), ("Day", "day"), ("Tasks", "todo")]:
            btn = QPushButton(label)
            btn.setObjectName("seg_btn")
            btn.setProperty("active", mode == self._view_mode)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(30)
            btn.clicked.connect(lambda _, m=mode: self._set_view(m))
            layout.addWidget(btn)
            setattr(self, f"_view_btn_{mode}", btn)

        # ── Separator ────────────────────────────────────────────────
        layout.addSpacing(8)
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedHeight(22)
        sep.setStyleSheet(f"color: {GRAY_BORDER};")
        layout.addWidget(sep)
        layout.addSpacing(6)

        # ── Group 3: tools ───────────────────────────────────────────
        import_btn = QPushButton("Import")
        import_btn.setObjectName("flat")
        import_btn.setFixedHeight(30)
        import_btn.setToolTip("Import events from an .ics file or macOS Calendar")
        import_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        import_btn.clicked.connect(self._on_import)
        layout.addWidget(import_btn)

        self._settings_btn = QPushButton("⚙")
        self._settings_btn.setObjectName("icon_btn")
        self._settings_btn.setFixedSize(30, 30)
        self._settings_btn.setToolTip("Assistant Settings")
        self._settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._settings_btn.clicked.connect(self._on_settings_popup)
        layout.addWidget(self._settings_btn)

        self._theme_btn = QPushButton("○")
        self._theme_btn.setObjectName("icon_btn")
        self._theme_btn.setFixedSize(30, 30)
        self._theme_btn.setToolTip("Toggle dark / light mode")
        self._theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._theme_btn.clicked.connect(self._on_toggle_theme)
        layout.addWidget(self._theme_btn)
        self._update_theme_btn()

        layout.addSpacing(2)

        self._mic_btn = QPushButton("🎙")
        self._mic_btn.setObjectName("mic_idle")
        self._mic_btn.setFixedSize(30, 30)
        self._mic_btn.setToolTip("Click or press Ctrl+J to toggle the microphone")
        self._mic_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if self._pipeline is not None:
            self._mic_btn.clicked.connect(self._pipeline.trigger)
        layout.addWidget(self._mic_btn)

        return bar

    def _update_theme_btn(self) -> None:
        # Show the icon for what the mode will switch TO
        self._theme_btn.setText("☀" if self._dark else "☾")
        self._theme_btn.setToolTip("Switch to light mode" if self._dark else "Switch to dark mode")

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _on_prev(self) -> None:
        if self._view_mode == "todo":
            return
        if self._view_mode == "month":
            d = self._current_date.replace(day=1) - datetime.timedelta(days=1)
            self._current_date = d.replace(day=1)
        elif self._view_mode == "week":
            self._current_date -= datetime.timedelta(weeks=1)
        else:  # day
            self._current_date -= datetime.timedelta(days=1)
        self._navigate()

    def _on_next(self) -> None:
        if self._view_mode == "todo":
            return
        if self._view_mode == "month":
            d = self._current_date.replace(day=28) + datetime.timedelta(days=4)
            self._current_date = d.replace(day=1)
        elif self._view_mode == "week":
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

    def _on_day_selected(self, date: datetime.date) -> None:
        self._current_date = date
        self._update_title()

    def _navigate(self) -> None:
        if self._view_mode == "todo":
            self._update_title()
            return
        if self._view_mode == "month":
            self._month_view.navigate(self._current_date.year, self._current_date.month)
        elif self._view_mode == "week":
            week_start = self._current_date - datetime.timedelta(days=(self._current_date.weekday() + 1) % 7)
            self._week_view.navigate(week_start)
        else:  # day
            self._day_view.navigate(self._current_date)
        self._update_title()

    def _set_view(self, mode: str) -> None:
        self._view_mode = mode
        widget = {
            "month": self._month_view,
            "week": self._week_view,
            "day": self._day_view,
            "todo": self._todo_view,
        }.get(mode, self._month_view)
        self._stack.setCurrentWidget(widget)
        for m in ("month", "week", "day", "todo"):
            btn = getattr(self, f"_view_btn_{m}", None)
            if btn:
                btn.setProperty("active", m == mode)
                btn.style().unpolish(btn)
                btn.style().polish(btn)
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

    def _update_title(self) -> None:
        if self._view_mode == "todo":
            self._title_label.setText("Tasks")
        elif self._view_mode == "month":
            self._title_label.setText(self._current_date.strftime("%B %Y"))
        elif self._view_mode == "week":
            week_start = self._current_date - datetime.timedelta(days=(self._current_date.weekday() + 1) % 7)
            week_end = week_start + datetime.timedelta(days=6)
            if week_start.month == week_end.month:
                self._title_label.setText(
                    f"{week_start.strftime('%B %-d')} – {week_end.day}, {week_end.year}"
                )
            else:
                self._title_label.setText(
                    f"{week_start.strftime('%b %-d')} – {week_end.strftime('%b %-d, %Y')}"
                )
        else:  # day
            self._title_label.setText(self._current_date.strftime("%A, %B %-d, %Y"))

    # ------------------------------------------------------------------
    # Event actions
    # ------------------------------------------------------------------

    def _on_new_event(self, default_date: Optional[datetime.date] = None) -> None:
        dialog = EventDialog(self, default_date=default_date or self._current_date)
        if dialog.exec() and dialog.event_data:
            self._db.create_event_from_dict(dialog.event_data)
            self.refresh_calendar()

    def _on_day_double_clicked(self, date: datetime.date) -> None:
        self._on_new_event(default_date=date)

    def _on_datetime_double_clicked(self, dt: datetime.datetime) -> None:
        end = dt + datetime.timedelta(hours=1)
        pre = {
            "title": "",
            "date": dt.date().isoformat(),
            "start_time": dt.strftime("%H:%M"),
            "end_time": end.strftime("%H:%M"),
            "attendees": "",
            "location": "",
            "description": "",
            "color": BLUE,
        }
        dialog = EventDialog(self, default_date=dt.date())
        if dialog.exec() and dialog.event_data:
            self._db.create_event_from_dict(dialog.event_data)
            self.refresh_calendar()

    def _on_event_clicked(self, event: dict) -> None:
        dialog = EventDialog(self, event=event)
        if dialog.exec():
            ev_id = event.get("id")
            series_id = event.get("series_id")

            if dialog.delete_series_requested and series_id:
                count = self._db.delete_series(series_id)
                self.refresh_calendar()
                self.show_toast(f"Deleted {count} events in series")
            elif dialog.delete_requested and ev_id:
                self._db.delete_event(ev_id)
                self.refresh_calendar()
                self.show_toast(f"Deleted \"{event['title']}\"")
            elif dialog.event_data:
                ev_id = dialog.event_data.pop("id", None)
                series_id = dialog.event_data.pop("series_id", None)
                
                if ev_id:
                    if series_id:
                        # For now, UI saves edits to just THIS instance
                        # (A more complex UI could ask "Apply changes to all?")
                        self._db.update_event(ev_id, **dialog.event_data)
                    else:
                        self._db.update_event(ev_id, **dialog.event_data)
                    self.refresh_calendar()
                    self.show_toast(f"Updated \"{dialog.event_data['title']}\"")

    def _on_event_rescheduled(self, event_id: int, updates: dict) -> None:
        if "start_time" in updates and "end_time" not in updates:
            event = self._db.get_event(event_id)
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
        self._db.update_event(event_id, **updates)
        self.refresh_calendar()
        self.show_toast("Event moved")

    # ------------------------------------------------------------------
    # Voice assistant integration
    # ------------------------------------------------------------------

    def _poll_status(self) -> None:
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

    def _handle_status(self, status: str, message: str = "") -> None:
        icon = _MIC_ICONS.get(status, "🎙")
        obj_name = _MIC_OBJ_NAMES.get(status, "mic_idle")
        self._mic_btn.setText(icon)
        self._mic_btn.setObjectName(obj_name)
        self._mic_btn.style().unpolish(self._mic_btn)
        self._mic_btn.style().polish(self._mic_btn)

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

    def refresh_calendar(self) -> None:
        """Reload events from DB in all calendar views."""
        self._month_view.refresh()
        self._week_view.refresh()
        self._day_view.refresh()

    def refresh_todos(self) -> None:
        """Reload todos from DB in the TodoView."""
        if hasattr(self, "_todo_view"):
            self._todo_view.refresh()

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
        dark = self._dark
        self.setStyleSheet(get_app_style(dark))
        self._month_view.apply_theme(dark)
        self._week_view.apply_theme(dark)
        self._day_view.apply_theme(dark)
        self._sidebar.apply_theme(dark)
        if hasattr(self, "_todo_view"):
            self._todo_view.apply_theme(dark)
        # Re-style toolbar
        bg = _styles.D_WHITE if dark else WHITE
        border = _styles.D_GRAY_BORDER if dark else GRAY_BORDER
        self._toolbar_bar.setStyleSheet(
            f"background-color: {bg}; border-bottom: 1px solid {border};"
        )
        # Force segmented buttons to repaint with new theme
        for m in ("month", "week", "day", "todo"):
            btn = getattr(self, f"_view_btn_{m}", None)
            if btn:
                btn.style().unpolish(btn)
                btn.style().polish(btn)
        self._update_theme_btn()
        self.show_toast("Dark mode on" if dark else "Light mode on")

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
        if not self._pipeline:
            return
            
        dialog = QDialog(self)
        dialog.setWindowTitle("Assistant Settings")
        dialog.setFixedSize(320, 240)
        
        layout = QVBoxLayout(dialog)
        
        # Auto-Approve check
        auto_cb = QCheckBox("Auto-Approve Actions (No Confirmations)")
        auto_cb.setChecked(self._pipeline._confirmer.level == 0)
        layout.addWidget(auto_cb)

        # Mute check
        mute_cb = QCheckBox("Mute Voice Output")
        mute_cb.setChecked(self._pipeline._tts.mute)
        layout.addWidget(mute_cb)
        
        # Speed 
        speed_layout = QHBoxLayout()
        speed_layout.addWidget(QLabel("Talking Speed:"))
        speed_spin = QSpinBox()
        speed_spin.setRange(50, 400)
        speed_spin.setValue(self._pipeline._tts.rate)
        speed_layout.addWidget(speed_spin)
        layout.addLayout(speed_layout)
        
        # Voice Dropdown
        voice_layout = QHBoxLayout()
        voice_layout.addWidget(QLabel("Voice Type:"))
        voice_combo = QComboBox()
        import subprocess
        try:
            voices = subprocess.check_output(["say", "-v", "?"], text=True).splitlines()
            voice_names = []
            for v in voices:
                if v.strip():
                    name = v.split()[0]
                    if name not in voice_names:
                        voice_names.append(name)
            voice_combo.addItems(voice_names)
        except Exception:
            voice_combo.addItems(["Samantha", "Daniel", "Alex", "Ava", "Zari"])
            
        current_voice = self._pipeline._tts.voice
        if current_voice in [voice_combo.itemText(i) for i in range(voice_combo.count())]:
            voice_combo.setCurrentText(current_voice)
        else:
            voice_combo.addItem(current_voice)
            voice_combo.setCurrentText(current_voice)
            
        voice_layout.addWidget(voice_combo)
        layout.addLayout(voice_layout)
        
        # Test & Save
        btn_layout = QHBoxLayout()
        test_btn = QPushButton("Test Audio")
        def run_test():
            if mute_cb.isChecked():
                self.show_toast("Muted. Uncheck to test.")
                return
            import threading
            threading.Thread(target=lambda: subprocess.Popen(
                ["say", "-v", voice_combo.currentText(), "-r", str(speed_spin.value()), "Hello, I am ready."],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            ), daemon=True).start()
        test_btn.clicked.connect(run_test)
        btn_layout.addWidget(test_btn)
        
        save_btn = QPushButton("Save Config")
        save_btn.setDefault(True)
        def save_config():
            self._pipeline._confirmer.level = 0 if auto_cb.isChecked() else 1
            self._pipeline._tts.mute = mute_cb.isChecked()
            self._pipeline._tts.rate = speed_spin.value()
            self._pipeline._tts.voice = voice_combo.currentText()
            # Try to write to config.yaml safely
            try:
                import os, re
                c_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config.yaml")
                if os.path.exists(c_path):
                    with open(c_path, "r") as f:
                        txt = f.read()
                    txt = re.sub(r"mute:\s*(true|false)", f"mute: {'true' if mute_cb.isChecked() else 'false'}", txt, count=1, flags=re.IGNORECASE)
                    txt = re.sub(r"voice:\s*\"[^\"]+\"", f'voice: "{voice_combo.currentText()}"', txt, count=1)
                    txt = re.sub(r"rate:\s*\d+", f"rate: {speed_spin.value()}", txt, count=1)
                    txt = re.sub(r"confirmation_level:\s*\d+", f"confirmation_level: {0 if auto_cb.isChecked() else 1}", txt, count=1)
                    with open(c_path, "w") as f:
                        f.write(txt)
            except Exception as e:
                print("Failed saving to config.yaml:", e)
                
            self.show_toast("Settings applied!")
            dialog.accept()
            
        save_btn.clicked.connect(save_config)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)
        
        dialog.exec()

    # ------------------------------------------------------------------
    # ICS / macOS Calendar import
    # ------------------------------------------------------------------

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
