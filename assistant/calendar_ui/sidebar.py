"""Left sidebar — mini-calendar navigation + New Event button."""

from __future__ import annotations

import datetime

from PyQt6.QtCore import (
    QDate,
    QEasingCurve,
    QEvent,
    QPropertyAnimation,
    Qt,
    pyqtSignal,
)
from PyQt6.QtWidgets import (
    QCalendarWidget,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from assistant.calendar_ui.styles import BLUE, ON_ACCENT, GRAY_BG, GRAY_BORDER
import assistant.calendar_ui.styles as _styles


class MiniCalendar(QWidget):
    """Compact month-navigation calendar.

    Wraps a QCalendarWidget with its native navigation bar hidden — that
    bar's month/year dropdown is a plain QMenu that macOS renders mostly
    outside our stylesheet's reach (it stays light even in dark mode).
    A custom header replaces it, styled to match the rest of the app, and
    adds mouse-wheel month navigation plus a short fade transition so
    switching months feels responsive instead of an instant jump-cut.
    """

    selectionChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMaximumHeight(214)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)

        header = QHBoxLayout()
        header.setContentsMargins(2, 0, 2, 4)
        header.setSpacing(0)

        self._prev_btn = QPushButton("‹")
        self._prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._prev_btn.setFixedSize(24, 24)
        self._prev_btn.clicked.connect(lambda: self._shift_month(-1))

        self._next_btn = QPushButton("›")
        self._next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._next_btn.setFixedSize(24, 24)
        self._next_btn.clicked.connect(lambda: self._shift_month(1))

        self._month_label = QLabel()
        self._month_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        header.addWidget(self._prev_btn)
        header.addWidget(self._month_label, 1)
        header.addWidget(self._next_btn)
        outer.addLayout(header)

        self._cal = QCalendarWidget()
        self._cal.setGridVisible(False)
        self._cal.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self._cal.setHorizontalHeaderFormat(QCalendarWidget.HorizontalHeaderFormat.ShortDayNames)
        self._cal.setNavigationBarVisible(False)
        self._cal.setMaximumHeight(184)
        self._cal.currentPageChanged.connect(self._on_page_changed)
        self._cal.selectionChanged.connect(self.selectionChanged)
        outer.addWidget(self._cal)

        # Force the internal table's header columns to stretch so day names fit
        self._table = self._cal.findChild(QTableView)
        if self._table:
            self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            self._table.viewport().installEventFilter(self)

        # Fade the grid on month change instead of an instant swap
        self._opacity = QGraphicsOpacityEffect(self._cal)
        self._opacity.setOpacity(1.0)
        self._cal.setGraphicsEffect(self._opacity)
        self._fade_anim = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade_anim.setDuration(180)
        self._fade_anim.setStartValue(0.35)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._update_label()
        self.apply_theme(False)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _shift_month(self, delta: int) -> None:
        year, month = self._cal.yearShown(), self._cal.monthShown()
        month += delta
        while month < 1:
            month += 12
            year -= 1
        while month > 12:
            month -= 12
            year += 1
        self._cal.setCurrentPage(year, month)

    def _on_page_changed(self, _year: int, _month: int) -> None:
        self._update_label()
        self._fade_anim.stop()
        self._fade_anim.start()

    def _update_label(self) -> None:
        qd = QDate(self._cal.yearShown(), self._cal.monthShown(), 1)
        self._month_label.setText(qd.toString("MMMM yyyy"))

    def eventFilter(self, obj, event) -> bool:
        if self._table and obj is self._table.viewport() and event.type() == QEvent.Type.Wheel:
            self._handle_wheel(event)
            return True
        return super().eventFilter(obj, event)

    def wheelEvent(self, event) -> None:
        self._handle_wheel(event)

    def _handle_wheel(self, event) -> None:
        delta = event.angleDelta().y()
        if delta > 0:
            self._shift_month(-1)
        elif delta < 0:
            self._shift_month(1)
        event.accept()

    # ------------------------------------------------------------------
    # Public API (mirrors the QCalendarWidget surface Sidebar relies on)
    # ------------------------------------------------------------------

    def selectedDate(self) -> QDate:
        return self._cal.selectedDate()

    def setSelectedDate(self, qdate: QDate) -> None:
        self._cal.setSelectedDate(qdate)
        self._update_label()

    def apply_theme(self, dark: bool) -> None:
        bg     = _styles.D_GRAY_BG     if dark else GRAY_BG
        text   = _styles.D_GRAY_DARK   if dark else _styles.GRAY_DARK
        text2  = _styles.D_GRAY_TEXT   if dark else _styles.GRAY_TEXT
        border = _styles.D_GRAY_BORDER if dark else GRAY_BORDER
        hover  = _styles.D_GRAY_LIGHT  if dark else _styles.GRAY_LIGHT

        self._month_label.setStyleSheet(
            f"font-size: 12.5px; font-weight: 700; color: {text}; letter-spacing: -0.01em;"
        )
        nav_style = f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-radius: 6px;
                color: {text2};
                font-size: 15px;
                font-weight: 700;
            }}
            QPushButton:hover {{
                background-color: {hover};
                color: {text};
            }}
            QPushButton:pressed {{
                background-color: {border};
            }}
        """
        self._prev_btn.setStyleSheet(nav_style)
        self._next_btn.setStyleSheet(nav_style)

        self._cal.setStyleSheet(f"""
            QCalendarWidget {{
                background-color: {bg};
            }}
            QCalendarWidget QAbstractItemView {{
                font-size: 11px;
                background-color: {bg};
                color: {text};
                selection-background-color: {BLUE};
                selection-color: {ON_ACCENT};
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
