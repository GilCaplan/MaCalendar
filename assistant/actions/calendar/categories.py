"""Event categories → colours.

Every event gets a category (Work, Study, Meeting, Social, Family, Prayer,
Fitness, Health, Errand, Meal, Travel, Personal) from a small deterministic
classifier over its title / attendees / location / description: category
keyword lists (English + the user's Hebrew/Israeli terms), names from the
personal vocabulary count as Social/Meeting, and unknown → Personal (the
"default if unsure" category). Each category has a colour and a secondary
shade; when two events sit next to each other on the same day with the same
colour, the second one takes the shade so neighbours are never identical.

Users can add/remove/rename categories, change colours and keywords; overrides
live in ~/.assistant_tools/categories.json (local only).
"""

from __future__ import annotations

import json
import os
import re
import threading
from typing import Any

# MACALENDAR_CATEGORIES: scratch override for tests (see MACALENDAR_DB).
CATEGORIES_PATH = os.environ.get("MACALENDAR_CATEGORIES") or os.path.expanduser("~/.assistant_tools/categories.json")

# name, primary colour, alternate shade, keywords (lower-case, substring match on word boundaries)
DEFAULTS: list[dict[str, Any]] = [
    {"name": "Work", "color": "#3b82f6", "alt": "#1d4ed8", "keywords": [
        "work", "office", "shift", "night shift", "job", "client", "standup", "stand-up", "sprint", "deploy",
        "interview", "netivim", "ta session", "teaching", "tutoring", "checkpoint", "hw checking", "grading", "grades"]},
    {"name": "Study", "color": "#8b5cf6", "alt": "#6d28d9", "keywords": [
        "class", "lecture", "seminar", "course", "exam", "test", "quiz", "homework", "hw", "study", "studying", "lab",
        "tutorial", "haxaga", "tavlin", "nlp", "robotics", "ethics", "diffusion", "cognition", "eurovision", "euroteq",
        "moed", "bagrut", "project meeting", "thesis", "semester", "technion", "university", "campus", "office hours"]},
    {"name": "Meeting", "color": "#f59e0b", "alt": "#b45309", "keywords": [
        "meeting", "meet", "call", "zoom", "sync", "1:1", "one on one", "catch up", "catch-up", "review", "demo",
        "presentation", "planning", "talk with", "chat with", "discussion"]},
    # The three seudot and their relatives scattered across three categories —
    # "Shabbat lunch" scored Social, "kiddush" and "seudah shlishit" scored
    # Prayer, "melave malka" matched nothing and fell to Personal. One weekly
    # fixture in three colours. Multi-word keywords score highest (2.0 + 0.2
    # per word) so "shabbat lunch" beats the bare "lunch" that sent it to
    # Social, and the phrases here are specific enough not to steal an
    # ordinary weekday meal.
    {"name": "Shabbat Meal", "color": "#c084fc", "alt": "#8b5cf6", "keywords": [
        "shabbat meal", "shabbat lunch", "shabbat dinner", "shabbos meal",
        "shabbos lunch", "shabbos dinner", "friday night dinner",
        "friday night meal", "shabbat seudah", "seudah", "seuda", "seudat",
        "seudah shlishit", "shalosh seudos", "shalosh seudot", "kiddush",
        "melave malka", "melaveh malka", "melava malka", "chag meal",
        "yom tov meal", "yom tov lunch", "chag lunch", "chag dinner",
        "break-fast", "break fast", "seudat mitzvah"]},
    {"name": "Social", "color": "#ec4899", "alt": "#be185d", "keywords": [
        "dinner", "lunch", "coffee", "drinks", "beer", "pub", "bar", "party", "pregame", "pizza", "bbq", "barbecue",
        "hangout", "hang out", "movie", "cinema", "concert", "show", "game night", "bowling", "birthday", "bday",
        "wedding", "sheva brachot", "date", "kems", "french bakery", "golda", "friends", "with"]},
    {"name": "Family", "color": "#f97316", "alt": "#c2410c", "keywords": [
        "family", "ima", "abba", "mom", "mum", "dad", "sister", "brother", "saba", "savta", "grandma", "grandpa",
        "aunt", "uncle", "cousin", "parents", "home", "visit", "tamar"]},
    {"name": "Prayer", "color": "#14b8a6", "alt": "#0f766e", "keywords": [
        "shacharit", "mincha", "maariv", "minyan", "shul", "synagogue", "beit knesset", "kiddush", "havdalah",
        "shabbat", "shabbos", "tfila", "tefilla", "davening", "daven", "shiur", "limud", "torah", "daf yomi",
        "chavruta", "kabbalat", "seudah", "megillah", "selichot", "chag", "erev", "motzei", "kippur", "rosh hashanah",
        "sukkot", "pesach", "purim", "chanukah", "shavuot", "yahrzeit", "leyning", "kol nidre", "fast"]},
    # The training vocabulary was the biggest single gap in this list: a third
    # of the calendar fell through to Personal, and twelve of those thirteen
    # events were runs — "Easy 8 km", "Long 11 km", "Easy 5 km + strides".
    # The words a runner actually writes down are distances, paces and session
    # types, and none of them were here.
    {"name": "Fitness", "color": "#22c55e", "alt": "#15803d", "keywords": [
        "gym", "workout", "run", "running", "jog", "swim", "swimming", "tennis", "football", "soccer", "basketball",
        "cycling", "bike", "ride", "hike", "yoga", "pilates", "training", "race", "sportplex", "match", "pushups",
        # distance and session shorthand
        "km", "k run", "5k", "10k", "half marathon", "marathon", "mile", "miles",
        "easy run", "long run", "recovery run", "shakeout", "strides", "tempo",
        "threshold", "intervals", "interval", "fartlek", "time trial", "reps",
        "400m", "800m", "1000m", "400 m", "800 m", "1000 m", "1k reps",
        "hill repeats", "negative split", "speed", "speed session", "w/u", "c/d",
        # strength and the words this plan uses for it
        "calisthenics", "lifting", "squat", "squats", "deadlift", "bench",
        "pull-up", "pull-ups", "push-up", "push-ups", "core", "mobility",
        "stretch", "stretching", "warm-up", "cool-down", "cooldown"]},
    {"name": "Health", "color": "#ef4444", "alt": "#b91c1c", "keywords": [
        "doctor", "dentist", "dental", "clinic", "kupat cholim", "maccabi", "clalit", "meuhedet", "appointment",
        "checkup", "check-up", "blood test", "vaccine", "physio", "therapy", "pharmacy", "hospital", "optician"]},
    {"name": "Errand", "color": "#a16207", "alt": "#713f12", "keywords": [
        "pick up", "pickup", "drop off", "package", "parcel", "post office", "bank", "leumi", "hapoalim", "misrad",
        "bituach leumi", "rav-kav", "groceries", "shopping", "supermarket", "super", "shuk", "laundry", "car",
        "garage", "mechanic", "haircut", "barber", "repair", "return"]},
    {"name": "Meal", "color": "#eab308", "alt": "#a16207", "keywords": [
        "breakfast", "brunch", "meal", "eat", "cook", "cooking", "bake", "restaurant", "shnitzel", "schnitzel",
        "trattoria", "food"]},
    {"name": "Travel", "color": "#06b6d4", "alt": "#0e7490", "keywords": [
        "flight", "fly", "flying", "airport", "train", "bus", "drive to", "trip", "travel", "hotel", "vacation",
        "holiday", "abroad", "check-in", "checkin", "taxi", "gett", "uber", "ben gurion"]},
    {"name": "Personal", "color": "#64748b", "alt": "#475569", "keywords": []},   # default
]

