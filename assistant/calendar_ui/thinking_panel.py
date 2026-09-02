"""Assistant "thinking" panel (Mac) — the desktop twin of the iOS timeline.

The iPhone renders each pipeline stage (STT → vocab → rule/LLM → validate →
execute → verify) as a timeline with icons, per-stage timings and a result
card. The Mac used to surface the same run as a single emoji on the mic
button plus a 3-second toast, so there was no way to see *why* it did what
it did. This renders the identical trace, in the app's own "moody dev-tool"
language: a card that fills in live while a command runs.

The widget itself is just the card. It used to live inside the calendar
window; it is now the whole content of `assistant.thinking_hud`, a separate
always-on-top app, so a command spoken from the phone while you are in another
application is still visible — and still visible with the calendar closed. The
HUD feeds it from `assistant.trace_bus`.
"""

from __future__ import annotations

import datetime as _dt

from PyQt6.QtCore import (
    QEasingCurve, QPoint, QPropertyAnimation, QRect, QSize, Qt, QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QDialog, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QLayout,
    QLineEdit, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from assistant.calendar_ui import icons
from assistant.calendar_ui import styles as _styles

PANEL_WIDTH = 400
PANEL_HEIGHT = 440

# How many widgets from finished commands to keep behind the current one. Each
# is a live Qt widget, and roughly seven make up one command, so this is about
# the last dozen commands — far more than anyone scrolls back through.
MAX_HISTORY_WIDGETS = 90

# How many past commands the History list offers. The bus keeps more; this is
# about how long the list takes to build and how far anyone actually scrolls.
HISTORY_LIMIT = 200

# stage -> icon file in calendar_ui/icons (same names the iOS AssistantIcon uses)
_STAGE_ICONS = {
    "stt": "heard", "vocab": "vocab", "rule": "rule", "memory": "memory",
    "llm": "llm", "validate": "validate", "execute": "execute",
    "verify": "verify", "done": "done", "error": "error",
}


def _fmt_ms(ms: int) -> str:
    """Always seconds. Two decimals under a second so a fast step still reads
    as a duration rather than flattening to "0.0 s"; one decimal above, where
    a hundredth is noise."""
    secs = ms / 1000
    # Branch on the rounded value, or 999 ms prints "1.00 s" while 1000 ms
    # prints "1.0 s" right next to it.
    return f"{secs:.2f} s" if round(secs, 2) < 1 else f"{secs:.1f} s"


# What the producers call themselves → what to call it on screen. The API
# server publishes `Trace.source`, which is "ios"; the calendar window used to
# hardcode "iPhone" on its way past, and nothing did once the HUD started
# reading the source off the bus itself.
_SOURCE_LABELS = {
    "mac": "Mac", "macos": "Mac", "desktop": "Mac", "laptop": "Mac",
    "ios": "iPhone", "iphone": "iPhone", "phone": "iPhone", "ipad": "iPad",
    "watch": "Apple Watch", "watchos": "Apple Watch",
}


def _source_label(source: str) -> str:
    return _SOURCE_LABELS.get((source or "").strip().lower(), source or "Mac")


class _Theme:
    """Resolved colors for one theme pass — passed down to every child."""

    def __init__(self, dark: bool) -> None:
        s = _styles
        self.dark = dark
        self.bg = s.D_GRAY_BG if dark else s.WHITE
        self.surface = s.D_GRAY_LIGHT if dark else s.GRAY_LIGHT
        self.border = s.D_GRAY_BORDER if dark else s.GRAY_BORDER
        self.text = s.D_GRAY_DARK if dark else s.GRAY_DARK
        self.text2 = s.D_GRAY_TEXT if dark else s.GRAY_TEXT
        self.accent = s.get_accent()
        self.on_accent = s.on_color(self.accent)
        self.destructive = s.DESTRUCTIVE_DARK if dark else s.DESTRUCTIVE
        self.purple = "#a78bfa" if dark else "#7c58b0"
        self.green = "#3ecf7f" if dark else "#2fae5c"
        self.orange = "#f0a35e" if dark else "#b84e0e"

    def stage_color(self, stage: str, ok: bool) -> str:
        if not ok:
            return self.destructive
        return {"rule": self.accent, "llm": self.purple,
                "done": self.green, "verify": self.orange}.get(stage, self.text2)


# ------------------------------------------------------------------ layout

class FlowLayout(QLayout):
    """Left-to-right layout that wraps — for the tappable transcript words.

    Qt ships no wrapping layout; this is the standard minimal implementation
    (measure in `_do_layout`, place when not in test-only mode).
    """

    def __init__(self, parent=None, spacing: int = 5) -> None:
        super().__init__(parent)
        self._items: list = []
        self._space = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item) -> None:      # noqa: N802 (Qt API)
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, i):                  # noqa: N802
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):                  # noqa: N802
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):        # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:   # noqa: N802
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:          # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:       # noqa: N802
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        x, y, line_height = rect.x(), rect.y(), 0
        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + self._space
            if next_x - self._space > rect.right() and line_height > 0:
                x = rect.x()
                y += line_height + self._space
                next_x = x + hint.width() + self._space
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y()


