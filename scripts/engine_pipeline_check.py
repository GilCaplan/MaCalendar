"""Verify the SHAPE of what each stage hands to the next, and end to end.

`engine_stage_check.py` asks whether a stage is right. This asks something
narrower and more mechanical: **is the thing it hands on the right shape?** —
because a stage that returns a plausible-looking wrong shape is the failure that
survives a unit test and breaks the product. The `Item.time` contract change
made that a live risk: `text` no longer carries the time, so a consumer reading
`text` where it needs `spoken()` produces events with no time and no error.

It runs a command through the real pipeline, stopping at each boundary to check
the state against the contract, then checks that what landed in the DB matches
what was asked for.

    python -m scripts.engine_pipeline_check            # shapes + end to end
    python -m scripts.engine_pipeline_check --verbose  # print every item

Scratch stores only, `source: "test"`, and no writes to the real DB — the five
MACALENDAR_* overrides are set below, before anything from `assistant` is
imported, because the paths are read at import time.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="engine_pipeline_check_")
for _k, _v in dict(
        MACALENDAR_DB=f"{_SCRATCH}/calendar.db",
        MACALENDAR_MEMORY_DB=f"{_SCRATCH}/memory.db",
        MACALENDAR_VOCAB=f"{_SCRATCH}/vocab.json",
        MACALENDAR_CATEGORIES=f"{_SCRATCH}/categories.json",
        MACALENDAR_TRACE_BUS=f"{_SCRATCH}/trace_bus.jsonl",
        MACALENDAR_NO_WARMUP="1").items():
    os.environ[_k] = _v

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from assistant.engine import Engine, load_config          # noqa: E402
from assistant.engine.state import ITEM_KINDS, EngineState, Item  # noqa: E402

_FAILURES: "list[str]" = []


def check(ok: bool, label: str, detail: str = "") -> bool:
    mark = "ok  " if ok else "FAIL"
    print(f"    {mark} {label}" + (f"  — {detail}" if detail and not ok else ""))
    if not ok:
        _FAILURES.append(f"{label}: {detail}")
    return ok


# ---------------------------------------------------------------------------
# The boundaries
# ---------------------------------------------------------------------------

def check_x1(state: EngineState) -> None:
    """X1 — what Ingest hands Segmentation: one repaired command string."""
    check(isinstance(state.text, str), "X1 is a str", type(state.text).__name__)
    check(bool(state.text.strip()), "X1 is not empty")
    check(isinstance(state.corrections, list), "corrections is a list")
    # needs_edit is the LIST of doubtful words that gate the round-trip,
    # not a flag — the first version of this check asserted `bool` and was
    # simply wrong about the contract.
    check(isinstance(state.needs_edit, list), "needs_edit is a list",
          type(state.needs_edit).__name__)


def check_x2(state: EngineState, verbose: bool) -> None:
    """X2 — what Segmentation hands on: [(action, time, tag)] as Items."""
    items = state.items
    if not check(isinstance(items, list) and bool(items), "X2 is a non-empty list"):
        return
    check(all(isinstance(i, Item) for i in items), "every element is an Item")
    check(all(i.kind in ITEM_KINDS for i in items),
          "every kind is in ITEM_KINDS", str([i.kind for i in items]))
    check(all(isinstance(i.text, str) and i.text.strip() for i in items),
          "every action text is a non-empty str")
    check(all(i.time is None or isinstance(i.time, str) for i in items),
          "every time is a str or None")
    # The whole point of the new shape: the time is NOT buried in the action,
    # and spoken() puts it back for anything that parses a date.
    check(all(i.spoken().startswith(i.text) for i in items),
          "spoken() extends the action rather than replacing it")
    check(len({i.id for i in items}) == len(items), "item ids are unique")
    # A time that has been RESOLVED is a contract violation: segmentation
    # captures words, never dates.
    import re
    resolved = [i.time for i in items
                if i.time and re.search(r"\b\d{4}-\d{2}-\d{2}\b", i.time)]
    check(not resolved, "no time was RESOLVED to a date", str(resolved))
    if verbose:
        for i in items:
            print(f"         {i.id} kind={i.kind:6s} text={i.text!r} "
                  f"time={i.time!r} spoken={i.spoken()!r}")


def check_x3(state: EngineState, verbose: bool) -> None:
    """X3 — after decompose_validate: atomic, repaired, legal items."""
    items = state.items
    check(bool(items), "X3 is non-empty")
    check(all(isinstance(i, Item) for i in items), "still Items")
    check(all(i.blocked is None or isinstance(i.blocked, str) for i in items),
          "blocked is a reason string or None")
    # Decomposition encodes itself in the id, bounded at depth 2.
    check(all(i.id.count("-") <= 2 for i in items),
          "decomposition depth is bounded", str([i.id for i in items]))
    if verbose:
        for i in items:
            print(f"         {i.id} kind={i.kind:6s} spoken={i.spoken()!r}"
                  + (f" BLOCKED={i.blocked}" if i.blocked else ""))


def check_x4(state: EngineState, verbose: bool) -> None:
    """X4 — after the object-making stage: something writable, or a reason."""
    items = state.items
    unresolved = [i for i in items if i.intent is None and not i.blocked]
    check(not unresolved, "every item has an intent or an honest refusal",
          str([i.text for i in unresolved]))
    check(all(i.action is None or isinstance(i.action, str) for i in items),
          "action is a registry name or None")
    if verbose:
        for i in items:
            print(f"         {i.id} action={i.action} "
                  f"intent={type(i.intent).__name__ if i.intent else None}")


# ---------------------------------------------------------------------------

def run_shapes(text: str, verbose: bool) -> None:
    """One command, stopping at each boundary."""
    from assistant.engine import _label, _segment, _transcript
    from assistant.engine.decompose_validate import decompose as _decompose
    from assistant.engine.decompose_validate import validate as _validate
    from assistant.engine.fastrule import objects as _generate

    cfg = load_config()
    state = EngineState(raw_text=text, text=text, source="test")

    print(f"\n  {text!r}")
    _transcript.run(state, cfg)
    check_x1(state)
    _segment.run(state, cfg)
    check_x2(state, verbose)
    _decompose.run(state, cfg)
    _validate.run(state, cfg)
    check_x3(state, verbose)
    _generate.run(state, cfg)
    _validate.run_objects(state, cfg)
    check_x4(state, verbose)
    _label.run(state, cfg)


def run_end_to_end(cases: "list[tuple[str, dict]]") -> None:
    """The whole engine, then read the DB back. `expect` names what must land."""
    from assistant.db import get_db

    engine = Engine()
    for text, expect in cases:
        out = engine.run(text, source="test")
        print(f"\n  {text!r}")
        check(isinstance(out.get("message"), str) and bool(out["message"]),
              "the reply is a non-empty string")
        check(out.get("parse") in ("fast", "deep", "needs_edit", "queued"),
              "parse path is a known value", str(out.get("parse")))
        got = sorted(out.get("actions") or [])
        want = sorted(expect.get("actions", []))
        check(got == want, f"actions == {want}", f"got {got}")
        # Read the row back by SEARCH rather than by listing: the DB has no
        # list_events(), and searching is also what proves the row is findable
        # the way an edit or a delete would have to find it.
        db = get_db()
        # Substring, case-insensitive, ON PURPOSE. The engine titles an event
        # properly rather than echoing the words: "book the dentist tomorrow at
        # 3" creates "Dentist appointment". Demanding the literal word would
        # fail a system that is behaving correctly, so the check asks the honest
        # question — is there a row about this thing?
        for want in expect.get("event_titles", []):
            titles = [r["title"] for r in db.search_events(want, limit=50)]
            check(any(want.lower() in t.lower() for t in titles),
                  f"an event about {want!r} was written", str(sorted(titles)))
        for want in expect.get("todo_titles", []):
            titles = [r["title"] for r in db.search_todos(want, limit=50)]
            check(any(want.lower() in t.lower() for t in titles),
                  f"a todo about {want!r} was written", str(sorted(titles)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    from assistant.engine.segmentation import IMPLEMENTATION
    from assistant.engine.segmentation.llmseg.llmseg import ENABLED

    print(f"scratch: {_SCRATCH}")
    print(f"segmentation={IMPLEMENTATION}   llmseg.ENABLED={ENABLED}")

    print("\n" + "=" * 70 + "\nSTAGE SHAPES — what each stage hands the next\n" + "=" * 70)
    for text in ["tomorrow gym at 7 and buy milk",
                 "meeting with Sam and Alex at 8",
                 "buy milk and eggs",
                 "what do i have on friday",
                 "every friday at 6 remind me to take out the bins",
                 '("gym tomorrow at 7")and("buy milk")']:
        run_shapes(text, a.verbose)

    print("\n" + "=" * 70 + "\nEND TO END — the reply, and what reached the DB\n" + "=" * 70)
    run_end_to_end([
        ("book the dentist tomorrow at 3",
         {"actions": ["create_event"], "event_titles": ["dentist"]}),
        ("add buy bread to my list",
         {"actions": ["create_todo"], "todo_titles": ["buy bread"]}),
        ("tomorrow gym at 7 and buy milk",
         {"actions": ["create_event", "create_todo"]}),
        ("what do i have today", {"actions": ["query_schedule"]}),
    ])

    print("\n" + "=" * 70)
    if _FAILURES:
        print(f"FAILED — {len(_FAILURES)} check(s)")
        for f in _FAILURES:
            print(f"   {f}")
        raise SystemExit(1)
    print("PASSED — every stage boundary matched its contract, and the "
          "end-to-end cases landed")


if __name__ == "__main__":
    main()
