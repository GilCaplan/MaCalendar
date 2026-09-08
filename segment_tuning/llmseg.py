"""LLMSeg — the model half of the segment component, and the guards around it.

    fastseg(text) -> proposal -> LLMSeg -> ACCEPT -> final items

LLMSeg does NOT verify. It is handed FastSeg's proposal as an anchor and
always emits its own decomposition; deterministic code then diffs the two and
decides. That protocol was measured, not assumed — against llama3.1:8b on 14
cases:

    V1  "No Change" or a correction ............  5/14
    V2  V1 + a four-point checklist .............  1/14   (it narrates)
    V3  no judgement, always emit, we diff ...... 11/14   <- this
    V6  V3 with no proposal shown ...............  8/14   (anchor worth +3)

Asking an 8B "is this right?" invites the accept bias — V1 waved through 4 of
7 broken inputs, which is the same self-assessment over-estimate ADaPT
measured at 30+ points. Taking the decision away from the model fixes it.

Two deterministic guards sit around the call, and both exist because the
tuning showed the model failing in exactly these ways:

  TAG COERCION   whatever string comes back is snapped to event|task|review.
                 The tag is then structurally correct rather than trusted.
  ACCEPT         the model's answer is taken only if it satisfies the
                 no-loss / no-invention invariant. Its commonest failure was
                 DELETING a shared "tomorrow" rather than distributing it;
                 that check reverts every instance of it to FastSeg's answer.
"""
from __future__ import annotations

import difflib
import json
import os
import re
import sys
import urllib.request

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from segment_tuning.fastseg import fastseg           # noqa: E402

TAGS = ("event", "task", "review")
MODEL = "llama3.1:8b"
ENDPOINT = "http://localhost:11434/api/chat"


# ---------------------------------------------------------------------------
# TAG COERCION — the tag is made correct, not requested
# ---------------------------------------------------------------------------

#: Words a model reaches for instead of the three it was given. Mapped rather
#: than rejected: "todo" is not a hallucination, it is a synonym, and throwing
#: the item away over it would lose a correct decomposition.
_TAG_SYNONYMS = {
    "calendar": "event", "appointment": "event", "meeting": "event",
    "schedule": "event", "events": "event",
    "todo": "task", "to-do": "task", "to do": "task", "reminder": "task",
    "tasks": "task", "chore": "task", "errand": "task",
    "query": "review", "question": "review", "check": "review",
    "lookup": "review", "read": "review", "reviews": "review",
}


def normalise_tag(value, fallback: str = "event") -> str:
    """Any string -> exactly one of event | task | review.

    Gil: "have an automatic function which given a string matches to the
    closest tag and fixes if needed, that way semantically the tag is always
    correct." Three passes, cheapest first: exact, synonym, then closest
    match. A value that resembles nothing keeps FastSeg's tag rather than
    defaulting blindly — FastSeg's guess is evidence, and an unparseable
    answer is not.
    """
    s = str(value or "").strip().lower().strip(".\"'")
    if s in TAGS:
        return s
    if s in _TAG_SYNONYMS:
        return _TAG_SYNONYMS[s]
    for word in re.findall(r"[a-z-]+", s):           # "an event" / "task item"
        if word in TAGS:
            return word
        if word in _TAG_SYNONYMS:
            return _TAG_SYNONYMS[word]
    close = difflib.get_close_matches(s, TAGS, n=1, cutoff=0.6)
    if close:
        return close[0]
    return fallback if fallback in TAGS else "event"


# ---------------------------------------------------------------------------
# THE PROMPT (V3, the tuned winner — see segment_tuning/verifier_prompt_v3.txt)
# ---------------------------------------------------------------------------

_RULES = """An item is ONE independent thing the speaker asked for. Each item has three parts:
  action - the item's words with the time reference removed. Keep EVERYTHING else:
           the verb, the object, people, places, quantities ("5 apples").
  time   - the time reference for this item, copied from the command AS SPOKEN.
  tag    - EXACTLY ONE OF THESE THREE WORDS, never any other:
             event   - goes on the calendar at a time
             task    - goes on the to-do list
             review  - asks what is scheduled; creates nothing

HOW TIME IS ASSIGNED
  - a time reference sitting INSIDE an item belongs to that item alone
  - a time reference at either END of the command, belonging to no single item,
    applies to EVERY item that has none of its own
  - a repeating time ("every friday") IS the time
  - an item with no time reference at all gets "today\""""

