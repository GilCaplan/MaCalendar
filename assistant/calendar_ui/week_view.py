"""Week calendar view with hourly time slots."""

from __future__ import annotations

import datetime
import html as _html
from typing import List

from PyQt6.QtCore import Qt, QMimeData, QByteArray, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QDrag, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QGraphicsDropShadowEffect,
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
_COL_GAP = 2       # px between side-by-side overlapping event columns
_LEFT_PAD = 2
_RIGHT_PAD = 2
_TEAL_TODO = "#0e9f8c"   # deadline pill colour (matches month view)
_TODO_PILL_H = 18        # px height of each todo pill


class TimeIndicatorOverlay(QWidget):
    """Transparent overlay that paints the current-time red line on top of event blocks."""

    def __init__(self, date: datetime.date, parent: "QWidget"):
        super().__init__(parent)
        self._date = date
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAutoFillBackground(False)
        self.resize(parent.size())

    def paintEvent(self, event):
        if self._date != datetime.date.today():
            return
        now = datetime.datetime.now()
        y = int((now.hour * 60 + now.minute) / 60 * HOUR_HEIGHT)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#d13438"), 2))
        painter.setBrush(QColor("#d13438"))
        painter.drawEllipse(0, y - 5, 10, 10)
        painter.drawLine(10, y, self.width(), y)


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
        title = _html.escape(event.get("title", ""))
        self.setText(
            f"<b style='font-size:{font_size}px'>{title}</b>"
            f"<br><span style='font-size:{max(font_size-2,8)}px;"
            f"opacity:0.82'>{start}–{end}</span>"
        )
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.setStyleSheet(
            f"""
            QLabel {{
                background-color: {color};
                color: white;
                border-radius: 4px;
                padding: 3px 5px 3px 8px;
                border-left: 4px solid rgba(0,0,0,0.30);
                border-bottom: 1px solid rgba(0,0,0,0.20);
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


class _TodoPill(QLabel):
    """Small teal deadline pill shown at the top of a week-view day column."""

    def __init__(self, todo: dict, parent=None):
        super().__init__(parent)
        self._text = f"⊙ {todo.get('title', '')}"
        self.setText(self._text)
        self.setStyleSheet("background: transparent;")
        self.setToolTip(f"Task due: {todo.get('title', '')}")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(_TEAL_TODO)
        painter.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 30)))
        painter.setPen(QPen(color, 1))
        painter.drawRoundedRect(self.rect().adjusted(0, 1, -1, -2), 4, 4)
        painter.setPen(color)
        font = self.font()
        font.setPointSize(7)
        font.setBold(True)
        painter.setFont(font)
        fm = painter.fontMetrics()
        elided = fm.elidedText(self._text, Qt.TextElideMode.ElideRight, self.width() - 8)
        painter.drawText(self.rect().adjusted(4, 0, -4, 0),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided)


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
        self._events: List[dict] = []
        self._drag_hover = False
        self._ui_config = None
        self._press_y: int = -1
        self._pending_click_dt: datetime.datetime | None = None
        self.setAcceptDrops(True)
        self._apply_bg()
        self._overlay: TimeIndicatorOverlay | None = None
        if self.is_today:
            self._overlay = TimeIndicatorOverlay(self.date, self)
            self._overlay.raise_()

    def _apply_bg(self) -> None:
        dark = _styles._dark
        if self.is_today:
            bg = _styles.D_GRAY_BG if dark else "#f0f7ff"
        elif self.is_weekend:
            bg = _styles.D_WEEKEND_BG if dark else WEEKEND_BG
        else:
            bg = _styles.D_WHITE if dark else WHITE
        self.setStyleSheet(f"background-color: {bg};")

    @staticmethod
    def _to_min(t: str) -> int:
        try:
            h, m = map(int, t.split(":"))
            return h * 60 + m
        except Exception:
            return 0

    def _compute_layout(self, events: List[dict], avail_w: int):
        """Returns [(event, x, w, top, height), ...] with overlap columns."""
        if not events:
            return []

        def ev_s(ev): return self._to_min(ev.get("start_time", "0:00"))
        def ev_e(ev):
            s = ev_s(ev)
            e = self._to_min(ev.get("end_time", "0:00"))
            return max(e, s + 15)

        sorted_evs = sorted(events, key=lambda ev: (ev_s(ev), -ev_e(ev)))

        clusters: List[List[dict]] = []
        cluster: List[dict] = []
        cluster_end = -1
        for ev in sorted_evs:
            s = ev_s(ev)
            if cluster and s >= cluster_end:
                clusters.append(cluster)
                cluster = []
                cluster_end = -1
            cluster.append(ev)
            cluster_end = max(cluster_end, ev_e(ev))
        if cluster:
            clusters.append(cluster)

        result = []
        for grp in clusters:
            col_ends: List[int] = []
            ev_col: List[int] = []
            for ev in grp:
                s = ev_s(ev)
                placed = False
                for ci, ce in enumerate(col_ends):
                    if s >= ce:
                        col_ends[ci] = ev_e(ev)
                        ev_col.append(ci)
                        placed = True
                        break
                if not placed:
                    ev_col.append(len(col_ends))
                    col_ends.append(ev_e(ev))

            n_cols = len(col_ends)
            usable = avail_w - _LEFT_PAD - _RIGHT_PAD
            col_w = (usable - _COL_GAP * (n_cols - 1)) / n_cols

            for i, ev in enumerate(grp):
                ci = ev_col[i]
                s = ev_s(ev)
                e = ev_e(ev)
                top = int(s / 60 * HOUR_HEIGHT)
                height = max(int((e - s) / 60 * HOUR_HEIGHT), 20)
                x = _LEFT_PAD + int(ci * (col_w + _COL_GAP))
                w = max(int(col_w), 30)
                # +1 top / -2 height creates a 2px gap between adjacent events
                result.append((ev, x, w, top + 1, height - 2))

        return result

    def load_events(self, events: List[dict]) -> None:
        self._events = events
        for w in self._event_widgets:
            w.deleteLater()
        self._event_widgets.clear()

        fs = 11 if not self._ui_config else self._ui_config.font_week
        for ev, x, w, top, h in self._compute_layout(events, self.width()):
            block = EventBlock(ev, font_size=fs, parent=self)
            block.clicked.connect(self.event_clicked)
            block.resized.connect(self.event_rescheduled)
            block.setGeometry(x, top, w, h)
            shadow = QGraphicsDropShadowEffect()
            shadow.setBlurRadius(6)
            shadow.setOffset(0, 2)
            shadow.setColor(QColor(0, 0, 0, 55))
            block.setGraphicsEffect(shadow)
            block.show()
            self._event_widgets.append(block)
        if self._overlay:
            self._overlay.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._events:
            layout = self._compute_layout(self._events, self.width())
            for block, item in zip(self._event_widgets, layout):
                block.setGeometry(item[1], block.y(), item[2], block.height())
        if self._overlay:
            self._overlay.resize(self.size())
            self._overlay.raise_()

    def mousePressEvent(self, event):
        self._press_y = event.pos().y()

    def mouseReleaseEvent(self, event):
        if self._press_y >= 0 and abs(event.pos().y() - self._press_y) < 10:
            y = self._press_y
            hour = min(y // HOUR_HEIGHT, 23)
            minute = (y % HOUR_HEIGHT) // (HOUR_HEIGHT // 4) * 15
            self._pending_click_dt = datetime.datetime.combine(
                self.date, datetime.time(hour, minute)
            )
            QTimer.singleShot(220, self._fire_slot_click)
        self._press_y = -1

    def mouseDoubleClickEvent(self, event):
        self._pending_click_dt = None  # cancel single-click timer on double-click

    def _fire_slot_click(self):
        if self._pending_click_dt is not None:
            self.slot_double_clicked.emit(self._pending_click_dt)
            self._pending_click_dt = None

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

        # All-day strip (task deadlines) — hidden until there are due tasks
        self._allday_row = QWidget()
        self._allday_row.setVisible(False)
        self._allday_layout = QGridLayout(self._allday_row)
        self._allday_layout.setContentsMargins(LABEL_WIDTH, 2, 0, 2)
        self._allday_layout.setSpacing(0)
        layout.addWidget(self._allday_row)
        self._allday_cells: List[QWidget] = []

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

        # Refresh current-time indicator every minute
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(900_000)  # 15 minutes
        self._tick_timer.timeout.connect(self._tick_time)
        self._tick_timer.start()

    def _tick_time(self) -> None:
        for col in self._day_columns:
            if col._overlay:
                col._overlay.update()

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
        self._allday_row.setStyleSheet(
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

        week_end = self._week_start + datetime.timedelta(days=6)
        todos_by_date: dict[str, list] = {}
        for t in self._db.get_todos(include_completed=False):
            due = t.get("due_date", "")
            if due:
                try:
                    due_d = datetime.date.fromisoformat(due)
                except ValueError:
                    continue
                if self._week_start <= due_d <= week_end:
                    todos_by_date.setdefault(due, []).append(t)

        max_todos = 0
        for i, col in enumerate(self._day_columns):
            date_str = col.date.isoformat()
            col.load_events(by_date.get(date_str, []))

            todos = todos_by_date.get(date_str, [])
            max_todos = max(max_todos, len(todos))
            cell = self._allday_cells[i]
            cell_layout = cell.layout()
            while cell_layout.count():
                w = cell_layout.takeAt(0).widget()
                if w:
                    w.deleteLater()
            for todo in todos:
                pill = _TodoPill(todo)
                pill.setFixedHeight(_TODO_PILL_H)
                cell_layout.addWidget(pill)

        if max_todos > 0:
            self._allday_row.setFixedHeight(max_todos * (_TODO_PILL_H + 1) + 6)
            self._allday_row.setVisible(True)
        else:
            self._allday_row.setVisible(False)

    def _rebuild_columns(self) -> None:
        # Clear header
        while self._header_layout.count():
            item = self._header_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Clear allday strip
        while self._allday_layout.count():
            item = self._allday_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._allday_cells.clear()

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

            # Allday cell for this column
            allday_cell = QWidget()
            allday_cell_layout = QVBoxLayout(allday_cell)
            allday_cell_layout.setContentsMargins(2, 0, 2, 0)
            allday_cell_layout.setSpacing(1)
            self._allday_layout.addWidget(allday_cell, 0, i)
            self._allday_layout.setColumnStretch(i, 1)
            self._allday_cells.append(allday_cell)

        self.refresh()
        self._apply_theme_styles()
