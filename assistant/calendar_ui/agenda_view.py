"""Agenda view — chronological list of the next 30 days' events, grouped by day."""

from __future__ import annotations

import datetime
from typing import List

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
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
    MONO_FONT,
    WHITE,
)
from assistant.hebrew_calendar import hebrew_day_label

DAYS_AHEAD = 30  # the window of upcoming days the agenda lists


class _EventRow(QFrame):
    """One compact clickable row: category color bar, times, title, location."""

    clicked = pyqtSignal(dict)

    def __init__(self, event: dict, font_size: int = 13, parent=None):
        super().__init__(parent)
        self.event = event
        self._font_size = font_size
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("agenda_row")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 5, 10, 5)
        lay.setSpacing(10)

        self._bar = QFrame()
        self._bar.setObjectName("agenda_row_bar")
        self._bar.setFixedWidth(4)
        lay.addWidget(self._bar)

        start = event.get("start_time", "") or ""
        end = event.get("end_time", "") or ""
        self._time_label = QLabel(f"{start}–{end}" if (start or end) else "")
        self._time_label.setObjectName("agenda_row_time")
        self._time_label.setFixedWidth(96)
        lay.addWidget(self._time_label)

        self._title_label = QLabel(event.get("title", ""))
        self._title_label.setObjectName("agenda_row_title")
        lay.addWidget(self._title_label)

        location = event.get("location") or ""
        self._location_label: QLabel | None = None
        if location:
            self._location_label = QLabel(f"📍 {location}")
            self._location_label.setObjectName("agenda_row_location")
            lay.addWidget(self._location_label)

        lay.addStretch()
        self.apply_style()

    def apply_style(self) -> None:
        dark = _styles._dark
        text_main = _styles.D_GRAY_DARK if dark else GRAY_DARK
        text2 = _styles.D_GRAY_TEXT if dark else GRAY_TEXT
        hover = _styles.D_GRAY_LIGHT if dark else _styles.GRAY_LIGHT
        color = self.event.get("color") or BLUE
        fs = self._font_size
        self.setStyleSheet(
            f"QFrame#agenda_row {{ background: transparent;"
            f" border-radius: {_styles.RADIUS_SM}px; }}"
            f"QFrame#agenda_row:hover {{ background-color: {hover}; }}"
            f"QFrame#agenda_row_bar {{ background-color: {color};"
            f" border-radius: 2px; }}"
            f"QLabel#agenda_row_time {{ color: {text2}; font-size: {fs - 1}px;"
            f" font-family: {MONO_FONT}; background: transparent; }}"
            f"QLabel#agenda_row_title {{ color: {text_main}; font-size: {fs}px;"
            f" font-weight: 600; background: transparent; }}"
            f"QLabel#agenda_row_location {{ color: {text2};"
            f" font-size: {fs - 1}px; background: transparent; }}"
        )

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and \
                self.rect().contains(event.pos()):
            self.clicked.emit(self.event)
        super().mouseReleaseEvent(event)


class _DayHeader(QLabel):
    """Header row for one day's group, e.g. "Sun 14 Oct" (+ Hebrew date)."""

    def __init__(self, date: datetime.date, text: str, font_size: int = 12,
                 parent=None):
        super().__init__(text, parent)
        self.date = date
        self._font_size = font_size
        self.setObjectName("agenda_day_header")
        self.apply_style()

    def apply_style(self) -> None:
        dark = _styles._dark
        text2 = _styles.D_GRAY_TEXT if dark else GRAY_TEXT
        border = _styles.D_GRAY_BORDER if dark else GRAY_BORDER
        is_today = self.date == datetime.date.today()
        color = BLUE if is_today else text2
        self.setStyleSheet(
            f"QLabel#agenda_day_header {{ color: {color};"
            f" font-size: {self._font_size}px; font-weight: 700;"
            f" padding: 10px 6px 3px 6px; background: transparent;"
            f" border-bottom: 1px solid {border}; }}"
        )


