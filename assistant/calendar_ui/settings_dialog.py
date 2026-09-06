"""The Assistant Settings dialog — extracted verbatim from window.py.

Convolution fix #3 (Gil-approved, 2026-09-06): window.py was a ~2,300-line
god-file and this dialog was ~450 of them. Moved whole, unchanged — the
function still takes the window as `self` so every `self._config` /
`self.show_toast` reference works exactly as before; window.py keeps a
3-line delegate. Persistence goes through assistant/config_store.
"""
from __future__ import annotations

import subprocess

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from assistant.calendar_ui import icons
from assistant.calendar_ui import styles as _styles
from assistant.calendar_ui.dialog_utils import install_enter_confirms
from assistant.calendar_ui.styles import GRAY_TEXT


def open_settings(self) -> None:
    if not self._pipeline:
        return

    from PyQt6.QtWidgets import QFormLayout, QFrame, QGroupBox, QScrollArea

    dialog = QDialog(self)
    dialog.setWindowTitle("Assistant Settings")
    dialog.setMinimumSize(520, 560)
    dialog.resize(560, 720)

    # Grouped into the same sections the iPhone's Settings screen uses
    # (Appearance / Tabs / Hebrew Calendar / Voice / Assistant) and scrolled,
    # with Test & Save pinned. It used to be one flat column of controls with
    # stretches between them, which squeezed everything below "Hebrew
    # Calendar" into overlapping slivers — the Font Sizes grid rendered at
    # zero height and could not be reached at all.
    outer = QVBoxLayout(dialog)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    content = QWidget()
    scroll.setWidget(content)
    outer.addWidget(scroll, 1)

    layout = QVBoxLayout(content)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(14)

    def section(title: str) -> QVBoxLayout:
        """One titled group; returns the layout to put controls in."""
        box = QGroupBox(title)
        inner = QVBoxLayout(box)
        inner.setContentsMargins(14, 12, 14, 12)
        inner.setSpacing(8)
        layout.addWidget(box)
        return inner

    def hint(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setObjectName("muted")
        lbl.setStyleSheet(
            f"color: {_styles.D_GRAY_TEXT if self._dark else GRAY_TEXT}; font-size: 11px;")
        return lbl

    # ── Appearance ────────────────────────────────────────────────
    appearance = section("Appearance")
    appearance_form = QFormLayout()
    appearance_form.setSpacing(8)
    appearance_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    theme_combo = QComboBox()
    theme_combo.addItems(["Light", "Dark"])
    theme_combo.setCurrentText("Dark" if (self._config.theme == "dark") else "Light")
    theme_combo.setMaximumWidth(160)
    appearance_form.addRow("Theme on startup:", theme_combo)

    accent_state = {"hex": self._config.ui.accent_color}
    swatch_row = QHBoxLayout()
    swatch_row.setSpacing(8)
    swatch_buttons: list[QPushButton] = []

    def make_swatch(hex_color: str) -> QPushButton:
        btn = QPushButton()
        btn.setFixedSize(24, 24)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)

        def refresh():
            selected = accent_state["hex"].lower() == hex_color.lower()
            ring = "#ffffff" if selected else "transparent"
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {hex_color}; border-radius: 12px; "
                f"padding: 0; border: 2px solid {ring}; }}"
            )
        btn._refresh = refresh
        refresh()

        def on_click():
            accent_state["hex"] = hex_color
            custom_btn.setStyleSheet("")
            for b in swatch_buttons:
                b._refresh()
        btn.clicked.connect(on_click)
        return btn

    for _name, hex_color in _styles.ACCENT_PRESETS:
        b = make_swatch(hex_color)
        b.setToolTip(_name)
        swatch_buttons.append(b)
        swatch_row.addWidget(b)

    custom_btn = QPushButton("Custom…")
    custom_btn.setObjectName("flat")

    def pick_custom():
        initial = QColor(accent_state["hex"])
        color = QColorDialog.getColor(initial, dialog, "Choose Accent Color")
        if color.isValid():
            accent_state["hex"] = color.name()
            for b in swatch_buttons:
                b._refresh()
            custom_btn.setStyleSheet(f"QPushButton#flat {{ border: 2px solid {color.name()}; }}")
    custom_btn.clicked.connect(pick_custom)
    swatch_row.addWidget(custom_btn)
    swatch_row.addStretch(1)
    swatch_holder = QWidget()
    swatch_holder.setLayout(swatch_row)
    appearance_form.addRow("Accent colour:", swatch_holder)
    appearance.addLayout(appearance_form)

    compact_cb = QCheckBox("Compact layout density")
    compact_cb.setChecked(self._config.ui.compact_ui)
    appearance.addWidget(compact_cb)

    def update_style(compact: bool):
        layout.setSpacing(10 if compact else 14)
    compact_cb.toggled.connect(update_style)

    appearance.addWidget(hint("Font sizes"))
    font_grid = QGridLayout()
    font_grid.setVerticalSpacing(6)
    font_grid.setHorizontalSpacing(14)
    font_spins: dict[str, QSpinBox] = {}
    for i, (label, attr) in enumerate((("Month", "font_month"), ("Week", "font_week"),
                                       ("Day", "font_day"), ("Tasks", "font_tasks"),
                                       ("Coursework", "font_coursework"))):
        spin = QSpinBox()
        spin.setRange(8, 24)
        spin.setValue(getattr(self._config.ui, attr))
        font_spins[attr] = spin
        row, col = divmod(i, 2)
        font_grid.addWidget(QLabel(f"{label}:"), row, col * 2,
                            alignment=Qt.AlignmentFlag.AlignRight)
        font_grid.addWidget(spin, row, col * 2 + 1)
    font_grid.setColumnStretch(4, 1)
    appearance.addLayout(font_grid)
    month_spin, week_spin = font_spins["font_month"], font_spins["font_week"]
    day_spin, tasks_spin = font_spins["font_day"], font_spins["font_tasks"]
    coursework_spin = font_spins["font_coursework"]

    # ── Tabs ──────────────────────────────────────────────────────
    tabs = section("Tabs")
    coursework_tab_cb = QCheckBox("Show Coursework tab")
    coursework_tab_cb.setChecked(self._config.ui.show_coursework)
    workout_tab_cb = QCheckBox("Show Workout tab")
    workout_tab_cb.setChecked(getattr(self._config.ui, "show_workout", True))
    timer_tab_cb = QCheckBox("Show Timer tab")
    timer_tab_cb.setChecked(getattr(self._config.ui, "show_timer", True))
    for cb in (coursework_tab_cb, workout_tab_cb, timer_tab_cb):
        tabs.addWidget(cb)

    # ── Hebrew calendar ───────────────────────────────────────────
    hebrew = section("Hebrew Calendar")
    hebrew_form = QFormLayout()
    hebrew_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    hebrew_mode_combo = QComboBox()
    hebrew_mode_combo.addItem("English only", "english")
    hebrew_mode_combo.addItem("Hebrew only", "hebrew")
    hebrew_mode_combo.addItem("Both", "both")
    idx = hebrew_mode_combo.findData(self._config.hebrew_calendar.display_mode)
    hebrew_mode_combo.setCurrentIndex(idx if idx >= 0 else 0)
    hebrew_mode_combo.setMaximumWidth(180)
    hebrew_form.addRow("Show dates as:", hebrew_mode_combo)
    hebrew.addLayout(hebrew_form)
    hebrew_holidays_cb = QCheckBox("Show Jewish / Israeli holidays")
    hebrew_holidays_cb.setChecked(self._config.hebrew_calendar.show_holidays)
    hebrew.addWidget(hebrew_holidays_cb)
    hebrew_israel_cb = QCheckBox("Israel holiday schedule (uncheck for Diaspora)")
    hebrew_israel_cb.setChecked(self._config.hebrew_calendar.israel_holidays)
    hebrew.addWidget(hebrew_israel_cb)
    observance_cb = QCheckBox("Skip Shabbat && yom tov in series (observance)")
    observance_cb.setObjectName("observance_enabled_cb")
    observance_cb.setToolTip(
        "Recurring series skip Shabbat, yom tov and fast days (meals excepted),\n"
        "and the assistant declines to book into them. Uncheck to turn the\n"
        "whole observance gate off.")
    observance_cb.setChecked(bool(getattr(getattr(self._config, "observance", None),
                                          "enabled", True)))
    hebrew.addWidget(observance_cb)

    # ── Voice ─────────────────────────────────────────────────────
    voice = section("Voice")
    mute_cb = QCheckBox("Mute voice output")
    mute_cb.setChecked(self._pipeline._tts.mute)
    voice.addWidget(mute_cb)

    voice_form = QFormLayout()
    voice_form.setSpacing(8)
    voice_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    speed_spin = QSpinBox()
    speed_spin.setRange(50, 400)
    speed_spin.setValue(self._pipeline._tts.rate)
    speed_spin.setSuffix(" wpm")
    speed_spin.setMaximumWidth(120)
    voice_form.addRow("Talking speed:", speed_spin)

    voice_combo = QComboBox()
    import subprocess
    try:
        voices = subprocess.check_output(["say", "-v", "?"], text=True).splitlines()
        voice_names = []
        for v in voices:
            if v.strip():
                name = v.split()[0]
                if name not in voice_names:
                    voice_names.append(name)
        voice_combo.addItems(voice_names)
    except Exception:
        voice_combo.addItems(["Samantha", "Daniel", "Alex", "Ava", "Zari"])
    current_voice = self._pipeline._tts.voice
    if current_voice in [voice_combo.itemText(i) for i in range(voice_combo.count())]:
        voice_combo.setCurrentText(current_voice)
    else:
        voice_combo.addItem(current_voice)
        voice_combo.setCurrentText(current_voice)
    voice_combo.setMaximumWidth(200)
    voice_form.addRow("Voice:", voice_combo)
    voice.addLayout(voice_form)

    review_cb = QCheckBox("Ask before sending (Redo / Add more / Send)")
    review_cb.setChecked(getattr(self._config.audio, "review_before_send", True))
    voice.addWidget(review_cb)

    review_row = QHBoxLayout()
    review_row.addSpacing(20)
    review_row.addWidget(QLabel("Sends by itself after"))
    review_spin = QSpinBox()
    review_spin.setRange(1, 15)
    review_spin.setSuffix(" s")
    review_spin.setValue(getattr(self._config.audio, "review_seconds", 3))
    review_spin.setMaximumWidth(80)
    review_row.addWidget(review_spin)
    review_row.addStretch(1)
    voice.addLayout(review_row)
    review_cb.toggled.connect(review_spin.setEnabled)
    review_spin.setEnabled(review_cb.isChecked())
    voice.addWidget(hint("A spoken stop word — “execute”, “done” — always sends straight "
                         "away, with no wait."))

    phrase_form = QFormLayout()
    phrase_form.setSpacing(8)
    phrase_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    stop_phrases_edit = QLineEdit()
    stop_phrases_edit.setPlaceholderText("e.g. finish, that's all, stop recording")
    stop_phrases_edit.setText(", ".join(self._config.audio.stop_phrases))
    stop_phrases_edit.setToolTip("Extra words that stop the mic, on top of the built-in ones")
    phrase_form.addRow("Stop phrases:", stop_phrases_edit)

    sep_edit = QLineEdit()
    sep_edit.setPlaceholderText('e.g. "next event" — blank to disable')
    sep_edit.setText(self._config.audio.event_separator)
    sep_edit.setToolTip('Say: "meeting at 10am next event lunch at noon"')
    phrase_form.addRow("Event separator:", sep_edit)

    keywords_edit = QLineEdit()
    keywords_edit.setPlaceholderText("e.g. meeting, appointment, activity")
    keywords_edit.setText(", ".join(self._config.nlu.event_keywords))
    keywords_edit.setToolTip("Create instantly with this as a placeholder title, then let the LLM improve it")
    phrase_form.addRow("Event keywords:", keywords_edit)
    voice.addLayout(phrase_form)

    # ── Assistant ─────────────────────────────────────────────────
    assistant = section("Assistant")
    auto_cb = QCheckBox("Auto-approve actions (no confirmations)")
    auto_cb.setChecked(self._pipeline._confirmer.level == 0)
    assistant.addWidget(auto_cb)

    thinking_cb = QCheckBox("Show assistant thinking (floating step-by-step HUD)")
    thinking_cb.setToolTip(
        "A timeline of what the assistant heard, parsed and did.\n"
        "It is its own always-on-top window, so it shows commands you gave\n"
        "from your phone while you were in another app.")
    thinking_cb.setChecked(getattr(self._config.ui, "show_thinking", True))
    assistant.addWidget(thinking_cb)

    thinking_row = QHBoxLayout()
    thinking_row.addSpacing(20)
    thinking_row.addWidget(QLabel("Park it in the"))
    thinking_corner_combo = QComboBox()
    for _label, _value in (("bottom right", "bottom-right"), ("bottom left", "bottom-left"),
                           ("top right", "top-right"), ("top left", "top-left")):
        thinking_corner_combo.addItem(_label, _value)
    _idx = thinking_corner_combo.findData(
        getattr(self._config.ui, "thinking_corner", "bottom-right"))
    thinking_corner_combo.setCurrentIndex(_idx if _idx >= 0 else 0)
    thinking_row.addWidget(thinking_corner_combo)
    thinking_row.addWidget(QLabel("of the screen"))
    thinking_row.addStretch(1)
    assistant.addLayout(thinking_row)

    def _thinking_toggled(on: bool) -> None:
        thinking_corner_combo.setEnabled(on)
    thinking_cb.toggled.connect(_thinking_toggled)
    _thinking_toggled(thinking_cb.isChecked())

    confirm_cb = QCheckBox("Check doubted words with me before acting")
    confirm_cb.setToolTip(
        "When the vocabulary isn't sure it heard a word right, show the\n"
        "transcription for a quick fix before anything is executed.\n"
        "Off: act on the best guess (you can still tap a word to fix it).")
    confirm_cb.setChecked(bool(getattr(getattr(self._config, "engine", None),
                                       "confirm_transcript", False)))
    assistant.addWidget(confirm_cb)

    vocab_btn = QPushButton(icons.icon("vocab"), "Vocabulary && Assistant Log…")
    vocab_btn.setToolTip("Teach the assistant names and words it mishears; review recent commands")
    vocab_btn.setCursor(Qt.CursorShape.PointingHandCursor)

    def _open_vocab():
        from assistant.calendar_ui.vocab_dialog import VocabDialog
        VocabDialog(self, pipeline=self._pipeline).exec()
    vocab_btn.clicked.connect(_open_vocab)

    review_btn = QPushButton(icons.icon("thumbs_up"), "Review Commands…")
    review_btn.setToolTip("Say whether recent voice commands did the right thing — the assistant learns from it")
    review_btn.setCursor(Qt.CursorShape.PointingHandCursor)

    def _open_review():
        from assistant.calendar_ui.review_dialog import ReviewDialog
        ReviewDialog(self, dark=self._dark).exec()
        _refresh_review_label()

    def _refresh_review_label():
        try:
            from assistant.calendar_ui.review_dialog import unreviewed
            n = len(unreviewed(limit=50))
        except Exception:
            n = 0
        review_btn.setText(f"Review Commands… ({n})" if n else "Review Commands…")

    review_btn.clicked.connect(_open_review)
    _refresh_review_label()

    colors_btn = QPushButton(icons.icon("corrected"), "Event Colours && Categories…")
    colors_btn.setToolTip("Categories, their colours and the keywords that pick them")
    colors_btn.setCursor(Qt.CursorShape.PointingHandCursor)

    def _open_categories():
        from assistant.calendar_ui.categories_dialog import CategoriesDialog
        if CategoriesDialog(self, dark=self._dark).exec():
            self.refresh_calendar()
    colors_btn.clicked.connect(_open_categories)

    for btn in (vocab_btn, review_btn, colors_btn):
        assistant.addWidget(btn)

    layout.addStretch(1)
    # Test & Save
    btn_layout = QHBoxLayout()
    test_btn = QPushButton("Test Audio")
    def run_test():
        if mute_cb.isChecked():
            self.show_toast("Muted. Uncheck to test.")
            return
        import threading
        threading.Thread(target=lambda: subprocess.Popen(
            ["say", "-v", voice_combo.currentText(), "-r", str(speed_spin.value()), "Hello, I am ready."],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        ), daemon=True).start()
    test_btn.clicked.connect(run_test)
    btn_layout.addWidget(test_btn)

    save_btn = QPushButton("Save Config")
    save_btn.setDefault(True)
    def save_config():
        self._pipeline._confirmer.level = 0 if auto_cb.isChecked() else 1
        self._pipeline._tts.mute = mute_cb.isChecked()
        self._pipeline._tts.rate = speed_spin.value()
        self._pipeline._tts.voice = voice_combo.currentText()
        # Parse event keywords and stop phrases from text fields
        raw_keywords = [k.strip() for k in keywords_edit.text().split(",") if k.strip()]
        self._config.nlu.event_keywords = raw_keywords
        raw_phrases = [p.strip() for p in stop_phrases_edit.text().split(",") if p.strip()]
        self._config.audio.stop_phrases = raw_phrases
        self._config.audio.event_separator = sep_edit.text().strip()
        self._config.hebrew_calendar.display_mode = hebrew_mode_combo.currentData()
        self._config.hebrew_calendar.show_holidays = hebrew_holidays_cb.isChecked()
        self._config.hebrew_calendar.israel_holidays = hebrew_israel_cb.isChecked()
        # Persist — one section-scoped, comment-preserving write
        # (assistant/config_store). Each setting names its section, so a
        # `rate:` under tts can never clobber a rate elsewhere, and keys
        # missing from an older config are inserted instead of dropped.
        try:
            from assistant.config_store import set_values
            ok = set_values({
                "": {"confirmation_level": 0 if auto_cb.isChecked() else 1,
                     "theme": theme_combo.currentText().lower()},
                "tts": {"mute": mute_cb.isChecked(),
                        "voice": voice_combo.currentText(),
                        "rate": speed_spin.value()},
                "ui": {"font_month": month_spin.value(),
                       "font_week": week_spin.value(),
                       "font_day": day_spin.value(),
                       "font_tasks": tasks_spin.value(),
                       "font_coursework": coursework_spin.value(),
                       "compact_ui": compact_cb.isChecked(),
                       "accent_color": accent_state["hex"],
                       "show_coursework": coursework_tab_cb.isChecked(),
                       "show_workout": workout_tab_cb.isChecked(),
                       "show_timer": timer_tab_cb.isChecked(),
                       "show_thinking": thinking_cb.isChecked(),
                       "thinking_corner": thinking_corner_combo.currentData()},
                "audio": {"review_before_send": review_cb.isChecked(),
                          "review_seconds": review_spin.value(),
                          "stop_phrases": raw_phrases,
                          "event_separator": sep_edit.text().strip()},
                "nlu": {"event_keywords": raw_keywords},
                "engine": {"confirm_transcript": confirm_cb.isChecked()},
                "hebrew_calendar": {"display_mode": hebrew_mode_combo.currentData(),
                                    "show_holidays": hebrew_holidays_cb.isChecked(),
                                    "israel_holidays": hebrew_israel_cb.isChecked()},
                # Read by observance.is_enabled() in the API process, which
                # loads config.yaml itself — nothing to apply in-memory here.
                "observance": {"enabled": observance_cb.isChecked()},
            })
            if ok:

                # Apply changes immediately
                self._config.ui.font_month = month_spin.value()
                self._config.ui.font_week = week_spin.value()
                self._config.ui.font_day = day_spin.value()
                self._config.ui.font_tasks = tasks_spin.value()
                self._config.ui.font_coursework = coursework_spin.value()
                self._config.ui.compact_ui = compact_cb.isChecked()
                self._config.ui.accent_color = accent_state["hex"]
                self._config.ui.show_coursework = coursework_tab_cb.isChecked()
                self._config.ui.show_workout = workout_tab_cb.isChecked()
                self._config.ui.show_timer = timer_tab_cb.isChecked()
                # The HUD is a separate process; it notices config.yaml
                # changing and re-reads these itself.
                self._config.ui.show_thinking = thinking_cb.isChecked()
                self._config.ui.thinking_corner = thinking_corner_combo.currentData()
                self._config.audio.review_before_send = review_cb.isChecked()
                self._config.audio.review_seconds = review_spin.value()
                for _mode in ("coursework", "workout", "timer"):
                    _visible = getattr(self._config.ui, f"show_{_mode}")
                    getattr(self, f"_view_btn_{_mode}").setVisible(_visible)
                    if not _visible and self._view_mode == _mode:
                        self._set_view("month")
                _styles.set_accent(accent_state["hex"])
                self._apply_ui_config()
                self._apply_theme(self._dark)

        except Exception as e:
            QMessageBox.critical(self, "Error Saving", f"Could not save config.yaml: {e}")

        self.show_toast("Settings applied!")
        self.refresh_calendar()
        dialog.accept()

    save_btn.clicked.connect(save_config)
    btn_layout.addWidget(save_btn)
    btn_layout.setContentsMargins(18, 10, 18, 14)
    outer.addLayout(btn_layout)

    dialog.exec()

# ------------------------------------------------------------------
# ICS / macOS Calendar import
# ------------------------------------------------------------------

