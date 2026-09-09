"""Post-generation rules that are not value resolution.

Each needs `item.intent` to exist, which is why they run after generate
rather than in the text pass. Grouped by what they are FOR:

  boundaries   junk_event_drop, question_creates_nothing,
               interrogative_create_asks_first  -- PLAN.md argues these
               belong to segmentation; recorded, not yet moved
  text         morning_title_guard
  reply        cadence_round_and_announce
  residual     past_date_bump, now_means_now -- the only two date rules that
               survived the swap, because neither reads the transcript as a
               list: one rolls a past date forward, the other reads "now".

RETIRED FROM `validate.py` (Gil, 2026-09-08). That module was the ported v1
implementation of this stage; `resolve.py` + `checks.py` replaced everything it
did with VALUES, and what remained were rules that were never value resolution.
Leaving them in a file called `validate.py` made the file's name a lie, so they
live where they belong. The original is in `retired/decompose-validate-v1/`.
"""
from __future__ import annotations

import datetime as _dt
import re

from assistant.engine.decompose_validate.targeting import _CREATE_VERB
from assistant.engine.decompose_validate.text_helpers import unsupported_cadence
from assistant.engine.state import EngineState

_NOW_RE = re.compile(r"\b(?:right\s+now|now|immediately|asap)\b", re.I)


_JUNK_TITLES = {"task", "tasks", "todo", "event", "events", "reminder",
                "list", "item", "items"}


_QUESTION_START = re.compile(
    r"^(does|do|did|is|are|was|were|will|can|could|would|what|when|where|who|how)\b", re.I)


_QUERY_OPENER = re.compile(
    r"^(?:please\s+)?(give me|show me|show|list|read( me)?|tell me|check)\b", re.I)


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


def _rule_now_means_now(state, intent, transcript) -> None:
    """"now" is a time the speaker gave — book it at the clock, not midnight.

    Real usage, 2026-09-08: "create an event NOW to go out for a run" was
    booked 12 AM–1 AM. The word carries no digits, so the temporal reader
    found nothing, the event fell to the 00:00 default, and both the fast
    parse and the model that inherited it kept it.

    It lives here rather than in the reader because BOTH paths have to be
    caught — FastRule's partial parse and the model's own answer — and this
    stage is the one that sees the produced object either way. Guarded three
    ways: the speaker must actually have said "now", must NOT have said
    midnight, and the object must be sitting on exactly the 00:00 default.
    """
    if not _NOW_RE.search(transcript or ""):
        return
    if re.search(r"\bmidnight\b", (transcript or ""), re.I):
        return
    start = getattr(intent, "start_time", None)
    if start != "00:00":
        return                       # a real time was read; leave it alone
    import datetime as _dt
    now = _dt.datetime.now()
    fresh = f"{now.hour:02d}:{now.minute:02d}"
    intent.start_time = fresh
    end = getattr(intent, "end_time", None)
    if end in ("01:00", "23:59", None, ""):
        intent.end_time = f"{(now.hour + 1) % 24:02d}:{now.minute:02d}"
    state.add_fix("validate", "now_means_now", start, fresh,
                  note="\"now\" is the clock, not midnight")


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


def _rule_junk_event_drop(state, item, intent, n_events, pairs) -> None:
    """Hybrid junk: an extra create_event with a generic title alongside real
    todos is parser noise, not a booking."""
    t = (getattr(intent, "title", "") or "").strip().lower()
    if n_events > 0 and t in _JUNK_TITLES and any(a == "create_todo" for _, a, _i in pairs):
        state.add_fix("validate", "junk_event_drop", t, "", note="dropped junk event")
        item.intent = None


def _rule_question_creates_nothing(state, cfg, pairs) -> None:
    """Dataset triage: "…does my daughter have a recital?" INVENTED a task
    from the question's subordinate clause. An item whose own words are a
    question feeds the query — it never creates. Scoped to the item's text,
    so "book gym and what's on friday?" keeps its booking."""
    for item, action, intent in pairs:
        if item.intent is None or not action or not action.startswith("create_"):
            continue
        if _rule_interrogative_create_asks_first(state, cfg, item, pairs):
            continue
        text = (item.text or "").strip()
        imperative_query = bool(_QUERY_OPENER.match(text)) and not _CREATE_VERB.search(text)
        if not text.endswith("?") and not _QUESTION_START.match(text) \
                and not imperative_query:
            continue
        if imperative_query:
            title = (getattr(intent, "title", None)
                     or (getattr(intent, "titles", None) or [""])[0] or item.text[:30])
            state.add_fix("validate", "question_creates_nothing", str(title), "",
                          note="an ask-to-see request creates nothing")
            item.intent = None
            continue
        base = item.id.split("-")[0]
        sibling_query = any(
            other.id.split("-")[0] == base and other.action
            and other.action.startswith("query")
            for other, _a, _i in pairs if other is not item)
        whole_question = text.endswith("?") and bool(_QUESTION_START.match(text))
        if sibling_query or whole_question:
            title = (getattr(intent, "title", None)
                     or (getattr(intent, "titles", None) or [""])[0] or item.text[:30])
            state.add_fix("validate", "question_creates_nothing", str(title), "",
                          note="a question asks; it does not create")
            item.intent = None


def _rule_interrogative_create_asks_first(state, cfg, item, pairs) -> bool:
    """Gil's ruling (2026-09-07, DEVQA Q9): an interrogative create —
    "should i add yoga to my calendar tomorrow?" — must neither auto-create
    nor be silently dropped. It gets a confirmation prompt instead.

    Returns True when this item is held for confirmation: the intent SURVIVES
    (fully validated, ready to POST) and `slots["confirm_create"]` tells the
    orchestrator to ask rather than commit — the same shape as the transcript
    gate's `needs_edit`, and gated the same way on the client saying it can
    render the prompt.

    Only when the question is the whole command. A confirmation holds
    everything, so "book gym at 7 and should i add yoga?" would strand the
    booking behind a dialog about the yoga; there the question half keeps
    today's behaviour and the booking runs.
    """
    if not state.supports_confirm:
        return False
    if not getattr(getattr(cfg, "engine", None), "confirm_create", True):
        return False
    from assistant.engine.segmentation.old_seg.segment import is_interrogative_create
    if not is_interrogative_create(item.text or ""):
        return False
    if sum(1 for other, _a, _i in pairs if other.intent is not None) != 1:
        return False
    item.slots["confirm_create"] = True
    title = (getattr(item.intent, "title", None)
             or (getattr(item.intent, "titles", None) or [""])[0] or item.text[:30])
    state.add_fix("validate", "interrogative_create_asks_first", str(title), "",
                  note="a question that would create something — asking first")
    return True


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

