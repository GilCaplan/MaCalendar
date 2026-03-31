"""Day calendar view — single-day timeline with current time indicator."""

from __future__ import annotations

import datetime
from typing import List

from PyQt6.QtCore import Qt, QMimeData, QByteArray, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QDrag, QFont, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

import assistant.calendar_ui.styles as _styles
from assistant.calendar_ui.styles import (
    BLUE,
    GRAY_BORDER,
    GRAY_DARK,
    GRAY_TEXT,
    WHITE,
)

HOUR_HEIGHT = 56   # slightly taller than week view for readability
LABEL_WIDTH = 60
RESIZE_HANDLE = 8  # px at top/bottom edge that activate resize mode
_SNAP_PX = HOUR_HEIGHT // 4  # 15-minute snap grid


class EventBlock(QLabel):
    """Colored block representing one event in the day timeline."""

    clicked = pyqtSignal(dict)
    resized = pyqtSignal(int, dict)  # (event_id, {start_time, end_time})

    def __init__(self, event: dict, parent=None):
        super().__init__(parent)
        color = event.get("color", BLUE)
        start = event.get("start_time", "")
        end = event.get("end_time", "")
        location = event.get("location") or ""
        self.event = event

        text = f"  {event['title']}\n  {start}–{end}"
        if location:
            text += f"\n  \U0001f4cd {location}"
        self.setText(text)
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.setStyleSheet(
            f"""
            QLabel {{
                background-color: {color};
                color: white;
                border-radius: 4px;
                font-size: 12px;
                padding: 4px 6px;
                border-left: 4px solid rgba(0,0,0,0.2);
            }}
            """
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self._drag_start = None
        # Resize state
        self._resize_edge: str | None = None  # "top" or "bottom"
        self._resize_orig_top = 0
        self._resize_orig_height = 0
        self._resize_press_y = 0  # parent-relative y at press

    def _edge_at(self, y: int) -> str | None:
        if y <= RESIZE_HANDLE:
            return "top"
        if y >= self.height() - RESIZE_HANDLE:
            return "bottom"
        return None

    def mousePressEvent(self, event):
        edge = self._edge_at(event.pos().y())
        if edge:
            self._resize_edge = edge
            self._resize_orig_top = self.y()
            self._resize_orig_height = self.height()
            self._resize_press_y = self.mapToParent(event.pos()).y()
            event.accept()
        else:
            self._drag_start = event.pos()

    def mouseMoveEvent(self, event):
        if self._resize_edge:
            parent_y = self.mapToParent(event.pos()).y()
            delta = parent_y - self._resize_press_y
            min_h = max(_SNAP_PX, 18)
            orig_bottom = self._resize_orig_top + self._resize_orig_height

            if self._resize_edge == "bottom":
                raw_bottom = orig_bottom + delta
                snapped_bottom = round(raw_bottom / _SNAP_PX) * _SNAP_PX
                new_h = max(snapped_bottom - self._resize_orig_top, min_h)
                self.setGeometry(self.x(), self._resize_orig_top, self.width(), new_h)
            else:  # top
                raw_top = self._resize_orig_top + delta
                snapped_top = round(raw_top / _SNAP_PX) * _SNAP_PX
                new_h = max(orig_bottom - snapped_top, min_h)
                actual_top = orig_bottom - new_h
                self.setGeometry(self.x(), actual_top, self.width(), new_h)
            event.accept()
            return

        if self._drag_start is not None:
            if (event.pos() - self._drag_start).manhattanLength() < 8:
                return
            drag = QDrag(self)
            mime = QMimeData()
            mime.setData("application/x-event-id", QByteArray(str(self.event["id"]).encode()))
            drag.setMimeData(mime)
            pixmap = self.grab()
            transparent = QPixmap(pixmap.size())
            transparent.fill(QColor(0, 0, 0, 0))
            p = QPainter(transparent)
            p.setOpacity(0.75)
            p.drawPixmap(0, 0, pixmap)
            p.end()
            drag.setPixmap(transparent)
            self._drag_start = None
            drag.exec(Qt.DropAction.MoveAction)
            return

        # Hover cursor update
        edge = self._edge_at(event.pos().y())
        self.setCursor(Qt.CursorShape.SizeVerCursor if edge else Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event):
        if self._resize_edge:
            top = self.y()
            bottom = top + self.height()
            start_min = round(top / HOUR_HEIGHT * 60)
            end_min = round(bottom / HOUR_HEIGHT * 60)
            start_min = max(0, min(start_min, 23 * 60))
            end_min = max(start_min + 15, min(end_min, 24 * 60 - 1))
            self.resized.emit(self.event["id"], {
                "start_time": f"{start_min // 60:02d}:{start_min % 60:02d}",
                "end_time":   f"{end_min   // 60:02d}:{end_min   % 60:02d}",
            })
            self._resize_edge = None
            event.accept()
        elif self._drag_start is not None:
            self._drag_start = None
            self.clicked.emit(self.event)


class DayTimeline(QWidget):
    """
    Full-width single-day timeline. Draws hour lines, places event blocks,
    and paints a red current-time indicator when the date is today.
    """

    slot_double_clicked = pyqtSignal(datetime.datetime)
    event_clicked = pyqtSignal(dict)
    event_rescheduled = pyqtSignal(int, dict)

    def __init__(self, date: datetime.date, parent=None):
        super().__init__(parent)
        self.date = date
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(HOUR_HEIGHT * 24)
        self._event_widgets: List[EventBlock] = []
        self._drag_hover = False
        self.setAcceptDrops(True)
        self._apply_bg()

    def _apply_bg(self) -> None:
        dark = _styles._dark
        bg = _styles.D_WHITE if dark else WHITE
        self.setStyleSheet(f"background-color: {bg};")

    def load_events(self, events: List[dict]) -> None:
        for w in self._event_widgets:
            w.deleteLater()
        self._event_widgets.clear()

        for ev in events:
            try:
                sh, sm = map(int, ev["start_time"].split(":"))
            except Exception:
                continue
            try:
                eh, em = map(int, ev["end_time"].split(":"))
            except Exception:
                end_min = sh * 60 + sm + 60
                eh, em = min(end_min // 60, 23), end_min % 60

            top = (sh * 60 + sm) / 60 * HOUR_HEIGHT
            h = max(((eh * 60 + em) - (sh * 60 + sm)) / 60 * HOUR_HEIGHT, 24)

            block = EventBlock(ev, self)
            block.clicked.connect(self.event_clicked)
            block.resized.connect(self.event_rescheduled)
            block.setGeometry(4, int(top), self.width() - 8, int(h))
            block.show()
            self._event_widgets.append(block)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for block in self._event_widgets:
            block.setGeometry(4, block.y(), self.width() - 8, block.height())

    def mouseDoubleClickEvent(self, event):
        y = event.pos().y()
        hour = y // HOUR_HEIGHT
        minute = (y % HOUR_HEIGHT) // (HOUR_HEIGHT // 2) * 30
        dt = datetime.datetime.combine(self.date, datetime.time(min(hour, 23), minute))
        self.slot_double_clicked.emit(dt)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-event-id"):
            event.acceptProposedAction()
            self._drag_hover = True
            self.update()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-event-id"):
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._drag_hover = False
        self.update()

    def dropEvent(self, event):
        self._drag_hover = False
        self.update()
        if event.mimeData().hasFormat("application/x-event-id"):
            event_id = int(bytes(event.mimeData().data("application/x-event-id")).decode())
            y = event.position().y()
            total_min = int(y / HOUR_HEIGHT * 60)
            total_min = (total_min // 30) * 30
            new_h = min(total_min // 60, 23)
            new_m = total_min % 60
            new_start = f"{new_h:02d}:{new_m:02d}"
            self.event_rescheduled.emit(event_id, {"start_time": new_start})
            event.acceptProposedAction()

    def paintEvent(self, event):
        super().paintEvent(event)
        dark = _styles._dark
        border_color = _styles.D_GRAY_BORDER if dark else GRAY_BORDER
        painter = QPainter(self)

        # Hour grid lines
        painter.setPen(QPen(QColor(border_color)))
        for h in range(25):
            y = h * HOUR_HEIGHT
            painter.drawLine(0, y, self.width(), y)

        if self._drag_hover:
            painter.fillRect(self.rect(), QColor("#0078d4").lighter(190))

        # Current-time indicator (red) when viewing today
        if self.date == datetime.date.today():
            now = datetime.datetime.now()
            y = int((now.hour * 60 + now.minute) / 60 * HOUR_HEIGHT)
            painter.setPen(QPen(QColor("#d13438"), 2))
            painter.setBrush(QColor("#d13438"))
            painter.drawEllipse(0, y - 5, 10, 10)
            painter.drawLine(10, y, self.width(), y)


class DayView(QWidget):
    """
    Single-day ("Today") view with a full timeline and Morning Briefing button.

    Signals:
        datetime_double_clicked(datetime) — double-click on a time slot opens new-event dialog
        event_clicked(event_dict)         — click on an event opens edit/delete dialog
        briefing_requested()              — user clicked "Brief Me", handled by CalendarWindow
    """

    datetime_double_clicked = pyqtSignal(datetime.datetime)
    event_clicked = pyqtSignal(dict)
    briefing_requested = pyqtSignal()
    event_rescheduled = pyqtSignal(int, dict)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self._db = db
        self._date = datetime.date.today()
        self._timeline: DayTimeline | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header ──────────────────────────────────────────────────────
        self._header = QWidget()
        self._header.setFixedHeight(52)
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(LABEL_WIDTH + 8, 0, 12, 0)
        header_layout.setSpacing(8)

        self._date_label = QLabel()
        font = QFont()
        font.setPointSize(14)
        font.setWeight(QFont.Weight.DemiBold)
        self._date_label.setFont(font)
        header_layout.addWidget(self._date_label)

        self._count_label = QLabel()
        self._count_label.setFont(QFont())
        header_layout.addWidget(self._count_label)

        header_layout.addStretch()

        self._brief_btn = QPushButton("\U0001f305  Brief Me")
        self._brief_btn.setObjectName("flat")
        self._brief_btn.setToolTip("Read today's schedule aloud")
        self._brief_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._brief_btn.clicked.connect(self.briefing_requested)
        header_layout.addWidget(self._brief_btn)

        layout.addWidget(self._header)

        # ── Scrollable body: time labels + timeline ──────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("border: none;")

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # Time labels column
        self._time_col = QWidget()
        self._time_col.setFixedWidth(LABEL_WIDTH)
        self._time_col.setFixedHeight(HOUR_HEIGHT * 24)
        self._time_labels: List[QLabel] = []
        time_layout = QVBoxLayout(self._time_col)
        time_layout.setContentsMargins(0, 0, 4, 0)
        time_layout.setSpacing(0)
        for h in range(24):
            if h == 0:
                label_text = "12 AM"
            elif h < 12:
                label_text = f"{h} AM"
            elif h == 12:
                label_text = "12 PM"
            else:
                label_text = f"{h - 12} PM"
            lbl = QLabel(label_text)
            lbl.setFixedHeight(HOUR_HEIGHT)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
            self._time_labels.append(lbl)
            time_layout.addWidget(lbl)
        body_layout.addWidget(self._time_col)

        # Timeline container (rebuilt on navigate)
        self._timeline_container = QWidget()
        self._timeline_container.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._timeline_container.setFixedHeight(HOUR_HEIGHT * 24)
        self._tc_layout = QVBoxLayout(self._timeline_container)
        self._tc_layout.setContentsMargins(0, 0, 0, 0)
        self._tc_layout.setSpacing(0)
        body_layout.addWidget(self._timeline_container, stretch=1)

        scroll.setWidget(body)
        layout.addWidget(scroll, stretch=1)
        self._scroll = scroll

        # Refresh current-time indicator every minute
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(60_000)
        self._tick_timer.timeout.connect(self._tick_time)
        self._tick_timer.start()

        self._build_timeline()
        self._apply_theme_styles()
        self._update_header()

        QTimer.singleShot(120, self._scroll_to_now)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def navigate(self, date: datetime.date) -> None:
        self._date = date
        self._build_timeline()
        self._update_header()
        QTimer.singleShot(50, self._scroll_to_now)

    def refresh(self) -> None:
        events = self._db.get_events_for_day(self._date)
        if self._timeline:
            self._timeline.load_events(events)
        self._update_count(len(events))

    def apply_theme(self, dark: bool) -> None:
        _styles._dark = dark
        self._apply_theme_styles()
        if self._timeline:
            self._timeline._apply_bg()
        self.refresh()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_timeline(self) -> None:
        while self._tc_layout.count():
            item = self._tc_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._timeline = DayTimeline(self._date)
        self._timeline.slot_double_clicked.connect(self.datetime_double_clicked)
        self._timeline.event_clicked.connect(self.event_clicked)
        self._timeline.event_rescheduled.connect(self.event_rescheduled)
        self._tc_layout.addWidget(self._timeline)
        self.refresh()

    def _update_header(self) -> None:
        today = datetime.date.today()
        if self._date == today:
            prefix = "Today"
        elif self._date == today + datetime.timedelta(days=1):
            prefix = "Tomorrow"
        elif self._date == today - datetime.timedelta(days=1):
            prefix = "Yesterday"
        else:
            prefix = None

        date_str = self._date.strftime("%A, %B %-d, %Y")
        self._date_label.setText(f"{prefix} \u2014 {date_str}" if prefix else date_str)
        # Brief Me button only makes sense for today
        self._brief_btn.setVisible(self._date == today)

    def _update_count(self, n: int) -> None:
        if n == 0:
            self._count_label.setText("No events")
        elif n == 1:
            self._count_label.setText("\u00b7 1 event")
        else:
            self._count_label.setText(f"\u00b7 {n} events")

    def _tick_time(self) -> None:
        if self._timeline and self._date == datetime.date.today():
            self._timeline.update()

    def _scroll_to_now(self) -> None:
        if self._date == datetime.date.today():
            now = datetime.datetime.now()
            y = int((now.hour * 60 + now.minute) / 60 * HOUR_HEIGHT)
            self._scroll.verticalScrollBar().setValue(max(0, y - 120))
        else:
            self._scroll.verticalScrollBar().setValue(HOUR_HEIGHT * 8)

    def _apply_theme_styles(self) -> None:
        dark = _styles._dark
        bg = _styles.D_WHITE if dark else WHITE
        border = _styles.D_GRAY_BORDER if dark else GRAY_BORDER
        text2 = _styles.D_GRAY_TEXT if dark else GRAY_TEXT
        text_main = _styles.D_GRAY_DARK if dark else GRAY_DARK

        self._header.setStyleSheet(
            f"background-color: {bg}; border-bottom: 1px solid {border};"
        )
        self._time_col.setStyleSheet(f"background-color: {bg};")
        for lbl in self._time_labels:
            lbl.setStyleSheet(f"font-size: 11px; color: {text2}; padding-top: 2px;")
        self._date_label.setStyleSheet(f"color: {text_main};")
        self._count_label.setStyleSheet(f"color: {text2};")
