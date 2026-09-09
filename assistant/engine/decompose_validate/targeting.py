"""Rules for EDITS and DELETES — which existing record the speaker meant.

Targeting, not value resolution: anaphora ("the one I just made"), filling a
move's missing time, and refusing to create when the sentence asked to remove.
`relative_dates` survives here for ONE reason — the anaphora guard needs to
know whether the command names a date at all. It is no longer used to decide
any event's date; that was the index-pinning bug behind `a987aba`.

RETIRED FROM `validate.py` (Gil, 2026-09-08). That module was the ported v1
implementation of this stage; `resolve.py` + `checks.py` replaced everything it
did with VALUES, and what remained were rules that were never value resolution.
Leaving them in a file called `validate.py` made the file's name a lie, so they
live where they belong. The original is in `retired/decompose-validate-v1/`.
"""
from __future__ import annotations

import datetime as _dt
import re

from assistant.engine.decompose_validate.text_helpers import spoken_times
from assistant.engine.state import EngineState

_WEEKDAY_WORDS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4,
    "saturday": 5, "sunday": 6,
    "mon": 0, "tue": 1, "tues": 1, "wed": 2, "thu": 3, "thur": 3, "thurs": 3,
    "fri": 4, "sat": 5, "sun": 6,
}


_REMOVE_SHAPE = re.compile(
    r"^(remove|delete|clear|take)\s+['\"]?(.+?)['\"]?\s+(?:from|off)\s+", re.I)
# The from-less forms: "get rid of this list", "erase/earse the next birthday
# event", "throw away X". Group 2 is the target.


# The from-less forms: "get rid of this list", "erase/earse the next birthday
# event", "throw away X". Group 2 is the target.
_REMOVE_LOOSE = re.compile(
    r"^(?:please\s+)?(get rid of|erase|earse|era[sz]e|trash|throw away|discard|"
    r"remove|delete|clear|cancel)\s+['\"]?(.+?)['\"]?\s*$", re.I)


_CREATE_VERB = re.compile(r"\b(add|create|make|set|book|schedule|new|start|open)\b", re.I)


def relative_dates(transcript: str) -> list:
    """Deterministic reading of relative-date phrases, in order of appearance.

    'thursday' = coming Thursday (today if today is Thursday); 'next thursday'
    = that weekday in NEXT calendar week; 'tomorrow', 'today/tonight',
    'the 19th' handled too. Returns ISO dates.
    """
    today = _dt.date.today()
    out = []
    t = transcript.lower()
    pat = re.compile(
        r"\b(day after tomorrow|tomorrow|today|tonight|this evening|this morning|"
        r"(?:next|this|coming)\s+(?:week\s+(?:on\s+)?)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)s?|"
        r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)s?|"
        r"(?:on\s+)?the\s+(\d{1,2})(?:st|nd|rd|th)\b)")
    # "the 12th of August" names a month — the bare-ordinal branch must not
    # claim it and resolve to the next 12th of *any* month.
    _MONTHS = ("january|february|march|april|may|june|july|august|september|"
               "october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec")
    for m in pat.finditer(t):
        full = m.group(1)
        if full == "day after tomorrow":
            out.append((today + _dt.timedelta(days=2)).isoformat())
        elif full == "tomorrow":
            out.append((today + _dt.timedelta(days=1)).isoformat())
        elif full in ("today", "tonight", "this evening", "this morning"):
            out.append(today.isoformat())
        elif m.group(2):                                   # next/this <weekday>
            wd = _WEEKDAY_WORDS[m.group(2)]
            days = (wd - today.weekday()) % 7
            if full.startswith("next"):
                days = (7 - today.weekday()) + wd          # NEXT calendar week
            out.append((today + _dt.timedelta(days=days)).isoformat())
        elif m.group(3):                                   # bare weekday
            wd = _WEEKDAY_WORDS[m.group(3)]
            days = (wd - today.weekday()) % 7
            out.append((today + _dt.timedelta(days=days)).isoformat())
        elif m.group(4):                                   # the 19th
            around = t[max(0, m.start() - 18):m.end() + 18]
            if re.search(rf"\b(?:{_MONTHS})\b", around):
                continue                                   # month named — leave it
            n = int(m.group(4))
            d0 = today
            for _ in range(3):
                try:
                    cand = d0.replace(day=n)
                except ValueError:
                    cand = None
                if cand and cand >= today:
                    out.append(cand.isoformat())
                    break
                d0 = (d0.replace(day=1) + _dt.timedelta(days=32)).replace(day=1)
    return out


