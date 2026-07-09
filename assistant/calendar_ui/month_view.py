"""Month calendar grid view."""

from __future__ import annotations

import calendar
import datetime
from typing import List, Optional

from PyQt6.QtCore import Qt, QMimeData, QByteArray, QPoint, pyqtSignal
from PyQt6.QtGui import QColor, QDrag, QPainter, QPen, QPixmap, QBrush
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
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
from assistant.hebrew_calendar import enumerate_holidays, hebrew_day_label

DAY_HEADERS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

_HOLIDAY_COLORS = {
    "major": "#c9a227",
    "minor": "#0e9f8c",
    "fast": "#6b7280",
    "modern": "#2563a8",
}


class HolidayBanner(QLabel):
    """All-day banner for a Jewish/Israeli holiday.

    Erev (evening-before) cells render lighter with a dashed outline, since
    the holiday has only just begun at sundown that day rather than being
    in full swing.
    """

    def __init__(self, name: str, category: str, is_erev: bool, font_size: int = 8, parent=None):
        super().__init__(parent)
        self._color = _HOLIDAY_COLORS.get(category, "#c9a227")
        self._is_erev = is_erev
        self._font_size = font_size
        self._text = f"🌙 Erev {name}" if is_erev else f"✡ {name}"
        self.setText(self._text)
        self.setFixedHeight(20)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setStyleSheet("background: transparent;")
        self.setToolTip(
            f"{name} — begins at sundown this evening" if is_erev else name
        )

    def paintEvent(self, _event):  # noqa: ARG002
        # Solid-fill + white text, same recipe as EventPill — proven legible
        # in both themes. The alpha-outlined style used earlier was nearly
        # invisible in dark mode (category color text on a near-black bg).
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(self._color)
        if self._is_erev:
            # Mostly-opaque tint + dashed border marks "begins tonight" while
            # staying readable — not the near-transparent wash used before.
            painter.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 190)))
            painter.setPen(QPen(color.darker(130), 1, Qt.PenStyle.DashLine))
        else:
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect().adjusted(0, 1, -1, -2), 4, 4)
        painter.setPen(QColor("white"))
        font = self.font()
        font.setPointSize(self._font_size)
        font.setWeight(font.Weight.DemiBold)
        painter.setFont(font)
        fm = painter.fontMetrics()
        elided = fm.elidedText(self._text, Qt.TextElideMode.ElideRight, self.width() - 8)
        painter.drawText(self.rect().adjusted(4, 0, -4, 0),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided)


class EventPill(QLabel):
    """A colored pill representing a single event in a day cell."""

    clicked = pyqtSignal(dict)

    def __init__(self, event: dict, font_size: int = 8, parent=None):
        super().__init__(parent)
        self.event = event
        self._font_size = font_size
        self._drag_start = None
        self._color = event.get("color", BLUE)
        start = event.get("start_time", "")
        self._pill_text = f"{start}  {event['title']}" if start else event['title']
        self.setText(self._pill_text)
        self.setFixedHeight(20)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setStyleSheet("background: transparent;")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(
            f"{event['title']}\n{event.get('date','')}  {start} – {event.get('end_time','')}"
        )

    def paintEvent(self, _event):  # noqa: ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(self._color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), 4, 4)
        painter.setPen(QColor(_styles.on_color(self._color)))
        font = self.font()
        font.setPointSize(self._font_size)
        font.setWeight(font.Weight.Medium)
        painter.setFont(font)
        fm = painter.fontMetrics()
        elided = fm.elidedText(self._pill_text, Qt.TextElideMode.ElideRight, self.width() - 8)
        painter.drawText(self.rect().adjusted(4, 0, -4, 0),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided)

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


TEAL = "#0e9f8c"


