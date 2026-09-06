"""Tag-suggestion history (Mac) — Gil-approved, 2026-09-06.

The tag-discovery popup (`assistant/actions/todo/tag_discovery.py`, wired in
`window.py`'s `_on_tag_suggestion`) tells the user "you can review or reverse
this later in the tag history" — this dialog is that promise kept: every past
suggestion, its verdict, and controls to change or hide it.

Same convention as `categories_dialog.py`: the Mac calendar app IS the
brain's host process (this is not the phone reaching over Tailscale), so this
talks to `assistant.actions.todo.tag_discovery` directly rather than through
the `/tags/suggestions/*` HTTP endpoints that module backs for the iPhone.

`change_answer` already handles every direction safely — accepting a refused
name, retracting an accepted one, or deciding a still-open one for the first
time (it only calls `delete_tag` when the prior status was actually
"accepted") — so every row's controls funnel through it rather than
duplicating that logic here. A suggestion's `status` from `history()` is
"accepted" or "refused" once decided; anything else (a row seeded before an
answer was recorded) reads as "Pending" and gets both Accept and Decline.
"""
from __future__ import annotations

import datetime as _dt

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from assistant.calendar_ui import styles as _styles


def _pretty_ts(iso: str) -> str:
    """2026-09-05T14:03:11 → Fri 5 Sep, 14:03."""
    try:
        return _dt.datetime.fromisoformat(iso).strftime("%a %-d %b, %H:%M")
    except Exception:
        return iso or "-"


class _TagHistoryRow(QFrame):
    """One suggestion, its verdict, and the controls to change it."""

    def __init__(self, entry: dict, on_change, on_hide, dark: bool, parent=None) -> None:
        super().__init__(parent)
        self._entry = entry
        text2 = _styles.D_GRAY_TEXT if dark else _styles.GRAY_TEXT
        border = _styles.D_GRAY_BORDER if dark else _styles.GRAY_BORDER
        surface = _styles.D_GRAY_LIGHT if dark else _styles.GRAY_LIGHT
        self.setStyleSheet(
            f"QFrame {{ background-color: {surface}; border: 1px solid {border};"
            f" border-radius: {_styles.RADIUS_MD}px; }} QLabel {{ border: none; }}"
        )

        hidden = bool(entry.get("hidden"))
        status = entry.get("status")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(10)

        info = QVBoxLayout()
        info.setSpacing(2)
        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        name = QLabel(entry.get("name", ""))
        font = name.font()
        font.setBold(True)
        name.setFont(font)
        if hidden:
            name.setStyleSheet(f"color: {text2};")
        name_row.addWidget(name)

        if status == "accepted":
            badge_text, badge_color = "Accepted", _styles.EVENT_COLORS[1]
        elif status == "refused":
            badge_text = "Declined"
            badge_color = _styles.DESTRUCTIVE_DARK if dark else _styles.DESTRUCTIVE
        else:
            badge_text, badge_color = "Pending", _styles.BLUE
        badge = QLabel(badge_text)
        badge.setStyleSheet(
            f"color: {badge_color}; font-size: 11px; font-weight: 600; "
            f"border: 1px solid {badge_color}; border-radius: {_styles.RADIUS_SM}px; "
            f"padding: 1px 6px;"
        )
        name_row.addWidget(badge)
        if hidden:
            hidden_lbl = QLabel("hidden")
            hidden_lbl.setStyleSheet(f"color: {text2}; font-size: 11px; font-style: italic;")
            name_row.addWidget(hidden_lbl)
        name_row.addStretch(1)
        info.addLayout(name_row)

        when = QLabel(f"Asked {_pretty_ts(entry.get('ts', ''))}")
        when.setStyleSheet(f"color: {text2}; font-size: 11px;")
        info.addWidget(when)
        lay.addLayout(info, 1)

        buttons = QHBoxLayout()
        buttons.setSpacing(6)

        def _btn(label: str, accept: bool, destructive: bool = False) -> QPushButton:
            b = QPushButton(label)
            if destructive:
                b.setObjectName("destructive")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda: on_change(entry.get("name", ""), accept))
            buttons.addWidget(b)
            return b

        if status == "accepted":
            _btn("Retract", accept=False, destructive=True)
        elif status == "refused":
            _btn("Accept", accept=True)
        else:
            _btn("Accept", accept=True)
            _btn("Decline", accept=False, destructive=True)

        hide_btn = QPushButton("Unhide" if hidden else "Hide")
        hide_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        hide_btn.clicked.connect(lambda: on_hide(entry.get("name", ""), not hidden))
        buttons.addWidget(hide_btn)

        lay.addLayout(buttons)


