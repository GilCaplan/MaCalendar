"""Event categories → colours (Mac).

The desktop twin of the iPhone's "Event colours" screen. Every event is
auto-tagged by the keyword classifier in `assistant.actions.calendar.categories`
and coloured by its category (the alternate shade kicks in when a neighbouring
event already uses the primary), so both apps edit the same
~/.assistant_tools/categories.json.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QColorDialog, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from assistant.actions.calendar import categories as _cat
from assistant.calendar_ui import styles as _styles


class _SwatchButton(QPushButton):
    """Colour well that opens the system picker."""

    def __init__(self, hex_color: str, size: int = 26, parent=None) -> None:
        super().__init__(parent)
        self._hex = hex_color
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._pick)
        self._refresh()

    @property
    def hex_color(self) -> str:
        return self._hex

    def _refresh(self) -> None:
        self.setStyleSheet(
            f"QPushButton {{ background-color: {self._hex}; border: 1px solid "
            f"{_styles.D_GRAY_MID if _styles._dark else _styles.GRAY_MID}; "
            f"border-radius: {_styles.RADIUS_SM}px; padding: 0; }}"
        )

    def _pick(self) -> None:
        color = QColorDialog.getColor(QColor(self._hex), self, "Choose colour")
        if color.isValid():
            self._hex = color.name()
            self._refresh()


class CategoryEditDialog(QDialog):
    """Name, the two shades, and the keywords that pick this category."""

    def __init__(self, category: dict | None = None, parent=None) -> None:
        super().__init__(parent)
        self._is_new = category is None
        category = category or {"name": "", "color": "#64748b", "alt": "#475569", "keywords": []}
        self._original_name = category["name"]
        self.setWindowTitle("Add category" if self._is_new else f"Edit “{category['name']}”")
        self.setMinimumWidth(420)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(10)

        form = QFormLayout()
        self._name = QLineEdit(category["name"])
        self._name.setPlaceholderText("e.g. Volunteering")
        self._name.setEnabled(self._is_new)   # renaming would orphan tagged events
        form.addRow("Name", self._name)

        swatches = QHBoxLayout()
        swatches.setSpacing(8)
        self._color = _SwatchButton(category.get("color", "#64748b"))
        self._alt = _SwatchButton(category.get("alt", "#475569"))
        swatches.addWidget(self._color)
        swatches.addWidget(QLabel("primary"))
        swatches.addSpacing(10)
        swatches.addWidget(self._alt)
        swatches.addWidget(QLabel("shade for neighbours"))
        swatches.addStretch(1)
        holder = QWidget()
        holder.setLayout(swatches)
        form.addRow("Colours", holder)
        lay.addLayout(form)

        lay.addWidget(QLabel("Keywords (comma-separated — matched in the event's title, guests and location):"))
        self._keywords = QPlainTextEdit(", ".join(category.get("keywords", [])))
        self._keywords.setFixedHeight(110)
        lay.addWidget(self._keywords)

        hint = QLabel("Leave keywords empty for a category that's only used when you say so. "
                      "“Personal” is the fallback when nothing matches.")
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        lay.addWidget(hint)

        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                               | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self._save)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    def _save(self) -> None:
        name = self._name.text().strip()
        if not name:
            QMessageBox.information(self, "Category", "Give the category a name.")
            return
        keywords = [k.strip() for k in self._keywords.toPlainText().replace("\n", ",").split(",") if k.strip()]
        try:
            _cat.upsert(name, color=self._color.hex_color, alt=self._alt.hex_color, keywords=keywords)
        except ValueError as exc:
            QMessageBox.warning(self, "Category", str(exc))
            return
        self.accept()


class CategoriesDialog(QDialog):
    """List of categories, their colours and the recolour actions."""

    def __init__(self, parent=None, dark: bool = True) -> None:
        super().__init__(parent)
        self.setWindowTitle("Event Colours & Categories")
        self.setMinimumSize(520, 560)
        self._dark = dark
        self._changed = False

        root = QVBoxLayout(self)
        intro = QLabel(
            "New events are tagged automatically from their title and coloured by category. "
            "Two events next to each other never share a colour — the second gets the category's "
            "darker shade. Unsure → Personal.")
        intro.setWordWrap(True)
        intro.setObjectName("muted")
        root.addWidget(intro)

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(lambda _: self._edit())
        root.addWidget(self._list, 1)

        row = QHBoxLayout()
        add_btn = QPushButton("Add…")
        add_btn.clicked.connect(self._add)
        edit_btn = QPushButton("Edit…")
        edit_btn.clicked.connect(self._edit)
        del_btn = QPushButton("Remove")
        del_btn.setObjectName("destructive")
        del_btn.clicked.connect(self._remove)
        for b in (add_btn, edit_btn, del_btn):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            row.addWidget(b)
        row.addStretch(1)
        root.addLayout(row)

        root.addWidget(QLabel("Existing events:"))
        recolor_row = QHBoxLayout()
        fill_btn = QPushButton("Colour events still on the default")
        fill_btn.clicked.connect(lambda: self._recolor(force=False))
        all_btn = QPushButton("Re-tag and recolour everything")
        all_btn.setObjectName("destructive")
        all_btn.clicked.connect(lambda: self._recolor(force=True))
        for b in (fill_btn, all_btn):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            recolor_row.addWidget(b)
        recolor_row.addStretch(1)
        root.addLayout(recolor_row)

        self._status = QLabel("")
        self._status.setObjectName("muted")
        root.addWidget(self._status)

        close_btn = QPushButton("Done")
        close_btn.setObjectName("primary")
        close_btn.clicked.connect(self._finish)
        root.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)

        self.reload()

    # ------------------------------------------------------------------

    def reload(self) -> None:
        self._list.clear()
        for c in _cat.all_categories():
            keywords = c.get("keywords") or []
            preview = ", ".join(keywords[:6]) + ("…" if len(keywords) > 6 else "")
            item = QListWidgetItem(f"{c['name']}   {preview or 'default when unsure'}")
            item.setData(Qt.ItemDataRole.UserRole, c)
            # two-tone swatch: primary, then the neighbour shade
            pm = QPixmap(26, 14)
            pm.fill(Qt.GlobalColor.transparent)
            p = QPainter(pm)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(c.get("color", "#64748b")))
            p.drawEllipse(0, 0, 14, 14)
            p.setBrush(QColor(c.get("alt", "#475569")))
            p.drawEllipse(14, 2, 10, 10)
            p.end()
            item.setIcon(QIcon(pm))
            self._list.addItem(item)

    def _selected(self) -> dict | None:
        item = self._list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _add(self) -> None:
        if CategoryEditDialog(None, self).exec():
            self._changed = True
            self.reload()

    def _edit(self) -> None:
        c = self._selected()
        if c is None:
            return
        if CategoryEditDialog(c, self).exec():
            self._changed = True
            self.reload()

    def _remove(self) -> None:
        c = self._selected()
        if c is None:
            return
        if c["name"].lower() == "personal":
            QMessageBox.information(self, "Categories",
                                    "“Personal” is the fallback category and can't be removed.")
            return
        if QMessageBox.question(self, "Remove category",
                                f"Remove “{c['name']}”? Events already tagged with it keep their colour "
                                "until you recolour them.") != QMessageBox.StandardButton.Yes:
            return
        if _cat.remove(c["name"]):
            self._changed = True
            self.reload()

    def _recolor(self, force: bool) -> None:
        if force and QMessageBox.question(
                self, "Recolour everything",
                "Re-tag and recolour every event, replacing colours you set by hand?"
        ) != QMessageBox.StandardButton.Yes:
            return
        from assistant.db import get_db
        n = get_db().recategorise_all(force=force)
        self._changed = True
        self._status.setText(f"{n} event{'' if n == 1 else 's'} recoloured.")

    def _finish(self) -> None:
        # accept() tells the caller to refresh the calendar; reject() = nothing changed
        if self._changed:
            self.accept()
        else:
            self.reject()
