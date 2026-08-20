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
import time as _time
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QDoubleSpinBox,
    QSpinBox,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QDateTimeEdit,
    QColorDialog,
)

from assistant.db import CalendarDB
import assistant.calendar_ui.styles as _styles
from assistant.calendar_ui.dialog_utils import install_enter_confirms

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


# Palette of colours for new timers (cycles through) — first entry follows
# the configured accent, same convention as styles.EVENT_COLORS.
_TIMER_COLORS = [
    _styles.BLUE,  # accent
    "#2fae5c",  # green
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
    """Seconds between start and end (or now if end is None).

    Timestamps may be naive (legacy rows) or timezone-aware (current
    format). Normalize both to aware datetimes anchored to the system's
    current local offset so the diff reflects real elapsed time even if
    the laptop's timezone changed between start and now (e.g. travel).
    """
    try:
        s = datetime.datetime.fromisoformat(start_iso)
        if s.tzinfo is None:
            s = s.astimezone()
        e = datetime.datetime.fromisoformat(end_iso) if end_iso else datetime.datetime.now()
        if e.tzinfo is None:
            e = e.astimezone()
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


def _time_bucket(dt: datetime.datetime) -> str:
    """Coarse time-of-day label for a press timestamp."""
    if dt.hour < 12:
        return "Morning"
    elif dt.hour < 18:
        return "Afternoon"
    else:
        return "Evening"


def _fmt_press_when(iso: str) -> str:
    """'2025-04-15T09:30:00' → 'Today · Morning' / 'Apr 15 · Afternoon'."""
    try:
        dt = datetime.datetime.fromisoformat(iso)
        today = datetime.date.today()
        if dt.date() == today:
            day_str = "Today"
        elif dt.date().year == today.year:
            day_str = dt.strftime("%b %-d")
        else:
            day_str = dt.strftime("%b %-d %Y")
        return f"{day_str} · {_time_bucket(dt)}"
    except Exception:
        return iso


def _presses_total(presses: list[dict]) -> int:
    """Net count from a list of press rows."""
    return sum(p.get("delta", 0) for p in presses)


def _fmt_payout(count: int, price_per_unit: float, currency: str = "ILS") -> str:
    if price_per_unit <= 0:
        return ""
    symbol = _currency_symbol(currency)
    return f"{symbol}{count * price_per_unit:,.2f}"


def _parse_dt_aware(iso: str) -> datetime.datetime:
    """Parse an ISO datetime string, normalizing naive timestamps to the
    system's current local offset (mirrors _duration_secs's approach) so
    comparisons between naive (dialog-entered) and aware (live-tap) rows
    stay consistent."""
    dt = datetime.datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt


def _presses_since(presses: list[dict], cycle_start_iso: Optional[str]) -> list[dict]:
    """Presses belonging to the current (open) tally cycle — those at or
    after cycle_start_iso. cycle_start_iso is None for a counter that's
    never been cashed out, meaning its entire press history is the current
    cycle. Malformed timestamps are kept rather than silently dropped."""
    if not cycle_start_iso:
        return presses
    try:
        start_dt = _parse_dt_aware(cycle_start_iso)
    except Exception:
        return presses
    kept = []
    for p in presses:
        try:
            p_dt = _parse_dt_aware(p.get("pressed_at", ""))
        except Exception:
            kept.append(p)
            continue
        if p_dt >= start_dt:
            kept.append(p)
    return kept


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
        color: str = _styles.BLUE,
        max_session_minutes: int = 0,
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

        self._max_session_spin = QSpinBox()
        self._max_session_spin.setRange(0, 1440)
        self._max_session_spin.setSingleStep(15)
        self._max_session_spin.setValue(max_session_minutes)
        self._max_session_spin.setSuffix(" min")
        self._max_session_spin.setSpecialValueText("No limit")
        self._max_session_spin.setToolTip(
            "Auto-stop this timer if a running session goes past this length "
            "(e.g. you forgot to stop it)."
        )
        form.addRow("Max session:", self._max_session_spin)

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
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setDefault(True)
        install_enter_confirms(self, ok_btn)
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
            f"background:{_styles.BLUE}; color:{_styles.ON_ACCENT}; border-radius:4px 0 0 4px; font-weight:bold;"
            if is_work else
            "background:transparent; border:1px solid #aaa; border-radius:4px 0 0 4px;"
        )
        self._personal_btn.setStyleSheet(
            f"background:{_styles.BLUE}; color:{_styles.ON_ACCENT}; border-radius:0 4px 4px 0; font-weight:bold;"
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

    @property
    def result_max_session_minutes(self) -> int:
        return self._max_session_spin.value()


# ---------------------------------------------------------------------------
# New / Edit Counter dialog
# ---------------------------------------------------------------------------

class CounterDialog(QDialog):
    """Create or edit a tally counter: title, price per unit, currency, colour."""

    def __init__(
        self,
        parent=None,
        *,
        title: str = "",
        price_per_unit: float = 0.0,
        currency: str = _DEFAULT_CURRENCY,
        color: str = _styles.BLUE,
    ):
        super().__init__(parent)
        self.setWindowTitle("Counter Settings")
        self.setMinimumWidth(380)

        self._color = color

        root = QVBoxLayout(self)
        root.setSpacing(14)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(10)

        self._title_edit = QLineEdit(title)
        self._title_edit.setPlaceholderText("e.g. Widgets Packed, Calls Made…")
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

        self._rate_spin = QDoubleSpinBox()
        self._rate_spin.setRange(0, 99999)
        self._rate_spin.setDecimals(2)
        self._rate_spin.setSingleStep(0.5)
        self._rate_spin.setValue(price_per_unit)
        self._rate_spin.setSuffix(" / unit")
        self._rate_spin.setSpecialValueText("No price set")
        form.addRow("Price per unit:", self._rate_spin)

        self._currency_picker = CurrencyPicker(currency, self)
        form.addRow("Currency:", self._currency_picker)

        root.addLayout(form)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(line)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setDefault(True)
        install_enter_confirms(self, ok_btn)
        root.addWidget(buttons)

    def _pick_color(self) -> None:
        c = QColorDialog.getColor(QColor(self._color), self, "Pick Counter Colour")
        if c.isValid():
            self._color = c.name()
            self._apply_color_btn()

    def _apply_color_btn(self) -> None:
        self._color_btn.setStyleSheet(
            f"background-color: {self._color}; border: 1px solid #aaa; border-radius: 4px;"
        )

    @property
    def result_title(self) -> str:
        return self._title_edit.text().strip() or "Untitled Counter"

    @property
    def result_rate(self) -> float:
        return self._rate_spin.value()

    @property
    def result_currency(self) -> str:
        return self._currency_picker.selected_code

    @property
    def result_color(self) -> str:
        return self._color


# ---------------------------------------------------------------------------
# Press edit dialog
# ---------------------------------------------------------------------------

class PressEditDialog(QDialog):
    """Edit a single counter press: label, +/- direction, and when it happened."""

    def __init__(self, parent=None, *, press: dict):
        super().__init__(parent)
        self.setWindowTitle("Edit Press")
        self.setMinimumWidth(340)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)

        self._label_edit = QLineEdit(press.get("label", ""))
        self._label_edit.setPlaceholderText("What was this for? (optional)")
        form.addRow("Label:", self._label_edit)

        from PyQt6.QtWidgets import QComboBox as _QComboBox
        self._sign_box = _QComboBox()
        self._sign_box.addItem("+ (add)", 1)
        self._sign_box.addItem("− (subtract)", -1)
        self._sign_box.setCurrentIndex(0 if press.get("delta", 1) >= 0 else 1)
        form.addRow("Direction:", self._sign_box)

        when_raw = press.get("pressed_at")
        when_dt = datetime.datetime.fromisoformat(when_raw) if when_raw else datetime.datetime.now()
        self._when_edit = QDateTimeEdit(when_dt)
        self._when_edit.setDisplayFormat("MMM d yyyy  h:mm AP")
        self._when_edit.setCalendarPopup(True)
        form.addRow("When:", self._when_edit)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setDefault(True)
        install_enter_confirms(self, ok_btn)
        layout.addWidget(buttons)

    @property
    def result_label(self) -> str:
        return self._label_edit.text().strip()

    @property
    def result_delta(self) -> int:
        return self._sign_box.currentData()

    @property
    def result_pressed_at(self) -> str:
        return self._when_edit.dateTime().toPyDateTime().isoformat()