_lock = threading.RLock()
_cache: dict[str, Any] | None = None
_mtime = -1.0


def _load() -> dict[str, Any]:
    """Merged categories: defaults + user overrides (added/removed/edited)."""
    global _cache, _mtime
    with _lock:
        try:
            m = os.path.getmtime(CATEGORIES_PATH)
        except OSError:
            m = -1.0
        if _cache is not None and m == _mtime:
            return _cache
        data = {"categories": [dict(c, keywords=list(c["keywords"])) for c in DEFAULTS], "removed": []}
        if m >= 0:
            try:
                with open(CATEGORIES_PATH, encoding="utf-8") as f:
                    user = json.load(f)
                by = {c["name"]: c for c in data["categories"]}
                for c in user.get("categories", []):
                    name = str(c.get("name", "")).strip()
                    if not name:
                        continue
                    if name in by:
                        by[name].update({k: v for k, v in c.items() if k in ("color", "alt", "keywords", "name")})
                    else:
                        data["categories"].append({"name": name, "color": c.get("color", "#64748b"),
                                                   "alt": c.get("alt", c.get("color", "#475569")),
                                                   "keywords": list(c.get("keywords", [])), "custom": True})
                removed = set(user.get("removed", []))
                data["categories"] = [c for c in data["categories"] if c["name"] not in removed or c["name"] == "Personal"]
                data["removed"] = sorted(removed)
            except Exception:
                pass
        _cache, _mtime = data, m
        return data


