"""
Timer view — track work sessions, compute earnings, manage sub-sessions.

Layout
------
TimerView (QWidget)
  ├─ top bar: "New Timer" button + daily summary label
  └─ scroll area → VBox of TimerCard widgets

TimerCard (QWidget)
  ├─ header row: color dot | title (editable) | elapsed | earnings | action btns | expand ▸
  └─ SessionsPanel (collapsible)
       ├─ SessionRow per session (title, date, start→end, duration, split, delete)
       └─ "Add session" button

A single 1-second QTimer in TimerView drives all live displays.
"""

from __future__ import annotations

import datetime
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QDoubleSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QDateTimeEdit,
    QColorDialog,
)

from assistant.db import CalendarDB

# ---------------------------------------------------------------------------
# Currency data  (code → (display name, symbol))
# ILS is default; list is sorted so ILS appears first in the picker.
# ---------------------------------------------------------------------------
_CURRENCIES: dict[str, tuple[str, str]] = {
    "ILS": ("Israeli Shekel",         "₪"),
    "USD": ("US Dollar",              "$"),
    "EUR": ("Euro",                   "€"),
    "GBP": ("British Pound",          "£"),
    "JPY": ("Japanese Yen",           "¥"),
    "CAD": ("Canadian Dollar",        "CA$"),
    "AUD": ("Australian Dollar",      "A$"),
    "CHF": ("Swiss Franc",            "CHF"),
    "CNY": ("Chinese Yuan",           "¥"),
    "INR": ("Indian Rupee",           "₹"),
    "BRL": ("Brazilian Real",         "R$"),
    "MXN": ("Mexican Peso",           "MX$"),
    "KRW": ("South Korean Won",       "₩"),
    "SGD": ("Singapore Dollar",       "S$"),
    "HKD": ("Hong Kong Dollar",       "HK$"),
    "SEK": ("Swedish Krona",          "kr"),
    "NOK": ("Norwegian Krone",        "kr"),
    "DKK": ("Danish Krone",           "kr"),
    "NZD": ("New Zealand Dollar",     "NZ$"),
    "ZAR": ("South African Rand",     "R"),
    "AED": ("UAE Dirham",             "د.إ"),
    "SAR": ("Saudi Riyal",            "﷼"),
    "QAR": ("Qatari Riyal",           "﷼"),
    "KWD": ("Kuwaiti Dinar",          "KD"),
    "BHD": ("Bahraini Dinar",         "BD"),
    "JOD": ("Jordanian Dinar",        "JD"),
    "EGP": ("Egyptian Pound",         "E£"),
    "TRY": ("Turkish Lira",           "₺"),
    "RUB": ("Russian Ruble",          "₽"),
    "PLN": ("Polish Złoty",           "zł"),
    "UAH": ("Ukrainian Hryvnia",      "₴"),
    "THB": ("Thai Baht",              "฿"),
    "IDR": ("Indonesian Rupiah",      "Rp"),
    "MYR": ("Malaysian Ringgit",      "RM"),
    "PHP": ("Philippine Peso",        "₱"),
    "VND": ("Vietnamese Dong",        "₫"),
    "TWD": ("Taiwan Dollar",          "NT$"),
    "CZK": ("Czech Koruna",           "Kč"),
    "HUF": ("Hungarian Forint",       "Ft"),
    "RON": ("Romanian Leu",           "lei"),
    "CLP": ("Chilean Peso",           "CL$"),
    "COP": ("Colombian Peso",         "CO$"),
    "ARS": ("Argentine Peso",         "AR$"),
    "PEN": ("Peruvian Sol",           "S/."),
    "NGN": ("Nigerian Naira",         "₦"),
    "PKR": ("Pakistani Rupee",        "₨"),
    "BDT": ("Bangladeshi Taka",       "৳"),
    "ISK": ("Icelandic Króna",        "kr"),
}

_DEFAULT_CURRENCY = "ILS"


def _currency_symbol(code: str) -> str:
    return _CURRENCIES.get(code, ("", code))[1]


