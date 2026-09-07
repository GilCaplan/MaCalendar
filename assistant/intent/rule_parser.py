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

from assistant.intent.list_split import lead_verb, split_items

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional imports — availability probed at import time, models loaded lazily
# on first parse call so the ~80 MB spaCy + thinc footprint is deferred until
# the user actually uses voice input.
# ---------------------------------------------------------------------------

import importlib.util as _iutil
import threading as _thr

# --- spaCy ---
_RULE_PARSER_AVAILABLE: bool = _iutil.find_spec("spacy") is not None
_NLP = None          # set by _ensure_nlp()
_nlp_lock = _thr.Lock()
_nlp_loaded = False

def _ensure_nlp() -> None:
    """Load the spaCy model on first call (thread-safe)."""
    global _NLP, _nlp_loaded
    if _nlp_loaded:
        return
    with _nlp_lock:
        if _nlp_loaded:
            return
        try:
            import spacy as _spacy
            _NLP = _spacy.load("en_core_web_sm")
            _nlp_loaded = True
            logger.info("spaCy model loaded (lazy).")
        except (ImportError, OSError) as exc:
            global _RULE_PARSER_AVAILABLE
            _RULE_PARSER_AVAILABLE = False
            logger.warning("RuleBasedParser disabled: %s", exc)
            _nlp_loaded = True  # don't retry

# --- recognizers-text-date-time ---
_DT_AVAILABLE: bool = _iutil.find_spec("recognizers_date_time") is not None
_DT_MODEL = None     # set by _ensure_dt()
_dt_lock = _thr.Lock()
_dt_loaded = False

def _ensure_dt() -> None:
    """Load the date/time recognizer model on first call (thread-safe)."""
    global _DT_MODEL, _dt_loaded
    if _dt_loaded:
        return
    with _dt_lock:
        if _dt_loaded:
            return
        try:
            from recognizers_date_time import DateTimeRecognizer, Culture as _Culture
            _DT_MODEL = DateTimeRecognizer(_Culture.English).get_datetime_model()
            _dt_loaded = True
            logger.info("DateTime recognizer loaded (lazy).")
        except Exception as exc:
            global _DT_AVAILABLE
            _DT_AVAILABLE = False
            logger.warning("DateTime recognizer disabled: %s", exc)
            _dt_loaded = True  # don't retry

if TYPE_CHECKING:
    from assistant.actions.base import BaseIntent
    from assistant.actions import ActionRegistry

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

RULE_THRESHOLD = 0.80   # tuned 2026-09-07: whole-command sweep, +2pp coverage at flat 87% precision (sub-item bar is 0.60)


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
    dropped_spans: int = 0   # parts of the command the rule parser could not route


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
    # "get rid of X" is removal-speak the verb map can't key on (multi-word):
    # normalize so ("remove", …) routing applies and a generic target like
    # "this list" hits the fast gate's veto (sandbox batch F2).
    (r"\bget rid of\b", "remove"),
    # --- F9 (simple-first abstain mining): 209 of 540 simple abstains were
    # outright skips caused by leading filler/courtesy hiding the command
    # from ^-anchored routing. Strip them FIRST (list order applies).
    (r"^(?:um+|uh+|so|well|ok(?:ay)?|alright|hey|yeah)[,\s]+", ""),
    (r"^(?:could|can)\s+you\s+tell\s+me\s+", ""),          # "…what's on my calendar" = query
    (r"^(?:could|can|would)\s+you\s+(?=remind\b)", ""),     # "could you remind me to X"
    # "let's do/have/get X" is create-speak the verb map can't key on
    (r"^let'?s\s+(?:do|have|get)\s+", "book "),
    # STT misspellings the expansion table lacked (measured, not guessed)
    (r"\btommorow\b", "tomorrow"),
    (r"\bapointment\b", "appointment"),
    (r"\bremindar\b", "reminder"),
    # "mark <date> as <occasion>" marks a DAY, it does not tick a task off:
    # "mark 13 october of this year as my birthday" fast-committed a wrong
    # complete_todo (F4b). Rewritten to the create shape the parser already
    # handles ("add my birthday on 13 october …"); requires a date-looking
    # object so "mark groceries as done" keeps completing, and a done-ish
    # label is left alone outright.
    (r"\bmark\s+((?:the\s+)?\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?"
     r"(?:january|february|march|april|may|june|july|august|september|october|"
     r"november|december)(?:\s+of\s+this\s+year|\s+this\s+year)?"
     r"|(?:january|february|march|april|may|june|july|august|september|october|"
     r"november|december)\s+(?:the\s+)?\d{1,2}(?:st|nd|rd|th)?"
     r"|today|tomorrow|next\s+\w+day)\s+as\s+"
     r"(?!done\b|complete\b|completed\b|finished\b)(.+)$",
     r"add \2 on \1"),
    # (b, F6) date-marking beyond explicit month-days: weekdays, relatives,
    #     named days ("christmas day"), "note" as the verb, an optional
    #     "on my calendar" infix. Same rewrite target as F4b.
    (r"\b(?:mark|note)\s+((?:next|this|coming)\s+\w+|today|tomorrow|"
     r"the\s+day\s+after\s+tomorrow|\w+(?:'s)?\s+day|\w+\s+eve)\s+"
     r"(?:on\s+my\s+calendar\s+)?as\s+"
     r"(?!done\b|complete\b|completed\b|finished\b)(.+)$",
     r"add \2 on \1"),
    # --- F6 (FastRule-6000 train mining, 2026-09-07): three systematic
    # false-accept families, each rewritten to a form the router already
    # handles correctly (the F2/F4b pattern: normalize, don't special-case).
    # (b) completion speak: "check off X" hit query_schedule, "i'm done with
    #     X" created a todo. "mark X as done" is the completion phrasing the
    #     router provably handles — rewrite everything completion-shaped to it.
    (r"^(?:yeah,?\s+|ok,?\s+|okay,?\s+)?(?:i(?:'m| am)\s+done\s+with|"
     r"i\s+already\s+did|i\s+finished)\s+(.+)$", r"mark \1 as done"),
    (r"^check\s+off\s+(.+)$", r"mark \1 as done"),
    (r"^complete\s+(?!the\s*$)(.+)$", r"mark \1 as done"),
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

    _ensure_nlp()
    if not _RULE_PARSER_AVAILABLE:  # may have been cleared by load failure
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


