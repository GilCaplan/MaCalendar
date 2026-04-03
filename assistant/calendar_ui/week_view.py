"""Week calendar view with hourly time slots."""

from __future__ import annotations

import datetime
from typing import List

from PyQt6.QtCore import Qt, QMimeData, QByteArray, pyqtSignal
from PyQt6.QtGui import QColor, QDrag, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QGridLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

import assistant.calendar_ui.styles as _styles
from assistant.calendar_ui.styles import (
    BLUE,
    BLUE_LIGHT,
    GRAY_BORDER,
    GRAY_DARK,
    GRAY_LIGHT,
    GRAY_TEXT,
    TODAY_BG,
    TODAY_TEXT,
    WEEKEND_BG,
    WHITE,
)

HOUR_HEIGHT = 48   # px per hour
LABEL_WIDTH = 52   # px for time labels on left
RESIZE_HANDLE = 7  # px at top/bottom edge that activate resize mode
_SNAP_PX = HOUR_HEIGHT // 4  # 15-minute snap grid (12px)


class EventBlock(QLabel):
    """Colored block representing an event in the week grid."""

    clicked = pyqtSignal(dict)
    resized = pyqtSignal(int, dict)  # (event_id, {start_time, end_time})

    def __init__(self, event: dict, font_size: int = 11, parent=None):
        super().__init__(parent)
        color = event.get("color", BLUE)
        start = event.get("start_time", "")
        end = event.get("end_time", "")
        self.event = event
        self._font_size = font_size
        self._drag_start = None
        self.setText(f"  {event['title']}\n  {start}–{end}")
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.setStyleSheet(
            f"""
            QLabel {{
                background-color: {color};
                color: white;
                border-radius: 3px;
                font-size: {self._font_size}px;
                padding: 2px 4px;
                border-left: 3px solid rgba(0,0,0,0.2);
            }}
            """
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
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
            payload = {
                "start_time": f"{start_min // 60:02d}:{start_min % 60:02d}",
                "end_time":   f"{end_min   // 60:02d}:{end_min   % 60:02d}",
            }
            event_id = self.event["id"]
            self._resize_edge = None
            event.accept()
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self.resized.emit(event_id, payload))
        elif self._drag_start is not None:
            self._drag_start = None
            self.clicked.emit(self.event)


class DayColumn(QWidget):
    """One vertical day column in the week view."""

    slot_double_clicked = pyqtSignal(datetime.datetime)
    event_clicked = pyqtSignal(dict)
    event_rescheduled = pyqtSignal(int, dict)

    def __init__(self, date: datetime.date, parent=None):
        super().__init__(parent)
        self.date = date
        self.setMinimumWidth(80)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(HOUR_HEIGHT * 24)

        self.is_today = date == datetime.date.today()
        self.is_weekend = date.weekday() >= 5
        self._event_widgets: List[EventBlock] = []
        self._drag_hover = False
        self._ui_config = None
        self.setAcceptDrops(True)
        self._apply_bg()

    def _apply_bg(self) -> None:
        dark = _styles._dark
        if self.is_today:
            bg = _styles.D_GRAY_BG if dark else "#f0f7ff"
        elif self.is_weekend:
            bg = _styles.D_WEEKEND_BG if dark else WEEKEND_BG
        else:
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
            h = max(((eh * 60 + em) - (sh * 60 + sm)) / 60 * HOUR_HEIGHT, 18)

            fs = 11 if not self._ui_config else self._ui_config.font_week
            block = EventBlock(ev, font_size=fs, parent=self)
            block.clicked.connect(self.event_clicked)
            block.resized.connect(self.event_rescheduled)
            block.setGeometry(2, int(top), self.width() - 4, int(h))
            block.show()
            self._event_widgets.append(block)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Re-layout event blocks on resize
        for block in self._event_widgets:
            block.setGeometry(2, block.y(), self.width() - 4, block.height())

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
            self.event_rescheduled.emit(event_id, {"date": self.date.isoformat(), "start_time": new_start})
            event.acceptProposedAction()

    def paintEvent(self, event):
        super().paintEvent(event)
        dark = _styles._dark
        border_color = _styles.D_GRAY_BORDER if dark else GRAY_BORDER
        painter = QPainter(self)
        painter.setPen(QPen(QColor(border_color)))
        # Hour lines
        for h in range(25):
            y = h * HOUR_HEIGHT
            painter.drawLine(0, y, self.width(), y)
        # Right border
        painter.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
        if self._drag_hover:
            painter.fillRect(self.rect(), QColor("#0078d4").lighter(190))


