"""Left sidebar — mini-calendar navigation + New Event button."""

from __future__ import annotations

import datetime

from PyQt6.QtCore import Qt, pyqtSignal, QDate
from PyQt6.QtWidgets import (
    QCalendarWidget,
    QHeaderView,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from assistant.calendar_ui.styles import BLUE, GRAY_BG, GRAY_BORDER
import assistant.calendar_ui.styles as _styles


class MiniCalendar(QCalendarWidget):
    """Compact month-navigation calendar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setGridVisible(False)
        self.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self.setHorizontalHeaderFormat(QCalendarWidget.HorizontalHeaderFormat.ShortDayNames)
        self.setNavigationBarVisible(True)
        self.setMaximumHeight(200)

        # Force the internal table's header columns to stretch so day names fit
        table = self.findChild(QTableView)
        if table:
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        self.apply_theme(False)

    def apply_theme(self, dark: bool) -> None:
        bg     = _styles.D_GRAY_BG     if dark else GRAY_BG
        text   = _styles.D_GRAY_DARK   if dark else _styles.GRAY_DARK
        border = _styles.D_GRAY_BORDER if dark else GRAY_BORDER
        self.setStyleSheet(f"""
            QCalendarWidget {{
                background-color: {bg};
            }}
            QCalendarWidget QAbstractItemView {{
                font-size: 11px;
                background-color: {bg};
                color: {text};
                selection-background-color: {BLUE};
                selection-color: white;
            }}
            QCalendarWidget QWidget#qt_calendar_navigationbar {{
                background-color: {bg};
            }}
            QCalendarWidget QToolButton {{
                color: {text};
                font-size: 11px;
                background: transparent;
                border: none;
            }}
            QCalendarWidget QToolButton:hover {{
                background-color: {border};
                border-radius: 3px;
            }}
            QCalendarWidget QSpinBox {{
                font-size: 11px;
                color: {text};
                background-color: {bg};
            }}
        """)


class Sidebar(QWidget):
    """
    Left panel: New Event button + mini-calendar.

    Signals:
        new_event_clicked()
        date_selected(date)
    """

    new_event_clicked = pyqtSignal()
    date_selected     = pyqtSignal(datetime.date)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(240)
        self._apply_bg(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 16, 12, 16)
        layout.setSpacing(14)

        # New Event button
        new_btn = QPushButton("+ New Event")
        new_btn.setObjectName("primary")
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.clicked.connect(self.new_event_clicked)
        layout.addWidget(new_btn)

        # Mini calendar
        self._mini_cal = MiniCalendar()
        self._mini_cal.selectionChanged.connect(self._on_date_selected)
        layout.addWidget(self._mini_cal)

        layout.addStretch()

    def _apply_bg(self, dark: bool) -> None:
        bg     = _styles.D_GRAY_BG     if dark else GRAY_BG
        border = _styles.D_GRAY_BORDER if dark else GRAY_BORDER
        self.setStyleSheet(
            f"QWidget#sidebar {{ background-color: {bg}; border-right: 1px solid {border}; }}"
        )

    def apply_theme(self, dark: bool) -> None:
        self._apply_bg(dark)
        self._mini_cal.apply_theme(dark)

    def _on_date_selected(self) -> None:
        qd = self._mini_cal.selectedDate()
        self.date_selected.emit(datetime.date(qd.year(), qd.month(), qd.day()))

    def set_date(self, date: datetime.date) -> None:
        self._mini_cal.setSelectedDate(QDate(date.year, date.month, date.day))
