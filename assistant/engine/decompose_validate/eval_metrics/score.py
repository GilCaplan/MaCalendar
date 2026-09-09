"""Score decompose_validate: did each item's VALUES match what was said.

Segmentation is scored on WORDS — did the right words land in the right item.
This stage is scored on VALUES — did `"next friday"` become a Friday. The two
cannot be confused, which is the point of having both.

The metric names come from TempEval-3 / ISO-TimeML, which splits the same way:
Task A is (a) the EXTENT of a time expression and (b) its normalized WREN against
an anchor. Extent is segmentation's board; WREN is this one. So the headline is
**value accuracy conditioned on the item matching**, which keeps a segmentation
mistake from being charged to this stage.

    A  VALUES        per field, and all-fields-exact — the headline
    B  TRACEABILITY  a value no words support is an INVENTION (must be 0)
    C  HONOURED      every time phrase in the text reached some item's value
    D  CONTRADICTIONS internal impossibilities that need no gold at all
    E  COST          calls and latency per row
    F  COMPOSITION   what the score was computed OVER — anchors, traps, fields

Six boards, never one number. `dataset/METRICS.md`'s rule: a single figure hides
WHICH WAY a run fails, and the ways cost differently.

Imports are stdlib only — no `assistant`, no spacy, no torch — so this is safe
to import from inside a process that already holds a model.

    python -m assistant.engine.decompose_validate.eval_metrics.score   # self-test
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import re

#: The fields this stage is responsible for filling. `text`/`time`/`kind` are
#: segmentation's and are NOT scored here — scoring them would double-count a
#: segmentation error and make this board unreadable.
VALUE_FIELDS = ("date", "start_time", "end_time", "recurrence",
                "quantity", "reminder_minutes")

_WEEKDAY_NAME = ("monday", "tuesday", "wednesday", "thursday",
                 "friday", "saturday", "sunday")


# ---------------------------------------------------------------------------
# Matching — pair predicted items to gold, on the ACTION, not on position
# ---------------------------------------------------------------------------

def _tokens(s) -> set:
    return set(re.findall(r"[a-z0-9']+", str(s or "").lower()))


def match_items(gold: list, pred: list, threshold: float = 0.5):
    """Greedy best-first on action-token overlap. Returns (pairs, unmatched).

    Position would be the easy way and the wrong one: if the stage drops or
    reorders an item, position-matching charges every LATER item with a value
    error it did not make, and one boundary slip looks like total collapse.
    """
    cands = []
    for gi, g in enumerate(gold):
        for pi, p in enumerate(pred):
            a, b = _tokens(g.get("text")), _tokens(p.get("text"))
            if not a or not b:
                continue
            score = 2 * len(a & b) / (len(a) + len(b))
            if score >= threshold:
                cands.append((-score, gi, pi))
    cands.sort()
    used_g, used_p, pairs = set(), set(), []
    for _s, gi, pi in cands:
        if gi in used_g or pi in used_p:
            continue
        used_g.add(gi)
        used_p.add(pi)
        pairs.append((gi, pi))
    return (pairs,
            [i for i in range(len(gold)) if i not in used_g],
            [i for i in range(len(pred)) if i not in used_p])


# ---------------------------------------------------------------------------
# B · TRACEABILITY — the invariant, and this stage's analogue of no-invention
# ---------------------------------------------------------------------------

def _own_words(item: dict, text: str) -> str:
    """The words THIS item is answerable for — its own time and action.

    NOT the whole transcript. Both checks below asked the transcript at first,
    and both threw false positives for the same reason the stage they measure
    used to: in "book standup the 21st and yoga in two days", the `21st` belongs
    to the FIRST item, so charging the second with it is charging an item for a
    neighbour's words. Segmentation already decided who owns what; the checks
    have to respect that or they measure segmentation, not this stage.

    `text` is still accepted and used as a fallback for an item that carries no
    time of its own, where the transcript is all there is.
    """
    own = f"{item.get('time') or ''} {item.get('text') or ''}".strip()
    return (own or (text or "")).lower()


def untraceable(item: dict, text: str, today: str) -> list:
    """Values the words cannot support. Empty list = every value is grounded.

    The mirror of segmentation's no-invention rule, one level up: there the
    question is "did you add a WORD nobody said", here it is "did you add a
    VALUE nobody's words support".

    Deliberately CONSERVATIVE — it only fires when it is certain, because a
    false invention report would send someone hunting a bug that is not there.
    A date equal to the anchor is always fine (the floor), and a value whose
    number appears in the text is fine.
    """
    out = []
    tl = _own_words(item, text)

    date = item.get("date")
    if date and date != today:
        try:
            d = dt.date.fromisoformat(date)
        except ValueError:
            out.append(f"date {date!r} is not a date")
            d = None
        if d is not None:
            # Grounded if the text names its weekday, its day-of-month, its
            # month, or any relative phrase at all.
            says_weekday = _WEEKDAY_NAME[d.weekday()] in tl
            says_dom = re.search(rf"\b{d.day}(?:st|nd|rd|th)?\b", tl) is not None
            says_month = d.strftime("%B").lower() in tl
            says_relative = re.search(
                r"\b(tomorrow|tonight|today|next|this|coming|"
                r"in \w+ (?:day|week|month)s?|\w+ (?:day|week|month)s? from|"
                r"christmas|new year|every|each|weekend)\b", tl) is not None
            if not (says_weekday or says_dom or says_month or says_relative):
                out.append(f"date {date} unsupported by the words")

    for field in ("start_time", "end_time"):
        wren = item.get(field)
        if not wren:
            continue
        m = re.match(r"(\d{1,2}):(\d{2})", str(wren))
        if not m:
            out.append(f"{field} {wren!r} is not a time")
            continue
        h, mins = int(m.group(1)), m.group(2)
        h12 = h % 12 or 12
        # NOT \b — "7am" has no word boundary after the 7, so \b7\b misses it
        # and a CORRECT answer got reported as an invention. Digit-boundary
        # instead: not preceded or followed by another digit, which also stops
        # "17:00" matching a 7.
        if not (re.search(rf"(?<!\d){h}(?!\d)|(?<!\d){h12}(?!\d)", tl)
                or re.search(r"\b(noon|midday|midnight|lunchtime|morning|"
                             r"afternoon|evening|tonight|half past|quarter)\b", tl)):
            out.append(f"{field} {wren} unsupported by the words")

    q = item.get("quantity")
    if q and not re.search(rf"\b{q}\b", tl) and not re.search(
            r"\b(two|three|four|five|six|eight|twelve|dozen|couple|few)\b", tl):
        out.append(f"quantity {q} unsupported by the words")

    rec = item.get("recurrence")
    if rec and not re.search(r"\b(every|each|daily|weekly|monthly|nightly)\b", tl):
        out.append(f"recurrence {rec!r} unsupported by the words")
    return out


# ---------------------------------------------------------------------------
# D · CONTRADICTIONS — checkable with no gold at all
# ---------------------------------------------------------------------------

def contradictions(item: dict, text: str, today: str) -> list:
    """Internal impossibilities. These need NO gold, so they can be run over
    real traffic where no labels exist — which is what makes them worth having
    separately from the value board."""
    out = []
    tl = _own_words(item, text)
    st, en = item.get("start_time"), item.get("end_time")
    if st and en and str(en) <= str(st):
        out.append(f"end {en} is not after start {st}")

    date, until = item.get("date"), item.get("recur_until")
    if date and until and str(until) < str(date):
        out.append(f"recur_until {until} precedes the start {date}")

    if item.get("recur_until") and not item.get("recurrence"):
        out.append("recur_until with no recurrence")

    if date and today and str(date) < str(today):
        out.append(f"date {date} is in the past (anchor {today})")

    # A weekly series named a weekday: the start must BE that weekday.
    want = item.get("recurrence_weekday")
    if want and date:
        try:
            if _WEEKDAY_NAME[dt.date.fromisoformat(date).weekday()] != want:
                out.append(f"weekly series says {want} but starts on a "
                           f"{_WEEKDAY_NAME[dt.date.fromisoformat(date).weekday()]}")
        except ValueError:
            pass

    # The words name a day-of-month; the resolved date must use it.
    m = re.search(r"\bthe (\d{1,2})(?:st|nd|rd|th)\b", tl)
    if m and date:
        try:
            if dt.date.fromisoformat(date).day != int(m.group(1)):
                out.append(f"text says the {m.group(1)}th but date is {date}")
        except ValueError:
            pass
    return out


# ---------------------------------------------------------------------------
# C · HONOURED — every time phrase in the text reached some value
# ---------------------------------------------------------------------------

_PHRASE = re.compile(
    r"\b(today|tonight|tomorrow|yesterday|monday|tuesday|wednesday|thursday|"
    r"friday|saturday|sunday|next \w+|this \w+|in \w+ (?:days?|weeks?|months?)|"
    r"the \d{1,2}(?:st|nd|rd|th)|january|february|march|april|may|june|july|"
    r"august|september|october|november|december|every \w+|daily|weekly|"
    r"monthly|noon|midnight)\b", re.I)


def unhonoured(text: str, items: list) -> list:
    """Time phrases in the text that no item's `time` accounts for.

    The value-level analogue of segmentation's no-LOSS rule. Segmentation
    guarantees no WORD is dropped; this asks whether every time phrase actually
    reached a value. It is what catches a phrase being half-read — the month
    severed from its ordinal, for instance.
    """
    said = {m.group(0).lower() for m in _PHRASE.finditer(text or "")}
    covered = set()
    for item in items:
        blob = f"{item.get('time','')} {item.get('text','')}".lower()
        covered |= {p for p in said if p in blob}
    return sorted(said - covered)


# ---------------------------------------------------------------------------

def score_rows(rows: list, predict, samples: int = 8) -> dict:
    """rows -> the six boards. `predict(text, today) -> list[item] | dict`."""
    n = len(rows)
    field_ok = collections.Counter()
    field_n = collections.Counter()
    all_ok = matched = 0
    inv_items = inv_rows = 0
    contra_items = 0
    unhon_rows = unhon_phrases = 0
    miss_g = miss_p = 0
    calls = seconds = 0.0
    rows_reporting = 0
    by_anchor = collections.defaultdict(lambda: [0, 0])
    by_trap = collections.defaultdict(lambda: [0, 0])
    failures = []

    for row in rows:
        gold, text, today = row["gold"], row["text"], row["today"]
        out = predict(text, today)
        meta = out if isinstance(out, dict) else {}
        pred = (out.get("items") if isinstance(out, dict) else out) or []
        if meta:
            rows_reporting += 1
            calls += meta.get("calls") or 0
            seconds += meta.get("seconds") or 0.0

        pairs, mg, mp = match_items(gold, pred)
        miss_g += len(mg)
        miss_p += len(mp)

        row_ok = not mg and not mp
        for gi, pi in pairs:
            matched += 1
            g, p = gold[gi], pred[pi]
            item_ok = True
            for f in VALUE_FIELDS:
                want, got = g.get(f), p.get(f)
                if want is None and got is None:
                    continue
                field_n[f] += 1
                if str(want) == str(got):
                    field_ok[f] += 1
                else:
                    item_ok = False
            bad = untraceable(p, text, today)
            if bad:
                inv_items += 1
            if contradictions(p, text, today):
                contra_items += 1
            row_ok = row_ok and item_ok
        if any(untraceable(p, text, today) for p in pred):
            inv_rows += 1
        lost = unhonoured(text, pred)
        if lost:
            unhon_rows += 1
            unhon_phrases += len(lost)

        all_ok += row_ok
        by_anchor[today][0] += 1
        by_anchor[today][1] += row_ok
        for t in (row.get("traps") or ["(none)"]):
            by_trap[t][0] += 1
            by_trap[t][1] += row_ok
        if not row_ok and len(failures) < samples:
            failures.append({"id": row.get("id"), "text": text, "today": today,
                             "gold": gold, "pred": pred,
                             "why": (unhonoured(text, pred)
                                     or [c for p in pred for c in contradictions(p, text, today)]
                                     or ["a field value differs"])[:2]})

    return {
        "n_rows": n,
        "values": {"all_fields_exact": all_ok, "matched_items": matched,
                   "per_field": {f: (field_ok[f], field_n[f]) for f in VALUE_FIELDS}},
        "traceability": {"invention_items": inv_items, "invention_rows": inv_rows},
        "honoured": {"rows_with_a_lost_phrase": unhon_rows,
                     "phrases_lost": unhon_phrases},
        "contradictions": {"items": contra_items},
        "matching": {"unmatched_gold": miss_g, "unmatched_pred": miss_p},
        "cost": {"rows_reporting": rows_reporting, "calls": calls,
                 "calls_per_row": calls / n if n else 0,
                 "seconds_per_row": seconds / n if n else 0},
        "composition": {
            "by_anchor": {k: tuple(v) for k, v in sorted(by_anchor.items())},
            "by_trap": {k: tuple(v) for k, v in
                        sorted(by_trap.items(), key=lambda kv: -kv[1][0])}},
        "failures": failures,
    }


def _pc(ok, n) -> str:
    """THE project rate format (Gil, 2026-09-08): padded, and ALWAYS with x/n.

    `53.5%` alone cannot be read — 53 of 100 and 5,350 of 10,000 print the same
    and mean very different things. The denominator is what makes a rate a
    result. Three boards printed this three ways; this is the one.
    """
    return f"{ok / n:6.1%}  ({ok}/{n})" if n else "     —  (0/0)"


def format_board(r: dict) -> str:
    L: list = []
    add = L.append
    n = r["n_rows"]
    v = r["values"]
    add(f"decompose_validate board — {n} rows, {v['matched_items']} matched items")
    add("(items paired by action overlap ≥ 0.50, so a segmentation slip is not "
        "charged here)")

    add("\nA · VALUES — did the words become the right value")
    add(f"   all fields exact (row)     {_pc(v['all_fields_exact'], n)}   <- the headline")
    for f, (ok, fn) in v["per_field"].items():
        add(f"   {f:<24}  {_pc(ok, fn)}")

    t = r["traceability"]
    add("\nB · TRACEABILITY — a value the words do not support is an INVENTION")
    add(f"   invention items            {t['invention_items']}   MUST BE 0")
    add(f"   invention rows             {t['invention_rows']}")

    h = r["honoured"]
    add("\nC · HONOURED — every time phrase in the text reached a value")
    add(f"   rows with a lost phrase    {h['rows_with_a_lost_phrase']}   MUST BE 0")
    add(f"   phrases lost               {h['phrases_lost']}")

    add("\nD · CONTRADICTIONS — impossible on their own terms (no gold needed)")
    add(f"   items                      {r['contradictions']['items']}   MUST BE 0")

    m = r["matching"]
    add(f"\n   (matching: {m['unmatched_gold']} gold items unmatched, "
        f"{m['unmatched_pred']} predicted items spurious)")

    c = r["cost"]
    add("\nE · COST")
    add(f"   model calls / row          {c['calls_per_row']:.2f}")
    add(f"   seconds / row              {c['seconds_per_row']:.3f}")

    comp = r["composition"]
    add("\nF · COMPOSITION — what the numbers were computed OVER")
    add("   by anchor (the reference date the row was spoken on)")
    for anchor, (rn, ok) in comp["by_anchor"].items():
        add(f"      {anchor}  {rn:4d} rows   all-fields {_pc(ok, rn)}")
    add("   by trap")
    for trap, (rn, ok) in list(comp["by_trap"].items())[:14]:
        add(f"      {trap:<28} n={rn:<5} all-fields {_pc(ok, rn)}")

    if r.get("failures"):
        add("\n--- reading the failures (a pointer, not a board) ---")
        for f in r["failures"]:
            add(f"   [{f['id']}] {f['text'][:66]}   (anchor {f['today']})")
            add(f"      why  {f['why']}")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Self-test — the scorer must be able to SEE each defect it claims to measure
# ---------------------------------------------------------------------------

def _selftest() -> int:
    rows = [{"id": "t1", "text": "book gym tomorrow at 7am", "today": "2026-09-08",
             "traps": ["basic"],
             "gold": [{"kind": "event", "text": "book gym", "time": "tomorrow at 7am",
                       "date": "2026-09-09", "start_time": "07:00", "end_time": None,
                       "recurrence": None, "quantity": None,
                       "reminder_minutes": None}]}]

    def perfect(text, today):
        return [dict(rows[0]["gold"][0])]

    def wrong_date(text, today):
        it = dict(rows[0]["gold"][0]); it["date"] = "2026-09-08"; return [it]

    def invents(text, today):
        it = dict(rows[0]["gold"][0]); it["quantity"] = 7; return [it]

    def contradicts(text, today):
        it = dict(rows[0]["gold"][0]); it["end_time"] = "06:00"; return [it]

    def loses_phrase(text, today):
        it = dict(rows[0]["gold"][0]); it["time"] = ""; return [it]

    checks = []
    r = score_rows(rows, perfect)
    checks.append(("perfect scores 1/1", r["values"]["all_fields_exact"] == 1))
    checks.append(("perfect invents nothing", r["traceability"]["invention_items"] == 0))
    r = score_rows(rows, wrong_date)
    checks.append(("a wrong date fails the row", r["values"]["all_fields_exact"] == 0))
    checks.append(("...and is counted on the date field",
                   r["values"]["per_field"]["date"] == (0, 1)))
    r = score_rows(rows, invents)
    checks.append(("an unsupported quantity is an invention",
                   r["traceability"]["invention_items"] == 1))
    r = score_rows(rows, contradicts)
    checks.append(("end before start is a contradiction",
                   r["contradictions"]["items"] == 1))
    r = score_rows(rows, loses_phrase)
    checks.append(("a dropped time phrase is unhonoured",
                   r["honoured"]["phrases_lost"] >= 1))

    bad = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"   {'ok  ' if ok else 'FAIL'} {name}")
    print("\n" + ("self-test PASSED — every board sees its own defect"
                  if not bad else f"self-test FAILED: {bad}"))
    return 1 if bad else 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", nargs="*", help="score gold files instead of self-testing")
    a = ap.parse_args()
    if not a.rows:
        raise SystemExit(_selftest())
    rows = [json.loads(l) for p in a.rows for l in open(p) if l.strip()]
    print(f"{len(rows)} rows loaded")


if __name__ == "__main__":
    main()
