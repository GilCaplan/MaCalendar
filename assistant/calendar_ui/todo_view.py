"""TodoView — Apple Reminders-inspired task panel for MaCalendar."""

from __future__ import annotations

import datetime
import json
import os
from typing import Optional

from PyQt6.QtCore import Qt, QDate, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
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
    QStackedWidget,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtGui import QDesktopServices

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

_PRIORITY_LABELS = ["none", "low", "medium", "high"]

IMG_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff", ".heic"}


# ---------------------------------------------------------------------------
# InsertLinkDialog — small modal for embedding a hyperlink in notes
# ---------------------------------------------------------------------------

class InsertLinkDialog(QDialog):
    """Two-field dialog: display text + URL → returns HTML anchor on accept."""

    def __init__(self, selected_text: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Insert Link")
        self.setMinimumWidth(340)
        self.setModal(True)

        form = QFormLayout(self)
        form.setContentsMargins(16, 16, 16, 12)
        form.setSpacing(10)

        self._text_edit = QLineEdit(selected_text)
        self._text_edit.setPlaceholderText("Display text")
        form.addRow("Text:", self._text_edit)

        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText("https://…")
        form.addRow("URL:", self._url_edit)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

        self._url_edit.returnPressed.connect(self.accept)

    def result_link(self) -> tuple[str, str]:
        """Returns (display_text, url)."""
        return self._text_edit.text().strip(), self._url_edit.text().strip()


# ---------------------------------------------------------------------------
# SubtaskRow — compact row inside TodoDetailPanel
# ---------------------------------------------------------------------------

class SubtaskRow(QWidget):
    """Minimal task row: checkbox + inline-editable title + hover-delete."""

    toggled = pyqtSignal(int, bool)   # (subtask_id, new_completed)
    edited  = pyqtSignal(int, str)    # (subtask_id, new_title)
    deleted = pyqtSignal(int)         # (subtask_id,)

    def __init__(self, subtask: dict, dark: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._subtask = subtask
        self._dark = dark
        self._editing = False
        self._build()
        self.setMouseTracking(True)

    def _build(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 4, 2)
        layout.setSpacing(6)

        self._check = QCheckBox()
        self._check.setChecked(bool(self._subtask["completed"]))
        self._check.setFixedSize(18, 18)
        self._check.toggled.connect(self._on_toggled)
        layout.addWidget(self._check)

        self._label = QLabel(self._subtask["title"])
        self._label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._label.setCursor(Qt.CursorShape.IBeamCursor)
        self._label.mousePressEvent = self._start_edit  # type: ignore[assignment]
        layout.addWidget(self._label)

        self._editor = QLineEdit(self._subtask["title"])
        self._editor.setObjectName("todo_editor")
        self._editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._editor.hide()
        self._editor.editingFinished.connect(self._commit_edit)
        layout.addWidget(self._editor)

        self._del_btn = QPushButton("×")
        self._del_btn.setFixedSize(18, 18)
        self._del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._del_btn.hide()
        self._del_btn.clicked.connect(lambda: self.deleted.emit(self._subtask["id"]))
        layout.addWidget(self._del_btn)

        self._apply_theme(self._dark)

    def _apply_theme(self, dark: bool) -> None:
        self._dark = dark
        text_color = D_GRAY_DARK if dark else GRAY_DARK
        check_border = D_GRAY_MID if dark else GRAY_MID
        del_color = "#ff6666" if dark else "#cc0000"

        self._check.setStyleSheet(f"""
            QCheckBox::indicator {{
                width: 13px; height: 13px;
                border-radius: 7px;
                border: 2px solid {check_border};
                background: transparent;
            }}
            QCheckBox::indicator:checked {{
                background-color: {BLUE};
                border-color: {BLUE};
            }}
        """)
        if self._subtask["completed"]:
            self._label.setStyleSheet("color: #a0a0a0; text-decoration: line-through; font-size: 12px;")
        else:
            self._label.setStyleSheet(f"color: {text_color}; font-size: 12px;")
        self._del_btn.setStyleSheet(
            f"QPushButton {{ color: {del_color}; background: transparent; border: none; "
            f"font-size: 13px; font-weight: bold; }}"
            f"QPushButton:hover {{ color: #ff0000; }}"
        )

    def enterEvent(self, event) -> None:
        self._del_btn.show()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._del_btn.hide()
        super().leaveEvent(event)

    def _on_toggled(self, checked: bool) -> None:
        self._subtask["completed"] = int(checked)
        self._apply_theme(self._dark)
        self.toggled.emit(self._subtask["id"], checked)

    def _start_edit(self, _event) -> None:
        if self._editing:
            return
        self._editing = True
        self._label.hide()
        self._editor.setText(self._subtask["title"])
        self._editor.show()
        self._editor.setFocus()
        self._editor.selectAll()

    def _commit_edit(self) -> None:
        if not self._editing:
            return
        self._editing = False
        new_title = self._editor.text().strip()
        if new_title and new_title != self._subtask["title"]:
            self._subtask["title"] = new_title
            self._label.setText(new_title)
            self.edited.emit(self._subtask["id"], new_title)
        self._editor.hide()
        self._label.show()

    def apply_theme(self, dark: bool) -> None:
        self._apply_theme(dark)


# ---------------------------------------------------------------------------
# TodoDetailPanel — rich inline detail below a task title row
# ---------------------------------------------------------------------------

class TodoDetailPanel(QWidget):
    """
    Expandable panel shown below the task header row.
    Contains: rich notes (with link embedding), subtasks, attachments,
    due date picker, and priority selector.
    """

    changed = pyqtSignal()  # emitted after any persistent field change

    def __init__(self, db, todo: dict, dark: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._db = db
        self._todo = todo
        self._dark = dark
        self._subtask_rows: list[SubtaskRow] = []
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._save_notes)
        self._build()
        self.load(todo)

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(46, 4, 12, 10)
        outer.setSpacing(8)

        # ── Notes ──────────────────────────────────────────────────────
        notes_wrap = QVBoxLayout()
        notes_wrap.setSpacing(2)

        # Toolbar row (only visible in edit mode)
        self._notes_toolbar = QHBoxLayout()
        self._notes_toolbar.setSpacing(4)

        def _make_toolbar_btn(label: str, tooltip: str) -> QPushButton:
            btn = QPushButton(label)
            btn.setToolTip(tooltip)
            btn.setFixedSize(24, 22)
            btn.setStyleSheet(
                "QPushButton { background: transparent; border: 1px solid #aaa; "
                "border-radius: 3px; font-size: 11px; font-weight: bold; }"
                "QPushButton:hover { background: #e0e0e0; }"
                "QPushButton:pressed { background: #c8c8c8; }"
            )
            return btn

        self._btn_bold   = _make_toolbar_btn("B", "Bold (Ctrl+B)")
        self._btn_italic = _make_toolbar_btn("I", "Italic (Ctrl+I)")
        self._btn_link   = _make_toolbar_btn("🔗", "Insert link")
        self._notes_toolbar.addWidget(self._btn_bold)
        self._notes_toolbar.addWidget(self._btn_italic)
        self._notes_toolbar.addWidget(self._btn_link)
        self._notes_toolbar.addStretch()

        self._toolbar_widget = QWidget()
        self._toolbar_widget.setLayout(self._notes_toolbar)
        self._toolbar_widget.hide()
        notes_wrap.addWidget(self._toolbar_widget)

        # Stacked: browser (read) / editor (write)
        self._notes_stack = QStackedWidget()
        self._notes_stack.setMinimumHeight(48)

        self._notes_browser = QTextBrowser()
        self._notes_browser.setOpenLinks(False)
        self._notes_browser.setPlaceholderText("Add notes…")
        self._notes_browser.setFrameShape(QFrame.Shape.NoFrame)
        self._notes_browser.setFixedHeight(72)
        self._notes_browser.anchorClicked.connect(
            lambda url: QDesktopServices.openUrl(url)
        )
        self._notes_browser.mousePressEvent = self._switch_to_edit  # type: ignore[assignment]

        self._notes_editor = QTextEdit()
        self._notes_editor.setObjectName("detail_notes_editor")
        self._notes_editor.setFrameShape(QFrame.Shape.NoFrame)
        self._notes_editor.setFixedHeight(72)
        self._notes_editor.setAcceptRichText(True)
        self._notes_editor.textChanged.connect(self._on_notes_changed)

        self._notes_stack.addWidget(self._notes_browser)  # index 0 = read
        self._notes_stack.addWidget(self._notes_editor)   # index 1 = edit

        notes_wrap.addWidget(self._notes_stack)

        outer.addLayout(notes_wrap)

        # ── Subtasks ───────────────────────────────────────────────────
        sub_header = QLabel("Subtasks")
        sub_header.setStyleSheet("font-size: 11px; font-weight: 600; color: #888;")
        outer.addWidget(sub_header)

        self._subtasks_layout = QVBoxLayout()
        self._subtasks_layout.setSpacing(0)
        self._subtasks_layout.setContentsMargins(0, 0, 0, 0)
        outer.addLayout(self._subtasks_layout)

        # Add-subtask row
        add_sub_row = QHBoxLayout()
        self._add_sub_edit = QLineEdit()
        self._add_sub_edit.setObjectName("new_todo_editor")
        self._add_sub_edit.setPlaceholderText("+ Add subtask…")
        self._add_sub_edit.returnPressed.connect(self._on_add_subtask)
        add_sub_row.addWidget(self._add_sub_edit)
        outer.addLayout(add_sub_row)

        # ── Attachments ────────────────────────────────────────────────
        att_header_row = QHBoxLayout()
        att_lbl = QLabel("Attachments")
        att_lbl.setStyleSheet("font-size: 11px; font-weight: 600; color: #888;")
        att_header_row.addWidget(att_lbl)
        att_header_row.addStretch()
        add_att_btn = QPushButton("📎 Add")
        add_att_btn.setFixedHeight(22)
        add_att_btn.setStyleSheet(
            "QPushButton { background: transparent; border: 1px solid #aaa; "
            "border-radius: 4px; font-size: 11px; padding: 0 6px; }"
            "QPushButton:hover { background: #e8e8e8; }"
        )
        add_att_btn.clicked.connect(self._on_add_attachment)
        att_header_row.addWidget(add_att_btn)
        outer.addLayout(att_header_row)

        self._att_row = QHBoxLayout()
        self._att_row.setSpacing(6)
        self._att_row.addStretch()
        outer.addLayout(self._att_row)

        # ── Metadata row (due date + priority) ────────────────────────
        meta_row = QHBoxLayout()
        meta_row.setSpacing(12)

        due_lbl = QLabel("Due:")
        due_lbl.setStyleSheet("font-size: 11px; color: #888;")
        meta_row.addWidget(due_lbl)

        self._due_edit = QDateEdit()
        self._due_edit.setCalendarPopup(True)
        self._due_edit.setDisplayFormat("MMM d, yyyy")
        self._due_edit.setFixedWidth(130)
        self._due_edit.setSpecialValueText("No date")
        self._due_edit.setMinimumDate(QDate(2000, 1, 1))
        self._due_edit.setMaximumDate(QDate(2099, 12, 31))
        self._due_edit.dateChanged.connect(self._on_due_date_changed)
        meta_row.addWidget(self._due_edit)

        meta_row.addSpacing(8)

        pri_lbl = QLabel("Priority:")
        pri_lbl.setStyleSheet("font-size: 11px; color: #888;")
        meta_row.addWidget(pri_lbl)

        self._priority_combo = QComboBox()
        self._priority_combo.setFixedWidth(100)
        for p in _PRIORITY_LABELS:
            self._priority_combo.addItem(p.capitalize(), p)
        self._priority_combo.currentIndexChanged.connect(self._on_priority_changed)
        meta_row.addWidget(self._priority_combo)

        meta_row.addStretch()
        outer.addLayout(meta_row)

        # Wire toolbar buttons
        self._btn_bold.clicked.connect(
            lambda: self._notes_editor.setFontWeight(
                700 if self._notes_editor.fontWeight() < 700 else 400
            )
        )
        self._btn_italic.clicked.connect(
            lambda: self._notes_editor.setFontItalic(not self._notes_editor.fontItalic())
        )
        self._btn_link.clicked.connect(self._on_insert_link)

        # Focus-out on editor → switch back to read mode
        self._notes_editor.focusOutEvent = self._on_notes_editor_blur  # type: ignore[assignment]

        self._apply_theme(self._dark)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def load(self, todo: dict) -> None:
        """Populate all fields from todo dict + fetch subtasks from DB."""
        self._todo = todo

        # Notes
        notes_html = todo.get("notes", "") or ""
        self._notes_browser.setHtml(notes_html)
        self._notes_editor.blockSignals(True)
        self._notes_editor.setHtml(notes_html)
        self._notes_editor.blockSignals(False)
        self._notes_stack.setCurrentIndex(0)
        self._toolbar_widget.hide()

        # Subtasks
        self._reload_subtasks()

        # Attachments
        self._reload_attachments()

        # Due date
        due = todo.get("due_date", "") or ""
        self._due_edit.blockSignals(True)
        if due:
            try:
                d = datetime.date.fromisoformat(due)
                self._due_edit.setDate(QDate(d.year, d.month, d.day))
            except ValueError:
                self._due_edit.setDate(self._due_edit.minimumDate().addDays(-1))
        else:
            self._due_edit.setDate(self._due_edit.minimumDate().addDays(-1))
        self._due_edit.blockSignals(False)

        # Priority
        self._priority_combo.blockSignals(True)
        pri = todo.get("priority", "none") or "none"
        idx = _PRIORITY_LABELS.index(pri) if pri in _PRIORITY_LABELS else 0
        self._priority_combo.setCurrentIndex(idx)
        self._priority_combo.blockSignals(False)

    def apply_theme(self, dark: bool) -> None:
        self._apply_theme(dark)

    # ------------------------------------------------------------------
    # Internal — notes
    # ------------------------------------------------------------------

    def _switch_to_edit(self, event=None) -> None:
        self._notes_stack.setCurrentIndex(1)
        self._toolbar_widget.show()
        self._notes_editor.setFocus()
        if event:
            QTextEdit.mousePressEvent(self._notes_editor, event)

    def _on_notes_editor_blur(self, event) -> None:
        QTextEdit.focusOutEvent(self._notes_editor, event)
        # Small delay so link-toolbar clicks don't immediately close edit mode
        QTimer.singleShot(150, self._switch_to_read)

    def _switch_to_read(self) -> None:
        if self._notes_stack.currentIndex() == 1:
            self._save_notes()
            html = self._notes_editor.toHtml()
            self._notes_browser.setHtml(html)
            self._notes_stack.setCurrentIndex(0)
            self._toolbar_widget.hide()

    def _on_notes_changed(self) -> None:
        self._save_timer.start(500)

    def _save_notes(self) -> None:
        html = self._notes_editor.toHtml()
        self._db.update_todo(self._todo["id"], notes=html)
        self._todo["notes"] = html
        self.changed.emit()

    def _on_insert_link(self) -> None:
        cursor = self._notes_editor.textCursor()
        selected = cursor.selectedText()
        dlg = InsertLinkDialog(selected_text=selected, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            display, url = dlg.result_link()
            if url:
                if not display:
                    display = url
                html = f'<a href="{url}">{display}</a>'
                cursor.insertHtml(html)

    # ------------------------------------------------------------------
    # Internal — subtasks
    # ------------------------------------------------------------------

    def _reload_subtasks(self) -> None:
        # Remove existing rows
        while self._subtasks_layout.count():
            item = self._subtasks_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._subtask_rows.clear()

        for sub in self._db.get_subtasks(self._todo["id"]):
            self._append_subtask_row(sub)

    def _append_subtask_row(self, subtask: dict) -> None:
        row = SubtaskRow(subtask, dark=self._dark, parent=self)
        row.toggled.connect(self._on_subtask_toggled)
        row.edited.connect(self._on_subtask_edited)
        row.deleted.connect(self._on_subtask_deleted)
        self._subtasks_layout.addWidget(row)
        self._subtask_rows.append(row)

    def _on_add_subtask(self) -> None:
        title = self._add_sub_edit.text().strip()
        if not title:
            return
        self._add_sub_edit.clear()
        subtask_id = self._db.create_subtask(self._todo["id"], title)
        self._append_subtask_row({
            "id": subtask_id, "todo_id": self._todo["id"],
            "title": title, "completed": 0, "position": 0,
        })
        self.changed.emit()

    def _on_subtask_toggled(self, subtask_id: int, checked: bool) -> None:
        self._db.update_subtask(subtask_id, completed=int(checked))
        self.changed.emit()

    def _on_subtask_edited(self, subtask_id: int, new_title: str) -> None:
        self._db.update_subtask(subtask_id, title=new_title)
        self.changed.emit()

    def _on_subtask_deleted(self, subtask_id: int) -> None:
        self._db.delete_subtask(subtask_id)
        self._reload_subtasks()
        self.changed.emit()

    # ------------------------------------------------------------------
    # Internal — attachments
    # ------------------------------------------------------------------

    def _reload_attachments(self) -> None:
        while self._att_row.count() > 1:  # keep the trailing stretch
            item = self._att_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        raw = self._todo.get("attachments", "[]") or "[]"
        try:
            paths: list[str] = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            paths = []

        for path in paths:
            self._att_row.insertWidget(self._att_row.count() - 1, self._make_thumb(path))

    def _make_thumb(self, path: str) -> QWidget:
        btn = QPushButton()
        btn.setFixedSize(60, 60)
        btn.setToolTip(os.path.basename(path))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)

        ext = os.path.splitext(path)[1].lower()
        if ext in IMG_EXTS and os.path.exists(path):
            pix = QPixmap(path).scaled(
                60, 60,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            btn.setIcon(pix)  # type: ignore[arg-type]
            from PyQt6.QtCore import QSize
            btn.setIconSize(QSize(58, 58))
            btn.setText("")
        else:
            btn.setText(os.path.basename(path)[:8])
            btn.setStyleSheet(
                "QPushButton { font-size: 9px; border: 1px solid #aaa; border-radius: 4px; }"
            )

        btn.setStyleSheet(
            btn.styleSheet()
            + " QPushButton { border: 1px solid #ccc; border-radius: 4px; background: #f0f0f0; }"
        )
        btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(path)))
        btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        btn.customContextMenuRequested.connect(lambda pos, p=path: self._att_context_menu(p, btn))
        return btn

    def _att_context_menu(self, path: str, btn: QPushButton) -> None:
        menu = QMenu(self)
        menu.addAction("Remove", lambda: self._on_remove_attachment(path))
        menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def _on_add_attachment(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Attach file", os.path.expanduser("~"),
            "Images & Files (*.png *.jpg *.jpeg *.gif *.bmp *.webp *.pdf *.txt *.md *.*)"
        )
        if not paths:
            return
        raw = self._todo.get("attachments", "[]") or "[]"
        try:
            existing: list[str] = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            existing = []
        for p in paths:
            abs_p = os.path.abspath(p)
            if abs_p not in existing:
                existing.append(abs_p)
        self._save_attachments(existing)

    def _on_remove_attachment(self, path: str) -> None:
        raw = self._todo.get("attachments", "[]") or "[]"
        try:
            existing: list[str] = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            existing = []
        existing = [p for p in existing if p != path]
        self._save_attachments(existing)

    def _save_attachments(self, paths: list[str]) -> None:
        new_raw = json.dumps(paths)
        self._db.update_todo(self._todo["id"], attachments=new_raw)
        self._todo["attachments"] = new_raw
        self._reload_attachments()
        self.changed.emit()

    # ------------------------------------------------------------------
    # Internal — metadata
    # ------------------------------------------------------------------

    def _on_due_date_changed(self, qdate: QDate) -> None:
        if qdate < self._due_edit.minimumDate():
            value = ""
        else:
            value = f"{qdate.year():04d}-{qdate.month():02d}-{qdate.day():02d}"
        self._db.update_todo(self._todo["id"], due_date=value)
        self._todo["due_date"] = value
        self.changed.emit()

    def _on_priority_changed(self, _index: int) -> None:
        priority = self._priority_combo.currentData()
        self._db.update_todo(self._todo["id"], priority=priority)
        self._todo["priority"] = priority
        self.changed.emit()

    # ------------------------------------------------------------------
    # Internal — theme
    # ------------------------------------------------------------------

    def _apply_theme(self, dark: bool) -> None:
        self._dark = dark
        bg    = D_WHITE if dark else WHITE
        bg2   = D_GRAY_BG if dark else GRAY_BG
        text  = D_GRAY_DARK if dark else GRAY_DARK
        bdr   = D_GRAY_BORDER if dark else GRAY_BORDER

        self.setStyleSheet(f"background: {bg};")

        browser_style = (
            f"QTextBrowser {{ background: {bg2}; color: {text}; "
            f"border: 1px solid {bdr}; border-radius: 4px; padding: 4px; font-size: 12px; }}"
        )
        self._notes_browser.setStyleSheet(browser_style)

        editor_style = (
            f"QTextEdit {{ background: {bg2}; color: {text}; "
            f"border: 1px solid {BLUE}; border-radius: 4px; padding: 4px; font-size: 12px; }}"
        )
        self._notes_editor.setStyleSheet(editor_style)

        combo_style = (
            f"QComboBox {{ background: {bg}; color: {text}; border: 1px solid {bdr}; "
            f"border-radius: 4px; padding: 2px 6px; font-size: 12px; }}"
        )
        self._priority_combo.setStyleSheet(combo_style)

        date_style = (
            f"QDateEdit {{ background: {bg}; color: {text}; border: 1px solid {bdr}; "
            f"border-radius: 4px; padding: 2px 4px; font-size: 12px; }}"
        )
        self._due_edit.setStyleSheet(date_style)

        for row in self._subtask_rows:
            row.apply_theme(dark)


# ---------------------------------------------------------------------------
# TodoItemWidget — one row per task
# ---------------------------------------------------------------------------

class TodoItemWidget(QWidget):
    """
    A single todo row: checkbox + title (inline editable) + priority dot +
    expand button + delete button, with an optional inline detail panel below.
    """

    toggled      = pyqtSignal(int, bool)  # (todo_id, new_completed_state)
    edited       = pyqtSignal(int, str)   # (todo_id, new_title)
    deleted      = pyqtSignal(int)        # (todo_id,)
    detail_saved = pyqtSignal()           # any field in detail panel auto-saved

    def __init__(self, todo: dict, db, dark: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._todo = todo
        self._db = db
        self._dark = dark
        self._editing = False
        self._expanded = False
        self._font_size = 13
        self._detail_panel: Optional[TodoDetailPanel] = None
        self._list_item: Optional[QListWidgetItem] = None
        self._list_widget: Optional[QListWidget] = None
        self._build()
        self.setMouseTracking(True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_list_item(self, item: QListWidgetItem, list_widget: QListWidget) -> None:
        """Called by TodoListWidget after setItemWidget so we can update size hints."""
        self._list_item = item
        self._list_widget = list_widget

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        # Outer VBox: title row + (optional) detail panel
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Title row
        title_row = QHBoxLayout()
        title_row.setContentsMargins(14, 6, 10, 6)
        title_row.setSpacing(10)

        # Drag grip handle
        self._grip = QLabel("⠿")
        self._grip.setFixedWidth(14)
        self._grip.setCursor(Qt.CursorShape.SizeAllCursor)
        self._grip.setToolTip("Drag to reorder")
        title_row.addWidget(self._grip)

        # Circular checkbox
        self._check = QCheckBox()
        self._check.setChecked(bool(self._todo["completed"]))
        self._check.setFixedSize(22, 22)
        self._check.toggled.connect(self._on_toggled)
        title_row.addWidget(self._check)

        # Title label (click to edit)
        self._label = QLabel(self._todo["title"])
        self._label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._label.setCursor(Qt.CursorShape.IBeamCursor)
        self._label.mousePressEvent = self._start_edit  # type: ignore[assignment]
        title_row.addWidget(self._label)

        self._editor = QLineEdit(self._todo["title"])
        self._editor.setObjectName("todo_editor")
        self._editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._editor.hide()
        self._editor.editingFinished.connect(self._commit_edit)
        self._editor.returnPressed.connect(self._commit_edit)
        title_row.addWidget(self._editor)

        # Priority dot
        self._priority_dot = QLabel("●")
        self._priority_dot.setFixedWidth(14)
        color = _PRIORITY_COLORS.get(self._todo.get("priority", "none"), "")
        if color:
            self._priority_dot.setStyleSheet(f"color: {color}; font-size: 10px;")
            self._priority_dot.show()
        else:
            self._priority_dot.hide()
        title_row.addWidget(self._priority_dot)

        # Expand label (▸/▾) — QLabel avoids global QPushButton padding issues
        self._expand_btn = QLabel("▸")
        self._expand_btn.setFixedWidth(16)
        self._expand_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._expand_btn.setToolTip("Show details")
        self._expand_btn.mousePressEvent = lambda _e: self._toggle_expand()  # type: ignore[assignment]
        title_row.addWidget(self._expand_btn)

        # Delete button (hidden until hover)
        self._del_btn = QPushButton("×")
        self._del_btn.setFixedSize(20, 20)
        self._del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._del_btn.setToolTip("Delete task")
        self._del_btn.hide()
        self._del_btn.clicked.connect(lambda: self.deleted.emit(self._todo["id"]))
        title_row.addWidget(self._del_btn)

        outer.addLayout(title_row)

        self._apply_completion_style()
        self._apply_theme(self._dark)

    # ------------------------------------------------------------------
    # Expand / collapse
    # ------------------------------------------------------------------

    def _toggle_expand(self) -> None:
        self._expanded = not self._expanded

        if self._expanded:
            if self._detail_panel is None:
                self._detail_panel = TodoDetailPanel(self._db, self._todo, self._dark, self)
                self._detail_panel.changed.connect(self.detail_saved)
                self.layout().addWidget(self._detail_panel)
            else:
                self._detail_panel.load(self._todo)
            self._detail_panel.show()
            self._expand_btn.setText("▾")
            self._expand_btn.setToolTip("Hide details")
        else:
            if self._detail_panel is not None:
                self._detail_panel.hide()
            self._expand_btn.setText("▸")
            self._expand_btn.setToolTip("Show details")

        # Defer so show()/hide() fully propagates before we query sizeHint()
        QTimer.singleShot(0, self._update_item_size)

    def _update_item_size(self) -> None:
        """Recalculate this item's size hint and update the list widget height."""
        if self._list_item is None or self._list_widget is None:
            return
        # Do NOT call adjustSize() here — it collapses item widgets to 0-height inside QListWidget
        self._list_item.setSizeHint(self.sizeHint())
        total_h = sum(
            self._list_widget.sizeHintForRow(i) + self._list_widget.spacing()
            for i in range(self._list_widget.count())
        ) + 4
        self._list_widget.setFixedHeight(max(total_h, 10))
        self._list_widget.updateGeometry()

    # ------------------------------------------------------------------
    # Styles
    # ------------------------------------------------------------------

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
        expand_color = D_GRAY_TEXT if dark else GRAY_TEXT

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

        self._expand_btn.setStyleSheet(
            f"color: {expand_color}; font-size: 12px;"
        )

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

        if self._detail_panel is not None:
            self._detail_panel.apply_theme(dark)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

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
            widget = TodoItemWidget(todo, self._db, dark=self._dark)
            widget._font_size = self._font_size
            widget.toggled.connect(self._on_toggled)
            widget.edited.connect(self._on_edited)
            widget.deleted.connect(self._on_deleted)
            widget.detail_saved.connect(lambda: QTimer.singleShot(0, self.todo_changed.emit))
            item.setSizeHint(widget.sizeHint())
            self._list_widget.setItemWidget(item, widget)
            widget.set_list_item(item, self._list_widget)
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
            self._new_task_editor.blockSignals(False)
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
        self._db.delete_subtasks_for_todo(todo_id)
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
