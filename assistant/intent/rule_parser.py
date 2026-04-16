"""Rule-based NLU fast-path for MACalendar.

Replaces LLM calls for simple, high-confidence voice commands.
Falls back to (or augments) the LLM for complex/ambiguous inputs.

Architecture
------------
Pipeline calls RuleBasedParser.analyze(transcript, current_view) which runs 7
phases and returns a RuleParseResult containing:
  - confidence (0.0–1.0)
  - intents (list of validated (action_name, BaseIntent) tuples)
  - missing_slots (required slots that could not be filled)
  - raw_slots (intermediate per-action slot dicts for LLM partial handoff)

If confidence >= RULE_THRESHOLD and missing_slots == []:
  → execute directly, no LLM call
Else:
  → pass raw_slots to LLM as pre-analysis context (parse_with_context)

RuleParserSkip is raised when the complexity gate fires or no intent matches.
Pipeline catches it and falls through to full LLM parse.
"""

from __future__ import annotations

import datetime
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional imports with graceful degradation
# ---------------------------------------------------------------------------

try:
    import spacy

    _NLP = spacy.load("en_core_web_sm")
    _RULE_PARSER_AVAILABLE = True
except (ImportError, OSError) as _spacy_err:
    _RULE_PARSER_AVAILABLE = False
    _NLP = None  # type: ignore[assignment]
    logger.warning("RuleBasedParser disabled: %s", _spacy_err)

try:
    from recognizers_date_time import DateTimeRecognizer, Culture as _Culture

    _DT_MODEL = DateTimeRecognizer(_Culture.English).get_datetime_model()
    _DT_AVAILABLE = True
except Exception as _dt_err:
    _DT_AVAILABLE = False
    _DT_MODEL = None  # type: ignore[assignment]
    logger.warning("DateTime recognizer disabled: %s", _dt_err)

if TYPE_CHECKING:
    from assistant.actions.base import BaseIntent
    from assistant.actions import ActionRegistry

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

RULE_THRESHOLD = 0.85


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class RuleParseResult:
    """Full result from RuleBasedParser.analyze()."""

    confidence: float
    intents: list[tuple[str, "BaseIntent"]]
    missing_slots: list[str]
    raw_slots: dict  # {action_name: {slot_name: value}}
    transcript: str
    routed_to_llm: bool = False


class RuleParserSkip(Exception):
    """Raised when the rule parser cannot handle the input (complexity gate or no match).
    Pipeline should catch this and fall through to the standard LLM parse.
    """


# ---------------------------------------------------------------------------
# STT shorthand expansion table
# ---------------------------------------------------------------------------

_STT_EXPANSIONS: list[tuple[str, str]] = [
    (r"\btmrw\b", "tomorrow"),
    (r"\btomoro\b", "tomorrow"),
    (r"\bnxt\b", "next"),
    (r"\bmtg\b", "meeting"),
    (r"\bappt\b", "appointment"),
    (r"\bw/\b", "with"),
    (r"\bthru\b", "through"),
    (r"\bcal\b", "calendar"),
    (r"\bsched\b", "schedule"),
    (r"\bappt\b", "appointment"),
    (r"\bwk\b", "week"),
    (r"\bmon\b(?=\s)", "monday"),
    (r"\btue\b", "tuesday"),
    (r"\bwed\b(?=\s)", "wednesday"),
    (r"\bthu\b", "thursday"),
    (r"\bfri\b(?=\s)", "friday"),
    (r"\bsat\b(?=\s)", "saturday"),
    (r"\bsun\b(?=\s)", "sunday"),
]

# ---------------------------------------------------------------------------
# Intent routing tables
# ---------------------------------------------------------------------------

