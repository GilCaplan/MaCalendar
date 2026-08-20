"""
Workout view — build/review workout templates, browse session history, view stats.

Explicitly build-and-review, NOT live tracking: the Mac app never gets a
one-tap-per-set workout screen (that's iOS-only, phone-in-hand). This tab is
for building/editing templates, reviewing AI-generated drafts, browsing and
correcting past sessions after the fact, and simple stats.

Layout
------
WorkoutView (QWidget)
  ├─ top bar: "Workout" heading + Templates/History/Stats segmented nav
  │            + draft-review banner (when drafts exist) + "New Template"
  └─ QStackedWidget
       ├─ Templates panel: "Needs Review" drafts section + saved template list
       ├─ History panel: WorkoutSessionRow list, newest first
       └─ Stats panel: period selector + summary tiles + per-exercise list

TemplateBuilderDialog (QDialog) — create/edit a template: name, default rest,
an ordered list of SingleBlockWidget / SupersetBlockWidget (add/remove/
reorder/merge-into-superset/split-apart), each with its own editable set
rows (SetRowWidget) supporting mixed reps/time sets and an exercise picker
(ExercisePicker) that searches-or-creates against workout_exercises.

SessionDetailDialog (QDialog) — edit a past session's start/end/notes and
each logged set's actual reps/seconds/weight/skipped flag, matching the
Timer feature's edit-after-the-fact precedent (see timer_view.py's
SessionEditDialog).
"""

from __future__ import annotations

import datetime
import uuid
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
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
    QSpinBox,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QDateTimeEdit,
)

from assistant.db import CalendarDB
import assistant.calendar_ui.styles as _styles
from assistant.calendar_ui.dialog_utils import install_enter_confirms


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _new_id() -> str:
    return str(uuid.uuid4())


def _duration_secs(start_iso: str, end_iso: Optional[str]) -> float:
    """Seconds between start and end. Returns 0 if end is missing — unlike
    Timer's live sessions, a workout session without an ended_at isn't
    "still running" here (no live tracking on Mac), just incomplete data."""
    try:
        s = datetime.datetime.fromisoformat(start_iso)
        if s.tzinfo is None:
            s = s.astimezone()
        if not end_iso:
            return 0.0
        e = datetime.datetime.fromisoformat(end_iso)
        if e.tzinfo is None:
            e = e.astimezone()
        return max(0.0, (e - s).total_seconds())
    except Exception:
        return 0.0


