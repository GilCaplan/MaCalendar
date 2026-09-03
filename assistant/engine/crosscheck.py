"""Step 6 — cross-check what was produced against what was said.

Contract (see DOCUMENTATION/ENGINE.md):
  reads   state.raw_text, state.text, state.items, state.executed
  writes  state.findings (CheckFinding), state.mistakes, trace steps (VERIFY)
  run(state, cfg) NEVER touches the database or loops itself — the
  orchestrator owns the loop-back (foreground, pre-commit) and the patch
  application (background, post-commit).

The design splits the work by who is good at it:

  1. EXTRACT, don't judge. The LLM lists the separate things the RAW text
     asks for (schema-constrained). Small models extract far more reliably
     than they self-evaluate — the model is never asked "is this right?".
  2. COMPARE deterministically. Code diffs the extraction against the
     produced items: an extracted ask nothing covers is `missing`; a produced
     create nothing asked for is `extra`.
  3. BLAME by mismatch type, never by LLM opinion: the fixed BLAME map names
     the stage to re-run, and the model has no say in it.

On transport failure (model offline, disabled) there are simply no findings —
a command must never fail because its checker could not run.
"""

from __future__ import annotations

import re

from assistant.engine.state import CheckFinding, EngineState

# The deterministic blame router: mismatch type → the stage re-run. The model
# never picks the stage.
BLAME = {
    "missing": "segment",
    "extra": "segment",
    "wrong_fields": "generate",
    "format": "validate",
}
MAX_REENTRIES = 3   # total per command, all stages combined

_EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "asks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["event", "task", "review"]},
                    "words": {"type": "string"},
                },
                "required": ["kind", "words"],
            },
        },
    },
    "required": ["asks"],
}

_EXTRACT_SYSTEM = """You read ONE voice command to a calendar assistant and list \
the separate things it asks for. For each: kind ("event" books or changes \
something on the calendar, "task" is a to-do item, "review" asks what is \
scheduled) and the speaker's own words for it (copy, never rephrase). \
"buy 5 apples" is ONE ask. People joined by "and" share one ask. Do not \
invent asks and do not list one twice. \
Return JSON: {"asks": [{"kind": ..., "words": ...}, ...]}"""

_STOPWORDS = frozenset(
    "a an the and or to for of on at in with my me i please add book schedule "
    "set remind buy get make new tomorrow today tonight".split())


def _tokens(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9']+", (text or "").lower())
            if w not in _STOPWORDS and len(w) > 1}


def _overlap(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def extract_asks(state: EngineState, cfg) -> "list[tuple[str, str]] | None":
    """The LLM's reading of the raw text: [(kind, words), …]. None = the model
    could not be consulted (offline/disabled) — no findings can be made."""
    from assistant.engine import llm as _llm

    try:
        out, ms = _llm.call_json(cfg, _EXTRACT_SYSTEM,
                                 f"The command: {state.raw_text}", _EXTRACT_SCHEMA)
        state.llm_ms += ms
    except Exception:
        return None
    asks = []
    for d in (out.get("asks") or []):
        if not isinstance(d, dict):
            continue
        kind = str(d.get("kind", "")).strip()
        words = str(d.get("words", "")).strip()
        if kind in ("event", "task", "review") and words:
            asks.append((kind, words))
    return asks or None


def _produced(state: EngineState) -> list:
    """The creates the engine decided on — the comparable surface. Updates,
    deletes and completes are judged by their own not-found honesty; queries
    map to review asks."""
    out = []
    for it in state.items:
        if it.intent is None or it.blocked:
            continue
        if it.action in ("create_event", "create_todo"):
            kind = "event" if it.action == "create_event" else "task"
            title = getattr(it.intent, "title", "") or it.text
            out.append((it, kind, _tokens(title) | _tokens(it.text)))
        elif it.action == "query_schedule":
            out.append((it, "review", _tokens(it.text)))
    return out


def run(state: EngineState, cfg) -> EngineState:
    from assistant.trace import VERIFY

    asks = extract_asks(state, cfg)
    if asks is None:
        return state

    produced = _produced(state)
    unmatched_asks = []
    matched_items = set()
    for kind, words in asks:
        toks = _tokens(words)
        best, best_score = None, 0.0
        for it, pkind, ptoks in produced:
            if id(it) in matched_items or pkind != kind:
                continue
            score = _overlap(toks, ptoks)
            if score > best_score:
                best, best_score = it, score
        if best is not None and best_score >= 0.34:
            matched_items.add(id(best))
        else:
            unmatched_asks.append((kind, words))

    findings: list = []
    for kind, words in unmatched_asks:
        findings.append(CheckFinding(
            type="missing", item_id=None,
            detail=f"the words ask for a {kind} — “{words}” — but nothing produced covers it",
            blamed_stage=BLAME["missing"]))
    for it, pkind, _ptoks in produced:
        if id(it) not in matched_items:
            title = getattr(it.intent, "title", None) or it.text
            findings.append(CheckFinding(
                type="extra", item_id=it.id,
                detail=f"a {pkind} — “{title}” — was produced but the words never asked for it",
                blamed_stage=BLAME["extra"]))

    state.findings = findings
    for f in findings:
        state.mistakes.append(f.detail)
    if state.trace:
        if findings:
            state.trace.step(VERIFY, "Cross-check",
                             "; ".join(f.detail for f in findings), ok=False,
                             findings=[f.type for f in findings])
        else:
            state.trace.step(VERIFY, "Cross-check",
                             f"{len(asks)} ask(s) in the words — all covered")
    return state
