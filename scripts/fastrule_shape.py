"""Score FastRule against its PRODUCT SHAPE (Gil, 2026-09-07).

FastRule is the atomic-item executor. So the only two questions that matter:

PRIMARY (Gil, 2026-09-07 — "I just want to see that it succeeds on
recognising and executing well on atomic items"):

    ATOMIC rows  → did it HANDLE them, and was it RIGHT?

NON-ATOMIC rows are DIAGNOSTIC, not a target. Gil's ruling: a compound runs
through FastRule anyway, and whatever it finds is PASSED TO THE NEXT STAGE
for the engine to decide (that is what the REFUSAL / STRUCTURE / INCAPACITY
deferral contract carries). So the three outcomes are reported without one
being "the metric":

    covered       committed, and every ask is present — the "easy enough to
                  complete" case Gil's product shape explicitly allows, and
                  the only path that still works with the LLM unreachable
    half-executed committed but an ask is MISSING — the real defect, and the
                  only one worth driving to zero
    deferred      handed up with a reason — also correct

    python -m scripts.fastrule_shape                # test split (reported)
    python -m scripts.fastrule_shape --split train  # mining
"""
from __future__ import annotations

import argparse
import collections
import datetime as _dt
import json
import os
import pathlib
import re
import sys
import tempfile

_T = tempfile.mkdtemp(prefix="fr_shape_")
for _v, _n in (("DB", "c"), ("MEMORY_DB", "m"), ("VOCAB", "v"),
               ("CATEGORIES", "cat"), ("TRACE_BUS", "t"), ("LOCATION", "l")):
    os.environ[f"MACALENDAR_{_v}"] = os.path.join(_T, _n)
os.environ["MACALENDAR_NO_WARMUP"] = "1"
for _b in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_b, "1")

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "dataset" / "fastrule" / "fastrule_7200.jsonl"
_CLOCK = _dt.datetime(2026, 9, 9, 10, 0)
#: the layer-0 verdicts — a defer carrying one of these means FastRule
#: RECOGNISED the compound, rather than tripping over it by luck
_ATOMICITY_REASONS = {"strong-compound", "clause-coordination", "mixed-mode-compound", "model-compound"}

#: An EXPLICIT spoken time — a digit or a named hour. These are the ones a
#: parse can get objectively wrong, so they are scored against the produced
#: start_time. Vague dayparts ("late afternoon") are deliberately excluded:
#: the engine maps them by a documented convention, and scoring our own
#: convention against itself would prove nothing.
_EXPLICIT_TIME_RE = re.compile(
    r"\b\d{1,2}\s*(?::\d{2})?\s*(?:am|pm)\b|\b\d{1,2}:\d{2}\b"
    r"|\bnoon\b|\bmidnight\b|\bquarter (?:to|past)\b|\bhalf past\b", re.I)

_HHMM = re.compile(r"^\d{2}:\d{2}$")
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_WEEKDAY = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6}
_MONTH = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}