# Palette of colours for new timers (cycles through)
_TIMER_COLORS = [
    "#1a6fc4",  # blue
    "#108010",  # green
    "#c83b01",  # red-orange
    "#7c58b0",  # purple
    "#028385",  # teal
    "#b034a8",  # pink
    "#b84e0e",  # orange
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _duration_secs(start_iso: str, end_iso: Optional[str]) -> float:
    """Seconds between start and end (or now if end is None)."""
    try:
        s = datetime.datetime.fromisoformat(start_iso)
        e = datetime.datetime.fromisoformat(end_iso) if end_iso else datetime.datetime.now()
        return max(0.0, (e - s).total_seconds())
    except Exception:
        return 0.0


def _fmt_duration(total_seconds: float) -> str:
    """Format seconds as HH:MM:SS."""
    total = int(total_seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def _fmt_earnings(total_seconds: float, hourly_rate: float, currency: str = "ILS") -> str:
    if hourly_rate <= 0:
        return ""
    earned = (total_seconds / 3600) * hourly_rate
    symbol = _currency_symbol(currency)
    return f"{symbol}{earned:,.2f}"


def _fmt_datetime_short(iso: str) -> str:
    """'2025-04-15T14:30:00' → 'Apr 15, 2:30 PM'"""
    try:
        dt = datetime.datetime.fromisoformat(iso)
        today = datetime.date.today()
        if dt.date() == today:
            return dt.strftime("%-I:%M %p")
        elif dt.date().year == today.year:
            return dt.strftime("%b %-d, %-I:%M %p")
        else:
            return dt.strftime("%b %-d %Y, %-I:%M %p")
    except Exception:
        return iso


def _sessions_total_secs(sessions: list[dict]) -> float:
    """Sum of all session durations (open sessions counted to now)."""
    return sum(_duration_secs(s["start_time"], s.get("end_time")) for s in sessions)


# ---------------------------------------------------------------------------
# Currency picker widget (searchable inline list)
# ---------------------------------------------------------------------------

class CurrencyPicker(QWidget):
    """Searchable inline list for selecting a currency code."""

    def __init__(self, current: str = _DEFAULT_CURRENCY, parent=None):
        super().__init__(parent)
        from PyQt6.QtWidgets import QListWidget

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search currency…")
        self._search.setClearButtonEnabled(True)
        layout.addWidget(self._search)

        self._list = QListWidget()
        self._list.setFixedHeight(130)
        self._list.setAlternatingRowColors(True)
        layout.addWidget(self._list)

        self._all_items: list[tuple[str, str]] = []   # (code, display text)
        for code, (name, symbol) in _CURRENCIES.items():
            display = f"{code}  {symbol}  —  {name}"
            self._all_items.append((code, display))

        self._populate(current)
        self._search.textChanged.connect(lambda t: self._populate(current if not t else None, query=t))

    def _populate(self, select_code: Optional[str], query: str = "") -> None:
        from PyQt6.QtWidgets import QListWidgetItem
        self._list.clear()
        q = query.strip().lower()
        for code, display in self._all_items:
            if q and q not in code.lower() and q not in display.lower():
                continue
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, code)
            self._list.addItem(item)
            if code == select_code:
                self._list.setCurrentItem(item)
        if self._list.currentItem() is None and self._list.count():
            self._list.setCurrentRow(0)

    @property
    def selected_code(self) -> str:
        item = self._list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else _DEFAULT_CURRENCY


# ---------------------------------------------------------------------------
# New / Edit Timer dialog
# ---------------------------------------------------------------------------

class TimerDialog(QDialog):
    """
    Create or edit a timer.

    Work timers  → show hourly rate + currency picker → earnings displayed on card.
    Personal timers → no rate/currency → no earnings shown.
    """

    def __init__(
        self,
        parent=None,
        *,
        title: str = "",
        timer_type: str = "work",
        hourly_rate: float = 0.0,
        currency: str = _DEFAULT_CURRENCY,
        color: str = "#1a6fc4",
    ):
        super().__init__(parent)
        self.setWindowTitle("Timer Settings")
        self.setMinimumWidth(380)

        self._color = color
        self._timer_type = timer_type

        root = QVBoxLayout(self)
        root.setSpacing(14)

        # ── Type selector ───────────────────────────────────────────────
        type_box = QWidget()
        type_layout = QHBoxLayout(type_box)
        type_layout.setContentsMargins(0, 0, 0, 0)
        type_layout.setSpacing(0)

        self._work_btn = QPushButton("💼  Work")
        self._work_btn.setCheckable(True)
        self._work_btn.setFixedHeight(32)
        self._work_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._work_btn.clicked.connect(lambda: self._set_type("work"))

        self._personal_btn = QPushButton("🏠  Personal")
        self._personal_btn.setCheckable(True)
        self._personal_btn.setFixedHeight(32)
        self._personal_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._personal_btn.clicked.connect(lambda: self._set_type("personal"))

        type_layout.addWidget(self._work_btn)
        type_layout.addWidget(self._personal_btn)
        root.addWidget(type_box)

        # ── Basic fields ────────────────────────────────────────────────
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(10)

        self._title_edit = QLineEdit(title)
        self._title_edit.setPlaceholderText("e.g. Client Project, Reading, Gym…")
        form.addRow("Title:", self._title_edit)

        color_row = QHBoxLayout()
        self._color_btn = QPushButton()
        self._color_btn.setFixedSize(32, 24)
        self._color_btn.setToolTip("Pick colour")
        self._color_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._color_btn.clicked.connect(self._pick_color)
        self._apply_color_btn()
        color_row.addWidget(self._color_btn)
        color_row.addStretch()
        form.addRow("Colour:", color_row)

        root.addLayout(form)

        # ── Earnings section (work only) ────────────────────────────────
        self._earnings_box = QWidget()
        earn_form = QFormLayout(self._earnings_box)
        earn_form.setContentsMargins(0, 0, 0, 0)
        earn_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        earn_form.setSpacing(10)

        self._rate_spin = QDoubleSpinBox()
        self._rate_spin.setRange(0, 99999)
        self._rate_spin.setDecimals(2)
        self._rate_spin.setSingleStep(5)
        self._rate_spin.setValue(hourly_rate)
        self._rate_spin.setSuffix(" / hr")
        self._rate_spin.setSpecialValueText("No rate set")
        earn_form.addRow("Hourly rate:", self._rate_spin)

        self._currency_picker = CurrencyPicker(currency, self)
        earn_form.addRow("Currency:", self._currency_picker)

        root.addWidget(self._earnings_box)

        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(line)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        # Apply initial state
        self._set_type(timer_type)

    # ------------------------------------------------------------------

    def _set_type(self, t: str) -> None:
        self._timer_type = t
        is_work = (t == "work")
        self._work_btn.setChecked(is_work)
        self._personal_btn.setChecked(not is_work)
        self._work_btn.setStyleSheet(
            "background:#1a6fc4; color:white; border-radius:4px 0 0 4px; font-weight:bold;"
            if is_work else
            "background:transparent; border:1px solid #aaa; border-radius:4px 0 0 4px;"
        )
        self._personal_btn.setStyleSheet(
            "background:#1a6fc4; color:white; border-radius:0 4px 4px 0; font-weight:bold;"
            if not is_work else
            "background:transparent; border:1px solid #aaa; border-radius:0 4px 4px 0;"
        )
        self._earnings_box.setVisible(is_work)
        self.adjustSize()

    def _pick_color(self) -> None:
        c = QColorDialog.getColor(QColor(self._color), self, "Pick Timer Colour")
        if c.isValid():
            self._color = c.name()
            self._apply_color_btn()

    def _apply_color_btn(self) -> None:
        self._color_btn.setStyleSheet(
            f"background-color: {self._color}; border: 1px solid #aaa; border-radius: 4px;"
        )

    @property
    def result_title(self) -> str:
        return self._title_edit.text().strip() or "Untitled Timer"

    @property
    def result_type(self) -> str:
        return self._timer_type

    @property
    def result_rate(self) -> float:
        return self._rate_spin.value() if self._timer_type == "work" else 0.0

    @property
    def result_currency(self) -> str:
        return self._currency_picker.selected_code if self._timer_type == "work" else _DEFAULT_CURRENCY

    @property
    def result_color(self) -> str:
        return self._color


# ---------------------------------------------------------------------------
# Log past time dialog  (duration-first, no need to specify exact datetimes)
# ---------------------------------------------------------------------------

class LogTimeDialog(QDialog):
    """
    Quick-log a past work block by duration rather than exact timestamps.

    Fields
    ------
    Session title  – optional label for this block of work
    Hours / mins   – how long you worked
    End date/time  – when you finished (defaults to right now so you can
                     say "I just finished 2 h of work")
    Notes          – optional free-text
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Log Past Time")
        self.setMinimumWidth(360)

        root = QVBoxLayout(self)
        root.setSpacing(12)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(10)

        # Session title
        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("e.g. Code review, Meeting, Writing… (optional)")
        form.addRow("What:", self._title_edit)

        # Duration row: [hours] h  [minutes] m
        dur_row = QHBoxLayout()
        from PyQt6.QtWidgets import QSpinBox as _QSpinBox
        self._hours_spin = _QSpinBox()
        self._hours_spin.setRange(0, 99)
        self._hours_spin.setSuffix(" h")
        self._hours_spin.setFixedWidth(72)
        self._hours_spin.setValue(1)
        dur_row.addWidget(self._hours_spin)
        dur_row.addSpacing(6)
        self._mins_spin = _QSpinBox()
        self._mins_spin.setRange(0, 59)
        self._mins_spin.setSuffix(" m")
        self._mins_spin.setFixedWidth(72)
        self._mins_spin.setValue(0)
        dur_row.addWidget(self._mins_spin)
        dur_row.addStretch()
        form.addRow("Duration:", dur_row)

        # Ended at (defaults to now, optional)
        from PyQt6.QtWidgets import QCheckBox as _QCheckBox
        now = datetime.datetime.now()
        self._end_edit = QDateTimeEdit(now)
        self._end_edit.setDisplayFormat("MMM d yyyy  h:mm AP")
        self._end_edit.setCalendarPopup(True)

        end_row = QHBoxLayout()
        end_row.setSpacing(8)
        end_row.addWidget(self._end_edit)
        self._end_unknown = _QCheckBox("Not sure")
        self._end_unknown.setToolTip("Leave end time approximate — will use current time when saved")
        self._end_unknown.toggled.connect(self._on_unknown_toggled)
        end_row.addWidget(self._end_unknown)
        end_row.addStretch()
        form.addRow("Ended at:", end_row)

        # Notes
        self._notes_edit = QTextEdit()
        self._notes_edit.setPlaceholderText("Notes… (optional)")
        self._notes_edit.setFixedHeight(56)
        form.addRow("Notes:", self._notes_edit)

        root.addLayout(form)

        # Computed preview label
        self._preview = QLabel()
        self._preview.setObjectName("secondary")
        root.addWidget(self._preview)
        self._hours_spin.valueChanged.connect(self._update_preview)
        self._mins_spin.valueChanged.connect(self._update_preview)
        self._end_edit.dateTimeChanged.connect(self._update_preview)
        self._update_preview()

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(line)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _on_unknown_toggled(self, checked: bool) -> None:
        self._end_edit.setEnabled(not checked)
        self._update_preview()

    def _update_preview(self) -> None:
        total_mins = self._hours_spin.value() * 60 + self._mins_spin.value()
        end = datetime.datetime.now() if self._end_unknown.isChecked() else self._end_edit.dateTime().toPyDateTime()
        start = end - datetime.timedelta(minutes=total_mins)
        if total_mins == 0:
            self._preview.setText("Duration must be at least 1 minute.")
        elif self._end_unknown.isChecked():
            self._preview.setText(
                f"Session: ~{start.strftime('%-I:%M %p')} → now  "
                f"({_fmt_duration(total_mins * 60)})  — end time approximate"
            )
        else:
            self._preview.setText(
                f"Session: {start.strftime('%-I:%M %p')} → {end.strftime('%-I:%M %p')}  "
                f"({_fmt_duration(total_mins * 60)})"
            )

    def _on_accept(self) -> None:
        total_mins = self._hours_spin.value() * 60 + self._mins_spin.value()
        if total_mins == 0:
            QMessageBox.warning(self, "Invalid Duration", "Please enter at least 1 minute.")
            return
        # Capture a single consistent end time so result_start and result_end
        # both derive from the same base (avoids the "now" drifting between calls).
        if self._end_unknown.isChecked():
            self._resolved_end = datetime.datetime.now()
        else:
            self._resolved_end = self._end_edit.dateTime().toPyDateTime()
        self._resolved_total_mins = total_mins
        self.accept()

    # ------------------------------------------------------------------
    @property
    def result_title(self) -> str:
        return self._title_edit.text().strip()

    @property
    def result_start(self) -> str:
        return (self._resolved_end - datetime.timedelta(minutes=self._resolved_total_mins)).isoformat()

    @property
    def result_end(self) -> str:
        return self._resolved_end.isoformat()

    @property
    def result_notes(self) -> str:
        return self._notes_edit.toPlainText().strip()


# ---------------------------------------------------------------------------
# Session edit dialog
# ---------------------------------------------------------------------------

class SessionEditDialog(QDialog):
    """Edit a single session's title, start time, end time, and notes."""

    def __init__(self, parent=None, *, session: dict):
        super().__init__(parent)
        self.setWindowTitle("Edit Session")
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)

        self._title_edit = QLineEdit(session.get("title", ""))
        self._title_edit.setPlaceholderText("Session label (optional)")
        form.addRow("Title:", self._title_edit)

        start_dt = datetime.datetime.fromisoformat(session["start_time"])
        self._start_edit = QDateTimeEdit(start_dt)
        self._start_edit.setDisplayFormat("MMM d yyyy  h:mm AP")
        self._start_edit.setCalendarPopup(True)
        form.addRow("Start:", self._start_edit)

        end_raw = session.get("end_time")
        self._session_running = not bool(end_raw)
        end_dt = datetime.datetime.fromisoformat(end_raw) if end_raw else datetime.datetime.now()
        self._end_edit = QDateTimeEdit(end_dt)
        self._end_edit.setDisplayFormat("MMM d yyyy  h:mm AP")
        self._end_edit.setCalendarPopup(True)

        if self._session_running:
            # Still open — end field disabled, labelled clearly
            form.addRow("End:", self._end_edit)
            self._end_edit.setEnabled(False)
            self._end_unknown = None
            form.addRow("", QLabel("(session still running — Stop it first to set an end time)"))
        else:
            from PyQt6.QtWidgets import QCheckBox as _QCheckBox
            end_row = QHBoxLayout()
            end_row.setSpacing(8)
            end_row.addWidget(self._end_edit)
            self._end_unknown = _QCheckBox("Not sure")
            self._end_unknown.setToolTip("Mark end time as approximate — will save current time when OK is clicked")
            self._end_unknown.toggled.connect(lambda checked: self._end_edit.setEnabled(not checked))
            end_row.addWidget(self._end_unknown)
            end_row.addStretch()
            form.addRow("End:", end_row)

        self._notes_edit = QTextEdit(session.get("notes", ""))
        self._notes_edit.setPlaceholderText("Notes…")
        self._notes_edit.setFixedHeight(60)
        form.addRow("Notes:", self._notes_edit)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def result_title(self) -> str:
        return self._title_edit.text().strip()

    @property
    def result_start(self) -> str:
        return self._start_edit.dateTime().toPyDateTime().isoformat()

    @property
    def result_end(self) -> Optional[str]:
        if self._session_running:
            return None  # still running, don't set end
        if self._end_unknown is not None and self._end_unknown.isChecked():
            return datetime.datetime.now().isoformat()
        return self._end_edit.dateTime().toPyDateTime().isoformat()

    @property
    def result_notes(self) -> str:
        return self._notes_edit.toPlainText().strip()