class TodoDeadlinePill(QLabel):
    """A read-only outlined pill showing a task deadline in a day cell."""

    def __init__(self, todo: dict, font_size: int = 8, parent=None):
        super().__init__(parent)
        self.todo = todo
        self._font_size = font_size
        self._pill_text = f"⊙ {todo['title']}"
        self.setText(self._pill_text)
        self.setFixedHeight(20)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setStyleSheet("background: transparent;")
        self.setToolTip(f"Task due: {todo['title']}")

    def paintEvent(self, _event):  # noqa: ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(TEAL)
        painter.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 28)))
        painter.setPen(QPen(color, 1))
        painter.drawRoundedRect(self.rect().adjusted(0, 1, -1, -2), 4, 4)
        painter.setPen(color)
        font = self.font()
        font.setPointSize(self._font_size)
        font.setWeight(font.Weight.Medium)
        painter.setFont(font)
        fm = painter.fontMetrics()
        elided = fm.elidedText(self._pill_text, Qt.TextElideMode.ElideRight, self.width() - 8)
        painter.drawText(self.rect().adjusted(4, 0, -4, 0),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided)


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
        self._todos: List[dict]  = []
        self._holidays: List[dict] = []
        self._ui_config       = None

        self.setMinimumHeight(88)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 3)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        is_weekend = date.weekday() in (5, 6)
        self._num_label = DayNumberLabel(date.day, self.is_today, self.is_current_month, is_weekend=is_weekend)
        header_row = QHBoxLayout()
        header_row.setSpacing(4)
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.addWidget(self._num_label)
        self._hebrew_label = QLabel()
        self._hebrew_font_size = 12
        self._apply_hebrew_label_style()
        self._hebrew_label.hide()
        header_row.addWidget(self._hebrew_label)
        header_row.addStretch()
        layout.addLayout(header_row)

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

    def set_hebrew_date(self, text: str) -> None:
        if text:
            self._hebrew_label.setText(text)
            self._hebrew_label.show()
        else:
            self._hebrew_label.hide()

    def set_hebrew_font_size(self, size: int) -> None:
        self._hebrew_font_size = size
        self._apply_hebrew_label_style()

    def _apply_hebrew_label_style(self) -> None:
        dark = _styles._dark
        color = _styles.D_GRAY_TEXT if dark else GRAY_TEXT
        self._hebrew_label.setStyleSheet(
            f"font-size: {self._hebrew_font_size}px; color: {color}; background: transparent;"
        )

    def load_events(self, events: List[dict]) -> None:
        self._events = events
        self._render_pills()

    def load_todos(self, todos: List[dict]) -> None:
        self._todos = todos
        self._render_pills()

    def load_holidays(self, holidays: List[dict]) -> None:
        self._holidays = holidays
        self._render_pills()

    def _render_pills(self) -> None:
        while self._event_layout.count():
            item = self._event_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        pill_fs = 8 if not self._ui_config else max(6, self._ui_config.font_month - 3)
        for h in self._holidays:
            banner = HolidayBanner(h["name"], h["category"], h["is_erev"], font_size=pill_fs)
            self._event_layout.addWidget(banner)

        all_items = [("event", e) for e in self._events] + [("todo", t) for t in self._todos]
        for tag, item in all_items[:3]:
            if tag == "todo":
                pill = TodoDeadlinePill(item, font_size=pill_fs)
            else:
                pill = EventPill(item, font_size=pill_fs)
                pill.clicked.connect(self.event_clicked)
            self._event_layout.addWidget(pill)
        if len(all_items) > 3:
            more_fs = 11 if not self._ui_config else self._ui_config.font_month
            text_color = _styles.D_GRAY_TEXT if _styles._dark else GRAY_TEXT
            more = QLabel(f"  +{len(all_items) - 3} more")
            more.setStyleSheet(f"font-size: {more_fs}px; color: {text_color}; padding: 0 2px;")
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
        elif self.date.weekday() in (1, 3, 5, 6):  # Tue, Thu, Sat, Sun → shaded stripe
            bg = _styles.D_WEEKEND_BG if dark else WEEKEND_BG
        else:
            bg = _styles.D_WHITE if dark else WHITE

        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(bg))
        if self._drag_hover:
            tint = QColor(BLUE)
            tint.setAlpha(70)
            painter.fillRect(self.rect(), tint)
        painter.setPen(QPen(QColor(border_color)))
        painter.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)