class TagHistoryDialog(QDialog):
    """The reviewable record of every past tag-discovery suggestion."""

    def __init__(self, parent=None, dark: bool = True) -> None:
        super().__init__(parent)
        self.setWindowTitle("Tag Suggestion History")
        self.setMinimumSize(540, 480)
        self._dark = dark

        root = QVBoxLayout(self)
        intro = QLabel(
            "Every tag the assistant has proposed from your task history, and what you "
            "answered. Change your mind any time — accepting adds the tag back to the "
            "palette, retracting removes it again. Hidden entries stay in the record but "
            "drop out of this list until you show them.")
        intro.setWordWrap(True)
        intro.setObjectName("muted")
        root.addWidget(intro)

        self._show_hidden_cb = QCheckBox("Show hidden")
        self._show_hidden_cb.setObjectName("tag_history_show_hidden")
        self._show_hidden_cb.toggled.connect(self.reload)
        root.addWidget(self._show_hidden_cb)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._host = QWidget()
        self._list = QVBoxLayout(self._host)
        self._list.setContentsMargins(0, 0, 6, 0)
        self._list.setSpacing(8)
        self._list.addStretch(1)
        self._scroll.setWidget(self._host)
        root.addWidget(self._scroll, 1)

        self._empty_label = QLabel("No tag suggestions yet — they show up here once the "
                                   "assistant notices a theme in your tasks.")
        self._empty_label.setWordWrap(True)
        self._empty_label.setObjectName("muted")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._empty_label)

        close_btn = QPushButton("Done")
        close_btn.setObjectName("primary")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        root.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)

        self.reload()

    # ---------------------------------------------------------------- data

    def reload(self) -> None:
        while self._list.count() > 1:
            item = self._list.takeAt(0)
            w = item.widget()
            if w is not None:
                # hide() first: takeAt() only detaches the layout item, so the
                # widget stays a visible child of _host until deleteLater()'s
                # DeferredDelete event is actually processed — which can be
                # well after this call returns (Qt only guarantees it by the
                # time control reaches an outer event loop). Without hide(),
                # a reload triggered from inside another reload's own click
                # handler would find last round's rows still findable/visible.
                w.hide()
                w.deleteLater()

        from assistant.actions.todo.tag_discovery import history
        entries = history()
        show_hidden = self._show_hidden_cb.isChecked()
        visible = [e for e in entries if show_hidden or not e.get("hidden")]
        self._empty_label.setVisible(not visible)
        self._scroll.setVisible(bool(visible))
        for entry in visible:
            row = _TagHistoryRow(entry, self._on_change, self._on_hide, self._dark)
            self._list.insertWidget(self._list.count() - 1, row)

    # -------------------------------------------------------------- actions

    def _on_change(self, name: str, accept: bool) -> None:
        from assistant.actions.todo.tag_discovery import change_answer
        if not name:
            return
        try:
            change_answer(name, accept)
        except Exception as exc:
            QMessageBox.warning(self, "Tag history", f"Couldn't update “{name}”: {exc}")
        self.reload()

    def _on_hide(self, name: str, hidden: bool) -> None:
        from assistant.actions.todo.tag_discovery import set_hidden
        if not name:
            return
        try:
            set_hidden(name, hidden)
        except Exception as exc:
            QMessageBox.warning(self, "Tag history", f"Couldn't update “{name}”: {exc}")
        self.reload()


def open_tag_history(parent_window) -> None:
    """Entry point — wired from window.py's toolbar."""
    TagHistoryDialog(parent_window, dark=getattr(parent_window, "_dark", True)).exec()
