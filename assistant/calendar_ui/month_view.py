"""Month calendar grid view."""

from __future__ import annotations

import calendar
import datetime
from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QBrush
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
    GRAY_BG,
    GRAY_BORDER,
    GRAY_DARK,
    GRAY_LIGHT,
    GRAY_TEXT,
    OTHER_MONTH_TEXT,
    SELECTED_BG,
    TODAY_BG,
    TODAY_TEXT,
    WEEKEND_BG,
    WHITE,
)

DAY_HEADERS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class EventPill(QLabel):
    """A colored pill representing a single event in a day cell."""

    clicked = pyqtSignal(dict)

    def __init__(self, event: dict, parent=None):
        super().__init__(parent)
        self.event = event
        color = event.get("color", BLUE)
        start = event.get("start_time", "")
        text = f"  {start} {event['title']}" if start else f"  {event['title']}"
        self.setText(text)
        self.setFixedHeight(18)
        self.setStyleSheet(
            f"""
            QLabel {{
                background-color: {color};
                color: white;
                border-radius: 3px;
                font-size: 11px;
                padding: 0 3px;
            }}
            """
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"{event['title']}\n{event.get('date','')} {start}–{event.get('end_time','')}")

    def mousePressEvent(self, event):
        self.clicked.emit(self.event)


class DayCell(QWidget):
    """One cell in the month grid (represents a single calendar day)."""

    day_clicked = pyqtSignal(datetime.date)
    event_clicked = pyqtSignal(dict)

    def __init__(self, date: datetime.date, is_current_month: bool, parent=None):
        super().__init__(parent)
        self.date = date
        self.is_current_month = is_current_month
        self.is_today = date == datetime.date.today()
        self._events: List[dict] = []

        self.setMinimumHeight(90)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 2)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Day number
        self._num_label = DayNumberLabel(date.day, self.is_today)
        layout.addWidget(self._num_label, alignment=Qt.AlignmentFlag.AlignLeft)

        self._event_layout = QVBoxLayout()
        self._event_layout.setSpacing(1)
        self._event_layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._event_layout)
        layout.addStretch()

    def load_events(self, events: List[dict]) -> None:
        while self._event_layout.count():
            item = self._event_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._events = events
        for ev in events[:3]:
            pill = EventPill(ev)
            pill.clicked.connect(self.event_clicked)
            self._event_layout.addWidget(pill)
        if len(events) > 3:
            text_color = _styles.D_GRAY_TEXT if _styles._dark else GRAY_TEXT
            more = QLabel(f"  +{len(events)-3} more")
            more.setStyleSheet(f"font-size: 11px; color: {text_color};")
            self._event_layout.addWidget(more)

    def mousePressEvent(self, event):
        self.day_clicked.emit(self.date)

    def mouseDoubleClickEvent(self, event):
        self.day_clicked.emit(self.date)

    def paintEvent(self, event):
        super().paintEvent(event)
        dark = _styles._dark
        border_color = _styles.D_GRAY_BORDER if dark else GRAY_BORDER

        if not self.is_current_month:
            bg = _styles.D_GRAY_LIGHT if dark else GRAY_LIGHT
        elif self.date.weekday() >= 5:
            bg = _styles.D_WEEKEND_BG if dark else WEEKEND_BG
        else:
            bg = _styles.D_WHITE if dark else WHITE

        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(bg))
        painter.setPen(QPen(QColor(border_color)))
        painter.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)


class DayNumberLabel(QLabel):
    """Day number — shown as blue circle for today."""

    def __init__(self, day: int, is_today: bool, parent=None):
        super().__init__(str(day), parent)
        self.is_today = is_today
        self.setFixedSize(26, 26)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._refresh_style()

    def _refresh_style(self) -> None:
        dark = _styles._dark
        if self.is_today:
            self.setStyleSheet(
                f"""
                QLabel {{
                    background-color: {TODAY_BG};
                    color: {TODAY_TEXT};
                    border-radius: 13px;
                    font-size: 12px;
                    font-weight: 700;
                }}
                """
            )
        else:
            text_color = _styles.D_GRAY_DARK if dark else GRAY_DARK
            self.setStyleSheet(
                f"""
                QLabel {{
                    font-size: 12px;
                    font-weight: 400;
                    color: {text_color};
                }}
                """
            )


class MonthView(QWidget):
    """
    Full month calendar grid.
    Signals:
        date_selected(date)  — user clicked a day
        date_double_clicked(date) — user double-clicked a day (open new event)
        event_clicked(event_dict) — user clicked an event pill
    """

    date_selected = pyqtSignal(datetime.date)
    date_double_clicked = pyqtSignal(datetime.date)
    event_clicked = pyqtSignal(dict)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self._db = db
        self._year = datetime.date.today().year
        self._month = datetime.date.today().month
        self._cells: List[DayCell] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Day-of-week header row
        self._header = QWidget()
        self._header.setFixedHeight(32)
        self._header_labels: List[QLabel] = []
        self._header_layout = QGridLayout(self._header)
        self._header_layout.setContentsMargins(0, 0, 0, 0)
        self._header_layout.setSpacing(0)
        for col, name in enumerate(DAY_HEADERS):
            lbl = QLabel(name)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._header_labels.append(lbl)
            self._header_layout.addWidget(lbl, 0, col)
        layout.addWidget(self._header)

        # Grid area
        self._grid_widget = QWidget()
        self._grid = QGridLayout(self._grid_widget)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(0)
        for col in range(7):
            self._grid.setColumnStretch(col, 1)

        layout.addWidget(self._grid_widget, stretch=1)
        self._apply_header_style()
        self._rebuild_grid()

    def _apply_header_style(self) -> None:
        dark = _styles._dark
        bg = _styles.D_WHITE if dark else WHITE
        border = _styles.D_GRAY_BORDER if dark else GRAY_BORDER
        text2 = _styles.D_GRAY_TEXT if dark else GRAY_TEXT
        self._header.setStyleSheet(
            f"background-color: {bg}; border-bottom: 1px solid {border};"
        )
        for lbl in self._header_labels:
            lbl.setStyleSheet(
                f"font-size: 11px; font-weight: 600; color: {text2}; text-transform: uppercase;"
            )

    def apply_theme(self, dark: bool) -> None:
        """Switch between light and dark theme and rebuild."""
        _styles._dark = dark
        self._apply_header_style()
        self._rebuild_grid()

    def navigate(self, year: int, month: int) -> None:
        self._year = year
        self._month = month
        self._rebuild_grid()

    def refresh(self) -> None:
        """Reload events from DB without rebuilding the grid."""
        events = self._db.get_events_for_month(self._year, self._month)
        events_by_date: dict[str, list] = {}
        for ev in events:
            events_by_date.setdefault(ev["date"], []).append(ev)
        for cell in self._cells:
            cell.load_events(events_by_date.get(cell.date.isoformat(), []))

    def _rebuild_grid(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._cells.clear()

        cal = calendar.Calendar(firstweekday=0)
        weeks = cal.monthdatescalendar(self._year, self._month)

        while len(weeks) < 6:
            last = weeks[-1]
            weeks.append([d + datetime.timedelta(days=7) for d in last])

        for row, week in enumerate(weeks[:6]):
            self._grid.setRowStretch(row, 1)
            for col, date in enumerate(week):
                cell = DayCell(date, date.month == self._month)
                cell.day_clicked.connect(self.date_selected)
                cell.event_clicked.connect(self.event_clicked)
                self._grid.addWidget(cell, row, col)
                self._cells.append(cell)

        self.refresh()