def _fmt_duration(total_seconds: float) -> str:
    """Human-friendly duration, e.g. '1h 12m', '34m 05s', '48s'."""
    total = int(total_seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    if h:
        return f"{h}h {m:02d}m"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def _fmt_datetime_short(iso: str) -> str:
    try:
        dt = datetime.datetime.fromisoformat(iso)
        today = datetime.date.today()
        if dt.date() == today:
            return dt.strftime("Today, %-I:%M %p")
        elif dt.date().year == today.year:
            return dt.strftime("%b %-d, %-I:%M %p")
        else:
            return dt.strftime("%b %-d %Y, %-I:%M %p")
    except Exception:
        return iso


def _default_set() -> dict:
    return {
        "id": _new_id(), "type": "reps", "target_reps": 8,
        "weight_kg": None, "target_seconds": None, "note": "",
    }


def _pad_equal(a: list, b: list) -> tuple[list, list]:
    """Pad the shorter of two set lists with default sets so both are the
    same length — required when merging two single blocks into a superset
    (sets_a/sets_b must be equal-length "rounds")."""
    n = max(len(a), len(b), 1)
    a = list(a) + [_default_set() for _ in range(n - len(a))]
    b = list(b) + [_default_set() for _ in range(n - len(b))]
    return a, b


def _set_log_display(log: Optional[dict]) -> str:
    if not log:
        return "—"
    if log.get("type") == "reps":
        reps = log.get("actual_reps") or 0
        w = log.get("actual_weight_kg")
        return f"{reps} reps @ {w:g}kg" if w else f"{reps} reps (BW)"
    secs = log.get("actual_seconds") or 0
    return f"{secs}s"


# ---------------------------------------------------------------------------
# Exercise picker — search-or-create against workout_exercises
# ---------------------------------------------------------------------------

class ExercisePicker(QComboBox):
    """Editable combo: autocompletes existing exercise names (case-insensitive
    substring match); typing a name that doesn't exist creates it lazily
    when resolved_exercise_id() is called (at save time)."""

    def __init__(self, db: CalendarDB, parent=None, current_name: str = ""):
        super().__init__(parent)
        self._db = db
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        for ex in self._db.get_workout_exercises():
            self.addItem(ex["name"])
        completer = QCompleter(self.model(), self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.setCompleter(completer)
        if current_name:
            self.setCurrentText(current_name)

    def resolved_exercise_id(self) -> Optional[str]:
        name = self.currentText().strip()
        if not name:
            return None
        existing = self._db.find_workout_exercise_by_name(name)
        if existing:
            return existing["id"]
        new_id = _new_id()
        self._db.create_workout_exercise(id=new_id, name=name)
        return new_id


# ---------------------------------------------------------------------------
# Set row (template editor) — one target set: reps+weight or seconds
# ---------------------------------------------------------------------------

class SetRowWidget(QWidget):
    """One editable planned-set row: type (reps/time), target values, note.

    show_remove=False hides the inline delete button — used inside a
    superset's paired round rows, where removal happens one round at a time
    via SupersetRoundRow's single shared delete button instead.
    """

    removed = pyqtSignal(object)  # emits self

    def __init__(self, set_data: Optional[dict] = None, show_remove: bool = True, parent=None):
        super().__init__(parent)
        self._data = dict(set_data) if set_data else _default_set()
        self._build(show_remove)

    def _build(self, show_remove: bool) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(6)

        self._type_combo = QComboBox()
        self._type_combo.addItem("Reps", "reps")
        self._type_combo.addItem("Time", "time")
        self._type_combo.setCurrentIndex(0 if self._data.get("type", "reps") == "reps" else 1)
        self._type_combo.setFixedWidth(68)
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        layout.addWidget(self._type_combo)

        self._reps_spin = QSpinBox()
        self._reps_spin.setRange(1, 999)
        self._reps_spin.setSuffix(" reps")
        self._reps_spin.setValue(self._data.get("target_reps") or 8)
        layout.addWidget(self._reps_spin)

        self._bodyweight_chk = QCheckBox("BW")
        self._bodyweight_chk.setToolTip("Bodyweight — no added weight")
        self._bodyweight_chk.setChecked(self._data.get("weight_kg") is None)
        self._bodyweight_chk.toggled.connect(self._on_bw_toggled)
        layout.addWidget(self._bodyweight_chk)

        self._weight_spin = QDoubleSpinBox()
        self._weight_spin.setRange(0, 999)
        self._weight_spin.setDecimals(1)
        self._weight_spin.setSuffix(" kg")
        self._weight_spin.setValue(self._data.get("weight_kg") or 0)
        layout.addWidget(self._weight_spin)

        self._secs_spin = QSpinBox()
        self._secs_spin.setRange(1, 3600)
        self._secs_spin.setSuffix(" sec")
        self._secs_spin.setValue(self._data.get("target_seconds") or 30)
        layout.addWidget(self._secs_spin)

        self._note_edit = QLineEdit(self._data.get("note", ""))
        self._note_edit.setPlaceholderText("note (optional)")
        self._note_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self._note_edit)

        if show_remove:
            del_btn = QPushButton("✕")
            del_btn.setObjectName("flat")
            del_btn.setFixedSize(22, 22)
            del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            del_btn.clicked.connect(lambda: self.removed.emit(self))
            layout.addWidget(del_btn)

        self._on_type_changed()
        self._on_bw_toggled(self._bodyweight_chk.isChecked())

    def _on_type_changed(self) -> None:
        is_reps = self._type_combo.currentData() == "reps"
        self._reps_spin.setVisible(is_reps)
        self._bodyweight_chk.setVisible(is_reps)
        self._weight_spin.setVisible(is_reps and not self._bodyweight_chk.isChecked())
        self._secs_spin.setVisible(not is_reps)

    def _on_bw_toggled(self, checked: bool) -> None:
        self._weight_spin.setEnabled(not checked)
        self._weight_spin.setVisible(not checked and self._type_combo.currentData() == "reps")

    def to_dict(self) -> dict:
        is_reps = self._type_combo.currentData() == "reps"
        return {
            "id": self._data.get("id") or _new_id(),
            "type": "reps" if is_reps else "time",
            "target_reps": self._reps_spin.value() if is_reps else None,
            "weight_kg": (None if self._bodyweight_chk.isChecked() else self._weight_spin.value()) if is_reps else None,
            "target_seconds": None if is_reps else self._secs_spin.value(),
            "note": self._note_edit.text().strip(),
        }


class SupersetRoundRow(QWidget):
    """One paired round inside a superset: exercise A's set | exercise B's
    set, removed together via a single shared delete button."""

    removed = pyqtSignal(object)

    def __init__(self, set_a: Optional[dict] = None, set_b: Optional[dict] = None, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(6)

        self._round_lbl = QLabel()
        self._round_lbl.setObjectName("secondary")
        self._round_lbl.setFixedWidth(18)
        layout.addWidget(self._round_lbl)

        self.row_a = SetRowWidget(set_a, show_remove=False)
        layout.addWidget(self.row_a, 1)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        layout.addWidget(sep)

        self.row_b = SetRowWidget(set_b, show_remove=False)
        layout.addWidget(self.row_b, 1)

        del_btn = QPushButton("✕")
        del_btn.setObjectName("flat")
        del_btn.setFixedSize(22, 22)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.clicked.connect(lambda: self.removed.emit(self))
        layout.addWidget(del_btn)

    def set_round_number(self, n: int) -> None:
        self._round_lbl.setText(str(n))


# ---------------------------------------------------------------------------
# Block widgets (single exercise / superset) — used inside TemplateBuilderDialog
# ---------------------------------------------------------------------------

class BlockWidgetBase(QWidget):
    move_up_requested = pyqtSignal(object)
    move_down_requested = pyqtSignal(object)
    remove_requested = pyqtSignal(object)
    merge_next_requested = pyqtSignal(object)   # single block → merge with the following block
    split_requested = pyqtSignal(object)        # superset → split back into two singles

    def __init__(self, db: CalendarDB, parent=None):
        super().__init__(parent)
        self._db = db
        self.setObjectName("workout_block")

    def _build_header(self, title: str, kind: str) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setSpacing(4)

        kind_lbl = QLabel(title)
        f = QFont()
        f.setWeight(QFont.Weight.DemiBold)
        kind_lbl.setFont(f)
        header.addWidget(kind_lbl)
        header.addStretch()

        if kind == "single":
            merge_btn = QPushButton("⇄ Superset w/ next")
            merge_btn.setObjectName("flat")
            merge_btn.setFixedHeight(22)
            merge_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            merge_btn.setToolTip("Combine this exercise with the block below into a superset")
            merge_btn.clicked.connect(lambda: self.merge_next_requested.emit(self))
            header.addWidget(merge_btn)
        else:
            split_btn = QPushButton("Split apart")
            split_btn.setObjectName("flat")
            split_btn.setFixedHeight(22)
            split_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            split_btn.setToolTip("Split this superset back into two separate exercise blocks")
            split_btn.clicked.connect(lambda: self.split_requested.emit(self))
            header.addWidget(split_btn)

        up_btn = QPushButton("▲")
        up_btn.setObjectName("flat")
        up_btn.setFixedSize(22, 22)
        up_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        up_btn.clicked.connect(lambda: self.move_up_requested.emit(self))
        header.addWidget(up_btn)

        down_btn = QPushButton("▼")
        down_btn.setObjectName("flat")
        down_btn.setFixedSize(22, 22)
        down_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        down_btn.clicked.connect(lambda: self.move_down_requested.emit(self))
        header.addWidget(down_btn)

        del_btn = QPushButton("✕ Remove")
        del_btn.setObjectName("flat")
        del_btn.setFixedHeight(22)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.clicked.connect(lambda: self.remove_requested.emit(self))
        header.addWidget(del_btn)

        return header


class SingleBlockWidget(BlockWidgetBase):
    """A single-exercise block: exercise picker, optional rest override,
    and a list of target sets (mixed reps/time allowed)."""

    kind = "single"

    def __init__(self, db: CalendarDB, block: Optional[dict] = None, parent=None):
        super().__init__(db, parent)
        block = block or {}
        self.block_id = block.get("id") or _new_id()
        self._set_rows: list[SetRowWidget] = []
        self._build(block)

    def _build(self, block: dict) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(6)
        outer.addLayout(self._build_header("Exercise", "single"))

        row = QHBoxLayout()
        row.addWidget(QLabel("Exercise:"))
        exercise_name = ""
        if block.get("exercise_id"):
            ex = self._db.get_workout_exercise(block["exercise_id"])
            exercise_name = ex["name"] if ex else ""
        self._exercise_picker = ExercisePicker(self._db, current_name=exercise_name)
        row.addWidget(self._exercise_picker, 1)
        row.addWidget(QLabel("Rest override:"))
        self._rest_spin = QSpinBox()
        self._rest_spin.setRange(0, 900)
        self._rest_spin.setSuffix(" s")
        self._rest_spin.setSpecialValueText("Default")
        self._rest_spin.setValue(block.get("rest_between_sets_override") or 0)
        row.addWidget(self._rest_spin)
        outer.addLayout(row)

        self._sets_layout = QVBoxLayout()
        self._sets_layout.setSpacing(2)
        outer.addLayout(self._sets_layout)
        for s in block.get("sets") or []:
            self._add_set_row(s)
        if not self._set_rows:
            self._add_set_row(None)

        add_set_btn = QPushButton("+ Add set")
        add_set_btn.setObjectName("flat")
        add_set_btn.setFixedHeight(22)
        add_set_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_set_btn.clicked.connect(lambda: self._add_set_row(None))
        outer.addWidget(add_set_btn)

    def _add_set_row(self, data: Optional[dict]) -> None:
        row = SetRowWidget(data)
        row.removed.connect(self._remove_set_row)
        self._set_rows.append(row)
        self._sets_layout.addWidget(row)

    def _remove_set_row(self, row: SetRowWidget) -> None:
        if len(self._set_rows) <= 1:
            return  # keep at least one set row
        self._set_rows.remove(row)
        self._sets_layout.removeWidget(row)
        row.deleteLater()

    def to_dict(self) -> dict:
        return {
            "id": self.block_id,
            "kind": "single",
            "exercise_id": self._exercise_picker.resolved_exercise_id(),
            "sets": [r.to_dict() for r in self._set_rows],
            "rest_between_sets_override": self._rest_spin.value() or None,
            "exercise_id_a": None,
            "exercise_id_b": None,
            "sets_a": [],
            "sets_b": [],
            "rest_after_round": None,
        }


class SupersetBlockWidget(BlockWidgetBase):
    """A superset block: two exercises (A/B), each with its own set list of
    equal length ("rounds"), plus a shared rest-after-round."""

    kind = "superset"

    def __init__(self, db: CalendarDB, block: Optional[dict] = None, parent=None):
        super().__init__(db, parent)
        block = block or {}
        self.block_id = block.get("id") or _new_id()
        self._rounds: list[SupersetRoundRow] = []
        self._build(block)

    def _build(self, block: dict) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(6)
        outer.addLayout(self._build_header("Superset", "superset"))

        name_a = name_b = ""
        if block.get("exercise_id_a"):
            ex = self._db.get_workout_exercise(block["exercise_id_a"])
            name_a = ex["name"] if ex else ""
        if block.get("exercise_id_b"):
            ex = self._db.get_workout_exercise(block["exercise_id_b"])
            name_b = ex["name"] if ex else ""

        pick_row = QHBoxLayout()
        pick_row.addWidget(QLabel("A:"))
        self._picker_a = ExercisePicker(self._db, current_name=name_a)
        pick_row.addWidget(self._picker_a, 1)
        pick_row.addWidget(QLabel("B:"))
        self._picker_b = ExercisePicker(self._db, current_name=name_b)
        pick_row.addWidget(self._picker_b, 1)
        outer.addLayout(pick_row)

        rest_row = QHBoxLayout()
        rest_row.addWidget(QLabel("Rest after round:"))
        self._rest_spin = QSpinBox()
        self._rest_spin.setRange(0, 900)
        self._rest_spin.setSuffix(" s")
        self._rest_spin.setValue(block.get("rest_after_round") or 60)
        rest_row.addWidget(self._rest_spin)
        rest_row.addStretch()
        outer.addLayout(rest_row)

        self._rounds_layout = QVBoxLayout()
        self._rounds_layout.setSpacing(2)
        outer.addLayout(self._rounds_layout)

        sets_a = block.get("sets_a") or []
        sets_b = block.get("sets_b") or []
        n = max(len(sets_a), len(sets_b))
        for i in range(n):
            self._add_round(sets_a[i] if i < len(sets_a) else None,
                             sets_b[i] if i < len(sets_b) else None)
        if not self._rounds:
            self._add_round(None, None)

        add_btn = QPushButton("+ Add round")
        add_btn.setObjectName("flat")
        add_btn.setFixedHeight(22)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(lambda: self._add_round(None, None))
        outer.addWidget(add_btn)

    def _add_round(self, set_a: Optional[dict], set_b: Optional[dict]) -> None:
        row = SupersetRoundRow(set_a, set_b)
        row.removed.connect(self._remove_round)
        self._rounds.append(row)
        self._rounds_layout.addWidget(row)
        self._renumber()

    def _remove_round(self, row: SupersetRoundRow) -> None:
        if len(self._rounds) <= 1:
            return
        self._rounds.remove(row)
        self._rounds_layout.removeWidget(row)
        row.deleteLater()
        self._renumber()

    def _renumber(self) -> None:
        for i, r in enumerate(self._rounds):
            r.set_round_number(i + 1)

    def to_dict(self) -> dict:
        return {
            "id": self.block_id,
            "kind": "superset",
            "exercise_id": None,
            "sets": [],
            "rest_between_sets_override": None,
            "exercise_id_a": self._picker_a.resolved_exercise_id(),
            "exercise_id_b": self._picker_b.resolved_exercise_id(),
            "sets_a": [r.row_a.to_dict() for r in self._rounds],
            "sets_b": [r.row_b.to_dict() for r in self._rounds],
            "rest_after_round": self._rest_spin.value() or None,
        }

    def to_single_dicts(self) -> tuple[dict, dict]:
        """Split this superset's current state into two independent single
        block payloads (used by the "Split apart" action)."""
        d = self.to_dict()
        single_a = {
            "id": _new_id(), "kind": "single", "exercise_id": d["exercise_id_a"],
            "sets": d["sets_a"], "rest_between_sets_override": None,
            "exercise_id_a": None, "exercise_id_b": None, "sets_a": [], "sets_b": [],
            "rest_after_round": None,
        }
        single_b = {
            "id": _new_id(), "kind": "single", "exercise_id": d["exercise_id_b"],
            "sets": d["sets_b"], "rest_between_sets_override": None,
            "exercise_id_a": None, "exercise_id_b": None, "sets_a": [], "sets_b": [],
            "rest_after_round": None,
        }
        return single_a, single_b


# ---------------------------------------------------------------------------
# Template builder dialog
# ---------------------------------------------------------------------------

class TemplateBuilderDialog(QDialog):
    """Create or edit a workout template: name, default rest, ordered
    exercise/superset blocks with per-set editing, reordering, and
    merge-into-superset / split-apart affordances."""

    def __init__(self, db: CalendarDB, parent=None, *, template: Optional[dict] = None):
        super().__init__(parent)
        self._db = db
        self._template = template or {}
        self.setWindowTitle("Edit Workout Template" if template else "New Workout Template")
        self.setMinimumSize(640, 560)
        self._block_widgets: list[QWidget] = []
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(10)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._name_edit = QLineEdit(self._template.get("name", ""))
        self._name_edit.setPlaceholderText("e.g. Push Day, Full Body A…")
        form.addRow("Name:", self._name_edit)

        rest_row = QHBoxLayout()
        self._rest_sets_spin = QSpinBox()
        self._rest_sets_spin.setRange(0, 900)
        self._rest_sets_spin.setSuffix(" s")
        self._rest_sets_spin.setValue(self._template.get("default_rest_between_sets", 90))
        self._rest_ex_spin = QSpinBox()
        self._rest_ex_spin.setRange(0, 900)
        self._rest_ex_spin.setSuffix(" s")
        self._rest_ex_spin.setValue(self._template.get("default_rest_between_exercises", 120))
        rest_row.addWidget(QLabel("Between sets:"))
        rest_row.addWidget(self._rest_sets_spin)
        rest_row.addSpacing(12)
        rest_row.addWidget(QLabel("Between exercises:"))
        rest_row.addWidget(self._rest_ex_spin)
        rest_row.addStretch()
        form.addRow("Default rest:", rest_row)
        root.addLayout(form)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        blocks_widget = QWidget()
        self._blocks_layout = QVBoxLayout(blocks_widget)
        self._blocks_layout.setSpacing(8)
        for b in self._template.get("blocks") or []:
            self._append_block_widget(self._make_block_widget(b))
        if not self._block_widgets:
            self._append_block_widget(self._make_block_widget(None))
        self._blocks_layout.addStretch()
        scroll.setWidget(blocks_widget)
        root.addWidget(scroll, 1)

        add_btn = QPushButton("+ Add Exercise")
        add_btn.setObjectName("flat")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(lambda: self._append_block_widget(self._make_block_widget(None)))
        root.addWidget(add_btn)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(line)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setDefault(True)
        install_enter_confirms(self, ok_btn)
        root.addWidget(buttons)

    # ------------------------------------------------------------------
    def _make_block_widget(self, block: Optional[dict]) -> QWidget:
        if block and block.get("kind") == "superset":
            w: QWidget = SupersetBlockWidget(self._db, block)
            w.split_requested.connect(self._split_block)
        else:
            w = SingleBlockWidget(self._db, block)
            w.merge_next_requested.connect(self._merge_with_next)
        w.move_up_requested.connect(self._move_up)
        w.move_down_requested.connect(self._move_down)
        w.remove_requested.connect(self._remove_block)
        return w

    def _append_block_widget(self, w: QWidget) -> None:
        self._block_widgets.append(w)
        self._blocks_layout.insertWidget(self._blocks_layout.count() - 1, w)

    def _relayout_blocks(self) -> None:
        for w in self._block_widgets:
            self._blocks_layout.removeWidget(w)
        for w in self._block_widgets:
            self._blocks_layout.insertWidget(self._blocks_layout.count() - 1, w)

    def _move_up(self, w: QWidget) -> None:
        i = self._block_widgets.index(w)
        if i == 0:
            return
        self._block_widgets[i - 1], self._block_widgets[i] = self._block_widgets[i], self._block_widgets[i - 1]
        self._relayout_blocks()

    def _move_down(self, w: QWidget) -> None:
        i = self._block_widgets.index(w)
        if i == len(self._block_widgets) - 1:
            return
        self._block_widgets[i + 1], self._block_widgets[i] = self._block_widgets[i], self._block_widgets[i + 1]
        self._relayout_blocks()

    def _remove_block(self, w: QWidget) -> None:
        if len(self._block_widgets) <= 1:
            QMessageBox.information(self, "Can't Remove", "A template needs at least one exercise block.")
            return
        self._block_widgets.remove(w)
        self._blocks_layout.removeWidget(w)
        w.deleteLater()

    def _merge_with_next(self, w: QWidget) -> None:
        i = self._block_widgets.index(w)
        if i + 1 >= len(self._block_widgets):
            return
        other = self._block_widgets[i + 1]
        if not isinstance(other, SingleBlockWidget):
            QMessageBox.information(self, "Can't Merge", "Can only merge two single-exercise blocks.")
            return
        d1, d2 = w.to_dict(), other.to_dict()
        sets_a, sets_b = _pad_equal(d1["sets"], d2["sets"])
        merged = {
            "id": _new_id(), "kind": "superset", "exercise_id": None, "sets": [],
            "rest_between_sets_override": None,
            "exercise_id_a": d1["exercise_id"], "exercise_id_b": d2["exercise_id"],
            "sets_a": sets_a, "sets_b": sets_b, "rest_after_round": None,
        }
        new_w = self._make_block_widget(merged)
        self._blocks_layout.removeWidget(w)
        w.deleteLater()
        self._blocks_layout.removeWidget(other)
        other.deleteLater()
        self._block_widgets.pop(i + 1)
        self._block_widgets.pop(i)
        self._block_widgets.insert(i, new_w)
        self._blocks_layout.insertWidget(i, new_w)

    def _split_block(self, w: QWidget) -> None:
        i = self._block_widgets.index(w)
        single_a, single_b = w.to_single_dicts()
        wa = self._make_block_widget(single_a)
        wb = self._make_block_widget(single_b)
        self._blocks_layout.removeWidget(w)
        w.deleteLater()
        self._block_widgets.pop(i)
        self._block_widgets.insert(i, wb)
        self._block_widgets.insert(i, wa)
        self._blocks_layout.insertWidget(i, wa)
        self._blocks_layout.insertWidget(i + 1, wb)

    # ------------------------------------------------------------------
    def _on_accept(self) -> None:
        if not self._name_edit.text().strip():
            QMessageBox.warning(self, "Name Required", "Please enter a name for this template.")
            return
        self.accept()

    def result_template(self, *, template_id: Optional[str] = None, status: str = "saved") -> dict:
        return {
            "id": template_id or self._template.get("id") or _new_id(),
            "name": self._name_edit.text().strip() or "Untitled Workout",
            "default_rest_between_sets": self._rest_sets_spin.value(),
            "default_rest_between_exercises": self._rest_ex_spin.value(),
            "status": status,
            "blocks": [w.to_dict() for w in self._block_widgets],
        }


# ---------------------------------------------------------------------------
# Template card (Templates panel list item)
# ---------------------------------------------------------------------------

class TemplateCard(QWidget):
    edit_requested = pyqtSignal(str)      # template_id
    delete_requested = pyqtSignal(str)    # template_id (delete or discard)
    approve_requested = pyqtSignal(str)   # template_id (drafts only)

    def __init__(self, template: dict, parent=None):
        super().__init__(parent)
        self._template = template
        self._build()

    @property
    def _is_draft(self) -> bool:
        return self._template.get("status") == "draft"

    def _summary_text(self) -> str:
        blocks = self._template.get("blocks") or []
        n_ex = sum(2 if b["kind"] == "superset" else 1 for b in blocks)
        n_sets = sum(
            len(b.get("sets") or []) + len(b.get("sets_a") or []) + len(b.get("sets_b") or [])
            for b in blocks
        )
        rs = self._template.get("default_rest_between_sets", 90)
        re_ = self._template.get("default_rest_between_exercises", 120)
        return f"{len(blocks)} block(s) · {n_ex} exercise(s) · {n_sets} set(s) · rest {rs}s / {re_}s"

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = QWidget()
        card.setObjectName("draft_card" if self._is_draft else "workout_card")
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(6)
        if self._is_draft:
            badge = QLabel("DRAFT")
            badge.setObjectName("draft_badge")
            header.addWidget(badge)
        title = QLabel(self._template.get("name", "Untitled Workout"))
        f = QFont()
        f.setPointSize(13)
        f.setWeight(QFont.Weight.DemiBold)
        title.setFont(f)
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        sub = QLabel(self._summary_text())
        sub.setObjectName("secondary")
        layout.addWidget(sub)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        if self._is_draft:
            approve_btn = QPushButton("Approve")
            approve_btn.setObjectName("primary")
            approve_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            approve_btn.clicked.connect(lambda: self.approve_requested.emit(self._template["id"]))
            btn_row.addWidget(approve_btn)
        edit_btn = QPushButton("Edit")
        edit_btn.setObjectName("flat")
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.clicked.connect(lambda: self.edit_requested.emit(self._template["id"]))
        btn_row.addWidget(edit_btn)
        del_btn = QPushButton("Discard" if self._is_draft else "Delete")
        del_btn.setObjectName("flat" if self._is_draft else "destructive")
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self._template["id"]))
        btn_row.addWidget(del_btn)
        layout.addLayout(btn_row)


