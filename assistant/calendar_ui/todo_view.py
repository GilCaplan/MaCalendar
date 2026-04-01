"""TodoView — Apple Reminders-inspired task panel for MaCalendar."""

from __future__ import annotations

import datetime
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from assistant.calendar_ui.styles import (
    BLUE,
    D_GRAY_BG,
    D_GRAY_BORDER,
    D_GRAY_DARK,
    D_GRAY_MID,
    D_GRAY_TEXT,
    D_WHITE,
    GRAY_BG,
    GRAY_BORDER,
    GRAY_DARK,
    GRAY_MID,
    GRAY_TEXT,
    WHITE,
)

_PRIORITY_COLORS = {
    "high":   "#d83b01",
    "medium": "#ca5010",
    "low":    "#107c10",
    "none":   "",
}


# ---------------------------------------------------------------------------
# TodoItemWidget — one row per task
# ---------------------------------------------------------------------------

class TodoItemWidget(QWidget):
    """A single todo row: checkbox + title (inline editable) + priority dot + delete button."""

    toggled = pyqtSignal(int, bool)    # (todo_id, new_completed_state)
    edited  = pyqtSignal(int, str)     # (todo_id, new_title)
    deleted = pyqtSignal(int)          # (todo_id,)

    def __init__(self, todo: dict, dark: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._todo = todo
        self._dark = dark
        self._editing = False
        self._build()
        self.setMouseTracking(True)

    def _build(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 6, 10, 6)
        layout.setSpacing(10)

        # Circular checkbox
        self._check = QCheckBox()
        self._check.setChecked(bool(self._todo["completed"]))
        self._check.setFixedSize(22, 22)
        self._check.toggled.connect(self._on_toggled)
        layout.addWidget(self._check)

        # Title label (click to edit)
        self._label = QLabel(self._todo["title"])
        self._label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._label.setCursor(Qt.CursorShape.IBeamCursor)
        self._label.mousePressEvent = self._start_edit  # type: ignore[assignment]
        layout.addWidget(self._label)

        # Inline editor (hidden by default)
        self._editor = QLineEdit(self._todo["title"])
        self._editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._editor.hide()
        self._editor.editingFinished.connect(self._commit_edit)
        self._editor.returnPressed.connect(self._commit_edit)
        layout.addWidget(self._editor)

        # Priority dot
        self._priority_dot = QLabel("●")
        self._priority_dot.setFixedWidth(14)
        color = _PRIORITY_COLORS.get(self._todo.get("priority", "none"), "")
        if color:
            self._priority_dot.setStyleSheet(f"color: {color}; font-size: 10px;")
            self._priority_dot.show()
        else:
            self._priority_dot.hide()
        layout.addWidget(self._priority_dot)

        # Delete button (hidden until hover)
        self._del_btn = QPushButton("×")
        self._del_btn.setFixedSize(20, 20)
        self._del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._del_btn.setToolTip("Delete task")
        self._del_btn.hide()
        self._del_btn.clicked.connect(lambda: self.deleted.emit(self._todo["id"]))
        layout.addWidget(self._del_btn)

        self._apply_completion_style()
        self._apply_theme(self._dark)

    def _apply_completion_style(self) -> None:
        if self._todo["completed"]:
            self._label.setStyleSheet("color: #a0a0a0; text-decoration: line-through;")
        else:
            self._label.setStyleSheet("")

    def _apply_theme(self, dark: bool) -> None:
        self._dark = dark
        text_color = D_GRAY_DARK if dark else GRAY_DARK
        border = D_GRAY_BORDER if dark else GRAY_BORDER
        check_border = D_GRAY_MID if dark else GRAY_MID

        self._check.setStyleSheet(f"""
            QCheckBox::indicator {{
                width: 16px; height: 16px;
                border-radius: 8px;
                border: 2px solid {check_border};
                background: transparent;
            }}
            QCheckBox::indicator:checked {{
                background-color: {BLUE};
                border-color: {BLUE};
            }}
        """)

        del_color = "#cc0000" if not dark else "#ff6666"
        self._del_btn.setStyleSheet(f"""
            QPushButton {{
                color: {del_color}; background: transparent;
                border: none; font-size: 14px; font-weight: bold;
            }}
            QPushButton:hover {{ color: #ff0000; }}
        """)

        if not self._todo["completed"]:
            self._label.setStyleSheet(f"color: {text_color};")

    def enterEvent(self, event) -> None:
        self._del_btn.show()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._del_btn.hide()
        super().leaveEvent(event)

    def _on_toggled(self, checked: bool) -> None:
        self._todo["completed"] = int(checked)
        self._apply_completion_style()
        self.toggled.emit(self._todo["id"], checked)

    def _start_edit(self, _event) -> None:
        if self._editing:
            return
        self._editing = True
        self._label.hide()
        self._editor.setText(self._todo["title"])
        self._editor.show()
        self._editor.setFocus()
        self._editor.selectAll()

    def _commit_edit(self) -> None:
        if not self._editing:
            return
        self._editing = False
        new_title = self._editor.text().strip()
        if new_title and new_title != self._todo["title"]:
            self._todo["title"] = new_title
            self._label.setText(new_title)
            self.edited.emit(self._todo["id"], new_title)
        self._editor.hide()
        self._label.show()

    def apply_theme(self, dark: bool) -> None:
        self._apply_theme(dark)


# ---------------------------------------------------------------------------
# TodoListWidget — a scrollable section of tasks for one list
# ---------------------------------------------------------------------------

class TodoListWidget(QWidget):
    """Displays all todos for a given list_name with add/complete/edit/delete."""

    todo_changed  = pyqtSignal()      # bubbles up to TodoView
    count_changed = pyqtSignal(int)   # pending task count

    def __init__(self, db, list_name: str, dark: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._db = db
        self._list_name = list_name
        self._dark = dark
        self._item_widgets: list[TodoItemWidget] = []

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._layout.addStretch()

    def populate(self, show_completed: bool = False) -> None:
        """Clear and rebuild the list from the database."""
        # Remove all existing widgets
        for w in self._item_widgets:
            w.setParent(None)
            w.deleteLater()
        self._item_widgets.clear()

        # Remove the stretch and "New Task" row (they'll be re-added)
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        todos = self._db.get_todos(list_name=self._list_name, include_completed=show_completed)

        for todo in todos:
            item = TodoItemWidget(todo, dark=self._dark)
            item.toggled.connect(self._on_toggled)
            item.edited.connect(self._on_edited)
            item.deleted.connect(self._on_deleted)
            self._layout.addWidget(item)
            self._item_widgets.append(item)

        pending = sum(1 for t in todos if not t["completed"])
        self.count_changed.emit(pending)

        # Add "New Task" row
        self._layout.addWidget(self._make_new_task_row())
        self._layout.addStretch()

    def _make_new_task_row(self) -> QWidget:
        row = QWidget()
        hl = QHBoxLayout(row)
        hl.setContentsMargins(14, 6, 10, 6)
        hl.setSpacing(10)

        # Placeholder "+" label that converts to an editor on click
        plus_label = QLabel("+ New Task")
        plus_label.setCursor(Qt.CursorShape.PointingHandCursor)
        add_color = D_GRAY_TEXT if self._dark else GRAY_TEXT
        plus_label.setStyleSheet(f"color: {add_color}; font-style: italic;")

        editor = QLineEdit()
        editor.setPlaceholderText("Task title…")
        editor.hide()

        def _start(_event):
            plus_label.hide()
            editor.show()
            editor.setFocus()

        def _commit():
            title = editor.text().strip()
            editor.blockSignals(True)
            editor.clear()
            editor.hide()
            plus_label.show()
            if title:
                self._db.create_todo(title=title, list_name=self._list_name)
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(0, self.todo_changed.emit)

        def _cancel():
            editor.clear()
            editor.hide()
            plus_label.show()

        editor.returnPressed.connect(_commit)
        editor.editingFinished.connect(lambda: _cancel() if not editor.text().strip() else _commit())
        plus_label.mousePressEvent = _start  # type: ignore[assignment]

        hl.addWidget(plus_label)
        hl.addWidget(editor)
        hl.addStretch()
        return row

    def _on_toggled(self, todo_id: int, checked: bool) -> None:
        completed_at = datetime.datetime.now().isoformat() if checked else ""
        self._db.update_todo(todo_id, completed=int(checked), completed_at=completed_at)
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, self.todo_changed.emit)

    def _on_edited(self, todo_id: int, new_title: str) -> None:
        self._db.update_todo(todo_id, title=new_title)
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, self.todo_changed.emit)

    def _on_deleted(self, todo_id: int) -> None:
        self._db.delete_todo(todo_id)
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, self.todo_changed.emit)

    def apply_theme(self, dark: bool) -> None:
        self._dark = dark
        for w in self._item_widgets:
            w.apply_theme(dark)


