"""
CourseworkView — course + assignment tracker for MACalendar.

Layout
------
CourseworkView (QWidget)
  ├── top bar: "Courses" label + "New Course" button
  └── QSplitter (horizontal)
      ├── course_list (QListWidget, 240px) — color dot | number | name | partner count
      └── _AssignmentPanel (fill)
              ├── header: course name + partners
              └── scrollable assignment rows + add-assignment bar
"""
from __future__ import annotations

import datetime
import json
from typing import Optional

from PyQt6.QtCore import Qt, QDate, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from assistant.calendar_ui.styles import (
    GRAY_BORDER,
    GRAY_TEXT,
    D_GRAY_BORDER,
    D_GRAY_TEXT,
)
from assistant.db import CalendarDB

# ---------------------------------------------------------------------------
# Color palette for courses
# ---------------------------------------------------------------------------

_COURSE_COLORS = [
    "#4BA8A0", "#6B42C8", "#B05090", "#5AACBA",
    "#8855D0", "#4A82C8", "#6A9FD0", "#5A8A60", "#C03030",
]

# ---------------------------------------------------------------------------
# Due-date helpers
# ---------------------------------------------------------------------------


def _due_label(due_date: str) -> str:
    if not due_date:
        return ""
    try:
        d = datetime.date.fromisoformat(due_date)
    except ValueError:
        return due_date
    days = (d - datetime.date.today()).days
    if days == 0:
        return "Due today"
    if days == 1:
        return "Due tomorrow"
    if days < 0:
        return f"Overdue ({-days}d)"
    return d.strftime("%b %-d")


def _due_color(due_date: str) -> Optional[str]:
    """Return warning hex color or None (use default text color)."""
    if not due_date:
        return None
    try:
        days = (datetime.date.fromisoformat(due_date) - datetime.date.today()).days
    except ValueError:
        return None
    if days < 0:
        return "#c0392b"
    if days <= 3:
        return "#d67c1c"
    return None


# ---------------------------------------------------------------------------
# Thin horizontal divider
# ---------------------------------------------------------------------------


class _HDivider(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.HLine)
        self.setFrameShadow(QFrame.Shadow.Plain)
        self.setFixedHeight(1)


# ---------------------------------------------------------------------------
# Assignment row widget
# ---------------------------------------------------------------------------


class _AssignmentRow(QWidget):
    toggled          = pyqtSignal(int)
    delete_requested = pyqtSignal(int)
    sync_requested   = pyqtSignal(int)
    edit_requested   = pyqtSignal(int)

    def __init__(self, row: dict, course_color: str, dark: bool = False, font_size: int = 13, parent=None):
        super().__init__(parent)
        self._row = row
        self._course_color = course_color
        self._dark = dark
        self._font_size = font_size
        self._build()

    def _build(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 5, 12, 5)
        layout.setSpacing(10)

        # Circle checkbox button
        self._check_btn = QPushButton()
        self._check_btn.setFixedSize(20, 20)
        self._check_btn.setCheckable(True)
        self._check_btn.setChecked(bool(self._row["completed"]))
        self._check_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._check_btn.clicked.connect(lambda: self.toggled.emit(self._row["id"]))
        self._check_btn.clicked.connect(self._refresh_check_style)
        layout.addWidget(self._check_btn)

        # Title
        self._title_lbl = QLabel(self._row["title"])
        self._title_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        if self._row["completed"]:
            self._title_lbl.setStyleSheet(f"text-decoration: line-through; color: #888; font-size: {self._font_size}px;")
        else:
            self._title_lbl.setStyleSheet(f"font-size: {self._font_size}px;")
        layout.addWidget(self._title_lbl)

        # Due date chip
        due = self._row.get("due_date", "")
        if due:
            self._due_lbl = QLabel(_due_label(due))
            col = _due_color(due)
            style = f"color: {col}; font-size: 11px; font-weight: 600;" if col else "color: #888; font-size: 11px;"
            self._due_lbl.setStyleSheet(style)
            layout.addWidget(self._due_lbl)

        # Calendar sync button
        self._cal_btn = QPushButton()
        synced = self._row.get("calendar_event_id") is not None
        self._cal_btn.setText("✓ synced" if synced else "📅")
        self._cal_btn.setToolTip(
            "Already synced to calendar" if synced else "Add due date to main calendar"
        )
        self._cal_btn.setEnabled(not synced)
        self._cal_btn.setObjectName("flat")
        self._cal_btn.setFixedHeight(24)
        self._cal_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cal_btn.setVisible(bool(due))
        self._cal_btn.clicked.connect(lambda: self.sync_requested.emit(self._row["id"]))
        layout.addWidget(self._cal_btn)

        self._refresh_check_style()

    def _refresh_check_style(self) -> None:
        if self._check_btn.isChecked():
            self._check_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {self._course_color};
                    border: 2px solid {self._course_color};
                    border-radius: 10px;
                    color: white;
                    font-size: 10px;
                    font-weight: bold;
                }}
                QPushButton:hover {{ background-color: {self._course_color}; }}
            """)
            self._check_btn.setText("✓")
        else:
            border = D_GRAY_BORDER if self._dark else GRAY_BORDER
            self._check_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    border: 2px solid {border};
                    border-radius: 10px;
                    color: transparent;
                }}
                QPushButton:hover {{ border-color: {self._course_color}; }}
            """)
            self._check_btn.setText("")

    def apply_theme(self, dark: bool) -> None:
        self._dark = dark
        self._refresh_check_style()

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        edit_act = menu.addAction("Edit Assignment…")
        menu.addSeparator()
        del_act = menu.addAction("Delete")
        action = menu.exec(event.globalPos())
        if action == del_act:
            self.delete_requested.emit(self._row["id"])
        elif action == edit_act:
            self.edit_requested.emit(self._row["id"])


