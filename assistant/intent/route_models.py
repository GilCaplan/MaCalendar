"""Q10's model tier — the routing fallthrough (Gil's two-subsystem design).

Stage-2 routing is two tiered subsystems: OPERATION (new/edit/remove/
complete/query) and KIND (event/task). The RULES tier — route overrides +
the verb table — answers first and keeps every confident answer it has
today. This module is the tier below: two tiny one-vs-rest logistic models
(hand features, weights fit OFFLINE on dataset B's TRAIN half only — never
test, never personal data — by scripts/fit_route_models.py, which emits
`route_model_weights.json` next to this file). They fire only where the
rules found nothing, and only when both margins clear a floor; otherwise
the old behavior stands (skip → the deep track).

A model-routed action is an INFERENCE and is billed like one: the caller
routes it through the domain-inferred confidence channel (×0.85), so the
front-door threshold still guards every commit.
"""
from __future__ import annotations

import json
import math
import pathlib
import re

_W = None
_WEIGHTS_PATH = pathlib.Path(__file__).with_name("route_model_weights.json")

OPS = ("new", "edit", "remove", "complete", "query")
# operation × kind → action (query splits by kind; complete is task-only)
_COMPOSE = {
    ("new", "event"): "create_event", ("new", "task"): "create_todo",
    ("edit", "event"): "update_event", ("edit", "task"): "update_todo",
    ("remove", "event"): "delete_event", ("remove", "task"): "delete_todo",
    ("complete", "task"): "complete_todo", ("complete", "event"): "complete_todo",
    ("query", "event"): "query_schedule", ("query", "task"): "query_todos",
}
# margins below these floors mean "not sure enough to guess" → old behavior
# floors tightened after the first dual-gate (F11: 26 new real-pool commits
# at ~77% correct = -1.0 adjusted; the models must speak only when SURE)
OP_MARGIN_FLOOR = 2.5
KIND_MARGIN_FLOOR = 1.5


def op_features(text: str) -> "list[float]":
    low = text.lower()
    def has(p): return 1.0 if re.search(p, low) else 0.0
    return [
        1.0,
        has(r"^\s*(?:add|book|schedule|create|put|set up|plan|make|new)\b"),
        has(r"\b(?:remind me|need to|have to|remember to|don'?t forget)\b"),
        has(r"^\s*(?:delete|remove|cancel|drop|clear|erase|scratch)\b"),
        has(r"\bfrom\s+(?:my|the)\b"),
        has(r"^\s*(?:move|reschedule|change|update|push|shift|postpone|rename|extend|shorten)\b"),
        has(r"\bto\s+(?:\d|noon|midnight|next|this|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b"),
        has(r"\b(?:as\s+)?(?:done|complete[d]?|finished)\b|\bcheck(?:ed)?\s+off\b|\balready did\b|\bi'?m done\b"),
        has(r"^\s*(?:what|which|when|show|list|tell me|do i have|how many|is there|what'?s)\b"),
        has(r"\bmy (?:schedule|day|week|agenda|calendar)\b"),
        has(r"\?\s*$"),
        has(r"\bat\s+\d|(?:\d|\b)(?:am|pm)\b"),
        has(r"\bas\s+(?:high|medium|low)\s+priority\b"),
        has(r"\binstead of\b|\bcall it\b|\brename\b"),
        has(r"\bevery\b|\bdaily\b|\bweekly\b"),
        has(r"^\s*(?:buy|get|pick up|grab|order)\b"),
        # F12/K3b: class-targeted features for the starved operations
        has(r"\boff\s+(?:my|the)\b|\bget rid of\b|\bno longer\b|\bwipe\b|\bstrike\b"),   # remove-speak
        has(r"^\s*(?:am i free|is there|any(?:thing)?\b|do i\b|have i\b)"),                     # query openers 2
        has(r"\bfree\b|\bbusy\b|\bavailable\b|\bcoming up\b|\bplanned\b"),               # availability speak
        has(r"^\s*(?:cross|take)\s+.+\s+off\b"),                                                # "cross X off"
        has(r"\bdid i\b|\bhave i\s+(?:done|finished)\b"),                                      # done-query guard
    ]


def kind_features(text: str) -> "list[float]":
    low = text.lower()
    def has(p): return 1.0 if re.search(p, low) else 0.0
    return [
        1.0,
        has(r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b|\bat\s+\d{1,2}\b|\b(?:noon|midnight|tonight|morning|evening|afternoon)\b"),
        has(r"\b(?:today|tomorrow|tonight)\b|\b(?:next|this|on)\s+(?:week|month|monday|tuesday|wednesday|thursday|friday|saturday|sunday|weekend)\b"),
        has(r"\bremind(?:er)?s?\b|\bnotify\b"),
        has(r"\bremind\s+\w+\s+to\b"),
        has(r"\b(?:meeting|appointment|party|dinner|lunch|brunch|breakfast|birthday|anniversary|wedding|concert|interview|class|lesson|conference|session|call)\b"),
        has(r"\b(?:list|to-?do|task|shopping)\b"),
        has(r"\b(?:buy|get|pick up|purchase|groceries)\b"),
        has(r"\b(?:calendar|schedule|book|invite)\b"),
        has(r"\bwith\s+[a-z]+\b"),
        has(r"\bevery\b"),
        1.0 if len(text.split()) > 9 else 0.0,
        # F12: parity with K1's proven feature set
        has(r"\b(?:shiur|recital|ceremony|festival|get-?together|funeral|checkup|check-?up|haircut|workout|gym|run|practice)\b"),
        has(r"\bat\s+\d{1,2}\b"),
        has(r"\b(?:errand|chore|homework|assignment|laundry|dishes|email|form|bill|report)\b"),
        has(r"\bfor\s+(?:me|us)\b|\bmy\s+(?:place|house|office)\b"),
    ]


def _load():
    global _W
    if _W is None:
        _W = json.loads(_WEIGHTS_PATH.read_text())
    return _W


def _scores(weights: dict, x: "list[float]") -> "dict[str, float]":
    return {k: sum(a * b for a, b in zip(w, x)) for k, w in weights.items()}


def _top2(sc: "dict[str, float]"):
    o = sorted(sc.items(), key=lambda p: -p[1])
    return o[0][0], (o[0][1] - o[1][1]) if len(o) > 1 else math.inf


def route(text: str) -> "str | None":
    """The composed action, or None when either model isn't sure enough."""
    try:
        W = _load()
    except Exception:
        return None
    op, op_margin = _top2(_scores(W["operation"], op_features(text)))
    kind, kind_margin = _top2(_scores(W["kind"], kind_features(text)))
    if op_margin < OP_MARGIN_FLOOR or kind_margin < KIND_MARGIN_FLOOR:
        return None
    return _COMPOSE.get((op, kind))
