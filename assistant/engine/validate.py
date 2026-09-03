"""Step 4 — validate & repair, the deterministic conscience of the engine.

Contract (see DOCUMENTATION/ENGINE.md):
  run(state, cfg)          pre-generation, item level:
      reads   state.items, state.text
      writes  item.text (repairs), state.fixes, trace steps (VALIDATE)
  run_objects(state, cfg)  post-generation, field level:
      reads   state.items (with intents), state.text
      writes  intent fields, item.intent=None (junk drop), item.blocked
              (observance refusal), state.messages (cadence note),
              state.fixes, trace steps (VALIDATE)

Every correction is a NAMED rule — the name lands in the Fix record and the
trace, so a wrong fix is greppable straight to its function. The rules are the
survivors of the old brain's `_normalise_intents`, each one bought with a real
bug (task-tracker row numbers in the docstrings), plus the observance gate,
which is new.

Nothing here calls the LLM. If a rule cannot decide deterministically it
leaves the field alone — step 6 exists to catch what slipped through.
"""

from __future__ import annotations

import datetime as _dt
import re

from assistant.engine.state import EngineState

# ---------------------------------------------------------------------------
# Shared reading of the sentence (times, dates, weekdays, cadence words)
# ---------------------------------------------------------------------------

_WEEKDAY_WORDS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4,
    "saturday": 5, "sunday": 6,
    "mon": 0, "tue": 1, "tues": 1, "wed": 2, "thu": 3, "thur": 3, "thurs": 3,
    "fri": 4, "sat": 5, "sun": 6,
}

_RECUR_WORDS = [
    (r"\bevery\s*day\b|\bdaily\b", "daily"),
    (r"\bevery\s+\w+day\b|\bweekly\b|\b(?:mon|tues|wednes|thurs|fri|satur|sun)days\b", "weekly"),
    (r"\bevery\s+month\b|\bmonthly\b", "monthly"),
]

# Cadences the data model cannot express. recurrence is one of daily, weekly
# or monthly, so each of these gets rounded to something else and produces a
# confidently wrong series. Saying so beats approximating silently.
_UNSUPPORTED_CADENCE = [
    (r"\bevery\s+other\b|\bfortnight|\bbi-?weekly\b|\balternate\s+\w+days?\b",
     "every other week"),
    (r"\b(twice|three times|3 times|two times)\s+(a|per)\s+(week|day|month)\b",
     "more than once a period"),
    (r"\bevery\s+(weekday|week\s?day)\b", "weekdays only"),
    (r"\bevery\s+\w+day\s+and\s+\w+day\b", "two days a week"),
]

# "until" names the boundary you stop at; "through"/"including" keep the day.
# English is genuinely ambiguous — this is the project's reading, applied
# everywhere rather than guessed per sentence.
_INCLUSIVE_END = r"\b(through|thru|including|inclusive|up to and including|end of)\b"
_EXCLUSIVE_END = r"\b(until|till|til|up to|up until|before)\b"

_JUNK_TITLES = {"task", "tasks", "todo", "event", "events", "reminder",
                "list", "item", "items"}

_EVENING_WORDS = re.compile(
    r"\b(dinner|drinks?|beer|pub|bar|party|pregame|pizza|kems|movie|cinema|"
    r"show|concert|tonight|evening|night|maariv|mincha)\b", re.I)

# Words that name no particular thing; a calendar full of "meeting" cannot be
# read back. Step 6 consumes this via is_placeholder_title().
_CONTENTLESS_TITLES = {
    "event", "events", "meeting", "meetings", "set meeting", "appointment",
    "activity", "session", "thing", "item", "task", "reminder",
}
_EMPTY_NOUNS = {"event", "events", "activity", "thing", "item"}


def end_is_exclusive(text: str) -> bool:
    """Does this sentence's end-date word exclude the day it names?"""
    t = text.lower()
    if re.search(_INCLUSIVE_END, t):
        return False
    return bool(re.search(_EXCLUSIVE_END, t))


def named_weekdays(text: str) -> set:
    return {n for w, n in _WEEKDAY_WORDS.items() if re.search(rf"\b{w}s?\b", text)}


def unsupported_cadence(text: str) -> "str | None":
    for pat, label in _UNSUPPORTED_CADENCE:
        if re.search(pat, text):
            return label
    return None


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


