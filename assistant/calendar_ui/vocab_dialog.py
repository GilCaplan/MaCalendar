"""Vocabulary & Assistant Log dialog (Mac).

Two tabs:
  • Vocabulary — words the STT should know, their learned aliases, a
    "heard X → should be Y" teacher, and the auto-correct toggles.
  • Assistant log — recent commands from the shared memory DB with what they
    turned into, plus queued commands waiting for the LLM.
"""

from __future__ import annotations

import json

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from assistant.calendar_ui import icons


def _icon_label(name: str, size: int = 14) -> QLabel:
    """Small QLabel showing one glyph (for composite list rows)."""
    lbl = QLabel()
    lbl.setPixmap(icons.pixmap(name, size=size))
    lbl.setFixedSize(size, size)
    return lbl


def _row_widget(*parts) -> QWidget:
    """Build one list-row widget from `("icon", name)` / `("text", s)` /
    `("muted", s)` parts. Used where a single row needs more than one
    leading glyph (source device, status, feedback mark, …) — a plain
    QListWidgetItem only supports a single QIcon.
    """
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(4, 2, 4, 2)
    lay.setSpacing(6)
    for kind, value in parts:
        if kind == "icon":
            lay.addWidget(_icon_label(value))
        else:
            text_lbl = QLabel(value)
            if kind == "muted":
                text_lbl.setObjectName("muted")
            lay.addWidget(text_lbl)
    lay.addStretch(1)
    return w


