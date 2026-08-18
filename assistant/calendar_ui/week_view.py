"""Week calendar view with hourly time slots."""

from __future__ import annotations

import datetime
import html as _html
import time as _time
from typing import List

from PyQt6.QtCore import Qt, QEvent, QMimeData, QByteArray, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QDrag, QFont, QFontMetrics, QPainter, QPen, QPixmap
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
from assistant.calendar_ui.month_view import HolidayBanner
from assistant.hebrew_calendar import enumerate_holidays, hebrew_day_label

HOUR_HEIGHT = 48       # px per hour at full size (also the ceiling when compressing)
MIN_HOUR_HEIGHT = 22   # px per hour floor before the view falls back to scrolling
LABEL_WIDTH = 52   # px for time labels on left
RESIZE_HANDLE = 7  # px at top/bottom edge that activate resize mode
_COL_GAP = 2       # px between side-by-side overlapping event columns
_LEFT_PAD = 2
_RIGHT_PAD = 2
_TEAL_TODO = "#0e9f8c"   # deadline pill colour (matches month view)


class TimeIndicatorOverlay(QWidget):
    """Transparent overlay that paints the current-time red line on top of event blocks."""

    def __init__(self, date: datetime.date, parent: "QWidget", hour_height: int = HOUR_HEIGHT):
        super().__init__(parent)
        self._date = date
        self._hour_height = hour_height
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAutoFillBackground(False)
        self.resize(parent.size())

    def set_hour_height(self, hour_height: int) -> None:
        self._hour_height = hour_height
        self.update()

    def paintEvent(self, event):
        if self._date != datetime.date.today():
            return
        now = datetime.datetime.now()
        y = int((now.hour * 60 + now.minute) / 60 * self._hour_height)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        accent = QColor(BLUE)

        # Soft glow halo behind the dot, for a less jarring, more
        # integrated feel against the event blocks it sits on top of.
        glow = QColor(accent)
        glow.setAlpha(50)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(-4, y - 9, 18, 18)

        # A faint dark halo under the line keeps it legible when it
        # crosses an event block in the same accent color family.
        halo = QColor(0, 0, 0, 70)
        halo_pen = QPen(halo, 3)
        halo_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(halo_pen)
        painter.drawLine(10, y, self.width(), y)

        # Thin, slightly translucent line with round caps.
        line_color = QColor(accent)
        line_color.setAlpha(210)
        pen = QPen(line_color, 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(10, y, self.width(), y)

        # Solid dot marking "now" at the left edge.
        painter.setPen(QPen(accent, 1))
        painter.setBrush(accent)
        painter.drawEllipse(0, y - 5, 10, 10)


class EventBlock(QLabel):
    """Colored block representing an event in the week grid."""

    clicked = pyqtSignal(dict)
    resized = pyqtSignal(int, dict)  # (event_id, {start_time, end_time})

    # Roomy padding is used when there's space for the full two-line
    # title+time label; tight padding kicks in for compact, short-event
    # blocks so every spare pixel goes to the text instead of whitespace.
    # Each tuple is (top, right, bottom, left) to match CSS padding order.
    _PAD_ROOMY = (3, 5, 3, 8)
    _PAD_TIGHT = (1, 4, 1, 6)

    def __init__(self, event: dict, font_size: int = 11, hour_height: int = HOUR_HEIGHT, parent=None):
        super().__init__(parent)
        self.event = event
        self._color = event.get("color", BLUE)
        self._title_raw = event.get("title", "")
        self._title_html = _html.escape(self._title_raw)
        self._start = event.get("start_time", "")
        self._end = event.get("end_time", "")
        self._font_size = font_size
        self._hour_height = hour_height
        self._drag_start = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        # Resize state
        self._resize_edge: str | None = None  # "top" or "bottom"
        self._resize_orig_top = 0
        self._resize_orig_height = 0
        self._resize_press_y = 0  # parent-relative y at press
        self._update_display()

    def _apply_style(self, pad: tuple[int, int, int, int]) -> None:
        top, right, bottom, left = pad
        self.setStyleSheet(
            f"""
            QLabel {{
                background-color: {self._color};
                color: {_styles.on_color(self._color)};
                border-radius: 4px;
                padding: {top}px {right}px {bottom}px {left}px;
                border-left: 4px solid rgba(0,0,0,0.30);
                border-bottom: 1px solid rgba(0,0,0,0.20);
            }}
            """
        )

    def _update_display(self) -> None:
        """Pick a one-line or two-line label depending on the block's actual
        height, so events stay readable no matter how short their duration or
        how far the user has dragged a resize handle. Runs from resizeEvent,
        so it re-evaluates live during interactive resize, window resize, and
        the initial layout pass alike."""
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return

        title_font = QFont(self.font())
        title_font.setPixelSize(self._font_size)
        title_font.setBold(True)
        title_fm = QFontMetrics(title_font)

        sub_size = max(self._font_size - 2, 8)
        sub_font = QFont(self.font())
        sub_font.setPixelSize(sub_size)
        sub_fm = QFontMetrics(sub_font)

        def content_h(pad):
            return h - pad[0] - pad[2] - 1  # -1 for the border-bottom

        two_line_h = title_fm.height() + 2 + sub_fm.height()

        if content_h(self._PAD_ROOMY) >= two_line_h:
            self._apply_style(self._PAD_ROOMY)
            self.setFont(QFont())  # let the rich-text spans own size/weight
            self.setWordWrap(True)
            self.setTextFormat(Qt.TextFormat.RichText)
            self.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            self.setText(
                f"<b style='font-size:{self._font_size}px'>{self._title_html}</b>"
                f"<br><span style='font-size:{sub_size}px;"
                f"opacity:0.82'>{self._start}–{self._end}</span>"
            )
        else:
            # Not enough vertical room for both lines: drop the time-range
            # subtitle and show a single, vertically-centered, elided title
            # instead of letting the two-line rich text get clipped.
            pad = self._PAD_TIGHT
            self._apply_style(pad)
            self.setFont(title_font)
            self.setWordWrap(False)
            self.setTextFormat(Qt.TextFormat.PlainText)
            self.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            avail_w = max(w - pad[1] - pad[3] - 4, 10)  # -4 for the border-left strip
            elided = title_fm.elidedText(self._title_raw, Qt.TextElideMode.ElideRight, avail_w)
            self.setText(elided)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_display()

    @property
    def _snap_px(self) -> int:
        return max(self._hour_height // 4, 3)  # 15-minute snap grid

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
            snap_px = self._snap_px
            parent_y = self.mapToParent(event.pos()).y()
            delta = parent_y - self._resize_press_y
            min_h = max(snap_px, 18)
            orig_bottom = self._resize_orig_top + self._resize_orig_height

            if self._resize_edge == "bottom":
                raw_bottom = orig_bottom + delta
                snapped_bottom = round(raw_bottom / snap_px) * snap_px
                new_h = max(snapped_bottom - self._resize_orig_top, min_h)
                self.setGeometry(self.x(), self._resize_orig_top, self.width(), new_h)
            else:  # top
                raw_top = self._resize_orig_top + delta
                snapped_top = round(raw_top / snap_px) * snap_px
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
            start_min = round(top / self._hour_height * 60)
            end_min = round(bottom / self._hour_height * 60)
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

    def __init__(self, todo: dict, font_size: int = 9, parent=None):
        super().__init__(parent)
        self._text = f"⊙ {todo.get('title', '')}"
        self._font_size = font_size
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
        font.setPointSize(self._font_size)
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
        self.hour_height = HOUR_HEIGHT
        self.setMinimumWidth(80)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(self.hour_height * 24)

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
            self._overlay = TimeIndicatorOverlay(self.date, self, hour_height=self.hour_height)
            self._overlay.raise_()

    def _apply_bg(self) -> None:
        dark = _styles._dark
        if self.is_today:
            bg = _styles.D_BLUE_LIGHT if dark else BLUE_LIGHT
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

    def _compute_layout(self, events: List[dict], avail_w: int, font_size: int = 11):
        """Returns [(event, x, w, top, height), ...] with overlap columns."""
        if not events:
            return []

        # Floor scales with the configured font so a larger Week font size
        # still leaves room for at least one readable line; EventBlock itself
        # adapts its label (drops the time subtitle) whenever a block ends up
        # too short for two lines, so this only needs to guarantee that much.
        min_block_h = max(20, font_size + 9)

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
                top = int(s / 60 * self.hour_height)
                height = max(int((e - s) / 60 * self.hour_height), min_block_h)
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
        self._fs = fs
        for ev, x, w, top, h in self._compute_layout(events, self.width(), fs):
            block = EventBlock(ev, font_size=fs, hour_height=self.hour_height, parent=self)
            block.clicked.connect(self.event_clicked)
            block.resized.connect(self.event_rescheduled)
            block.setGeometry(x, top, w, h)
            # setGeometry() on a still-hidden widget doesn't reliably deliver
            # a resizeEvent, so refresh the label content explicitly instead
            # of trusting resizeEvent alone for this first layout pass.
            block._update_display()
            shadow = QGraphicsDropShadowEffect()
            shadow.setBlurRadius(6)
            shadow.setOffset(0, 2)
            shadow.setColor(QColor(0, 0, 0, 55))
            block.setGraphicsEffect(shadow)
            block.show()
            self._event_widgets.append(block)
        if self._overlay:
            self._overlay.raise_()

    def set_hour_height(self, hour_height: int) -> None:
        """Rescale this column's timeline (called by WeekView when the window is resized)."""
        if hour_height == self.hour_height:
            return
        self.hour_height = hour_height
        self.setFixedHeight(hour_height * 24)
        if self._overlay:
            self._overlay.set_hour_height(hour_height)
        if self._events:
            self.load_events(self._events)
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._events:
            layout = self._compute_layout(self._events, self.width(), getattr(self, "_fs", 11))
            for block, item in zip(self._event_widgets, layout):
                block.setGeometry(item[1], block.y(), item[2], block.height())
                block._update_display()
        if self._overlay:
            self._overlay.resize(self.size())
            self._overlay.raise_()

    def mousePressEvent(self, event):
        self._press_y = event.pos().y()

    def mouseReleaseEvent(self, event):
        if self._press_y >= 0 and abs(event.pos().y() - self._press_y) < 10:
            y = self._press_y
            hour = min(y // self.hour_height, 23)
            minute = (y % self.hour_height) // (self.hour_height // 4) * 15
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
            total_min = int(y / self.hour_height * 60)
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
            y = h * self.hour_height
            painter.drawLine(0, y, self.width(), y)
        # Right border
        painter.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
        if self._drag_hover:
            tint = QColor(BLUE)
            tint.setAlpha(70)
            painter.fillRect(self.rect(), tint)


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
        self._hebrew_config = None
        self._hour_height = HOUR_HEIGHT

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
        time_col.setFixedHeight(self._hour_height * 24)
        self._time_labels: List[QLabel] = []
        time_layout = QVBoxLayout(time_col)
        time_layout.setContentsMargins(0, 0, 4, 0)
        time_layout.setSpacing(0)
        for h in range(24):
            lbl = QLabel("12 AM" if h == 0 else f"{h} AM" if h < 12 else "12 PM" if h == 12 else f"{h-12} PM")
            lbl.setFixedHeight(self._hour_height)
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
        self._scroll = scroll

        # Compress hour rows to fit the available height instead of always
        # scrolling — recalculated whenever the scroll viewport is resized.
        scroll.viewport().installEventFilter(self)

        # Scroll to 8am on load
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(100, lambda: scroll.verticalScrollBar().setValue(self._hour_height * 8))
        QTimer.singleShot(0, lambda: self._recalc_hour_height(scroll.viewport().height()))

        self._rebuild_columns()
        self._apply_theme_styles()

        # Refresh current-time indicator every minute
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(60_000)
        self._tick_timer.timeout.connect(self._tick_time)
        self._tick_timer.start()

    def eventFilter(self, obj, event):
        if obj is self._scroll.viewport() and event.type() == QEvent.Type.Resize:
            self._recalc_hour_height(event.size().height())
        return super().eventFilter(obj, event)

    def _recalc_hour_height(self, viewport_h: int) -> None:
        """Shrink/grow the hour-row height so the full day fits the window when
        possible, only falling back to scrolling below MIN_HOUR_HEIGHT."""
        if viewport_h <= 0:
            return
        new_h = max(MIN_HOUR_HEIGHT, min(HOUR_HEIGHT, viewport_h // 24))
        if new_h == self._hour_height:
            return
        self._hour_height = new_h
        self._time_col.setFixedHeight(new_h * 24)
        for lbl in self._time_labels:
            lbl.setFixedHeight(new_h)
        for col in self._day_columns:
            col.set_hour_height(new_h)

    def _tick_time(self) -> None:
        # Re-sync to the OS timezone in case it changed while the app was
        # running (e.g. laptop travel) — datetime.now() can otherwise keep
        # using the zone that was active when the process started.
        _time.tzset()
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

    def apply_hebrew_config(self, hebrew_config) -> None:
        self._hebrew_config = hebrew_config
        self._rebuild_columns()
        self.refresh()

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

        holidays_by_date: dict[str, list] = {}
        if self._hebrew_config and self._hebrew_config.show_holidays:
            for h in enumerate_holidays(self._week_start, week_end, israel=self._hebrew_config.israel_holidays):
                d = h.gregorian_erev_start
                while d <= h.gregorian_end:
                    holidays_by_date.setdefault(d.isoformat(), []).append(h)
                    d += datetime.timedelta(days=1)

        # Deadline/holiday pills default larger than the old hardcoded 7pt —
        # and now scale with the user's configured Week font size like every
        # other element in this view already does, instead of ignoring it.
        pill_fs = 9 if not self._ui_config else max(8, self._ui_config.font_week - 2)
        pill_h = 20 if not self._ui_config else max(20, self._ui_config.font_week + 8)

        max_items = 0
        for i, col in enumerate(self._day_columns):
            date_str = col.date.isoformat()
            col.load_events(by_date.get(date_str, []))

            todos = todos_by_date.get(date_str, [])
            holidays = holidays_by_date.get(date_str, [])
            max_items = max(max_items, len(todos) + len(holidays))
            cell = self._allday_cells[i]
            cell_layout = cell.layout()
            while cell_layout.count():
                w = cell_layout.takeAt(0).widget()
                if w:
                    w.deleteLater()
            for h in holidays:
                is_erev = col.date == h.gregorian_erev_start
                banner = HolidayBanner(h.name_en, h.category, is_erev, font_size=pill_fs)
                banner.setFixedHeight(pill_h)
                cell_layout.addWidget(banner)
            for todo in todos:
                pill = _TodoPill(todo, font_size=pill_fs)
                pill.setFixedHeight(pill_h)
                cell_layout.addWidget(pill)

        if max_items > 0:
            self._allday_row.setFixedHeight(max_items * (pill_h + 1) + 6)
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

            if self._hebrew_config and self._hebrew_config.display_mode != "english":
                hebrew_lbl = QLabel(hebrew_day_label(date))
                hebrew_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                hebrew_lbl.setStyleSheet(f"font-size: 10px; color: {text2};")
                header_layout.addWidget(hebrew_lbl)

            self._header_layout.addWidget(header_cell, 0, i)
            self._header_layout.setColumnStretch(i, 1)

            # Day column
            col = DayColumn(date)
            col._ui_config = self._ui_config
            if self._hour_height != col.hour_height:
                col.set_hour_height(self._hour_height)
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