# ---------------------------------------------------------------------------
# Course list item widget (left panel)
# ---------------------------------------------------------------------------


class _CourseItem(QWidget):
    def __init__(self, course: dict, font_size: int = 13, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(8)

        dot = QLabel("●")
        dot.setStyleSheet(f"color: {course['color']}; font-size: {font_size}px;")
        dot.setFixedWidth(16)
        layout.addWidget(dot)

        text = QLabel()
        num  = course.get("number", "")
        name = course.get("name", "Unnamed Course")
        num_size = max(font_size - 3, 9)
        if num:
            text.setText(f'<span style="font-size:{num_size}px; color:#888;">{num}</span><br><b style="font-size:{font_size}px;">{name}</b>')
        else:
            text.setText(f'<b style="font-size:{font_size}px;">{name}</b>')
        text.setWordWrap(True)
        layout.addWidget(text, stretch=1)

        partners = course.get("partners", [])
        if isinstance(partners, str):
            try: partners = json.loads(partners)
            except Exception: partners = []
        if partners:
            pc = QLabel(f"👥 {len(partners)}")
            pc.setStyleSheet("font-size: 11px; color: #888;")
            layout.addWidget(pc)


# ---------------------------------------------------------------------------
# Assignment panel (right side)
# ---------------------------------------------------------------------------


class _AssignmentPanel(QWidget):
    edit_course_requested = pyqtSignal()

    def __init__(self, db: CalendarDB, dark: bool = False, font_size: int = 13, parent=None):
        super().__init__(parent)
        self._db        = db
        self._dark      = dark
        self._font_size = font_size
        self._course: Optional[dict] = None
        self._rows: list[QWidget] = []
        self._build()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Header ──
        header = QWidget()
        hlayout = QVBoxLayout(header)
        hlayout.setContentsMargins(20, 14, 20, 10)
        hlayout.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setSpacing(10)

        self._title_lbl = QLabel("Select a course")
        f = QFont()
        f.setPointSize(16)
        f.setWeight(QFont.Weight.DemiBold)
        self._title_lbl.setFont(f)
        title_row.addWidget(self._title_lbl, stretch=1)

        self._edit_course_btn = QPushButton("✎  Edit Course")
        self._edit_course_btn.setObjectName("flat")
        self._edit_course_btn.setFixedHeight(26)
        self._edit_course_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_course_btn.setVisible(False)
        self._edit_course_btn.clicked.connect(self._on_edit_course_btn)
        title_row.addWidget(self._edit_course_btn)

        hlayout.addLayout(title_row)

        self._number_lbl = QLabel()
        self._number_lbl.setStyleSheet(f"color: {GRAY_TEXT}; font-size: 11px;")
        hlayout.addWidget(self._number_lbl)

        self._partners_lbl = QLabel()
        self._partners_lbl.setStyleSheet(f"color: {GRAY_TEXT}; font-size: 12px;")
        self._partners_lbl.setWordWrap(True)
        hlayout.addWidget(self._partners_lbl)

        hlayout.addWidget(_HDivider())
        outer.addWidget(header)

        # ── Scroll area ──
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._body = QWidget()
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(12, 8, 12, 8)
        self._body_layout.setSpacing(2)
        self._body_layout.addStretch()
        self._scroll.setWidget(self._body)
        outer.addWidget(self._scroll, stretch=1)

        # ── Add assignment bar ──
        self._add_bar = QWidget()
        alayout = QHBoxLayout(self._add_bar)
        alayout.setContentsMargins(16, 6, 16, 12)
        alayout.setSpacing(8)
        self._add_edit = QLineEdit()
        self._add_edit.setPlaceholderText("Add assignment…")
        self._add_edit.setObjectName("new_todo_editor")
        self._add_edit.returnPressed.connect(self._on_add)
        alayout.addWidget(self._add_edit)
        add_btn = QPushButton("+")
        add_btn.setObjectName("primary")
        add_btn.setFixedSize(28, 28)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._on_add)
        alayout.addWidget(add_btn)
        self._add_bar.setVisible(False)
        outer.addWidget(self._add_bar)

    # ── Public ──

    def load_course(self, course: Optional[dict]) -> None:
        self._course = course
        if course is None:
            self._title_lbl.setText("Select a course")
            self._number_lbl.setText("")
            self._partners_lbl.setText("")
            self._edit_course_btn.setVisible(False)
            self._add_bar.setVisible(False)
            self._clear_rows()
            return

        self._title_lbl.setText(course["name"])
        self._edit_course_btn.setVisible(True)
        num = course.get("number", "")
        self._number_lbl.setText(num)
        self._number_lbl.setVisible(bool(num))

        partners = course.get("partners", [])
        if isinstance(partners, str):
            try: partners = json.loads(partners)
            except Exception: partners = []
        self._partners_lbl.setText("👥  " + "   ·   ".join(partners) if partners else "")
        self._partners_lbl.setVisible(bool(partners))

        self._add_bar.setVisible(True)
        self._reload_assignments()

    def _on_edit_course_btn(self) -> None:
        self.edit_course_requested.emit()

    def apply_theme(self, dark: bool) -> None:
        self._dark = dark
        color = D_GRAY_TEXT if dark else GRAY_TEXT
        self._number_lbl.setStyleSheet(f"color: {color}; font-size: 11px;")
        self._partners_lbl.setStyleSheet(f"color: {color}; font-size: 12px;")
        for row in self._rows:
            if isinstance(row, _AssignmentRow):
                row.apply_theme(dark)

    # ── Private ──

    def _reload_assignments(self) -> None:
        self._clear_rows()
        if self._course is None:
            return
        assignments = self._db.get_assignments(self._course["id"])
        assignments.sort(key=lambda a: (a["completed"], a["due_date"] or "9999-99-99"))

        if not assignments:
            ph = QLabel("No assignments yet — add one below.")
            ph.setStyleSheet(f"color: {GRAY_TEXT}; font-size: 13px; padding: 20px;")
            ph.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._rows.append(ph)
            self._body_layout.insertWidget(self._body_layout.count() - 1, ph)
            return

        for asgn in assignments:
            row = _AssignmentRow(asgn, self._course["color"], dark=self._dark, font_size=self._font_size)
            row.toggled.connect(self._on_toggle)
            row.delete_requested.connect(self._on_delete)
            row.sync_requested.connect(self._on_sync)
            row.edit_requested.connect(self._on_edit_assignment)
            self._rows.append(row)
            self._body_layout.insertWidget(self._body_layout.count() - 1, row)

    def _clear_rows(self) -> None:
        while self._body_layout.count() > 1:
            item = self._body_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._rows.clear()

    def _on_toggle(self, asgn_id: int) -> None:
        self._db.toggle_assignment(asgn_id)
        self._reload_assignments()

    def _on_delete(self, asgn_id: int) -> None:
        self._db.delete_assignment(asgn_id)
        self._reload_assignments()

    def _on_sync(self, asgn_id: int) -> None:
        if self._course is None:
            return
        assignments = self._db.get_assignments(self._course["id"])
        asgn = next((a for a in assignments if a["id"] == asgn_id), None)
        if asgn is None or not asgn.get("due_date"):
            return
        num  = self._course.get("number", "")
        desc = f"{num} — {self._course['name']}".strip(" —") if num else self._course["name"]
        event_id = self._db.create_event_from_dict({
            "title":       f"📚 {asgn['title']}",
            "date":        asgn["due_date"],
            "start_time":  "23:59",
            "end_time":    "23:59",
            "color":       self._course["color"],
            "description": desc,
        })
        self._db.set_assignment_calendar_event(asgn_id, event_id)
        self._reload_assignments()

    def _on_add(self) -> None:
        if self._course is None:
            return
        title = self._add_edit.text().strip()
        if not title:
            return
        self._db.create_assignment(self._course["id"], title)
        self._add_edit.clear()
        self._reload_assignments()

    def _on_edit_assignment(self, asgn_id: int) -> None:
        if self._course is None:
            return
        assignments = self._db.get_assignments(self._course["id"])
        asgn = next((a for a in assignments if a["id"] == asgn_id), None)
        if asgn is None:
            return
        dlg = _AssignmentDialog(existing=asgn, parent=self)
        if dlg.exec():
            data = dlg.result_data()
            self._db.update_assignment(
                asgn_id,
                title=data["title"],
                due_date=data["due_date"],
            )
            self._reload_assignments()


