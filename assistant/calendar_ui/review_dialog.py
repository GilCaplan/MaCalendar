"""“Was this right?” — review recent voice commands (Mac).

The desktop twin of the iPhone's Review-commands screen. Every command the
assistant runs is kept in the shared memory DB (~/.assistant_tools) with no
verdict until someone gives one; a 👍 / 👎 / fix here feeds the few-shot
examples the parser learns from. Since the Mac *is* the brain, this talks to
`assistant.intent.memory` directly rather than through the API the phone uses.
"""

from __future__ import annotations

import datetime as _dt

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from assistant.calendar_ui import icons
from assistant.calendar_ui import styles as _styles


def _pretty_date(iso: str) -> str:
    """2026-08-27 → Thu 27 Aug."""
    try:
        return _dt.date.fromisoformat(iso).strftime("%a %-d %b")
    except Exception:
        return iso


def _summarise(example: dict) -> str:
    """One line describing what the command actually did."""
    parts: list[str] = []
    resolved = example.get("resolved") or []
    for action in example.get("actions") or []:
        name = action.get("action", "")
        params = action.get("parameters", {}) or {}
        if name in ("create_event", "update_event"):
            real = next((r for r in resolved if r.get("type") == "event"), None)
            title = (real or {}).get("title") or params.get("title") or "event"
            date = (real or {}).get("date") or params.get("date") or ""
            start = (real or {}).get("start_time") or params.get("start_time") or ""
            when = " ".join(x for x in (_pretty_date(date) if date else "", start) if x)
            label = "Updated event" if name == "update_event" else "Event"
            parts.append(f"{label}: {title}" + (f" · {when}" if when else ""))
        elif name == "create_todo":
            titles = params.get("titles") or ([params["title"]] if params.get("title") else [])
            parts.append(("Tasks: " if len(titles) > 1 else "Task: ") + ", ".join(titles))
        elif name == "delete_event":
            parts.append("Deleted event " + (params.get("match_title") or ""))
        elif name == "query_schedule":
            parts.append("Read schedule")
        else:
            parts.append(name.replace("_", " "))
    return " · ".join(parts)


def unreviewed(limit: int = 30) -> list[dict]:
    """Successful commands nobody has judged yet, with what they created.

    Mirrors GET /memory/unreviewed so the phone and the Mac show the same
    backlog in the same order. Module-level so the Settings button can show
    the count without opening the dialog.
    """
    from assistant.db import get_db
    from assistant.intent.memory import get_memory
    memory, db = get_memory(), get_db()
    rows = [r for r in memory.recent(200)
            if r["feedback"] == "none" and r["success"] and r["actions"]][:limit]
    for row in rows:
        resolved = []
        for rec in memory.records_for(row["id"]):
            try:
                if rec["record_type"] == "event":
                    ev = db.get_event(int(rec["record_id"]))
                    if ev:
                        resolved.append({"type": "event", "id": ev["id"], "action": rec["action"],
                                         "title": ev["title"], "date": ev["date"],
                                         "start_time": ev["start_time"], "end_time": ev.get("end_time", "")})
                else:
                    td = db.get_todo(int(rec["record_id"]))
                    if td:
                        resolved.append({"type": "todo", "id": td["id"], "action": rec["action"],
                                         "title": td["title"], "date": td.get("due_date", ""),
                                         "start_time": "", "end_time": ""})
            except Exception:
                pass
        row["resolved"] = resolved
    return rows