# ---------------------------------------------------------------------------
# Session row (History panel list item) + detail/edit dialog
# ---------------------------------------------------------------------------

class WorkoutSessionRow(QWidget):
    clicked = pyqtSignal(str)            # session_id
    delete_requested = pyqtSignal(str)   # session_id

    def __init__(self, session: dict, template_name: Optional[str], parent=None):
        super().__init__(parent)
        self._session = session
        self._build(template_name)

    def _build(self, template_name: Optional[str]) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = QWidget()
        card.setObjectName("workout_card")
        outer.addWidget(card)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        info = QVBoxLayout()
        info.setSpacing(2)
        title_lbl = QLabel(template_name or "Ad-hoc workout")
        f = QFont()
        f.setWeight(QFont.Weight.DemiBold)
        title_lbl.setFont(f)
        info.addWidget(title_lbl)

        when = _fmt_datetime_short(self._session["started_at"])
        dur = _duration_secs(self._session["started_at"], self._session.get("ended_at"))
        set_count = len(self._session.get("set_logs") or [])
        dur_str = _fmt_duration(dur) if self._session.get("ended_at") else "no end time"
        sub = QLabel(f"{when}  ·  {dur_str}  ·  {set_count} set(s)")
        sub.setObjectName("secondary")
        info.addWidget(sub)
        layout.addLayout(info, 1)

        open_btn = QPushButton("View / Edit")
        open_btn.setObjectName("flat")
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.clicked.connect(lambda: self.clicked.emit(self._session["id"]))
        layout.addWidget(open_btn)

        del_btn = QPushButton("✕")
        del_btn.setObjectName("flat")
        del_btn.setFixedSize(24, 24)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setToolTip("Delete this session")
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self._session["id"]))
        layout.addWidget(del_btn)


