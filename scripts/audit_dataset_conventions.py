"""Audit the dataset against the PRODUCT's conventions and emit overrides.

The HWU-64-derived ground truth encodes its source corpus' worldview: separate
list objects, standing "notify me when" alerts, per-kind compound splits taken
from the source utterances' intents. Our product deliberately differs (no list
objects — Today/General + tags; no standing alerts; "remind me to VERB" with
no clock time is a task even when the source called it an event). Scoring
those rows raw penalizes the engine for being right.

Inputs stay frozen. This script classifies rows by MECHANICAL RULES —
written from dev-region evidence (tier_rank ≤ 600) only, then applied to the
whole dataset without inspecting held-out rows — and writes
`dataset/inputs/convention_overrides.json`, a versioned second layer the
scorer applies as an ADJUSTED metric next to the raw one. Raw `count_ok`
never changes, so every logged run stays comparable.

Treatments (implemented in scripts/score_dataset_run.py):

  noop_ok        an honest nothing is as correct as a sensible creation:
                 pass if (0 creations, 0 mutations) or (≥1 creation, none
                 garbage-titled)
  half_flexible  compound with one half our product legitimately declines
                 (placeholder text, standing alert): pass if total ≥ 1 clean
                 creation
  split_flexible compound whose per-kind split came from source intents our
                 conventions re-file ("remind me to X" halves): pass on
                 total ≥ 2 creations, kinds free

Run:  python -m scripts.audit_dataset_conventions        # writes + summarizes
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "dataset" / "inputs" / "hwu64_sample.json"
OUT = ROOT / "dataset" / "inputs" / "convention_overrides.json"

_PLACEHOLDER = re.compile(r"\bxx+x\b|[{}]|<insert\b", re.I)
_TRUNCATED = re.compile(r"\b(of|to|the|a|my|for|and|in|with|on|at)\s*[.?!]?$", re.I)
# The verb must act on the LIST ITSELF ("open a new list") — never on an item
# ("add cereal to my shopping list" is a task + tag and stays strictly scored).
# Anchored full-text so any "<item> to my … list" shape falls through; a
# "list of <content>" also falls through (there is something to create).
_LIST_BARE = re.compile(
    r"^(?:\w+[,!]?\s+)?(?:(?:please|can you|could you|i need to|i want to|i'd like to)\s+)*"
    r"(?:open(?: up)?|start|create|make|begin)\s+(?:me\s+)?(?:a|an|another|the)?\s*"
    r"(?:new\s+)?(?:[a-z' -]+\s+)?list(?:\s+(?:called|named)\s+.+)?\s*[.?!]*$", re.I)
_LIST_BARE_ADD = re.compile(r"^(?:please\s+)?add\s+(?:a\s+)?new\s+list\s*[.?!]*$", re.I)
_ALERT = re.compile(
    r"\b(notify|alert|tell)\s+me\s+(when|if|whenever|every time)\b"
    r"|\blet me know\s+(when|if)\b", re.I)
_REMIND_TO = re.compile(r"\bremind (me )?to\b", re.I)


def classify(row: dict) -> "tuple[str, str] | None":
    """(class, treatment) for a row our conventions re-read, else None."""
    text, scen, intent = row["text"], row["scenario"], row["intent"]
    creator = intent in ("set", "createoradd")
    if _PLACEHOLDER.search(text):
        if scen == "compound":
            return "placeholder", "half_flexible"
        if creator:
            return "placeholder", "noop_ok"
        return None                      # query/remove already expect nothing
    if creator and scen != "compound" and _TRUNCATED.search(text.strip()):
        return "truncated", "noop_ok"
    if scen == "lists" and intent == "createoradd" and (
            _LIST_BARE.match(text.strip()) or _LIST_BARE_ADD.match(text.strip())):
        return "list_create_bare", "noop_ok"     # no list objects here
    if _ALERT.search(text):
        if scen == "compound":
            return "standing_alert", "half_flexible"
        if creator:
            return "standing_alert", "noop_ok"   # no standing-alert object
        return None
    if scen == "compound" and intent in ("event+event", "event+task") \
            and _REMIND_TO.search(text):
        return "remind_half", "split_flexible"   # remind-to may be a task
    return None


def build() -> dict:
    rows = json.loads(FIXTURE.read_text())["rows"]
    out: dict[str, dict] = {}
    for r in rows:
        hit = classify(r)
        if hit:
            out[r["text"]] = {"class": hit[0], "treatment": hit[1]}
    return {
        "version": 1,
        "generated": "2026-09-06",
        "note": ("Mechanical rules mined from dev region (tier_rank<=600) "
                 "only, applied dataset-wide. Raw count_ok is never changed; "
                 "the scorer reports these as count_ok_adj."),
        "rows": out,
    }


def main() -> int:
    doc = build()
    OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    rows = json.loads(FIXTURE.read_text())["rows"]
    dev = {r["text"] for r in rows if int(r["tier_rank"]) <= 600}
    from collections import Counter
    total = Counter(v["class"] for v in doc["rows"].values())
    in_dev = Counter(v["class"] for t, v in doc["rows"].items() if t in dev)
    print(f"overrides written: {len(doc['rows'])}/{len(rows)} rows -> {OUT}")
    print(f"{'class':<18}{'dev(<=600)':>11}{'all':>7}")
    for cls, n in total.most_common():
        print(f"{cls:<18}{in_dev.get(cls, 0):>11}{n:>7}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