# ---------------------------------------------------------------------------
# Cash Out dialog — close a counter's current tally cycle as a logged payout
# ---------------------------------------------------------------------------

class CashOutDialog(QDialog):
    """Log a payout for a counter's current tally cycle.

    Shows the read-only cycle count, an editable amount (pre-filled from
    count × price_per_unit when a rate is set), a date, and an optional
    note. Mirrors PressEditDialog's structure/styling.
    """

    def __init__(self, parent=None, *, count: int, price_per_unit: float = 0.0, currency: str = _DEFAULT_CURRENCY):
        super().__init__(parent)
        self.setWindowTitle("Cash Out")
        self.setMinimumWidth(340)
        self._count = count

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)

        count_lbl = QLabel(f"{count:,}")
        count_font = QFont()
        count_font.setWeight(QFont.Weight.DemiBold)
        count_lbl.setFont(count_font)
        form.addRow("Cycle count:", count_lbl)

        symbol = _currency_symbol(currency)
        self._amount_spin = QDoubleSpinBox()
        self._amount_spin.setRange(0, 9_999_999)
        self._amount_spin.setDecimals(2)
        self._amount_spin.setPrefix(f"{symbol} ")
        self._amount_spin.setValue(round(count * price_per_unit, 2) if price_per_unit > 0 else 0.0)
        form.addRow("Amount:", self._amount_spin)

        self._when_edit = QDateTimeEdit(datetime.datetime.now())
        self._when_edit.setDisplayFormat("MMM d yyyy  h:mm AP")
        self._when_edit.setCalendarPopup(True)
        form.addRow("Date:", self._when_edit)

        self._note_edit = QLineEdit()
        self._note_edit.setPlaceholderText("Note (optional)")
        form.addRow("Note:", self._note_edit)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setText("Cash Out")
        ok_btn.setDefault(True)
        install_enter_confirms(self, ok_btn)
        layout.addWidget(buttons)

    @property
    def result_count(self) -> int:
        return self._count

    @property
    def result_amount(self) -> float:
        return self._amount_spin.value()

    @property
    def result_payout_at(self) -> str:
        return self._when_edit.dateTime().toPyDateTime().isoformat()

    @property
    def result_note(self) -> str:
        return self._note_edit.text().strip()


# ---------------------------------------------------------------------------
# Payout edit dialog
# ---------------------------------------------------------------------------

class PayoutEditDialog(QDialog):
    """Edit a logged payout: date, amount, and note.

    Count and cycle start are immutable snapshots (see counter_payouts
    schema) — count is shown read-only, cycle start isn't shown at all.
    """

    def __init__(self, parent=None, *, payout: dict):
        super().__init__(parent)
        self.setWindowTitle("Edit Payout")
        self.setMinimumWidth(340)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)

        count_lbl = QLabel(f"{payout.get('count', 0):,}")
        count_font = QFont()
        count_font.setWeight(QFont.Weight.DemiBold)
        count_lbl.setFont(count_font)
        form.addRow("Cycle count:", count_lbl)

        currency = payout.get("currency", _DEFAULT_CURRENCY)
        symbol = _currency_symbol(currency)
        self._amount_spin = QDoubleSpinBox()
        self._amount_spin.setRange(0, 9_999_999)
        self._amount_spin.setDecimals(2)
        self._amount_spin.setPrefix(f"{symbol} ")
        self._amount_spin.setValue(payout.get("amount") or 0.0)
        form.addRow("Amount:", self._amount_spin)

        when_raw = payout.get("payout_at")
        when_dt = datetime.datetime.fromisoformat(when_raw) if when_raw else datetime.datetime.now()
        self._when_edit = QDateTimeEdit(when_dt)
        self._when_edit.setDisplayFormat("MMM d yyyy  h:mm AP")
        self._when_edit.setCalendarPopup(True)
        form.addRow("Date:", self._when_edit)

        self._note_edit = QLineEdit(payout.get("note", ""))
        self._note_edit.setPlaceholderText("Note (optional)")
        form.addRow("Note:", self._note_edit)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setDefault(True)
        install_enter_confirms(self, ok_btn)
        layout.addWidget(buttons)

    @property
    def result_amount(self) -> float:
        return self._amount_spin.value()

    @property
    def result_payout_at(self) -> str:
        return self._when_edit.dateTime().toPyDateTime().isoformat()

    @property
    def result_note(self) -> str:
        return self._note_edit.text().strip()


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
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setDefault(True)
        install_enter_confirms(self, ok_btn)
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
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setDefault(True)
        install_enter_confirms(self, ok_btn)
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
            live = _styles.DESTRUCTIVE_DARK if _styles._dark else _styles.DESTRUCTIVE
            self._dot.setStyleSheet(f"color: {live};")
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
            QMessageBox.StandardButton.Yes,  # Enter confirms; Escape still cancels
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
        # Cached sessions list — updated only when the timer state changes,
        # not on every 1-second tick.  None means "needs a fresh fetch".
        self._cached_sessions: list[dict] | None = None
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
        self._sessions_panel.sessions_changed.connect(self._invalidate_cache)
        self._sessions_panel.sessions_changed.connect(self.tick)
        self._sessions_panel.hide()
        card_layout.addWidget(self._sessions_panel)

        self.tick()

    # ------------------------------------------------------------------
    def _invalidate_cache(self) -> None:
        """Force the next tick() to re-fetch sessions from the DB."""
        self._cached_sessions = None

    def tick(self) -> None:
        """Refresh elapsed time and earnings.

        Uses a cached session list — only re-queries the DB when
        _cached_sessions is None (set after any state change) or when a
        session is currently running (end_time is None, so the elapsed
        time grows every second and we need an accurate 'now' snapshot).
        """
        is_running_cached = self._cached_sessions is not None and any(
            s.get("end_time") is None for s in self._cached_sessions
        )
        # Re-fetch only when: cache is cold, or a timer is actively ticking.
        if self._cached_sessions is None or is_running_cached:
            self._cached_sessions = self._db.get_timer_sessions(self._timer["id"])

        sessions = self._cached_sessions
        running = next((s for s in sessions if s.get("end_time") is None), None)

        limit_min = self._timer.get("max_session_minutes", 0) or 0
        if running is not None and limit_min > 0:
            elapsed = _duration_secs(running["start_time"], None)
            if elapsed >= limit_min * 60:
                start_dt = datetime.datetime.fromisoformat(running["start_time"])
                cap_dt = start_dt + datetime.timedelta(minutes=limit_min)
                self._db.stop_timer_session(running["id"], end_time=cap_dt.isoformat())
                sessions = self._cached_sessions = self._db.get_timer_sessions(self._timer["id"])
                running = None
                if self._expanded:
                    self._sessions_panel.reload()
                self.changed.emit()

        total = _sessions_total_secs(sessions)
        is_running = running is not None

        live = _styles.DESTRUCTIVE_DARK if _styles._dark else _styles.DESTRUCTIVE
        self._dot.setStyleSheet(
            f"color: {live if is_running else self._timer['color']};"
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
            self._action_btn.setText("Start")
            self._action_btn.setObjectName("start_btn")
            self._stop_btn.setEnabled(False)

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
        self._invalidate_cache()
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
        self._invalidate_cache()
        self.tick()
        if self._expanded:
            self._sessions_panel.reload()
        self.changed.emit()

    def _on_stop(self) -> None:
        running = self._db.get_running_session(self._timer["id"])
        if running:
            self._db.stop_timer_session(running["id"])
        self._invalidate_cache()
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
            color=self._timer.get("color", _styles.BLUE),
            max_session_minutes=self._timer.get("max_session_minutes", 0),
        )
        if dlg.exec():
            self._db.update_timer(
                self._timer["id"],
                title=dlg.result_title,
                timer_type=dlg.result_type,
                hourly_rate=dlg.result_rate,
                currency=dlg.result_currency,
                color=dlg.result_color,
                max_session_minutes=dlg.result_max_session_minutes,
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
                QMessageBox.StandardButton.Yes,  # Enter confirms; Escape still cancels
            )
            if confirm == QMessageBox.StandardButton.Yes:
                self._db.delete_timer(self._timer["id"])
                self.delete_requested.emit(self._timer["id"])