_IMPERATIVE_VERB_LEMMAS: frozenset = frozenset(lemma for (lemma, _domain) in INTENT_MAP.keys())

# Common Whisper mishearings of sentence-initial imperative verbs. Only consulted
# at ROOT position in _route_intent (see Pass 5) — never as a general text
# substitution — so "meeting by 3pm" (where "by" is a legitimate preposition,
# not the ROOT) is unaffected.
_STT_HOMOPHONE_VERBS: dict = {
    "by": "buy",
    "bye": "buy",
}


def _lexicon_split_points(doc) -> list:
    """Fallback split-point detector for when spaCy's VERB-conjunct detection fails.

    spaCy's statistical POS tagger frequently mistags a bare imperative verb
    immediately followed by a bare-noun object as a NOUN compound instead of a
    VERB — e.g. "schedule meeting tomorrow" gets ROOT="meeting" (NOUN), hiding
    "schedule" from the VERB-conjunct search entirely. "book", "plan", and
    "block" show the same failure mode with their own bare-noun objects.

    Rather than fight the tagger, use vocabulary we already control: INTENT_MAP's
    verb lemmas. A token qualifies as a split point only if it's sentence-initial
    or immediately follows a coordinating "and"/"or" — both low-risk positions
    (a command verb mid-clause, e.g. "the schedule needs an update", won't match
    either condition), so this can't fire on ordinary single-action sentences.
    """
    points = []
    for i, tok in enumerate(doc):
        if tok.lemma_.lower() not in _IMPERATIVE_VERB_LEMMAS:
            continue
        sentence_initial = i == 0
        follows_cc = i > 0 and doc[i - 1].dep_ == "cc" and doc[i - 1].lower_ in ("and", "or")
        if sentence_initial or follows_cc:
            points.append(tok)
    return points


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

    if len(split_verbs) < 2:
        # spaCy's dependency parse found only one verb — try the lexicon fallback
        # before giving up and treating this as a single-intent sentence.
        lexicon_points = _lexicon_split_points(doc)
        if len(lexicon_points) >= 2:
            # These tokens aren't reliable syntactic heads (mistagged as NOUN, so
            # their .subtree is unusable — it may not cover the clause's temporal
            #/object tokens at all). Partition the doc by raw token position
            # between consecutive split points instead of by subtree.
            points_sorted = sorted(lexicon_points, key=lambda t: t.i)
            spans = []
            for idx, tok in enumerate(points_sorted):
                start = tok.i
                end = points_sorted[idx + 1].i if idx + 1 < len(points_sorted) else len(doc)
                if start < end:
                    spans.append(doc[start:end])
            return spans if spans else [doc[:]]
        return [doc[:]]

    # Sort by position and build non-overlapping spans.
    # A conj verb's own .subtree always includes everything nested under it, and
    # since conj verbs hang off the ROOT, the ROOT's subtree also covers the whole
    # sentence — using raw subtree bounds would make span[0] duplicate the full
    # transcript alongside the later per-verb spans. Clip each span so it stops at
    # the start of the next split verb and starts no earlier than the previous
    # span's end, giving contiguous, non-overlapping chunks instead.
    split_verbs_sorted = sorted(split_verbs, key=lambda t: t.i)
    spans = []
    prev_end = 0
    for idx, verb in enumerate(split_verbs_sorted):
        subtree_tokens = sorted(verb.subtree, key=lambda t: t.i)
        start = max(subtree_tokens[0].i, prev_end)
        end = subtree_tokens[-1].i + 1
        if idx < len(split_verbs_sorted) - 1:
            end = min(end, split_verbs_sorted[idx + 1].i)
        if start < end:
            spans.append(doc[start:end])
            prev_end = end

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


