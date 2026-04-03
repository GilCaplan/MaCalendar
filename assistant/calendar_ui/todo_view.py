"""TodoView — Apple Reminders-inspired task panel for MaCalendar."""

from __future__ import annotations

import datetime
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
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
        self._font_size = 13
        self._build()
        self.setMouseTracking(True)

    def _build(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 6, 10, 6)
        layout.setSpacing(10)

        # Drag grip handle
        self._grip = QLabel("⠿")
        self._grip.setFixedWidth(14)
        self._grip.setCursor(Qt.CursorShape.SizeAllCursor)
        self._grip.setToolTip("Drag to reorder")
        layout.addWidget(self._grip)

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

        self._editor = QLineEdit(self._todo["title"])
        self._editor.setObjectName("todo_editor")
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
        self.setStyleSheet("background: transparent;")
        text_color = D_GRAY_DARK if dark else GRAY_DARK
        check_border = D_GRAY_MID if dark else GRAY_MID
        grip_color = D_GRAY_MID if dark else GRAY_MID

        self._grip.setStyleSheet(f"color: {grip_color}; font-size: {self._font_size - 1}px;")

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
                border: none; font-size: {self._font_size + 1}px; font-weight: bold;
            }}
            QPushButton:hover {{ color: #ff0000; }}
        """)
 
        if not self._todo["completed"]:
            self._label.setStyleSheet(f"color: {text_color}; font-size: {self._font_size}px;")

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
# TodoListWidget — draggable QListWidget for one list
# ---------------------------------------------------------------------------

class TodoListWidget(QWidget):
    """
    Displays all todos for a given list_name with add/complete/edit/delete/reorder.
    Uses a QListWidget internally for native drag-and-drop row reordering.
    """

    todo_changed  = pyqtSignal()      # bubbles up to TodoView
    count_changed = pyqtSignal(int)   # pending task count

    def __init__(self, db, list_name: str, dark: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._db = db
        self._list_name = list_name
        self._dark = dark
        self._item_widgets: list[TodoItemWidget] = []
        self._reorder_enabled = True
        self._font_size = 13

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Draggable list
        self._list_widget = QListWidget()
        self._list_widget.setDragEnabled(True)
        self._list_widget.setAcceptDrops(True)
        self._list_widget.setDropIndicatorShown(True)
        self._list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list_widget.setFrameShape(QFrame.Shape.NoFrame)
        self._list_widget.setSpacing(0)
        self._list_widget.model().rowsMoved.connect(self._on_reorder)
        outer.addWidget(self._list_widget)

        # "New Task" row below the list
        outer.addWidget(self._make_new_task_row())

    def populate(self, show_completed: bool = False) -> None:
        """Clear and rebuild the list from the database."""
        self._reorder_enabled = False
        self._list_widget.clear()
        self._item_widgets.clear()

        todos = self._db.get_todos(list_name=self._list_name, include_completed=show_completed)

        for todo in todos:
            item = QListWidgetItem(self._list_widget)
            item.setData(Qt.ItemDataRole.UserRole, todo["id"])
            widget = TodoItemWidget(todo, dark=self._dark)
            widget._font_size = self._font_size
            widget.toggled.connect(self._on_toggled)
            widget.edited.connect(self._on_edited)
            widget.deleted.connect(self._on_deleted)
            item.setSizeHint(widget.sizeHint())
            self._list_widget.setItemWidget(item, widget)
            self._item_widgets.append(widget)

        # Resize list widget to fit content
        total_h = sum(
            self._list_widget.sizeHintForRow(i) + self._list_widget.spacing()
            for i in range(self._list_widget.count())
        ) + 4
        self._list_widget.setFixedHeight(max(total_h, 10))

        pending = sum(1 for t in todos if not t["completed"])
        self.count_changed.emit(pending)
        self._reorder_enabled = True

    def _make_new_task_row(self) -> QWidget:
        row = QWidget()
        hl = QHBoxLayout(row)
        hl.setContentsMargins(14, 6, 10, 6)
        hl.setSpacing(10)

        self._plus_label = QLabel("+ New Task")
        self._plus_label.setCursor(Qt.CursorShape.PointingHandCursor)
        add_color = D_GRAY_TEXT if self._dark else GRAY_TEXT
        self._plus_label.setStyleSheet(f"color: {add_color}; font-style: italic; font-size: {self._font_size}px;")

        self._new_task_editor = QLineEdit()
        self._new_task_editor.setObjectName("new_todo_editor")
        self._new_task_editor.setPlaceholderText("Task title…")
        self._new_task_editor.hide()

        def _start(_event):
            self._plus_label.hide()
            self._new_task_editor.show()
            self._new_task_editor.setFocus()

        def _commit():
            title = self._new_task_editor.text().strip()
            self._new_task_editor.blockSignals(True)
            self._new_task_editor.clear()
            self._new_task_editor.hide()
            self._plus_label.show()
            if title:
                self._db.create_todo(title=title, list_name=self._list_name)
                QTimer.singleShot(0, self.todo_changed.emit)

        def _cancel():
            self._new_task_editor.clear()
            self._new_task_editor.hide()
            self._plus_label.show()

        self._new_task_editor.returnPressed.connect(_commit)
        self._new_task_editor.editingFinished.connect(lambda: _cancel() if not self._new_task_editor.text().strip() else _commit())
        self._plus_label.mousePressEvent = _start  # type: ignore[assignment]

        hl.addWidget(self._plus_label)
        hl.addWidget(self._new_task_editor)
        hl.addStretch()
        return row

    # ------------------------------------------------------------------
    # Drag-drop reorder
    # ------------------------------------------------------------------

    def _on_reorder(self, _parent, _start, _end, _dest, _row) -> None:
        if not self._reorder_enabled:
            return
        ids = []
        for i in range(self._list_widget.count()):
            item = self._list_widget.item(i)
            if item:
                todo_id = item.data(Qt.ItemDataRole.UserRole)
                if todo_id is not None:
                    ids.append(todo_id)
        if ids:
            self._db.reorder_todos(self._list_name, ids)

    # ------------------------------------------------------------------
    # Signal handlers
    # ------------------------------------------------------------------

    def _on_toggled(self, todo_id: int, checked: bool) -> None:
        completed_at = datetime.datetime.now().isoformat() if checked else ""
        self._db.update_todo(todo_id, completed=int(checked), completed_at=completed_at)
        QTimer.singleShot(0, self.todo_changed.emit)

    def _on_edited(self, todo_id: int, new_title: str) -> None:
        self._db.update_todo(todo_id, title=new_title)
        QTimer.singleShot(0, self.todo_changed.emit)

    def _on_deleted(self, todo_id: int) -> None:
        self._db.delete_todo(todo_id)
        QTimer.singleShot(0, self.todo_changed.emit)

    def apply_theme(self, dark: bool) -> None:
        self._dark = dark
        for w in self._item_widgets:
            w.apply_theme(dark)

        # Update "New Task" row colors
        add_color = D_GRAY_TEXT if dark else GRAY_TEXT
        self._plus_label.setStyleSheet(f"color: {add_color}; font-style: italic;")


# ---------------------------------------------------------------------------
# SectionHeader — bold title + sync badge + gear menu + clear-completed button
# ---------------------------------------------------------------------------

class SectionHeader(QWidget):
    """Section header with title, task count, optional sync button, gear menu, and clear-completed."""

    sync_now_clicked    = pyqtSignal()
    sync_mode_changed   = pyqtSignal(str)
    clear_completed_clicked = pyqtSignal()

    def __init__(self, title: str, show_sync_button: bool = False,
                 show_sync_gear: bool = False,
                 dark: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._dark = dark
        self._font_size = 13
        hl = QHBoxLayout(self)
        hl.setContentsMargins(14, 12, 12, 4)
        hl.setSpacing(6)

        # Bold section title
        self._title_lbl = QLabel(title)
        font = QFont()
        font.setPointSize(self._font_size)
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

        # Clear Completed button (hidden until there are completed tasks)
        self._clear_btn = QPushButton("Clear Completed")
        self._clear_btn.setToolTip("Delete all completed tasks in this section")
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.setFixedHeight(22)
        self._clear_btn.hide()
        self._clear_btn.setStyleSheet("""
            QPushButton {
                color: #cc0000; background: transparent;
                border: 1px solid #cc0000; border-radius: 4px;
                padding: 0 8px; font-size: 10px;
            }
            QPushButton:hover { background-color: #ffeaea; }
        """)
        self._clear_btn.clicked.connect(self.clear_completed_clicked.emit)
        hl.addWidget(self._clear_btn)

        if show_sync_button:
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
            gear = QPushButton("⚙")
            gear.setFixedSize(24, 24)
            gear.setToolTip("Sync settings")
            gear.setStyleSheet("QPushButton { background: transparent; border: none; font-size: 13px; }")
            gear.setCursor(Qt.CursorShape.PointingHandCursor)
            gear.clicked.connect(self._show_sync_menu)
            hl.addWidget(gear)

        self._apply_theme(dark)

    def set_count(self, n: int) -> None:
        if n > 0:
            self._count_lbl.setText(str(n))
            self._count_lbl.show()
        else:
            self._count_lbl.hide()

    def set_synced(self, synced: bool) -> None:
        self._sync_badge.setVisible(synced)

    def set_has_completed(self, has_completed: bool) -> None:
        """Show or hide the Clear Completed button."""
        self._clear_btn.setVisible(has_completed)

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
        self._ui_config = config.ui if config else None
        self._build_ui()

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(0, 0, 0, 16)
        self._content_layout.setSpacing(0)

        # ── Today section ──
        self._today_header = SectionHeader(
            "Today", show_sync_button=True, show_sync_gear=True, dark=self._dark
        )
        self._today_header.sync_now_clicked.connect(self._on_sync_now)
        self._today_header.sync_mode_changed.connect(self._on_sync_mode_changed)
        self._today_header.clear_completed_clicked.connect(
            lambda: self._clear_completed("today")
        )
        self._content_layout.addWidget(self._today_header)

        self._today_list = TodoListWidget(self._db, "today", dark=self._dark)
        self._today_list.todo_changed.connect(self.refresh)
        self._today_list.count_changed.connect(self._today_header.set_count)
        self._content_layout.addWidget(self._today_list)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {GRAY_BORDER};")
        self._content_layout.addWidget(sep)

        # ── General section ──
        self._general_header = SectionHeader("General", dark=self._dark)
        self._general_header.clear_completed_clicked.connect(
            lambda: self._clear_completed("general")
        )
        self._content_layout.addWidget(self._general_header)

        self._general_list = TodoListWidget(self._db, "general", dark=self._dark)
        self._general_list.todo_changed.connect(self.refresh)
        self._general_list.count_changed.connect(self._general_header.set_count)
        self._content_layout.addWidget(self._general_list)

        self._content_layout.addStretch()

        scroll.setWidget(content)
        root.addWidget(scroll)

        self.refresh()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Reload todos from DB and repopulate both lists."""
        self._today_list.populate(self._show_completed)
        self._general_list.populate(self._show_completed)
        self._apply_sync_badge()
        self._update_clear_buttons()

    def apply_theme(self, dark: bool) -> None:
        self._dark = dark
        bg = D_WHITE if dark else WHITE
        self.setStyleSheet(f"background-color: {bg};")
        self._general_header.apply_theme(dark)
        self._today_list.apply_theme(dark)
        self._general_list.apply_theme(dark)
        self.refresh()

    def apply_ui_config(self, ui_config) -> None:
        self._ui_config = ui_config
        fs = ui_config.font_tasks
        self._today_header._font_size = fs
        self._general_header._font_size = fs
        self._today_list._font_size = fs
        self._general_list._font_size = fs
        self.refresh()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _update_clear_buttons(self) -> None:
        today_todos = self._db.get_todos(list_name="today", include_completed=True)
        general_todos = self._db.get_todos(list_name="general", include_completed=True)
        self._today_header.set_has_completed(any(t["completed"] for t in today_todos))
        self._general_header.set_has_completed(any(t["completed"] for t in general_todos))

    def _clear_completed(self, list_name: str) -> None:
        self._db.delete_completed_todos(list_name=list_name)
        self.refresh()

    def _apply_sync_badge(self) -> None:
        synced = self._sync_mode != "off"
        self._today_header.set_synced(synced and self._sync_mode == "today")

    def _on_sync_now(self) -> None:
        count = self._db.sync_calendar_to_todos(list_name="today")
        self._sync_mode = "today"
        if self._config is not None:
            self._config.todo.sync.mode = "today"
            self._write_sync_mode_to_config("today")
        self.refresh()
        if hasattr(self._today_header, "_sync_btn"):
            btn = self._today_header._sync_btn
            btn.setText(f"✓ {count} synced" if count else "✓ Up to date")
            QTimer.singleShot(2000, lambda: btn.setText("🔄 Sync Today"))

    def _on_sync_mode_changed(self, mode: str) -> None:
        self._sync_mode = mode
        if mode == "off":
            self._db.delete_todos_by_source("calendar_sync")
        else:
            self._db.sync_calendar_to_todos(list_name=mode)
        if self._config is not None:
            self._config.todo.sync.mode = mode
            self._write_sync_mode_to_config(mode)
        self.refresh()

    def _write_sync_mode_to_config(self, mode: str) -> None:
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
            pass
