"""First-run vocabulary interview.

A short set of questions that seed the personal vocabulary with the names and
words speech-to-text is most likely to mangle for *this* user — people, places,
religious/cultural terms, courses. Answers are stored only in the local
vocab.json (~/.assistant_tools), never in the repository.

Presets are opt-in packs of words the user can switch on wholesale; the
questions are free text (comma separated), one list per question.
"""

from __future__ import annotations

from typing import Any

# Each question: id, prompt, hint, placeholder examples.
QUESTIONS: list[dict[str, Any]] = [
    {"id": "people", "question": "Who do you talk about most?",
     "hint": "Family, partner, friends, pets — first names the assistant should always get right.",
     "examples": ["Kyra", "Ima", "Abba", "Saba", "Savta"]},
    {"id": "places", "question": "Places you go to regularly?",
     "hint": "Cities, neighbourhoods, gyms, restaurants, friends' homes.",
     "examples": ["Technion", "Haifa", "Edo's", "Tel Aviv"]},
    {"id": "religious", "question": "Prayer, synagogue and Shabbat words you use?",
     "hint": "Anything you'd schedule around — services, learning, meals.",
     "examples": ["Mincha", "Maariv", "Shacharit", "Kiddush", "Havdalah", "Shiur"]},
    {"id": "institutions", "question": "Schools, courses, workplaces, teams?",
     "hint": "Course names/numbers, professors, companies, units.",
     "examples": ["Modern Vision", "Eurovision course", "Miluim"]},
    {"id": "hebrew", "question": "Hebrew or Yiddish words you mix into English?",
     "hint": "Words you say as-is: Yalla, Balagan, Achi, Beseder…",
     "examples": ["Yalla", "Balagan", "Beseder", "Achi"]},
    {"id": "other", "question": "Anything else it keeps mishearing?",
     "hint": "Brand names, apps, nicknames, slang.",
     "examples": []},
]

PRESETS: list[dict[str, Any]] = [
    {"id": "tefillah", "label": "Prayer & Shabbat",
     "words": ["Shacharit", "Mincha", "Maariv", "Minchat Maariv", "Shabbat", "Erev Shabbat",
               "Motzei Shabbat", "Kiddush", "Havdalah", "Kabbalat Shabbat", "Seudah Shlishit",
               "Beit Knesset", "Shul", "Minyan", "Shiur", "Daf Yomi", "Chavruta", "Tefillin",
               "Rosh Chodesh", "Selichot", "Musaf", "Hallel"]},
    {"id": "chagim", "label": "Holidays",
     "words": ["Rosh Hashanah", "Yom Kippur", "Sukkot", "Simchat Torah", "Shemini Atzeret",
               "Chanukah", "Purim", "Pesach", "Seder", "Chol Hamoed", "Lag BaOmer", "Shavuot",
               "Tisha B'Av", "Yom HaZikaron", "Yom HaAtzmaut", "Yom Yerushalayim", "Erev Chag",
               "Tu BiShvat", "Fast of Esther"]},
    {"id": "israel", "label": "Israeli life",
     "words": ["Technion", "Haifa", "Tel Aviv", "Jerusalem", "Yerushalayim", "Herzliya", "Jerusalem",
               "Beer Sheva", "Netanya", "Modi'in", "Miluim", "Tzahal", "Kupat Cholim", "Misrad",
               "Rav-Kav", "Shuk", "Machane Yehuda", "Yalla", "Beseder", "Balagan", "Sababa", "Achi",
               "Chevre", "Ulpan", "Bituach Leumi"]},
    {"id": "family", "label": "Family words (Hebrew)",
     "words": ["Ima", "Abba", "Saba", "Savta", "Achot", "Ach", "Dod", "Doda", "Mishpacha"]},
    {"id": "simcha", "label": "Life events",
     "words": ["Bar Mitzvah", "Bat Mitzvah", "Brit Milah", "Chuppah", "Sheva Brachot", "Shiva",
               "Yahrzeit", "Aufruf", "L'chaim", "Simcha", "Kiddush Levana"]},
]


def payload(store) -> dict[str, Any]:
    """What the client renders: questions, presets, and current status."""
    existing = {e.word.lower() for e in store.entries}
    return {
        "done": bool(getattr(store, "onboarded", False)),
        "questions": QUESTIONS,
        "presets": [{**p, "already": sum(w.lower() in existing for w in p["words"])} for p in PRESETS],
        "word_count": len(existing),
    }


def apply(store, answers: dict[str, list[str]] | None, presets: list[str] | None,
          mark_done: bool = True) -> dict[str, Any]:
    """Add all answered words + selected preset packs. Returns counts."""
    added = 0
    words: list[str] = []
    for q in QUESTIONS:
        for w in (answers or {}).get(q["id"], []) or []:
            w = str(w).strip().strip(",")
            if w:
                words.append(w)
    chosen = set(presets or [])
    for p in PRESETS:
        if p["id"] in chosen:
            words.extend(p["words"])
    before = {e.word.lower() for e in store.entries}
    for w in words:
        if w.lower() not in before:
            store.add_word(w)
            before.add(w.lower())
            added += 1
    if mark_done:
        store.set_onboarded(True)
    return {"added": added, "total": len(store.entries), "done": store.onboarded}