# "7am" / "7a.m." — an hour with the meridiem written against it. The datetime
# recogniser sometimes hands back BOTH readings for these (it separates cleanly
# on "7 am"), and preferring PM then turned an explicitly stated morning time
# into an evening one.
# "rename the meeting with Tal to robotics sync" — everything between the verb
# and the final "to"/"as" is the event, the rest is its new name.
# "the meeting with Ima", "lunch with Tal" — noun chunking stops at the noun and
# drops the person, leaving a bare "meeting" that matches ANY meeting. Since the
# name is the only thing distinguishing one from another, keep it.
_WITH_WHOM_RE = re.compile(
    r"\b{title}\s+(with\s+[A-Za-z][\w'’-]*(?:\s+(?:and|&)\s+[A-Za-z][\w'’-]*)?)",
    re.IGNORECASE,
)


def _extend_title_with_whom(span_text: str, title: str) -> str:
    """Append a trailing "with <name>" to a matched title, when one was said."""
    if not title:
        return title
    pattern = _WITH_WHOM_RE.pattern.format(title=re.escape(title.strip()))
    m = re.search(pattern, span_text, re.IGNORECASE)
    if not m:
        return title
    return f"{title.strip()} {m.group(1).strip()}"


# "with the dentist" / "with my mum" — the word after "with" is a determiner, so
# the person's name never made it in. Half a phrase ("meeting with the") is a
# worse needle than the bare word, so it does not count as naming anybody.
_NOT_A_NAME_AFTER_WITH = frozenset({
    "the", "a", "an", "my", "our", "your", "his", "her", "their", "its",
    "this", "that", "these", "those", "some", "any", "each", "both",
    "him", "them", "me", "us", "someone", "somebody", "everyone", "everybody",
})


def _title_with_person(span_text: str, title: str) -> tuple[str, bool]:
    """Return the title plus any trailing "with <name>", and whether one was found.

    The flag is what lets a caller tell "meeting with Ima" (identifies one
    event) from a bare "meeting" (identifies any of them).
    """
    if not title:
        return title, False
    extended = _extend_title_with_whom(span_text, title)
    if extended.strip().lower() == title.strip().lower():
        return title, False
    whom = extended[len(title.strip()):].split()      # ["with", "<name>", ...]
    if len(whom) < 2 or whom[1].lower() in _NOT_A_NAME_AFTER_WITH:
        return title, False
    return extended, True


_RENAME_RE = re.compile(
    r"\b(?:rename|re-?name)\s+(?:the\s+|my\s+)?(.+?)\s+(?:to|as)\s+(.+?)\s*$",
    re.IGNORECASE,
)

_SAID_MERIDIEM = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s?m\.?\b", re.I)