class WeekView(QWidget):
    """
    Full week view with a time axis on the left and 7 day columns.
    Signals:
        datetime_double_clicked(datetime) — double-click on a time slot
        event_clicked(event_dict)
    """

    datetime_double_clicked = pyqtSignal(datetime.datetime)
    event_clicked = pyqtSignal(dict)
    event_rescheduled = pyqtSignal(int, dict)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self._db = db
        today = datetime.date.today()
        self._week_start = today - datetime.timedelta(days=(today.weekday() + 1) % 7)
        self._day_columns: List[DayColumn] = []
        self._ui_config = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Day header row
        self._header = QWidget()
        self._header.setFixedHeight(48)
        self._header_layout = QGridLayout(self._header)
        self._header_layout.setContentsMargins(LABEL_WIDTH, 0, 0, 0)
        self._header_layout.setSpacing(0)
        layout.addWidget(self._header)

        # Scrollable body
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("border: none;")

        body = QWidget()
        body_layout = QGridLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # Time labels column
        self._time_col = QWidget()
        time_col = self._time_col
        time_col.setFixedWidth(LABEL_WIDTH)
        time_col.setFixedHeight(HOUR_HEIGHT * 24)
        self._time_labels: List[QLabel] = []
        time_layout = QVBoxLayout(time_col)
        time_layout.setContentsMargins(0, 0, 4, 0)
        time_layout.setSpacing(0)
        for h in range(24):
            lbl = QLabel("12 AM" if h == 0 else f"{h} AM" if h < 12 else "12 PM" if h == 12 else f"{h-12} PM")
            lbl.setFixedHeight(HOUR_HEIGHT)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
            self._time_labels.append(lbl)
            time_layout.addWidget(lbl)

        body_layout.addWidget(time_col, 0, 0)
        body_layout.setColumnStretch(0, 0)

        self._col_container = QWidget()
        self._col_layout = QGridLayout(self._col_container)
        self._col_layout.setContentsMargins(0, 0, 0, 0)
        self._col_layout.setSpacing(0)
        body_layout.addWidget(self._col_container, 0, 1)
        body_layout.setColumnStretch(1, 1)

        scroll.setWidget(body)
        layout.addWidget(scroll, stretch=1)

        # Scroll to 8am on load
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(100, lambda: scroll.verticalScrollBar().setValue(HOUR_HEIGHT * 8))
        self._scroll = scroll

        self._rebuild_columns()
        self._apply_theme_styles()

    def apply_theme(self, dark: bool) -> None:
        """Switch between light and dark theme and rebuild."""
        _styles._dark = dark
        self._apply_theme_styles()
        self._rebuild_columns()

    def apply_ui_config(self, ui_config) -> None:
        self._ui_config = ui_config
        self._apply_theme_styles()
        self._rebuild_columns()

    def _apply_theme_styles(self) -> None:
        """Reapply stylesheet constants that depend on the current theme."""
        dark = _styles._dark
        bg = _styles.D_WHITE if dark else WHITE
        border = _styles.D_GRAY_BORDER if dark else GRAY_BORDER
        text2 = _styles.D_GRAY_TEXT if dark else GRAY_TEXT
        self._header.setStyleSheet(
            f"background-color: {bg}; border-bottom: 1px solid {border};"
        )
        self._time_col.setStyleSheet(f"background-color: {bg};")
        fs = 11 if not self._ui_config else self._ui_config.font_week
        for lbl in self._time_labels:
            lbl.setStyleSheet(f"font-size: {fs}px; color: {text2}; padding-top: 2px;")

    def navigate(self, week_start: datetime.date) -> None:
        self._week_start = week_start
        self._rebuild_columns()

    def refresh(self) -> None:
        events = self._db.get_events_for_week(self._week_start)
        by_date: dict[str, list] = {}
        for ev in events:
            by_date.setdefault(ev["date"], []).append(ev)
        for col in self._day_columns:
            col.load_events(by_date.get(col.date.isoformat(), []))

    def _rebuild_columns(self) -> None:
        # Clear header
        while self._header_layout.count():
            item = self._header_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Clear columns
        while self._col_layout.count():
            item = self._col_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._day_columns.clear()

        today = datetime.date.today()
        for i in range(7):
            date = self._week_start + datetime.timedelta(days=i)
            is_today = date == today

            # Header cell
            header_cell = QWidget()
            header_layout = QVBoxLayout(header_cell)
            header_layout.setContentsMargins(0, 4, 0, 4)
            header_layout.setSpacing(0)

            dark = _styles._dark
            text2 = _styles.D_GRAY_TEXT if dark else GRAY_TEXT
            text_main = _styles.D_GRAY_DARK if dark else GRAY_DARK

            day_name = QLabel(date.strftime("%a").upper())
            day_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            day_name.setStyleSheet(f"font-size: 11px; color: {text2}; font-weight: 600;")

            day_num = QLabel(str(date.day))
            day_num.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if is_today:
                day_num.setStyleSheet(
                    f"font-size: 22px; font-weight: 700; color: {TODAY_BG};"
                )
            else:
                day_num.setStyleSheet(f"font-size: 22px; font-weight: 300; color: {text_main};")

            header_layout.addWidget(day_name)
            header_layout.addWidget(day_num)
            self._header_layout.addWidget(header_cell, 0, i)
            self._header_layout.setColumnStretch(i, 1)

            # Day column
            col = DayColumn(date)
            col._ui_config = self._ui_config
            col.slot_double_clicked.connect(self.datetime_double_clicked)
            col.event_clicked.connect(self.event_clicked)
            col.event_rescheduled.connect(self.event_rescheduled)
            self._col_layout.addWidget(col, 0, i)
            self._col_layout.setColumnStretch(i, 1)
            self._day_columns.append(col)

        self.refresh()
        self._apply_theme_styles()