class VocabDialog(QDialog):
    def __init__(self, parent=None, pipeline=None) -> None:
        super().__init__(parent)
        self._pipeline = pipeline
        self.setWindowTitle("Vocabulary & Assistant Log")
        self.setMinimumSize(620, 520)
        from assistant.stt.vocab import get_vocab
        from assistant.intent.memory import get_memory
        self._vocab = get_vocab()
        self._memory = get_memory()

        root = QVBoxLayout(self)
        tabs = QTabWidget()
        root.addWidget(tabs)
        tabs.addTab(self._build_vocab_tab(), "Vocabulary")
        tabs.addTab(self._build_log_tab(), "Assistant log")

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        root.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)

    # ------------------------------------------------------------ vocab

    def _build_vocab_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        # toggles
        row = QHBoxLayout()
        self._auto_cb = QCheckBox("Auto-correct transcripts")
        self._auto_cb.setChecked(self._vocab.auto_correct)
        self._learn_cb = QCheckBox("Learn new misspellings")
        self._learn_cb.setChecked(self._vocab.learn_aliases)
        self._thr = QDoubleSpinBox()
        self._thr.setRange(0.6, 0.95)
        self._thr.setSingleStep(0.05)
        self._thr.setValue(self._vocab.threshold)
        self._thr.setToolTip("Similarity needed for a fuzzy fix (lower = more aggressive)")
        for cb in (self._auto_cb, self._learn_cb):
            cb.toggled.connect(self._save_settings)
        self._thr.valueChanged.connect(self._save_settings)
        row.addWidget(self._auto_cb)
        row.addWidget(self._learn_cb)
        row.addStretch(1)
        row.addWidget(QLabel("Strictness:"))
        row.addWidget(self._thr)
        lay.addLayout(row)

        hint = QLabel("Words here are given to Whisper as a hint and used to auto-correct "
                      "near-misses. Fix a misheard word once and it's remembered.")
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        lay.addWidget(hint)

        # search — 374 words is well past the point of scrolling for one
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search words, labels and expansions")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(lambda _t: self._refresh_vocab())
        lay.addWidget(self._search)

        # word list — double-click opens what the word means
        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(self._edit_word)
        self._list.setToolTip("Double-click a word to set what it means")
        lay.addWidget(self._list, 1)

        # add word
        add_row = QHBoxLayout()
        self._new_word = QLineEdit()
        self._new_word.setPlaceholderText("Add a name or word (e.g. Kyra, Shaul, Minchat Maariv)")
        self._new_word.returnPressed.connect(self._add_word)
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._add_word)
        del_btn = QPushButton("Remove selected")
        del_btn.clicked.connect(self._remove_selected)
        add_row.addWidget(self._new_word, 1)
        add_row.addWidget(add_btn)
        add_row.addWidget(del_btn)
        setup_btn = QPushButton("Set up… (questions & starter packs)")
        setup_btn.clicked.connect(self._run_interview)
        add_row.addWidget(setup_btn)
        import_btn = QPushButton("Import text / WhatsApp…")
        import_btn.setToolTip("Pick a WhatsApp chat export (.txt) or any text file; names and non-English words are proposed for approval")
        import_btn.clicked.connect(self._import_file)
        add_row.addWidget(import_btn)
        lay.addLayout(add_row)

        # teach correction
        form = QFormLayout()
        self._wrong = QLineEdit()
        self._wrong.setPlaceholderText("what it heard, e.g. Shawl")
        self._right = QLineEdit()
        self._right.setPlaceholderText("what you said, e.g. Shaul")
        self._right.returnPressed.connect(self._teach)
        teach_btn = QPushButton("Teach correction")
        teach_btn.clicked.connect(self._teach)
        form.addRow("Heard:", self._wrong)
        form.addRow("Should be:", self._right)
        form.addRow("", teach_btn)
        lay.addLayout(form)

        # recent transcripts (double-click a word → prefill "heard")
        lay.addWidget(QLabel("Recent transcripts (double-click to load into the teacher):"))
        self._recent = QListWidget()
        self._recent.setMaximumHeight(120)
        self._recent.itemDoubleClicked.connect(self._recent_clicked)
        lay.addWidget(self._recent)

        self._refresh_vocab()
        return w

    def _refresh_vocab(self) -> None:
        self._list.clear()
        needle = (self._search.text() if hasattr(self, "_search") else "").strip().lower()
        for e in self._vocab.entries:
            if needle and needle not in " ".join(
                [e.word, getattr(e, "label", "") or "", getattr(e, "expands_to", "") or "",
                 " ".join(e.aliases)]
            ).lower():
                continue
            text = e.word
            # A word can do three separate things; showing which is which is
            # the whole point of the list.
            if getattr(e, "label", ""):
                text += f"   [{e.label}]"
            if getattr(e, "expands_to", ""):
                text += f"   = {e.expands_to}"
            if e.aliases:
                text += "   ← heard as: " + ", ".join(e.aliases)
            if e.hits:
                text += f"   ({e.hits}× fixed)"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, e.word)
            self._list.addItem(item)
        self._recent.clear()
        for r in self._vocab.recent[:10]:
            src_icon = "iphone" if r.get("source") == "ios" else "mac"
            fixes = r.get("corrections") or []
            parts = [("icon", src_icon), ("text", r.get("corrected", ""))]
            if fixes:
                parts.append(("icon", "corrected"))
                parts.append(("muted", ", ".join(f"{c['from']}→{c['to']}" for c in fixes)))
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, r.get("original", ""))
            row = _row_widget(*parts)
            item.setSizeHint(row.sizeHint())
            self._recent.addItem(item)
            self._recent.setItemWidget(item, row)

    def _save_settings(self) -> None:
        self._vocab.update_settings(
            auto_correct=self._auto_cb.isChecked(),
            learn_aliases=self._learn_cb.isChecked(),
            threshold=self._thr.value(),
        )

    def _edit_word(self, item: QListWidgetItem) -> None:
        """What a word means, and what it is short for.

        Both fields change how commands are interpreted — a label decides how
        a task is tagged — and until now they could only be set by editing a
        JSON file. A wrong label has no visible symptom beyond tasks quietly
        filing themselves in the wrong place, which is exactly the kind of
        thing that needs to be visible.
        """
        word = item.data(Qt.ItemDataRole.UserRole)
        entry = next((e for e in self._vocab.entries if e.word == word), None)
        if entry is None:
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(word)
        outer = QVBoxLayout(dlg)
        form = QFormLayout()

        label = QLineEdit(getattr(entry, "label", "") or "")
        label.setPlaceholderText("Coursework, Groceries, Errands…")
        form.addRow("Means", label)

        expands = QLineEdit(getattr(entry, "expands_to", "") or "")
        expands.setPlaceholderText("What the shorthand stands for")
        form.addRow("Short for", expands)

        aliases = QLineEdit(", ".join(entry.aliases))
        aliases.setPlaceholderText("Misheard spellings, comma separated")
        form.addRow("Heard as", aliases)
        outer.addLayout(form)

        hint = QLabel(
            f"A task mentioning “{word}” gets the tag above. An expansion is "
            "never substituted into your words — the assistant is only told "
            "what it means."
        )
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        outer.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        outer.addWidget(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        self._vocab.update_word(
            word,
            label=label.text().strip(),
            expands_to=expands.text().strip(),
            aliases=[a.strip() for a in aliases.text().split(",") if a.strip()],
        )
        self._refresh_vocab()

    def _add_word(self) -> None:
        word = self._new_word.text().strip()
        if not word:
            return
        self._vocab.add_word(word)
        self._new_word.clear()
        self._refresh_vocab()

    def _remove_selected(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        word = item.data(Qt.ItemDataRole.UserRole)
        if QMessageBox.question(self, "Remove word", f"Remove '{word}' from your vocabulary?") \
                == QMessageBox.StandardButton.Yes:
            self._vocab.remove_word(word)
            self._refresh_vocab()

    def _teach(self) -> None:
        wrong, right = self._wrong.text().strip(), self._right.text().strip()
        if not wrong or not right or wrong.lower() == right.lower():
            return
        self._vocab.add_alias(wrong, right)
        self._wrong.clear()
        self._right.clear()
        self._refresh_vocab()

    def _run_interview(self) -> None:
        """First-run vocabulary interview: one prompt per question, then presets."""
        from PyQt6.QtWidgets import QInputDialog
        from assistant.stt import vocab_onboarding as ob
        answers: dict[str, list[str]] = {}
        for q in ob.QUESTIONS:
            ex = ", ".join(q["examples"][:4])
            text, ok = QInputDialog.getText(
                self, "Teach it your words", f"{q['question']}\n{q['hint']}\n\nComma-separated"
                + (f" (e.g. {ex})" if ex else "") + ":")
            if not ok:
                return
            answers[q["id"]] = [w.strip() for w in text.split(",") if w.strip()]
        presets: list[str] = []
        for p in ob.PRESETS:
            sample = ", ".join(p["words"][:6]) + ("…" if len(p["words"]) > 6 else "")
            if QMessageBox.question(self, "Starter pack", f"Add the “{p['label']}” pack?\n{sample}") \
                    == QMessageBox.StandardButton.Yes:
                presets.append(p["id"])
        res = ob.apply(self._vocab, answers, presets)
        QMessageBox.information(self, "Vocabulary", f"Added {res['added']} words ({res['total']} total).")
        self._refresh_vocab()

    def _import_file(self) -> None:
        from PyQt6.QtWidgets import QFileDialog, QDialogButtonBox
        from assistant.stt import vocab_import
        QMessageBox.information(
            self, "Import words",
            "Pick any text that has your names and words in it — a WhatsApp chat export, notes, an email.\n\n"
            "WhatsApp (phone): open the chat → tap the name at the top → Export Chat → Without Media → "
            "Save to Files / AirDrop to this Mac. Then choose that .txt here.\n\n"
            "Privacy: the file is scanned once for names and non-English words and you choose which to keep. "
            "The text itself is not stored anywhere, not uploaded, and not sent to any AI service — "
            "only the ticked words go into your local vocabulary (~/.assistant_tools/vocab.json).",
        )
        path, _ = QFileDialog.getOpenFileName(self, "Import text", "", "Text files (*.txt *.md *.csv);;All files (*)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except OSError as e:
            QMessageBox.critical(self, "Import", f"Could not read file: {e}")
            return
        known = {e.word for e in self._vocab.entries}
        cands = vocab_import.extract(text, known)
        if not cands:
            QMessageBox.information(self, "Import", "Nothing new found in that file.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Choose words to add")
        dlg.setMinimumSize(420, 520)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(f"{len(cands)} candidates — tick the ones the assistant should know:"))
        lst = QListWidget()
        labels = {"sender": "person", "name": "name/place", "hebrew": "Hebrew", "non-english": "non-English"}
        for c in cands:
            it = QListWidgetItem(f"{c['word']}   ({labels.get(c['reason'], c['reason'])}, {c['count']}×)"
                                 + (f"   — {c['sample']}" if c.get("sample") and c["sample"] != c["word"] else ""))
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if c["reason"] in ("sender", "hebrew") else Qt.CheckState.Unchecked)
            it.setData(Qt.ItemDataRole.UserRole, c["word"])
            lst.addItem(it)
        lay.addWidget(lst, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(buttons)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        added = 0
        for i in range(lst.count()):
            it = lst.item(i)
            if it.checkState() == Qt.CheckState.Checked:
                self._vocab.add_word(it.data(Qt.ItemDataRole.UserRole)); added += 1
        QMessageBox.information(self, "Import", f"Added {added} words.")
        self._refresh_vocab()

    def _recent_clicked(self, item: QListWidgetItem) -> None:
        self._wrong.setText(item.data(Qt.ItemDataRole.UserRole) or "")
        self._wrong.setFocus()
        self._wrong.selectAll()

    # -------------------------------------------------------------- log

    def _build_log_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        stats = self._memory.stats()
        fb = stats.get("feedback", {})
        summary = QLabel(
            f"{stats['total']} commands remembered · "
            f"{fb.get('corrected', 0)} corrected · {fb.get('rejected', 0)} rejected · "
            f"avg LLM {stats['avg_llm_ms'] / 1000:.1f} s · avg total {stats['avg_total_ms'] / 1000:.1f} s"
        )
        summary.setObjectName("muted")
        lay.addWidget(summary)

        # Commands parked because the LLM was unreachable. The phone can retry
        # these via /pending/<id>/retry; these buttons are the Mac's equivalent.
        self._pending_box = QVBoxLayout()
        lay.addLayout(self._pending_box)
        self._refresh_pending()

        self._log = QListWidget()
        self._log.itemClicked.connect(self._show_example)
        lay.addWidget(self._log, 2)
        self._detail = QTextEdit()
        self._detail.setReadOnly(True)
        lay.addWidget(self._detail, 1)

        fb_icons = {"corrected": "corrected", "rejected": "rejected", "approved": "thumbs_up"}
        for ex in self._memory.recent(100):
            src_icon = "iphone" if ex["source"] == "ios" else "mac"
            ok_icon = "approved" if ex["success"] else "error"
            parts = [
                ("icon", ok_icon), ("icon", src_icon),
                ("text", f"{ex['time'][5:16]}  [{ex['parse_path'] or '-'}]  {ex['transcript'][:70]}"),
            ]
            if ex["feedback"] in fb_icons:
                parts.append(("icon", fb_icons[ex["feedback"]]))
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, ex)
            row = _row_widget(*parts)
            item.setSizeHint(row.sizeHint())
            self._log.addItem(item)
            self._log.setItemWidget(item, row)
        return w

    def _refresh_pending(self) -> None:
        while self._pending_box.count():
            item = self._pending_box.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
            elif item.layout() is not None:
                while item.layout().count():
                    sub_item = item.layout().takeAt(0)
                    if sub_item.widget() is not None:
                        sub_item.widget().deleteLater()
        for row in self._memory.pending():
            line = QHBoxLayout()
            line.addWidget(_icon_label("pending"), 0, Qt.AlignmentFlag.AlignVCenter)
            label = QLabel(f"Queued ({row.get('reason', 'LLM offline')}): {row['transcript'][:60]}")
            label.setWordWrap(True)
            line.addWidget(label, 1)
            retry_btn = QPushButton("Retry")
            retry_btn.setEnabled(self._pipeline is not None)
            retry_btn.setToolTip("Run this command now" if self._pipeline is not None
                                 else "Available while the voice assistant is running")
            retry_btn.clicked.connect(lambda _=False, pid=int(row["id"]): self._retry_pending(pid))
            line.addWidget(retry_btn)
            dismiss_btn = QPushButton("Dismiss")
            dismiss_btn.clicked.connect(lambda _=False, pid=int(row["id"]): self._dismiss_pending(pid))
            line.addWidget(dismiss_btn)
            self._pending_box.addLayout(line)

    def _retry_pending(self, pending_id: int) -> None:
        if self._pipeline is None:
            return
        if self._pipeline.retry_pending(pending_id):
            QMessageBox.information(self, "Queued command",
                                    "Running it now — watch the thinking panel.")
            self.accept()
        else:
            QMessageBox.information(self, "Queued command",
                                    "The assistant is busy — try again in a moment.")

    def _dismiss_pending(self, pending_id: int) -> None:
        self._memory.resolve_pending(pending_id, "dismissed")
        self._refresh_pending()

    def _show_example(self, item: QListWidgetItem) -> None:
        ex = item.data(Qt.ItemDataRole.UserRole)
        lines = [
            f"Transcript: {ex['transcript']}",
            f"Raw STT:    {ex['raw_transcript']}" if ex.get("raw_transcript") != ex["transcript"] else "",
            f"Path: {ex['parse_path']}   LLM: {ex['llm_ms'] / 1000:.1f} s   "
                f"total: {ex['total_ms'] / 1000:.1f} s",
            f"Result: {ex['result']}",
            "Actions: " + json.dumps(ex["actions"], ensure_ascii=False, indent=1),
        ]
        if ex.get("correction"):
            lines.append(f"Feedback ({ex['feedback']}): " + json.dumps(ex["correction"], ensure_ascii=False, indent=1))
        self._detail.setPlainText("\n".join(l for l in lines if l))