# (verb_lemma, domain_hint | None) → action_name
# More specific (non-None domain) entries take priority.
INTENT_MAP: dict[tuple[str, str | None], str] = {
    # --- Calendar create ---
    ("schedule", None): "create_event",
    ("book", None): "create_event",
    ("plan", None): "create_event",
    ("block", None): "create_event",
    ("add", "calendar"): "create_event",
    ("create", "calendar"): "create_event",
    ("make", "calendar"): "create_event",
    ("set", "calendar"): "create_event",
    ("organize", None): "create_event",
    # --- Calendar update ---
    ("move", None): "update_event",
    ("reschedule", None): "update_event",
    ("postpone", None): "update_event",
    ("delay", None): "update_event",
    ("push", None): "update_event",
    ("advance", None): "update_event",
    ("shift", None): "update_event",
    ("change", "calendar"): "update_event",
    ("update", "calendar"): "update_event",
    ("edit", "calendar"): "update_event",
    # --- Calendar delete ---
    ("cancel", None): "delete_event",
    ("delete", "calendar"): "delete_event",
    ("remove", "calendar"): "delete_event",
    ("clear", "calendar"): "delete_event",
    ("drop", "calendar"): "delete_event",
    # --- Calendar update (additional verbs) ---
    ("rename", None): "update_event",
    # Extend / shorten duration
    ("extend", None): "update_event",
    ("lengthen", None): "update_event",
    ("shorten", None): "update_event",
    ("stretch", None): "update_event",
    ("prolong", None): "update_event",
    ("trim", "calendar"): "update_event",
    # --- Schedule query ---
    ("show", "calendar"): "query_schedule",
    ("list", "calendar"): "query_schedule",
    ("read", "calendar"): "query_schedule",
    ("check", "calendar"): "query_schedule",
    ("summarize", "calendar"): "query_schedule",
    # --- Todo create ---
    ("add", "todo"): "create_todo",
    ("create", "todo"): "create_todo",
    ("make", "todo"): "create_todo",
    ("remind", None): "create_todo",
    ("buy", None): "create_todo",
    ("call", None): "create_todo",
    ("email", None): "create_todo",
    ("text", None): "create_todo",
    ("pick", None): "create_todo",
    ("get", "todo"): "create_todo",
    ("write", "todo"): "create_todo",
    ("send", None): "create_todo",
    ("order", None): "create_todo",
    ("pay", None): "create_todo",
    ("fix", "todo"): "create_todo",
    ("clean", "todo"): "create_todo",
    ("wash", None): "create_todo",
    ("cook", None): "create_todo",
    ("prepare", None): "create_todo",
    # --- Todo complete ---
    ("mark", None): "complete_todo",
    ("check", "todo"): "complete_todo",   # "check off" / "check the task"
    ("complete", None): "complete_todo",
    ("finish", None): "complete_todo",
    ("done", None): "complete_todo",
    # --- Todo update ---
    ("update", "todo"): "update_todo",
    ("edit", "todo"): "update_todo",
    ("change", "todo"): "update_todo",
    ("set", "todo"): "update_todo",
    ("rename", "todo"): "update_todo",
    ("move", "todo"): "update_todo",    # "move task X to general" — overrides calendar "move"
    ("note", "todo"): "update_todo",
    ("annotate", None): "update_todo",
    # --- Todo delete ---
    ("delete", "todo"): "delete_todo",
    ("remove", "todo"): "delete_todo",
    ("clear", "todo"): "delete_todo",
    ("drop", "todo"): "delete_todo",
    ("scrap", None): "delete_todo",
    # --- Todo query ---
    ("show", "todo"): "query_todos",
    ("list", "todo"): "query_todos",
    ("read", "todo"): "query_todos",
}

# Words that strongly signal the calendar domain
_CALENDAR_SIGNALS = frozenset({
    "meeting", "event", "appointment", "sync", "standup", "stand-up",
    "interview", "session", "class", "lecture", "conference", "call",
    "seminar", "webinar", "calendar", "agenda", "schedule",
})

# Words that strongly signal the todo/task domain
_TODO_SIGNALS = frozenset({
    "task", "todo", "to-do", "reminder", "list", "grocery", "groceries",
    "errand", "chore", "shopping", "item", "priority", "subtask",
})

# Scope keywords for query_schedule
_SCOPE_PHRASES: list[tuple[str, str]] = [
    ("this week", "week"),
    ("next week", "week"),
    ("the week", "week"),
    ("week", "week"),
    ("tomorrow", "tomorrow"),
    ("next day", "tomorrow"),
    ("today", "today"),
    ("this morning", "today"),
    ("this afternoon", "today"),
    ("tonight", "today"),
    ("this evening", "today"),
]

# Verbs that extend/shorten the duration of an event (not move it)
# For these, "at X" = match_start_time (finder) and "to Y" = new_end_time (change)
_EXTEND_VERBS = frozenset({"extend", "lengthen", "stretch", "prolong", "shorten", "trim"})

# Anaphoric references that trigger context memory lookup
_ANAPHORS = frozenset({
    "it", "that", "this", "the meeting", "the event", "that event",
    "this event", "the task", "that task", "the last one",
    "the last event", "the last task", "my last one",
})

# Required slots per action — used for confidence scoring and missing-slot detection
_REQUIRED_SLOTS: dict[str, list[str]] = {
    "create_event": ["title", "date", "start_time"],
    "update_event": ["match_title"],
    "delete_event": ["match_title"],
    "query_schedule": [],
    "create_todo": ["titles"],
    "complete_todo": ["match_title"],
    "delete_todo": ["match_title"],
    "update_todo": ["match_title"],
    "query_todos": [],
    "add_subtask": ["parent_title", "subtask_title"],
    "complete_subtask": ["parent_title", "subtask_title"],
    "delete_subtask": ["parent_title", "subtask_title"],
}

# Optional slots whose presence boosts confidence
_BONUS_SLOTS: dict[str, list[str]] = {
    "create_event": ["end_time", "attendees"],
    "update_event": ["new_start_time", "new_date", "match_start_time"],
    "delete_event": ["match_date", "match_start_time"],
    "create_todo": ["due_date", "priority"],
    "update_todo": ["new_priority", "new_due_date"],
}

# Priority keyword → priority level
_PRIORITY_KEYWORDS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(urgent|critical|asap|important|high[- ]priority)\b"), "high"),
    (re.compile(r"\bmedium[- ]priority\b"), "medium"),
    (re.compile(r"\blow[- ]priority\b"), "low"),
]

# Priority name words used in "set priority to X" patterns
_PRIORITY_NAMES = {"high": "high", "medium": "medium", "low": "low",
                   "urgent": "high", "critical": "high", "important": "high"}

# ---------------------------------------------------------------------------
# Pre-processing helpers
# ---------------------------------------------------------------------------