# ---------------------------------------------------------------------------
# Main view
# ---------------------------------------------------------------------------


class CourseworkView(QWidget):
    def __init__(self, db: CalendarDB, dark: bool = False, font_size: int = 13, parent=None):
        super().__init__(parent)
        self._db        = db
        self._dark      = dark
        self._font_size = font_size
        self._courses: list[dict] = []
        self._selected_id: Optional[int] = None
        self._build()
        self.refresh()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Top bar ──
        bar = QWidget()
        bar.setFixedHeight(44)
        blayout = QHBoxLayout(bar)
        blayout.setContentsMargins(14, 0, 14, 0)
        lbl = QLabel("Courses")
        f = QFont()
        f.setPointSize(13)
        f.setWeight(QFont.Weight.DemiBold)
        lbl.setFont(f)
        blayout.addWidget(lbl)
        blayout.addStretch()
        add_btn = QPushButton("＋  New Course")
        add_btn.setObjectName("primary")
        add_btn.setFixedHeight(28)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._on_add_course)
        blayout.addWidget(add_btn)
        outer.addWidget(bar)

        outer.addWidget(_HDivider())

        # ── Horizontal splitter ──
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)

        self._course_list = QListWidget()
        self._course_list.setMinimumWidth(160)
        self._course_list.setSpacing(2)
        self._course_list.currentRowChanged.connect(self._on_course_selected)
        self._course_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._course_list.customContextMenuRequested.connect(self._on_course_context_menu)
        splitter.addWidget(self._course_list)

        self._panel = _AssignmentPanel(self._db, dark=self._dark, font_size=self._font_size)
        self._panel.edit_course_requested.connect(self._on_edit_selected_course)
        splitter.addWidget(self._panel)
        splitter.setSizes([300, 700])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setCollapsible(0, False)
        outer.addWidget(splitter, stretch=1)

    def refresh(self) -> None:
        self._courses = self._db.get_courses()
        # Block signals while rebuilding list to avoid spurious selection events
        self._course_list.blockSignals(True)
        self._course_list.clear()
        restore_row = -1
        for i, course in enumerate(self._courses):
            item   = QListWidgetItem()
            widget = _CourseItem(course, font_size=self._font_size)
            item.setSizeHint(widget.sizeHint())
            self._course_list.addItem(item)
            self._course_list.setItemWidget(item, widget)
            if course["id"] == self._selected_id:
                restore_row = i
        self._course_list.blockSignals(False)

        if restore_row >= 0:
            self._course_list.setCurrentRow(restore_row)
            selected = self._courses[restore_row]
            self._panel.load_course(selected)
        elif self._courses:
            self._course_list.setCurrentRow(0)
            self._selected_id = self._courses[0]["id"]
            self._panel.load_course(self._courses[0])
        else:
            self._panel.load_course(None)

    def apply_theme(self, dark: bool) -> None:
        self._dark = dark
        self._panel.apply_theme(dark)
        self.refresh()

    def apply_ui_config(self, ui_config) -> None:
        self._font_size         = ui_config.font_coursework
        self._panel._font_size  = ui_config.font_coursework
        self.refresh()

    # ── Course selection / context menu ──

    def _on_course_selected(self, row: int) -> None:
        if 0 <= row < len(self._courses):
            course = self._courses[row]
            self._selected_id = course["id"]
            self._panel.load_course(course)
        else:
            self._selected_id = None
            self._panel.load_course(None)

    def _on_edit_selected_course(self) -> None:
        course = next((c for c in self._courses if c["id"] == self._selected_id), None)
        if course:
            self._edit_course(course)

    def _on_course_context_menu(self, pos) -> None:
        item = self._course_list.itemAt(pos)
        if item is None:
            return
        row = self._course_list.row(item)
        if not (0 <= row < len(self._courses)):
            return
        course = self._courses[row]
        menu     = QMenu(self)
        edit_act = menu.addAction("Edit Course…")
        menu.addSeparator()
        del_act  = menu.addAction("Delete Course")
        action = menu.exec(self._course_list.mapToGlobal(pos))
        if action == edit_act:
            self._edit_course(course)
        elif action == del_act:
            self._delete_course(course)

    # ── CRUD ──

    def _on_add_course(self) -> None:
        dlg = _CourseDialog(existing=None, parent=self)
        if dlg.exec():
            data = dlg.result_data()
            if data["name"]:
                self._db.create_course(
                    number=data["number"],
                    name=data["name"],
                    color=data["color"],
                    partners=data["partners"],
                )
                self.refresh()

    def _edit_course(self, course: dict) -> None:
        dlg = _CourseDialog(existing=course, parent=self)
        if dlg.exec():
            data = dlg.result_data()
            if data["name"]:
                self._db.update_course(
                    course["id"],
                    number=data["number"],
                    name=data["name"],
                    color=data["color"],
                    partners=data["partners"],
                )
                self.refresh()

    def _delete_course(self, course: dict) -> None:
        reply = QMessageBox.question(
            self,
            "Delete Course",
            f"Delete \"{course['name']}\" and all its assignments?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            if self._selected_id == course["id"]:
                self._selected_id = None
            self._db.delete_course(course["id"])
            self.refresh()


# ---------------------------------------------------------------------------
# Course add/edit dialog
# ---------------------------------------------------------------------------


class _CourseDialog(QDialog):
    def __init__(self, existing: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self._existing       = existing
        self._selected_color = existing["color"] if existing else _COURSE_COLORS[0]
        self._color_btns: list[tuple[str, QPushButton]] = []
        self.setWindowTitle("Edit Course" if existing else "New Course")
        self.setMinimumWidth(420)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(8)

        self._number_edit = QLineEdit(self._existing.get("number", "") if self._existing else "")
        self._number_edit.setPlaceholderText("e.g. 00960336")
        form.addRow("Course Number", self._number_edit)

        self._name_edit = QLineEdit(self._existing.get("name", "") if self._existing else "")
        self._name_edit.setPlaceholderText("Course name")
        form.addRow("Course Name", self._name_edit)
        layout.addLayout(form)

        # Color palette
        color_lbl = QLabel("Color")
        color_lbl.setStyleSheet("font-size: 12px; color: #888;")
        layout.addWidget(color_lbl)

        color_row = QHBoxLayout()
        color_row.setSpacing(8)
        for hex_color in _COURSE_COLORS:
            btn = QPushButton()
            btn.setFixedSize(30, 30)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._color_btns.append((hex_color, btn))
            btn.clicked.connect(lambda _, c=hex_color: self._select_color(c))
            color_row.addWidget(btn)
        color_row.addStretch()
        layout.addLayout(color_row)
        self._select_color(self._selected_color)  # apply initial selection

        # Partners
        partners_lbl = QLabel("Partners")
        partners_lbl.setStyleSheet("font-size: 12px; color: #888;")
        layout.addWidget(partners_lbl)

        if self._existing:
            raw = self._existing.get("partners", [])
            if isinstance(raw, str):
                try: raw = json.loads(raw)
                except Exception: raw = []
            self._partners: list[str] = list(raw)
        else:
            self._partners = []

        self._partner_list = QListWidget()
        self._partner_list.setMaximumHeight(90)
        for p in self._partners:
            self._partner_list.addItem(p)
        layout.addWidget(self._partner_list)

        partner_row = QHBoxLayout()
        self._partner_edit = QLineEdit()
        self._partner_edit.setPlaceholderText("Partner name…")
        self._partner_edit.returnPressed.connect(self._add_partner)
        partner_row.addWidget(self._partner_edit)
        add_p  = QPushButton("Add")
        add_p.setObjectName("flat")
        add_p.clicked.connect(self._add_partner)
        partner_row.addWidget(add_p)
        rem_p  = QPushButton("Remove")
        rem_p.setObjectName("flat")
        rem_p.clicked.connect(self._remove_partner)
        partner_row.addWidget(rem_p)
        layout.addLayout(partner_row)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _select_color(self, hex_color: str) -> None:
        self._selected_color = hex_color
        for c, btn in self._color_btns:
            outline = "2px solid #111" if c == hex_color else "2px solid transparent"
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {c};
                    border-radius: 15px;
                    border: {outline};
                }}
                QPushButton:hover {{ border: 2px solid #111; }}
            """)

    def _add_partner(self) -> None:
        name = self._partner_edit.text().strip()
        if name and name not in self._partners:
            self._partners.append(name)
            self._partner_list.addItem(name)
            self._partner_edit.clear()

    def _remove_partner(self) -> None:
        row = self._partner_list.currentRow()
        if row >= 0:
            self._partner_list.takeItem(row)
            del self._partners[row]

    def result_data(self) -> dict:
        return {
            "number":   self._number_edit.text().strip(),
            "name":     self._name_edit.text().strip(),
            "color":    self._selected_color,
            "partners": self._partners,
        }


# ---------------------------------------------------------------------------
# Assignment add/edit dialog
# ---------------------------------------------------------------------------


class _AssignmentDialog(QDialog):
    def __init__(self, existing: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self._existing = existing
        self.setWindowTitle("Edit Assignment" if existing else "New Assignment")
        self.setMinimumWidth(340)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        form   = QFormLayout()
        form.setSpacing(10)

        self._title_edit = QLineEdit(self._existing.get("title", "") if self._existing else "")
        self._title_edit.setPlaceholderText("Assignment title")
        form.addRow("Title", self._title_edit)

        due = self._existing.get("due_date", "") if self._existing else ""

        self._date_check = QCheckBox("Set due date")
        self._date_check.setChecked(bool(due))

        self._date_edit = QDateEdit()
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setEnabled(bool(due))
        if due:
            try:
                d = datetime.date.fromisoformat(due)
                self._date_edit.setDate(QDate(d.year, d.month, d.day))
            except ValueError:
                self._date_edit.setDate(QDate.currentDate())
        else:
            self._date_edit.setDate(QDate.currentDate())

        self._date_check.toggled.connect(self._date_edit.setEnabled)

        date_row = QHBoxLayout()
        date_row.addWidget(self._date_check)
        date_row.addWidget(self._date_edit)
        date_row.addStretch()

        layout.addLayout(form)
        layout.addLayout(date_row)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def result_data(self) -> dict:
        due = ""
        if self._date_check.isChecked():
            d   = self._date_edit.date()
            due = f"{d.year():04d}-{d.month():02d}-{d.day():02d}"
        return {
            "title":    self._title_edit.text().strip(),
            "due_date": due,
        }