def at_times(text: str) -> set:
    """Times introduced by "at" — i.e. when something STARTS."""
    out: set = set()
    t = text.lower().replace(".", ":")
    for m in re.finditer(r"\bat\s+(?:around\s+|about\s+|roughly\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm|a:m|p:m)?\b", t):
        h, mm, ap = int(m.group(1)), m.group(2) or "00", (m.group(3) or "").replace(":", "")
        if h > 24:
            continue
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
        out.add(f"{h % 24:02d}:{mm}")
        if not ap and h <= 12:                      # bare hour: both readings
            out.add(f"{(h + 12) % 24:02d}:{mm}")
    return out


def spoken_times(text: str) -> set:
    """All clock times a command mentions, as HH:MM (both readings for bare hours)."""
    out: set = set()
    t = text.lower().replace(".", ":")
    for m in re.finditer(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a:m|p:m)?\b", t):
        h, mm, ap = int(m.group(1)), m.group(2) or "00", (m.group(3) or "").replace(":", "")
        if h > 24:
            continue
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
        out.add(f"{h % 24:02d}:{mm}")
        if not ap and h <= 12:
            out.add(f"{(h + 12) % 24:02d}:{mm}")
    for m in re.finditer(r"\b(\d{2})(\d{2})\b", t):          # 1930, 0915
        h, mm = int(m.group(1)), m.group(2)
        if h < 24 and int(mm) < 60:
            out.add(f"{h:02d}:{mm}")
    if "noon" in t:
        out.add("12:00")
    if "midnight" in t:
        out.add("00:00")
    return out


def is_placeholder_title(title: str, cfg) -> bool:
    """Would this title be useless in a calendar? ("meeting", "event with X")"""
    t = (title or "").strip().lower().strip(" .-")
    if not t:
        return True
    configured = {k.lower() for k in getattr(cfg.nlu, "event_keywords", [])}
    if t in _CONTENTLESS_TITLES | configured:
        return True
    first, _, rest = t.partition(" ")
    return bool(rest) and first in _EMPTY_NOUNS and \
        rest.split(" ", 1)[0] in ("with", "for", "to", "on", "at", "about", "re")


def bare_hour_pm(transcript: str, hhmm: str) -> "str | None":
    """'Kems tomorrow at 8' → 20:00. A bare hour 1–8 is far more often PM in
    calendar speech; 7–8 only when evening words are present."""
    m = re.match(r"(\d{2}):(\d{2})", hhmm or "")
    if not m:
        return None
    h = int(m.group(1))
    if not (1 <= h <= 8):
        return None
    tl = transcript.lower()
    if re.search(rf"\b{h}(?::\d{{2}})?\s*(?:am|a\.m\.)\b", tl) or \
            re.search(rf"\b0?{h}:\d{{2}}\b(?!\s*pm)", tl) and re.search(rf"\b(?:0{h}|{h + 12}):", tl):
        return None
    if re.search(rf"\b{h}(?::\d{{2}})?\s*(?:pm|p\.m\.)\b", tl):
        return None
    if not re.search(rf"\b(?:at\s+)?{h}(?::\d{{2}})?\b", tl):
        return None
    if h <= 6 or _EVENING_WORDS.search(tl):
        return f"{h + 12:02d}:{m.group(2)}"
    return None


# ---------------------------------------------------------------------------
# The observance gate (new — the one rule that REFUSES rather than repairs)
# ---------------------------------------------------------------------------

_DAVENING_RE = re.compile(
    r"\b(daven|davening|shacharit|mincha|maariv|arvit|musaf|selichot|tefill?ah|"
    r"prayer|shul|synagogue|minyan)\b", re.I)
_LEYNING_RE = re.compile(
    r"\b(leyn|leyning|laining|kriah|kriat|torah reading|parsha|megillah?|shiur)\b", re.I)