class SetLogRow(QWidget):
    """One editable logged set inside SessionDetailDialog: exercise name,
    skipped toggle, and actual reps/weight or seconds."""

    removed = pyqtSignal(object)

    def __init__(self, log: dict, exercise_name: str, parent=None):
        super().__init__(parent)
        self._log = dict(log)
        self._build(exercise_name)

    def _build(self, exercise_name: str) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(6)

        name_lbl = QLabel(exercise_name or "Exercise")
        name_lbl.setMinimumWidth(130)
        layout.addWidget(name_lbl)

        self._skipped_chk = QCheckBox("Skipped")
        self._skipped_chk.setChecked(bool(self._log.get("skipped")))
        self._skipped_chk.toggled.connect(self._on_skip_toggled)
        layout.addWidget(self._skipped_chk)

        is_reps = self._log.get("type", "reps") == "reps"
        self._reps_spin = QSpinBox()
        self._reps_spin.setRange(0, 999)
        self._reps_spin.setSuffix(" reps")
        self._reps_spin.setValue(self._log.get("actual_reps") or 0)
        self._reps_spin.setVisible(is_reps)
        layout.addWidget(self._reps_spin)

        self._weight_spin = QDoubleSpinBox()
        self._weight_spin.setRange(0, 999)
        self._weight_spin.setDecimals(1)
        self._weight_spin.setSuffix(" kg")
        self._weight_spin.setValue(self._log.get("actual_weight_kg") or 0)
        self._weight_spin.setVisible(is_reps)
        layout.addWidget(self._weight_spin)

        self._secs_spin = QSpinBox()
        self._secs_spin.setRange(0, 3600)
        self._secs_spin.setSuffix(" sec")
        self._secs_spin.setValue(self._log.get("actual_seconds") or 0)
        self._secs_spin.setVisible(not is_reps)
        layout.addWidget(self._secs_spin)

        layout.addStretch()

        del_btn = QPushButton("✕")
        del_btn.setObjectName("flat")
        del_btn.setFixedSize(22, 22)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.clicked.connect(lambda: self.removed.emit(self))
        layout.addWidget(del_btn)

        self._on_skip_toggled(self._skipped_chk.isChecked())

    def _on_skip_toggled(self, checked: bool) -> None:
        for w in (self._reps_spin, self._weight_spin, self._secs_spin):
            w.setEnabled(not checked)

    def to_dict(self) -> dict:
        is_reps = self._log.get("type", "reps") == "reps"
        return {
            "id": self._log.get("id") or _new_id(),
            "exercise_id": self._log["exercise_id"],
            "set_index": self._log.get("set_index", 0),
            "type": self._log.get("type", "reps"),
            "actual_reps": self._reps_spin.value() if is_reps else None,
            "actual_seconds": self._secs_spin.value() if not is_reps else None,
            "actual_weight_kg": self._weight_spin.value() if is_reps else None,
            "completed_at": self._log.get("completed_at"),
            "skipped": self._skipped_chk.isChecked(),
        }