class AgendaView(QWidget):
    """
    Chronological list of the next 30 days' events, grouped by day.

    Signals:
        event_clicked(event_dict) — click on an event row opens the edit dialog
                                    (wired in CalendarWindow like the other views)
    """

    event_clicked = pyqtSignal(dict)

    def __init__(self, db, ui_config=None, parent=None):
        super().__init__(parent)
        self._db = db
        self._ui_config = ui_config
        self._hebrew_config = None
        self._start_date = datetime.date.today()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("border: none;")
        self._scroll = scroll

        body = QWidget()
        self._body = body
        self._list_layout = QVBoxLayout(body)
        self._list_layout.setContentsMargins(8, 0, 8, 12)
        self._list_layout.setSpacing(2)
        self._list_layout.addStretch()
        scroll.setWidget(body)
        layout.addWidget(scroll, stretch=1)

        # Empty state — shown instead of the (empty) list when the whole
        # window of days has nothing in it.
        self._empty_label = QLabel(f"Nothing in the next {DAYS_AHEAD} days")
        self._empty_label.setObjectName("agenda_empty")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setSizePolicy(QSizePolicy.Policy.Expanding,
                                        QSizePolicy.Policy.Expanding)
        layout.addWidget(self._empty_label, stretch=1)

        self._rows: List[_EventRow] = []
        self._headers: List[_DayHeader] = []
        self._apply_theme_styles()
        self.refresh()

    # ------------------------------------------------------------------
    # Public API (mirrors the other calendar views)
    # ------------------------------------------------------------------

    def set_start_date(self, date: datetime.date) -> None:
        """Move the 30-day window's anchor and re-query."""
        self._start_date = date
        self.refresh()

    # CalendarWindow._navigate calls navigate() on every calendar view.
    navigate = set_start_date

    def refresh(self) -> None:
        """Re-query the DB and rebuild the day-grouped list."""
        # Clear everything but the trailing stretch item.
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._rows = []
        self._headers = []

        fs = 13 if not self._ui_config else self._ui_config.font_day
        show_hebrew = bool(self._hebrew_config
                           and self._hebrew_config.display_mode != "english")

        insert_at = 0
        for offset in range(DAYS_AHEAD):
            day = self._start_date + datetime.timedelta(days=offset)
            events = self._db.get_events_for_day(day)
            if not events:
                continue

            base = day.strftime("%a %-d %b")
            if day == datetime.date.today():
                base = f"Today — {base}"
            if show_hebrew:
                heb = hebrew_day_label(day)
                if heb:
                    base = f"{base}   ·   {heb}"
            header = _DayHeader(day, base, font_size=max(10, fs - 1))
            self._list_layout.insertWidget(insert_at, header)
            insert_at += 1
            self._headers.append(header)

            for ev in sorted(events, key=lambda e: e.get("start_time", "")):
                row = _EventRow(ev, font_size=fs)
                row.clicked.connect(self.event_clicked)
                self._list_layout.insertWidget(insert_at, row)
                insert_at += 1
                self._rows.append(row)

        has_events = bool(self._rows)
        self._scroll.setVisible(has_events)
        self._empty_label.setVisible(not has_events)

    def apply_theme(self, dark: bool) -> None:
        _styles._dark = dark
        self._apply_theme_styles()
        self.refresh()

    def apply_ui_config(self, ui_config) -> None:
        self._ui_config = ui_config
        self.refresh()

    def apply_hebrew_config(self, hebrew_config) -> None:
        self._hebrew_config = hebrew_config
        self.refresh()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_theme_styles(self) -> None:
        dark = _styles._dark
        bg = _styles.D_WHITE if dark else WHITE
        text2 = _styles.D_GRAY_TEXT if dark else GRAY_TEXT
        self._body.setStyleSheet(f"background-color: {bg};")
        self._empty_label.setStyleSheet(
            f"QLabel#agenda_empty {{ color: {text2}; font-size: 14px;"
            f" background-color: {bg}; }}"
        )