def _observance_verdict(intent, cfg) -> "str | None":
    """Refusal reason if this AI-created one-off event may not be booked.

    On Shabbat / yom tov (sundown-bounded, same windows the recurring-series
    skip uses) only leyning / meals / davening belong; on a fast day a meal is
    the one thing that must not be booked before the fast ends, and Yom Kippur
    is both — the fast wins. Manual edits through the GUI or endpoints are
    never gated; this runs only on what the engine itself creates.

    None (allowed) on ANY doubt or computation failure — refusing a legitimate
    event is worse than admitting one, and `db._skip_for_observance` already
    keeps series honest.
    """
    try:
        from assistant.db import _is_meal
        from assistant.observance import (
            candle_lighting, is_fast_day, is_shabbat, is_yom_tov, tzeit,
        )

        if getattr(intent, "recurrence", None):
            return None                      # series: db-level skipping owns it
        d = getattr(intent, "date", None)
        if not d:
            return None
        date = _dt.date.fromisoformat(str(d))
        title = getattr(intent, "title", "") or ""
        desc = getattr(intent, "description", "") or ""
        try:
            when = _dt.time.fromisoformat(getattr(intent, "start_time", "") or "")
        except ValueError:
            when = None

        meal = _is_meal(title, desc)
        davening = bool(_DAVENING_RE.search(title) or _DAVENING_RE.search(desc))
        leyning = bool(_LEYNING_RE.search(title) or _LEYNING_RE.search(desc))
        fast = is_fast_day(date)

        # A meal on a fast day, before the fast is out, must not be booked —
        # whatever kind of day it otherwise is.
        if meal and fast:
            ends = tzeit(date)
            if when is None or ends is None or when < ends.replace(microsecond=0):
                name = "a fast day"
                out = f" — it ends at {ends:%H:%M}" if ends else ""
                return (f"that's a meal on {name} ({date:%A, %b %-d}){out}")

        holy = is_shabbat(date) or is_yom_tov(date)
        eve_of_holy = is_shabbat(date + _dt.timedelta(days=1)) or \
            is_yom_tov(date + _dt.timedelta(days=1))
        inside = False
        if holy:
            ends = tzeit(date)
            inside = when is None or ends is None or when < ends.replace(microsecond=0)
        elif eve_of_holy and when is not None:
            starts = candle_lighting(date)
            inside = starts is not None and when >= starts.replace(microsecond=0)
        if not inside:
            return None
        if leyning or davening or (meal and not fast):
            return None
        day = "Shabbat" if (is_shabbat(date) or (eve_of_holy and is_shabbat(date + _dt.timedelta(days=1)))) \
            else "yom tov"
        ends = tzeit(date if holy else date)
        after = f" — after {ends:%H:%M} works" if holy and ends else ""
        return f"that lands on {day} ({date:%A, %b %-d}){after}"
    except Exception:
        return None


# ---------------------------------------------------------------------------
# The two passes
# ---------------------------------------------------------------------------

def run(state: EngineState, cfg) -> EngineState:
    """Pre-generation, item level: format hygiene and text repair."""
    from assistant.trace import VALIDATE

    repaired = 0
    for item in state.items:
        cleaned = item.text.strip().strip("[]").strip()
        # Collapse doubled whitespace Whisper leaves around cut words.
        cleaned = re.sub(r"\s{2,}", " ", cleaned)
        if cleaned != item.text:
            state.add_fix("validate", "text_tidy", item.text, cleaned)
            item.text = cleaned
            repaired += 1
    if state.trace and repaired:
        state.trace.step(VALIDATE, "Tidied", f"{repaired} item(s) cleaned")
    return state


def run_objects(state: EngineState, cfg) -> EngineState:
    """Post-generation, field level: the ported named rules + the gate."""
    from assistant.trace import VALIDATE

    transcript = state.text
    tl = transcript.lower()
    today = _dt.date.today()
    fixes_before = len(state.fixes)

    recur = next((v for pat, v in _RECUR_WORDS if re.search(pat, tl)), None)
    rel = relative_dates(transcript)

    pairs = [(it, it.action, it.intent) for it in state.items if it.intent is not None]
    n_events = sum(1 for _, a, _i in pairs if a == "create_event")
    n_todos = sum(1 for _, a, _i in pairs if a == "create_todo")
    orig_event_dates = {getattr(i, "date", None) for _, a, i in pairs if a == "create_event"}
    ev_idx = 0
    td_idx = 0

    for item, action, intent in pairs:
        if action in ("update_event", "delete_event"):
            _rule_anaphor_guard(state, intent, tl, rel, action)
            continue
        if action == "create_event":
            _rule_relative_date_pin(state, intent, rel, recur, ev_idx, n_events,
                                    orig_event_dates, transcript)
            ev_idx += 1
            _rule_past_date_bump(state, intent, today)
            _rule_recurrence_words(state, intent, recur)
            _rule_until_exclusive(state, intent, tl)
            _rule_weekly_start_day(state, intent, tl, today)
            _rule_at_time_is_start(state, intent, transcript)
            _rule_morning_title_guard(state, intent, transcript)
            _rule_bare_hour_pm(state, intent, transcript, tl)
            _rule_junk_event_drop(state, item, intent, n_events, pairs)
            if item.intent is None:
                continue
            reason = _observance_verdict(intent, cfg)
            if reason:
                item.blocked = reason
                state.add_fix("validate", "observance_gate", getattr(intent, "title", ""), "",
                              note=reason)
        elif action == "create_todo":
            _rule_due_date_pin(state, intent, rel, recur, td_idx, n_todos)
            td_idx += 1

    _rule_cadence_round_and_announce(state, tl)

    applied = state.fixes[fixes_before:]
    if state.trace and applied:
        state.trace.step(VALIDATE, "Sanity fixes",
                         "; ".join(f.human() for f in applied))
    return state