# ------------------------------------------------------------------ pieces

class _Spinner(QWidget):
    """Small rotating arc — shown while the run is still in flight."""

    def __init__(self, color: str, size: int = 14, parent=None) -> None:
        super().__init__(parent)
        self._color = color
        self._angle = 0
        self.setFixedSize(size, size)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(60)

    def set_color(self, color: str) -> None:
        self._color = color
        self.update()

    def _tick(self) -> None:
        self._angle = (self._angle + 30) % 360
        self.update()

    def paintEvent(self, _event) -> None:   # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(self._color))
        pen.setWidthF(1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        r = self.rect().adjusted(2, 2, -2, -2)
        # Qt angles are 1/16th of a degree, counter-clockwise from 3 o'clock
        p.drawArc(r, -self._angle * 16, 270 * 16)
        p.end()


class _DetailLabel(QLabel):
    """Wrapped detail text, clamped to 3 lines until clicked (like iOS)."""

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._expanded = False
        self._clamp()

    def _clamp(self) -> None:
        if self._expanded:
            self.setMaximumHeight(16777215)
        else:
            self.setMaximumHeight(int(self.fontMetrics().lineSpacing() * 3) + 2)

    def mousePressEvent(self, _event) -> None:   # noqa: N802
        self._expanded = not self._expanded
        self._clamp()
        self.updateGeometry()


class _StepRow(QWidget):
    """One timeline entry: badge + connector on the left, text on the right.

    The badge and the connector line are painted rather than laid out so the
    line always spans the row's real height, however far the detail text wraps.
    """

    BADGE = 28
    GUTTER = 40

    def __init__(self, step: dict, theme: _Theme, parent=None) -> None:
        super().__init__(parent)
        self._step = step
        self._theme = theme
        self._is_last = True

        lay = QVBoxLayout(self)
        lay.setContentsMargins(self.GUTTER, 2, 4, 14)
        lay.setSpacing(2)

        head = QHBoxLayout()
        head.setSpacing(8)
        self._title = QLabel(step.get("title", ""))
        f = self._title.font()
        f.setPointSize(f.pointSize())
        f.setWeight(QFont.Weight.DemiBold)
        self._title.setFont(f)
        head.addWidget(self._title)
        head.addStretch(1)
        self._ms = QLabel(_fmt_ms(int(step.get("ms", 0))))
        mf = QFont()
        mf.setFamilies(["SF Mono", "Menlo", "Consolas", "monospace"])
        mf.setPointSize(max(9, self._ms.font().pointSize() - 2))
        self._ms.setFont(mf)
        head.addWidget(self._ms)
        lay.addLayout(head)

        detail = (step.get("detail") or "").strip()
        self._detail = _DetailLabel(detail) if detail else None
        if self._detail is not None:
            df = self._detail.font()
            df.setPointSize(max(9, df.pointSize() - 1))
            self._detail.setFont(df)
            lay.addWidget(self._detail)

        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self.apply_theme(theme)

    def set_last(self, is_last: bool) -> None:
        self._is_last = is_last
        self.update()

    def apply_theme(self, theme: _Theme) -> None:
        self._theme = theme
        ok = bool(self._step.get("ok", True))
        self._title.setStyleSheet(f"color: {theme.text};")
        self._ms.setStyleSheet(f"color: {theme.text2};")
        if self._detail is not None:
            color = theme.text if ok else theme.destructive
            self._detail.setStyleSheet(f"color: {color};")
        self.update()

    def paintEvent(self, _event) -> None:   # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        theme = self._theme
        stage = self._step.get("stage", "")
        ok = bool(self._step.get("ok", True))
        color = QColor(theme.stage_color(stage, ok))

        d = self.BADGE
        top = 2
        halo = QColor(color)
        halo.setAlphaF(0.18)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(halo)
        p.drawEllipse(4, top, d, d)

        pm = icons.pixmap(_STAGE_ICONS.get(stage, "pending"), color.name(), 14)
        p.drawPixmap(4 + (d - 14) // 2, top + (d - 14) // 2, pm)

        if not self._is_last:
            pen = QPen(QColor(theme.border))
            pen.setWidthF(1.5)
            p.setPen(pen)
            x = 4 + d / 2
            p.drawLine(int(x), top + d + 3, int(x), self.height())
        p.end()


class _WordChip(QLabel):
    """One transcript word — click to teach the assistant the right spelling.

    A QLabel rather than a QPushButton: buttons carry a platform minimum
    width, which spaced the words out far enough that the sentence stopped
    reading as a sentence.
    """

    clicked = pyqtSignal()

    def __init__(self, word: str, theme: _Theme, parent=None) -> None:
        super().__init__(word, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._hover = False
        self.apply_theme(theme)

    def apply_theme(self, theme: _Theme) -> None:
        self._theme = theme
        color = theme.accent if self._hover else theme.text
        border = theme.accent if self._hover else "transparent"
        self.setStyleSheet(
            f"QLabel {{ background: transparent; border: 1px solid {border};"
            f" border-radius: {_styles.RADIUS_SM}px; padding: 1px 3px; color: {color}; }}"
        )
        self.adjustSize()

    def enterEvent(self, _event) -> None:    # noqa: N802
        self._hover = True
        self.apply_theme(self._theme)

    def leaveEvent(self, _event) -> None:    # noqa: N802
        self._hover = False
        self.apply_theme(self._theme)

    def mousePressEvent(self, _event) -> None:   # noqa: N802
        self.clicked.emit()


class QuickFixDialog(QDialog):
    """"heard X → should be Y" — the Mac twin of the iOS QuickFixSheet."""

    def __init__(self, wrong: str, parent=None) -> None:
        super().__init__(parent)
        self._wrong = wrong
        self.setWindowTitle("Fix a word")
        self.setMinimumWidth(340)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(10)

        title = QLabel(f"Fix “{wrong}”")
        tf = title.font()
        tf.setWeight(QFont.Weight.Bold)
        title.setFont(tf)
        lay.addWidget(title)

        self._edit = QLineEdit(wrong)
        self._edit.selectAll()
        self._edit.returnPressed.connect(self._save)
        lay.addWidget(self._edit)

        hint = QLabel("Added to your vocabulary — future commands will use this spelling.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {_styles.D_GRAY_TEXT if _styles._dark else _styles.GRAY_TEXT};")
        lay.addWidget(hint)

        btn = QPushButton("Teach it")
        btn.setObjectName("primary")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self._save)
        lay.addWidget(btn)

    def _save(self) -> None:
        right = self._edit.text().strip()
        if not right or right == self._wrong:
            self.reject()
            return
        try:
            from assistant.stt.vocab import get_vocab
            get_vocab().add_alias(self._wrong, right)
        except Exception:
            pass
        self.accept()


class _ResultCard(QFrame):
    """What the run produced: transcript, corrections, spoken reply, feedback."""

    fix_word = pyqtSignal(str)
    feedback = pyqtSignal(str)
    retry = pyqtSignal(int)

    def __init__(self, result: dict, theme: _Theme, parent=None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._labels: list[tuple[QLabel, str]] = []
        self._chips: list[_WordChip] = []
        self._feedback_sent: str | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        transcript = (result.get("transcript") or "").strip()
        if transcript:
            heard = QLabel("I heard")
            self._labels.append((heard, "text2"))
            lay.addWidget(heard)
            chips_host = QWidget()
            chips_host.setStyleSheet("background: transparent; border: none;")
            flow = FlowLayout(chips_host, spacing=3)
            for word in transcript.split():
                chip = _WordChip(word, theme)
                chip.clicked.connect(lambda w=word: self.fix_word.emit(w.strip(".,!?;:")))
                flow.addWidget(chip)
                self._chips.append(chip)
            lay.addWidget(chips_host)
            tip = QLabel("Click a word to fix it")
            self._labels.append((tip, "text2"))
            lay.addWidget(tip)

        corrections = result.get("corrections") or []
        if corrections:
            text = "Auto-corrected: " + ", ".join(f"{c['from']} → {c['to']}" for c in corrections)
            lbl = QLabel(text)
            lbl.setWordWrap(True)
            self._labels.append((lbl, "green"))
            lay.addWidget(lbl)

        message = (result.get("message") or "").strip()
        if message:
            lbl = QLabel(message)
            lbl.setWordWrap(True)
            mf = lbl.font()
            mf.setWeight(QFont.Weight.DemiBold)
            lbl.setFont(mf)
            self._labels.append((lbl, "text"))
            lay.addWidget(lbl)

        uncertain = result.get("uncertain_words") or []
        if uncertain:
            warn = QLabel("Not sure about these — click to type the right word")
            self._labels.append((warn, "orange"))
            lay.addWidget(warn)
            host = QWidget()
            host.setStyleSheet("background: transparent; border: none;")
            flow = FlowLayout(host, spacing=4)
            for w in uncertain:
                heard = w.get("heard", "") if isinstance(w, dict) else str(w)
                cand = w.get("candidate") if isinstance(w, dict) else None
                chip = _WordChip(f"{heard} → {cand}?" if cand else heard, theme)
                chip.clicked.connect(lambda h=heard: self.fix_word.emit(h))
                flow.addWidget(chip)
                self._chips.append(chip)
            lay.addWidget(host)

        self._retry_btn: QPushButton | None = None
        if result.get("pending_id"):
            # Styled inline rather than via objectName="primary": inside this
            # card the app stylesheet's #primary rule applied `color` but not
            # `background-color`, leaving dark text on a dark button. (Same
            # PyQt6 QSS quirk the toolbar's _style_seg_btn works around.)
            self._retry_btn = QPushButton("Retry now")
            self._retry_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._retry_btn.clicked.connect(
                lambda _=False, pid=int(result["pending_id"]): self.retry.emit(pid))
            lay.addWidget(self._retry_btn)

        if result.get("memory_id") and result.get("actions"):
            self._fb_row = QHBoxLayout()
            self._fb_row.setSpacing(8)
            ask = QLabel("Was this right?")
            self._labels.append((ask, "text2"))
            self._fb_row.addWidget(ask)
            self._fb_row.addStretch(1)
            self._up = QPushButton()
            self._up.setIcon(icons.icon("thumbs_up", theme.text2, 15))
            self._down = QPushButton()
            self._down.setIcon(icons.icon("thumbs_down", theme.text2, 15))
            for b, value in ((self._up, "approved"), (self._down, "rejected")):
                b.setFlat(True)
                b.setFixedSize(26, 24)
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.clicked.connect(lambda _=False, v=value: self._send_feedback(v))
                self._fb_row.addWidget(b)
            self._fb_thanks = QLabel("")
            self._fb_thanks.hide()
            self._labels.append((self._fb_thanks, "text2"))
            self._fb_row.addWidget(self._fb_thanks)
            lay.addLayout(self._fb_row)

        self.apply_theme(theme)

    def _send_feedback(self, value: str) -> None:
        if self._feedback_sent:
            return
        self._feedback_sent = value
        self._up.hide()
        self._down.hide()
        self._fb_thanks.setText("Thanks" if value == "approved" else "Noted")
        self._fb_thanks.show()
        self.feedback.emit(value)

    def apply_theme(self, theme: _Theme) -> None:
        self._theme = theme
        self.setStyleSheet(
            f"QFrame {{ background-color: {theme.surface}; border: 1px solid {theme.border};"
            f" border-radius: {_styles.RADIUS_MD}px; }}"
        )
        for lbl, role in self._labels:
            color = {"text": theme.text, "text2": theme.text2,
                     "green": theme.green, "orange": theme.orange}[role]
            size = "font-size: 11px;" if role == "text2" else ""
            lbl.setStyleSheet(f"color: {color}; border: none; {size}")
        for chip in self._chips:
            chip.apply_theme(theme)
        if self._retry_btn is not None:
            self._retry_btn.setStyleSheet(
                f"QPushButton {{ background-color: {theme.accent}; color: {theme.on_accent};"
                f" border: 1px solid {theme.accent}; border-radius: {_styles.RADIUS_MD}px;"
                f" padding: 6px 14px; font-weight: 700; }}"
            )


# ------------------------------------------------------------------- panel

class _HistoryRow(QFrame):
    """One past command in the history list: what you said, what it did.

    A QFrame rather than a QPushButton. A button's sizeHint comes from its
    text, not from any layout put inside it, so building one as a container
    collapsed every row to 15px — two hundred of them, present and correct and
    showing nothing at all.
    """

    clicked = pyqtSignal()

    def __init__(self, entry: dict, theme, parent=None) -> None:
        super().__init__(parent)
        self.entry = entry
        result = entry.get("result") or {}
        said = (result.get("transcript") or "").strip() or "(no transcript)"
        did = (result.get("message") or "").strip() or "—"
        when = _dt.datetime.fromtimestamp(entry.get("ts") or 0).strftime("%d %b %H:%M")
        src = _source_label(entry.get("source") or "mac")
        where = "" if src == "Mac" else f" · {src}"

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)   # or :hover never fires
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(2)

        self._when = QLabel(f"{when}{where}", self)
        f = self._when.font(); f.setPointSize(max(9, f.pointSize() - 2)); self._when.setFont(f)
        lay.addWidget(self._when)

        self._said = QLabel(said if len(said) < 70 else said[:69] + "…", self)
        self._said.setWordWrap(True)
        lay.addWidget(self._said)

        self._did = QLabel(did if len(did) < 90 else did[:89] + "…", self)
        self._did.setWordWrap(True)
        f = self._did.font(); f.setPointSize(max(9, f.pointSize() - 1)); self._did.setFont(f)
        lay.addWidget(self._did)

        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self.apply_theme(theme)

    def mouseReleaseEvent(self, event) -> None:   # noqa: N802 - Qt naming
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.pos()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def apply_theme(self, theme) -> None:
        self._when.setStyleSheet(f"color: {theme.text2}; background: transparent;")
        self._said.setStyleSheet(f"color: {theme.text}; background: transparent; font-weight: 600;")
        self._did.setStyleSheet(f"color: {theme.text2}; background: transparent;")
        self.setStyleSheet(
            f"_HistoryRow {{ border: none; border-radius: 6px; background: transparent; }}"
            f"_HistoryRow:hover {{ background: {theme.surface}; }}"
        )


class _RunDivider(QWidget):
    """Heads each command in the timeline once more than one is shown.

    Without it the steps of three commands run together into one list and you
    cannot tell where an answer stopped and the next question started.
    """

    def __init__(self, text: str, theme, parent=None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 10, 0, 6)
        lay.setSpacing(8)
        self._label = QLabel(text)
        f = self._label.font()
        f.setPointSize(max(9, f.pointSize() - 1))
        self._label.setFont(f)
        lay.addWidget(self._label)
        self._line = QFrame()
        self._line.setFrameShape(QFrame.Shape.HLine)
        self._line.setFixedHeight(1)
        lay.addWidget(self._line, 1)
        self.apply_theme(theme)

    def apply_theme(self, theme) -> None:
        self._label.setStyleSheet(f"color: {theme.text2};")
        self._line.setStyleSheet(f"background: {theme.text2}; border: none;")


class ThinkingPanel(QFrame):
    """Floating card that mirrors the iOS thinking timeline.

    Parented to the window's central widget and positioned by the window, so
    it floats over whichever view is active without stealing focus.
    """

    closed = pyqtSignal()
    retry_requested = pyqtSignal(int)
    resized = pyqtSignal()          # so the window can re-anchor it to its corner

    def __init__(self, parent=None, dark: bool = True) -> None:
        super().__init__(parent)
        self._theme = _Theme(dark)
        self._rows: list[_StepRow] = []
        self._result_card: _ResultCard | None = None
        # Everything from earlier commands: step rows, dividers, result cards.
        # Kept only so it can be trimmed and re-themed; nothing reads it back.
        self._history: list[QWidget] = []
        self._source = "Mac"
        self._minimised = False
        self._finished = True
        self.setFixedSize(PANEL_WIDTH, PANEL_HEIGHT)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 150 if dark else 60))
        self.setGraphicsEffect(shadow)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # header
        self._header = QWidget()
        head = QHBoxLayout(self._header)
        head.setContentsMargins(14, 10, 8, 10)
        head.setSpacing(8)
        self._title = QLabel("Thinking")
        tf = self._title.font()
        tf.setWeight(QFont.Weight.Bold)
        self._title.setFont(tf)
        head.addWidget(self._title)
        self._count = QLabel("")
        head.addWidget(self._count)
        head.addStretch(1)
        # Minimise to the title bar. The header keeps showing the live step
        # count, so a command still in flight is visible while it's out of the way.
        self._hist_btn = QPushButton("History")
        self._hist_btn.setFlat(True)
        self._hist_btn.setFixedHeight(24)
        self._hist_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hist_btn.setToolTip("Every command the assistant has run")
        # Through a lambda, not connected directly: QPushButton.clicked emits a
        # `checked` bool, which binds to toggle_history's `on` argument as
        # False — so every click meant "hide history" and the button did
        # nothing. The minimise button beside it already does this.
        self._hist_btn.clicked.connect(lambda: self.toggle_history())
        head.addWidget(self._hist_btn)

        self._min_btn = QPushButton("–")
        self._min_btn.setFlat(True)
        self._min_btn.setFixedSize(24, 24)
        self._min_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._min_btn.setToolTip("Minimise")
        # `clicked` carries the checked state — a bool, False here — and
        # toggle_minimised's first parameter would swallow it as an explicit
        # "restore", so the button did nothing at all. Drop the argument.
        self._min_btn.clicked.connect(lambda: self.toggle_minimised())
        head.addWidget(self._min_btn)

        self._close_btn = QPushButton("×")
        self._close_btn.setFlat(True)
        self._close_btn.setFixedSize(24, 24)
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.clicked.connect(self._on_close)
        head.addWidget(self._close_btn)
        root.addWidget(self._header)

        self._header.mouseDoubleClickEvent = lambda _e: self.toggle_minimised()

        self._rule = QFrame()
        self._rule.setFixedHeight(1)
        root.addWidget(self._rule)

        # timeline
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._body = QWidget()
        self._body_lay = QVBoxLayout(self._body)
        self._body_lay.setContentsMargins(12, 12, 12, 12)
        self._body_lay.setSpacing(0)

        self._working = QWidget()
        w_lay = QHBoxLayout(self._working)
        w_lay.setContentsMargins(40, 2, 0, 8)
        w_lay.setSpacing(8)
        self._spinner = _Spinner(self._theme.accent)
        w_lay.addWidget(self._spinner)
        self._working_lbl = QLabel("Working…")
        w_lay.addWidget(self._working_lbl)
        w_lay.addStretch(1)
        self._body_lay.addWidget(self._working)
        self._working.hide()

        self._empty = QLabel("Press the mic (or ⌘J) and the assistant's steps show up here.")
        self._empty.setWordWrap(True)
        self._body_lay.addWidget(self._empty)

        self._body_lay.addStretch(1)
        self._scroll.setWidget(self._body)
        root.addWidget(self._scroll, 1)

        # The history list is its own scroll area rather than more rows in the
        # timeline: 300 past commands as step rows would be unreadable, and the
        # question "what has it done" is a different one from "what is it doing".
        # Search and filters live above the list, in their own widget so the
        # whole lot can be hidden with it.
        self._hist_tools = QWidget()
        tools = QVBoxLayout(self._hist_tools)
        tools.setContentsMargins(8, 6, 8, 4)
        tools.setSpacing(4)

        self._hist_search = QLineEdit()
        self._hist_search.setPlaceholderText("Search what you said, or what it did…")
        self._hist_search.setClearButtonEnabled(True)
        self._hist_search.textChanged.connect(self._apply_history_filter)
        tools.addWidget(self._hist_search)

        chips = QHBoxLayout()
        chips.setContentsMargins(0, 0, 0, 0)
        chips.setSpacing(4)
        # Kept to five, and each one answers a question actually worth asking of
        # a command log: where did it come from, what kind of thing was it, and
        # did it go wrong. Anything more is a query builder.
        self._hist_chips: dict[str, QPushButton] = {}
        for key, text in (("mac", "Mac"), ("ios", "iPhone"), ("events", "Events"),
                          ("tasks", "Tasks"), ("failed", "Failed")):
            b = QPushButton(text)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedHeight(20)
            # Through a lambda: clicked emits `checked`, which would bind to the
            # first positional argument of the slot. Same trap as the History
            # button, which shipped broken for exactly this reason.
            b.clicked.connect(lambda _=False: self._apply_history_filter())
            self._hist_chips[key] = b
            chips.addWidget(b)
        chips.addStretch(1)
        tools.addLayout(chips)

        self._hist_count = QLabel("")
        f = self._hist_count.font(); f.setPointSize(max(9, f.pointSize() - 2))
        self._hist_count.setFont(f)
        tools.addWidget(self._hist_count)

        self._hist_tools.hide()
        root.addWidget(self._hist_tools)

        self._hist_scroll = QScrollArea()
        self._hist_scroll.setWidgetResizable(True)
        self._hist_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._hist_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._hist_body = QWidget()
        self._hist_lay = QVBoxLayout(self._hist_body)
        self._hist_lay.setContentsMargins(8, 8, 8, 8)
        self._hist_lay.setSpacing(2)
        self._hist_empty = QLabel("Nothing yet — commands show up here once you use it.")
        self._hist_empty.setWordWrap(True)
        self._hist_lay.addWidget(self._hist_empty)
        self._hist_lay.addStretch(1)
        self._hist_scroll.setWidget(self._hist_body)
        self._hist_scroll.hide()
        root.addWidget(self._hist_scroll, 1)
        self._showing_history = False
        self._hist_rows: list = []

        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(160)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.apply_theme(dark)
        self.hide()

    # ------------------------------------------------------------- feeding

    def begin(self, source: str = "Mac") -> None:
        """A new command started — clear the timeline.

        `source` says which device it came from: the Mac runs the phone's
        commands too, so the panel labels them rather than leaving you to guess
        why a timeline appeared while you weren't talking to it. A command you
        spoke at the Mac is just "Thinking" — you know where it came from.
        """
        self._source = label = _source_label(source)
        self._title.setText("Thinking" if label == "Mac" else f"Thinking · from your {label}")

        # The timeline used to be wiped here, so the only command you could
        # ever see was the one running. Glance away while it works and the
        # answer was gone — and with it any chance of noticing that the thing
        # it did three commands ago was wrong. Previous commands stay, headed
        # by a divider, and the card scrolls.
        if self._rows or self._result_card is not None:
            when = _dt.datetime.now().strftime("%H:%M")
            head = "Thinking" if label == "Mac" else f"from your {label}"
            div = _RunDivider(f"{when} · {head}", self._theme, self._body)
            self._history.append(div)
            self._body_lay.insertWidget(self._body_lay.indexOf(self._working), div)

        self._history.extend(self._rows)
        if self._result_card is not None:
            self._history.append(self._result_card)
        self._rows = []
        self._result_card = None
        self._trim_history()

        self._finished = False
        self._empty.hide()
        self._working.show()
        self._update_count()

    def _trim_history(self) -> None:
        """Keep the card from growing without limit.

        A fixed-size panel scrolls rather than stretches, so this is about
        memory and scroll length rather than layout: past some depth nobody is
        scrolling back that far, and every row is a live widget.
        """
        while len(self._history) > MAX_HISTORY_WIDGETS:
            w = self._history.pop(0)
            w.setParent(None)
            w.deleteLater()

    def add_step(self, step: dict) -> None:
        if self._finished:      # a late step (self-check) reopens the timeline
            self._finished = False
            self._working.show()
        self._empty.hide()
        row = _StepRow(step, self._theme, self._body)
        for prev in self._rows:
            prev.set_last(False)
        row.set_last(True)
        self._rows.append(row)
        # keep the working row and the trailing stretch below the steps
        self._body_lay.insertWidget(self._body_lay.indexOf(self._working), row)
        self._update_count()
        QTimer.singleShot(0, self._scroll_to_bottom)

    def finish(self, result: dict | None = None) -> None:
        self._finished = True
        self._working.hide()
        if result:
            card = _ResultCard(result, self._theme, self._body)
            card.fix_word.connect(self._on_fix_word)
            card.feedback.connect(lambda v, r=result: self._on_feedback(r, v))
            card.retry.connect(self.retry_requested)
            self._result_card = card
            self._body_lay.insertWidget(self._body_lay.count() - 1, card)
        self._update_count()
        QTimer.singleShot(0, self._scroll_to_bottom)

    @property
    def step_count(self) -> int:
        return len(self._rows)

    @property
    def running(self) -> bool:
        return not self._finished

    def toggle_history(self, on: bool | None = None) -> None:
        """Swap the timeline for the list of everything it has ever run."""
        self._showing_history = (not self._showing_history) if on is None else on
        if self._showing_history:
            self._load_history()
        self._scroll.setVisible(not self._showing_history and not self._minimised)
        self._hist_scroll.setVisible(self._showing_history and not self._minimised)
        self._hist_tools.setVisible(self._showing_history and not self._minimised)
        self._hist_btn.setText("Back" if self._showing_history else "History")
        self._hist_btn.setToolTip("Back to the current command" if self._showing_history
                                  else "Every command the assistant has run")

    def _load_history(self) -> None:
        """Rebuild the list from the bus file — the durable record.

        Read fresh each time rather than kept in memory: it is the only copy
        that survives this process restarting, and it holds everything from
        before the card was ever opened.
        """
        for row in self._hist_rows:
            row.setParent(None)
            row.deleteLater()
        self._hist_rows.clear()

        try:
            from assistant import trace_bus
            entries = trace_bus.read_history(HISTORY_LIMIT)
        except Exception:
            entries = []

        self._hist_empty.setVisible(not entries)
        for entry in entries:
            row = _HistoryRow(entry, self._theme, self._hist_body)
            row.clicked.connect(lambda _=False, e=entry: self._open_history_entry(e))
            self._hist_rows.append(row)
            self._hist_lay.insertWidget(len(self._hist_rows) - 1, row)
        self._apply_history_filter()

    def _apply_history_filter(self) -> None:
        """Show only the rows that match the search box and the active chips.

        Rows are hidden rather than rebuilt: retyping a search should not cost
        two hundred widget constructions per keystroke.

        Chips are OR within a group and AND across groups — Mac+Events means
        "from the Mac, and about an event", which is what anyone would expect
        of two filters both switched on.
        """
        needle = self._hist_search.text().strip().lower()
        on = {k for k, b in self._hist_chips.items() if b.isChecked()}
        sources = {k for k in ("mac", "ios") if k in on}
        kinds = {k for k in ("events", "tasks") if k in on}

        shown = 0
        for row in self._hist_rows:
            entry = row.entry
            result = entry.get("result") or {}
            haystack = f"{result.get('transcript', '')} {result.get('message', '')}".lower()
            actions = [str(a) for a in (result.get("actions") or [])]

            ok = (not needle) or needle in haystack
            if ok and sources:
                ok = (entry.get("source") or "mac").lower() in sources
            if ok and kinds:
                is_event = any("event" in a for a in actions)
                is_task = any("todo" in a for a in actions)
                ok = (("events" in kinds and is_event) or ("tasks" in kinds and is_task))
            if ok and "failed" in on:
                # No action taken, or an answer that says it could not.
                msg = str(result.get("message", "")).lower()
                ok = (not actions) or "couldn't" in msg or "could not" in msg or "error" in msg
            row.setVisible(ok)
            shown += ok

        total = len(self._hist_rows)
        self._hist_count.setText(
            f"{total} command{'' if total == 1 else 's'}" if shown == total
            else f"{shown} of {total}")
        self._hist_empty.setVisible(total > 0 and shown == 0)
        if total and not shown:
            self._hist_empty.setText("Nothing matches that.")
        elif not total:
            self._hist_empty.setText("Nothing yet — commands show up here once you use it.")

    def _open_history_entry(self, entry: dict) -> None:
        """Show one past command in the timeline, as it looked when it ran."""
        self.begin(source=entry.get("source") or "mac")
        for step in entry.get("steps") or []:
            self.add_step(step)
        self.finish(entry.get("result") or {})
        self.toggle_history(False)

    def _update_count(self) -> None:
        n = len(self._rows)
        self._count.setText("" if not n else f"{n} step{'' if n == 1 else 's'}")

    def _scroll_to_bottom(self) -> None:
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _on_fix_word(self, word: str) -> None:
        QuickFixDialog(word, self.window()).exec()

    def _on_feedback(self, result: dict, value: str) -> None:
        try:
            from assistant.intent.memory import get_memory
            get_memory().set_feedback(int(result["memory_id"]), value)
        except Exception:
            pass

    # ------------------------------------------------------------ presence

    def toggle_minimised(self, minimised: bool | None = None) -> None:
        """Collapse to the title bar, or restore."""
        self._minimised = (not self._minimised) if minimised is None else minimised
        self._scroll.setVisible(not self._minimised and not self._showing_history)
        self._hist_scroll.setVisible(not self._minimised and self._showing_history)
        self._hist_tools.setVisible(not self._minimised and self._showing_history)
        self._rule.setVisible(not self._minimised)
        self._min_btn.setText("+" if self._minimised else "–")
        self._min_btn.setToolTip("Restore" if self._minimised else "Minimise")
        if self._minimised:
            self.setFixedSize(PANEL_WIDTH, self._header.sizeHint().height() + 2)
        else:
            self.setFixedSize(PANEL_WIDTH, PANEL_HEIGHT)
        self.resized.emit()

    @property
    def minimised(self) -> bool:
        return self._minimised

    @property
    def header_widget(self) -> QWidget:
        """The title bar. The HUD makes it the drag handle for its frameless
        window — a card with no title bar has to be movable by something."""
        return self._header

    def reveal(self) -> None:
        self.show()
        self.raise_()
        self._fade.stop()
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()

    def _on_close(self) -> None:
        self.hide()
        self.closed.emit()

    # --------------------------------------------------------------- theme

    def apply_theme(self, dark: bool) -> None:
        theme = _Theme(dark)
        self._theme = theme
        self.setStyleSheet(
            f"ThinkingPanel {{ background-color: {theme.bg}; border: 1px solid {theme.border};"
            f" border-radius: {_styles.RADIUS_LG}px; }}"
        )
        self._header.setStyleSheet("background: transparent;")
        self._title.setStyleSheet(f"color: {theme.text}; background: transparent;")
        self._count.setStyleSheet(f"color: {theme.text2}; background: transparent; font-size: 11px;")
        for _btn, _size in ((self._min_btn, 18), (self._close_btn, 16)):
            _btn.setStyleSheet(
                f"QPushButton {{ background: transparent; border: none; color: {theme.text2};"
                f" font-size: {_size}px; }} QPushButton:hover {{ color: {theme.text}; }}"
            )
        self._hist_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; color: {theme.text2};"
            f" font-size: 11px; padding: 0 6px; }}"
            f"QPushButton:hover {{ color: {theme.text}; }}"
        )
        self._rule.setStyleSheet(f"background-color: {theme.border}; border: none;")
        self._hist_tools.setStyleSheet("background: transparent;")
        self._hist_count.setStyleSheet(f"color: {theme.text2}; background: transparent;")
        self._hist_search.setStyleSheet(
            f"QLineEdit {{ background: {theme.surface}; border: 1px solid {theme.border};"
            f" border-radius: 6px; padding: 3px 6px; color: {theme.text}; }}"
            f"QLineEdit:focus {{ border-color: {theme.accent}; }}"
        )
        for _chip in self._hist_chips.values():
            _chip.setStyleSheet(
                f"QPushButton {{ background: transparent; border: 1px solid {theme.border};"
                f" border-radius: 10px; padding: 0 8px; font-size: 11px; color: {theme.text2}; }}"
                f"QPushButton:hover {{ color: {theme.text}; }}"
                f"QPushButton:checked {{ background: {theme.accent};"
                f" border-color: {theme.accent}; color: {theme.on_accent}; }}"
            )
        # The card carries its own scrollbar style. Inside the calendar app it
        # inherited one from the application stylesheet; as its own window
        # (assistant.thinking_hud) there is no application stylesheet to
        # inherit, and the native scrollbar's arrow buttons drew outside the
        # card's rounded corners.
        self._scroll.setStyleSheet(
            f"QScrollArea {{ background-color: {theme.bg}; border: none; }}"
            f"QScrollBar:vertical {{ background: transparent; width: 8px;"
            f" border: none; margin: 4px 2px 4px 2px; }}"
            f"QScrollBar::handle:vertical {{ background: {theme.border};"
            f" border-radius: 4px; min-height: 30px; }}"
            f"QScrollBar::handle:vertical:hover {{ background: {theme.text2}; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}"
            f"QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}"
            f"QScrollBar:horizontal {{ height: 0; }}"
        )
        self._body.setStyleSheet(f"background-color: {theme.bg};")
        self._working.setStyleSheet("background: transparent;")
        self._working_lbl.setStyleSheet(f"color: {theme.text2}; background: transparent;")
        self._empty.setStyleSheet(f"color: {theme.text2}; background: transparent;")
        self._spinner.set_color(theme.accent)
        for row in self._rows:
            row.apply_theme(theme)
        if self._result_card is not None:
            self._result_card.apply_theme(theme)
        effect = self.graphicsEffect()
        if isinstance(effect, QGraphicsDropShadowEffect):
            effect.setColor(QColor(0, 0, 0, 150 if dark else 60))
