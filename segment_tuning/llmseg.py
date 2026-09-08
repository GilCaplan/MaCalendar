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

from segment_tuning import invariant as _invariant    # noqa: E402
from segment_tuning.fastseg import fastseg           # noqa: E402

TAGS = ("event", "task", "review")
MODEL = "llama3.1:8b"
ENDPOINT = "http://localhost:11434/api/chat"

#: OFF BY DEFAULT (Gil, 2026-09-08). LLMSeg is wired, tested and kept, but it
#: does not run unless something asks for it.
#:
#: It was measured against FastSeg on 571 trap-stratified TRAIN rows, four
#: independent ways, and every one came back negative — most decisively the V4
#: prompt, written after an audit fixed five places where the prompt taught
#: something the gold no longer accepted. With the prompt correct it still
#: fixed ONE row in 358 and broke 42. The prompt was not the problem.
#:
#:     FastSeg alone            exact-row 55.4%
#:     FastSeg + LLMSeg (V4)    exact-row 43.8%      fixes 1 / breaks 42
#:     cost                     10 ms/row -> 6.3 s/row
#:
#: Full numbers and the three limits of that conclusion are in
#: `assistant/engine/segmentation/ARCHITECTURE.md`.
#:
#: The env override exists so an experiment can turn it on without editing
#: code — and so that turning it on is always a deliberate act that shows up
#: in the command that ran it.
ENABLED = os.environ.get("MACALENDAR_LLMSEG", "").strip().lower() in (
    "1", "true", "yes", "on")


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

#: V4. V3 was measured against gold that has since changed underneath it, and
#: an audit found FIVE places where it taught something the gold no longer
#: accepts — the symmetric edge rule (12.2% of rows), a missing date floor in
#: one example that contradicted another example, a dropped preposition, a
#: half-stated floor rule, and nothing at all about what the tag means for a
#: delete. Every one of those graded the model wrong for obeying its
#: instructions, so no V3 measurement is evidence about the model.
_RULES = """An item is ONE independent thing the speaker asked for. Each item has three parts:
  action - the item's words with the time reference removed. Keep EVERYTHING else:
           the verb, the object, people, places, quantities ("5 apples").
  time   - the time reference for this item, copied from the command AS SPOKEN,
           INCLUDING the preposition it was said with ("on friday", "by monday",
           "at 8"). Never a date, never a clock reading, never a range.
  tag    - EXACTLY ONE OF THESE THREE WORDS, never any other:
             event   - belongs to the CALENDAR
             task    - belongs to the TO-DO LIST
             review  - only asks a question; changes nothing
           The tag names WHICH LIST the item is about, NOT what is being done
           to it. "cancel the dentist" is `event` - it is about the calendar,
           even though it deletes rather than creates.

HOW TIME IS ASSIGNED
  - a time reference sitting INSIDE an item belongs to that item ALONE, and
    does not reach backwards to an earlier item
  - a time reference that OPENS the command scopes FORWARD over all of it. A
    day and a clock are separate slots, so a leading day still reaches an item
    that has a clock but no day.
  - a time reference that CLOSES the command reaches back ONLY to an item that
    has no time of its own at all. If an earlier item already has a time, the
    closing one stays where it is.
  - a repeating time ("every friday") IS the time

THE DATE FLOOR
  - the DAY defaults to "today" when the item names none
  - the CLOCK is never invented
  So: nothing said -> "today"; only a clock -> "today at 7"; only a day ->
  "tomorrow"; both -> "tomorrow at 7\""""

_EXAMPLES = """EXAMPLES
  "tomorrow gym at 7 and meeting at 11"
  {"1": ["gym", "tomorrow at 7", "event"], "2": ["meeting", "tomorrow at 11", "event"]}
  the leading "tomorrow" reaches item 2, which has a clock but no day
  "gym session at 7, tomorrow meeting at 10"
  {"1": ["gym session", "today at 7", "event"], "2": ["meeting", "tomorrow at 10", "event"]}
  the interior "tomorrow" does NOT reach back; item 1 floors to today
  "submit the grades and prepare the slides by friday"
  {"1": ["submit the grades", "by friday", "task"], "2": ["prepare the slides", "by friday", "task"]}
  the closing "by friday" reaches item 1, which had no time at all
  "do i have anything this weekend and book the haircut at 3:45"
  {"1": ["do i have anything", "this weekend", "review"], "2": ["book the haircut", "today at 3:45", "event"]}
  the closing clock stays put - item 1 already has a time of its own
  "buy 5 apples"
  {"1": ["buy 5 apples", "today", "task"]}
  "meeting with Sam and Alex at 8"
  {"1": ["meeting with Sam and Alex", "today at 8", "event"]}
  the "and" joins two PEOPLE - one item, not two
  "wash and fold the laundry"
  {"1": ["wash and fold the laundry", "today", "task"]}
  two verbs, one object - one item
  "cancel the dentist tomorrow"
  {"1": ["cancel the dentist", "tomorrow", "event"]}
  a delete is still about the CALENDAR, so the tag is event
  "what do i have on friday"
  {"1": ["what do i have", "on friday", "review"]}
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
    # keep_alive matters more than it looks: without it Ollama evicts the model
    # between calls and every request pays the reload, which is most of the
    # ~19s/row a scoring pass was showing. It changes latency only — the
    # sampled answer at temperature 0 is identical either way.
    body = json.dumps({"model": MODEL, "stream": False,
                       "keep_alive": "30m",
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

#: The dataset's metric and the runtime guard are deliberately the same
#: function — a rule that is only checked offline is a rule the product does
#: not have. It lives in `invariant.py` because three copies disagreed: this
#: one used to reject a model answer for defaulting an untimed item to
#: "today", which is exactly what SPEC.md tells it to do.
invariant_violations = _invariant.violations


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


def segment(text: str, use_model: "bool | None" = None) -> "dict":
    """The whole component. Returns the items and how they were arrived at.

    `use_model=None` means "whatever the flag says", which is OFF. Pass True to
    force it on for an experiment; pass False to force it off. A caller that
    measures LLMSeg must pass True EXPLICITLY — if the default silently decided
    it, a board would report FastSeg's numbers under LLMSeg's name, which is
    the exact class of silent-measurement bug this module has already been
    bitten by twice.
    """
    if use_model is None:
        use_model = ENABLED
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
        r = segment(probe, use_model=True)
        print(f"\n{probe!r}   [{r['route']}]")
        for it in r["items"]:
            print(f"   action={it['action']!r:36s} time={it['time']!r:20s} {it['tag']}")
