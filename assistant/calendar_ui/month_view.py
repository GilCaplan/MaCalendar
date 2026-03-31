"""Month calendar grid view."""

from __future__ import annotations

import calendar
import datetime
from typing import List, Optional

from PyQt6.QtCore import Qt, QMimeData, QByteArray, QPoint, pyqtSignal
from PyQt6.QtGui import QColor, QDrag, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QGridLayout,
    QLabel,
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
    SELECTED_BG,
    TODAY_BG,
    TODAY_TEXT,
    WEEKEND_BG,
    WHITE,
)

DAY_HEADERS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


class EventPill(QLabel):
    """A colored pill representing a single event in a day cell."""

    clicked = pyqtSignal(dict)

    def __init__(self, event: dict, parent=None):
        super().__init__(parent)
        self.event = event
        self._drag_start = None
        color = event.get("color", BLUE)
        start = event.get("start_time", "")
        text = f"  {start}  {event['title']}" if start else f"  {event['title']}"
        self.setText(text)
        self.setFixedHeight(20)
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {color};
                color: white;
                border-radius: 4px;
                font-size: 11px;
                font-weight: 500;
                padding: 0 4px;
            }}
        """)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(
            f"{event['title']}\n{event.get('date','')}  {start} – {event.get('end_time','')}"
        )

    def mousePressEvent(self, event):
        self._drag_start = event.pos()

    def mouseMoveEvent(self, event):
        if self._drag_start is None:
            return
        if (event.pos() - self._drag_start).manhattanLength() < 8:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData("application/x-event-id", QByteArray(str(self.event["id"]).encode()))
        drag.setMimeData(mime)
        # Semi-transparent drag pixmap
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

    def mouseReleaseEvent(self, event):
        if self._drag_start is not None:
            self._drag_start = None
            self.clicked.emit(self.event)


class DayCell(QWidget):
    """One cell in the month grid."""

    day_clicked    = pyqtSignal(datetime.date)
    event_clicked  = pyqtSignal(dict)
    event_rescheduled = pyqtSignal(int, dict)

    def __init__(self, date: datetime.date, is_current_month: bool, parent=None):
        super().__init__(parent)
        self.date             = date
        self.is_current_month = is_current_month
        self.is_today         = date == datetime.date.today()
        self._selected        = False
        self._drag_hover      = False
        self._events: List[dict] = []

        self.setMinimumHeight(88)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 3)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._num_label = DayNumberLabel(date.day, self.is_today, self.is_current_month)
        layout.addWidget(self._num_label, alignment=Qt.AlignmentFlag.AlignLeft)

        self._event_layout = QVBoxLayout()
        self._event_layout.setSpacing(2)
        self._event_layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._event_layout)
        layout.addStretch()

    def set_selected(self, selected: bool) -> None:
        if self._selected != selected:
            self._selected = selected
            self._num_label.set_selected(selected)
            self.update()

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
            more = QLabel(f"  +{len(events) - 3} more")
            more.setStyleSheet(f"font-size: 11px; color: {text_color}; padding: 0 2px;")
            self._event_layout.addWidget(more)

    def mousePressEvent(self, event):
        self.day_clicked.emit(self.date)

    def mouseDoubleClickEvent(self, event):
        self.day_clicked.emit(self.date)

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
            self.event_rescheduled.emit(event_id, {"date": self.date.isoformat()})
            event.acceptProposedAction()

    def paintEvent(self, event):
        super().paintEvent(event)
        dark = _styles._dark
        border_color = _styles.D_GRAY_BORDER if dark else GRAY_BORDER

        if self._selected and not self.is_today:
            bg = _styles.D_BLUE_LIGHT if dark else SELECTED_BG
        elif self.date.weekday() % 2 == 0:   # Mon, Wed, Fri, Sun → shaded stripe
            bg = _styles.D_WEEKEND_BG if dark else WEEKEND_BG
        else:
            bg = _styles.D_WHITE if dark else WHITE

        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(bg))
        if self._drag_hover:
            painter.fillRect(self.rect(), QColor("#0078d4").lighter(190))
        painter.setPen(QPen(QColor(border_color)))
        painter.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)


class DayNumberLabel(QLabel):
    """Day number — blue filled circle for today, outlined ring when selected."""

    def __init__(self, day: int, is_today: bool, is_current_month: bool = True, parent=None):
        super().__init__(str(day), parent)
        self.is_today         = is_today
        self.is_current_month = is_current_month
        self._selected        = False
        self.setFixedSize(26, 26)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._refresh_style()

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._refresh_style()

    def _refresh_style(self) -> None:
        dark = _styles._dark
        if self.is_today:
            self.setStyleSheet(f"""
                QLabel {{
                    background-color: {TODAY_BG};
                    color: {TODAY_TEXT};
                    border-radius: 13px;
                    font-size: 12px;
                    font-weight: 700;
                }}
            """)
        elif self._selected:
            self.setStyleSheet(f"""
                QLabel {{
                    background: transparent;
                    border: 2px solid {BLUE};
                    color: {BLUE};
                    border-radius: 13px;
                    font-size: 12px;
                    font-weight: 600;
                }}
            """)
        else:
            if self.is_current_month:
                text = _styles.D_GRAY_DARK if dark else GRAY_DARK
            else:
                text = _styles.D_OTHER_MONTH_TEXT if dark else _styles.OTHER_MONTH_TEXT
            self.setStyleSheet(f"""
                QLabel {{
                    background: transparent;
                    border: none;
                    font-size: 12px;
                    font-weight: 400;
                    color: {text};
                }}
            """)


class MonthView(QWidget):
    """
    Full month calendar grid.
    Signals:
        date_selected(date)
        date_double_clicked(date)
        event_clicked(event_dict)
    """

    date_selected       = pyqtSignal(datetime.date)
    date_double_clicked = pyqtSignal(datetime.date)
    event_clicked       = pyqtSignal(dict)
    event_rescheduled   = pyqtSignal(int, dict)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self._db    = db
        self._year  = datetime.date.today().year
        self._month = datetime.date.today().month
        self._cells: List[DayCell]       = []
        self._selected_date: Optional[datetime.date] = datetime.date.today()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Day-of-week header row
        self._header = QWidget()
        self._header.setFixedHeight(30)
        self._header_labels: List[QLabel] = []
        header_layout = QGridLayout(self._header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(0)
        for col, name in enumerate(DAY_HEADERS):
            lbl = QLabel(name)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._header_labels.append(lbl)
            header_layout.addWidget(lbl, 0, col)
        layout.addWidget(self._header)

        # Grid
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
        dark   = _styles._dark
        bg     = _styles.D_WHITE       if dark else WHITE
        border = _styles.D_GRAY_BORDER if dark else GRAY_BORDER
        color  = _styles.D_GRAY_TEXT   if dark else GRAY_TEXT
        self._header.setStyleSheet(
            f"background-color: {bg}; border-bottom: 1px solid {border};"
        )
        for lbl in self._header_labels:
            lbl.setStyleSheet(
                f"font-size: 11px; font-weight: 600; color: {color}; letter-spacing: 0.5px;"
            )

    def apply_theme(self, dark: bool) -> None:
        _styles._dark = dark
        self._apply_header_style()
        self._rebuild_grid()

    def navigate(self, year: int, month: int) -> None:
        self._year  = year
        self._month = month
        self._rebuild_grid()

    def refresh(self) -> None:
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

        cal   = calendar.Calendar(firstweekday=6)
        weeks = cal.monthdatescalendar(self._year, self._month)
        while len(weeks) < 6:
            last = weeks[-1]
            weeks.append([d + datetime.timedelta(days=7) for d in last])

        for row, week in enumerate(weeks[:6]):
            self._grid.setRowStretch(row, 1)
            for col, date in enumerate(week):
                cell = DayCell(date, date.month == self._month)
                cell.set_selected(date == self._selected_date)
                cell.day_clicked.connect(self._on_cell_clicked)
                cell.event_clicked.connect(self.event_clicked)
                cell.event_rescheduled.connect(self.event_rescheduled)
                self._grid.addWidget(cell, row, col)
                self._cells.append(cell)

        self.refresh()

    def _on_cell_clicked(self, date: datetime.date) -> None:
        self._selected_date = date
        for cell in self._cells:
            cell.set_selected(cell.date == date)
        self.date_selected.emit(date)