# ---------------------------------------------------------------------------
# Press row widget
# ---------------------------------------------------------------------------

class PressRow(QWidget):
    """One row in the presses panel: sign | when (date · time-of-day) | label | actions."""

    delete_requested = pyqtSignal(int)   # press_id
    edit_requested = pyqtSignal(int)     # press_id

    def __init__(self, press: dict, parent=None):
        super().__init__(parent)
        self._press = press
        self._build()

    def _build(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(6)

        self._sign_lbl = QLabel()
        self._sign_lbl.setFixedWidth(16)
        sign_font = QFont()
        sign_font.setWeight(QFont.Weight.DemiBold)
        self._sign_lbl.setFont(sign_font)
        layout.addWidget(self._sign_lbl)

        self._when_lbl = QLabel()
        self._when_lbl.setMinimumWidth(140)
        self._when_lbl.setObjectName("secondary")
        layout.addWidget(self._when_lbl)

        self._label_lbl = QLabel()
        self._label_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self._label_lbl)

        edit_btn = QPushButton("Edit")
        edit_btn.setObjectName("flat")
        edit_btn.setFixedHeight(22)
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.clicked.connect(lambda: self.edit_requested.emit(self._press["id"]))
        layout.addWidget(edit_btn)

        del_btn = QPushButton("✕")
        del_btn.setObjectName("flat")
        del_btn.setFixedHeight(22)
        del_btn.setFixedWidth(22)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setToolTip("Delete this press")
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self._press["id"]))
        layout.addWidget(del_btn)

        self.refresh(self._press)

    def refresh(self, press: dict) -> None:
        self._press = press
        delta = press.get("delta", 1)
        live = _styles.DESTRUCTIVE_DARK if _styles._dark else _styles.DESTRUCTIVE
        if delta >= 0:
            self._sign_lbl.setText(f"+{delta}")
            self._sign_lbl.setStyleSheet("color: #2fae5c;")
        else:
            self._sign_lbl.setText(str(delta))
            self._sign_lbl.setStyleSheet(f"color: {live};")
        self._when_lbl.setText(_fmt_press_when(press["pressed_at"]))
        self._label_lbl.setText(press.get("label") or "—")


# ---------------------------------------------------------------------------
# Presses panel (collapsible)
# ---------------------------------------------------------------------------

class PressesPanel(QWidget):
    """Expandable panel showing every logged +/- press for a counter."""

    presses_changed = pyqtSignal()

    def __init__(self, counter_id: int, db: CalendarDB, parent=None):
        super().__init__(parent)
        self._counter_id = counter_id
        self._db = db
        self._press_rows: dict[int, PressRow] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 4, 4, 8)
        outer.setSpacing(0)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("divider")
        outer.addWidget(line)

        self._rows_layout = QVBoxLayout()
        self._rows_layout.setContentsMargins(0, 4, 0, 0)
        self._rows_layout.setSpacing(0)
        outer.addLayout(self._rows_layout)

        add_btn = QPushButton("+ Add manual press")
        add_btn.setObjectName("flat")
        add_btn.setFixedHeight(24)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._add_manual_press)
        outer.addWidget(add_btn)

        self.reload()

    def reload(self) -> None:
        presses = list(reversed(self._db.get_counter_presses(self._counter_id)))  # newest first
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._press_rows.clear()

        if not presses:
            lbl = QLabel("No presses yet. Tap + or − on the counter, or add one manually.")
            lbl.setObjectName("secondary")
            lbl.setContentsMargins(0, 4, 0, 4)
            self._rows_layout.addWidget(lbl)
            return

        for p in presses:
            row = PressRow(p, self)
            row.delete_requested.connect(self._on_delete)
            row.edit_requested.connect(self._on_edit)
            self._press_rows[p["id"]] = row
            self._rows_layout.addWidget(row)

    def _on_delete(self, press_id: int) -> None:
        confirm = QMessageBox.question(
            self, "Delete Press",
            "Remove this press? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._db.delete_counter_press(press_id)
        self.presses_changed.emit()
        self.reload()

    def _on_edit(self, press_id: int) -> None:
        presses = self._db.get_counter_presses(self._counter_id)
        press = next((p for p in presses if p["id"] == press_id), None)
        if not press:
            return
        dlg = PressEditDialog(self, press=press)
        if dlg.exec():
            self._db.update_counter_press(
                press_id,
                label=dlg.result_label,
                delta=dlg.result_delta,
                pressed_at=dlg.result_pressed_at,
            )
            self.presses_changed.emit()
            self.reload()

    def _add_manual_press(self) -> None:
        fake = {"id": -1, "counter_id": self._counter_id, "delta": 1, "label": "", "pressed_at": datetime.datetime.now().isoformat()}
        dlg = PressEditDialog(self, press=fake)
        if dlg.exec():
            self._db.create_counter_press(
                self._counter_id,
                delta=dlg.result_delta,
                label=dlg.result_label,
                pressed_at=dlg.result_pressed_at,
            )
            self.presses_changed.emit()
            self.reload()


# ---------------------------------------------------------------------------
# Payout row widget
# ---------------------------------------------------------------------------

class PayoutRow(QWidget):
    """One row in the payouts panel: date | count | amount | note | actions."""

    delete_requested = pyqtSignal(int)   # payout_id
    edit_requested = pyqtSignal(int)     # payout_id

    def __init__(self, payout: dict, parent=None):
        super().__init__(parent)
        self._payout = payout
        self._build()

    def _build(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(6)

        self._when_lbl = QLabel()
        self._when_lbl.setMinimumWidth(120)
        self._when_lbl.setObjectName("secondary")
        layout.addWidget(self._when_lbl)

        self._count_lbl = QLabel()
        self._count_lbl.setFixedWidth(60)
        self._count_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._count_lbl)

        self._amount_lbl = QLabel()
        self._amount_lbl.setObjectName("earn_label")
        self._amount_lbl.setFixedWidth(90)
        self._amount_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._amount_lbl)

        self._note_lbl = QLabel()
        self._note_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self._note_lbl)

        edit_btn = QPushButton("Edit")
        edit_btn.setObjectName("flat")
        edit_btn.setFixedHeight(22)
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.clicked.connect(lambda: self.edit_requested.emit(self._payout["id"]))
        layout.addWidget(edit_btn)

        del_btn = QPushButton("✕")
        del_btn.setObjectName("flat")
        del_btn.setFixedHeight(22)
        del_btn.setFixedWidth(22)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setToolTip("Delete this payout")
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self._payout["id"]))
        layout.addWidget(del_btn)

        self.refresh(self._payout)

    def refresh(self, payout: dict) -> None:
        self._payout = payout
        self._when_lbl.setText(_fmt_datetime_short(payout.get("payout_at", "")))
        self._count_lbl.setText(f"{payout.get('count', 0):,}")
        amount = payout.get("amount")
        currency = payout.get("currency", _DEFAULT_CURRENCY)
        if amount:
            symbol = _currency_symbol(currency)
            self._amount_lbl.setText(f"{symbol}{amount:,.2f}")
        else:
            self._amount_lbl.setText("—")
        self._note_lbl.setText(payout.get("note") or "—")