def _preprocess(transcript: str) -> tuple[str, bool]:
    """Normalise text and check complexity gate.

    Returns (normalised_text, should_skip).
    should_skip=True means the complexity gate fired → caller should raise RuleParserSkip.
    """
    if not _RULE_PARSER_AVAILABLE:
        return transcript, True

    text = transcript.strip().lower()

    # Strip view-context prefix injected by pipeline
    text = re.sub(r"^\[tasks view\]\s*", "", text)

    # Expand STT shorthands
    for pattern, replacement in _STT_EXPANSIONS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    # Complexity gate: content-word count (stop/filler words don't add complexity)
    _FILLER = frozenset({
        "a", "an", "the", "my", "your", "our", "its", "i", "you", "we", "they",
        "is", "are", "was", "were", "be", "been", "being", "do", "does", "did",
        "can", "could", "will", "would", "should", "shall", "may", "might",
        "have", "has", "had", "of", "in", "on", "at", "to", "for", "with",
        "by", "from", "up", "about", "into", "and", "or", "but", "that", "this",
        "these", "those", "me", "him", "her", "us", "them", "it", "so",
        "please", "kindly", "just", "go", "ahead", "okay", "ok", "well",
        "actually", "really", "also", "too", "then", "there", "here",
        "what", "when", "where", "which", "who", "how", "let", "execute",
    })
    content_words = [w for w in text.split() if w.rstrip(".,!?;:") not in _FILLER]
    if len(content_words) > 12:
        return text, True

    # Clause-count gate via spaCy
    doc = _NLP(text)
    clause_verbs = [
        tok for tok in doc
        if tok.pos_ == "VERB"
        and (tok.dep_ == "ROOT" or tok.dep_ == "conj")
        and any(child.dep_ in ("nsubj", "nsubjpass", "expl") for child in tok.subtree)
    ]
    if len(clause_verbs) > 3:
        return text, True

    # Relative clause with an explicit subject (e.g. "delete the event you created")
    # → too ambiguous for the rule parser, let the LLM handle it.
    has_relcl_with_subj = any(
        tok.pos_ == "VERB" and tok.dep_ == "relcl"
        and any(c.dep_ in ("nsubj", "nsubjpass") for c in tok.children)
        for tok in doc
    )
    if has_relcl_with_subj:
        return text, True

    return text, False


# ---------------------------------------------------------------------------
# Phase 1: Multi-intent splitting
# ---------------------------------------------------------------------------


def _split_intents(doc) -> list:
    """Split a spaCy Doc into per-intent Span objects.

    Finds the ROOT verb and any conjunct VERBs, then builds subtree spans
    for each, so "buy milk and call mom" → two spans.
    """
    root = next((tok for tok in doc if tok.dep_ == "ROOT"), None)
    if root is None:
        return [doc[:]]

    split_verbs = [root] + [
        tok for tok in doc
        if tok.dep_ == "conj" and tok.head == root and tok.pos_ == "VERB"
    ]

    if len(split_verbs) == 1:
        return [doc[:]]

    # Sort by position and build non-overlapping subtree spans
    split_verbs_sorted = sorted(split_verbs, key=lambda t: t.i)
    spans = []
    for verb in split_verbs_sorted:
        subtree_tokens = sorted(verb.subtree, key=lambda t: t.i)
        start = subtree_tokens[0].i
        end = subtree_tokens[-1].i + 1
        spans.append(doc[start:end])

    return spans if spans else [doc[:]]


# ---------------------------------------------------------------------------
# Phase 2: Temporal extraction
# ---------------------------------------------------------------------------


def _normalize_time(value: str) -> str:
    """Convert 'T15:00:00' or '15:00:00' to 'HH:MM'."""
    value = value.lstrip("T")
    parts = value.split(":")
    if len(parts) >= 2:
        return f"{int(parts[0]):02d}:{parts[1]}"
    return value


def _pick_business_hour_time(values: list[dict]) -> str | None:
    """Given multiple time values (AM/PM ambiguity), prefer PM for hours 1–7."""
    if not values:
        return None
    times = [v.get("value", "") or v.get("timex", "") for v in values]
    parsed: list[tuple[int, str]] = []
    for t in times:
        normalized = _normalize_time(t)
        try:
            h = int(normalized.split(":")[0])
            parsed.append((h, normalized))
        except Exception:
            pass
    if not parsed:
        return None
    # Prefer PM (12-19) for business hours ambiguity; else just take highest hour
    pm_options = [(h, t) for h, t in parsed if 12 <= h <= 20]
    if pm_options:
        return min(pm_options, key=lambda x: x[0])[1]
    return min(parsed, key=lambda x: abs(x[0] - 10))[1]  # closest to 10 AM


