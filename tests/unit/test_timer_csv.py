"""Export CSV on the Timer tab's Stats panel.

The button saves exactly what the Stats tiles are aggregating — one row per
session under the current period + timer-checklist filters, plus a TOTAL row
mirroring the Tracked Time / Total Earnings tiles.

House rule: a UI test that never sends a mouse event tests nothing. Every
path here is driven with QTest.mouseClick — the Stats section button, the
period buttons, the Export CSV button — with QFileDialog.getSaveFileName
monkeypatched to hand back a tmp path instead of opening a real dialog.
"""
from __future__ import annotations

import csv
import datetime

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import Qt                       # noqa: E402
from PyQt6.QtTest import QTest                    # noqa: E402
from PyQt6.QtWidgets import QApplication          # noqa: E402

from assistant.calendar_ui import timer_view as tv  # noqa: E402
from assistant.db import CalendarDB                 # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _finished_session(db: CalendarDB, timer_id: int, start: datetime.datetime,
                      hours: float, title: str = "") -> None:
    sid = db.create_timer_session(timer_id, title=title, start_time=start.isoformat())
    db.stop_timer_session(sid, end_time=(start + datetime.timedelta(hours=hours)).isoformat())


@pytest.fixture
def view(qapp, tmp_path):
    """A TimerView over a scratch DB seeded with:

    - "Client A" (work, ₪100/hr): a 2 h session today and a 2 h session
      40 days ago (outside the default Week period)
    - "Reading" (personal, no rate): a 30 min session today
    """
    db = CalendarDB(str(tmp_path / "cal.db"))
    now = datetime.datetime.now().astimezone()

    client = db.create_timer(title="Client A", timer_type="work", hourly_rate=100.0, currency="ILS")
    _finished_session(db, client, now - datetime.timedelta(hours=2), 2.0, title="deep work")
    _finished_session(db, client, now - datetime.timedelta(days=40), 2.0, title="old block")

    reading = db.create_timer(title="Reading", timer_type="personal")
    _finished_session(db, reading, now - datetime.timedelta(minutes=30), 0.5)

    v = tv.TimerView(db)
    v.show()
    QTest.qWaitForWindowExposed(v, 2000)
    QApplication.processEvents()
    yield v
    v.hide()
    v.deleteLater()
    QApplication.processEvents()


def _click(widget) -> None:
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton)
    QApplication.processEvents()


def _export_to(view, monkeypatch, path) -> None:
    monkeypatch.setattr(
        tv.QFileDialog, "getSaveFileName",
        lambda *a, **k: (str(path), "CSV files (*.csv)"),
    )
    _click(view._export_btn)


def _read(path) -> list[list[str]]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.reader(f))


# ------------------------------------------------------------------ export

def test_export_writes_header_sessions_and_totals(view, monkeypatch, tmp_path):
    out = tmp_path / "export.csv"
    _click(view._sect_btn_stats)
    _export_to(view, monkeypatch, out)

    assert out.exists()
    rows = _read(out)
    assert rows[0] == ["project", "start", "end", "duration_hours",
                       "hourly_rate", "currency", "earned"]
    # Default period is Week: the 40-day-old session is excluded, exactly as
    # it is from the tiles → header + 2 sessions + TOTAL.
    assert len(rows) == 4

    by_project = {r[0]: r for r in rows[1:-1]}
    client = by_project["Client A"]
    assert client[3] == "2.0000"
    assert client[4] == "100"
    assert client[5] == "ILS"
    assert client[6] == "200.00"
    # Both timestamps present (session is finished) and ISO-parseable.
    datetime.datetime.fromisoformat(client[1])
    datetime.datetime.fromisoformat(client[2])

    reading = by_project["Reading"]
    assert reading[3] == "0.5000"
    # Personal timer shows no earnings in the view — so none are invented here.
    assert reading[4:7] == ["", "", ""]

    total = rows[-1]
    assert total[0] == "TOTAL"
    assert total[3] == "2.5000"
    assert total[6] == "₪200.00"  # same per-currency format as the tile


def test_export_follows_the_selected_period(view, monkeypatch, tmp_path):
    """Clicking All-time first brings the 40-day-old session into the export,
    just as it brings it into the tiles."""
    out = tmp_path / "export_all.csv"
    _click(view._sect_btn_stats)
    _click(view._period_btn_all)
    _export_to(view, monkeypatch, out)

    rows = _read(out)
    assert len(rows) == 5  # header + 3 sessions + TOTAL
    total = rows[-1]
    assert total[3] == "4.5000"
    assert total[6] == "₪400.00"


def test_cancelling_the_dialog_writes_nothing(view, monkeypatch, tmp_path):
    out = tmp_path / "never_written.csv"
    _click(view._sect_btn_stats)
    monkeypatch.setattr(tv.QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    _click(view._export_btn)
    assert not out.exists()
