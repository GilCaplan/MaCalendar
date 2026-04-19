"""Day calendar view — single-day timeline with current time indicator."""

from __future__ import annotations

import datetime
from typing import List

from PyQt6.QtCore import Qt, QMimeData, QByteArray, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QDrag, QFont, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QGraphicsDropShadowEffect,
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

HOUR_HEIGHT = 60   # px per hour
LABEL_WIDTH = 60
RESIZE_HANDLE = 8  # px at top/bottom edge that activate resize mode
_SNAP_PX = HOUR_HEIGHT // 4  # 15-minute snap grid
_COL_GAP = 3       # px gap between side-by-side event columns
_LEFT_PAD = 4      # px left of first column
_RIGHT_PAD = 6     # px right of last column


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
        self._font_size = 12

        title_line = f"<b>{event['title']}</b>"
        time_line = f"<span style='opacity:0.85;font-size:{self._font_size - 1}px'>{start}–{end}</span>"
        html = title_line + "<br>" + time_line
        if location:
            html += f"<br><span style='opacity:0.8;font-size:{self._font_size - 1}px'>📍 {location}</span>"
        self.setText(html)
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._color = color
        self._apply_block_style()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self._drag_start = None
        self._col_x = 0        # set by DayTimeline layout
        self._col_w = 0        # set by DayTimeline layout
        # Resize state
        self._resize_edge: str | None = None  # "top" or "bottom"
        self._resize_orig_top = 0
        self._resize_orig_height = 0
        self._resize_press_y = 0  # parent-relative y at press

    def _apply_block_style(self) -> None:
        fs = self._font_size
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {self._color};
                color: white;
                border-radius: 6px;
                font-size: {fs}px;
                padding: 5px 8px 4px 10px;
                border-left: 5px solid rgba(0,0,0,0.25);
                border-bottom: 1px solid rgba(0,0,0,0.20);
            }}
        """)

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


_TEAL_TODO = "#0e9f8c"
_TODO_PILL_H = 18


class _TodoPill(QLabel):
    """Small teal deadline pill shown in the all-day strip."""

    def __init__(self, todo: dict, parent=None):
        super().__init__(parent)
        self._text = f"⊙ {todo.get('title', '')}"
        self.setText(self._text)
        self.setStyleSheet("background: transparent;")
        self.setToolTip(f"Task due: {todo.get('title', '')}")
        self.setFixedHeight(_TODO_PILL_H)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(_TEAL_TODO)
        painter.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 30)))
        painter.setPen(QPen(color, 1))
        painter.drawRoundedRect(self.rect().adjusted(0, 1, -1, -2), 4, 4)
        painter.setPen(color)
        font = self.font()
        font.setPointSize(8)
        font.setBold(True)
        painter.setFont(font)
        fm = painter.fontMetrics()
        elided = fm.elidedText(self._text, Qt.TextElideMode.ElideRight, self.width() - 8)
        painter.drawText(self.rect().adjusted(4, 0, -4, 0),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided)


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


class DayTimeline(QWidget):
    """
    Full-width single-day timeline. Draws hour lines and places event blocks.
    A transparent TimeIndicatorOverlay child renders the red current-time line
    on top of all event blocks.
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
        self._ui_config = None
        self._press_y: int = -1
        self._pending_click_dt: datetime.datetime | None = None
        self.setAcceptDrops(True)
        self._apply_bg()
        self._overlay = TimeIndicatorOverlay(self.date, self)
        self._overlay.raise_()

    def _apply_bg(self) -> None:
        dark = _styles._dark
        bg = _styles.D_WHITE if dark else WHITE
        self.setStyleSheet(f"background-color: {bg};")

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_min(t: str) -> int:
        try:
            h, m = map(int, t.split(":"))
            return h * 60 + m
        except Exception:
            return 0

    def _compute_layout(self, events: List[dict], avail_w: int):
        """
        Returns [(event, x, w, top, height), ...].
        Overlapping events are placed in side-by-side columns (Google Calendar style).
        """
        if not events:
            return []

        def ev_s(ev): return self._to_min(ev.get("start_time", "0:00"))
        def ev_e(ev):
            s = ev_s(ev)
            e = self._to_min(ev.get("end_time", "0:00"))
            return max(e, s + 15)

        sorted_evs = sorted(events, key=lambda ev: (ev_s(ev), -ev_e(ev)))

        # Split into non-overlapping clusters
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
            # Greedy column assignment within this cluster
            col_ends: List[int] = []   # latest end_min placed in each column
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
                height = max(int((e - s) / 60 * HOUR_HEIGHT), 30)
                x = _LEFT_PAD + int(ci * (col_w + _COL_GAP))
                w = max(int(col_w), 40)
                # +1 top / -2 height creates a 2px gap between adjacent events
                result.append((ev, x, w, top + 1, height - 2))

        return result

    # ------------------------------------------------------------------

    def load_events(self, events: List[dict]) -> None:
        self._events = events  # store for re-layout on resize
        for w in self._event_widgets:
            w.deleteLater()
        self._event_widgets.clear()

        fs = 12 if not self._ui_config else self._ui_config.font_day
        layout = self._compute_layout(events, self.width())

        for ev, x, w, top, h in layout:
            block = EventBlock(ev, self)
            block._font_size = fs
            block._color = ev.get("color", BLUE)
            block._apply_block_style()
            block._col_x = x
            block._col_w = w
            block.clicked.connect(self.event_clicked)
            block.resized.connect(self.event_rescheduled)
            block.setGeometry(x, top, w, h)
            shadow = QGraphicsDropShadowEffect()
            shadow.setBlurRadius(8)
            shadow.setOffset(0, 2)
            shadow.setColor(QColor(0, 0, 0, 55))
            block.setGraphicsEffect(shadow)
            block.show()
            self._event_widgets.append(block)
        self._overlay.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Re-run full layout so column widths scale correctly
        if self._event_widgets and hasattr(self, "_events"):
            layout = self._compute_layout(self._events, self.width())
            for block, item in zip(self._event_widgets, layout):
                x, w = item[1], item[2]
                block._col_x = x
                block._col_w = w
                block.setGeometry(x, block.y(), w, block.height())
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
        self._pending_click_dt = None  # cancel single-click on double-click

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

    def dragLeaveEvent(self, _event):
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
        self._ui_config = None

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

        # ── All-day strip (task deadlines) ───────────────────────────────
        self._allday_strip = QWidget()
        self._allday_strip.setVisible(False)
        self._allday_strip_layout = QHBoxLayout(self._allday_strip)
        self._allday_strip_layout.setContentsMargins(LABEL_WIDTH + 4, 3, 8, 3)
        self._allday_strip_layout.setSpacing(4)
        layout.addWidget(self._allday_strip)

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
        self._refresh_allday()

    def _refresh_allday(self) -> None:
        layout = self._allday_strip_layout
        while layout.count():
            w = layout.takeAt(0).widget()
            if w:
                w.deleteLater()

        date_str = self._date.isoformat()
        todos = [
            t for t in self._db.get_todos(include_completed=False)
            if t.get("due_date", "")[:10] == date_str
        ]
        if todos:
            for todo in todos:
                pill = _TodoPill(todo)
                layout.addWidget(pill)
            layout.addStretch()
            self._allday_strip.setFixedHeight(_TODO_PILL_H + 8)
            self._allday_strip.setVisible(True)
        else:
            self._allday_strip.setVisible(False)

    def apply_theme(self, dark: bool) -> None:
        _styles._dark = dark
        self._apply_theme_styles()
        if self._timeline:
            self._timeline._apply_bg()
        self.refresh()

    def apply_ui_config(self, ui_config) -> None:
        self._ui_config = ui_config
        self._apply_theme_styles()
        if self._timeline:
            self._timeline._ui_config = ui_config
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
            self._timeline._overlay.update()

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
        self._allday_strip.setStyleSheet(
            f"background-color: {bg}; border-bottom: 1px solid {border};"
        )
        self._time_col.setStyleSheet(f"background-color: {bg};")
        fs = 11 if not self._ui_config else self._ui_config.font_day - 2
        for lbl in self._time_labels:
            lbl.setStyleSheet(f"font-size: {fs}px; color: {text2}; padding-top: 2px;")
        
        main_fs = 14 if not self._ui_config else self._ui_config.font_day + 1
        font = self._date_label.font()
        font.setPointSize(main_fs)
        self._date_label.setFont(font)
        self._date_label.setStyleSheet(f"color: {text_main};")
        self._count_label.setStyleSheet(f"color: {text2};")