class SessionDetailDialog(QDialog):
    """Edit a past session's start/end/notes and each logged set's actual
    values after the fact — matches TimerCard's SessionEditDialog precedent."""

    def __init__(self, db: CalendarDB, parent=None, *, session: dict):
        super().__init__(parent)
        self._db = db
        self._session = session
        self.setWindowTitle("Workout Session")
        self.setMinimumSize(540, 480)
        self._log_rows: list[SetLogRow] = []
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)

        start_dt = datetime.datetime.fromisoformat(self._session["started_at"])
        self._start_edit = QDateTimeEdit(start_dt)
        self._start_edit.setDisplayFormat("MMM d yyyy  h:mm AP")
        self._start_edit.setCalendarPopup(True)
        form.addRow("Start:", self._start_edit)

        end_raw = self._session.get("ended_at")
        end_dt = datetime.datetime.fromisoformat(end_raw) if end_raw else start_dt
        self._end_edit = QDateTimeEdit(end_dt)
        self._end_edit.setDisplayFormat("MMM d yyyy  h:mm AP")
        self._end_edit.setCalendarPopup(True)
        form.addRow("End:", self._end_edit)

        self._notes_edit = QTextEdit(self._session.get("notes", ""))
        self._notes_edit.setFixedHeight(56)
        form.addRow("Notes:", self._notes_edit)
        root.addLayout(form)

        root.addWidget(QLabel("Logged sets:"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        rows_widget = QWidget()
        self._rows_layout = QVBoxLayout(rows_widget)
        self._rows_layout.setSpacing(2)
        exercises = {e["id"]: e["name"] for e in self._db.get_workout_exercises()}
        logs = self._session.get("set_logs") or []
        if not logs:
            self._rows_layout.addWidget(QLabel("No sets logged for this session."))
        for log in logs:
            self._add_log_row(log, exercises.get(log["exercise_id"], "Exercise"))
        self._rows_layout.addStretch()
        scroll.setWidget(rows_widget)
        root.addWidget(scroll, 1)

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

    def _add_log_row(self, log: dict, name: str) -> None:
        row = SetLogRow(log, name)
        row.removed.connect(self._remove_log_row)
        self._log_rows.append(row)
        self._rows_layout.insertWidget(self._rows_layout.count() - 1 if self._rows_layout.count() else 0, row)

    def _remove_log_row(self, row: SetLogRow) -> None:
        self._log_rows.remove(row)
        self._rows_layout.removeWidget(row)
        row.deleteLater()

    @property
    def result_start(self) -> str:
        return self._start_edit.dateTime().toPyDateTime().isoformat()

    @property
    def result_end(self) -> str:
        return self._end_edit.dateTime().toPyDateTime().isoformat()

    @property
    def result_notes(self) -> str:
        return self._notes_edit.toPlainText().strip()

    @property
    def result_set_logs(self) -> list[dict]:
        return [r.to_dict() for r in self._log_rows]


# ---------------------------------------------------------------------------
# Main workout view
# ---------------------------------------------------------------------------

class WorkoutView(QWidget):
    """
    The full Workout tab: Templates (build/review) / History / Stats,
    switched via an internal segmented nav. No live tracking — see module
    docstring.
    """

    def __init__(self, db: CalendarDB, parent=None):
        super().__init__(parent)
        self._db = db
        self._dark = False
        self._section = "templates"     # "templates" | "history" | "stats"
        self._stats_period = "week"     # "week" | "month" | "all"
        self._build()
        self._apply_card_styles()
        self.reload()

    # ------------------------------------------------------------------
    # Visibility — refresh on show so drafts created elsewhere (voice
    # pipeline, iOS via the shared DB) show up promptly when the tab opens.
    # ------------------------------------------------------------------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.reload()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        top = QWidget()
        top.setObjectName("workout_topbar")
        top.setFixedHeight(48)
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(16, 8, 16, 8)
        top_layout.setSpacing(6)

        heading = QLabel("Workout")
        f = QFont()
        f.setPointSize(15)
        f.setWeight(QFont.Weight.DemiBold)
        heading.setFont(f)
        top_layout.addWidget(heading)

        top_layout.addSpacing(12)
        for label, sect in [("Templates", "templates"), ("History", "history"), ("Stats", "stats")]:
            btn = QPushButton(label)
            btn.setObjectName("seg_btn")
            btn.setFixedHeight(28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, s=sect: self._set_section(s))
            top_layout.addWidget(btn)
            setattr(self, f"_sect_btn_{sect}", btn)

        top_layout.addStretch()

        self._draft_banner_btn = QPushButton()
        self._draft_banner_btn.setObjectName("flat")
        self._draft_banner_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._draft_banner_btn.setVisible(False)
        self._draft_banner_btn.clicked.connect(lambda: self._set_section("templates"))
        top_layout.addWidget(self._draft_banner_btn)

        new_btn = QPushButton("+ New Template")
        new_btn.setObjectName("primary")
        new_btn.setFixedHeight(30)
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.clicked.connect(self._on_new_template)
        top_layout.addWidget(new_btn)

        root.addWidget(top)

        self._stack = QStackedWidget()
        self._templates_panel = self._build_templates_panel()
        self._history_panel = self._build_history_panel()
        self._stats_panel = self._build_stats_panel()
        self._stack.addWidget(self._templates_panel)
        self._stack.addWidget(self._history_panel)
        self._stack.addWidget(self._stats_panel)
        root.addWidget(self._stack, 1)

        self._set_section("templates")

    def _build_templates_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        self._drafts_heading = QLabel("Needs Review")
        f = QFont()
        f.setPointSize(12)
        f.setWeight(QFont.Weight.DemiBold)
        self._drafts_heading.setFont(f)
        self._drafts_heading.setObjectName("secondary")
        self._drafts_heading.setVisible(False)
        layout.addWidget(self._drafts_heading)

        self._drafts_layout = QVBoxLayout()
        self._drafts_layout.setSpacing(8)
        layout.addLayout(self._drafts_layout)

        self._templates_heading = QLabel("Templates")
        f2 = QFont()
        f2.setPointSize(12)
        f2.setWeight(QFont.Weight.DemiBold)
        self._templates_heading.setFont(f2)
        self._templates_heading.setObjectName("secondary")
        layout.addWidget(self._templates_heading)

        self._templates_layout = QVBoxLayout()
        self._templates_layout.setSpacing(8)
        layout.addLayout(self._templates_layout)

        layout.addStretch()
        scroll.setWidget(w)
        return scroll

    def _build_history_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        self._history_layout = QVBoxLayout()
        self._history_layout.setSpacing(8)
        layout.addLayout(self._history_layout)
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
        self._tile_workouts = self._make_stat_tile("Workouts")
        self._tile_sets = self._make_stat_tile("Total Sets")
        self._tile_volume = self._make_stat_tile("Total Volume")
        self._tile_time = self._make_stat_tile("Training Time")
        tiles_row.addWidget(self._tile_workouts, 0, 0)
        tiles_row.addWidget(self._tile_sets, 0, 1)
        tiles_row.addWidget(self._tile_volume, 0, 2)
        tiles_row.addWidget(self._tile_time, 0, 3)
        layout.addLayout(tiles_row)

        ex_heading = QLabel("Per-exercise")
        f = QFont()
        f.setPointSize(12)
        f.setWeight(QFont.Weight.DemiBold)
        ex_heading.setFont(f)
        ex_heading.setObjectName("secondary")
        layout.addWidget(ex_heading)

        self._exercise_stats_layout = QVBoxLayout()
        self._exercise_stats_layout.setSpacing(4)
        layout.addLayout(self._exercise_stats_layout)

        layout.addStretch()
        scroll.setWidget(w)
        return scroll

    def _make_stat_tile(self, title: str) -> QWidget:
        tile = QWidget()
        tile.setObjectName("workout_card")
        tl = QVBoxLayout(tile)
        tl.setContentsMargins(14, 10, 14, 10)
        tl.setSpacing(2)
        val_lbl = QLabel("—")
        vf = QFont()
        vf.setPointSize(20)
        vf.setWeight(QFont.Weight.Bold)
        val_lbl.setFont(vf)
        tl.addWidget(val_lbl)
        title_lbl = QLabel(title)
        title_lbl.setObjectName("secondary")
        tl.addWidget(title_lbl)
        tile._value_label = val_lbl  # stash for later updates
        return tile

    # ------------------------------------------------------------------
    # Section / period switching
    # ------------------------------------------------------------------

    def _style_seg_btn(self, btn: QPushButton, active: bool) -> None:
        btn.setProperty("active", active)
        btn.style().unpolish(btn)
        btn.style().polish(btn)

    def _set_section(self, section: str) -> None:
        self._section = section
        widget = {
            "templates": self._templates_panel,
            "history": self._history_panel,
            "stats": self._stats_panel,
        }[section]
        self._stack.setCurrentWidget(widget)
        for s in ("templates", "history", "stats"):
            btn = getattr(self, f"_sect_btn_{s}", None)
            if btn:
                self._style_seg_btn(btn, s == section)
        if section == "templates":
            self._reload_templates()
        elif section == "history":
            self._reload_history()
        elif section == "stats":
            self._reload_stats()

    def _set_stats_period(self, period: str) -> None:
        self._stats_period = period
        for p in ("week", "month", "all"):
            btn = getattr(self, f"_period_btn_{p}", None)
            if btn:
                self._style_seg_btn(btn, p == period)
        self._reload_stats()

    # ------------------------------------------------------------------
    # Load / reload
    # ------------------------------------------------------------------

    def reload(self) -> None:
        self._reload_templates()
        if self._section == "history":
            self._reload_history()
        elif self._section == "stats":
            self._reload_stats()

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                # setParent(None) detaches it from the widget tree immediately
                # (so it stops being painted); deleteLater() alone leaves it
                # visible at its old position — still a child, just no longer
                # layout-managed — until the deferred-delete event actually
                # runs, which briefly ghosts the old card under the new list.
                w.setParent(None)
                w.deleteLater()

    def _reload_templates(self) -> None:
        all_templates = self._db.get_workout_templates(include_drafts=True)
        drafts = [t for t in all_templates if t.get("status") == "draft"]
        saved = [t for t in all_templates if t.get("status") != "draft"]

        self._clear_layout(self._drafts_layout)
        self._drafts_heading.setVisible(bool(drafts))
        for t in drafts:
            card = TemplateCard(t, self)
            card.edit_requested.connect(self._on_edit_template)
            card.delete_requested.connect(self._on_discard_draft)
            card.approve_requested.connect(self._on_approve_draft)
            self._drafts_layout.addWidget(card)

        self._clear_layout(self._templates_layout)
        if not saved:
            lbl = QLabel("No templates yet. Click \"+ New Template\" to build one.")
            lbl.setObjectName("secondary")
            self._templates_layout.addWidget(lbl)
        for t in saved:
            card = TemplateCard(t, self)
            card.edit_requested.connect(self._on_edit_template)
            card.delete_requested.connect(self._on_delete_template)
            self._templates_layout.addWidget(card)

        if drafts:
            n = len(drafts)
            noun = "draft" if n == 1 else "drafts"
            verb = "needs" if n == 1 else "need"
            self._draft_banner_btn.setText(f"⚠ {n} {noun} {verb} review")
            self._draft_banner_btn.setVisible(True)
        else:
            self._draft_banner_btn.setVisible(False)

    def _reload_history(self) -> None:
        self._clear_layout(self._history_layout)
        sessions = self._db.get_workout_sessions(limit=200)
        template_names = {t["id"]: t["name"] for t in self._db.get_workout_templates(include_drafts=True)}
        if not sessions:
            lbl = QLabel("No workout sessions logged yet.")
            lbl.setObjectName("secondary")
            self._history_layout.addWidget(lbl)
            return
        for s in sessions:
            row = WorkoutSessionRow(s, template_names.get(s.get("template_id")), self)
            row.clicked.connect(self._on_open_session)
            row.delete_requested.connect(self._on_delete_session)
            self._history_layout.addWidget(row)

    def _period_start_date(self) -> Optional[str]:
        today = datetime.date.today()
        if self._stats_period == "week":
            return (today - datetime.timedelta(days=7)).isoformat()
        if self._stats_period == "month":
            return (today - datetime.timedelta(days=30)).isoformat()
        return None  # all-time

    def _reload_stats(self) -> None:
        sessions = self._db.get_workout_sessions(start_date=self._period_start_date())
        exercises = {e["id"]: e["name"] for e in self._db.get_workout_exercises()}

        workout_count = len(sessions)
        total_sets = 0
        total_volume = 0.0
        total_secs = 0.0
        per_exercise: dict[str, dict] = {}

        for s in sessions:
            if s.get("ended_at"):
                total_secs += _duration_secs(s["started_at"], s["ended_at"])
            for log in s.get("set_logs") or []:
                if log.get("skipped"):
                    continue
                total_sets += 1
                if log.get("type") == "reps" and log.get("actual_weight_kg") and log.get("actual_reps"):
                    total_volume += log["actual_weight_kg"] * log["actual_reps"]

                ex_id = log["exercise_id"]
                entry = per_exercise.setdefault(ex_id, {"most_recent": None, "most_recent_at": "", "best": None})
                completed_at = log.get("completed_at") or s["started_at"]
                if completed_at >= entry["most_recent_at"]:
                    entry["most_recent_at"] = completed_at
                    entry["most_recent"] = log

                cur = entry["best"]
                if log.get("type") == "reps":
                    key = (log.get("actual_weight_kg") or 0, log.get("actual_reps") or 0)
                    cur_key = (cur.get("actual_weight_kg") or 0, cur.get("actual_reps") or 0) if cur and cur.get("type") == "reps" else (-1, -1)
                    if key > cur_key:
                        entry["best"] = log
                else:
                    secs = log.get("actual_seconds") or 0
                    cur_secs = (cur.get("actual_seconds") or 0) if cur and cur.get("type") == "time" else -1
                    if secs > cur_secs:
                        entry["best"] = log

        self._tile_workouts._value_label.setText(str(workout_count))
        self._tile_sets._value_label.setText(str(total_sets))
        self._tile_volume._value_label.setText(f"{total_volume:,.0f} kg")
        self._tile_time._value_label.setText(_fmt_duration(total_secs))

        self._clear_layout(self._exercise_stats_layout)
        if not per_exercise:
            lbl = QLabel("No logged sets in this period.")
            lbl.setObjectName("secondary")
            self._exercise_stats_layout.addWidget(lbl)
            return
        for ex_id, entry in sorted(per_exercise.items(), key=lambda kv: exercises.get(kv[0], "").lower()):
            name = exercises.get(ex_id, "Exercise")
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(4, 2, 4, 2)
            name_lbl = QLabel(name)
            name_lbl.setMinimumWidth(140)
            rl.addWidget(name_lbl)
            info = QLabel(
                f"Best: {_set_log_display(entry['best'])}   ·   "
                f"Most recent: {_set_log_display(entry['most_recent'])}"
            )
            info.setObjectName("secondary")
            rl.addWidget(info, 1)
            self._exercise_stats_layout.addWidget(row)

    # ------------------------------------------------------------------
    # Actions — templates
    # ------------------------------------------------------------------

    def _on_new_template(self) -> None:
        dlg = TemplateBuilderDialog(self._db, self)
        if dlg.exec():
            self._db.create_workout_template(dlg.result_template(status="saved"))
            self._reload_templates()

    def _on_edit_template(self, template_id: str) -> None:
        template = self._db.get_workout_template(template_id)
        if not template:
            return
        dlg = TemplateBuilderDialog(self._db, self, template=template)
        if dlg.exec():
            # Editing a draft keeps it a draft until the user explicitly
            # clicks Approve — saving edits alone shouldn't silently
            # promote it out of the review queue.
            status = template.get("status", "saved")
            payload = dlg.result_template(template_id=template_id, status=status)
            self._db.replace_workout_template(template_id, payload)
            self._reload_templates()

    def _on_delete_template(self, template_id: str) -> None:
        confirm = QMessageBox.question(
            self, "Delete Template",
            "Delete this workout template? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self._db.delete_workout_template(template_id)
            self._reload_templates()

    def _on_discard_draft(self, template_id: str) -> None:
        confirm = QMessageBox.question(
            self, "Discard Draft",
            "Discard this AI-generated draft? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self._db.delete_workout_template(template_id)
            self._reload_templates()

    def _on_approve_draft(self, template_id: str) -> None:
        self._db.approve_workout_template(template_id)
        self._reload_templates()

    # ------------------------------------------------------------------
    # Actions — history
    # ------------------------------------------------------------------

    def _on_open_session(self, session_id: str) -> None:
        session = self._db.get_workout_session(session_id)
        if not session:
            return
        dlg = SessionDetailDialog(self._db, self, session=session)
        if dlg.exec():
            self._db.update_workout_session(
                session_id,
                started_at=dlg.result_start,
                ended_at=dlg.result_end,
                notes=dlg.result_notes,
                set_logs=dlg.result_set_logs,
            )
            self._reload_history()

    def _on_delete_session(self, session_id: str) -> None:
        confirm = QMessageBox.question(
            self, "Delete Session",
            "Delete this workout session? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self._db.delete_workout_session(session_id)
            self._reload_history()

    # ------------------------------------------------------------------
    # Theme / config
    # ------------------------------------------------------------------

    def apply_theme(self, dark: bool) -> None:
        self._dark = dark
        self._apply_card_styles()

    def apply_ui_config(self, _=None) -> None:
        pass  # reserved for future font-size controls

    def _apply_card_styles(self) -> None:
        bg = _styles.D_WHITE if self._dark else _styles.WHITE
        card_bg = _styles.D_GRAY_LIGHT if self._dark else _styles.GRAY_LIGHT
        border = _styles.D_GRAY_BORDER if self._dark else _styles.GRAY_BORDER
        text2 = _styles.D_GRAY_TEXT if self._dark else _styles.GRAY_TEXT
        accent = _styles.BLUE

        self.setStyleSheet(f"""
            QWidget#workout_topbar {{
                background: {bg};
                border-bottom: 1px solid {border};
            }}
            QWidget#workout_card {{
                background: {card_bg};
                border: 1px solid {border};
                border-radius: 8px;
            }}
            QWidget#workout_block {{
                background: {card_bg};
                border: 1px solid {border};
                border-radius: 6px;
            }}
            QWidget#draft_card {{
                background: {card_bg};
                border: 1px solid {accent};
                border-radius: 8px;
            }}
            QLabel#draft_badge {{
                background: {accent};
                color: {_styles.ON_ACCENT};
                border-radius: 3px;
                padding: 1px 6px;
                font-size: 10px;
                font-weight: 700;
            }}
            QLabel#secondary {{
                color: {text2};
                font-size: 12px;
            }}
        """)