# --- the named rules -------------------------------------------------------

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


def _rule_relative_date_pin(state, intent, rel, recur, ev_idx, n_events,
                            orig_event_dates, transcript) -> None:
    """Deterministic relative dates beat the model's guess — unless the model
    already told the events apart (then collapsing them corrupts the ones the
    relative-date reader never saw; that was a real command with two absolute
    dates and one spoken "Tuesday")."""
    d = getattr(intent, "date", None)
    if rel and not recur:
        if len(set(rel)) == 1:
            want = rel[0] if len(orig_event_dates) <= 1 else None
        else:
            want = rel[ev_idx] if ev_idx < len(rel) and len(rel) == n_events else None
        if want and d != want:
            state.add_fix("validate", "relative_date_pin", str(d), want,
                          note=f"'{transcript[:30]}…' says so")
            intent.date = want


def _rule_past_date_bump(state, intent, today) -> None:
    """Row 29: roll a past date forward without discarding what was said.
    Within a week back it's a weekday that just went → same weekday next week;
    further back the speaker named a calendar day → same day next year."""
    d = getattr(intent, "date", None)
    if not d:
        return
    try:
        dd = _dt.date.fromisoformat(d)
    except ValueError:
        return
    if dd >= today:
        return
    if (today - dd).days <= 7:
        bump = dd
        while bump < today:
            bump += _dt.timedelta(days=7)
    else:
        try:
            bump = dd.replace(year=dd.year + 1)
        except ValueError:                       # 29 Feb → 28 Feb
            bump = dd.replace(year=dd.year + 1, day=28)
    state.add_fix("validate", "past_date_bump", d, bump.isoformat(), note="was in the past")
    intent.date = bump.isoformat()


def _rule_recurrence_words(state, intent, recur) -> None:
    """Recurrence words in the transcript but none on the intent → set it."""
    if recur and not getattr(intent, "recurrence", None):
        intent.recurrence = recur
        state.add_fix("validate", "recurrence_words", "", recur)


def _rule_until_exclusive(state, intent, tl) -> None:
    """"until Oct 6" stops before the 6th; "through Oct 6" keeps it."""
    ru = getattr(intent, "recur_until", None)
    if ru and getattr(intent, "recurrence", None) and end_is_exclusive(tl):
        try:
            rd = _dt.date.fromisoformat(str(ru))
        except ValueError:
            return
        excl = (rd - _dt.timedelta(days=1)).isoformat()
        intent.recur_until = excl
        state.add_fix("validate", "until_exclusive", str(ru), excl,
                      note="“until” excludes the day it names")


def _rule_weekly_start_day(state, intent, tl, today) -> None:
    """A weekly series starts on the soonest weekday it names — "every sunday
    and tuesday at 9am" once produced 106 events, none on a Sunday or Tuesday."""
    if getattr(intent, "recurrence", None) != "weekly":
        return
    named = named_weekdays(tl)
    try:
        dd = _dt.date.fromisoformat(str(intent.date))
    except (TypeError, ValueError):
        return
    if named and dd.weekday() not in named:
        ahead = min((w - today.weekday()) % 7 for w in named)
        anchored = today + _dt.timedelta(days=ahead)
        state.add_fix("validate", "weekly_start_day", intent.date, anchored.isoformat(),
                      note="weekly series must start on the day it names")
        intent.date = anchored.isoformat()