_EXAMPLES = """EXAMPLES
  "tomorrow gym at 7 and meeting at 11"
  {"1": ["gym", "tomorrow at 7", "event"], "2": ["meeting", "tomorrow at 11", "event"]}
  "gym session at 7, tomorrow meeting at 10"
  {"1": ["gym session", "today at 7", "event"], "2": ["meeting", "tomorrow at 10", "event"]}
  "buy 5 apples"
  {"1": ["buy 5 apples", "today", "task"]}
  "meeting with Sam and Alex at 8"
  {"1": ["meeting with Sam and Alex", "at 8", "event"]}
  the "and" joins two PEOPLE - one item, not two
  "wash and fold the laundry"
  {"1": ["wash and fold the laundry", "today", "task"]}
  two verbs, one object - one item
  "what do i have on friday"
  {"1": ["what do i have", "friday", "review"]}
  a question about the calendar creates nothing"""


def build_prompt(text: str, proposal: "list[dict]") -> str:
    compact = {str(i + 1): [it["action"], it["time"], it["tag"]]
               for i, it in enumerate(proposal)}
    return f"""COMMAND (exactly as spoken):
{text}

A parser proposed this decomposition. It may be right or wrong:
{json.dumps(compact)}

{_RULES}

{_EXAMPLES}

Output the CORRECT decomposition as one JSON object. If the proposal above is
already correct, output it unchanged. Output the JSON and nothing else - no
explanation, no preamble, no code fence."""


def call_model(prompt: str, timeout: int = 180) -> str:
    body = json.dumps({"model": MODEL, "stream": False,
                       "options": {"temperature": 0},
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(ENDPOINT, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["message"]["content"].strip()


def parse_items(raw: str, proposal: "list[dict]") -> "list[dict] | None":
    """The model's reply -> items, with every tag coerced. None if unusable."""
    try:
        blob = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    except Exception:
        return None
    items = []
    for i, value in enumerate(blob.values()):
        if not isinstance(value, (list, tuple)) or len(value) < 2:
            return None
        fallback = proposal[i]["tag"] if i < len(proposal) else "event"
        items.append({"action": str(value[0]).strip(),
                      "time": str(value[1]).strip() or "today",
                      "tag": normalise_tag(value[2] if len(value) > 2 else "",
                                           fallback)})
    return items or None


# ---------------------------------------------------------------------------
# ACCEPT — deterministic, and the model never has the last word
# ---------------------------------------------------------------------------

_STOP = frozenset("a an the and or then also to of for on at in by with my me "
                  "i please can you it that this".split())


def _content(s: str) -> "set[str]":
    return {w for w in re.findall(r"[a-z0-9']+", (s or "").lower())
            if w not in _STOP}


def invariant_violations(text: str, items: "list[dict]") -> "list[str]":
    """Every content token accounted for, and none invented.

    This is the dataset's metric and the runtime guard, deliberately the same
    function — a rule that is only checked offline is a rule the product does
    not have.
    """
    src = _content(text)
    out: list[str] = []
    seen: set[str] = set()
    for i, it in enumerate(items, 1):
        got = _content(it.get("action", "")) | _content(it.get("time", ""))
        invented = got - src
        if invented:
            out.append(f"item {i} invented {sorted(invented)}")
        seen |= got
    missing = src - seen
    if missing:
        out.append(f"lost {sorted(missing)}")
    return out


def accept(text: str, proposal: "list[dict]", candidate) -> "tuple[list[dict], str]":
    """Choose between FastSeg's answer and LLMSeg's. Returns (items, why)."""
    if candidate is None:
        return proposal, "llmseg-unparseable"
    if candidate == proposal:
        return proposal, "agreed"
    bad = invariant_violations(text, candidate)
    if bad:
        # The model's commonest failure in tuning was deleting a shared
        # "tomorrow" instead of distributing it. A decomposition that loses a
        # word does not get to overwrite one that kept it.
        return proposal, f"rejected: {'; '.join(bad)}"
    return candidate, "corrected"


def segment(text: str, use_model: bool = True) -> "dict":
    """The whole component. Returns the items and how they were arrived at."""
    proposal = fastseg(text)
    if not use_model:
        return {"items": proposal, "route": "fastseg-only", "proposal": proposal}
    try:
        raw = call_model(build_prompt(text, proposal))
    except Exception as exc:                          # model down: FastSeg stands
        return {"items": proposal, "route": f"model-error:{type(exc).__name__}",
                "proposal": proposal}
    items, why = accept(text, proposal, parse_items(raw, proposal))
    return {"items": items, "route": why, "proposal": proposal, "raw": raw}


if __name__ == "__main__":                            # pragma: no cover
    for probe in ("tomorrow gym at 7 and meeting at 11",
                  "gym session at 7, tomorrow meeting at 10",
                  "submit the grades and prepare the slides by friday",
                  "what do i have on friday",
                  "meeting with Sam and Alex at 8"):
        r = segment(probe)
        print(f"\n{probe!r}   [{r['route']}]")
        for it in r["items"]:
            print(f"   action={it['action']!r:36s} time={it['time']!r:20s} {it['tag']}")
