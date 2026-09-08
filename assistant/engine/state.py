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
# One entry per BOX in the chain (assistant/engine/ARCHITECTURE.md).
# Re-cut 2026-09-08 with the rewire: decompose+validate became one box,
# generate became fastrule (the stage IS object-making), crosscheck became
# llmjudge, and label moved inside commit.
STAGES = (
    "ingest",              # X0 → X1  queue + coalescing + vocabulary repair
    "transcript",          #          the repair half, still its own Stage
    "segment",             # X1 → X2  split into (action, time, tag) items
    "decompose_validate",  # X2 → X3  atomise, repair, observance gate
    "fastrule",            # X3 → X4  items → calendar / to-do objects
    "llmjudge",            # X4 →     judge, and rewrite-and-loop if unhappy
    "commit",              #          write + label, one step
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
    text: str                 # the ACTION words for this item; stages may
                              # repair it. Since segmentation returns
                              # (action, time, tag), the time is NOT in here —
                              # it is in `time`. Use `spoken()` when you need
                              # the command as the speaker said it.
    time: str | None = None   # step 2: the time reference AS SPOKEN, never
                              # resolved ("next friday", not a date). None when
                              # the implementation does not separate it.
    slots: dict = field(default_factory=dict)   # structured hints: quantity,
                                                # recurrence, attendees, times…
    action: str | None = None                   # step 5: registry action name
    intent: Any = None                          # step 5: the BaseIntent
    blocked: str | None = None                  # step 4: refusal reason (never
                                                # executed; reported honestly)
    labels: dict = field(default_factory=dict)  # step 7: category / tag

    def spoken(self) -> str:
        """This item as the speaker said it — the action WITH its time.

        Anything that parses an item for a date or a duration wants this, not
        `text`. `FastRule` and the LLM parser both extract the time from the
        string they are given, so handing them `text` alone silently produced
        events with no time at all.

        The date FLOOR is left out when the speaker never said it: SPEC defaults
        an untimed item to "today", and pasting that in would put a word in the
        title that nobody uttered.
        """
        when = (self.time or "").strip()
        if not when:
            return self.text
        keep = [w for w in when.split()
                if w.lower() != "today" or "today" in self.text.lower()]
        tail = " ".join(keep).strip()
        if not tail or tail.lower() in self.text.lower():
            return self.text
        return f"{self.text} {tail}"


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

    # -- set at ingest, read-only afterwards --------------------------------
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
    #: what FastRule concluded about the WHOLE command at the front door,
    #: even when it declined to commit (Gil, 2026-09-07: "run FastRule but
    #: don't commit, keep it running through the system to the next stage").
    #: Its work used to be discarded here and the deep track started cold;
    #: the stages below are LLM calls, and this is the context that makes
    #: them better-informed. Shape: {"reason", "reason_class", "confidence",
    #: "actions"} — never the intent objects, which the deep track rebuilds.
    fastrule_verdict: "dict | None" = None
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