def _save(data: dict[str, Any]) -> None:
    global _cache, _mtime
    with _lock:
        os.makedirs(os.path.dirname(CATEGORIES_PATH), exist_ok=True)
        tmp = CATEGORIES_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CATEGORIES_PATH)
        _cache = None; _mtime = -1.0


# ------------------------------------------------------------------ public

def all_categories() -> list[dict[str, Any]]:
    return [dict(c) for c in _load()["categories"]]


def get(name: str) -> dict[str, Any] | None:
    for c in _load()["categories"]:
        if c["name"].lower() == (name or "").lower():
            return dict(c)
    return None


def upsert(name: str, color: str | None = None, alt: str | None = None,
           keywords: list[str] | None = None, add_keywords: list[str] | None = None) -> dict[str, Any]:
    name = name.strip()
    if not name:
        raise ValueError("category name required")
    if color and not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise ValueError("color must be #rrggbb")
    data = _load()
    user = {"categories": [], "removed": list(data.get("removed", []))}
    if os.path.exists(CATEGORIES_PATH):
        try:
            with open(CATEGORIES_PATH, encoding="utf-8") as f:
                user = json.load(f)
        except Exception:
            pass
    user.setdefault("categories", []); user.setdefault("removed", [])
    entry = next((c for c in user["categories"] if c.get("name", "").lower() == name.lower()), None)
    if entry is None:
        entry = {"name": name}; user["categories"].append(entry)
    if color: entry["color"] = color
    if alt: entry["alt"] = alt
    if keywords is not None: entry["keywords"] = [k.strip().lower() for k in keywords if k.strip()]
    if add_keywords:
        base = get(name) or {}
        entry["keywords"] = sorted(set(entry.get("keywords", base.get("keywords", []))) | {k.strip().lower() for k in add_keywords if k.strip()})
    if name in user["removed"]:
        user["removed"].remove(name)
    _save(user)
    return get(name) or entry


def remove(name: str) -> bool:
    if name.lower() == "personal":
        return False
    data = _load()
    if not any(c["name"].lower() == name.lower() for c in data["categories"]):
        return False
    user = {"categories": [], "removed": []}
    if os.path.exists(CATEGORIES_PATH):
        try:
            with open(CATEGORIES_PATH, encoding="utf-8") as f:
                user = json.load(f)
        except Exception:
            pass
    user.setdefault("categories", []); user.setdefault("removed", [])
    user["categories"] = [c for c in user["categories"] if c.get("name", "").lower() != name.lower()]
    if name not in user["removed"]:
        user["removed"].append(name)
    _save(user)
    return True