# ---------------------------------------------------------------------------
# Payouts panel (collapsible) — payout / "cash out" history for a counter
# ---------------------------------------------------------------------------

class PayoutsPanel(QWidget):
    """Expandable panel showing every logged payout for a counter, newest first."""

    payouts_changed = pyqtSignal()

    def __init__(self, counter_id: int, db: CalendarDB, parent=None):
        super().__init__(parent)
        self._counter_id = counter_id
        self._db = db
        self._payout_rows: dict[int, PayoutRow] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 4, 4, 8)
        outer.setSpacing(0)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("divider")
        outer.addWidget(line)

        heading = QLabel("Payout history")
        heading.setObjectName("secondary")
        heading.setContentsMargins(0, 4, 0, 0)
        outer.addWidget(heading)

        self._rows_layout = QVBoxLayout()
        self._rows_layout.setContentsMargins(0, 4, 0, 0)
        self._rows_layout.setSpacing(0)
        outer.addLayout(self._rows_layout)

        self.reload()

    def reload(self) -> None:
        payouts = self._db.get_counter_payouts(self._counter_id)  # already newest first
        # setParent(None) before deleteLater() detaches rows from the widget
        # tree immediately — see TimerView._clear_layout for why the naive
        # deleteLater()-only version ghosts stale rows on reload.
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self._payout_rows.clear()

        if not payouts:
            lbl = QLabel("No payouts yet. Use Cash Out to log one.")
            lbl.setObjectName("secondary")
            lbl.setContentsMargins(0, 4, 0, 4)
            self._rows_layout.addWidget(lbl)
            return

        for p in payouts:
            row = PayoutRow(p, self)
            row.delete_requested.connect(self._on_delete)
            row.edit_requested.connect(self._on_edit)
            self._payout_rows[p["id"]] = row
            self._rows_layout.addWidget(row)

    def _on_delete(self, payout_id: int) -> None:
        confirm = QMessageBox.question(
            self, "Delete Payout",
            "Delete this payout record? This only removes the payout log "
            "entry — the underlying press history is unaffected. This "
            "cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._db.delete_counter_payout(payout_id)
        self.payouts_changed.emit()
        self.reload()

    def _on_edit(self, payout_id: int) -> None:
        payouts = self._db.get_counter_payouts(self._counter_id)
        payout = next((p for p in payouts if p["id"] == payout_id), None)
        if not payout:
            return
        dlg = PayoutEditDialog(self, payout=payout)
        if dlg.exec():
            self._db.update_counter_payout(
                payout_id,
                amount=dlg.result_amount,
                payout_at=dlg.result_payout_at,
                note=dlg.result_note,
            )
            self.payouts_changed.emit()
            self.reload()


# ---------------------------------------------------------------------------
# Counter card
# ---------------------------------------------------------------------------

class CounterCard(QWidget):
    """A single tally-counter card: +/- controls, live count and payout, press log."""

    changed = pyqtSignal()               # presses added/removed/edited → parent re-totals
    delete_requested = pyqtSignal(int)   # counter_id

    def __init__(self, counter: dict, db: CalendarDB, parent=None):
        super().__init__(parent)
        self._counter = counter
        self._db = db
        self._expanded = False
        self._payouts_expanded = False
        self._cached_presses: list[dict] | None = None
        self._build()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        card = QWidget()
        card.setObjectName("timer_card")
        outer.addWidget(card)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(0)

        header = QHBoxLayout()
        header.setSpacing(8)

        self._dot = QLabel("●")
        dot_font = QFont()
        dot_font.setPointSize(16)
        self._dot.setFont(dot_font)
        self._dot.setFixedWidth(20)
        header.addWidget(self._dot)

        self._title_lbl = QLabel()
        title_font = QFont()
        title_font.setPointSize(13)
        title_font.setWeight(QFont.Weight.DemiBold)
        self._title_lbl.setFont(title_font)
        self._title_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self._title_lbl.setToolTip("Click to edit counter settings")
        self._title_lbl.mousePressEvent = lambda _: self._on_edit()
        header.addWidget(self._title_lbl)

        header.addStretch()

        # Live count
        self._count_lbl = QLabel()
        count_font = QFont()
        count_font.setFamily("Menlo, Monaco, monospace")
        count_font.setPointSize(18)
        count_font.setWeight(QFont.Weight.DemiBold)
        self._count_lbl.setFont(count_font)
        self._count_lbl.setMinimumWidth(60)
        self._count_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(self._count_lbl)

        # Payout
        self._payout_lbl = QLabel()
        self._payout_lbl.setObjectName("earn_label")
        self._payout_lbl.setMinimumWidth(80)
        self._payout_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(self._payout_lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedHeight(22)
        header.addWidget(sep)

        # − button
        self._minus_btn = QPushButton("−")
        self._minus_btn.setObjectName("stop_btn")
        self._minus_btn.setFixedHeight(28)
        self._minus_btn.setFixedWidth(36)
        self._minus_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._minus_btn.setToolTip("Subtract one")
        self._minus_btn.clicked.connect(lambda: self._on_press(-1))
        header.addWidget(self._minus_btn)

        # + button
        self._plus_btn = QPushButton("+")
        self._plus_btn.setObjectName("start_btn")
        self._plus_btn.setFixedHeight(28)
        self._plus_btn.setFixedWidth(36)
        self._plus_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._plus_btn.setToolTip("Add one")
        self._plus_btn.clicked.connect(lambda: self._on_press(1))
        header.addWidget(self._plus_btn)

        self._payouts_btn = QPushButton("🧾")
        self._payouts_btn.setObjectName("flat")
        self._payouts_btn.setFixedSize(28, 28)
        self._payouts_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._payouts_btn.setToolTip("Show / hide payout history")
        self._payouts_btn.clicked.connect(self._toggle_payouts)
        header.addWidget(self._payouts_btn)

        more_btn = QPushButton("⋯")
        more_btn.setObjectName("flat")
        more_btn.setFixedSize(28, 28)
        more_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        more_btn.setToolTip("Edit / Delete counter")
        more_btn.clicked.connect(self._on_more)
        header.addWidget(more_btn)

        self._expand_btn = QPushButton("▸")
        self._expand_btn.setObjectName("flat")
        self._expand_btn.setFixedSize(28, 28)
        self._expand_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._expand_btn.setToolTip("Show / hide press log")
        self._expand_btn.clicked.connect(self._toggle_expand)
        header.addWidget(self._expand_btn)

        card_layout.addLayout(header)

        self._presses_panel = PressesPanel(self._counter["id"], self._db, card)
        self._presses_panel.presses_changed.connect(self.changed.emit)
        self._presses_panel.presses_changed.connect(self._invalidate_cache)
        self._presses_panel.presses_changed.connect(self.refresh)
        self._presses_panel.hide()
        card_layout.addWidget(self._presses_panel)

        self._payouts_panel = PayoutsPanel(self._counter["id"], self._db, card)
        self._payouts_panel.payouts_changed.connect(self.changed.emit)
        self._payouts_panel.payouts_changed.connect(self._invalidate_cache)
        self._payouts_panel.payouts_changed.connect(self.refresh)
        self._payouts_panel.hide()
        card_layout.addWidget(self._payouts_panel)

        self.refresh()

    # ------------------------------------------------------------------
    def _invalidate_cache(self) -> None:
        self._cached_presses = None

    def _cycle_start(self) -> Optional[str]:
        """Start of the counter's current (open) tally cycle: the most
        recent payout's date, or the counter's own created_at if it's
        never been cashed out."""
        return self._db.get_counter_cycle_start(self._counter["id"]) or self._counter.get("created_at")

    def refresh(self) -> None:
        if self._cached_presses is None:
            self._cached_presses = self._db.get_counter_presses(self._counter["id"])

        cycle_presses = _presses_since(self._cached_presses, self._cycle_start())
        count = _presses_total(cycle_presses)
        self._dot.setStyleSheet(f"color: {self._counter['color']};")
        self._title_lbl.setText(self._counter["title"])
        self._count_lbl.setText(f"{count:,}")

        payout = _fmt_payout(count, self._counter.get("price_per_unit", 0), self._counter.get("currency", _DEFAULT_CURRENCY))
        self._payout_lbl.setText(payout)
        self._payout_lbl.setVisible(bool(payout))

        if self._expanded:
            self._presses_panel.reload()
        if self._payouts_expanded:
            self._payouts_panel.reload()

    def reload_counter(self) -> None:
        """Reload counter metadata from DB (after an edit)."""
        counters = self._db.get_counters(include_archived=True)
        for c in counters:
            if c["id"] == self._counter["id"]:
                self._counter = c
                break
        self._invalidate_cache()
        self.refresh()

    def current_count(self) -> int:
        """Net count for the counter's current (open) tally cycle."""
        if self._cached_presses is None:
            self._cached_presses = self._db.get_counter_presses(self._counter["id"])
        return _presses_total(_presses_since(self._cached_presses, self._cycle_start()))

    # ------------------------------------------------------------------
    def _on_press(self, delta: int) -> None:
        self._db.create_counter_press(self._counter["id"], delta=delta)
        self._invalidate_cache()
        self.refresh()
        self.changed.emit()

    def _toggle_expand(self) -> None:
        self._expanded = not self._expanded
        if self._expanded:
            self._presses_panel.reload()
            self._presses_panel.show()
            self._expand_btn.setText("▾")
        else:
            self._presses_panel.hide()
            self._expand_btn.setText("▸")

    def _toggle_payouts(self) -> None:
        self._payouts_expanded = not self._payouts_expanded
        if self._payouts_expanded:
            self._payouts_panel.reload()
            self._payouts_panel.show()
        else:
            self._payouts_panel.hide()

    def _on_edit(self) -> None:
        dlg = CounterDialog(
            self,
            title=self._counter["title"],
            price_per_unit=self._counter.get("price_per_unit", 0),
            currency=self._counter.get("currency", _DEFAULT_CURRENCY),
            color=self._counter.get("color", _styles.BLUE),
        )
        if dlg.exec():
            self._db.update_counter(
                self._counter["id"],
                title=dlg.result_title,
                price_per_unit=dlg.result_rate,
                currency=dlg.result_currency,
                color=dlg.result_color,
            )
            self.reload_counter()

    def _on_cash_out(self) -> None:
        """Close out the current tally cycle: log a payout and start a
        fresh cycle (the displayed count returns to 0) without touching
        the underlying press log."""
        count = self.current_count()
        price = self._counter.get("price_per_unit", 0)
        currency = self._counter.get("currency", _DEFAULT_CURRENCY)
        dlg = CashOutDialog(self, count=count, price_per_unit=price, currency=currency)
        if dlg.exec():
            self._db.create_counter_payout(
                self._counter["id"],
                cycle_started_at=self._cycle_start(),
                payout_at=dlg.result_payout_at,
                count=dlg.result_count,
                amount=dlg.result_amount,
                currency=currency,
                note=dlg.result_note,
            )
            self._invalidate_cache()
            self.refresh()
            self.changed.emit()

    def _on_more(self) -> None:
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        edit_act = menu.addAction("Edit counter settings")
        cashout_act = menu.addAction("Cash Out…")
        archive_act = menu.addAction("Archive counter")
        menu.addSeparator()
        hard_reset_act = menu.addAction("Hard reset (discard press log)…")
        del_act = menu.addAction("Delete counter…")

        action = menu.exec(self._plus_btn.mapToGlobal(self._plus_btn.rect().bottomLeft()))
        if action == edit_act:
            self._on_edit()
        elif action == cashout_act:
            self._on_cash_out()
        elif action == archive_act:
            self._db.update_counter(self._counter["id"], archived=1)
            self.delete_requested.emit(self._counter["id"])
        elif action == hard_reset_act:
            # Secondary/destructive path for genuine data-entry corrections —
            # unlike Cash Out, this leaves no record a payout ever happened.
            # Defaults to Cancel since it's no longer the easy default action.
            confirm = QMessageBox.question(
                self, "Hard Reset Counter",
                f"Discard the entire press log for \"{self._counter['title']}\" "
                "without logging a payout? This permanently erases press "
                "history and cannot be undone. Use Cash Out instead if you "
                "want to keep a record of this cycle.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if confirm == QMessageBox.StandardButton.Yes:
                for p in self._db.get_counter_presses(self._counter["id"]):
                    self._db.delete_counter_press(p["id"])
                self._invalidate_cache()
                self.refresh()
                self.changed.emit()
        elif action == del_act:
            confirm = QMessageBox.question(
                self, "Delete Counter",
                f"Delete \"{self._counter['title']}\" and its entire press "
                "and payout log? This cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes,
            )
            if confirm == QMessageBox.StandardButton.Yes:
                self._db.delete_counter(self._counter["id"])
                self.delete_requested.emit(self._counter["id"])


# ---------------------------------------------------------------------------
# Archived timer row (Archive panel list item)
# ---------------------------------------------------------------------------

class ArchivedTimerRow(QWidget):
    """One row in the Archive panel: colour dot, title, lifetime totals,
    and Unarchive / Delete actions."""

    unarchive_requested = pyqtSignal(int)   # timer_id
    delete_requested = pyqtSignal(int)      # timer_id

    def __init__(self, timer: dict, db: CalendarDB, parent=None):
        super().__init__(parent)
        self._timer = timer
        self._db = db
        self._build()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = QWidget()
        card.setObjectName("timer_card")
        outer.addWidget(card)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        dot = QLabel("●")
        dot_font = QFont()
        dot_font.setPointSize(16)
        dot.setFont(dot_font)
        dot.setFixedWidth(20)
        dot.setStyleSheet(f"color: {self._timer.get('color', _styles.BLUE)};")
        layout.addWidget(dot)

        info = QVBoxLayout()
        info.setSpacing(2)
        title_lbl = QLabel(self._timer.get("title", "Untitled Timer"))
        title_font = QFont()
        title_font.setWeight(QFont.Weight.DemiBold)
        title_lbl.setFont(title_font)
        info.addWidget(title_lbl)

        sessions = self._db.get_timer_sessions(self._timer["id"])
        total_secs = _sessions_total_secs(sessions)
        sub_parts = [f"{_fmt_duration(total_secs)} tracked lifetime", f"{len(sessions)} session(s)"]
        is_work = self._timer.get("timer_type", "work") == "work"
        if is_work and self._timer.get("hourly_rate", 0) > 0:
            earn = _fmt_earnings(
                total_secs, self._timer["hourly_rate"], self._timer.get("currency", _DEFAULT_CURRENCY)
            )
            if earn:
                sub_parts.append(f"{earn} earned lifetime")
        sub_lbl = QLabel("  ·  ".join(sub_parts))
        sub_lbl.setObjectName("secondary")
        info.addWidget(sub_lbl)
        layout.addLayout(info, 1)

        unarchive_btn = QPushButton("Unarchive")
        unarchive_btn.setObjectName("flat")
        unarchive_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        unarchive_btn.setToolTip("Move this timer back to Active")
        unarchive_btn.clicked.connect(lambda: self.unarchive_requested.emit(self._timer["id"]))
        layout.addWidget(unarchive_btn)

        del_btn = QPushButton("Delete")
        del_btn.setObjectName("stop_btn")
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setToolTip("Permanently delete this timer and its session history")
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self._timer["id"]))
        layout.addWidget(del_btn)


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
        self._counter_cards: dict[int, CounterCard] = {}  # counter_id → card
        self._dark = False

        self._section = "active"        # "active" | "archive" | "stats"
        self._stats_period = "week"     # "week" | "month" | "all"
        self._stats_selected_ids: set[int] = set()  # empty = aggregate all active timers

        self._build()

        # 1-second tick for live clocks.
        # The timer is paused via hideEvent/showEvent so it only fires while
        # the Timer tab is actually visible — no CPU or DB work on other tabs.
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(1000)
        self._tick_timer.timeout.connect(self._tick)
        # Don't start here — showEvent will start it when the tab becomes visible.

        self.reload()

    # ------------------------------------------------------------------
    # Visibility — pause/resume tick so we do zero work on other tabs
    # ------------------------------------------------------------------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._tick_timer.start()
        self._tick()  # immediate refresh so clocks are current when tab opens

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._tick_timer.stop()

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

        top_layout.addSpacing(12)
        for label, sect in [("Active", "active"), ("Archive", "archive"), ("Stats", "stats")]:
            btn = QPushButton(label)
            btn.setObjectName("seg_btn")
            btn.setFixedHeight(28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, s=sect: self._set_section(s))
            top_layout.addWidget(btn)
            setattr(self, f"_sect_btn_{sect}", btn)

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

        new_counter_btn = QPushButton("+ New Counter")
        new_counter_btn.setObjectName("seg_btn")
        new_counter_btn.setFixedHeight(30)
        new_counter_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_counter_btn.clicked.connect(self._on_new_counter)
        top_layout.addWidget(new_counter_btn)

        root.addWidget(top)

        # ── Scroll area for cards (Active view) ─────────────────────────────
        self._active_panel = QScrollArea()
        self._active_panel.setWidgetResizable(True)
        self._active_panel.setFrameShape(QFrame.Shape.NoFrame)

        self._cards_widget = QWidget()
        outer_layout = QVBoxLayout(self._cards_widget)
        outer_layout.setContentsMargins(16, 12, 16, 12)
        outer_layout.setSpacing(8)

        # Timers section
        self._cards_layout = QVBoxLayout()
        self._cards_layout.setSpacing(8)
        outer_layout.addLayout(self._cards_layout)

        # Counters section
        outer_layout.addSpacing(8)
        counters_heading = QLabel("Counters")
        counters_heading_font = QFont()
        counters_heading_font.setPointSize(12)
        counters_heading_font.setWeight(QFont.Weight.DemiBold)
        counters_heading.setFont(counters_heading_font)
        counters_heading.setObjectName("secondary")
        outer_layout.addWidget(counters_heading)

        self._counters_layout = QVBoxLayout()
        self._counters_layout.setSpacing(8)
        outer_layout.addLayout(self._counters_layout)

        outer_layout.addStretch()

        self._active_panel.setWidget(self._cards_widget)

        self._archive_panel = self._build_archive_panel()
        self._stats_panel = self._build_stats_panel()

        self._stack = QStackedWidget()
        self._stack.addWidget(self._active_panel)
        self._stack.addWidget(self._archive_panel)
        self._stack.addWidget(self._stats_panel)
        root.addWidget(self._stack, stretch=1)

        self._set_section("active")

    def _build_archive_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        self._archive_layout = QVBoxLayout()
        self._archive_layout.setSpacing(8)
        layout.addLayout(self._archive_layout)
        layout.addStretch()
        scroll.setWidget(w)
        return scroll

    def _build_stats_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        period_row = QHBoxLayout()
        for label, period in [("Week", "week"), ("Month", "month"), ("All-time", "all")]:
            btn = QPushButton(label)
            btn.setObjectName("seg_btn")
            btn.setFixedHeight(26)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, p=period: self._set_stats_period(p))
            period_row.addWidget(btn)
            setattr(self, f"_period_btn_{period}", btn)
        period_row.addStretch()
        layout.addLayout(period_row)

        tiles_row = QGridLayout()
        tiles_row.setSpacing(10)
        self._tile_tracked_time = self._make_stat_tile("Tracked Time")
        self._tile_earnings = self._make_stat_tile("Total Earnings")
        self._tile_active_timers = self._make_stat_tile("Active Timers")
        self._tile_sessions = self._make_stat_tile("Sessions")
        tiles_row.addWidget(self._tile_tracked_time, 0, 0)
        tiles_row.addWidget(self._tile_earnings, 0, 1)
        tiles_row.addWidget(self._tile_active_timers, 0, 2)
        tiles_row.addWidget(self._tile_sessions, 0, 3)
        layout.addLayout(tiles_row)

        checklist_heading = QLabel("Timers  (check to aggregate a subset — none checked = all)")
        heading_font = QFont()
        heading_font.setPointSize(12)
        heading_font.setWeight(QFont.Weight.DemiBold)
        checklist_heading.setFont(heading_font)
        checklist_heading.setObjectName("secondary")
        layout.addWidget(checklist_heading)

        self._stats_checklist_layout = QVBoxLayout()
        self._stats_checklist_layout.setSpacing(4)
        layout.addLayout(self._stats_checklist_layout)

        layout.addStretch()
        scroll.setWidget(w)
        return scroll

    def _make_stat_tile(self, title: str) -> QWidget:
        tile = QWidget()
        tile.setObjectName("timer_card")
        tl = QVBoxLayout(tile)
        tl.setContentsMargins(14, 10, 14, 10)
        tl.setSpacing(2)
        val_lbl = QLabel("—")
        val_lbl.setWordWrap(True)
        vf = QFont()
        vf.setPointSize(18)
        vf.setWeight(QFont.Weight.Bold)
        val_lbl.setFont(vf)
        tl.addWidget(val_lbl)
        title_lbl = QLabel(title)
        title_lbl.setObjectName("secondary")
        tl.addWidget(title_lbl)
        tile._value_label = val_lbl  # stash for later updates
        return tile

    # ------------------------------------------------------------------
    # Section / period switching (Active / Archive / Stats)
    # ------------------------------------------------------------------

    def _style_seg_btn(self, btn: QPushButton, active: bool) -> None:
        btn.setProperty("active", active)
        btn.style().unpolish(btn)
        btn.style().polish(btn)

    def _set_section(self, section: str) -> None:
        self._section = section
        widget = {
            "active": self._active_panel,
            "archive": self._archive_panel,
            "stats": self._stats_panel,
        }[section]
        self._stack.setCurrentWidget(widget)
        for s in ("active", "archive", "stats"):
            btn = getattr(self, f"_sect_btn_{s}", None)
            if btn:
                self._style_seg_btn(btn, s == section)
        if section == "active":
            self.reload()
        elif section == "archive":
            self._reload_archive()
        elif section == "stats":
            self._reload_stats_panel()

    def _set_stats_period(self, period: str) -> None:
        self._stats_period = period
        for p in ("week", "month", "all"):
            btn = getattr(self, f"_period_btn_{p}", None)
            if btn:
                self._style_seg_btn(btn, p == period)
        self._recompute_stats_tiles()

    def _period_start_date(self) -> Optional[str]:
        today = datetime.date.today()
        if self._stats_period == "week":
            return (today - datetime.timedelta(days=7)).isoformat()
        if self._stats_period == "month":
            return (today - datetime.timedelta(days=30)).isoformat()
        return None  # all-time

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                # setParent(None) detaches it from the widget tree immediately
                # (so it stops being painted); deleteLater() alone leaves it
                # visible at its old position until the deferred-delete event
                # actually runs, which briefly ghosts the old row on reload.
                w.setParent(None)
                w.deleteLater()

    # ------------------------------------------------------------------
    # Archive panel
    # ------------------------------------------------------------------

    def _reload_archive(self) -> None:
        self._clear_layout(self._archive_layout)
        archived = [t for t in self._db.get_timers(include_archived=True) if t.get("archived")]
        if not archived:
            lbl = QLabel("No archived timers.\nArchive a timer from its ⋯ menu to see it here.")
            lbl.setObjectName("secondary")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setContentsMargins(0, 40, 0, 0)
            self._archive_layout.addWidget(lbl)
            return
        for t in archived:
            row = ArchivedTimerRow(t, self._db, self)
            row.unarchive_requested.connect(self._on_unarchive_timer)
            row.delete_requested.connect(self._on_delete_archived_timer)
            self._archive_layout.addWidget(row)

    def _on_unarchive_timer(self, timer_id: int) -> None:
        self._db.update_timer(timer_id, archived=0)
        self._reload_archive()
        self.reload()

    def _on_delete_archived_timer(self, timer_id: int) -> None:
        timer = next((t for t in self._db.get_timers(include_archived=True) if t["id"] == timer_id), None)
        title = timer["title"] if timer else "this timer"
        confirm = QMessageBox.question(
            self, "Delete Archived Timer",
            f"Permanently delete \"{title}\" and its entire session history? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,  # Enter confirms; Escape still cancels
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self._db.delete_timer(timer_id)
            self._reload_archive()

    # ------------------------------------------------------------------
    # Stats panel
    # ------------------------------------------------------------------

    def _reload_stats_panel(self) -> None:
        active_timers = self._db.get_timers(include_archived=False)
        valid_ids = {t["id"] for t in active_timers}
        # Drop selections for timers that no longer exist / got archived.
        self._stats_selected_ids &= valid_ids

        self._clear_layout(self._stats_checklist_layout)
        if not active_timers:
            lbl = QLabel("No active timers yet.")
            lbl.setObjectName("secondary")
            self._stats_checklist_layout.addWidget(lbl)
        for t in active_timers:
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(2, 0, 2, 0)
            rl.setSpacing(6)
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {t.get('color', _styles.BLUE)};")
            dot.setFixedWidth(16)
            rl.addWidget(dot)
            chk = QCheckBox(t["title"])
            chk.setChecked(t["id"] in self._stats_selected_ids)
            chk.toggled.connect(lambda checked, tid=t["id"]: self._on_stats_checkbox_toggled(tid, checked))
            rl.addWidget(chk)
            rl.addStretch()
            self._stats_checklist_layout.addWidget(row)

        self._recompute_stats_tiles()

    def _on_stats_checkbox_toggled(self, timer_id: int, checked: bool) -> None:
        if checked:
            self._stats_selected_ids.add(timer_id)
        else:
            self._stats_selected_ids.discard(timer_id)
        self._recompute_stats_tiles()

    def _recompute_stats_tiles(self) -> None:
        active_timers = self._db.get_timers(include_archived=False)
        included_ids = self._stats_selected_ids if self._stats_selected_ids else {t["id"] for t in active_timers}
        period_start = self._period_start_date()

        total_secs = 0.0
        earn_by_currency: dict[str, float] = {}
        session_count = 0

        for t in active_timers:
            if t["id"] not in included_ids:
                continue
            sessions = self._db.get_timer_sessions(t["id"])
            is_work = t.get("timer_type", "work") == "work"
            currency = t.get("currency", _DEFAULT_CURRENCY)
            rate = t.get("hourly_rate", 0)
            for s in sessions:
                try:
                    s_date = datetime.datetime.fromisoformat(s["start_time"]).date().isoformat()
                except Exception:
                    s_date = ""
                if period_start is not None and s_date < period_start:
                    continue
                secs = _duration_secs(s["start_time"], s.get("end_time"))
                total_secs += secs
                session_count += 1
                if is_work and rate > 0:
                    earn_by_currency[currency] = earn_by_currency.get(currency, 0.0) + (secs / 3600) * rate

        self._tile_tracked_time._value_label.setText(_fmt_duration(total_secs))
        if earn_by_currency:
            parts = [f"{_currency_symbol(c)}{amt:,.2f}" for c, amt in earn_by_currency.items()]
            self._tile_earnings._value_label.setText("  ·  ".join(parts))
        else:
            self._tile_earnings._value_label.setText("—")
        self._tile_active_timers._value_label.setText(str(len(included_ids)))
        self._tile_sessions._value_label.setText(str(session_count))

    # ------------------------------------------------------------------
    # Load / reload
    # ------------------------------------------------------------------

    def reload(self) -> None:
        """Rebuild card lists from DB."""
        self._reload_timers()
        self._reload_counters()
        self._update_summary()

    def _reload_timers(self) -> None:
        timers = self._db.get_timers(include_archived=False)
        timer_ids = {t["id"] for t in timers}

        # Remove cards for deleted/archived timers
        for tid in list(self._cards.keys()):
            if tid not in timer_ids:
                card = self._cards.pop(tid)
                self._cards_layout.removeWidget(card)
                # setParent(None) detaches it from the widget tree immediately
                # (so it stops being painted); deleteLater() alone leaves it
                # visible at its old position — still a child, just no longer
                # layout-managed — until the deferred-delete event actually
                # runs, which briefly ghosts the old card under the new list.
                card.setParent(None)
                card.deleteLater()

        # Add cards for new timers (insert before the stretch)
        for i, t in enumerate(timers):
            if t["id"] not in self._cards:
                card = TimerCard(t, self._db, self)
                card.changed.connect(self._update_summary)
                card.delete_requested.connect(self._on_card_deleted)
                self._cards[t["id"]] = card
                self._cards_layout.insertWidget(i, card)

        self._show_empty_state(len(timers) == 0)

    def _reload_counters(self) -> None:
        counters = self._db.get_counters(include_archived=False)
        counter_ids = {c["id"] for c in counters}

        for cid in list(self._counter_cards.keys()):
            if cid not in counter_ids:
                card = self._counter_cards.pop(cid)
                self._counters_layout.removeWidget(card)
                card.deleteLater()

        for i, c in enumerate(counters):
            if c["id"] not in self._counter_cards:
                card = CounterCard(c, self._db, self)
                card.changed.connect(self._update_summary)
                card.delete_requested.connect(self._on_counter_card_deleted)
                self._counter_cards[c["id"]] = card
                self._counters_layout.insertWidget(i, card)

        self._show_counters_empty_state(len(counters) == 0)

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

    def _show_counters_empty_state(self, empty: bool) -> None:
        if not hasattr(self, "_counters_empty_lbl"):
            self._counters_empty_lbl = QLabel(
                "No counters yet.\nClick \"+ New Counter\" to start a tally."
            )
            self._counters_empty_lbl.setObjectName("secondary")
            self._counters_empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._counters_empty_lbl.setContentsMargins(0, 16, 0, 16)
            self._counters_layout.insertWidget(0, self._counters_empty_lbl)
        self._counters_empty_lbl.setVisible(empty)

    def _update_summary(self) -> None:
        """Recompute daily total and earnings across all timers.

        Reuses each TimerCard's cached session list so we issue zero extra
        DB queries when the timers are not running.  The cards already
        refreshed from the DB (if needed) in their own tick() calls.
        """
        today = datetime.date.today().isoformat()
        total_secs = 0.0
        # Accumulate earnings per currency separately (timers can use different currencies)
        earn_by_currency: dict[str, float] = {}
        any_running = False

        for timer_id, card in self._cards.items():
            t = card._timer
            # Use the card's session cache; fall back to a DB query only if
            # the card hasn't been ticked yet (e.g. on the very first reload).
            sessions = card._cached_sessions
            if sessions is None:
                sessions = self._db.get_timer_sessions(timer_id)
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

        # Fold today's counter payouts into the same per-currency totals.
        total_count_today = 0
        for counter_id, card in self._counter_cards.items():
            c = card._counter
            presses = card._cached_presses
            if presses is None:
                presses = self._db.get_counter_presses(counter_id)
            currency = c.get("currency", _DEFAULT_CURRENCY)
            price = c.get("price_per_unit", 0)
            for p in presses:
                try:
                    p_date = datetime.datetime.fromisoformat(p["pressed_at"]).date().isoformat()
                except Exception:
                    p_date = ""
                if p_date == today:
                    total_count_today += p.get("delta", 0)
                    if price > 0:
                        earn_by_currency[currency] = (
                            earn_by_currency.get(currency, 0.0) + p.get("delta", 0) * price
                        )

        parts = [f"Today: {_fmt_duration(total_secs)}"]
        if total_count_today:
            parts.append(f"{total_count_today:,} counted")
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
        # Re-sync to the OS timezone in case it changed while the app was
        # running (e.g. laptop travel) — datetime.now() can otherwise keep
        # using the zone that was active when the process started.
        _time.tzset()
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
                max_session_minutes=dlg.result_max_session_minutes,
            )
            self.reload()
            if self._section == "stats":
                self._reload_stats_panel()

    def _on_card_deleted(self, timer_id: int) -> None:
        card = self._cards.pop(timer_id, None)
        if card:
            self._cards_layout.removeWidget(card)
            card.setParent(None)  # detach immediately — see _reload_timers note
            card.deleteLater()
        timers = self._db.get_timers()
        self._show_empty_state(len(timers) == 0)
        self._update_summary()

    def _on_new_counter(self) -> None:
        existing = self._db.get_counters(include_archived=True)
        color = _TIMER_COLORS[len(existing) % len(_TIMER_COLORS)]
        dlg = CounterDialog(self, color=color)
        if dlg.exec():
            self._db.create_counter(
                title=dlg.result_title,
                price_per_unit=dlg.result_rate,
                currency=dlg.result_currency,
                color=dlg.result_color,
            )
            self.reload()

    def _on_counter_card_deleted(self, counter_id: int) -> None:
        card = self._counter_cards.pop(counter_id, None)
        if card:
            self._counters_layout.removeWidget(card)
            card.deleteLater()
        counters = self._db.get_counters()
        self._show_counters_empty_state(len(counters) == 0)
        self._update_summary()

    # ------------------------------------------------------------------
    # Theme / config
    # ------------------------------------------------------------------

    def apply_theme(self, dark: bool) -> None:
        self._dark = dark
        self._apply_card_styles()

    def _apply_card_styles(self) -> None:
        bg = _styles.D_WHITE if self._dark else _styles.WHITE
        card_bg = _styles.D_GRAY_LIGHT if self._dark else _styles.GRAY_LIGHT
        border = _styles.D_GRAY_BORDER if self._dark else _styles.GRAY_BORDER
        text2 = _styles.D_GRAY_TEXT if self._dark else _styles.GRAY_TEXT
        destructive = _styles.DESTRUCTIVE_DARK if self._dark else _styles.DESTRUCTIVE

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
                color: #2fae5c;
                font-weight: bold;
                font-size: 13px;
            }}
            QPushButton#start_btn {{
                background: {_styles.BLUE};
                color: {_styles.ON_ACCENT};
                border-radius: 5px;
                font-weight: bold;
            }}
            QPushButton#start_btn:hover {{
                background: {_styles.BLUE_HOVER};
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
                color: {destructive};
                border: 1px solid {destructive};
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