def _phrase_to_date(phrase: str, today: "_dt.date") -> "str | None":
    """Resolve a ground-truth date phrase to an ISO date, or None when the
    phrase is inherently a RANGE ("next week", "this weekend") — those have
    no single right answer, so they are excluded from scoring rather than
    guessed at. Dates had NO metric at all until now (Gil, 2026-09-07);
    times were added the same day and immediately exposed a live defect.
    """
    s = (phrase or "").strip().lower()
    if s in ("today", "this afternoon", "this evening", "this morning", "tonight"):
        return today.isoformat()
    if s in ("tomorrow", "tomorrow morning", "tomorrow afternoon", "tomorrow evening"):
        return (today + _dt.timedelta(days=1)).isoformat()
    if s in ("the day after tomorrow",):
        return (today + _dt.timedelta(days=2)).isoformat()
    m = re.match(r"in (\d+|a|two|three|four|five|six|seven) days?$", s)
    if m:
        n = {"a": 1, "two": 2, "three": 3, "four": 4, "five": 5,
             "six": 6, "seven": 7}.get(m.group(1))
        n = n if n else int(m.group(1))
        return (today + _dt.timedelta(days=n)).isoformat()
    m = re.match(r"(?:this|next|coming|on)\s+(\w+day)$", s)
    if m and m.group(1) in _WEEKDAY:
        delta = (_WEEKDAY[m.group(1)] - today.weekday()) % 7
        if s.startswith("next"):
            delta = delta or 7
        return (today + _dt.timedelta(days=delta or 7 if s.startswith("next") else delta)).isoformat()
    m = re.match(r"(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?$", s)
    if m:                                   # "the 21st" — this month or next
        day = int(m.group(1))
        cand = today.replace(day=day) if day >= today.day else None
        if cand is None:
            nm = (today.replace(day=28) + _dt.timedelta(days=4)).replace(day=1)
            cand = nm.replace(day=day)
        return cand.isoformat()
    m = re.match(r"(\w+)\s+(\d{1,2})(?:st|nd|rd|th)?$", s)
    if m and m.group(1) in _MONTH:          # "march 5th"
        mo, day = _MONTH[m.group(1)], int(m.group(2))
        yr = today.year + (1 if (mo, day) < (today.month, today.day) else 0)
        return _dt.date(yr, mo, day).isoformat()
    return None                             # ranges and anything unresolved


#: How much a wrong commit COSTS the user (Gil, 2026-09-07). A wrong title is
#: an annoyance; a wrong DELETE destroys something they may not get back. The
#: project already rules that "deleting is destructive" — the metric should
#: say so too, or the loop has no reason to prefer failing safely.
_SEVERITY = {
    "delete_event": 4, "delete_todo": 4,     # irreversible-ish loss
    "update_event": 2, "update_todo": 2,     # overwrote something real
    "complete_todo": 2,                      # marked the wrong thing done
    "create_event": 1, "create_todo": 1,     # a spurious row, easily removed
    "query": 0, "query_schedule": 0, "query_todos": 0,   # read-only
}


