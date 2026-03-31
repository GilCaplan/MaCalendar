"""Create / edit calendar event dialog."""

from __future__ import annotations

import datetime
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtCore import QDate, QTime

from assistant.calendar_ui.styles import BLUE, EVENT_COLORS, GRAY_BORDER, GRAY_TEXT


class ColorDot(QWidget):
    """Small colored circle for color selection."""

    clicked_color = pyqtSignal(str)

    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self.color = color
        self.setFixedSize(20, 20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event):
        from PyQt6.QtGui import QPainter, QColor, QBrush
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QBrush(QColor(self.color)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(2, 2, 16, 16)

    def mousePressEvent(self, event):
        self.clicked_color.emit(self.color)


class EventDialog(QDialog):
    """
    Dialog for creating or editing a calendar event.
    On save, returns the event data as a dict via .event_data attribute.
    """

    def __init__(
        self,
        parent=None,
        event: Optional[dict] = None,
        default_date: Optional[datetime.date] = None,
    ):
        super().__init__(parent)
        self._event = event  # None = create mode
        self._selected_color = (event or {}).get("color", BLUE)
        self.event_data: Optional[dict] = None
        self.delete_requested: bool = False
        self.delete_series_requested: bool = False

        self.setWindowTitle("New Event" if event is None else "Edit Event")
        self.setMinimumWidth(480)
        self.setModal(True)

        self._build_ui(default_date or datetime.date.today())

    def _build_ui(self, default_date: datetime.date) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 16)
        layout.setSpacing(12)

        # Title
        self._title = QLineEdit()
        self._title.setObjectName("title_input")
        self._title.setPlaceholderText("Add title")
        if self._event:
            self._title.setText(self._event["title"])
        layout.addWidget(self._title)

        # Form fields
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(10)

        # Date
        self._date = QDateEdit()
        self._date.setCalendarPopup(True)
        self._date.setDisplayFormat("dddd, MMMM d, yyyy")
        d = self._event["date"] if self._event else default_date.isoformat()
        self._date.setDate(QDate.fromString(d, "yyyy-MM-dd"))
        form.addRow("Date", self._date)

        # Time row
        time_row = QHBoxLayout()
        self._start = QTimeEdit()
        self._start.setDisplayFormat("hh:mm AP")
        self._end = QTimeEdit()
        self._end.setDisplayFormat("hh:mm AP")
        if self._event:
            self._start.setTime(QTime.fromString(self._event["start_time"], "HH:mm"))
            self._end.setTime(QTime.fromString(self._event["end_time"], "HH:mm"))
        else:
            now = datetime.datetime.now().replace(minute=0, second=0)
            self._start.setTime(QTime(now.hour, 0))
            self._end.setTime(QTime(now.hour + 1, 0))
        time_row.addWidget(self._start)
        time_row.addWidget(QLabel("–"))
        time_row.addWidget(self._end)
        time_row.addStretch()
        form.addRow("Time", time_row)

        # Attendees
        self._attendees = QLineEdit()
        self._attendees.setPlaceholderText("Add attendees (names or emails, comma-separated)")
        if self._event:
            self._attendees.setText(self._event.get("attendees", ""))
        form.addRow("Attendees", self._attendees)

        # Location
        self._location = QLineEdit()
        self._location.setPlaceholderText("Add location or meeting link")
        if self._event:
            self._location.setText(self._event.get("location", ""))
        form.addRow("Location", self._location)

        # Description
        self._description = QTextEdit()
        self._description.setPlaceholderText("Add description")
        self._description.setFixedHeight(80)
        if self._event:
            self._description.setPlainText(self._event.get("description", ""))
        form.addRow("Notes", self._description)

        # Repeat
        self._repeat = QComboBox()
        self._repeat.addItems(["None", "Daily", "Weekly", "Monthly"])
        if self._event and self._event.get("recurrence"):
            idx = {"daily": 1, "weekly": 2, "monthly": 3}.get(self._event["recurrence"], 0)
            self._repeat.setCurrentIndex(idx)
        form.addRow("Repeat", self._repeat)

        # Until (Date)
        self._until = QDateEdit()
        self._until.setCalendarPopup(True)
        self._until.setDisplayFormat("dddd, MMMM d, yyyy")
        if self._event and self._event.get("recurrence_end"):
            self._until.setDate(QDate.fromString(self._event["recurrence_end"], "yyyy-MM-dd"))
        else:
            self._until.setDate(QDate.fromString(d, "yyyy-MM-dd").addYears(1))
        
        self._until.setVisible(self._repeat.currentIndex() > 0)
        self._repeat.currentIndexChanged.connect(
            lambda idx: self._until.setVisible(idx > 0)
        )
        form.addRow("Until", self._until)

        # Color
        color_row = QHBoxLayout()
        self._color_dots: list[ColorDot] = []
        for c in EVENT_COLORS:
            dot = ColorDot(c)
            dot.clicked_color.connect(self._on_color_selected)
            self._color_dots.append(dot)
            color_row.addWidget(dot)
        color_row.addStretch()
        self._update_color_dots()
        form.addRow("Color", color_row)

        layout.addLayout(form)

        # Button row
        btn_row = QHBoxLayout()

        # Delete button (edit mode only)
        if self._event:
            del_btn = QPushButton("🗑 Delete")
            del_btn.setObjectName("delete_btn")
            del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            del_btn.setStyleSheet(
                "QPushButton { background-color: #d83b01; color: white; "
                "border: none; border-radius: 4px; padding: 5px 14px; font-weight: 600; }"
                "QPushButton:hover { background-color: #b83000; }"
            )
            del_btn.clicked.connect(self._on_delete)
            btn_row.addWidget(del_btn)

        btn_row.addStretch()

        # Cancel + Save
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("primary")
        buttons.button(QDialogButtonBox.StandardButton.Save).setDefault(True)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        btn_row.addWidget(buttons)

        layout.addLayout(btn_row)

        self._title.setFocus()

    def _on_color_selected(self, color: str) -> None:
        self._selected_color = color
        self._update_color_dots()

    def _update_color_dots(self) -> None:
        for dot in self._color_dots:
            dot.setFixedSize(24 if dot.color == self._selected_color else 20, 24 if dot.color == self._selected_color else 20)

    def _on_delete(self) -> None:
        from PyQt6.QtWidgets import QMessageBox
        if self._event and self._event.get("series_id"):
            msg = QMessageBox(self)
            msg.setWindowTitle("Delete Event")
            msg.setText("This is a repeating event.")
            msg.setInformativeText("Do you want to delete only this instance, or the entire series?")
            btn_only_this = msg.addButton("Only this instance", QMessageBox.ButtonRole.ActionRole)
            btn_series = msg.addButton("Entire series", QMessageBox.ButtonRole.DestructiveRole)
            msg.addButton(QMessageBox.StandardButton.Cancel)
            msg.exec()
            if msg.clickedButton() == btn_only_this:
                self.delete_requested = True
                self.accept()
            elif msg.clickedButton() == btn_series:
                self.delete_series_requested = True
                self.accept()
        else:
            title = self._event["title"] if self._event else "this event"
            reply = QMessageBox.question(
                self,
                "Delete Event",
                f"Delete \"{title}\"?\nThis cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.delete_requested = True
                self.accept()

    def _on_save(self) -> None:
        title = self._title.text().strip()
        if not title:
            self._title.setPlaceholderText("Title is required")
            return

        date_str = self._date.date().toString("yyyy-MM-dd")
        start_str = self._start.time().toString("HH:mm")
        end_str = self._end.time().toString("HH:mm")

        recur_idx = self._repeat.currentIndex()
        recurrence = ["", "daily", "weekly", "monthly"][recur_idx]
        recur_until = self._until.date().toString("yyyy-MM-dd") if recur_idx > 0 else ""

        self.event_data = {
            "title": title,
            "date": date_str,
            "start_time": start_str,
            "end_time": end_str,
            "attendees": self._attendees.text().strip(),
            "location": self._location.text().strip(),
            "description": self._description.toPlainText().strip(),
            "color": self._selected_color,
            "recurrence": recurrence,
            "recurrence_end": recur_until,
        }
        if self._event:
            self.event_data["id"] = self._event["id"]
            if self._event.get("series_id"):
                self.event_data["series_id"] = self._event["series_id"]

        self.accept()