def _rule_anaphor_guard(state, intent, tl, rel, action) -> None:
    """Row 10/47: "the one I just made" is an anaphor, never a title guess;
    a day named in the sentence pins the search to that day."""
    if re.search(r"\b(just (made|created|added|set|scheduled)|last (event|one)|the one i just|you just)\b", tl) \
            and not getattr(intent, "match_date", None) and not getattr(intent, "match_start_time", None):
        if (getattr(intent, "match_title", "") or "").lower() != "it":
            state.add_fix("validate", "anaphor_guard", intent.match_title, "it",
                          note="refers to the last event")
            intent.match_title = "it"
    elif rel and not getattr(intent, "match_date", None):
        state.add_fix("validate", "anaphor_guard", "", rel[0], note="day said in the sentence")
        intent.match_date = rel[0]
        if action == "update_event" and len(rel) > 1 and not getattr(intent, "new_date", None):
            intent.new_date = rel[1]


def _rule_move_time_fill(state, intent, transcript) -> None:
    """"moved from 9:30 to 9" once became new_start_time=09:30 — the origin
    filed as the destination — and "move my 1pm meeting to 3pm" updated
    nothing. The words "from X" and "to Y" are deterministic: X is which
    event is meant, Y is where it goes, and an explicit reading beats
    whatever the model filed (same doctrine as relative_date_pin)."""
    tl = transcript.lower().replace(".", ":")
    _T = r"(\d{1,2}(?::\d{2})?)\s*(am|pm|a:m|p:m)?"

    def _resolve(num: str, ap: str, prefer_pm: "bool | None") -> str:
        h, mm = (num.split(":") + ["00"])[:2]
        h = int(h)
        ap = (ap or "").replace(":", "")
        if ap == "pm" and h < 12:
            h += 12
        elif ap == "am" and h == 12:
            h = 0
        elif not ap and 1 <= h <= 11 and prefer_pm:
            h += 12
        return f"{h:02d}:{mm}"

    m = re.search(rf"\bfrom\s+{_T}\s+to\s+{_T}\b", tl)
    if m:
        src_pm = (m.group(2) or "").startswith("p") or None
        src = _resolve(m.group(1), m.group(2), None)
        dst = _resolve(m.group(3), m.group(4),
                       prefer_pm=int(str(src)[:2]) >= 12 if src_pm is None else src_pm)
        changed = []
        if getattr(intent, "match_start_time", None) != src:
            intent.match_start_time = src
            changed.append(f"match {src}")
        if getattr(intent, "new_start_time", None) != dst:
            intent.new_start_time = dst
            changed.append(f"new {dst}")
        if changed:
            state.add_fix("validate", "move_time_fill", "", " ".join(changed),
                          note="“from X to Y” says which event and where it goes")
        return

    m = re.search(rf"\bto\s+{_T}\b", tl)
    if not m:
        return
    # A destination without a "from": the OTHER spoken time (if exactly one)
    # is which event is meant.
    dst_raw = _resolve(m.group(1), m.group(2), None)
    ms = getattr(intent, "match_start_time", None)
    prefer_pm = int(str(ms)[:2]) >= 12 if ms else None
    others = {t for t in spoken_times(transcript)
              if (int(t[:2]) % 12, t[3:5]) != (int(dst_raw[:2]) % 12, dst_raw[3:5])}
    other_keys = {(int(t[:2]) % 12, t[3:5]) for t in others}
    if not ms and len(other_keys) == 1:
        k = other_keys.pop()
        cands = sorted(t for t in others if (int(t[:2]) % 12, t[3:5]) == k)
        intent.match_start_time = cands[-1] if len(cands) > 1 else cands[0]
        ms = intent.match_start_time
        prefer_pm = int(ms[:2]) >= 12
    dst = _resolve(m.group(1), m.group(2), prefer_pm)
    if getattr(intent, "new_start_time", None) != dst:
        old = getattr(intent, "new_start_time", None)
        intent.new_start_time = dst
        state.add_fix("validate", "move_time_fill", str(old or ""), dst,
                      note="“to X” is where it moves")


def _rule_create_from_remove_guard(state, item, intent) -> None:
    """Dataset triage: "remove 'table' from furniture" CREATED a task named
    "remove table from furniture". A create whose own title is a remove
    instruction is the parser echoing the words back — it becomes the delete
    it says, never a new row."""
    title = (getattr(intent, "title", None)
             or (getattr(intent, "titles", None) or [""])[0] or "")
    m = _REMOVE_SHAPE.match(title.strip()) or _REMOVE_LOOSE.match(title.strip())
    if not m:
        return
    from assistant.actions.todo.intent import DeleteTodoIntent
    target = m.group(2).strip()
    try:
        item.action = "delete_todo"
        item.intent = DeleteTodoIntent(match_title=target)
    except Exception:
        item.intent = None      # cannot build the delete: drop the echo-create
    state.add_fix("validate", "create_from_remove_guard", title, target,
                  note="a remove instruction is a delete, not a new row")

