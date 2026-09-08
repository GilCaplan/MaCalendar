"""Turn the existing 321 FastRule templates into segment gold, by construction.

The hand-written rows in `data/*_traps.jsonl` are the honest core, but they are
slow to write and they carry my blind spots. `dataset/fastrule/banks/
complex_patterns.json` already holds 321 templates that were built for a
different board — and it encodes exactly what segment gold needs:

    atomic   True  -> ONE item, whatever the joiners look like
    template "book {event_title} {date} and {event_title2} {date2}"

Because the template names its slots, the action/time split is **known**, not
inferred: `{date}` IS the time reference, so gold is derived from structure
rather than guessed from surface text. That is the whole reason this is worth
doing — a regex over rendered text would just be FastSeg marking its own
homework.

74 of the atomic templates contain a joiner ("buy {item} and {item2}"), so they
are decoy rows a naive splitter fails. Those are the expensive ones to write by
hand and the cheapest ones to get here.

THE RULE OF THIS FILE: a template whose gold cannot be derived *and validated*
is EXCLUDED and reported, never emitted with a guess. `--report` prints what
was dropped and why; nothing is silently truncated.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
_BANKS = os.path.join(_ROOT, "dataset", "fastrule", "banks")

from segment_tuning import invariant                  # noqa: E402

# --------------------------------------------------------------------------
# What counts as a time reference — by SLOT NAME, which is why gold is exact
# --------------------------------------------------------------------------

#: Slots that hold a time reference, grouped by the slot-class the spec's edge
#: rule distributes over: a command may supply a day and a clock separately
#: ("tomorrow ... at 7"), and each distributes independently.
_DAY_SLOTS = {"date", "date2", "date3", "recurrence", "recurrence2",
              "query_range", "query_range2"}
_CLOCK_SLOTS = {"time", "time2", "time3", "time_range", "lead_time"}
_TIME_SLOTS = _DAY_SLOTS | _CLOCK_SLOTS

#: `duration` ("by 30 minutes") modifies an update; it is not when the thing
#: happens, so it stays in the action. `occasion` ("my birthday") is a named
#: day and behaves as one. Both decided once, here, rather than per row.
_ACTION_SLOTS_THAT_LOOK_TEMPORAL = {"duration"}

#: The comma branch has to swallow a joiner that follows it. Written as two
#: alternatives it did not: in "call the plumber, then print the pass" the
#: comma matched first and left "then" glued to the front of item 2's action.
_JOINER = re.compile(
    r"\s*(?:,\s*)?(?:and then|and also|as well as|and|then|also|plus)\s+"
    r"|,\s*")

#: A time slot is spoken with its preposition — the spec captures "by friday",
#: not "friday". Optional, because "book X {date}" is bare.
#: "to" is here because of `reschedule the call with {name} and {name2} to
#: {date}`: without it the date was pulled bare and "to" was left stranded on
#: the end of the action, which is 40 of the corpus's gold items. It only ever
#: fires when it sits IMMEDIATELY before a time slot, so "add {task} to my
#: list {date}" is untouched — there "to" precedes "my", not the slot.
_PREP = r"(?:at|on|for|by|from|in|to|starting|until|through|around)"


def _slot_re(names) -> re.Pattern:
    return re.compile(r"(?:(" + _PREP + r")\s+)?\{(" + "|".join(sorted(names)) + r")\}")


_TIME_RE = _slot_re(_TIME_SLOTS)
_ANY_SLOT = re.compile(r"\{(\w+)\}")


def _class_of(slot: str) -> str:
    return "day" if slot in _DAY_SLOTS else "clock"


# --------------------------------------------------------------------------
# Derivation: template -> parts -> (action, time) per part
# --------------------------------------------------------------------------

def template_parts(t: dict) -> "list[str]":
    """The item-level pieces of a template.

    `atomic` is the bank's own judgement and it outranks the joiner: that is
    precisely what makes "buy {item} and {item2}" a decoy rather than a split.
    """
    if t["atomic"]:
        return [t["template"].strip()]
    return [p.strip() for p in _JOINER.split(t["template"]) if p.strip()]


def _pull_times(part: str) -> "tuple[str, list[tuple[str, str]]]":
    """part -> (action template, [(class, time template), ...])

    Returns the action with its time expressions removed, and each time
    expression with the preposition it was spoken with.
    """
    found: list[tuple[str, str]] = []

    def take(m: re.Match) -> str:
        prep, slot = m.group(1), m.group(2)
        found.append((_class_of(slot), (f"{prep} " if prep else "") + "{" + slot + "}"))
        return " "

    action = _TIME_RE.sub(take, part)
    return _tidy_action(action), found


#: A joiner or infinitive marker left at the edge of an action carries no
#: content — the invariant's stop list already ignores these words, so removing
#: them loses nothing and stops the gold from treating the two halves of
#: "remind me to X and to Y" differently (item 1 kept its wrapper, item 2 was
#: labelled "to fix the leaky faucet").
_EDGE_JUNK_HEAD = re.compile(r"^(?:and|then|also|plus|or|to|for)\s+", re.I)
_EDGE_JUNK_TAIL = re.compile(
    r"\s+(?:to|for|at|on|by|from|in|with|of|the|a|an|and|or|then)$", re.I)


def _tidy_action(action: str) -> str:
    action = re.sub(r"\s{2,}", " ", action).strip(" ,")
    for _ in range(3):
        before = action
        action = _EDGE_JUNK_HEAD.sub("", action)
        action = _EDGE_JUNK_TAIL.sub("", action)
        action = action.strip(" ,")
        if action == before:
            break
    return action


def derive(t: dict) -> "list[dict] | None":
    """Template -> per-item (action, time, tag) templates. None if underivable."""
    parts = template_parts(t)
    pulled = [_pull_times(p) for p in parts]

    # --- the spec's edge rule, applied where slot positions are known -------
    # INTERIOR binds to its own item. An edge reference belongs to no single
    # item and covers the rest — but the two edges do NOT behave the same, and
    # that asymmetry was found by generating, not by reasoning:
    #
    #   LEADING  scopes forward over the whole command, and distributes per
    #            slot class. "tomorrow gym at 7 and meeting at 11" -> the
    #            second item has a clock but no day, and takes "tomorrow".
    #   TRAILING attaches to its own clause unless no other clause carries a
    #            time at all. "submit the grades and prepare the slides by
    #            friday" -> item 1 has nothing, so it takes "by friday"; but
    #            in "do i have anything this weekend and book the haircut at
    #            3:45" the trailing clock stays with the haircut, because the
    #            question already carries its own time.
    #
    # Per-class distribution in both directions gave the question
    # "this weekend at 3:45pm", which is the bug this asymmetry fixes. It also
    # matches how English works: pre-posed temporal adverbials scope over the
    # utterance, post-posed ones attach to the nearest clause.
    lead: list[tuple[str, str]] = []
    trail: list[tuple[str, str]] = []
    if len(parts) > 1:
        for idx, (part, (_, times)) in enumerate(zip(parts, pulled)):
            for cls, expr in times:
                m = re.search(re.escape(expr), part)
                if not m:
                    continue
                if idx == 0 and m.start() <= 1:
                    lead.append((cls, expr))
                elif idx == len(parts) - 1 and m.end() >= len(part) - 1:
                    trail.append((cls, expr))

    items = []
    for action, times in pulled:
        mine = list(times)
        have = {cls for cls, _ in mine}
        for cls, expr in lead:
            if cls not in have and (cls, expr) not in mine:
                mine.append((cls, expr))
                have.add(cls)
        if not mine:                      # trailing: only a wholly untimed item
            mine = list(trail)
        order = {"day": 0, "clock": 1}
        mine.sort(key=lambda ce: order[ce[0]])
        tag = _tag_for(action, t)
        if tag is None or not action:
            return None
        # THE DATE FLOOR (SPEC): the day defaults to today, the clock never
        # does — so a clock-only item is "today at 7", not "at 7".
        if not any(cls == "day" for cls, _ in mine):
            mine.insert(0, ("day", "today"))
        items.append({"action": action,
                      "time": " ".join(e for _, e in mine),
                      "tag": tag})
    return items


def _tag_for(action_tpl: str, t: dict) -> "str | None":
    """Which surface this item targets: calendar, to-do list, or a question.

    NOTE (design, recorded rather than assumed): the tag names the SURFACE, not
    the operation. "cancel the meeting" is tagged `event` because it is about
    the calendar; whether it creates or deletes is the operation feature, which
    belongs to a later stage. `review` is reserved for items that neither
    create nor change anything.
    """
    slots = set(_ANY_SLOT.findall(action_tpl))
    if "query_range" in slots or "query_range2" in slots:
        return "review"
    if re.search(r"\bwhat(?:'s| is| do)\b|\bcheck what\b|\bdo i have\b", action_tpl):
        return "review"
    if slots & {"event_title", "event_title2", "event_title3", "occasion"}:
        return "event"
    if slots & {"task_title", "task_title2", "task_title3",
                "item", "item2", "item3", "quoted_item"}:
        return "task"
    by_action = {"create_event": "event", "delete_event": "event",
                 "update_event": "event", "query": "review",
                 "create_todo": "task", "delete_todo": "task",
                 "update_todo": "task", "complete_todo": "task"}
    return by_action.get(t["action"])


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

_FILL = {"event_title": "event_titles", "event_title2": "event_titles",
         "event_title3": "event_titles", "task_title": "task_titles",
         "task_title2": "task_titles", "task_title3": "task_titles",
         "item": "items", "item2": "items", "item3": "items",
         "qty": "quantities", "name": "names", "name2": "names",
         "date": "dates", "date2": "dates", "date3": "dates",
         "time": "times", "time2": "times", "time3": "times",
         "time_range": "time_ranges", "recurrence": "recurrences",
         "recurrence2": "recurrences", "occasion": "occasions",
         "lead_time": "lead_times", "duration": "durations",
         "quoted_item": "quotable", "generic_target": "generic_targets",
         "query_range": "query_ranges", "query_range2": "query_ranges"}


def _bind(template: str, banks: dict, rng: random.Random) -> dict:
    """One value per slot, shared across the whole row so text and gold agree.

    Distinct values for the numbered variants — "{event_title} and
    {event_title2}" rendering the same title twice would make a two-item row
    indistinguishable from a repetition, and the invariant would pass on a row
    that teaches the wrong thing.
    """
    binding: dict[str, str] = {}
    used: dict[str, set] = {}
    for slot in dict.fromkeys(_ANY_SLOT.findall(template)):
        bank = _FILL.get(slot)
        if bank is None:
            return {}
        pool = [v for v in banks[bank] if v not in used.setdefault(bank, set())]
        if not pool:
            pool = banks[bank]
        value = rng.choice(pool)
        used[bank].add(value)
        binding[slot] = value
    return binding


def _fill(template: str, binding: dict) -> str:
    out = _ANY_SLOT.sub(lambda m: binding.get(m.group(1), m.group(0)), template)
    return re.sub(r"\s{2,}", " ", out).strip()


# --------------------------------------------------------------------------
# Validation — nothing ships that cannot be checked
# --------------------------------------------------------------------------

def validate(text: str, items: "list[dict]", t: dict) -> "list[str]":
    """Every check that must hold before a generated row is allowed out."""
    bad = list(invariant.violations(text, items))
    for i, it in enumerate(items, 1):
        if not it["action"].strip():
            bad.append(f"item {i} empty action")
        if it["tag"] not in ("event", "task", "review"):
            bad.append(f"item {i} bad tag {it['tag']!r}")
    # The bank's own count, where it is meaningful. `events + tasks` counts
    # objects CREATED, which equals the item count only when every item
    # creates something. A `mixed` row like "cancel X and book Y" is two
    # segment items and one created object, and a `delete` row is one item and
    # zero — so the check applies to pure-create templates only. (Applying it
    # to `mixed` dropped 30 correctly-derived families before this was
    # noticed; the derivation was right and the check was wrong.)
    if t["action"] in ("create_event", "create_todo"):
        want = (t.get("events") or 0) + (t.get("tasks") or 0)
        if want and want != len(items):
            bad.append(f"count {len(items)} != bank's {want}")
    if t["atomic"] and len(items) != 1:
        bad.append(f"atomic but produced {len(items)} items")
    return bad


# --------------------------------------------------------------------------

#: `propose` templates ("should i book X?") ask for advice. They are neither a
#: calendar question nor a create, so the three-tag contract has no honest
#: label for them — the engine treats them as the interrogative-create refusal
#: class. Excluded deliberately, and reported, rather than mislabelled.
_EXCLUDE_ACTIONS = {"propose"}


def build(per_template: int = 6, seed: int = 20260908) -> "tuple[list[dict], list[dict]]":
    banks = json.load(open(os.path.join(_BANKS, "fillers.json")))
    templates = json.load(open(os.path.join(_BANKS, "complex_patterns.json")))
    rows, dropped = [], []

    for t in templates:
        if t["action"] in _EXCLUDE_ACTIONS:
            dropped.append({"family": t["family"], "why": "action=propose (no honest tag)"})
            continue
        spec = derive(t)
        if spec is None:
            dropped.append({"family": t["family"], "template": t["template"],
                            "why": "underivable action/tag"})
            continue

        rng = random.Random(f"{seed}:{t['family']}")
        made, failures = 0, []
        for n in range(per_template * 3):        # oversample; keep what validates
            if made >= per_template:
                break
            binding = _bind(t["template"], banks, rng)
            if not binding and _ANY_SLOT.search(t["template"]):
                failures.append("unknown slot")
                break
            text = _fill(t["template"], binding)
            items = [{"action": _fill(s["action"], binding),
                      "time": _fill(s["time"], binding),
                      "tag": s["tag"]} for s in spec]
            bad = validate(text, items, t)
            if bad:
                failures.append(bad[0])
                continue
            rows.append({"id": f"gen_{t['family']}_{n}", "text": text,
                         "gold": items, "traps": [t["nuance"]],
                         "source": "generated", "family": t["family"],
                         "atomic": t["atomic"]})
            made += 1
        if not made:
            dropped.append({"family": t["family"], "template": t["template"],
                            "why": failures[0] if failures else "no valid render"})
    return rows, dropped


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-template", type=int, default=6)
    ap.add_argument("--out", default=os.path.join(_HERE, "data", "generated.jsonl"))
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()

    rows, dropped = build(a.per_template)
    with open(a.out, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")

    fams = {r["family"] for r in rows}
    n_atomic = sum(1 for r in rows if r["atomic"])
    print(f"wrote {len(rows)} rows from {len(fams)} families -> {a.out}")
    print(f"   atomic (must NOT split) {n_atomic}   |   multi-item {len(rows) - n_atomic}")
    print(f"   dropped {len(dropped)} families (nothing guessed)")
    if a.report:
        import collections
        for why, n in collections.Counter(d["why"] for d in dropped).most_common():
            print(f"      {n:3d}  {why}")
        print("\n   sample dropped:")
        for d in dropped[:12]:
            print(f"      [{d['family']}] {d.get('template','')}  <- {d['why']}")


if __name__ == "__main__":
    main()