def _pick_business_hour_time(values: list[dict], said: str = "") -> str | None:
    """Given multiple time values (AM/PM ambiguity), prefer PM for hours 1–7.

    `said` is the text the values came from: when it states am or pm outright
    that wins, because there is no ambiguity left to resolve.
    """
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

    # Honour an explicitly spoken meridiem before guessing.
    for m in _SAID_MERIDIEM.finditer(said or ""):
        hour12 = int(m.group(1)) % 12
        wanted = hour12 + (12 if m.group(3).lower() == "p" else 0)
        for h, t in parsed:
            if h == wanted:
                return t

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

    if _DT_AVAILABLE:
        _ensure_dt()
    if _DT_AVAILABLE and _DT_MODEL is not None:
        dt_ref = datetime.datetime.combine(today, datetime.time())
        recognized = _DT_MODEL.parse(span_text, dt_ref)
        for res in recognized:
            span = (res.start, res.end + 1)
            result["spans"].append(span)
            # The recogniser can return a match with no resolution at all —
            # "from 9 to 10" is one — and dereferencing it raised an
            # AttributeError that escaped the parser entirely, killing the
            # command instead of falling back to the LLM.
            resolution = getattr(res, "resolution", None) or {}
            for wren in resolution.get("values", []):
                timex_type = wren.get("type", "")

                if timex_type == "datetime" and not result["date"]:
                    raw = wren.get("value", "")
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
                    raw = wren.get("value", "")
                    if raw and raw != "not resolved":
                        # For ambiguous dates (multiple values like Friday past/future),
                        # we'll take the last recognized result (processed on next iteration)
                        candidate = raw
                        if candidate >= today.isoformat():
                            result["date"] = candidate

                elif timex_type == "time" and not result["start_time"]:
                    # May have multiple values (AM/PM ambiguity) — pick business hours
                    all_time_vals = (getattr(res, "resolution", None) or {}).get("values", [])
                    result["start_time"] = _pick_business_hour_time(all_time_vals, span_text)

                elif timex_type == "timerange":
                    start_v = wren.get("start", "")
                    end_v = wren.get("end", "")
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
                for v in (getattr(res, "resolution", None) or {}).get("values", [])
                if v.get("type") == "datetime"
            ]
            if len(all_dt_vals) >= 2 and result["start_time"] is None:
                # Re-pick based on business hours
                result["start_time"] = _pick_business_hour_time(
                    [{"value": v.get("value", "").split(" ")[-1] if " " in v.get("value", "") else ""}
                     for v in all_dt_vals],
                    span_text,
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

    # An end time before the start means the range crossed noon without saying so
    # ("lunch from 12 to 1" → 12:00–01:00, a negative hour). Push the end into
    # the afternoon, unless it was explicitly stated as a morning time.
    if result["start_time"] and result["end_time"]:
        try:
            _sh, _sm = (int(x) for x in result["start_time"].split(":"))
            _eh, _em = (int(x) for x in result["end_time"].split(":"))
            _end_is_am = re.search(r"to\s+\d{1,2}(?::\d{2})?\s*a\.?\s?m\.?(?![a-z])",
                                   span_text, re.IGNORECASE)
            if (_eh * 60 + _em) <= (_sh * 60 + _sm) and _eh < 12 and not _end_is_am:
                result["end_time"] = f"{_eh + 12:02d}:{_em:02d}"
        except (ValueError, AttributeError):
            pass

    # Post-process: business-hours PM heuristic for recognizer-extracted times.
    # "2 o'clock", "3 o'clock" etc. without explicit AM context are almost
    # always afternoon in a calendar/meeting context — convert 1–7 to PM.
    if result["start_time"]:
        # "7am" has no word boundary between the digit and "am", and "a.m."
        # doesn't end on one either — so the old \b(am|a\.m\.)\b test missed both
        # and turned an explicitly stated 7am into 19:00. Match the meridiem
        # against the digit instead, and treat morning words as morning.
        _has_am = (
            re.search(r"\d\s*a\.?\s?m\.?(?![a-z])", span_text, re.IGNORECASE)
            or re.search(r"\b(morning|midnight|breakfast|shacharit|sunrise)\b",
                         span_text, re.IGNORECASE)
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


_ROUTE_OVERRIDES = [
    (re.compile(r"^\s*(?:please\s+)?(?:add|put)\s+.+\s+(?:on|to)\s+(?:my|the)\s+(?:\w+\s+)?list\b"), "create_todo"),
    # F6a: an encounter being ARRANGED is an event — must outrank the
    # need-to→todo row below ("i need to talk to Quinn friday" was a todo).
    # "see my …" excluded: that's query-speak ("i need to see my lists").
    (re.compile(r"^\s*(?:please\s+)?(?:i\s+)?(?:need|want)\s+to\s+(?:talk|speak|"
                r"meet|catch\s+up|touch\s+base|sit\s+down|see\s+(?!my\b))"), "create_event"),
    # F6c: completion-speak routes by PHRASE — the inner title's own verbs
    # ("buy", "change") were hijacking verb-routing ("mark buy groceries as
    # done" → create_todo). Rewrites funnel done-with/already-did/check-off
    # into this shape; the override then routes them all.
    (re.compile(r"^\s*(?:please\s+)?mark\s+.+\s+as\s+done\b"), "complete_todo"),
    # F7b: "set X as high priority" is a fully-structured UPDATE — the verb
    # heuristics read it as a create ("set" → create at 1.00, the worst kind
    # of confident wrong).
    (re.compile(r"^\s*(?:please\s+)?(?:set|make)\s+.+\s+as\s+"
                r"(?:high|medium|low)\s+priority\b"), "update_todo"),
    (re.compile(r"^\s*(?:please\s+)?(?:i\s+)?(?:need|have|want|got)\s+to\s+"), "create_todo"),
    (re.compile(r"^\s*(?:please\s+)?remind me\b"), "create_todo"),
    (re.compile(r"^\s*(?:please\s+)?add\s+(?:a\s+|\d+\s+|two\s+|three\s+)?(?:new\s+)?tasks?\b"), "create_todo"),
    (re.compile(r"^\s*(?:what|which|show|list|read)\b.*\b(?:tasks?|todos?|to-dos?)\b"), "query_todos"),
]


def _route_intent(span, current_view: str) -> tuple[str | None, str, bool, bool]:
    """Route a span to an (action_name, domain, domain_inferred, domain_material) tuple.

    domain_inferred=True means we fell back to view context (lower confidence).
    domain_material=True means the *guessed* domain was actually load-bearing in
    picking the action (INTENT_MAP had a domain-specific entry for this verb, e.g.
    ("delete", "todo") vs ("delete", "calendar") give different actions). Verbs
    that map via the domain-agnostic (lemma, None) entry — "buy", "call", "email",
    etc. always mean create_todo regardless of domain — have domain_material=False,
    since the domain guess played no role in resolving them.
    """
    span_text = span.text.lower()
    span_words = set(re.findall(r"\w+", span_text))

    # --- Phrase-level overrides (checked before verb heuristics) ---
    for pat, action in _ROUTE_OVERRIDES:
        if pat.search(span_text):
            return action, ("todo" if "todo" in action else "calendar"), False, False

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

    def _maps_to_action(lemma: str) -> tuple[str | None, bool]:
        """Returns (action_name, domain_was_material) — see docstring above."""
        domain_specific = INTENT_MAP.get((lemma, domain))
        if domain_specific:
            return domain_specific, True
        generic = INTENT_MAP.get((lemma, None))
        if generic:
            return generic, False
        return None, False

    # WH-word check first — "what/when/how many" sentences are queries regardless
    # of what other INTENT_MAP verbs appear in the span (e.g. "what's on my schedule")
    _WH_RE = re.compile(r"^(what|when|how\s+many|which|show|list|read)\b", re.IGNORECASE)
    if _WH_RE.search(span_text.strip()):
        wh_action = "query_schedule" if domain == "calendar" else "query_todos"
        return wh_action, domain, False, True  # WH-word is explicit, not inferred

    root_verb = None
    action = None
    domain_material = False

    # Pass 1: ROOT verb that directly maps
    for tok in span:
        if tok.dep_ == "ROOT" and tok.pos_ in ("VERB", "AUX"):
            mapped, material = _maps_to_action(tok.lemma_)
            if mapped:
                root_verb = tok
                action = mapped
                domain_material = material
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
                mapped, material = _maps_to_action(tok.lemma_)
                if mapped:
                    root_verb = tok
                    action = mapped
                    domain_material = material
                    break

    # Pass 4: any token with known action lemma (noun-verb ambiguity, ADJ mis-tags, etc.)
    if action is None:
        for tok in span:
            mapped, material = _maps_to_action(tok.lemma_)
            if mapped:
                root_verb = tok
                action = mapped
                domain_material = material
                break

    # Pass 5: STT homophone fallback, ROOT position only. A preposition/adverb
    # can't legitimately be a well-formed sentence's syntactic ROOT — when spaCy
    # lands there, it's a signal the transcript is a fragment, usually because
    # Whisper misheard an imperative verb as its homophone (e.g. "buy" -> "by").
    # Restricted to ROOT to avoid false positives on legitimate uses elsewhere in
    # the sentence (e.g. "meeting by 3pm", where "by" is a prep, not the ROOT).
    if action is None:
        for tok in span:
            if tok.dep_ != "ROOT":
                continue
            alias = _STT_HOMOPHONE_VERBS.get(tok.lower_)
            if alias:
                mapped, material = _maps_to_action(alias)
                if mapped:
                    root_verb = tok
                    action = mapped
                    domain_material = material
            break  # only one ROOT per span

    if action is None:
        # No-verb fallbacks: WH-word query
        if re.match(r"\b(what|when|how many|which|show|list|read)\b", span_text):
            action_fallback = "query_schedule" if domain == "calendar" else "query_todos"
            return action_fallback, domain, domain_inferred, True
        return None, domain, domain_inferred, True

    return action, domain, domain_inferred, domain_material


# ---------------------------------------------------------------------------
# Phase 4: Slot filling
# ---------------------------------------------------------------------------


def _in_temporal(tok, temporal_spans: list[tuple[int, int]]) -> bool:
    return any(start <= tok.idx < end for start, end in temporal_spans)


_PRONOUN_TITLES = frozenset({"me", "i", "it", "you", "us", "them", "that", "this", "task", "tasks", "todo", "reminder", "list"})

_TODO_LEAD = re.compile(
    r"^\s*(?:(?:please|hey|ok|okay)[,\s]+)?"
    r"(?:remind me(?:\s+(?:tomorrow|today|tonight|later|on\s+\w+|next\s+\w+|this\s+\w+))?\s+(?:to|about|that)\s+"
    r"|add\s+(?:a\s+|the\s+|\d+\s+|two\s+|three\s+)?(?:new\s+)?tasks?\s*(?:to|:|-|—)?\s*(?:my\s+list\s*)?(?:to\s+)?"
    r"|(?:i\s+)?(?:need|have|want|got)\s+to\s+"
    r"|(?:add|put)\s+(?:to\s+(?:my|the)\s+(?:\w+\s+)?list\s*:?\s*)"
    r"|(?:make|create)\s+(?:a\s+)?(?:todo|task|reminder)\s+(?:to\s+|for\s+|:\s*)?"
    r"|(?:todo|task|reminder)\s*:\s*)",
    re.IGNORECASE,
)
_TODO_TRAIL = re.compile(
    r"\s+(?:on|to)\s+(?:my|the)\s+(?:\w+\s+)?list\s*$|\s+(?:due|by|for|on)\s+(?:tomorrow|today|tonight|next\s+\w+|this\s+\w+|\w+day|the\s+\d+\w*)\s*$",
    re.IGNORECASE,
)


def _todo_titles_from_text(text: str, temporal_spans, span) -> list[str]:
    """'remind me tomorrow to send the syllabus to Guri' → ['send the syllabus to Guri'];
    'add buy milk, eggs and bread to my list' → ['buy milk', 'buy eggs', 'buy bread']."""
    t = text.strip().rstrip(".!?")
    m = _TODO_LEAD.match(t)
    if not m:
        # "put milk and bananas on the groceries list" / "add X to my list"
        m2 = re.match(r"^\s*(?:add|put)\s+(.+?)\s+(?:on|to)\s+(?:my|the)\s+(?:\w+\s+)?list\s*$", t, re.IGNORECASE)
        if not m2:
            return []
        body = m2.group(1)
    else:
        body = t[m.end():]
        body = _TODO_TRAIL.sub("", body)
    body = re.sub(r"\s+(?:due|by)\s+.*$", "", body, flags=re.IGNORECASE).strip(" ,;:")
    if not body:
        return []
    return split_items(body, drop=_PRONOUN_TITLES)[:10]


# "put it on the groceries list" / "tag it as coursework" — the user naming a
# tag outright. Resolved against the real palette by CreateTodoAction; a word
# that isn't a tag is dropped there.
_TODO_TAG_PATTERNS = (
    re.compile(r"\b(?:on|to)\s+(?:my|the)\s+([\w-]+)\s+list\b", re.IGNORECASE),
    re.compile(r"\btag(?:ged)?\s+(?:it\s+)?(?:as|with)\s+([\w-]+)", re.IGNORECASE),
    re.compile(r"\bunder\s+([\w-]+)\s*$", re.IGNORECASE),
)
# List names, not tags.
_NOT_TAG_WORDS = frozenset({"today", "general", "todo", "to-do", "task", "tasks",
                            "my", "the", "this", "that", "shopping"})


def _todo_tags_from_text(text: str) -> list[str]:
    """Tag names the user said out loud, if any."""
    tags: list[str] = []
    for pattern in _TODO_TAG_PATTERNS:
        m = pattern.search(text)
        if m:
            word = m.group(1).strip().lower()
            if word and word not in _NOT_TAG_WORDS and word not in tags:
                tags.append(word)
    return tags


def _extract_title(span, temporal_spans: list[tuple[int, int]]) -> str | None:
    """Extract the best title from a span, blocking temporal token positions."""
    # Priority 1: noun chunk containing dobj of root verb
    dobj_chunks = [
        chunk for chunk in span.noun_chunks
        if chunk.root.dep_ == "dobj"
        and not any(_in_temporal(t, temporal_spans) for t in chunk)
    ]
    for c in dobj_chunks:
        t = _clean_title(c.text)
        if t:
            return t

    # Priority 2: noun chunk containing pobj (object of preposition)
    pobj_chunks = [
        chunk for chunk in span.noun_chunks
        if chunk.root.dep_ == "pobj"
        and not any(_in_temporal(t, temporal_spans) for t in chunk)
    ]
    for c in pobj_chunks:
        t = _clean_title(c.text)
        if t:
            return t

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
    text = " ".join(words)          # may be empty when the chunk was only a verb ("book")
    text = re.sub(r"\s+", " ", text)
    return text


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
            # "set a meeting with Ravid" → title "meeting with Ravid" instead of a bare placeholder
            if slots.get("title", "").lower() in {"meeting", "set meeting", "event", "appointment", "call", "lunch", "dinner", "coffee", "zoom"}:
                slots["title"] = f"{slots['title'].replace('set ', '')} with {' and '.join(attendees)}"

    elif action_name == "update_event":
        # F10: the mutation phrase delimits multi-word titles noun-chunking
        # drops ("reschedule HAIRCUT to this weekend"); the generic-target
        # veto still judges whatever is captured.
        m10 = re.search(r"\b(?:reschedule|move|push|shift|postpone)\s+(.+?)\s+"
                        r"(?:to|until|for)\b", span.text, re.IGNORECASE)
        if m10:
            cand = _clean_title(m10.group(1))
            if cand and cand.lower() not in _CALENDAR_SIGNALS:
                slots.setdefault("match_title", cand)
        # Detect whether this is an extend/shorten action (vs. a move/reschedule)
        is_extend = any(tok.lemma_.lower() in _EXTEND_VERBS for tok in span)

        if is_extend:
            # Extend/shorten semantics:
            #   "at X"  → match_start_time  (which event to find)
            #   "to Y"  → new_end_time      (what to change)
            #   "on D"  → match_date        (which day to look on)
            # Generic calendar words ("event", "appointment") are not real titles here.
            if title and title.lower() not in _CALENDAR_SIGNALS:
                slots["match_title"] = _extend_title_with_whom(span.text, title)
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

            # The dependency route above is fragile: "rename gym to workout"
            # yields nothing, and "with Tal" or a two-word name derails it
            # ("… to robotics sync" came back as just "robotics"). When the
            # sentence says "rename X to/as Y" outright, read it literally.
            if not new_title_from_rename:
                m = _RENAME_RE.search(span.text)
                if m:
                    old_name, new_name = m.group(1).strip(), m.group(2).strip()
                    # "rename the meeting to 3pm" is a reschedule, not a rename.
                    _probe = _extract_temporal(new_name, datetime.date.today())
                    if new_name and not _probe.get("start_time"):
                        new_title_from_rename = _clean_title(new_name)
                        if old_name:
                            slots["match_title"] = _extend_title_with_whom(span.text, _clean_title(old_name))

            if new_title_from_rename:
                slots["new_title"] = new_title_from_rename
                if not slots.get("match_title"):
                    root_chunks = [
                        c for c in span.noun_chunks
                        if c.root.dep_ == "ROOT" and not any(_in_temporal(t, temporal_spans) for t in c)
                    ]
                    if root_chunks:
                        slots["match_title"] = _extend_title_with_whom(span.text, _clean_title(root_chunks[0].text))
                    elif title and title != new_title_from_rename:
                        slots["match_title"] = _extend_title_with_whom(span.text, title)
            else:
                if title:
                    slots["match_title"] = _extend_title_with_whom(span.text, title)

            if temporal.get("start_time"):
                slots["new_start_time"] = temporal["start_time"]
            if temporal.get("end_time"):
                slots["new_end_time"] = temporal["end_time"]
            if temporal.get("date"):
                slots["new_date"] = temporal["date"]

    elif action_name == "delete_event":
        # A bare calendar word is a placeholder rather than a name ("delete the
        # event at 6pm"), and deleting on one could take any event — so it is
        # dropped and the date/time has to identify the event instead.
        #
        # Noun chunking, though, reduces "the meeting with Ima" to that same bare
        # "meeting", and there the person is the whole identity of the event.
        # Keep such a title once the name is recovered, and only then: with no
        # name to pin it down, empty slots (answered with "I couldn't find …")
        # beat deleting somebody else's meeting.
        titled, names_a_person = _title_with_person(span.text, title)
        if titled and (names_a_person or titled.lower() not in _CALENDAR_SIGNALS):
            slots["match_title"] = titled
        # F10: "delete WEDDING REHEARSAL from my calendar" — the phrase
        # delimits what chunking dropped; the veto judges the capture.
        if not slots.get("match_title"):
            m10 = re.search(r"\b(?:delete|remove|cancel|drop)\s+(.+?)\s+"
                            r"from\s+(?:my|the)\s+(?:calendar|schedule)\b",
                            span.text, re.IGNORECASE)
            if m10:
                cand = _clean_title(m10.group(1))
                if cand and cand.lower() not in _CALENDAR_SIGNALS:
                    slots["match_title"] = cand
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
        # _SCOPE_PHRASES knows "today", "tomorrow" and "week" and nothing else,
        # so a named day — "what do I have on friday" — matched no phrase and
        # silently kept the default. The same extractor that dates an event
        # resolves it, so the two agree about what Friday means.
        if scope != "week" and temporal.get("date"):
            slots["date"] = temporal["date"]
        # Query type
        if any(w in span_lower for w in ("first", "earliest")):
            slots["query_type"] = "first"
        elif any(w in span_lower for w in ("next", "upcoming")):
            slots["query_type"] = "next"
        elif any(w in span_lower for w in ("how many", "count", "number")):
            slots["query_type"] = "count"
        else:
            slots["query_type"] = "full"

    elif action_name == "create_todo" and temporal.get("start_time") and re.search(r"\bremind me (?:about|of)\b", span.text, re.I):
        # "remind me about X at 9 am" is a calendar event, not a task
        slots["_reroute"] = "create_event"
        slots["title"] = re.sub(r"^\s*remind me (?:about|of)\s+(?:the\s+|my\s+)?", "", span.text, flags=re.I)
        slots["title"] = re.sub(r"\s+(?:tomorrow|today|tonight|on\s+\w+|next\s+\w+|this\s+\w+|at\s+[\d:.]+\s*(?:am|pm)?).*$", "", slots["title"], flags=re.I).strip() or "reminder"
        if temporal.get("date"):
            slots["date"] = temporal["date"]
        slots["start_time"] = temporal["start_time"]
        slots["end_time"] = temporal.get("end_time") or ""
    elif action_name == "create_todo":
        # Phrase-level extraction first: dependency heuristics produce "me"
        # for "remind me to …" and "task" for "add a task to …".
        phrase_titles = _todo_titles_from_text(span.text, temporal_spans, span)
        if phrase_titles:
            slots["titles"] = phrase_titles
        elif title and title.lower() not in _PRONOUN_TITLES:
            # The noun-chunk fallback keeps only the object: "call the dentist"
            # became a task called "dentist". Put the verb back so the task says
            # what to do rather than what it is about.
            verb = lead_verb(span.text.strip())
            if verb and not title.lower().startswith(verb.lower()):
                title = f"{verb} {title}"
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
        tags = _todo_tags_from_text(span.text)
        if tags:
            slots["tags"] = tags

    elif action_name in ("delete_todo", "complete_todo", "update_todo"):
        # F6c: the completion funnel "mark X as done" delimits X by the
        # phrase itself — noun-chunk extraction returns nothing when X is
        # verb-led ("mark WALK THE DOG as done"), so capture it directly.
        m6 = re.search(r"\bmark\s+(.+?)\s+(?:as\s+)?(?:done|complete[d]?|finished)\b",
                       span.text, re.IGNORECASE)
        if m6 and not slots.get("match_title"):
            slots["match_title"] = _clean_title(m6.group(1))
        # F10: mutation phrases delimit multi-word titles noun-chunking
        # drops ("remove BUY SOCKS from my list", "delete WALK THE DOG").
        if not slots.get("match_title"):
            m10 = re.search(r"\b(?:delete|remove|cancel|drop)\s+(.+?)\s+"
                            r"from\s+(?:my|the)\s+(?:\w+\s+)?(?:list|tasks?|to-?dos?)\b",
                            span.text, re.IGNORECASE)
            if m10:
                slots["match_title"] = _clean_title(m10.group(1))
        # F7b: "set X as <level> priority" — phrase-delimited, like m6
        m7 = re.search(r"\b(?:set|make)\s+(.+?)\s+as\s+(high|medium|low)\s+priority\b",
                       span.text, re.IGNORECASE)
        if m7:
            if not slots.get("match_title"):
                slots["match_title"] = _clean_title(m7.group(1))
            slots["priority"] = m7.group(2).lower()
            # the rename extractor reads "as high priority" as a new NAME —
            # a priority change must never retitle the task
            slots.pop("new_title", None)
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
                slots["match_title"] = _extend_title_with_whom(span.text, candidate)
        elif title:
            slots["match_title"] = _extend_title_with_whom(span.text, title)

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
                        cand = _clean_title(pobj_chunks[0].text)
                        # F7b: "set X as HIGH PRIORITY" — the priority phrase
                        # is a level, never the task's new name
                        if not re.match(r"^(?:high|medium|low)\s+priority$", cand, re.I):
                            slots["new_title"] = cand
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

    # Two distinct clock times in one span usually means two events ("lunch at noon
    # and coffee at 9") — the single-intent slots can't represent that; force hybrid.
    if action_name == "create_event" and temporal.get("_n_times", 0) >= 2 and not temporal.get("end_time"):
        multiplier *= 0.7

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
        dropped_spans = 0

        for span in spans:
            # Phase 2: Temporal extraction
            temporal = _extract_temporal(span.text, today)

            # Phase 3: Intent/domain routing
            action_name, _, domain_inferred, domain_material = _route_intent(span, current_view)
            if action_name is None:
                if len(spans) == 1:
                    raise RuleParserSkip(f"No action matched for: {span.text!r}")
                # Multi-span: skip unmatched span, continue — but remember it: part of
                # the command was ignored, so the LLM should get a look (hybrid).
                dropped_spans += 1
                continue

            # Phase 4: Slot filling
            _tt = re.sub(r"(\d)\.(\d)", r"\1:\2", span.text)   # 4.30 pm → 4:30 pm
            temporal["_n_times"] = len(re.findall(
                r"(?<![\d:])(?:\d{1,2}:\d{2}\s*(?:am|pm|a\.m\.|p\.m\.)?|\d{1,2}\s*(?:am|pm|a\.m\.|p\.m\.)|noon|midnight|\d{1,2}\s*o'clock|at\s+\d{1,2}(?![\d:]))\b",
                _tt, re.I))
            slots = _fill_slots(span, action_name, temporal, current_view)
            if "_reroute" in slots:
                action_name = slots.pop("_reroute")

            # Phase 5: Anaphora resolution
            slots, used_anaphora = _resolve_anaphora(slots, action_name, self._memory)
            temporal["_used_anaphora"] = used_anaphora
            temporal["_domain_inferred"] = domain_inferred

            # Phase 6: Confidence + validation
            missing = _compute_missing_slots(action_name, slots)
            # Only penalize the guessed domain when it was actually load-bearing in
            # picking the action (domain_material) — a domain-agnostic verb like
            # "buy"/"call"/"email" maps to create_todo regardless of domain, so an
            # unresolved domain guess shouldn't dock confidence on those.
            confidence = _compute_confidence(
                action_name, slots, temporal, domain_inferred and domain_material, used_anaphora
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

        overall_confidence = min(confidences) * (0.7 if dropped_spans else 1.0)

        return RuleParseResult(
            confidence=overall_confidence,
            intents=all_intents,
            missing_slots=all_missing,
            raw_slots=all_raw_slots,
            transcript=normalized,
            dropped_spans=dropped_spans,
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