def classify(title: str, attendees: str | list | None = None, location: str = "", description: str = "") -> str:
    """Best category name for an event. Deterministic, keyword-scored; 'Personal' if unsure.

    The title counts for more than everything else. It used to count the same,
    which let a note about *when* outvote the statement of *what*: the running
    plan appends observance notes to the description, so "Threshold 9 km" with
    "Erev Shabbat" underneath scored Prayer — the same title landed in two
    different categories depending on which day it fell on.
    """
    def _clean(x) -> str:
        return " " + re.sub(r"[^\w\s'-]", " ", str(x or "").lower()) + " "

    title_text = _clean(title)
    rest = _clean(" ".join(str(x or "") for x in (location, description)))
    att = attendees if isinstance(attendees, list) else [a for a in str(attendees or "").split(",") if a.strip()]
    if att:
        rest = rest[:-1] + " with " + " ".join(att).lower() + " "
    text = title_text + rest
    best, best_score = "Personal", 0.0
    scores: dict[str, float] = {}
    phrase_hit = False          # did any category match a multi-word phrase?
    # A hit in the title is worth more than a hit anywhere else. TITLE_WEIGHT
    # of 2 means a single title keyword beats a single one in a description,
    # while two supporting words in a description can still carry a title that
    # says nothing.
    TITLE_WEIGHT = 3.0
    for c in _load()["categories"]:
        score = 0.0
        for kw in c.get("keywords", []):
            if not kw:
                continue
            k = " " + kw.lower() + " " if " " in kw else None
            for haystack, weight in ((title_text, TITLE_WEIGHT), (rest, 1.0)):
                if k and k in haystack:
                    score += (2.0 + 0.2 * len(kw.split())) * weight
                    phrase_hit = True
                elif re.search(rf"(?<![\w'-]){re.escape(kw.lower())}(?![\w'-])", haystack):
                    score += (1.5 if len(kw) > 3 else 1.0) * weight
        # Generic "with <name>" is a weak Social signal; a real Social keyword beats it.
        if c["name"] == "Social" and score and re.search(r"\bwith\b", text) and score <= 1.0:
            score = 0.6
        scores[c["name"]] = score
        if score > best_score:
            best, best_score = c["name"], score

    # "Shabbat dinner with Ima" scored Social 2.5 against Shabbat Meal 2.4:
    # "dinner" plus the bare word "with", against a phrase that names the
    # occasion exactly. A generic "with" should not outweigh a specific
    # multi-word match, so it is withdrawn once one exists — the guard above
    # only fires when Social has nothing else at all.
    if phrase_hit and best == "Social" and re.search(r"\bwith\b", text):
        social = scores.get("Social", 0.0) - 1.0
        rival = max((v for k, v in scores.items() if k != "Social"), default=0.0)
        if rival > social:
            best = next(k for k, v in scores.items() if v == rival and k != "Social")
            best_score = rival
    # Names of people alone (vocab) → Social unless something stronger matched
    if best_score == 0:
        try:
            from assistant.stt.vocab import get_vocab
            words = {w.lower() for w in re.findall(r"[a-zA-Z][a-zA-Z'-]+", title or "")}
            people = {e.word.lower() for e in get_vocab().entries if len(e.word.split()) == 1 and e.word[:1].isupper()}
            if words & people:
                return "Social"
        except Exception:
            pass
    return best


def color_for(category: str) -> tuple[str, str]:
    c = get(category) or get("Personal") or DEFAULTS[-1]
    return c["color"], c.get("alt", c["color"])


def pick_color(category: str, neighbour_colors: list[str]) -> str:
    """Primary colour unless an adjacent event already uses it → alternate shade."""
    primary, alt = color_for(category)
    taken = {c.lower() for c in neighbour_colors if c}
    if primary.lower() not in taken:
        return primary
    if alt.lower() not in taken:
        return alt
    # both taken: nudge lightness so it is still visibly different
    r, g, b = int(primary[1:3], 16), int(primary[3:5], 16), int(primary[5:7], 16)
    r, g, b = (min(255, int(x * 0.7 + 60)) for x in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"