def _rule_at_time_is_start(state, intent, transcript) -> None:
    """A time spoken as "at X" is when the thing STARTS — "dinner at 8 pm"
    came out 18:00–20:00 with 8 filed as the end."""
    at = at_times(transcript)
    s, e = getattr(intent, "start_time", None), getattr(intent, "end_time", None)
    if e and e in at and s and s not in at:
        try:
            hh, mm = map(int, e.split(":"))
        except ValueError:
            return
        intent.start_time = e
        intent.end_time = f"{(hh + 1) % 24:02d}:{mm:02d}"
        state.add_fix("validate", "at_time_is_start", s, e, note=f"'at {e}' is when it starts")


def _rule_morning_title_guard(state, intent, transcript) -> None:
    """A morning word in the event's OWN title means morning — "Shacharit at
    6:30" was booked at 18:30. Scoped to the title so one "Shacharit" cannot
    drag every event in the sentence back twelve hours."""
    title_l = (getattr(intent, "title", "") or "").lower()
    morning = re.search(r"\b(?:shacharit|breakfast|sunrise)\b", title_l)
    st = getattr(intent, "start_time", None) or ""
    if not (morning and re.fullmatch(r"1[2-9]:\d{2}|2[0-3]:\d{2}", st)):
        return
    hh, mm = map(int, st.split(":"))
    am = f"{hh - 12:02d}:{mm:02d}"
    if f"{hh - 12}:{mm:02d}" in transcript or str(hh - 12) in transcript:
        intent.start_time = am
        end = getattr(intent, "end_time", None)
        if end:
            try:
                eh, em = map(int, end.split(":"))
                intent.end_time = f"{max(0, eh - 12):02d}:{em:02d}"
            except ValueError:
                pass
        state.add_fix("validate", "morning_title_guard", st, am, note="a morning event")


def _rule_bare_hour_pm(state, intent, transcript, tl) -> None:
    """Row 41's counterpart: a bare small hour reads PM in calendar speech."""
    pm = bare_hour_pm(transcript, getattr(intent, "start_time", None) or "")
    if pm and not re.search(r"\b(?:morning|breakfast|shacharit|am)\b", tl):
        old_s, old_e = intent.start_time, getattr(intent, "end_time", None)
        intent.start_time = pm
        if old_e:
            try:
                hh, mm = map(int, old_e.split(":"))
                intent.end_time = f"{(hh + 12) % 24:02d}:{mm:02d}"
            except Exception:
                pass
        state.add_fix("validate", "bare_hour_pm", str(old_s), pm, note="PM")


def _rule_junk_event_drop(state, item, intent, n_events, pairs) -> None:
    """Hybrid junk: an extra create_event with a generic title alongside real
    todos is parser noise, not a booking."""
    t = (getattr(intent, "title", "") or "").strip().lower()
    if n_events > 0 and t in _JUNK_TITLES and any(a == "create_todo" for _, a, _i in pairs):
        state.add_fix("validate", "junk_event_drop", t, "", note="dropped junk event")
        item.intent = None


def _rule_due_date_pin(state, intent, rel, recur, td_idx, n_todos) -> None:
    """Deadlines get the same deterministic date resolution events do —
    "due next monday" was left as the model's guess, a Sunday."""
    due = getattr(intent, "due_date", None)
    if rel and not recur:
        if len(set(rel)) == 1:
            want = rel[0]
        else:
            want = rel[td_idx] if td_idx < len(rel) and len(rel) == n_todos else None
        if want and due != want:
            state.add_fix("validate", "due_date_pin", str(due), want)
            intent.due_date = want


def _rule_cadence_round_and_announce(state, tl) -> None:
    """A cadence the model cannot represent is approximated — and the
    approximation is SAID, not done quietly ("every other tuesday" once
    became a single event with no mention)."""
    cadence = unsupported_cadence(tl)
    if not cadence:
        return
    made = next((it.intent for it in state.items
                 if it.action == "create_event" and it.intent is not None), None)
    if made is None:
        return
    as_what = getattr(made, "recurrence", None) or "one-off"
    state.messages.append(
        f"Note: I can only repeat daily, weekly or monthly, so "
        f"“{cadence}” became {as_what} — adjust it if that is wrong.")
    state.add_fix("validate", "cadence_round_and_announce", cadence, str(as_what),
                  note="the model has no way to express the first")
