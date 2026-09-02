"""The words people actually write, not the words for the activity.

Half the tasks on this calendar had no tag, and the keyword inferrer could
name one of the twelve. The reason was uniform: the lists knew the word for
the *errand* — "groceries", "supermarket", "shuk" — and nothing about what
ends up in the basket. A task that says "zucchini" is a shopping list of one.

The same gap on the calendar side: the Fitness list knew "run" and "gym" but
not "km", "threshold", "strides" or "5 × 400 m", which is what a training plan
is actually written in.

These are prebuilt because they are true for anybody. Words true only for one
person — a course called Haxaga, a task called "Close Malag" — are deliberately
absent: those need confirming, not guessing.
"""
from __future__ import annotations

import pytest

from assistant.actions.calendar.categories import classify
from assistant.actions.todo.tagging import infer_tag


# --------------------------------------------------------------- groceries

@pytest.mark.parametrize("title", [
    "zucchini", "Canola oil", "gatorade", "buy cold brew", "buy pepsi",
    "buy dr. brown", "almond milk", "sweet potato", "frozen peas",
    "sparkling water", "cream cheese", "bagels",
])
def test_a_single_item_is_a_shopping_list_of_one(title):
    assert infer_tag(title) == "Groceries"


@pytest.mark.parametrize("title", [
    "buy a gift for Tamar",       # a purchase, not a grocery
    "pay rent",
    "book the driving test",
    "submit NLP homework",
])
def test_ordinary_tasks_are_not_swept_into_groceries(title):
    """The list is long, so the risk it introduces is over-capture."""
    assert infer_tag(title) != "Groceries"


@pytest.mark.parametrize("title, tag", [
    ("pick up the package", "Errands"),
    ("call the dentist", "Errands"),
    ("submit NLP homework", "Coursework"),
])
def test_the_other_tags_still_work(title, tag):
    assert infer_tag(title) == tag


# ----------------------------------------------------------------- fitness

@pytest.mark.parametrize("title", [
    "Easy 8 km", "Long 11 km", "Threshold 9 km", "Speed 5 × 400 m",
    "Easy 5 km + strides", "Threshold 30 min", "Speed 4 × 1000 m",
    "Gym / Calisthenics",
])
def test_a_training_plan_reads_as_exercise(title):
    assert classify(title) == "Fitness"


@pytest.mark.parametrize("title, expected", [
    ("Mincha Maariv", "Prayer"),
    ("Shacharit", "Prayer"),
    ("Kabbalat Shabbat", "Prayer"),
    ("Shabbat lunch", "Shabbat Meal"),
    ("dentist appointment", "Health"),
    ("meeting with Tal", "Meeting"),
    ("lunch with Tal", "Social"),
])
def test_the_training_words_do_not_capture_everything_else(title, expected):
    assert classify(title) == expected


# ------------------------------------------------------- title beats notes

def test_the_title_outweighs_a_note_about_the_day():
    """The planner appends observance notes to the description, so a run on a
    Friday carried "Erev Shabbat" underneath it. Scored equally, two words
    about *when* beat the title's statement of *what*, and the same session
    landed in different categories depending on the date it fell on."""
    assert classify("Threshold 9 km", "", "",
                    "2 km w/u · 2 × 10 min @ 4:40 · 2 km c/d\nErev Shabbat") == "Fitness"
    assert classify("Long 15 km", "", "", "15 km easy\nErev Shabbat") == "Fitness"


def test_a_description_still_decides_when_the_title_says_nothing():
    """Weighting the title must not silence the description entirely — a
    title that names nothing should still be classifiable."""
    assert classify("event", "", "", "shacharit and mincha at the shul") == "Prayer"
