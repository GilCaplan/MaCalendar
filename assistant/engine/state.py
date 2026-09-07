"""The engine's shared state — the ONLY thing stages exchange.

These dataclasses are the frozen inter-stage contract (`DOCUMENTATION/ENGINE.md`
describes which stage reads and writes which field). A stage receives an
EngineState, mutates only the fields its contract grants it, and returns the
same object. Nothing else passes between stages: no imports of another stage's
internals, no side-channels.

`tests/unit/test_engine_contracts.py` pins every field name here. Changing a
field is changing the contract every stage was built against — the test going
red on an "innocent rename" is the point.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Stage names, in pipeline order. The orchestrator wires them; step 6 may jump
# execution back to one of them by name (its blame router only ever names one
# of these).
STAGES = (
    "intake",      # step 0 — queue + coalescing (lives in the orchestrator)
    "transcript",  # step 1 — vocabulary repair + confidence gate
    "segment",     # step 2 — split into typed items (events / tasks / review)
    "decompose",   # step 3 — recursive per-item breakdown
    "validate",    # step 4 — format rules, text repair, observance gate
    "generate",    # step 5 — items → concrete intents (rule parser else LLM)
    "crosscheck",  # step 6 — raw text vs. produced objects, loop-back
    "label",       # step 7 — category / tag consistency
)

# What an item is *about*. Edits and deletes of an event are kind "event" —
# kind is the domain the item concerns, not the verb; the verb lands in
# Item.action at step 5.
ITEM_KINDS = ("event", "task", "review", "other")


@dataclass
class Fix:
    """One deterministic correction, applied by a stage and shown in the trace."""

    stage: str    # which stage applied it (a STAGES name)
    rule: str     # the named rule, e.g. "past_date_bump" — greppable
    before: str
    after: str
    note: str = ""

    def human(self) -> str:
        core = f"{self.before}→{self.after}" if self.before or self.after else self.rule
        return f"{core} ({self.note})" if self.note else core


@dataclass
class Item:
    """One independent thing the speaker asked for.

    Ids encode decomposition: "item_1" split by step 3 becomes "item_1-1",
    "item_1-2" (depth is bounded there, not here).
    """

    id: str
    kind: str                 # one of ITEM_KINDS
    text: str                 # the words for this item; stages may repair it
    slots: dict = field(default_factory=dict)   # structured hints: quantity,
                                                # recurrence, attendees, times…
    action: str | None = None                   # step 5: registry action name
    intent: Any = None                          # step 5: the BaseIntent
    blocked: str | None = None                  # step 4: refusal reason (never
                                                # executed; reported honestly)
    labels: dict = field(default_factory=dict)  # step 7: category / tag


@dataclass
class ExecutedAction:
    """One action the commit step actually ran, tied back to its item."""

    item_id: str
    action: str
    message: str
    ok: bool
    # ("event" | "todo", row id, action name, execution index) — exactly the
    # tuple the command memory records, now attributed per item, which is what
    # prevents the row-75 class of cross-item corruption.
    record: tuple | None = None


@dataclass
class CheckFinding:
    """One mismatch step 6 found between the raw text and what was produced."""

    type: str            # "missing" | "extra" | "wrong_fields"
    item_id: str | None  # the produced item concerned, when there is one
    detail: str
    blamed_stage: str    # a STAGES name — assigned by the deterministic router


@dataclass
class EngineState:
    """Everything about one command's journey through the engine."""

    # -- set at intake, read-only afterwards --------------------------------
    raw_text: str                 # exactly what arrived
    source: str = "test"          # "mac" | "ios" | "test"
    current_view: str = "month"
    supports_edit: bool = False   # client can render a needs_edit round-trip
    supports_confirm: bool = False  # client can render a confirm_create prompt
    mode: str = "foreground"      # "foreground" | "background" (fast-track
                                  # verify pass runs the same stages in
                                  # background mode: compare, never re-commit)

    # -- step 1 -------------------------------------------------------------
    text: str = ""                          # working transcript after repair
    corrections: list = field(default_factory=list)   # vocab fixes (client shape)
    needs_edit: list = field(default_factory=list)    # doubtful words gating

    # -- steps 2/3 ----------------------------------------------------------
    items: list = field(default_factory=list)         # list[Item], ordered

    # -- commit -------------------------------------------------------------
    executed: list = field(default_factory=list)      # list[ExecutedAction]
    messages: list = field(default_factory=list)      # reply fragments, in order
    refresh: str = ""                                 # "events"|"todos"|"both"|""

    # -- step 6 -------------------------------------------------------------
    findings: list = field(default_factory=list)      # list[CheckFinding]
    retries: dict = field(default_factory=dict)       # stage name → re-entries
    mistakes: list = field(default_factory=list)      # carried into retried
    #: texts FastRule has already judged this command (Q12): it is
    #: deterministic, so re-asking the same words wastes a retry that
    #: cannot change its mind.
    asked_fastrule: set = field(default_factory=set)
                                                      # stages' prompts

    # -- bookkeeping (orchestrator-owned) -----------------------------------
    fixes: list = field(default_factory=list)         # list[Fix], all stages
    trace: Any = None                                 # assistant.trace.Trace
    parse_path: str = "deep"      # "fast" | "deep" | "error" | "ignored"
    llm_ms: int = 0
    rule_confidence: float = -1.0  # the fast-track score, recorded so the
                                   # routing threshold can be calibrated from
                                   # outcomes (-1: the rules never scored it)
    ignored: bool = False         # trivial transcript: not parsed, not remembered
    memory_id: int | None = None
    verify_token: str | None = None
    pending_id: int | None = None

    def add_fix(self, stage: str, rule: str, before: str = "", after: str = "",
                note: str = "") -> Fix:
        fx = Fix(stage=stage, rule=rule, before=str(before), after=str(after), note=note)
        self.fixes.append(fx)
        return fx

    def next_item_id(self) -> str:
        return f"item_{len(self.items) + 1}"
