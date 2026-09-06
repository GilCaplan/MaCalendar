"""The event dialog's "Share .ics" button — clicked, not called (house rule)."""

from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QFileDialog, QPushButton  # noqa: E402

from assistant.calendar_ui.event_dialog import EventDialog  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_share_button_writes_the_ics_file(qapp, tmp_path, monkeypatch):
    out = tmp_path / "dentist.ics"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(out), "")))
    dlg = EventDialog(event={
        "id": 7, "title": "Dentist", "date": "2026-10-14",
        "start_time": "12:00", "end_time": "12:45",
        "attendees": "", "location": "Clinic", "description": "",
        "color": "#0078d4", "recurrence": "", "recurrence_end": "",
    })
    btn = next(b for b in dlg.findChildren(QPushButton)
               if b.text() == "Share .ics")
    QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
    text = out.read_text()
    assert "SUMMARY:Dentist" in text
    assert "DTSTART:20261014T120000" in text


def test_duplicate_button_sets_the_flag(qapp):
    dlg = EventDialog(event={
        "id": 7, "title": "Gym", "date": "2026-10-14",
        "start_time": "18:30", "end_time": "19:30",
        "attendees": "", "location": "", "description": "",
        "color": "#0078d4", "recurrence": "", "recurrence_end": "",
    })
    btn = next(b for b in dlg.findChildren(QPushButton)
               if b.text() == "Duplicate")
    QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
    assert dlg.duplicate_requested is True
    assert dlg.result() == 1        # accepted - the caller makes the copy


def test_create_mode_has_no_share_button(qapp):
    dlg = EventDialog(event=None)
    assert not any(b.text() == "Share .ics" for b in dlg.findChildren(QPushButton))
