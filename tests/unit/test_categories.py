"""Event category classifier + neighbour-aware colour."""

import datetime

import pytest

from assistant.actions.calendar import categories as cat


@pytest.fixture(autouse=True)
def _isolated_categories(tmp_path, monkeypatch):
    monkeypatch.setattr(cat, "CATEGORIES_PATH", str(tmp_path / "categories.json"))
    cat._cache = None; cat._mtime = -1.0
    yield
    cat._cache = None; cat._mtime = -1.0


@pytest.mark.parametrize("title,expected", [
    ("Shacharit", "Prayer"),
    ("Mincha at shul", "Prayer"),
    ("Dentist appointment", "Health"),
    ("gym", "Fitness"),
    ("Lunch with Tal", "Social"),
    ("Netivim zoom", "Work"),
    ("NLP lecture", "Study"),
    ("Bagrut prep with Rei", "Study"),
    ("Flight to NYC", "Travel"),
    ("pick up package", "Errand"),
    ("Relax", "Personal"),
    ("", "Personal"),
])
def test_classify(title, expected):
    assert cat.classify(title) == expected


def test_attendees_alone_lean_social():
    assert cat.classify("Sync", attendees=["Ravid"]) == "Meeting"     # real keyword beats "with"
    assert cat.classify("Catch up", attendees="Noa") == "Meeting"


def test_user_category_add_edit_remove():
    c = cat.upsert("Volunteering", color="#112233", alt="#445566", keywords=["soup kitchen", "volunteer"])
    assert c["name"] == "Volunteering" and c["color"] == "#112233"
    assert cat.classify("Volunteer shift at the soup kitchen") == "Volunteering"
    cat.upsert("Volunteering", add_keywords=["Leket"])
    assert "leket" in cat.get("Volunteering")["keywords"]
    assert cat.remove("Volunteering")
    assert cat.get("Volunteering") is None
    assert cat.classify("volunteer") == "Personal"


def test_personal_cannot_be_removed_and_bad_color_rejected():
    assert not cat.remove("Personal")
    with pytest.raises(ValueError):
        cat.upsert("X", color="red")


def test_pick_color_avoids_neighbours():
    primary, alt = cat.color_for("Social")
    assert cat.pick_color("Social", []) == primary
    assert cat.pick_color("Social", [primary]) == alt
    third = cat.pick_color("Social", [primary, alt])
    assert third not in (primary, alt) and third.startswith("#") and len(third) == 7


def test_db_assigns_category_and_alternating_colours(tmp_path, monkeypatch):
    monkeypatch.setenv("MACALENDAR_DB", str(tmp_path / "cal.db"))
    from assistant.db import CalendarDB
    db = CalendarDB()
    day = "2026-08-27"
    db.create_event_from_dict({"title": "Lunch with Tal", "date": day, "start_time": "12:00", "end_time": "13:00"})
    db.create_event_from_dict({"title": "Coffee with Noa", "date": day, "start_time": "13:00", "end_time": "14:00"})
    db.create_event_from_dict({"title": "Dentist", "date": day, "start_time": "16:00", "end_time": "17:00", "color": "#123456"})
    ev = {e["title"]: e for e in db.get_events_for_day(datetime.date(2026, 8, 27))}
    social, social_alt = cat.color_for("Social")
    assert ev["Lunch with Tal"]["category"] == "Social" and ev["Lunch with Tal"]["color"] == social
    assert ev["Coffee with Noa"]["color"] == social_alt            # neighbour had the primary
    assert ev["Dentist"]["category"] == "Health" and ev["Dentist"]["color"] == "#123456"   # explicit colour kept
    assert db.recategorise_all(force=False) == 0                    # nothing left on defaults
    assert db.recategorise_all(force=True) == 3
    ev = {e["title"]: e for e in db.get_events_for_day(datetime.date(2026, 8, 27))}
    assert ev["Dentist"]["color"] == cat.color_for("Health")[0]