class DayNumberLabel(QLabel):
    """Day number — blue filled circle for today, outlined ring when selected."""

    def __init__(self, day: int, is_today: bool, is_current_month: bool = True, is_weekend: bool = False, parent=None):
        super().__init__(str(day), parent)
        self.is_today         = is_today
        self.is_current_month = is_current_month
        self.is_weekend       = is_weekend
        self._selected        = False
        self._font_size       = 12
        self.setFixedSize(26, 26)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._refresh_style()

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._refresh_style()

    def apply_ui_config(self, ui_config) -> None:
        self._font_size = ui_config.font_month + 1
        self._refresh_style()

    def _refresh_style(self) -> None:
        dark = _styles._dark
        if self.is_today:
            self.setStyleSheet(f"""
                QLabel {{
                    background-color: {TODAY_BG};
                    color: {TODAY_TEXT};
                    border-radius: 13px;
                    font-size: {self._font_size}px;
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
                    font-size: {self._font_size}px;
                    font-weight: 600;
                }}
            """)
        else:
            if self.is_current_month:
                if self.is_weekend:
                    text = _styles.DESTRUCTIVE_DARK if dark else _styles.DESTRUCTIVE
                else:
                    text = _styles.D_GRAY_DARK if dark else GRAY_DARK
            else:
                text = _styles.D_OTHER_MONTH_TEXT if dark else _styles.OTHER_MONTH_TEXT

            self.setStyleSheet(f"""
                QLabel {{
                    background: transparent;
                    border: none;
                    font-size: {self._font_size}px;
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
        self._ui_config = None
        self._hebrew_config = None

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
            header_layout.setColumnStretch(col, 1)
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
        fs = 11 if not self._ui_config else self._ui_config.font_month
        for i, lbl in enumerate(self._header_labels):
            # Sunday (0) and Saturday (6) in red
            lbl_color = (_styles.DESTRUCTIVE_DARK if dark else _styles.DESTRUCTIVE) if i in (0, 6) else color
            lbl.setStyleSheet(
                f"font-size: {fs}px; font-weight: 600; color: {lbl_color};"
            )

    def apply_theme(self, dark: bool) -> None:
        _styles._dark = dark
        self._apply_header_style()
        self._rebuild_grid()

    def apply_ui_config(self, ui_config) -> None:
        self._ui_config = ui_config
        self._apply_header_style()
        self._rebuild_grid()

    def apply_hebrew_config(self, hebrew_config) -> None:
        self._hebrew_config = hebrew_config
        self.refresh()

    def navigate(self, year: int, month: int) -> None:
        self._year  = year
        self._month = month
        self._rebuild_grid()

    def refresh(self) -> None:
        events = self._db.get_events_for_month(self._year, self._month)
        events_by_date: dict[str, list] = {}
        for ev in events:
            events_by_date.setdefault(ev["date"], []).append(ev)

        month_prefix = f"{self._year:04d}-{self._month:02d}"
        todos_by_date: dict[str, list] = {}
        for t in self._db.get_todos(include_completed=False):
            due = t.get("due_date", "")
            if due and due.startswith(month_prefix):
                todos_by_date.setdefault(due, []).append(t)

        holidays_by_date: dict[str, list] = {}
        if self._cells and self._hebrew_config and self._hebrew_config.show_holidays:
            grid_start = self._cells[0].date
            grid_end = self._cells[-1].date
            for h in enumerate_holidays(grid_start, grid_end, israel=self._hebrew_config.israel_holidays):
                d = h.gregorian_erev_start
                while d <= h.gregorian_end:
                    holidays_by_date.setdefault(d.isoformat(), []).append({
                        "name": h.name_en,
                        "category": h.category,
                        "is_erev": d == h.gregorian_erev_start,
                    })
                    d += datetime.timedelta(days=1)

        display_mode = self._hebrew_config.display_mode if self._hebrew_config else "english"

        for cell in self._cells:
            date_str = cell.date.isoformat()
            cell.load_events(events_by_date.get(date_str, []))
            cell.load_todos(todos_by_date.get(date_str, []))
            cell.load_holidays(holidays_by_date.get(date_str, []))
            if display_mode == "english":
                cell.set_hebrew_date("")
            else:
                cell.set_hebrew_date(hebrew_day_label(cell.date))

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
                cell._ui_config = self._ui_config
                if self._ui_config:
                    cell._num_label._font_size = self._ui_config.font_month + 1
                    cell._num_label._refresh_style()
                    cell.set_hebrew_font_size(max(10, self._ui_config.font_month - 1))
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