def _phrase_to_hhmm(phrase: str) -> "str | None":
    """Resolve an explicit spoken time to HH:MM, or None if it isn't one."""
    s = (phrase or "").strip().lower()
    words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
             "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
             "twelve": 12}
    m = re.match(r"quarter to (\w+)$", s)
    if m and (m.group(1) in words or m.group(1).isdigit()):
        h = (words.get(m.group(1)) or int(m.group(1))) - 1
        return f"{(12 if h == 0 else h):02d}:45"
    m = re.match(r"(?:quarter past|half past) (\w+)$", s)
    if m and (m.group(1) in words or m.group(1).isdigit()):
        h = words.get(m.group(1)) or int(m.group(1))
        return f"{h:02d}:{'15' if s.startswith('quarter') else '30'}"
    if s in ("noon", "midday"):
        return "12:00"
    if s == "midnight":
        return "00:00"
    m = re.match(r"(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", s)
    if m:
        h = int(m.group(1)); mins = m.group(2) or "00"; ap = m.group(3)
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
        return f"{h:02d}:{mins}"
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=("train", "test"), default="test")
    a = ap.parse_args()
    mining = a.split == "train"

    from freezegun import freeze_time
    from assistant.engine.fastrule import FastRule
    from assistant.intent.rule_parser import RULE_THRESHOLD

    fr = FastRule(RULE_THRESHOLD)
    fr.run("book gym tomorrow at 7am")          # warm outside the frozen clock

    rows = [json.loads(l) for l in DATA.open() if f'"{a.split}"' in l]
    rows = [r for r in rows if r["split"] == a.split]

    # atomic buckets: a propose row is atomic-but-must-not-commit (Q9), so it
    # gets its own bucket rather than polluting either side
    A_OK = A_MISS = A_WRONG = 0          # atomic: committed-right / deferred / committed-wrong
    N_DEFER = N_COMMIT = N_COMMIT_OK = 0  # non-atomic: deferred / committed (violation)
    N_DEFER_KNEW = 0                      # ...deferred BECAUSE it saw the compound
    P_DEFER = P_COMMIT = 0                # propose rows
    T_OK = T_N = 0                        # explicit times: right / scored
    INVENT = INVENT_N = 0                 # a time produced where none was said
    D_OK = D_N = 0                        # resolvable dates: right / scored
    HARM = 0                              # severity-weighted cost of wrong commits
    HARM_BY: collections.Counter = collections.Counter()
    viol: collections.Counter = collections.Counter()
    miss_reason: collections.Counter = collections.Counter()
    samples: dict = collections.defaultdict(list)

    with freeze_time(_CLOCK):
        for r in rows:
            e = r["expect"]
            act = e.get("action", "")
            res = fr.run(r["text"])
            committed = bool(res and res.committed)
            if act == "propose":
                if committed:
                    P_COMMIT += 1
                    if mining and len(samples["propose-commit"]) < 5:
                        samples["propose-commit"].append(r["text"][:60])
                else:
                    P_DEFER += 1
                continue
            if not e.get("atomic", True):
                if committed:
                    N_COMMIT += 1
                    ev = sum(1 for n, _ in res.intents if n == "create_event")
                    td = sum(1 for n, _ in res.intents if n == "create_todo")
                    ok = ev >= e.get("events", 0) and td >= e.get("tasks", 0)
                    N_COMMIT_OK += 1 if ok else 0
                    viol[r["family"].rsplit("_", 1)[0]] += 1
                    if mining and len(samples["nonatomic-commit"]) < 8:
                        samples["nonatomic-commit"].append(
                            f"[{'ok' if ok else 'WRONG'}] {r['text'][:56]}")
                else:
                    N_DEFER += 1
                    # deferred for the RIGHT reason (the atomicity layer saw
                    # the compound) vs by accident (low confidence, missing
                    # slot) — only the former survives as FastRule improves
                    if (res.reason or "").split(":")[0] in _ATOMICITY_REASONS:
                        N_DEFER_KNEW += 1
                continue
            # atomic row
            if not committed:
                A_MISS += 1
                miss_reason[(res.reason or "none").split(":")[0]] += 1
                if mining and len(samples["atomic-deferred"]) < 10:
                    samples["atomic-deferred"].append(
                        f"[{(res.reason or '?').split(':')[0]}] {r['text'][:52]}")
                continue
            ev = sum(1 for n, _ in res.intents if n == "create_event")
            td = sum(1 for n, _ in res.intents if n == "create_todo")
            names = [n for n, _ in res.intents]
            if act in ("create_event", "create_todo"):
                ok = ev >= e.get("events", 0) and td >= e.get("tasks", 0)
            elif act == "query":
                ok = (ev + td) == 0 and any(n.startswith("query") for n in names)
            else:
                ok = (ev + td) == 0 and any(n.startswith(act.split("_")[0]) for n in names)
            # --- TIME CORRECTNESS (added 2026-09-07): neither scorer looked
            # at the time before, so a parser that invents plausible times
            # could only ever LOOK better. An autonomous loop must not be
            # blind to the field users care most about.
            # --- DATE CORRECTNESS: times were scored first and immediately
            # found a defect; dates had the same exposure and no metric.
            if act in ("create_event", "create_todo"):
                firstc = next((i for n, i in res.intents
                               if n.startswith("create")), None)
                got_d = str(getattr(firstc, "date", "")
                            or getattr(firstc, "due_date", "") or "")
                dphrase = (e.get("slots", {}) or {}).get("date_phrase") or ""
                if dphrase and _ISO.match(got_d):
                    want_d = _phrase_to_date(dphrase, _CLOCK.date())
                    if want_d:              # ranges resolve to None: not scored
                        D_N += 1
                        D_OK += 1 if got_d == want_d else 0
            if act == "create_event":
                first = next((i for n, i in res.intents
                              if n == "create_event"), None)
                got_t = str(getattr(first, "start_time", "") or "")
                phrase = (e.get("slots", {}) or {}).get("time_phrase") or ""
                if phrase and _EXPLICIT_TIME_RE.search(phrase):
                    want = _phrase_to_hhmm(phrase)
                    if want and _HHMM.match(got_t):
                        T_N += 1
                        T_OK += 1 if got_t == want else 0
                elif not phrase:
                    # nothing was said about a time: 00:00 (all-day) is the
                    # honest answer, anything else is an invention
                    INVENT_N += 1
                    if _HHMM.match(got_t) and got_t != "00:00":
                        INVENT += 1
            if ok:
                A_OK += 1
            else:
                A_WRONG += 1
                # what did this wrong commit COST? (severity, not just count)
                for nm, _ in res.intents:
                    w = _SEVERITY.get(nm, 1)
                    HARM += w
                    if w >= 2:
                        HARM_BY[nm] += 1
                if mining and len(samples["atomic-wrong"]) < 8:
                    samples["atomic-wrong"].append(f"[{act}→{names}] {r['text'][:48]}")

    A_N = A_OK + A_WRONG + A_MISS
    N_N = N_DEFER + N_COMMIT
    P_N = P_DEFER + P_COMMIT
    def pc(x, n): return f"{x/n:.1%}" if n else "—"
    print(f"[{a.split}] FastRule product-shape board\n")
    print(f"ATOMIC rows ({A_N}) — should HANDLE")
    print(f"   handled (committed)      {pc(A_OK + A_WRONG, A_N)}")
    print(f"   correct-on-handled       {pc(A_OK, A_OK + A_WRONG)}")
    print(f"   deferred (missed work)   {pc(A_MISS, A_N)}")
    if D_N:
        print(f"\nDATE CORRECTNESS (on committed creates)")
        print(f"   resolvable date right    {pc(D_OK, D_N)}  (n={D_N}; "
              f"range phrases like 'next week' excluded, no single right answer)")
    if A_WRONG:
        print(f"\nHARM (severity-weighted cost of wrong commits)")
        print(f"   harm score               {HARM}  over {A_WRONG} wrong commits "
              f"(delete=4 · update/complete=2 · create=1 · query=0)")
        if HARM_BY:
            print(f"   DESTRUCTIVE errors       "
                  + " · ".join(f"{k} {v}" for k, v in HARM_BY.most_common(4)))
        else:
            print(f"   DESTRUCTIVE errors       none — every wrong commit was "
                  f"a spurious row, not a loss")
    if T_N or INVENT_N:
        print(f"\nTIME CORRECTNESS (on committed events)")
        print(f"   explicit time right      {pc(T_OK, T_N)}  (n={T_N})")
        print(f"   INVENTED a time          {pc(INVENT, INVENT_N)}  "
              f"(n={INVENT_N} events where the speaker named no time)")
    print(f"\nNON-ATOMIC rows ({N_N}) — diagnostic; the engine decides")
    print(f"   deferred, handed up      {pc(N_DEFER, N_N)}")
    print(f"     ...knew it was compound {pc(N_DEFER_KNEW, N_N)}  (layer 0 said so)")
    print(f"     ...by accident          {pc(N_DEFER - N_DEFER_KNEW, N_N)}  (low confidence / missing slot)")
    print(f"   covered (all asks present) {N_COMMIT_OK} ({pc(N_COMMIT_OK, N_N)})  — acceptable")
    print(f"   HALF-EXECUTED             {N_COMMIT - N_COMMIT_OK} "
          f"({pc(N_COMMIT - N_COMMIT_OK, N_N)})  <- the defect that matters")
    print(f"\nPROPOSE rows ({P_N}) — should DEFER (Q9)")
    print(f"   defer rate               {pc(P_DEFER, P_N)}  · violations {P_COMMIT}")
    if not mining:
        print("\n(test split: aggregates only — leakage guard)")
        return 0
    print("\n--- mining (train only) ---")
    print("atomic rows deferred, by reason:")
    for k, v in miss_reason.most_common(8):
        print(f"   {v:>4}  {k}")
    for k in ("atomic-deferred", "atomic-wrong", "nonatomic-commit", "propose-commit"):
        if samples[k]:
            print(f"\n{k}:")
            for s in samples[k]:
                print(f"   {s}")
    if viol:
        print("\nviolating families:")
        for k, v in viol.most_common(6):
            print(f"   {v:>3}  {k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
