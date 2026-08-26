"""Seed the command memory (RAG) from DOCUMENTATION/NLU_TRACKING.md.

Rebuilds each SUCCESS entry into an example: transcript → actions with the
parameters we can recover from the result line (title, start/end time, todo
titles). Entries that were clearly wrong in practice — placeholder titles
('event'), an event request routed to create_todo, "couldn't find" results —
are stored as `rejected` so retrieval never uses them as a model answer.

Run once:  python -m scripts.seed_memory_from_history [--dry-run]
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assistant.intent.memory import get_memory  # noqa: E402

_TIME = r"(\d{1,2}(?::\d{2})? ?[AP]M)"


def _hhmm(t: str) -> str:
    t = t.replace(" ", "")
    return dt.datetime.strptime(t, "%I:%M%p" if ":" in t else "%I%p").strftime("%H:%M")


def parse_entries(path: str) -> list[dict]:
    text = open(path, encoding="utf-8").read()
    out = []
    for block in text.split("\n## ")[1:]:
        head = block.split("\n", 1)[0]
        if "SUCCESS" not in head:
            continue
        m_t = re.search(r"\*\*Transcript:\*\* `(.+?)`", block)
        m_a = re.search(r"\*\*Actions:\*\* ([\w, ]+)", block)
        m_p = re.search(r"\*\*Parse:\*\* (\S+ [^|]+)", block)
        if not m_t or not m_a:
            continue
        transcript = m_t.group(1).strip()
        actions = [a.strip() for a in m_a.group(1).split(",") if a.strip()]
        results = [l[2:].strip() for l in block.splitlines() if l.startswith("- ")]
        parse_path = "rule" if "rule" in (m_p.group(1) if m_p else "") else \
                     ("hybrid" if "hybrid" in (m_p.group(1) if m_p else "") else "llm")
        source = "ios" if "iOS" in head else "mac"

        acts, bad = [], []
        for i, a in enumerate(actions):
            r = results[i] if i < len(results) else ""
            params: dict = {}
            if a == "create_event":
                m = re.search(r"event '(.+?)'", r)
                if m:
                    params["title"] = m.group(1)
                m = re.search(rf"from {_TIME} to {_TIME}", r)
                if m:
                    params["start_time"], params["end_time"] = _hhmm(m.group(1)), _hhmm(m.group(2))
                m = re.search(r"recurring (\w+)", r)
                if m:
                    params["recurrence"] = m.group(1)
                if params.get("title", "").lower() in ("event", "meeting", "appointment", "activity", ""):
                    bad.append("placeholder title")
            elif a == "create_todo":
                m = re.search(r"Added '(.+?)'", r)
                if m:
                    params["titles"] = [m.group(1)]
                if re.search(r"\b(event|meeting|appointment)\b", transcript.lower()) and re.search(r"\d\s?(am|pm|a\.m|p\.m|o'clock)", transcript.lower()):
                    bad.append("event request routed to todo")
            elif a == "update_event":
                m = re.search(r"Updated '(.+?)'", r)
                if m:
                    params["match_title"] = m.group(1)
            if "couldn't find" in r.lower() or "not found" in r.lower():
                bad.append("target not found")
            acts.append((a, params))
        out.append({"transcript": transcript, "actions": acts, "result": " ".join(results),
                    "parse_path": parse_path, "source": source, "bad": bad})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default="DOCUMENTATION/NLU_TRACKING.md")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    entries = parse_entries(args.path)
    mem = get_memory()
    existing = {e["transcript"] for e in mem.recent(5000)}
    added = rejected = skipped = 0
    for e in entries:
        if e["transcript"] in existing:
            skipped += 1
            continue
        flag = "REJECT" if e["bad"] else "ok    "
        print(f"{flag}  {e['transcript'][:70]:70}  {[a for a, _ in e['actions']]}  {'; '.join(e['bad'])}")
        if args.dry_run:
            continue
        ex_id = mem.record(transcript=e["transcript"], source=e["source"], parse_path=e["parse_path"],
                           actions=e["actions"], result=e["result"], success=True)
        if e["bad"]:
            mem.set_feedback(ex_id, "rejected", notes="seeded from history: " + "; ".join(e["bad"]))
            rejected += 1
        else:
            added += 1
    print(f"\n{added} usable examples added, {rejected} stored as rejected, {skipped} already present"
          + (" (dry run — nothing written)" if args.dry_run else ""))


if __name__ == "__main__":
    main()
