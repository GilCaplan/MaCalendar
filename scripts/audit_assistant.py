"""End-to-end audit of the voice assistant: accuracy, latency, self-check.

Runs a generated corpus of ~120 commands through the REAL server path
(POST /voice/text → rule parser → hybrid/LLM → validate → execute →
background self-check) against SCRATCH databases, then writes a Markdown
report with accuracy by area / parse path, latency distributions, and the
"quick answer vs settled answer" story.

    python -m scripts.audit_assistant                 # full corpus
    python -m scripts.audit_assistant --area events   # one area
    python -m scripts.audit_assistant --limit 20      # smoke
    python -m scripts.audit_assistant --audio         # also push a subset through `say` → Whisper
    python -m scripts.audit_assistant --out DOCUMENTATION/ASSISTANT_AUDIT.md

Never touches ~/.assistant_tools/calendar.db — it sets MACALENDAR_DB and
MACALENDAR_MEMORY_DB to temp files before importing the app. The real
vocabulary IS used (that's part of what's being audited).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import statistics
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# --- isolate BEFORE importing the app ------------------------------------
_TMP = tempfile.mkdtemp(prefix="macal_audit_")
os.environ["MACALENDAR_DB"] = os.path.join(_TMP, "calendar.db")
os.environ["MACALENDAR_MEMORY_DB"] = os.path.join(_TMP, "memory.db")

# --- the memory-aware mode -----------------------------------------------
# The audit has always run against an EMPTY command history, which means every
# claim about personalisation has been unmeasured: whether the four retrieved
# examples help at all, whether four is the right number, whether a corrected
# example beats a recent one. None of that can be seen when there is nothing
# to retrieve.
#
# `--memory` replays the corpus against a COPY of the real history, so the
# personalisation layer is actually exercised. Read from argv rather than from
# argparse because these paths are set at import time and argparse runs far too
# late — the same reason the other stores are redirected up here.
_WANT_MEMORY = "--memory" in sys.argv
if _WANT_MEMORY:
    # `--memory-source PATH` replays against a given copy of the history
    # instead of the live one — e.g. a slice with one dominant day held out,
    # to check that a k>0 effect is the user's general style and not one
    # day's particular vocabulary. Defaults to the real file, as before.
    _real_memory = os.path.expanduser("~/.assistant_tools/nlu_memory.db")
    for _i, _arg in enumerate(sys.argv):
        if _arg == "--memory-source" and _i + 1 < len(sys.argv):
            _real_memory = os.path.expanduser(sys.argv[_i + 1])
        elif _arg.startswith("--memory-source="):
            _real_memory = os.path.expanduser(_arg.split("=", 1)[1])
    if os.path.exists(_real_memory):
        import shutil as _sh
        _sh.copyfile(_real_memory, os.environ["MACALENDAR_MEMORY_DB"])
        print(f"memory: replaying against a copy of the real history "
              f"({os.path.getsize(_real_memory) // 1024} KB)")
    else:
        print("memory: --memory given but there is no history to copy")

# `--memory-k N` overrides how many examples are retrieved, which is the whole
# A/B: k=0 answers "is the memory helping at all", and only then is "is four
# the right number" a sensible question to ask.
for _i, _arg in enumerate(sys.argv):
    if _arg == "--memory-k" and _i + 1 < len(sys.argv):
        os.environ["MACALENDAR_MEMORY_K"] = sys.argv[_i + 1]
    elif _arg.startswith("--memory-k="):
        os.environ["MACALENDAR_MEMORY_K"] = _arg.split("=", 1)[1]
os.environ["MACALENDAR_NO_WARMUP"] = "1"
# The trace bus is the durable record the thinking card's History reads back.
# Without this the audit publishes 89 synthetic commands into it on every run,
# and the log of what you actually asked the assistant becomes mostly corpus.
os.environ["MACALENDAR_TRACE_BUS"] = os.path.join(_TMP, "trace_bus.jsonl")

# The audit is meant to run against the REAL vocabulary — that's part of what's
# being measured — but running it must not change it. Work from a copy: the
# same words go in, while the transcripts it replays and any aliases the
# auto-corrector learns from them stay out of the user's personal file.
import shutil as _shutil
for _var, _real, _name in (
        ("MACALENDAR_VOCAB", os.path.expanduser("~/.assistant_tools/vocab.json"), "vocab.json"),
        ("MACALENDAR_CATEGORIES", os.path.expanduser("~/.assistant_tools/categories.json"), "categories.json")):
    _copy = os.path.join(_TMP, _name)
    if os.path.exists(_real):
        _shutil.copyfile(_real, _copy)
    os.environ[_var] = _copy
os.chdir(ROOT)

TODAY = dt.date.today()


def d(offset: int) -> str:
    return (TODAY + dt.timedelta(days=offset)).isoformat()


def next_wd(wd: int, strictly_after: bool = False) -> str:
    days = (wd - TODAY.weekday()) % 7
    if days == 0 and strictly_after:
        days = 7
    return d(days)


WD_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


# ------------------------------------------------------------------ corpus
# Each case: {"area", "shape", "text", "expect": [(action, {field: value})], "seed": [...events]}
# Field checks: date/start_time/end_time exact; title_contains (case-insens);
# recurrence; titles_contain (todo, list of substrings); list_name;
# todo_count (how many task rows the command should leave); tags_contain.

def build_corpus(seed: int = 7) -> list[dict]:
    rnd = random.Random(seed)
    people = ["Ravid", "Tal", "Rei", "Ezra", "Danny", "Yotam", "Ofir", "Adin", "Tamar", "Eitan"]
    places = ["Kems", "the French Bakery", "Golda", "Feldman", "Technion", "Tel Mond", "Jerusalem", "Herzliya"]
    topics = ["the robotics project", "Bagrut prep", "Haxaga", "the NLP seminar", "Netivim", "project funds"]
    religious = ["Mincha", "Maariv", "Shacharit", "Mincha Maariv at shul", "Kiddush", "Limud Torah"]
    C: list[dict] = []

    def ev(text, expect, shape, area="events"):
        C.append({"area": area, "shape": shape, "text": text, "expect": expect})

    # --- events: single -------------------------------------------------
    for p, pl, t in [(people[0], places[0], "14:00"), (people[1], places[1], "09:30"), (people[2], places[2], "18:15")]:
        hh = int(t[:2]); disp = f"{hh if hh <= 12 else hh - 12}{':' + t[3:] if t[3:] != '00' else ''} {'am' if hh < 12 else 'pm'}"
        ev(f"set a meeting tomorrow at {disp} with {p} at {pl}",
           [("create_event", {"date": d(1), "start_time": t, "title_contains": p})], "single/explicit-time")
    ev("dentist appointment on thursday at 9 am", [("create_event", {"date": next_wd(3), "start_time": "09:00", "title_contains": "dentist"})], "single/weekday")
    ev("lunch with Tal at noon on the 19th", [("create_event", {"start_time": "12:00", "title_contains": "Tal"})], "single/day-of-month")
    ev("add gym at 6 am for one hour tomorrow", [("create_event", {"date": d(1), "start_time": "06:00", "end_time": "07:00", "title_contains": "gym"})], "single/duration")
    ev("meeting with Ravid from 3 to 4:30 pm today", [("create_event", {"date": d(0), "start_time": "15:00", "end_time": "16:30"})], "single/range")
    ev("set an event next wednesday at 2pm technion talk regarding project funds",
       [("create_event", {"date": d((7 - TODAY.weekday()) + 2), "start_time": "14:00"})], "single/next-weekday")
    ev("Mincha Maariv at shul tonight at 7:15", [("create_event", {"date": d(0), "start_time": "19:15", "title_contains": "Mincha"})], "single/hebrew-term")
    ev("Limud Torah at Ohel Ari on tuesday at 9 pm", [("create_event", {"date": next_wd(1), "start_time": "21:00", "title_contains": "Limud"})], "single/hebrew-term")
    ev("coffee with Ezra friday morning at 9:15 at the French Bakery",
       [("create_event", {"date": next_wd(4), "start_time": "09:15", "title_contains": "Ezra"})], "single/place")
    ev("driving lesson thursday 8 am", [("create_event", {"date": next_wd(3), "start_time": "08:00", "title_contains": "driving"})], "single/terse")
    ev("schedule a zoom with Guri Karpas about the robotics project on monday at 4:30 pm",
       [("create_event", {"date": next_wd(0), "start_time": "16:30", "title_contains": "Guri"})], "single/full-name")
    ev("book a haircut for tuesday at half past two", [("create_event", {"date": next_wd(1), "start_time": "14:30", "title_contains": "haircut"})], "single/spoken-time")
    ev("set a meeting for me tomorrow at 4pm execute", [("create_event", {"date": d(1), "start_time": "16:00"})], "single/stop-word")
    ev("meeting tomorrow at 2 sorry not 2, 3 pm with Adin for the project",
       [("create_event", {"date": d(1), "start_time": "15:00", "title_contains": "Adin"})], "single/disfluency")

    # --- events: multiple same day ---------------------------------------
    ev("set a meeting tomorrow at 1 pm, another one at 4 pm and then pizza at 6:30 pm tomorrow",
       [("create_event", {"date": d(1), "start_time": "13:00"}), ("create_event", {"date": d(1), "start_time": "16:00"}),
        ("create_event", {"date": d(1), "start_time": "18:30", "title_contains": "pizza"})], "multi/same-day-3")
    ev("walk Kyra the dog at 3:30 pm today and then go to shul for Mincha Maariv at 7:30 pm",
       [("create_event", {"date": d(0), "start_time": "15:30", "title_contains": "Kyra"}),
        ("create_event", {"date": d(0), "start_time": "19:30"})], "multi/same-day-2")
    ev("tomorrow gym at 7 am and a meeting with Tal at 11", [("create_event", {"date": d(1), "start_time": "07:00"}),
        ("create_event", {"date": d(1), "start_time": "11:00", "title_contains": "Tal"})], "multi/same-day-2")
    ev("on thursday I have Shacharit at 6:30 am, a lecture at 10 and dinner with Danny at 8 pm",
       [("create_event", {"date": next_wd(3), "start_time": "06:30"}), ("create_event", {"date": next_wd(3), "start_time": "10:00"}),
        ("create_event", {"date": next_wd(3), "start_time": "20:00", "title_contains": "Danny"})], "multi/same-day-3")
    ev("two events tomorrow, one at four o'clock meeting with Rei and one at seven pm pizza with Ezra",
       [("create_event", {"date": d(1), "start_time": "16:00", "title_contains": "Rei"}),
        ("create_event", {"date": d(1), "start_time": "19:00", "title_contains": "Ezra"})], "multi/same-day-2")

    # --- events: multiple different days ---------------------------------
    ev("meeting with Ravid tomorrow at 2 pm and dentist on thursday at 9 am",
       [("create_event", {"date": d(1), "start_time": "14:00", "title_contains": "Ravid"}),
        ("create_event", {"date": next_wd(3), "start_time": "09:00", "title_contains": "dentist"})], "multi/different-days")
    ev("set lunch with Tal on monday at noon and coffee with Ezra on friday at 9",
       [("create_event", {"date": next_wd(0), "start_time": "12:00"}), ("create_event", {"date": next_wd(4), "start_time": "09:00"})], "multi/different-days")
    ev("gym tomorrow at 6 am, tuesday at 6 am and friday at 6 am",
       [("create_event", {"date": d(1), "start_time": "06:00"}), ("create_event", {"date": next_wd(1), "start_time": "06:00"}),
        ("create_event", {"date": next_wd(4), "start_time": "06:00"})], "multi/different-days-3")

    # --- events: recurring -----------------------------------------------
    ev("schedule gym every monday at 6 am", [("create_event", {"start_time": "06:00", "recurrence": "weekly"})], "recurring/weekly")
    ev("daily Shacharit at 6:30 am", [("create_event", {"start_time": "06:30", "recurrence": "daily"})], "recurring/daily")
    ev("weekly Netivim zoom on wednesdays at 7 pm", [("create_event", {"start_time": "19:00", "recurrence": "weekly"})], "recurring/weekly")

    # --- events: from real failures ---------------------------------------
    # Mined from ~/.assistant_tools/nlu_memory.db (feedback in corrected/rejected,
    # llm/hybrid path — the only path few-shot examples reach). The hand-written
    # corpus above scores 100% on that path in both k=0 and k=4 (ASSISTANT_AUDIT_
    # SUMMARY.md, run 7), so it cannot show whether the examples help. These two
    # reproduced against current code before being added; the ground truth is
    # read straight off what the speaker actually said, not off correction_json
    # (much of that pool turned out to be stale or, for one row, corrupted by
    # the batch-correction bug fixed alongside this).
    ev("set a meeting at 4pm today, but it is only 20 minutes meeting with one moment meeting with reards, "
       "okay, then let's do another meeting from 6 from 6 o'clock to 640 meetings with kids for project defense",
       [("create_event", {"date": d(0), "start_time": "16:00", "end_time": "16:20"}),
        ("create_event", {"date": d(0), "start_time": "18:00", "end_time": "18:40"})], "multi/disfluent-duration")
    ev("a meeting for me tomorrow at two one sorry one pm and four pm and then another one a pizza party at 6.30 pm at edo's",
       [("create_event", {"date": d(1), "start_time": "13:00", "end_time": "14:00"}),
        ("create_event", {"date": d(1), "start_time": "16:00", "end_time": "17:00"}),
        ("create_event", {"date": d(1), "start_time": "18:30", "end_time": "19:30", "title_contains": "pizza"})],
       "multi/self-correction-count")

    # --- tasks -------------------------------------------------------------
    def td(text, expect, shape):
        C.append({"area": "tasks", "shape": shape, "text": text, "expect": expect})
    td("remind me to buy milk", [("create_todo", {"titles_contain": ["milk"]})], "single")
    td("add a task to call the dentist", [("create_todo", {"titles_contain": ["dentist"]})], "single")
    td("add buy milk, eggs and bread to my list", [("create_todo", {"titles_contain": ["milk", "eggs", "bread"], "todo_count": 3})], "multi/same-list")
    # One command, several things to buy: one task each, not a summary task.
    td("i want to buy chicken and rice",
       [("create_todo", {"titles_contain": ["chicken", "rice"], "todo_count": 2, "tags_contain": "Groceries"})], "multi/shared-verb")
    td("remind me to buy chicken, rice and olive oil",
       [("create_todo", {"titles_contain": ["chicken", "rice", "olive oil"], "todo_count": 3})], "multi/shared-verb-3")
    td("remind me to call mom and dad",
       [("create_todo", {"titles_contain": ["mom", "dad"], "todo_count": 2})], "multi/shared-verb-people")
    # …but an "and" inside one errand is not a separator.
    td("remind me to buy a birthday gift for mom and dad",
       [("create_todo", {"titles_contain": ["gift"], "todo_count": 1})], "single/internal-and")
    td("add a task to submit the NLP homework",
       [("create_todo", {"titles_contain": ["NLP"], "tags_contain": "Coursework"})], "single/inferred-tag")
    td("I need to finish the robotics report and email Alon", [("create_todo", {"titles_contain": ["report", "Alon"]})], "multi/same-list")
    td("add tasks: submit the Haxaga grades, prepare Netivim slides, pay rent",
       [("create_todo", {"titles_contain": ["grades", "slides", "rent"]})], "multi/same-list-3")
    td("remind me tomorrow to send the syllabus to Guri", [("create_todo", {"titles_contain": ["syllabus"], "due_date": d(1)})], "single/due-tomorrow")
    td("add task submit NLP homework due friday", [("create_todo", {"titles_contain": ["NLP"], "due_date": next_wd(4)})], "single/due-weekday")
    td("two tasks due tomorrow: buy groceries and return the library book",
       [("create_todo", {"titles_contain": ["groceries", "library"], "due_date": d(1)})], "multi/same-due-date")
    td("add buy a gift for Tamar due thursday and book the driving test due next monday",
       [("create_todo", {"titles_contain": ["gift"], "due_date": next_wd(3)}), ("create_todo", {"titles_contain": ["driving"], "due_date": next_wd(0)})], "multi/different-due-dates")
    td("put milk and bananas on the groceries list",
       [("create_todo", {"titles_contain": ["milk", "bananas"], "todo_count": 2, "tags_contain": "Groceries"})], "multi/tagged")
    td("add to my general list: renew passport", [("create_todo", {"titles_contain": ["passport"], "list_name": "general"})], "single/general-list")
    td("remind me to call Ima", [("create_todo", {"titles_contain": ["Ima"]})], "single/hebrew-name")

    # --- tasks: from real failures -----------------------------------------
    # Same provenance as the events cases above. Ground truth is deliberately
    # conservative (item count and titles only) — the real correction data
    # for this one wasn't clean enough to assert more without guessing.
    td("[TASKS VIEW] i need to buy some groceries, i need rice and chicken, the chicken i need to get "
       "far away, the rice i can get at whole foods",
       [("create_todo", {"titles_contain": ["chicken", "rice"], "todo_count": 2})], "multi/interleaved-clauses")

    # --- update / delete (seeded) ----------------------------------------
    seed_ev = {"title": "Meeting with Tal", "date": d(1), "start_time": "13:00", "end_time": "14:00"}
    seed_ev2 = {"title": "Pizza party", "date": next_wd(4), "start_time": "18:30", "end_time": "19:30"}

    def ud(text, expect, shape, seeds):
        C.append({"area": "update-delete", "shape": shape, "text": text, "expect": expect, "seed": seeds})
    ud("move my 1pm meeting tomorrow to 3pm", [("update_event", {"db_event_start": ("Meeting with Tal", "15:00")})], "update/move-by-time", [seed_ev])
    ud("move the meeting with Tal to 4:30 pm", [("update_event", {"db_event_start": ("Meeting with Tal", "16:30")})], "update/move-by-title", [seed_ev])
    ud("extend the meeting with Tal tomorrow until 3 pm", [("update_event", {"db_event_end": ("Meeting with Tal", "15:00")})], "update/extend", [seed_ev])
    ud("rename the meeting with Tal to robotics sync", [("update_event", {"db_event_title": ("robotics", "13:00")})], "update/rename", [seed_ev])
    ud("delete the pizza party on friday", [("delete_event", {"db_event_absent": "Pizza party"})], "delete/by-title", [seed_ev2])
    ud("cancel my 1 pm meeting tomorrow", [("delete_event", {"db_event_absent": "Meeting with Tal"})], "delete/by-time", [seed_ev])
    ud("move the pizza party to saturday night 8 pm", [("update_event", {"db_event_start": ("Pizza party", "20:00")})], "update/move-day", [seed_ev2])

    # --- queries -----------------------------------------------------------
    for text, scope in [("what do I have on tomorrow", "tomorrow"), ("what's on my schedule today", "today"), ("what do I have this week", "week")]:
        C.append({"area": "query", "shape": f"query/{scope}", "text": text, "expect": [("query_schedule", {})]})

    # --- mixed -------------------------------------------------------------
    C.append({"area": "mixed", "shape": "event+task", "text": "set a meeting with Ravid tomorrow at 2 pm and remind me to buy a gift for him",
              "expect": [("create_event", {"date": d(1), "start_time": "14:00"}), ("create_todo", {"titles_contain": ["gift"]})]})
    C.append({"area": "mixed", "shape": "task+event", "text": "add a task to prepare slides and set a lecture on wednesday at 10 am",
              "expect": [("create_todo", {"titles_contain": ["slides"]}), ("create_event", {"date": next_wd(2), "start_time": "10:00"})]})
    C.append({"area": "mixed", "shape": "3events+task", "text": "tomorrow: Shacharit at 6:30, Haxaga TA at 12, dinner with Ezra at 8 pm, and remind me to pay rent",
              "expect": [("create_event", {"date": d(1), "start_time": "06:30"}), ("create_event", {"date": d(1), "start_time": "12:00"}),
                         ("create_event", {"date": d(1), "start_time": "20:00"}), ("create_todo", {"titles_contain": ["rent"]})]})

    # --- adversarial -------------------------------------------------------
    C.append({"area": "adversarial", "shape": "ambiguous/no-time", "text": "set a meeting with Tal", "expect": [("clarify|create_event", {})]})
    C.append({"area": "adversarial", "shape": "task-not-event", "text": "remind me to call Ravid", "expect": [("create_todo", {"titles_contain": ["Ravid"]})]})
    C.append({"area": "adversarial", "shape": "event-not-task", "text": "remind me about the dentist tomorrow at 9 am", "expect": [("create_event", {"date": d(1), "start_time": "09:00"})]})
    C.append({"area": "adversarial", "shape": "misheard-names", "text": "meet Ravid at the french bakery in Jerusalem after shacharis at 9 am tomorrow",
              "expect": [("create_event", {"date": d(1), "start_time": "09:00", "title_contains": "Ravid"})]})
    C.append({"area": "adversarial", "shape": "past-tense-noise", "text": "I had a meeting today at 8:30 pm with Nurit to work on the project",
              "expect": [("create_event|update_event|clarify", {})]})

    # --- realistic phrasings lifted from the user's own chats ----------------
    chat = [
        ("coffee friday 9:15 at the French Bakery with Ravid", [("create_event", {"date": next_wd(4), "start_time": "09:15", "title_contains": "Ravid"})]),
        ("Kems tomorrow at 8 with Ravid and Ezra", [("create_event", {"date": d(1), "start_time": "20:00"})]),
        ("pregame at our place wednesday 8:30 pm", [("create_event", {"date": next_wd(2), "start_time": "20:30", "title_contains": "pregame"})]),
        ("bowling tuesday night for Rei's birthday", [("create_event", {"date": next_wd(1), "title_contains": "bowling"})]),
        ("zoom with Alon thursday at 3 pm", [("create_event", {"date": next_wd(3), "start_time": "15:00", "title_contains": "Alon"})]),
        ("lunch 12:30 with Tal on campus tomorrow", [("create_event", {"date": d(1), "start_time": "12:30", "title_contains": "Tal"})]),
        ("tennis wednesday at 17:30", [("create_event", {"date": next_wd(2), "start_time": "17:30", "title_contains": "tennis"})]),
        ("pick up the package from Parcel Home on Hazayit on friday", [("create_todo|create_event", {})]),
        ("night shift tomorrow from 8 pm to 6 am", [("create_event", {"date": d(1), "start_time": "20:00"})]),
        ("Netivim zoom 1800-2000 tonight", [("create_event", {"date": d(0), "start_time": "18:00", "end_time": "20:00"})]),
        ("Shabbat lunch at Ravid's this saturday 12:30", [("create_event", {"date": next_wd(5), "start_time": "12:30"})]),
        ("meeting with Guri moved from 9:30 to 9 on wednesday", [("create_event|update_event", {})]),
        ("Haxaga TA session mondays at noon", [("create_event", {"start_time": "12:00", "recurrence": "weekly"})]),
        ("remind me to send Ravid the tzofim code", [("create_todo", {"titles_contain": ["Ravid"]})]),
        ("sadna on sunday the 15th at 9 am then driving lesson at 8 am", [("create_event", {"start_time": "09:00"}), ("create_event", {"start_time": "08:00"})]),
    ]
    for text, expect in chat:
        C.append({"area": "from-chats", "shape": "chat-phrasing", "text": text, "expect": expect})

    # a few randomised generic events for volume (different names/places each run)
    for i in range(12):
        p, pl, t = rnd.choice(people), rnd.choice(places), rnd.choice(topics)
        hh = rnd.choice([9, 10, 11, 13, 14, 15, 16, 17, 19]); mm = rnd.choice(["00", "30"])
        wd = rnd.randrange(7); disp = f"{hh if hh <= 12 else hh - 12}{':' + mm if mm != '00' else ''} {'am' if hh < 12 else 'pm'}"
        text = rnd.choice([f"meeting with {p} on {WD_NAMES[wd]} at {disp} about {t}",
                           f"set {t} with {p} at {pl} on {WD_NAMES[wd]} at {disp}",
                           f"{WD_NAMES[wd]} {disp} {t} with {p}"])
        ev(text, [("create_event", {"date": next_wd(wd), "start_time": f"{hh:02d}:{mm}", "title_contains": None})], "generated/single")
    return C


# ----------------------------------------------------------------- helpers

def _norm_action(a: str) -> str:
    return a.split("|")[0]


def _check(case: dict, resp: dict, db) -> tuple[bool, list[str], dict]:
    """Compare executed actions + DB effects against expectations.

    A single pass/fail bit collapses two different failure modes that call
    for different fixes: missing something the command asked for (recall),
    and producing something it didn't (precision) — a duplicated task from
    a misread clause is a precision failure, a dropped self-correction that
    merges two events into one is a recall failure on the second event, and
    "97% accurate" doesn't say which one a run mostly had. So each expected
    item is tracked individually (`exp_hit`) rather than folded into one
    case-wide bit, and actions/DB rows the system produced beyond what was
    expected are counted explicitly rather than only mentioned in passing.
    """
    problems: list[str] = []
    got_actions = list(resp.get("actions") or [])
    exp = case["expect"]
    exp_hit = [True] * len(exp)   # per expected item: did everything about it check out

    # action multiset (order-insensitive), with alternatives "a|b"
    remaining = got_actions[:]
    for idx, (name, _) in enumerate(exp):
        alts = name.split("|")
        hit = next((g for g in remaining if g in alts), None)
        if hit is None:
            problems.append(f"missing action {name} (got {got_actions})")
            exp_hit[idx] = False
        else:
            remaining.remove(hit)
    extra_actions = remaining
    if extra_actions:
        problems.append(f"extra actions {extra_actions}")

    # DB effects
    events = []
    for off in range(-1, 45):
        events += db.get_events_for_day(TODAY + dt.timedelta(days=off))
    todos = db.get_todos(include_completed=True)
    used_ev: set[int] = set()
    extra_todo_rows = 0
    for idx, (name, f) in enumerate(exp):
        if name.startswith("create_event"):
            cands = [e for e in events if e["id"] not in used_ev
                     and (not f.get("date") or e["date"] == f["date"])
                     and (not f.get("start_time") or e["start_time"] == f["start_time"])
                     and (not f.get("end_time") or e["end_time"] == f["end_time"])
                     and (not f.get("title_contains") or f["title_contains"].lower() in e["title"].lower())
                     and (not f.get("recurrence") or (e.get("recurrence") or "") == f["recurrence"])]
            if not cands:
                problems.append(f"no event matching {f} in DB " + str([(e['title'], e['date'], e['start_time']) for e in events][:6]))
                exp_hit[idx] = False
            else:
                used_ev.add(cands[0]["id"])
        elif name.startswith("create_todo"):
            # How many rows: "buy chicken and rice" is two tasks, and
            # titles_contain alone can't tell that from one task named
            # "buy chicken and rice". A count higher than expected (not just
            # different) is specifically the "extra output" failure mode —
            # e.g. an interleaved clause spawning its own spurious task.
            if f.get("todo_count") is not None and len(todos) != f["todo_count"]:
                problems.append(f"expected {f['todo_count']} todos, got {len(todos)}: {[t['title'] for t in todos]}")
                exp_hit[idx] = False
                extra_todo_rows += max(0, len(todos) - f["todo_count"])
            for sub in f.get("titles_contain", []):
                m = [t for t in todos if sub.lower() in t["title"].lower()]
                if not m:
                    problems.append(f"no todo containing '{sub}' (todos={[t['title'] for t in todos]})")
                    exp_hit[idx] = False
                else:
                    if f.get("due_date") and (m[0].get("due_date") or "")[:10] != f["due_date"]:
                        problems.append(f"todo '{m[0]['title']}' due {m[0].get('due_date')} != {f['due_date']}")
                        exp_hit[idx] = False
                    if f.get("list_name") and (m[0].get("list_name") or m[0].get("list")) != f["list_name"]:
                        problems.append(f"todo '{m[0]['title']}' list {m[0].get('list_name')} != {f['list_name']}")
                        exp_hit[idx] = False
                    if f.get("tags_contain") and not any(
                            x.lower() == f["tags_contain"].lower() for x in (m[0].get("tags") or [])):
                        problems.append(f"todo '{m[0]['title']}' tags {m[0].get('tags')} missing {f['tags_contain']}")
                        exp_hit[idx] = False
        elif "db_event_start" in f:
            title, t = f["db_event_start"]
            if not any(title.lower() in e["title"].lower() and e["start_time"] == t for e in events):
                problems.append(f"expected '{title}' at {t}; have {[(e['title'], e['date'], e['start_time']) for e in events]}")
                exp_hit[idx] = False
        elif "db_event_end" in f:
            title, t = f["db_event_end"]
            if not any(title.lower() in e["title"].lower() and e["end_time"] == t for e in events):
                problems.append(f"expected '{title}' ending {t}; have {[(e['title'], e['end_time']) for e in events]}")
                exp_hit[idx] = False
        elif "db_event_title" in f:
            sub, t = f["db_event_title"]
            if not any(sub.lower() in e["title"].lower() and e["start_time"] == t for e in events):
                problems.append(f"expected event titled ~'{sub}' at {t}; have {[(e['title'], e['start_time']) for e in events]}")
                exp_hit[idx] = False
        elif "db_event_absent" in f:
            if any(f["db_event_absent"].lower() in e["title"].lower() for e in events):
                problems.append(f"'{f['db_event_absent']}' still in DB")
                exp_hit[idx] = False

    counts = {
        "expected": len(exp),
        "recall_hits": sum(exp_hit),
        "produced_actions": len(got_actions),
        "extra_actions": len(extra_actions),
        "extra_todo_rows": extra_todo_rows,
    }
    return (not problems), problems, counts


def _reset_db(db) -> None:
    import sqlite3
    with sqlite3.connect(db.path) as c:
        for t in ("events", "todos", "subtasks"):
            c.execute(f"DELETE FROM {t}")
    from assistant.intent.context import context_memory
    context_memory.reset()


def _seed(db, seeds: list[dict]) -> None:
    for s in seeds:
        db.create_event_from_dict({"title": s["title"], "date": s["date"], "start_time": s["start_time"],
                                   "end_time": s["end_time"], "color": "#0078d4"})


def _pct(v, q):
    if not v:
        return 0
    v = sorted(v); k = (len(v) - 1) * q; f = int(k); c = min(f + 1, len(v) - 1)
    return v[f] + (v[c] - v[f]) * (k - f)


# --------------------------------------------------------------------- run

def run(args) -> dict:
    from assistant.api.server import create_app, _verify_store, _verify_lock
    from assistant.db import get_db
    from assistant.stt.vocab import get_vocab
    app = create_app(); app.config["TESTING"] = True
    client = app.test_client()
    db = get_db()
    assert db.path.startswith(_TMP), "refusing to run against a non-scratch DB"

    corpus = build_corpus()
    if args.area:
        corpus = [c for c in corpus if c["area"] == args.area]
    if args.limit:
        corpus = corpus[: args.limit]

    # warm everything once so case 1 isn't a cold start
    client.post("/voice/text", json={"transcript": "what do I have today"})
    _reset_db(db)

    results = []
    print(f"Running {len(corpus)} cases against scratch DB {db.path}\n")
    for i, case in enumerate(corpus, 1):
        _reset_db(db)
        _seed(db, case.get("seed", []))
        t0 = time.perf_counter()
        resp = client.post("/voice/text", json={"transcript": case["text"]}).get_json()
        first_ms = int((time.perf_counter() - t0) * 1000)
        ok_quick, problems_quick, counts_quick = _check(case, resp, db)

        # wait for the background self-check (if any) and re-check DB
        verify = None; settle_ms = first_ms
        token = resp.get("verify_token")
        if token:
            deadline = time.time() + 90
            while time.time() < deadline:
                with _verify_lock:
                    entry = _verify_store.get(token)
                if entry is None or entry["ready"]:
                    verify = (entry or {}).get("correction")
                    break
                time.sleep(0.25)
            settle_ms = int((time.perf_counter() - t0) * 1000)
        ok_settled, problems_settled, counts_settled = _check(case, resp, db)

        trace = resp.get("trace") or []
        stage_ms = {s["stage"]: stage_ms_get(trace, s["stage"]) for s in trace}
        rules = [r_ for st in trace for r_ in (st.get("data", {}) or {}).get("rules", [])]
        loops = sum(1 for st in trace if st.get("title") == "Looping back")
        findings = [f for st in trace for f in (st.get("data", {}) or {}).get("findings", [])]
        r = {"i": i, "area": case["area"], "shape": case["shape"], "text": case["text"],
             "parse": resp.get("parse"), "actions": resp.get("actions"), "message": resp.get("message", "")[:160],
             "first_ms": first_ms, "settle_ms": settle_ms, "llm_ms": stage_ms.get("llm", 0), "rule_ms": stage_ms.get("rule", 0),
             "stage_ms": stage_ms, "rules": rules, "loops": loops, "findings": findings,
             "corrections": resp.get("corrections"), "verify": verify,
             "ok_quick": ok_quick, "ok_settled": ok_settled, "problems": problems_settled or problems_quick,
             "counts": counts_settled,
             "changed_by_selfcheck": (ok_quick != ok_settled) or bool(verify and not verify.get("ok", True) and verify.get("applied"))}
        results.append(r)
        mark = "✓" if ok_settled else ("~" if ok_quick else "✗")
        sc = "" if verify is None else (" · self-check: ok" if verify.get("ok") else f" · self-check: {verify.get('severity')} {'applied' if verify.get('applied') else 'not applied'}")
        print(f"{mark} [{r['parse'] or '-':6}] {first_ms:6}ms/{settle_ms:6}ms  {case['text'][:70]}  → {r['actions']}{sc}")
        for p in r["problems"][:2]:
            print(f"      ! {p[:160]}")

    audio = []
    if args.audio:
        audio = run_audio(client, db, corpus[:8])
    return {"results": results, "audio": audio, "corpus_size": len(corpus), "vocab_words": len(get_vocab().entries)}


def stage_ms_get(trace, stage):
    return sum(s["ms"] for s in trace if s["stage"] == stage)


def run_audio(client, db, cases) -> list[dict]:
    """Synthesize a few commands with macOS `say` and push them through Whisper + vocab."""
    import io, subprocess, wave
    out = []
    voices = ["Daniel", "Samantha", "Karen"]
    for i, case in enumerate(cases):
        voice = voices[i % len(voices)]
        aiff = os.path.join(_TMP, f"a{i}.aiff"); wav = os.path.join(_TMP, f"a{i}.wav")
        subprocess.run(["say", "-v", voice, "-o", aiff, case["text"]], check=True)
        subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", aiff, wav], check=True)
        _reset_db(db); _seed(db, case.get("seed", []))
        t0 = time.perf_counter()
        with open(wav, "rb") as f:
            resp = client.post("/voice", data={"audio": (f, "a.wav")}, content_type="multipart/form-data").get_json()
        ms = int((time.perf_counter() - t0) * 1000)
        ok, problems, _counts = _check(case, resp, db)
        heard = resp.get("original_transcript") or resp.get("transcript") or ""
        out.append({"voice": voice, "text": case["text"], "heard": heard, "corrected": resp.get("transcript"),
                    "corrections": resp.get("corrections"), "ok": ok, "ms": ms, "stt_ms": stage_ms_get(resp.get("trace") or [], "stt")})
        print(f"{'✓' if ok else '✗'} [{voice:8}] {ms:6}ms  said: {case['text'][:50]!r}\n        heard: {heard[:90]!r}")
    return out


# ------------------------------------------------------------------ report

def _recall_precision(rows: list[dict]) -> tuple[float, float, dict]:
    """Recall and precision over expected-item / produced-item counts.

    "Accuracy" (the case-level ok_settled rate) doesn't say whether a wrong
    case failed because the system missed something it should have done
    (recall) or did something extra it shouldn't have (precision) — those
    call for different fixes, and a single percentage collapses them.
    """
    exp = sum(r["counts"]["expected"] for r in rows)
    hits = sum(r["counts"]["recall_hits"] for r in rows)
    produced = sum(r["counts"]["produced_actions"] for r in rows)
    extra = sum(r["counts"]["extra_actions"] for r in rows)
    extra_rows = sum(r["counts"]["extra_todo_rows"] for r in rows)
    tp = produced - extra
    fp = extra + extra_rows
    recall = hits / exp if exp else 1.0
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    return recall, precision, {"expected": exp, "recall_hits": hits, "produced": produced,
                                "extra_actions": extra, "extra_todo_rows": extra_rows}


def write_report(data: dict, path: str, args) -> None:
    R = data["results"]
    n = len(R)
    def rate(xs): return f"{sum(xs)/len(xs):.0%}" if xs else "–"
    recall, precision, rp_counts = _recall_precision(R)
    lines = [
        "# Assistant audit — accuracy, latency, self-check",
        "",
        f"_Generated {dt.datetime.now():%Y-%m-%d %H:%M} · {n} commands · scratch DB · vocabulary {data['vocab_words']} words · "
        f"machine {os.uname().machine}. Re-run: `python -m scripts.audit_assistant`._",
        "",
        "## Headline",
        "",
        f"- **Correct after the quick answer:** {rate([r['ok_quick'] for r in R])}  ·  **correct once settled (after self-check):** {rate([r['ok_settled'] for r in R])} "
        f"— case-level exact match against this corpus's hand-written expectations, {n} cases, not a real-usage or human-judged figure",
        f"- **Recall {recall:.0%}** ({rp_counts['recall_hits']}/{rp_counts['expected']} expected items produced correctly) · "
        f"**precision {precision:.0%}** ({rp_counts['produced'] - rp_counts['extra_actions']}/{rp_counts['produced']} produced actions were expected"
        + (f", plus {rp_counts['extra_todo_rows']} extra task rows beyond what was expected" if rp_counts['extra_todo_rows'] else "") + ") "
        "— accuracy alone doesn't distinguish missing something asked for from producing something extra",
        f"- **Time to first result:** p50 {_pct([r['first_ms'] for r in R], .5)/1000:.1f} s · p95 {_pct([r['first_ms'] for r in R], .95)/1000:.1f} s  ·  "
        f"**time to settled:** p50 {_pct([r['settle_ms'] for r in R], .5)/1000:.1f} s · p95 {_pct([r['settle_ms'] for r in R], .95)/1000:.1f} s",
        f"- Parse paths: " + ", ".join(f"{p} {sum(1 for r in R if r['parse']==p)}"
                                       for p in sorted({r["parse"] or "-" for r in R})),
        "",
        "## By area",
        "",
        "| Area | n | quick ✓ | settled ✓ | recall | precision | first p50 | first p95 | settled p50 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for area in sorted({r["area"] for r in R}):
        xs = [r for r in R if r["area"] == area]
        rec, prec, _c = _recall_precision(xs)
        lines.append(f"| {area} | {len(xs)} | {rate([r['ok_quick'] for r in xs])} | {rate([r['ok_settled'] for r in xs])} | "
                     f"{rec:.0%} | {prec:.0%} | "
                     f"{_pct([r['first_ms'] for r in xs], .5)/1000:.1f} s | {_pct([r['first_ms'] for r in xs], .95)/1000:.1f} s | {_pct([r['settle_ms'] for r in xs], .5)/1000:.1f} s |")
    lines += ["", "## By parse path", "", "| Path | n | quick ✓ | settled ✓ | recall | precision | first p50 | first p95 | LLM ms p50 |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for p in sorted({r["parse"] or "-" for r in R}):
        xs = [r for r in R if r["parse"] == p]
        if xs:
            rec, prec, _c = _recall_precision(xs)
            lines.append(f"| {p} | {len(xs)} | {rate([r['ok_quick'] for r in xs])} | {rate([r['ok_settled'] for r in xs])} | "
                         f"{rec:.0%} | {prec:.0%} | "
                         f"{_pct([r['first_ms'] for r in xs], .5)/1000:.1f} s | {_pct([r['first_ms'] for r in xs], .95)/1000:.1f} s | {int(_pct([r['llm_ms'] for r in xs], .5))} |")
    fixed = [r for r in R if not r["ok_quick"] and r["ok_settled"]]
    broke = [r for r in R if r["ok_quick"] and not r["ok_settled"]]
    applied = [r for r in R if r["verify"] and not r["verify"].get("ok", True)]
    lines += ["", "## Quick answer vs self-check", "",
              f"- Self-check ran on {sum(1 for r in R if r['verify'] is not None)} commands; it proposed a correction on {len(applied)} "
              f"({sum(1 for r in applied if r['verify'].get('applied'))} applied).",
              f"- **Fixed by self-check:** {len(fixed)}  ·  **broken by self-check:** {len(broke)}",
              ]
    for r in fixed[:5]:
        lines.append(f"  - fixed: “{r['text']}” → {r['verify']}")
    for r in broke[:5]:
        lines.append(f"  - broke: “{r['text']}” → {r['verify']}")
    stages = ("stt", "vocab", "rule", "llm", "validate", "execute", "verify")
    lines += ["", "## Engine stages (latency; a slow or misbehaving stage is fixed in ITS module)", "",
              "| Stage | ran on | ms p50 | ms p95 |", "|---|---:|---:|---:|"]
    for st in stages:
        xs = [r["stage_ms"][st] for r in R if r.get("stage_ms", {}).get(st)]
        if xs:
            lines.append(f"| {st} | {len(xs)}/{n} | {int(_pct(xs, .5))} | {int(_pct(xs, .95))} |")
    rule_counts = {}
    for r in R:
        for rule in r.get("rules", []):
            rule_counts[rule] = rule_counts.get(rule, 0) + 1
    if rule_counts:
        lines += ["", "## Named-rule fixes applied", "", "| Rule | times |", "|---|---:|"]
        for rule, c in sorted(rule_counts.items(), key=lambda kv: -kv[1]):
            lines.append(f"| {rule} | {c} |")
    looped = [r for r in R if r.get("loops")]
    found = [f for r in R for f in r.get("findings", [])]
    lines += ["", "## Cross-check (step 6)", "",
              f"- Findings: {len(found)} ({', '.join(sorted(set(found))) or 'none'}) across "
              f"{sum(1 for r in R if r.get('findings'))} command(s); loop-backs on {len(looped)} "
              f"command(s) ({sum(r['loops'] for r in looped)} re-entries total).",
              f"- Budget exhausted (answer flagged as unsure): "
              f"{sum(1 for r in R if 'not sure I caught every part' in (r['message'] or ''))}."]
    lines += ["", "## By shape (failures first)", "", "| Shape | n | settled ✓ | first p50 |", "|---|---:|---:|---:|"]
    shapes = sorted({r["shape"] for r in R}, key=lambda s: (sum(r["ok_settled"] for r in R if r["shape"] == s) / max(1, sum(1 for r in R if r["shape"] == s))))
    for s in shapes:
        xs = [r for r in R if r["shape"] == s]
        lines.append(f"| {s} | {len(xs)} | {rate([r['ok_settled'] for r in xs])} | {_pct([r['first_ms'] for r in xs], .5)/1000:.1f} s |")
    extra_output = [r for r in R if r["counts"]["extra_actions"] or r["counts"]["extra_todo_rows"]]
    if extra_output:
        lines += ["", "## Produced more than expected (precision failures)", "",
                  "Distinct from a wrong or missing answer: the system did something on top of what "
                  "was asked for — an extra action, or extra rows from one action (a duplicated task "
                  "from a misread clause is invisible to an action-count check, since the action count "
                  "can still be right).", ""]
        for r in extra_output:
            extras = []
            if r["counts"]["extra_actions"]:
                extras.append(f"{r['counts']['extra_actions']} extra action(s)")
            if r["counts"]["extra_todo_rows"]:
                extras.append(f"{r['counts']['extra_todo_rows']} extra task row(s)")
            lines.append(f"- **{r['text']}** — {', '.join(extras)} — got {r['actions']}")

    lines += ["", "## Failures", ""]
    fails = [r for r in R if not r["ok_settled"]]
    if not fails:
        lines.append("None.")
    for r in fails:
        lines += [f"### {r['area']} · {r['shape']} · `{r['parse']}` · {r['first_ms']/1000:.1f} s",
                  f"- **Said:** {r['text']}", f"- **Did:** {r['actions']} — {r['message']}"]
        for p in r["problems"][:3]:
            lines.append(f"- {p}")
        if r["corrections"]:
            lines.append(f"- vocab corrections: {r['corrections']}")
        lines.append("")
    lines += ["## Slowest 10", "", "| s | path | command |", "|---:|---|---|"]
    for r in sorted(R, key=lambda r: -r["first_ms"])[:10]:
        lines.append(f"| {r['first_ms']/1000:.1f} | {r['parse']} | {r['text'][:80]} |")
    if data["audio"]:
        A = data["audio"]
        lines += ["", "## Audio (macOS `say` → Whisper → vocab)", "",
                  f"{sum(a['ok'] for a in A)}/{len(A)} correct end-to-end · STT p50 {_pct([a['stt_ms'] for a in A], .5)/1000:.1f} s",
                  "", "| ✓ | voice | said | heard | fixes |", "|---|---|---|---|---|"]
        for a in A:
            lines.append(f"| {'✓' if a['ok'] else '✗'} | {a['voice']} | {a['text'][:50]} | {a['heard'][:60]} | {', '.join(c['from']+'→'+c['to'] for c in (a['corrections'] or []))} |")
    lines += ["", "## Raw", "", f"Full per-case JSON: `{path}.json`"]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    with open(path + ".json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, default=str)
    print(f"\nReport: {path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--area"); ap.add_argument("--limit", type=int)
    ap.add_argument("--memory", action="store_true",
                    help="replay against a copy of the real command history, so the "
                         "personalisation layer is exercised instead of ignored")
    ap.add_argument("--memory-k", type=int, metavar="N",
                    help="how many past examples to retrieve (0 turns the memory off, "
                         "which is the comparison worth running first)")
    ap.add_argument("--memory-source", metavar="PATH",
                    help="replay against a copy of this history file instead of the live "
                         "one (already applied at import time, above — declared here only "
                         "so argparse doesn't reject it as unrecognized)")
    ap.add_argument("--audio", action="store_true")
    ap.add_argument("--out", default="DOCUMENTATION/ASSISTANT_AUDIT.md")
    args = ap.parse_args()
    data = run(args)
    write_report(data, args.out, args)


if __name__ == "__main__":
    main()