# ---------------------------------------------------------------------------
# SectionHeader — bold title + sync badge + gear menu
# ---------------------------------------------------------------------------

class SectionHeader(QWidget):
    """Section header with title, task count, optional sync button and gear menu."""

    sync_now_clicked  = pyqtSignal()
    sync_mode_changed = pyqtSignal(str)

    def __init__(self, title: str, show_sync_button: bool = False,
                 show_sync_gear: bool = False,
                 dark: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._dark = dark
        hl = QHBoxLayout(self)
        hl.setContentsMargins(14, 12, 12, 4)
        hl.setSpacing(6)

        # Bold section title
        self._title_lbl = QLabel(title)
        font = QFont()
        font.setPointSize(13)
        font.setBold(True)
        self._title_lbl.setFont(font)
        hl.addWidget(self._title_lbl)

        # Count badge
        self._count_lbl = QLabel()
        self._count_lbl.setStyleSheet(
            "color: #ffffff; background-color: #1a6fc4; border-radius: 8px;"
            " font-size: 10px; font-weight: 600; padding: 1px 6px;"
        )
        self._count_lbl.hide()
        hl.addWidget(self._count_lbl)

        # Sync badge (hidden by default)
        self._sync_badge = QLabel("synced")
        self._sync_badge.setStyleSheet(
            "color: #1a6fc4; font-size: 10px; padding: 1px 6px;"
            " border: 1px solid #1a6fc4; border-radius: 8px;"
        )
        self._sync_badge.hide()
        hl.addWidget(self._sync_badge)

        hl.addStretch()

        if show_sync_button:
            # Prominent "🔄 Sync Today" button
            self._sync_btn = QPushButton("🔄 Sync Today")
            self._sync_btn.setToolTip("Pull today's calendar events into this list")
            self._sync_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._sync_btn.setFixedHeight(26)
            self._sync_btn.setStyleSheet("""
                QPushButton {
                    background-color: #0078d4;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 0 10px;
                    font-size: 11px;
                }
                QPushButton:hover { background-color: #106ebe; }
                QPushButton:pressed { background-color: #005a9e; }
            """)
            self._sync_btn.clicked.connect(self.sync_now_clicked.emit)
            hl.addWidget(self._sync_btn)

        if show_sync_gear:
            # Gear for advanced sync settings
            gear = QPushButton("⚙")
            gear.setFixedSize(24, 24)
            gear.setToolTip("Sync settings")
            gear.setStyleSheet("QPushButton { background: transparent; border: none; font-size: 13px; }")
            gear.setCursor(Qt.CursorShape.PointingHandCursor)
            gear.clicked.connect(self._show_sync_menu)
            hl.addWidget(gear)

        self._apply_theme(dark)

    def set_count(self, n: int) -> None:
        """Show or hide the pending-task count badge."""
        if n > 0:
            self._count_lbl.setText(str(n))
            self._count_lbl.show()
        else:
            self._count_lbl.hide()

    def set_synced(self, synced: bool) -> None:
        self._sync_badge.setVisible(synced)

    def _show_sync_menu(self) -> None:
        menu = QMenu(self)
        menu.addAction("Sync today's calendar events here",
                       lambda: self.sync_mode_changed.emit("today"))
        menu.addAction("Sync upcoming week to General list",
                       lambda: self.sync_mode_changed.emit("general"))
        menu.addSeparator()
        menu.addAction("Clear synced tasks",
                       lambda: self.sync_mode_changed.emit("off"))
        menu.exec(self.mapToGlobal(self.rect().bottomLeft()))

    def _apply_theme(self, dark: bool) -> None:
        self._dark = dark
        text = D_GRAY_DARK if dark else GRAY_DARK
        self._title_lbl.setStyleSheet(f"color: {text};")

    def apply_theme(self, dark: bool) -> None:
        self._apply_theme(dark)


# ---------------------------------------------------------------------------
# TodoView — top-level widget
# ---------------------------------------------------------------------------

class TodoView(QWidget):
    """
    Apple Reminders-style todo panel with two sections: Today and General.
    Integrates with CalendarDB for persistence and supports calendar sync.
    """

    def __init__(self, db, config=None, parent=None) -> None:
        super().__init__(parent)
        self._db = db
        self._config = config
        self._dark = False
        self._show_completed = config.todo.show_completed if config else False
        self._sync_mode = config.todo.sync.mode if config else "off"
        self._build_ui()

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(0, 0, 0, 16)
        self._content_layout.setSpacing(0)

        # ── Today section ──
        self._today_header = SectionHeader("Today", show_sync_button=True, show_sync_gear=True, dark=self._dark)
        self._today_header.sync_now_clicked.connect(self._on_sync_now)
        self._today_header.sync_mode_changed.connect(self._on_sync_mode_changed)
        self._content_layout.addWidget(self._today_header)

        self._today_list = TodoListWidget(self._db, "today", dark=self._dark)
        self._today_list.todo_changed.connect(self.refresh)
        self._today_list.count_changed.connect(self._today_header.set_count)
        self._content_layout.addWidget(self._today_list)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {GRAY_BORDER};")
        self._content_layout.addWidget(sep)

        # ── General section ──
        self._general_header = SectionHeader("General", show_sync_gear=False, dark=self._dark)
        self._content_layout.addWidget(self._general_header)

        self._general_list = TodoListWidget(self._db, "general", dark=self._dark)
        self._general_list.todo_changed.connect(self.refresh)
        self._general_list.count_changed.connect(self._general_header.set_count)
        self._content_layout.addWidget(self._general_list)

        self._content_layout.addStretch()

        scroll.setWidget(content)
        root.addWidget(scroll)

        # Initial population
        self.refresh()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Reload todos from DB and repopulate both lists."""
        self._today_list.populate(self._show_completed)
        self._general_list.populate(self._show_completed)
        self._apply_sync_badge()

    def apply_theme(self, dark: bool) -> None:
        """Restyle all child widgets for dark/light mode."""
        self._dark = dark
        bg = D_WHITE if dark else WHITE
        border = D_GRAY_BORDER if dark else GRAY_BORDER
        self.setStyleSheet(f"background-color: {bg};")

        self._today_header.apply_theme(dark)
        self._general_header.apply_theme(dark)
        self._today_list.apply_theme(dark)
        self._general_list.apply_theme(dark)

        sep_color = D_GRAY_BORDER if dark else GRAY_BORDER
        # Repopulate to pick up new theme on item widgets
        self.refresh()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _apply_sync_badge(self) -> None:
        synced = self._sync_mode != "off"
        self._today_header.set_synced(synced and self._sync_mode == "today")

    def _on_sync_now(self) -> None:
        """Direct 'Sync Today' button — pull today's calendar events into the Today list."""
        count = self._db.sync_calendar_to_todos(list_name="today")
        self._sync_mode = "today"
        if self._config is not None:
            self._config.todo.sync.mode = "today"
            self._write_sync_mode_to_config("today")
        self.refresh()
        # Brief visual feedback on the button
        if hasattr(self._today_header, "_sync_btn"):
            btn = self._today_header._sync_btn
            btn.setText(f"✓ {count} synced" if count else "✓ Up to date")
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(2000, lambda: btn.setText("🔄 Sync Today"))

    def _on_sync_mode_changed(self, mode: str) -> None:
        """Handle sync mode selection from the gear menu."""
        self._sync_mode = mode

        if mode == "off":
            self._db.delete_todos_by_source("calendar_sync")
        else:
            self._db.sync_calendar_to_todos(list_name=mode)

        # Persist to config.yaml if config is available
        if self._config is not None:
            self._config.todo.sync.mode = mode
            self._write_sync_mode_to_config(mode)

        self.refresh()

    def _write_sync_mode_to_config(self, mode: str) -> None:
        """Update the todo.sync.mode value in config.yaml using regex replacement."""
        import os
        import re

        config_path = os.path.abspath("config.yaml")
        if not os.path.exists(config_path):
            return
        try:
            with open(config_path) as f:
                txt = f.read()
            txt = re.sub(
                r'(todo:.*?sync:.*?mode:\s*")[^"]*(")',
                lambda m: m.group(1) + mode + m.group(2),
                txt,
                flags=re.DOTALL,
            )
            with open(config_path, "w") as f:
                f.write(txt)
        except Exception:
            pass  # non-fatal if config write fails