# ---------------------------------------------------------------------------
# Session row widget
# ---------------------------------------------------------------------------

class SessionRow(QWidget):
    """One row in the sessions panel: title | date range | duration | actions."""

    delete_requested = pyqtSignal(int)   # session_id
    split_requested = pyqtSignal(int)    # session_id
    edit_requested = pyqtSignal(int)     # session_id

    def __init__(self, session: dict, parent=None):
        super().__init__(parent)
        self._session = session
        self._build()

    def _build(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(6)

        # Running indicator dot
        self._dot = QLabel("●")
        self._dot.setFixedWidth(12)
        font = self._dot.font()
        font.setPointSize(8)
        self._dot.setFont(font)
        layout.addWidget(self._dot)

        # Title
        self._title_lbl = QLabel()
        self._title_lbl.setMinimumWidth(120)
        layout.addWidget(self._title_lbl)

        # Date/time range
        self._range_lbl = QLabel()
        self._range_lbl.setObjectName("secondary")
        self._range_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self._range_lbl)

        # Duration
        self._dur_lbl = QLabel()
        self._dur_lbl.setFixedWidth(70)
        self._dur_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._dur_lbl)

        # Action buttons
        edit_btn = QPushButton("Edit")
        edit_btn.setObjectName("flat")
        edit_btn.setFixedHeight(22)
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.clicked.connect(lambda: self.edit_requested.emit(self._session["id"]))
        layout.addWidget(edit_btn)

        split_btn = QPushButton("Split")
        split_btn.setObjectName("flat")
        split_btn.setFixedHeight(22)
        split_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        split_btn.clicked.connect(lambda: self.split_requested.emit(self._session["id"]))
        layout.addWidget(split_btn)

        del_btn = QPushButton("✕")
        del_btn.setObjectName("flat")
        del_btn.setFixedHeight(22)
        del_btn.setFixedWidth(22)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setToolTip("Delete this session")
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self._session["id"]))
        layout.addWidget(del_btn)

        self.refresh(self._session)

    def refresh(self, session: dict) -> None:
        self._session = session
        is_running = session.get("end_time") is None
        title = session.get("title") or ("Running…" if is_running else "Session")
        self._title_lbl.setText(title)

        start_str = _fmt_datetime_short(session["start_time"])
        if is_running:
            self._range_lbl.setText(f"{start_str} → now")
            self._dot.setStyleSheet("color: #c83b01;")
        else:
            end_str = _fmt_datetime_short(session["end_time"])
            self._range_lbl.setText(f"{start_str} → {end_str}")
            self._dot.setStyleSheet("color: transparent;")

        secs = _duration_secs(session["start_time"], session.get("end_time"))
        self._dur_lbl.setText(_fmt_duration(secs))