def _extract_temporal(span_text: str, today: datetime.date) -> dict:
    """Extract date/time information from a span of text.

    Returns a dict with keys:
      date, start_time, end_time, spans (list of (start_char, end_char) blocked)
      _source: "recognizer" | "regex_fallback"
    """
    result: dict = {
        "date": None,
        "start_time": None,
        "end_time": None,
        "spans": [],
        "_source": "recognizer",
        "_used_anaphora": False,
        "_domain_inferred": False,
    }

    if _DT_AVAILABLE and _DT_MODEL is not None:
        dt_ref = datetime.datetime.combine(today, datetime.time())
        recognized = _DT_MODEL.parse(span_text, dt_ref)
        for res in recognized:
            span = (res.start, res.end + 1)
            result["spans"].append(span)
            for val in res.resolution.get("values", []):
                timex_type = val.get("type", "")

                if timex_type == "datetime" and not result["date"]:
                    raw = val.get("value", "")
                    if raw and raw != "not resolved":
                        parts = raw.split(" ")
                        date_part = parts[0]
                        time_part = parts[1][:5] if len(parts) > 1 else None
                        if date_part >= today.isoformat():
                            result["date"] = date_part
                            if time_part and not result["start_time"]:
                                result["start_time"] = time_part
                        elif "_dt_past_fallback" not in result:
                            # Past date — keep as fallback in case no future value follows
                            result["_dt_past_fallback"] = (date_part, time_part)

                elif timex_type == "date" and not result["date"]:
                    raw = val.get("value", "")
                    if raw and raw != "not resolved":
                        # For ambiguous dates (multiple values like Friday past/future),
                        # we'll take the last recognized result (processed on next iteration)
                        candidate = raw
                        if candidate >= today.isoformat():
                            result["date"] = candidate

                elif timex_type == "time" and not result["start_time"]:
                    # May have multiple values (AM/PM ambiguity) — pick business hours
                    all_time_vals = res.resolution.get("values", [])
                    result["start_time"] = _pick_business_hour_time(all_time_vals)

                elif timex_type == "timerange":
                    start_v = val.get("start", "")
                    end_v = val.get("end", "")
                    if start_v and not result["start_time"]:
                        result["start_time"] = _normalize_time(start_v)
                    if end_v and not result["end_time"]:
                        result["end_time"] = _normalize_time(end_v)

        # Apply past-datetime fallback if no future date was resolved
        if not result["date"] and "_dt_past_fallback" in result:
            date_part, time_part = result.pop("_dt_past_fallback")
            result["date"] = date_part
            if time_part and not result["start_time"]:
                result["start_time"] = time_part
        else:
            result.pop("_dt_past_fallback", None)

        # Handle datetime with AM/PM ambiguity (two values returned)
        if recognized:
            all_dt_vals = [
                v for res in recognized
                for v in res.resolution.get("values", [])
                if v.get("type") == "datetime"
            ]
            if len(all_dt_vals) >= 2 and result["start_time"] is None:
                # Re-pick based on business hours
                result["start_time"] = _pick_business_hour_time(
                    [{"value": v.get("value", "").split(" ")[-1] if " " in v.get("value", "") else ""}
                     for v in all_dt_vals]
                )
            if all_dt_vals and result["date"] is None:
                raw = all_dt_vals[0].get("value", "")
                if raw and " " in raw:
                    result["date"] = raw.split(" ")[0]

    # Regex fallback for simple "today" / "tomorrow" if recognizer missed them
    if not result["date"]:
        result["_source"] = "regex_fallback"
        lower = span_text.lower()
        if re.search(r"\btoday\b", lower):
            result["date"] = today.isoformat()
        elif re.search(r"\btomorrow\b", lower):
            result["date"] = (today + datetime.timedelta(days=1)).isoformat()

    # Regex fallback: "noon" → 12:00, "midnight" → 00:00
    if not result["start_time"]:
        lower = span_text.lower()
        if re.search(r"\bnoon\b", lower):
            result["start_time"] = "12:00"
            result["_source"] = "regex_fallback"
        elif re.search(r"\bmidnight\b", lower):
            result["start_time"] = "00:00"
            result["_source"] = "regex_fallback"

    # Regex fallback for bare time like "at 3" or "at 3pm" if recognizer missed
    if not result["start_time"]:
        result["_source"] = "regex_fallback"
        m = re.search(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", span_text, re.IGNORECASE)
        if m:
            h = int(m.group(1))
            mins = m.group(2) or "00"
            ampm = (m.group(3) or "").lower()
            if ampm == "pm" and h < 12:
                h += 12
            elif not ampm and 1 <= h <= 7:
                h += 12  # business-hours heuristic
            result["start_time"] = f"{h:02d}:{mins}"

    # Regex fallback for "from X to Y" when recognizer misses ambiguous times
    if not result["start_time"] and not result["end_time"]:
        m = re.search(
            r"\bfrom\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s+to\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b",
            span_text, re.IGNORECASE
        )
        if m:
            result["_source"] = "regex_fallback"
            sh, sm = int(m.group(1)), m.group(2) or "00"
            eh, em = int(m.group(4)), m.group(5) or "00"
            sampm = (m.group(3) or "").lower()
            eampm = (m.group(6) or "").lower()
            if eampm == "pm" and eh < 12:
                eh += 12
            if sampm == "pm" and sh < 12:
                sh += 12
            elif not sampm and sh < eh and eh >= 12:
                sh += 12  # infer PM from end marker
            elif not sampm and 1 <= sh <= 7:
                sh += 12  # business-hours heuristic
                # If we bumped start to PM, end should also be PM if it's < start
                if eh < sh:
                    eh += 12
            result["start_time"] = f"{sh:02d}:{sm}"
            result["end_time"] = f"{eh:02d}:{em}"

    # Fallback for "to HH" alone (update_event: "reschedule to 4pm")
    if result["start_time"] is None and result["end_time"] is None:
        m = re.search(r"\bto\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", span_text, re.IGNORECASE)
        if m:
            h = int(m.group(1))
            mins = m.group(2) or "00"
            ampm = (m.group(3) or "").lower()
            if ampm == "pm" and h < 12:
                h += 12
            elif not ampm and 1 <= h <= 7:
                h += 12
            # For update_event "to X" → new_start_time (not end_time)
            result["start_time"] = f"{h:02d}:{mins}"
            result["_source"] = "regex_fallback"

    # Post-process: business-hours PM heuristic for recognizer-extracted times.
    # "2 o'clock", "3 o'clock" etc. without explicit AM context are almost
    # always afternoon in a calendar/meeting context — convert 1–7 to PM.
    if result["start_time"]:
        _has_am = re.search(
            r"\b(am|a\.m\.|morning|midnight)\b", span_text, re.IGNORECASE
        )
        if not _has_am:
            try:
                _h, _m = result["start_time"].split(":")
                _h = int(_h)
                if 1 <= _h <= 7:
                    result["start_time"] = f"{_h + 12:02d}:{_m}"
            except (ValueError, AttributeError):
                pass

    return result


# ---------------------------------------------------------------------------
# Phase 3: Intent/domain routing
# ---------------------------------------------------------------------------


def _route_intent(span, current_view: str) -> tuple[str | None, str, bool]:
    """Route a span to an (action_name, domain, domain_inferred) tuple.

    domain_inferred=True means we fell back to view context (lower confidence).
    """
    span_text = span.text.lower()
    span_words = set(re.findall(r"\w+", span_text))

    # --- Domain detection ---
    has_calendar = bool(span_words & _CALENDAR_SIGNALS)
    has_todo = bool(span_words & _TODO_SIGNALS)

    if has_calendar and not has_todo:
        domain = "calendar"
        domain_inferred = False
    elif has_todo and not has_calendar:
        domain = "todo"
        domain_inferred = False
    elif has_todo and has_calendar:
        # Both signals: default to todo (most common conflict: "add task to calendar")
        domain = "todo"
        domain_inferred = True
    else:
        # No explicit signal: fall back to current_view
        domain = "todo" if current_view in ("todo", "tasks") else "calendar"
        domain_inferred = True

    # --- Find action verb and route to action ---
    # Strategy: collect all candidate verb tokens, try each until one maps to an action.
    # This handles cases where spaCy tags the action word as NOUN/ADJ/PROPN (e.g.
    # "schedule" as NOUN in "schedule meeting", "mark" as PROPN in "mark it done").
    #
    # Priority:
    #   1. ROOT verb/aux that maps to INTENT_MAP
    #   2. ROOT verb/aux (even if no direct map, use for WH fallback)
    #   3. Any VERB/AUX in span that maps to INTENT_MAP
    #   4. Any token (any POS) whose lemma maps to INTENT_MAP

    def _maps_to_action(lemma: str) -> str | None:
        return INTENT_MAP.get((lemma, domain)) or INTENT_MAP.get((lemma, None))

    # WH-word check first — "what/when/how many" sentences are queries regardless
    # of what other INTENT_MAP verbs appear in the span (e.g. "what's on my schedule")
    _WH_RE = re.compile(r"^(what|when|how\s+many|which|show|list|read)\b", re.IGNORECASE)
    if _WH_RE.search(span_text.strip()):
        wh_action = "query_schedule" if domain == "calendar" else "query_todos"
        return wh_action, domain, False  # WH-word is explicit, not inferred

    root_verb = None
    action = None

    # Pass 1: ROOT verb that directly maps
    for tok in span:
        if tok.dep_ == "ROOT" and tok.pos_ in ("VERB", "AUX"):
            mapped = _maps_to_action(tok.lemma_)
            if mapped:
                root_verb = tok
                action = mapped
                break

    # Pass 2: ROOT verb even without map (for WH-fallback path)
    if root_verb is None:
        for tok in span:
            if tok.dep_ == "ROOT" and tok.pos_ in ("VERB", "AUX"):
                root_verb = tok
                break

    # Pass 3: any VERB/AUX with map
    if action is None:
        for tok in span:
            if tok.pos_ in ("VERB", "AUX"):
                mapped = _maps_to_action(tok.lemma_)
                if mapped:
                    root_verb = tok
                    action = mapped
                    break

    # Pass 4: any token with known action lemma (noun-verb ambiguity, ADJ mis-tags, etc.)
    if action is None:
        for tok in span:
            mapped = _maps_to_action(tok.lemma_)
            if mapped:
                root_verb = tok
                action = mapped
                break

    if action is None:
        # No-verb fallbacks: WH-word query
        if re.match(r"\b(what|when|how many|which|show|list|read)\b", span_text):
            action_fallback = "query_schedule" if domain == "calendar" else "query_todos"
            return action_fallback, domain, domain_inferred
        return None, domain, domain_inferred

    return action, domain, domain_inferred


# ---------------------------------------------------------------------------
# Phase 4: Slot filling
# ---------------------------------------------------------------------------


def _in_temporal(tok, temporal_spans: list[tuple[int, int]]) -> bool:
    return any(start <= tok.idx < end for start, end in temporal_spans)


def _extract_title(span, temporal_spans: list[tuple[int, int]]) -> str | None:
    """Extract the best title from a span, blocking temporal token positions."""
    # Priority 1: noun chunk containing dobj of root verb
    dobj_chunks = [
        chunk for chunk in span.noun_chunks
        if chunk.root.dep_ == "dobj"
        and not any(_in_temporal(t, temporal_spans) for t in chunk)
    ]
    if dobj_chunks:
        return _clean_title(dobj_chunks[0].text)

    # Priority 2: noun chunk containing pobj (object of preposition)
    pobj_chunks = [
        chunk for chunk in span.noun_chunks
        if chunk.root.dep_ == "pobj"
        and not any(_in_temporal(t, temporal_spans) for t in chunk)
    ]
    if pobj_chunks:
        return _clean_title(pobj_chunks[0].text)

    # Priority 3: any noun chunk not in temporal zone, closest to root
    root_tok = next((tok for tok in span if tok.dep_ == "ROOT"), span[0])
    candidates = [
        chunk for chunk in span.noun_chunks
        if not any(_in_temporal(t, temporal_spans) for t in chunk)
    ]
    if candidates:
        closest = min(candidates, key=lambda c: abs(c.root.i - root_tok.i))
        return _clean_title(closest.text)

    return None


# Action verb lemmas that spaCy sometimes drags into noun chunks as compound modifiers
_TITLE_STRIP_VERBS = frozenset({
    "schedule", "book", "plan", "cancel", "delete", "add", "create",
    "remind", "buy", "call", "email", "text", "pick", "get", "write",
    "send", "order", "pay", "fix", "clean", "wash", "cook", "prepare",
    "move", "reschedule", "postpone", "push", "update", "rename",
    "mark", "check", "complete", "finish", "remove", "clear", "drop",
    "show", "list", "read", "summarize",
})


def _clean_title(text: str) -> str:
    """Strip leading determiners, possessives, and action verb compounds."""
    text = re.sub(r"^(my|the|a|an|our|your)\s+", "", text, flags=re.IGNORECASE).strip()
    # Strip leading word if it's a known action verb (compound mis-tag)
    words = text.split()
    while words and words[0].lower() in _TITLE_STRIP_VERBS:
        words = words[1:]
    text = " ".join(words) if words else text
    text = re.sub(r"\s+", " ", text)
    return text if text else text


def _fill_slots(span, action_name: str, temporal: dict, current_view: str) -> dict:
    """Fill action-specific slots from the span and temporal extraction."""
    temporal_spans = temporal.get("spans", [])
    slots: dict = {}

    title = _extract_title(span, temporal_spans)

    if action_name == "create_event":
        if title:
            slots["title"] = title
        if temporal.get("date"):
            slots["date"] = temporal["date"]
        if temporal.get("start_time"):
            slots["start_time"] = temporal["start_time"]
        # end_time defaults to "" so the CalendarIntent model_validator can auto-fill it
        slots["end_time"] = temporal.get("end_time") or ""
        # Attendees: "with <PROPN>" pattern
        attendees = []
        for tok in span:
            if tok.lower_ == "with" and not _in_temporal(tok, temporal_spans):
                for child in tok.children:
                    if child.pos_ in ("PROPN", "NOUN") and not _in_temporal(child, temporal_spans):
                        attendees.append(child.text)
        if attendees:
            slots["attendees"] = attendees

    elif action_name == "update_event":
        # Detect whether this is an extend/shorten action (vs. a move/reschedule)
        is_extend = any(tok.lemma_.lower() in _EXTEND_VERBS for tok in span)

        if is_extend:
            # Extend/shorten semantics:
            #   "at X"  → match_start_time  (which event to find)
            #   "to Y"  → new_end_time      (what to change)
            #   "on D"  → match_date        (which day to look on)
            # Generic calendar words ("event", "appointment") are not real titles here.
            if title and title.lower() not in _CALENDAR_SIGNALS:
                slots["match_title"] = title
            if temporal.get("date"):
                slots["match_date"] = temporal["date"]
            if temporal.get("start_time"):
                slots["match_start_time"] = temporal["start_time"]
            # end_time from recognizer directly → new_end_time
            if temporal.get("end_time"):
                slots["new_end_time"] = temporal["end_time"]
            # Also scan for "to Xpm" in the raw text — recognizer stops after the first
            # time hit, so "extend at 1pm to 3pm" won't yield end_time automatically.
            if not slots.get("new_end_time"):
                m = re.search(
                    r"\bto\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b",
                    span.text, re.IGNORECASE,
                )
                if m:
                    h = int(m.group(1))
                    mins = m.group(2) or "00"
                    ampm = (m.group(3) or "").lower()
                    if ampm == "pm" and h < 12:
                        h += 12
                    elif not ampm and 1 <= h <= 7:
                        h += 12
                    slots["new_end_time"] = f"{h:02d}:{mins}"
        else:
            # Standard move/reschedule/rename semantics:
            #   title    → match_title
            #   time     → new_start_time
            #   date     → new_date
            # For rename: "rename X to Y" — match_title = X, new_title = Y (pobj of "to")
            new_title_from_rename: str | None = None
            for tok in span:
                if tok.lower_ == "to" and tok.dep_ in ("prep", "dative", "aux"):
                    pobj_chunks = [
                        c for c in span.noun_chunks
                        if c.root.head == tok and not any(_in_temporal(t, temporal_spans) for t in c)
                    ]
                    if pobj_chunks:
                        new_title_from_rename = _clean_title(pobj_chunks[0].text)
                        break

            if new_title_from_rename:
                slots["new_title"] = new_title_from_rename
                root_chunks = [
                    c for c in span.noun_chunks
                    if c.root.dep_ == "ROOT" and not any(_in_temporal(t, temporal_spans) for t in c)
                ]
                if root_chunks:
                    slots["match_title"] = _clean_title(root_chunks[0].text)
                elif title and title != new_title_from_rename:
                    slots["match_title"] = title
            else:
                if title:
                    slots["match_title"] = title

            if temporal.get("start_time"):
                slots["new_start_time"] = temporal["start_time"]
            if temporal.get("end_time"):
                slots["new_end_time"] = temporal["end_time"]
            if temporal.get("date"):
                slots["new_date"] = temporal["date"]

    elif action_name == "delete_event":
        # Only use title if it's a real event name, not a generic calendar word
        # (e.g. "delete the event at 6pm" — "event" is a placeholder, not the title)
        if title and title.lower() not in _CALENDAR_SIGNALS:
            slots["match_title"] = title
        if temporal.get("date"):
            slots["match_date"] = temporal["date"]
        if temporal.get("start_time"):
            slots["match_start_time"] = temporal["start_time"]

    elif action_name == "query_schedule":
        # Scope detection on raw span text (before temporal exclusion)
        span_lower = span.text.lower()
        scope = "today"
        for phrase, scope_val in _SCOPE_PHRASES:
            if phrase in span_lower:
                scope = scope_val
                break
        slots["scope"] = scope
        # Query type
        if any(w in span_lower for w in ("first", "earliest")):
            slots["query_type"] = "first"
        elif any(w in span_lower for w in ("next", "upcoming")):
            slots["query_type"] = "next"
        elif any(w in span_lower for w in ("how many", "count", "number")):
            slots["query_type"] = "count"
        else:
            slots["query_type"] = "full"

    elif action_name == "create_todo":
        if title:
            slots["titles"] = [title]
        if temporal.get("date"):
            slots["due_date"] = temporal["date"]
        # Detect list_name from explicit "general" / "someday" keywords in span
        span_lower = span.text.lower()
        if re.search(r"\b(general|someday|later|backlog)\b", span_lower):
            slots["list_name"] = "general"
        else:
            slots["list_name"] = "today"
        # Extract priority from keywords ("urgent", "high priority", etc.)
        for pattern, level in _PRIORITY_KEYWORDS:
            if pattern.search(span_lower):
                slots["priority"] = level
                break

    elif action_name in ("delete_todo", "complete_todo", "update_todo"):
        # For complete/update/delete, also try extracting the subject noun
        # (e.g. "mark groceries as done" → subject "groceries", not "mark groceries")
        subject_chunks = [
            chunk for chunk in span.noun_chunks
            if chunk.root.dep_ in ("nsubj", "nsubjpass")
            and not any(_in_temporal(t, temporal_spans) for t in chunk)
        ]
        if subject_chunks:
            candidate = _clean_title(subject_chunks[0].text)
            if candidate:
                slots["match_title"] = candidate
        elif title:
            slots["match_title"] = title

        if action_name == "update_todo":
            span_lower = span.text.lower()
            # "rename X to Y" / "rename X as Y" → new_title from pobj of "to"/"as"
            for tok in span:
                if tok.lower_ in ("to", "as") and tok.dep_ in ("prep", "dative"):
                    pobj_chunks = [
                        c for c in span.noun_chunks
                        if c.root.head == tok and not any(_in_temporal(t, temporal_spans) for t in c)
                    ]
                    if pobj_chunks:
                        slots["new_title"] = _clean_title(pobj_chunks[0].text)
                        break
            # "set priority to high/medium/low" or "make it high priority"
            # Only match explicit priority-level words to avoid false hits like "grocery priority"
            _PRI_WORDS = r"(high|medium|low|urgent|critical|important)"
            m = re.search(rf"\bpriority\s+(?:to\s+)?{_PRI_WORDS}\b", span_lower)
            if not m:
                m = re.search(rf"\b{_PRI_WORDS}\s+priority\b", span_lower)
            if m:
                word = m.group(1).lower()
                slots["new_priority"] = _PRIORITY_NAMES.get(word, word)
            # "set due date to Friday" / "change due date to next Monday"
            if temporal.get("date") and re.search(r"\bdue\b", span_lower):
                slots["new_due_date"] = temporal["date"]
            # "move to general / today list"
            if re.search(r"\b(general|someday|later|backlog)\b", span_lower):
                slots["new_list"] = "general"
            elif re.search(r"\btoday\b", span_lower):
                slots["new_list"] = "today"

    elif action_name == "query_todos":
        span_lower = span.text.lower()
        if "general" in span_lower:
            slots["list_name"] = "general"
        elif "all" in span_lower:
            slots["list_name"] = "all"
        else:
            slots["list_name"] = "today"
        slots["include_completed"] = "complete" in span_lower or "done" in span_lower

    return slots


# ---------------------------------------------------------------------------
# Phase 5: Anaphora resolution
# ---------------------------------------------------------------------------


def _resolve_anaphora(slots: dict, action_name: str, memory) -> tuple[dict, bool]:
    """Substitute anaphoric match_title with the known context entity.

    Returns (updated_slots, used_anaphora).
    """
    key = "match_title" if action_name in (
        "update_event", "delete_event", "complete_todo", "delete_todo", "update_todo"
    ) else None

    if key is None:
        return slots, False

    current_val = slots.get(key, "")
    if current_val.lower().strip() not in _ANAPHORS:
        return slots, False

    if "event" in action_name and memory.last_event_title:
        slots[key] = memory.last_event_title
        if not slots.get("match_date") and memory.last_event_date:
            slots["match_date"] = memory.last_event_date
        return slots, True

    if "todo" in action_name and memory.last_todo_title:
        slots[key] = memory.last_todo_title
        return slots, True

    # Anaphor present but memory is empty — can't resolve
    return slots, False


# ---------------------------------------------------------------------------
# Phase 6: Confidence scoring
# ---------------------------------------------------------------------------


def _compute_missing_slots(action_name: str, slots: dict) -> list[str]:
    # delete_event / update_event: match_title OR match_start_time is sufficient
    if action_name in ("delete_event", "update_event"):
        if not slots.get("match_title") and not slots.get("match_start_time"):
            return ["match_title"]
        return []
    required = _REQUIRED_SLOTS.get(action_name, [])
    return [s for s in required if not slots.get(s)]


def _compute_confidence(
    action_name: str,
    slots: dict,
    temporal: dict,
    domain_inferred: bool,
    used_anaphora: bool,
) -> float:
    # delete_event / update_event: satisfied by match_title OR match_start_time
    if action_name in ("delete_event", "update_event"):
        base = 1.0 if (slots.get("match_title") or slots.get("match_start_time")) else 0.0
    else:
        required = _REQUIRED_SLOTS.get(action_name, [])
        total_required = len(required)
        if total_required == 0:
            base = 1.0
        else:
            filled = sum(1 for s in required if slots.get(s))
            base = filled / total_required

    multiplier = 1.0

    if temporal.get("_source") == "regex_fallback":
        multiplier *= 0.95

    if domain_inferred and action_name not in ("query_schedule", "query_todos"):
        multiplier *= 0.85

    if used_anaphora:
        multiplier *= 0.80

    confidence = base * multiplier

    # Bonus for optional slots
    bonus_list = _BONUS_SLOTS.get(action_name, [])
    bonus = sum(0.05 for s in bonus_list if slots.get(s))
    confidence = min(1.0, confidence + min(0.10, bonus))

    return round(confidence, 3)


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------


class RuleBasedParser:
    """Fast-path NLU parser using spaCy + recognizers-text-date-time.

    Handles simple voice commands in <10ms without an LLM call.
    For ambiguous or complex inputs, raises RuleParserSkip (caller uses LLM).
    For partial matches, returns a RuleParseResult with confidence < RULE_THRESHOLD
    so the caller can hand off to the LLM with pre-filled slot context.
    """

    def __init__(self, registry: "ActionRegistry") -> None:
        self._registry = registry
        from assistant.intent.context import context_memory
        self._memory = context_memory

    def analyze(self, transcript: str, current_view: str = "month") -> RuleParseResult:
        """Full 7-phase analysis.

        Raises RuleParserSkip if the complexity gate fires or no intent matches.
        Otherwise returns a RuleParseResult (which may have low confidence or
        missing slots, in which case the pipeline should hand off to the LLM).
        """
        if not _RULE_PARSER_AVAILABLE:
            raise RuleParserSkip("spaCy not available")

        # Phase 0: Preprocess + complexity gate
        normalized, should_skip = _preprocess(transcript)
        if should_skip:
            raise RuleParserSkip(f"Complexity gate fired for: {transcript!r}")

        doc = _NLP(normalized)

        # Phase 1: Multi-intent splitting
        spans = _split_intents(doc)

        today = datetime.date.today()

        all_intents: list[tuple[str, "BaseIntent"]] = []
        all_missing: list[str] = []
        all_raw_slots: dict = {}
        confidences: list[float] = []

        for span in spans:
            # Phase 2: Temporal extraction
            temporal = _extract_temporal(span.text, today)

            # Phase 3: Intent/domain routing
            action_name, _, domain_inferred = _route_intent(span, current_view)
            if action_name is None:
                if len(spans) == 1:
                    raise RuleParserSkip(f"No action matched for: {span.text!r}")
                # Multi-span: skip unmatched span, continue
                continue

            # Phase 4: Slot filling
            slots = _fill_slots(span, action_name, temporal, current_view)

            # Phase 5: Anaphora resolution
            slots, used_anaphora = _resolve_anaphora(slots, action_name, self._memory)
            temporal["_used_anaphora"] = used_anaphora
            temporal["_domain_inferred"] = domain_inferred

            # Phase 6: Confidence + validation
            missing = _compute_missing_slots(action_name, slots)
            confidence = _compute_confidence(
                action_name, slots, temporal, domain_inferred, used_anaphora
            )

            all_missing.extend(missing)
            confidences.append(confidence)
            all_raw_slots[action_name] = slots

            logger.debug(
                "Rule parser: action=%s confidence=%.2f missing=%s slots=%s",
                action_name, confidence, missing, slots,
            )

            # Attempt Pydantic validation when all required slots are present
            if not missing:
                action_cls = self._registry.get(action_name)
                if action_cls is not None:
                    try:
                        intent = action_cls.intent_model.model_validate(slots)
                        all_intents.append((action_name, intent))
                    except Exception as exc:
                        logger.debug("Rule parser validation failed for %s: %s", action_name, exc)
                        all_missing.append("validation_error")
                        confidences[-1] = round(confidence * 0.5, 3)

        if not confidences:
            raise RuleParserSkip("No spans produced confident results")

        overall_confidence = min(confidences)

        return RuleParseResult(
            confidence=overall_confidence,
            intents=all_intents,
            missing_slots=all_missing,
            raw_slots=all_raw_slots,
            transcript=normalized,
        )

    def parse(self, transcript: str, current_view: str = "month") -> list[tuple[str, "BaseIntent"]]:
        """Public parse API compatible with the ParserProtocol.

        Returns intents directly when confidence is high and slots are complete.
        Raises RuleParserSkip if confidence < RULE_THRESHOLD or missing_slots.
        Pipeline should catch RuleParserSkip and fall through to LLM.
        """
        result = self.analyze(transcript, current_view)
        if result.confidence >= RULE_THRESHOLD and not result.missing_slots:
            return result.intents
        raise RuleParserSkip(
            f"Confidence {result.confidence:.2f} < {RULE_THRESHOLD} or missing slots: {result.missing_slots}"
        )
