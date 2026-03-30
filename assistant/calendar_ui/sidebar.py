"""Left sidebar — mini-calendar navigation + New Event button."""

from __future__ import annotations

import datetime

from PyQt6.QtCore import Qt, pyqtSignal, QDate
from PyQt6.QtWidgets import (
    QCalendarWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from assistant.calendar_ui.styles import BLUE, GRAY_BG, GRAY_BORDER, GRAY_DARK, GRAY_TEXT, WHITE
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
        self.apply_theme(False)

    def apply_theme(self, dark: bool) -> None:
        bg = _styles.D_GRAY_BG if dark else GRAY_BG
        text = _styles.D_GRAY_DARK if dark else GRAY_DARK
        border = _styles.D_GRAY_BORDER if dark else GRAY_BORDER
        self.setStyleSheet(
            f"""
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
            """
        )


class Sidebar(QWidget):
    """
    Left panel of the calendar app.

    Signals:
        new_event_clicked()
        date_selected(date)   — mini-calendar click
    """

    new_event_clicked = pyqtSignal()
    date_selected = pyqtSignal(datetime.date)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(200)
        self.setStyleSheet(
            f"QWidget#sidebar {{ background-color: {GRAY_BG}; border-right: 1px solid {GRAY_BORDER}; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 16, 12, 16)
        layout.setSpacing(12)

        # New Event button
        new_btn = QPushButton("+ New event")
        new_btn.setObjectName("primary")
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.clicked.connect(self.new_event_clicked)
        layout.addWidget(new_btn)

        # Mini calendar
        self._mini_cal = MiniCalendar()
        self._mini_cal.selectionChanged.connect(self._on_date_selected)
        layout.addWidget(self._mini_cal)

        # My Calendars section
        cal_header = QLabel("My Calendars")
        cal_header.setStyleSheet(
            f"font-size: 11px; font-weight: 600; color: {GRAY_TEXT}; padding-top: 8px;"
        )
        layout.addWidget(cal_header)

        dot_row = QWidget()
        dot_layout = QVBoxLayout(dot_row)
        dot_layout.setContentsMargins(4, 0, 0, 0)
        dot_layout.setSpacing(4)

        voice_cal = QLabel("● Voice Assistant")
        voice_cal.setStyleSheet(f"font-size: 12px; color: {BLUE};")
        dot_layout.addWidget(voice_cal)
        layout.addWidget(dot_row)

        layout.addStretch()

        self._cal_header = cal_header
        self._voice_cal = voice_cal

    def apply_theme(self, dark: bool) -> None:
        """Switch sidebar and mini-calendar to dark or light theme."""
        bg = _styles.D_GRAY_BG if dark else GRAY_BG
        border = _styles.D_GRAY_BORDER if dark else GRAY_BORDER
        text2 = _styles.D_GRAY_TEXT if dark else GRAY_TEXT
        self.setStyleSheet(
            f"QWidget#sidebar {{ background-color: {bg}; border-right: 1px solid {border}; }}"
        )
        self._cal_header.setStyleSheet(
            f"font-size: 11px; font-weight: 600; color: {text2}; padding-top: 8px;"
        )
        self._mini_cal.apply_theme(dark)

    def _on_date_selected(self) -> None:
        qdate = self._mini_cal.selectedDate()
        self.date_selected.emit(
            datetime.date(qdate.year(), qdate.month(), qdate.day())
        )

    def set_date(self, date: datetime.date) -> None:
        self._mini_cal.setSelectedDate(QDate(date.year, date.month, date.day))