# ---------------------------------------------------------------------------
# Sessions panel (collapsible)
# ---------------------------------------------------------------------------

class SessionsPanel(QWidget):
    """Expandable panel showing all sessions for a timer."""

    sessions_changed = pyqtSignal()

    def __init__(self, timer_id: int, db: CalendarDB, parent=None):
        super().__init__(parent)
        self._timer_id = timer_id
        self._db = db
        self._session_rows: dict[int, SessionRow] = {}  # session_id → row

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 4, 4, 8)
        outer.setSpacing(0)

        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("divider")
        outer.addWidget(line)

        self._rows_layout = QVBoxLayout()
        self._rows_layout.setContentsMargins(0, 4, 0, 0)
        self._rows_layout.setSpacing(0)
        outer.addLayout(self._rows_layout)

        # Add session button
        add_btn = QPushButton("+ Add manual session")
        add_btn.setObjectName("flat")
        add_btn.setFixedHeight(24)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._add_manual_session)
        outer.addWidget(add_btn)

        self.reload()

    def reload(self) -> None:
        sessions = self._db.get_timer_sessions(self._timer_id)
        # Remove old rows
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._session_rows.clear()

        if not sessions:
            lbl = QLabel("No sessions. Use Start or Log past time to add one.")
            lbl.setObjectName("secondary")
            lbl.setContentsMargins(0, 4, 0, 4)
            self._rows_layout.addWidget(lbl)
            return

        for s in sessions:
            row = SessionRow(s, self)
            row.delete_requested.connect(self._on_delete)
            row.split_requested.connect(self._on_split)
            row.edit_requested.connect(self._on_edit)
            self._session_rows[s["id"]] = row
            self._rows_layout.addWidget(row)

    def tick(self) -> None:
        """Called every second to refresh running session durations."""
        for _, row in self._session_rows.items():
            if row._session.get("end_time") is None:
                row.refresh(row._session)

    def _on_delete(self, session_id: int) -> None:
        confirm = QMessageBox.question(
            self, "Delete Session",
            "Remove this session? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._db.delete_timer_session(session_id)
        self.sessions_changed.emit()
        self.reload()

    def _on_split(self, session_id: int) -> None:
        self._db.split_timer_session(session_id)
        self.sessions_changed.emit()
        self.reload()

    def _on_edit(self, session_id: int) -> None:
        sessions = self._db.get_timer_sessions(self._timer_id)
        session = next((s for s in sessions if s["id"] == session_id), None)
        if not session:
            return
        dlg = SessionEditDialog(self, session=session)
        if dlg.exec():
            updates: dict = {"title": dlg.result_title, "start_time": dlg.result_start, "notes": dlg.result_notes}
            end = dlg.result_end
            if end is not None:
                updates["end_time"] = end
            self._db.update_timer_session(session_id, **updates)
            self.sessions_changed.emit()
            self.reload()

    def _add_manual_session(self) -> None:
        now = datetime.datetime.now()
        one_hour_ago = now - datetime.timedelta(hours=1)
        fake = {
            "id": -1,
            "timer_id": self._timer_id,
            "title": "",
            "start_time": one_hour_ago.isoformat(),
            "end_time": now.isoformat(),
            "notes": "",
        }
        dlg = SessionEditDialog(self, session=fake)
        if dlg.exec():
            sid = self._db.create_timer_session(
                self._timer_id,
                title=dlg.result_title,
                start_time=dlg.result_start,
            )
            end = dlg.result_end
            if end:
                self._db.stop_timer_session(sid, end_time=end)
            self.sessions_changed.emit()
            self.reload()


# ---------------------------------------------------------------------------
# Timer card
# ---------------------------------------------------------------------------

class TimerCard(QWidget):
    """A single timer project card with header controls and collapsible sessions panel."""

    changed = pyqtSignal()       # sessions added/removed/edited → parent re-totals
    delete_requested = pyqtSignal(int)   # timer_id

    def __init__(self, timer: dict, db: CalendarDB, parent=None):
        super().__init__(parent)
        self._timer = timer
        self._db = db
        self._expanded = False
        self._build()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Card frame
        card = QWidget()
        card.setObjectName("timer_card")
        outer.addWidget(card)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(0)

        # ── Header row ──────────────────────────────────────────────────
        header = QHBoxLayout()
        header.setSpacing(8)

        # Colour dot
        self._dot = QLabel("●")
        dot_font = QFont()
        dot_font.setPointSize(16)
        self._dot.setFont(dot_font)
        self._dot.setFixedWidth(20)
        header.addWidget(self._dot)

        # Title (click to edit)
        self._title_lbl = QLabel()
        title_font = QFont()
        title_font.setPointSize(13)
        title_font.setWeight(QFont.Weight.DemiBold)
        self._title_lbl.setFont(title_font)
        self._title_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self._title_lbl.setToolTip("Click to edit timer settings")
        self._title_lbl.mousePressEvent = lambda _: self._on_edit()
        header.addWidget(self._title_lbl)

        header.addStretch()

        # Live elapsed
        self._elapsed_lbl = QLabel()
        elapsed_font = QFont()
        elapsed_font.setFamily("Menlo, Monaco, monospace")
        elapsed_font.setPointSize(18)
        elapsed_font.setWeight(QFont.Weight.DemiBold)
        self._elapsed_lbl.setFont(elapsed_font)
        self._elapsed_lbl.setMinimumWidth(100)
        self._elapsed_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(self._elapsed_lbl)

        # Earnings
        self._earn_lbl = QLabel()
        self._earn_lbl.setObjectName("earn_label")
        self._earn_lbl.setMinimumWidth(80)
        self._earn_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(self._earn_lbl)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedHeight(22)
        header.addWidget(sep)

        # Start / Pause / Resume button
        self._action_btn = QPushButton()
        self._action_btn.setFixedHeight(28)
        self._action_btn.setFixedWidth(80)
        self._action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._action_btn.clicked.connect(self._on_action)
        header.addWidget(self._action_btn)

        # Stop button
        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setObjectName("stop_btn")
        self._stop_btn.setFixedHeight(28)
        self._stop_btn.setFixedWidth(60)
        self._stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._stop_btn.clicked.connect(self._on_stop)
        header.addWidget(self._stop_btn)

        # Kebab / more options
        more_btn = QPushButton("⋯")
        more_btn.setObjectName("flat")
        more_btn.setFixedSize(28, 28)
        more_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        more_btn.setToolTip("Edit / Delete timer")
        more_btn.clicked.connect(self._on_more)
        header.addWidget(more_btn)

        # Expand chevron
        self._expand_btn = QPushButton("▸")
        self._expand_btn.setObjectName("flat")
        self._expand_btn.setFixedSize(28, 28)
        self._expand_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._expand_btn.setToolTip("Show / hide sessions")
        self._expand_btn.clicked.connect(self._toggle_expand)
        header.addWidget(self._expand_btn)

        card_layout.addLayout(header)

        # ── Sessions panel (hidden by default) ──────────────────────────
        self._sessions_panel = SessionsPanel(self._timer["id"], self._db, card)
        self._sessions_panel.sessions_changed.connect(self.changed.emit)
        self._sessions_panel.sessions_changed.connect(self.tick)
        self._sessions_panel.hide()
        card_layout.addWidget(self._sessions_panel)

        self.tick()

    # ------------------------------------------------------------------
    def tick(self) -> None:
        """Refresh elapsed time and earnings from DB (called every second)."""
        sessions = self._db.get_timer_sessions(self._timer["id"])
        total = _sessions_total_secs(sessions)
        is_running = any(s.get("end_time") is None for s in sessions)

        self._dot.setStyleSheet(
            f"color: {'#c83b01' if is_running else self._timer['color']};"
        )
        self._title_lbl.setText(self._timer["title"])
        self._elapsed_lbl.setText(_fmt_duration(total))

        is_work = self._timer.get("timer_type", "work") == "work"
        if is_work:
            earn = _fmt_earnings(
                total,
                self._timer.get("hourly_rate", 0),
                self._timer.get("currency", _DEFAULT_CURRENCY),
            )
            self._earn_lbl.setText(earn)
            self._earn_lbl.setVisible(True)
        else:
            self._earn_lbl.setVisible(False)

        if is_running:
            self._action_btn.setText("Pause")
            self._action_btn.setObjectName("pause_btn")
            self._stop_btn.setEnabled(True)
        else:
            running_session = self._db.get_running_session(self._timer["id"])
            if running_session is None:
                self._action_btn.setText("Start")
                self._action_btn.setObjectName("start_btn")
                self._stop_btn.setEnabled(False)
            else:
                self._action_btn.setText("Pause")
                self._action_btn.setObjectName("pause_btn")
                self._stop_btn.setEnabled(True)

        self._action_btn.style().unpolish(self._action_btn)
        self._action_btn.style().polish(self._action_btn)

        if self._expanded:
            self._sessions_panel.tick()

    def reload_timer(self) -> None:
        """Reload timer metadata from DB (after an edit)."""
        timers = self._db.get_timers(include_archived=True)
        for t in timers:
            if t["id"] == self._timer["id"]:
                self._timer = t
                break
        self.tick()

    # ------------------------------------------------------------------
    def _on_action(self) -> None:
        running = self._db.get_running_session(self._timer["id"])
        if running:
            # Pause: close the current session
            self._db.stop_timer_session(running["id"])
        else:
            # Start / Resume: open a new session
            self._db.create_timer_session(self._timer["id"])
        self.tick()
        if self._expanded:
            self._sessions_panel.reload()
        self.changed.emit()

    def _on_stop(self) -> None:
        running = self._db.get_running_session(self._timer["id"])
        if running:
            self._db.stop_timer_session(running["id"])
        self.tick()
        if self._expanded:
            self._sessions_panel.reload()
        self.changed.emit()

    def _toggle_expand(self) -> None:
        self._expanded = not self._expanded
        if self._expanded:
            self._sessions_panel.reload()
            self._sessions_panel.show()
            self._expand_btn.setText("▾")
        else:
            self._sessions_panel.hide()
            self._expand_btn.setText("▸")

    def _on_edit(self) -> None:
        dlg = TimerDialog(
            self,
            title=self._timer["title"],
            timer_type=self._timer.get("timer_type", "work"),
            hourly_rate=self._timer.get("hourly_rate", 0),
            currency=self._timer.get("currency", _DEFAULT_CURRENCY),
            color=self._timer.get("color", "#1a6fc4"),
        )
        if dlg.exec():
            self._db.update_timer(
                self._timer["id"],
                title=dlg.result_title,
                timer_type=dlg.result_type,
                hourly_rate=dlg.result_rate,
                currency=dlg.result_currency,
                color=dlg.result_color,
            )
            self.reload_timer()

    def _on_log_time(self) -> None:
        """Open the quick log-past-time dialog and save the session."""
        dlg = LogTimeDialog(self)
        if dlg.exec():
            sid = self._db.create_timer_session(
                self._timer["id"],
                title=dlg.result_title,
                start_time=dlg.result_start,
            )
            self._db.stop_timer_session(sid, end_time=dlg.result_end)
            if dlg.result_notes:
                self._db.update_timer_session(sid, notes=dlg.result_notes)
            self.tick()
            if self._expanded:
                self._sessions_panel.reload()
            self.changed.emit()

    def _on_more(self) -> None:
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        log_act = menu.addAction("Log past time…")
        menu.addSeparator()
        edit_act = menu.addAction("Edit timer settings")
        archive_act = menu.addAction("Archive timer")
        menu.addSeparator()
        del_act = menu.addAction("Delete timer…")

        action = menu.exec(self._action_btn.mapToGlobal(self._action_btn.rect().bottomLeft()))
        if action == log_act:
            self._on_log_time()
        elif action == edit_act:
            self._on_edit()
        elif action == archive_act:
            self._db.update_timer(self._timer["id"], archived=1)
            self.delete_requested.emit(self._timer["id"])
        elif action == del_act:
            confirm = QMessageBox.question(
                self, "Delete Timer",
                f"Delete \"{self._timer['title']}\" and all its sessions? This cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            )
            if confirm == QMessageBox.StandardButton.Yes:
                self._db.delete_timer(self._timer["id"])
                self.delete_requested.emit(self._timer["id"])


# ---------------------------------------------------------------------------
# Main timer view
# ---------------------------------------------------------------------------

class TimerView(QWidget):
    """
    The full Timer tab: dashboard of TimerCard widgets, daily summary,
    and a 1-second tick that drives all live displays.
    """

    def __init__(self, db: CalendarDB, parent=None):
        super().__init__(parent)
        self._db = db
        self._cards: dict[int, TimerCard] = {}  # timer_id → card
        self._dark = False

        self._build()

        # 1-second tick for live clocks
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(1000)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start()

        self.reload()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top bar ──────────────────────────────────────────────────────
        top = QWidget()
        top.setObjectName("timer_topbar")
        top.setFixedHeight(48)
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(16, 8, 16, 8)
        top_layout.setSpacing(12)

        heading = QLabel("Timers")
        heading_font = QFont()
        heading_font.setPointSize(15)
        heading_font.setWeight(QFont.Weight.DemiBold)
        heading.setFont(heading_font)
        top_layout.addWidget(heading)

        top_layout.addStretch()

        # Daily summary
        self._summary_lbl = QLabel()
        self._summary_lbl.setObjectName("secondary")
        top_layout.addWidget(self._summary_lbl)

        new_btn = QPushButton("+ New Timer")
        new_btn.setObjectName("seg_btn")
        new_btn.setProperty("active", True)
        new_btn.setFixedHeight(30)
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.clicked.connect(self._on_new_timer)
        top_layout.addWidget(new_btn)

        root.addWidget(top)

        # ── Scroll area for cards ─────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._cards_widget = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_widget)
        self._cards_layout.setContentsMargins(16, 12, 16, 12)
        self._cards_layout.setSpacing(8)
        self._cards_layout.addStretch()

        scroll.setWidget(self._cards_widget)
        root.addWidget(scroll, stretch=1)

    # ------------------------------------------------------------------
    # Load / reload
    # ------------------------------------------------------------------

    def reload(self) -> None:
        """Rebuild card list from DB."""
        timers = self._db.get_timers(include_archived=False)
        timer_ids = {t["id"] for t in timers}

        # Remove cards for deleted/archived timers
        for tid in list(self._cards.keys()):
            if tid not in timer_ids:
                card = self._cards.pop(tid)
                self._cards_layout.removeWidget(card)
                card.deleteLater()

        # Add cards for new timers (insert before the stretch)
        for i, t in enumerate(timers):
            if t["id"] not in self._cards:
                card = TimerCard(t, self._db, self)
                card.changed.connect(self._update_summary)
                card.delete_requested.connect(self._on_card_deleted)
                self._cards[t["id"]] = card
                self._cards_layout.insertWidget(i, card)

        self._update_summary()
        self._show_empty_state(len(timers) == 0)

    def _show_empty_state(self, empty: bool) -> None:
        if not hasattr(self, "_empty_lbl"):
            self._empty_lbl = QLabel(
                "No timers yet.\nClick \"+ New Timer\" to start tracking your work."
            )
            self._empty_lbl.setObjectName("secondary")
            self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._empty_lbl.setContentsMargins(0, 40, 0, 0)
            self._cards_layout.insertWidget(0, self._empty_lbl)
        self._empty_lbl.setVisible(empty)

    def _update_summary(self) -> None:
        """Recompute daily total and earnings across all timers."""
        timers = self._db.get_timers()
        today = datetime.date.today().isoformat()
        total_secs = 0.0
        # Accumulate earnings per currency separately (timers can use different currencies)
        earn_by_currency: dict[str, float] = {}
        any_running = False

        for t in timers:
            sessions = self._db.get_timer_sessions(t["id"])
            is_work = t.get("timer_type", "work") == "work"
            currency = t.get("currency", _DEFAULT_CURRENCY)
            for s in sessions:
                try:
                    s_date = datetime.datetime.fromisoformat(s["start_time"]).date().isoformat()
                except Exception:
                    s_date = ""
                if s_date == today or (s.get("end_time") is None and s_date <= today):
                    secs = _duration_secs(s["start_time"], s.get("end_time"))
                    total_secs += secs
                    if is_work and t.get("hourly_rate", 0) > 0:
                        earn_by_currency[currency] = (
                            earn_by_currency.get(currency, 0.0)
                            + (secs / 3600) * t["hourly_rate"]
                        )
                if s.get("end_time") is None:
                    any_running = True

        parts = [f"Today: {_fmt_duration(total_secs)}"]
        for cur, amount in earn_by_currency.items():
            sym = _currency_symbol(cur)
            parts.append(f"{sym}{amount:,.2f} earned")
        if any_running:
            parts.append("● Running")
        self._summary_lbl.setText("  ·  ".join(parts))

    # ------------------------------------------------------------------
    # Tick
    # ------------------------------------------------------------------

    def _tick(self) -> None:
        for card in self._cards.values():
            card.tick()
        self._update_summary()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_new_timer(self) -> None:
        existing = self._db.get_timers(include_archived=True)
        color = _TIMER_COLORS[len(existing) % len(_TIMER_COLORS)]
        dlg = TimerDialog(self, color=color)
        if dlg.exec():
            self._db.create_timer(
                title=dlg.result_title,
                timer_type=dlg.result_type,
                hourly_rate=dlg.result_rate,
                currency=dlg.result_currency,
                color=dlg.result_color,
            )
            self.reload()

    def _on_card_deleted(self, timer_id: int) -> None:
        card = self._cards.pop(timer_id, None)
        if card:
            self._cards_layout.removeWidget(card)
            card.deleteLater()
        timers = self._db.get_timers()
        self._show_empty_state(len(timers) == 0)
        self._update_summary()

    # ------------------------------------------------------------------
    # Theme / config
    # ------------------------------------------------------------------

    def apply_theme(self, dark: bool) -> None:
        self._dark = dark
        self._apply_card_styles()

    def _apply_card_styles(self) -> None:
        from assistant.calendar_ui import styles as _styles
        bg = _styles.D_WHITE if self._dark else _styles.WHITE
        card_bg = _styles.D_GRAY_LIGHT if self._dark else _styles.GRAY_LIGHT
        border = _styles.D_GRAY_BORDER if self._dark else _styles.GRAY_BORDER
        text2 = _styles.D_GRAY_TEXT if self._dark else _styles.GRAY_TEXT

        self.setStyleSheet(f"""
            QWidget#timer_topbar {{
                background: {bg};
                border-bottom: 1px solid {border};
            }}
            QWidget#timer_card {{
                background: {card_bg};
                border: 1px solid {border};
                border-radius: 8px;
            }}
            QLabel#secondary {{
                color: {text2};
                font-size: 12px;
            }}
            QLabel#earn_label {{
                color: #108010;
                font-weight: bold;
                font-size: 13px;
            }}
            QPushButton#start_btn {{
                background: #1a6fc4;
                color: white;
                border-radius: 5px;
                font-weight: bold;
            }}
            QPushButton#start_btn:hover {{
                background: #1862ad;
            }}
            QPushButton#pause_btn {{
                background: #b84e0e;
                color: white;
                border-radius: 5px;
                font-weight: bold;
            }}
            QPushButton#pause_btn:hover {{
                background: #a04008;
            }}
            QPushButton#stop_btn {{
                background: transparent;
                color: #c83b01;
                border: 1px solid #c83b01;
                border-radius: 5px;
            }}
            QPushButton#stop_btn:disabled {{
                color: {text2};
                border-color: {border};
            }}
            QFrame#divider {{
                color: {border};
            }}
        """)

    def apply_ui_config(self, _=None) -> None:
        pass  # reserved for future font-size controls
