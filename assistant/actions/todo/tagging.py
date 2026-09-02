"""Task tags inferred from the task title.

Voice-created tasks arrived untagged unless "tag mode" was switched on, so a
grocery run landed as a wall of unsorted items. This is the same shape of
classifier as the event categories (`assistant/actions/calendar/categories.py`):
a keyword list per built-in tag, scored over the title, and **no tag at all**
when nothing matches — an untagged task is the honest answer, a wrongly tagged
one has to be undone by hand.

Only names actually in the palette (the `todo_tags` table) are ever returned, so
a tag the user renamed or deleted never comes back. Custom tags get a free ride:
a tag whose own name appears in the title matches without any keyword list.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

# tag name → keywords (lower-case; multi-word entries are matched as phrases and
# score higher, the way categories.classify weights them).
KEYWORDS: dict[str, list[str]] = {
    "Groceries": [
        # the words that name the errand itself
        "groceries", "grocery", "supermarket", "makolet", "shuk",
        "shufersal", "rami levy", "tiv taam", "osher ad",
        # staples
        "milk", "eggs", "bread", "pita", "challah", "cheese", "butter", "yogurt",
        "cottage", "labane", "hummus", "tahini", "techina", "olive oil",
        "flour", "sugar", "salt", "pepper", "spices", "rice", "pasta", "noodles",
        "couscous", "quinoa", "lentils", "chickpeas", "beans", "cereal", "granola",
        "honey", "jam", "peanut butter", "chocolate", "cookies", "snacks", "crackers",
        # produce / protein
        "chicken", "beef", "meat", "steak", "schnitzel", "shnitzel", "turkey", "lamb",
        "fish", "salmon", "tuna", "tofu", "vegetables", "veggies", "fruit", "apples",
        "bananas", "oranges", "lemons", "grapes", "avocado", "tomatoes", "cucumbers",
        "onions", "garlic", "potatoes", "carrots", "lettuce", "salad", "spinach",
        # drinks / household
        "coffee", "tea", "juice", "wine", "beer", "soda", "cola",
        "toilet paper", "paper towels", "napkins", "detergent", "soap", "shampoo",
        "toothpaste", "garbage bags", "trash bags", "dish soap", "tin foil",
        # More of the shopping list itself. The list above named the errand and
        # the staples; half the untagged tasks on this calendar were single
        # items — "zucchini", "Canola oil", "gatorade" — which no amount of
        # words for *shopping* will ever match. These are things anybody buys,
        # so they ship prebuilt; anything specific to one person belongs in
        # their own vocabulary, confirmed rather than assumed.
        "zucchini", "courgette", "eggplant", "aubergine", "squash", "pumpkin",
        "peppers", "broccoli", "cauliflower", "mushrooms", "celery", "corn",
        "peas", "beets", "radish", "cabbage", "leek", "sweet potato", "ginger",
        "parsley", "cilantro", "coriander", "basil", "mint", "dill", "herbs",
        "canola oil", "vegetable oil", "sunflower oil", "sesame oil", "vinegar",
        "ketchup", "mayo", "mayonnaise", "mustard", "soy sauce", "silan",
        "date honey", "zaatar", "paprika", "cumin", "turmeric",
        "cream", "sour cream", "cream cheese", "almond milk", "oat milk",
        "soy milk", "ice cream", "frozen",
        "bagels", "rolls", "buns", "baguette", "cake", "muffins", "pastry",
        "gatorade", "powerade", "pepsi", "coke", "coca-cola", "sprite", "fanta",
        "dr. brown", "dr brown", "cold brew", "espresso", "sparkling water",
        "soda water", "seltzer", "gazoz", "smoothie", "lemonade",
        "nuts", "almonds", "walnuts", "cashews", "pistachios", "raisins",
        "dates", "olives", "pickles", "sauce", "pesto", "salsa",
    ],
    "Coursework": [
        "homework", "hw", "assignment", "problem set", "pset", "essay",
        "lab report", "exam", "midterm", "quiz", "moed", "lecture", "seminar",
        "tutorial", "course", "syllabus", "semester", "thesis", "technion",
        "moodle", "study", "studying", "revise", "revision", "grades", "grading",
        "submission", "nlp", "robotics",
    ],
    "Errands": [
        "pick up", "pickup", "drop off", "dropoff", "post office", "package", "parcel",
        "bank", "leumi", "hapoalim", "atm", "deposit", "misrad", "bituach leumi",
        "rav-kav", "rav kav", "passport", "visa", "license", "renew", "laundry",
        "dry cleaning", "cleaners", "pharmacy", "haircut", "barber", "garage",
        "mechanic", "car wash", "petrol", "repair", "return",
        "appointment", "doctor", "dentist", "clinic",
    ],
    "Work": [
        "work", "office", "shift", "client", "customer", "invoice", "boss", "manager",
        "standup", "stand-up", "sprint", "deploy", "release", "ticket", "jira",
        "pull request", "code review", "interview", "cv", "resume", "salary",
        "payslip", "netivim", "onboarding", "meeting notes", "timesheet",
    ],
}

# Tags that are never inferred: "Personal" is the shrug bucket, and guessing it
# is no better than leaving the task untagged.
_NEVER_INFER = frozenset({"personal"})


def _score(text: str, keywords: Iterable[str]) -> float:
    score = 0.0
    for kw in keywords:
        kw = kw.lower()
        if not kw:
            continue
        if " " in kw:
            if f" {kw} " in text:
                score += 2.0 + 0.2 * len(kw.split())
        elif re.search(rf"(?<![\w'-]){re.escape(kw)}(?![\w'-])", text):
            score += 1.5 if len(kw) > 3 else 1.0
    return score


def infer_tag(title: str, palette: Optional[Iterable[str]] = None) -> Optional[str]:
    """Best tag name for a task title, or None when nothing matches.

    `palette` is the list of tag names that exist; only those can be returned.
    Passing None means "the built-in names" — callers with a DB should pass the
    real palette so renamed/deleted tags are honoured (see `suggest_tags`).
    """
    if not title or not title.strip():
        return None
    names = list(palette) if palette is not None else list(KEYWORDS)
    allowed = {n.lower(): n for n in names if n and n.lower() not in _NEVER_INFER}
    if not allowed:
        return None

    text = " " + re.sub(r"[^\w\s'-]", " ", title.lower()) + " "
    text = re.sub(r"\s+", " ", text)

    # This user's own words come first. The vocabulary already knew "Haxaga"
    # and "Malag" were words they say — it just had nowhere to record what they
    # were *about*, so half their untagged tasks were course work the tagger
    # could not see. A label they set by hand outranks any list that ships with
    # the app: they said Haxaga is a course, so it is, whatever else the
    # sentence looks like.
    try:
        from assistant.stt.vocab import get_vocab
        personal = get_vocab().label_for(title)
        if personal and personal.lower() in allowed:
            return allowed[personal.lower()]
    except Exception:                       # pragma: no cover - defensive
        pass

    best, best_score = None, 0.0
    for tag, keywords in KEYWORDS.items():
        if tag.lower() not in allowed:
            continue
        s = _score(text, keywords)
        if s > best_score:
            best, best_score = allowed[tag.lower()], s

    # A tag whose own name is in the title beats a keyword match — that is the
    # user naming it outright, and it is the only way custom tags can match.
    for lower, name in allowed.items():
        if re.search(rf"(?<![\w'-]){re.escape(lower)}(?![\w'-])", text):
            return name

    return best


def suggest_tags(title: str, palette: Optional[Iterable[str]] = None) -> list[str]:
    """`infer_tag` as a tags list, reading the palette from the DB if not given."""
    if palette is None:
        try:
            from assistant.db import get_db
            palette = [row["name"] for row in get_db().get_tags()]
        except Exception:      # no DB yet (first launch, tests without a store)
            palette = None
    tag = infer_tag(title, palette)
    return [tag] if tag else []


def resolve_tags(names: Iterable[str], palette: Optional[Iterable[str]] = None) -> list[str]:
    """Keep only names that exist in the palette, corrected to its casing.

    The parser and the LLM both propose tag names off the user's own words
    ("put it on the groceries list"); anything that isn't a real tag is dropped
    rather than silently creating a new one.
    """
    if palette is None:
        try:
            from assistant.db import get_db
            palette = [row["name"] for row in get_db().get_tags()]
        except Exception:
            return []
    known = {n.lower(): n for n in palette if n}
    out: list[str] = []
    for n in names or []:
        real = known.get(str(n).strip().lower())
        if real and real not in out:
            out.append(real)
    return out
