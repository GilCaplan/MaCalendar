"""AgendaView — day-grouped rows in date order, clicked not called (house rule)."""

from __future__ import annotations

import datetime

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from assistant.calendar_ui.agenda_view import AgendaView, _DayHeader, _EventRow  # noqa: E402
from assistant.db import CalendarDB  # noqa: E402

TODAY = datetime.date.today()


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _make_db(tmp_path) -> CalendarDB:
    return CalendarDB(path=str(tmp_path / "agenda_test.db"))


def _seed(db: CalendarDB, title: str, date: datetime.date,
          start: str = "10:00", end: str = "11:00", location: str = "") -> int:
    return db.create_event_from_dict({
        "title": title, "date": date.isoformat(),
        "start_time": start, "end_time": end,
        "attendees": "", "location": location, "description": "",
        "recurrence": "", "recurrence_end": "",
    })


def _list_widgets(view: AgendaView) -> list:
    """The list's widgets in layout (i.e. render) order."""
    out = []
    for i in range(view._list_layout.count()):
        w = view._list_layout.itemAt(i).widget()
        if w is not None:
            out.append(w)
    return out


def _shown(view: AgendaView, qapp) -> AgendaView:
    view.resize(640, 480)
    view.show()
    qapp.processEvents()
    return view


def test_rows_and_headers_render_in_date_order(qapp, tmp_path):
    db = _make_db(tmp_path)
    # Inserted deliberately out of order — the view must sort, not echo.
    _seed(db, "Far checkup", TODAY + datetime.timedelta(days=10))
    _seed(db, "Evening run", TODAY, start="18:00", end="19:00")
    _seed(db, "Dentist", TODAY + datetime.timedelta(days=3), location="Clinic")
    _seed(db, "Morning daf", TODAY, start="07:00", end="08:00")
    # Outside the 30-day window in both directions — must not render.
    _seed(db, "Too far", TODAY + datetime.timedelta(days=40))
    _seed(db, "Yesterday", TODAY - datetime.timedelta(days=1))

    view = _shown(AgendaView(db), qapp)
    widgets = _list_widgets(view)
    headers = [w for w in widgets if isinstance(w, _DayHeader)]
    rows = [w for w in widgets if isinstance(w, _EventRow)]

    # One header per day that has events, in date order, no empty-day headers.
    assert [h.date for h in headers] == [
        TODAY, TODAY + datetime.timedelta(days=3), TODAY + datetime.timedelta(days=10)]
    assert headers[0].text().startswith("Today")

    # Rows sorted by day, and by start time within the day.
    assert [r.event["title"] for r in rows] == [
        "Morning daf", "Evening run", "Dentist", "Far checkup"]
    titles = {w.text() for w in widgets if isinstance(w, _DayHeader)}
    assert not any("Too far" in t or "Yesterday" in t for t in titles)

    # Interleaving: each row sits under its own day's header.
    kinds = ["H" if isinstance(w, _DayHeader) else "R" for w in widgets
             if isinstance(w, (_DayHeader, _EventRow))]
    assert kinds == ["H", "R", "R", "H", "R", "H", "R"]

    # Row content: times, and location when present.
    dentist = next(r for r in rows if r.event["title"] == "Dentist")
    assert dentist._time_label.text() == "10:00–11:00"
    assert "Clinic" in dentist._location_label.text()

    # The empty state stays hidden when there are events.
    assert not view._empty_label.isVisible()


def test_clicking_a_row_emits_event_clicked(qapp, tmp_path):
    db = _make_db(tmp_path)
    _seed(db, "Shiur", TODAY + datetime.timedelta(days=1))
    dentist_id = _seed(db, "Dentist", TODAY + datetime.timedelta(days=3))

    view = _shown(AgendaView(db), qapp)
    fired: list[dict] = []
    view.event_clicked.connect(fired.append)

    row = next(r for r in _list_widgets(view)
               if isinstance(r, _EventRow) and r.event["title"] == "Dentist")
    QTest.mouseClick(row, Qt.MouseButton.LeftButton)

    assert len(fired) == 1
    assert fired[0]["id"] == dentist_id
    assert fired[0]["title"] == "Dentist"


def test_empty_db_shows_empty_state(qapp, tmp_path):
    db = _make_db(tmp_path)
    view = _shown(AgendaView(db), qapp)
    assert view._empty_label.isVisible()
    assert "Nothing in the next 30 days" in view._empty_label.text()
    assert not view._scroll.isVisible()
    assert [r for r in _list_widgets(view) if isinstance(r, _EventRow)] == []


def test_set_start_date_moves_the_window(qapp, tmp_path):
    db = _make_db(tmp_path)
    _seed(db, "Way out", TODAY + datetime.timedelta(days=45))

    view = _shown(AgendaView(db), qapp)
    assert view._empty_label.isVisible()  # 45 days out is beyond the window

    view.set_start_date(TODAY + datetime.timedelta(days=30))
    qapp.processEvents()
    rows = [r for r in _list_widgets(view) if isinstance(r, _EventRow)]
    assert [r.event["title"] for r in rows] == ["Way out"]
    assert not view._empty_label.isVisible()