class _ReviewRow(QFrame):
    """One command awaiting a verdict."""

    def __init__(self, example: dict, on_verdict, on_fix, dark: bool, parent=None) -> None:
        super().__init__(parent)
        self._example = example
        text2 = _styles.D_GRAY_TEXT if dark else _styles.GRAY_TEXT
        border = _styles.D_GRAY_BORDER if dark else _styles.GRAY_BORDER
        surface = _styles.D_GRAY_LIGHT if dark else _styles.GRAY_LIGHT
        self.setStyleSheet(
            f"QFrame {{ background-color: {surface}; border: 1px solid {border};"
            f" border-radius: {_styles.RADIUS_MD}px; }} QLabel {{ border: none; }}"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(6)
        src = QLabel()
        src.setPixmap(icons.pixmap("iphone" if example.get("source") == "ios" else "mac",
                                   text2, 13))
        head.addWidget(src)
        when = QLabel(str(example.get("time", "")).replace("T", " ")[:16])
        when.setStyleSheet(f"color: {text2}; font-size: 11px;")
        head.addWidget(when)
        head.addStretch(1)
        path = QLabel(example.get("parse_path") or "-")
        path.setStyleSheet(f"color: {text2}; font-size: 11px;")
        head.addWidget(path)
        lay.addLayout(head)

        said = QLabel(f"“{example.get('transcript', '')}”")
        said.setWordWrap(True)
        lay.addWidget(said)

        summary = _summarise(example)
        if summary:
            lbl = QLabel(summary)
            lbl.setWordWrap(True)
            lbl.setStyleSheet(f"color: {text2};")
            lay.addWidget(lbl)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        right = QPushButton(icons.icon("thumbs_up", size=14), " Right")
        right.clicked.connect(lambda: on_verdict(example, "approved"))
        wrong = QPushButton(icons.icon("thumbs_down", size=14), " Wrong")
        wrong.clicked.connect(lambda: on_verdict(example, "rejected"))
        fix = QPushButton(icons.icon("corrected", size=14), " Fix…")
        fix.clicked.connect(lambda: on_fix(example))
        for b in (right, wrong, fix):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            buttons.addWidget(b)
        buttons.addStretch(1)
        lay.addLayout(buttons)


class CorrectionDialog(QDialog):
    """“What should it have done?” — patch the record and store the fix as the
    example the assistant learns from (the Mac twin of the iOS Fix… sheet)."""

    def __init__(self, example: dict, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Fix this")
        self.setMinimumWidth(430)
        self._example = example
        self.correction: list | None = None
        self.notes: str = ""
        self.patch: tuple[int, dict] | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(10)

        said = QLabel(f"You said: “{example.get('transcript', '')}”")
        said.setWordWrap(True)
        lay.addWidget(said)

        # Prefill from what actually landed in the calendar, else from the
        # parsed parameters.
        self._event_id: int | None = None
        title = date = start = end = ""
        real = next((r for r in (example.get("resolved") or []) if r.get("type") == "event"), None)
        if real:
            self._event_id = int(real["id"])
            title, date = real.get("title", ""), real.get("date", "")
            start, end = real.get("start_time", ""), real.get("end_time", "")
        else:
            action = next((a for a in (example.get("actions") or [])
                           if a.get("action") == "create_event"), None)
            if action:
                p = action.get("parameters", {}) or {}
                title, date = p.get("title", ""), p.get("date", "")
                start, end = p.get("start_time", ""), p.get("end_time", "")
        self._is_event = bool(real) or bool(title)

        self._title = QLineEdit(title)
        self._date = QLineEdit(date)
        self._start = QLineEdit(start)
        self._end = QLineEdit(end)
        if self._is_event:
            form = QFormLayout()
            self._date.setPlaceholderText("YYYY-MM-DD")
            self._start.setPlaceholderText("HH:MM")
            self._end.setPlaceholderText("HH:MM")
            form.addRow("Title", self._title)
            form.addRow("Date", self._date)
            times = QHBoxLayout()
            times.addWidget(self._start)
            times.addWidget(QLabel("–"))
            times.addWidget(self._end)
            form.addRow("Time", times)
            lay.addLayout(form)

        lay.addWidget(QLabel("What went wrong?"))
        self._notes = QPlainTextEdit()
        self._notes.setPlaceholderText(
            "e.g. it heard 'Aura' but I said 'Nurit'; should have been a task, not an event")
        self._notes.setFixedHeight(72)
        lay.addWidget(self._notes)

        hint = QLabel(
            "Saving fixes the event in your calendar and teaches the assistant the corrected version."
            if self._is_event else
            "Stored with the command so the assistant can learn from it.")
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        lay.addWidget(hint)

        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                               | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self._save)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    def _save(self) -> None:
        self.notes = self._notes.toPlainText().strip()
        if not self._is_event:
            if not self.notes:
                QMessageBox.information(self, "Fix this", "Say what went wrong so it can learn from it.")
                return
            self.accept()
            return
        title = self._title.text().strip()
        if not title:
            QMessageBox.information(self, "Fix this", "Give the event a title.")
            return
        params: dict = {"title": title}
        for key, field in (("date", self._date), ("start_time", self._start), ("end_time", self._end)):
            value = field.text().strip()
            if value:
                params[key] = value
        self.correction = [{"action": "create_event", "parameters": params}]
        if self._event_id is not None:
            self.patch = (self._event_id, params)
        self.accept()


class ReviewDialog(QDialog):
    """The backlog of commands with no verdict yet."""

    def __init__(self, parent=None, dark: bool = True) -> None:
        super().__init__(parent)
        self.setWindowTitle("Review commands")
        self.setMinimumSize(560, 560)
        self._dark = dark
        self._done = 0
        from assistant.intent.memory import get_memory
        self._memory = get_memory()

        root = QVBoxLayout(self)
        self._intro = QLabel()
        self._intro.setWordWrap(True)
        self._intro.setObjectName("muted")
        root.addWidget(self._intro)

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

        buttons = QHBoxLayout()
        self._skip_btn = QPushButton("Dismiss all")
        self._skip_btn.setToolTip("Clear the backlog without marking anything right or wrong")
        self._skip_btn.clicked.connect(self._skip_all)
        buttons.addWidget(self._skip_btn)
        buttons.addStretch(1)
        close_btn = QPushButton("Done")
        close_btn.setObjectName("primary")
        close_btn.clicked.connect(self.accept)
        buttons.addWidget(close_btn)
        root.addLayout(buttons)

        self.reload()

    # ---------------------------------------------------------------- data

    def reload(self) -> None:
        while self._list.count() > 1:
            item = self._list.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        items = unreviewed()
        self._skip_btn.setVisible(bool(items))
        if not items:
            self._intro.setText(
                f"All caught up — {self._done} reviewed." if self._done
                else "Nothing to review. Every voice command shows up here until you've said "
                     "whether it was right; a few seconds a day and the assistant learns your phrasing.")
            return
        self._intro.setText(
            f"{len(items)} to review · 👍 if it did the right thing, 👎 if not. "
            "Only what you tick is stored.")
        for ex in items:
            self._list.insertWidget(self._list.count() - 1,
                                    _ReviewRow(ex, self._verdict, self._fix, self._dark))

    # -------------------------------------------------------------- actions

    def _verdict(self, example: dict, value: str) -> None:
        self._memory.set_feedback(int(example["id"]), value)
        self._done += 1
        self.reload()

    def _fix(self, example: dict) -> None:
        dlg = CorrectionDialog(example, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        if dlg.patch is not None:
            from assistant.db import get_db
            event_id, fields = dlg.patch
            try:
                get_db().update_event(event_id, **fields)
            except Exception as exc:
                QMessageBox.warning(self, "Fix this", f"Couldn't update the event: {exc}")
        self._memory.set_feedback(int(example["id"]), "corrected",
                                  correction=dlg.correction, notes=dlg.notes)
        self._done += 1
        self.reload()

    def _skip_all(self) -> None:
        count = len(unreviewed(limit=1000))
        if QMessageBox.question(
                self, "Dismiss all",
                f"Dismiss all {count} without a verdict? They won't count as right or wrong."
        ) != QMessageBox.StandardButton.Yes:
            return
        self._memory.skip_unreviewed()
        self._done = 0
        self.reload()
