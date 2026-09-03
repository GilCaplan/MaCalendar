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
the separate things it asks for.

For each ask give:
- kind: "event" (books, moves, cancels or changes something WITH a date/time),
  "task" (a to-do / shopping / reminder-to-do item), "review" (asks what is
  scheduled).
- words: the speaker's OWN words for that ask, copied — include its verb and
  its time if said. Never rephrase, never summarise, never invent.

How to count asks (this must match how the assistant itself counts):
- A list of things to do or buy is one ask PER thing, each carrying the verb:
  "buy milk, eggs and bread" = three asks (buy milk / buy eggs / buy bread).
- A count is ONE ask: "buy 5 apples" is one ask, never five.
- People joined by "and" share one ask: "meeting with Tal and Ravid" is one.
- One thing plus its description is one ask: "a gift for mom and dad" is one.
- The same activity at two times is two asks: "walk the dog at 9 and 2:30".
- Moving, renaming, deleting or completing something is an ask too.
Do not list an ask twice. When unsure whether something is one ask or two,
say ONE.

Examples:
"book gym tomorrow at 7am and remind me to buy milk"
→ {"asks": [{"kind": "event", "words": "book gym tomorrow at 7am"},
            {"kind": "task", "words": "remind me to buy milk"}]}
"add buy milk, eggs and bread to my list"
→ {"asks": [{"kind": "task", "words": "buy milk"},
            {"kind": "task", "words": "buy eggs"},
            {"kind": "task", "words": "buy bread"}]}
"meeting with Tal and Ravid at Kems tomorrow evening"
→ {"asks": [{"kind": "event", "words": "meeting with Tal and Ravid at Kems tomorrow evening"}]}
"buy 5 apples"
→ {"asks": [{"kind": "task", "words": "buy 5 apples"}]}
"move my haircut to 6pm"
→ {"asks": [{"kind": "event", "words": "move my haircut to 6pm"}]}

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
    """Everything the engine decided about — the comparable surface.

    A BLOCKED item is included: the observance gate answered that ask (with an
    explained refusal), and counting it "missing" once sent almost every gated
    command into a full loop-back storm — three re-parses that could never
    change a policy refusal. Updates/deletes/completes are included too: the
    extraction has no way to know "move the meeting" is not a fresh event, and
    treating those asks as uncovered was another loop with no possible win.
    Each entry: (item, kind, tokens, removable, capacity) — only a genuinely
    created row is `removable` (an extra-finding candidate), and `capacity` is
    how many ASKS the item can cover: a fast-track create_todo carries every
    title in ONE intent ("milk, eggs and bread" = titles×3), and letting it
    satisfy only one ask was exactly what invented two "missing" tasks and
    had the background patch add duplicates."""
    out = []
    for it in state.items:
        if it.intent is None:
            continue
        if it.action in ("create_event", "create_todo"):
            kind = "event" if it.action == "create_event" else "task"
            titles = list(getattr(it.intent, "titles", None) or [])
            if not titles:
                titles = [getattr(it.intent, "title", "") or it.text]
            toks = _tokens(it.text)
            for t in titles:
                toks |= _tokens(t)
            out.append((it, kind, toks, not it.blocked, max(1, len(titles))))
        elif it.action in ("update_event", "delete_event", "update_todo",
                           "delete_todo", "complete_todo", "add_subtask"):
            kind = "event" if "event" in it.action else "task"
            title = getattr(it.intent, "match_title", None) or \
                getattr(it.intent, "title", None) or it.text
            out.append((it, kind, _tokens(title) | _tokens(it.text), False, 1))
        elif it.action == "query_schedule":
            out.append((it, "review", _tokens(it.text), False, 1))
    return out


def run(state: EngineState, cfg) -> EngineState:
    from assistant.trace import VERIFY

    asks = extract_asks(state, cfg)
    if asks is None:
        return state

    produced = _produced(state)
    capacity = {id(it): cap for it, _k, _t, _r, cap in produced}
    unmatched_asks = []
    for kind, words in asks:
        toks = _tokens(words)
        # Two passes: same-kind first, then any kind — the extraction
        # regularly mislabels a task as an event, and a kind quibble must not
        # become a false "missing" (which costs three pointless re-parses).
        best, best_score = None, 0.0
        for same_kind_only in (True, False):
            for it, pkind, ptoks, _removable, _cap in produced:
                if capacity[id(it)] <= 0:
                    continue
                if same_kind_only and pkind != kind:
                    continue
                score = _overlap(toks, ptoks)
                if score > best_score:
                    best, best_score = it, score
            if best is not None and best_score >= 0.25:
                break
        if best is not None and best_score >= 0.25:
            capacity[id(best)] -= 1
        else:
            unmatched_asks.append((kind, words))

    findings: list = []
    for kind, words in unmatched_asks:
        findings.append(CheckFinding(
            type="missing", item_id=None,
            detail=f"the words ask for a {kind} — “{words}” — but nothing produced covers it",
            blamed_stage=BLAME["missing"]))
    for it, pkind, _ptoks, removable, cap in produced:
        if removable and capacity[id(it)] >= cap:   # nothing matched it at all
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
