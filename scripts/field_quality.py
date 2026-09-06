"""Field-level quality — do created items carry the RIGHT contents?

Gil's brief (2026-09-05): an event/task is not one atomic thing. Score its
components, split objective from subjective, and weight by what matters —
the when is paramount; a title should be short and similar (not necessarily
identical); location/description matter only in that they must not be
invented; a task's name, quantity and tag each count.

There is no per-field gold label in the dataset, so every check is grounded
on the TRANSCRIPT itself, replayed at the row's recorded timestamp:

  objective  — the words make the truth checkable ("at 11 am", "tomorrow",
               "5 apples"): hard pass/fail, but only where expressed —
               a component the words don't pin is UNCOVERED, excluded from
               the average and reported as coverage, never guessed.
  subjective — titles: a similarity score in [0,1] (content-word overlap
               with the transcript, small brevity penalty past 7 words),
               because "gym" vs "gym session" are both right.

Weights (documented, tunable):
  events: when 0.5 · title 0.3 · extras-grounded 0.2
  tasks:  title 0.5 · quantity 0.3 · tag 0.2

Aggregation is micro over items (a row that created 3 things weighs 3), with
per-complexity tiers and a difficulty-weighted headline (simple 1.0 /
medium 1.5 / complex 2.0) — a complex prompt scored right is worth more than
a simple one, per Gil.
"""
from __future__ import annotations

import datetime as _dt
import json
import re

STOPWORDS = frozenset(
    "a an the my your me i to for of on at in with and or then also please set "
    "add create make new book schedule remind reminder reminders it this that "
    "is are be will would can could you olly alexa pda am pm oclock o'clock".split())

_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday",
             "saturday", "sunday"]

_CLOCK_RE = re.compile(
    r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)\b|\b(\d{1,2}):(\d{2})\b", re.I)
_BARE_AT_RE = re.compile(r"\bat\s+(\d{1,2})\b(?!\s*:|\s*(?:am|pm))", re.I)


def _content_words(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9']+", (text or "").lower())
            if w not in STOPWORDS and not w.isdigit()}


def transcript_clock_hours(text: str) -> "set[tuple[int, int | None]]":
    """(hour mod 12, minutes-or-None) for every explicit time in the words.
    noon/midnight included; a bare "at 7" gives (7, None)."""
    out = set()
    for m in _CLOCK_RE.finditer(text):
        if m.group(1) is not None:
            out.add((int(m.group(1)) % 12, int(m.group(2)) if m.group(2) else None))
        else:
            out.add((int(m.group(4)) % 12, int(m.group(5))))
    for m in _BARE_AT_RE.finditer(text):
        out.add((int(m.group(1)) % 12, None))
    low = text.lower()
    if "noon" in low:
        out.add((0, 0))       # 12 % 12
    if "midnight" in low:
        out.add((0, 0))
    return out


def _time_ok(start_time: str, wanted: set) -> "bool | None":
    """None = uncovered (no explicit time in the words)."""
    if not wanted:
        return None
    m = re.match(r"(\d{1,2}):(\d{2})", start_time or "")
    if not m:
        return False
    hh, mm = int(m.group(1)) % 12, int(m.group(2))
    for wh, wm in wanted:
        if hh == wh and (wm is None or mm == wm):
            return True
    return False


def _date_ok(date_str: str, text: str, ts: float) -> "bool | None":
    """Checkable only for today/tonight/tomorrow and named weekdays."""
    try:
        ev = _dt.date.fromisoformat((date_str or "")[:10])
    except ValueError:
        return False
    now = _dt.datetime.fromtimestamp(ts).date()
    low = text.lower()
    checks = []
    if re.search(r"\btoday\b|\btonight\b", low):
        checks.append(ev == now)
    if re.search(r"\btomorrow\b", low):
        checks.append(ev == now + _dt.timedelta(days=1))
    named = [d for d in _WEEKDAYS if re.search(rf"\b{d}\b", low)]
    if named:
        checks.append(_WEEKDAYS[ev.weekday()] in named)
    if not checks:
        return None
    return any(checks)      # multi-event rows: matching ANY named day counts


def _title_sim(title: str, text: str) -> float:
    words = _content_words(title)
    if not words:
        return 0.0
    grounded = len(words & _content_words(text)) / len(words)
    brevity = 1.0 if len(words) <= 7 else max(0.3, 7 / len(words))
    return grounded * brevity


def _grounded_or_absent(value: str, text: str) -> "bool | None":
    """Extras (location/description/attendees): absent = uncovered; present
    must draw its words from the transcript (invention check)."""
    if not (value or "").strip():
        return None
    words = _content_words(value)
    if not words:
        return True
    return len(words & _content_words(text)) / len(words) >= 0.5


def _qty_ok(quantity: int, text: str) -> "bool | None":
    nums = set()
    for m in re.finditer(r"\b(\d{1,3})\b", text):
        tail = text[m.end():m.end() + 3]
        if re.match(r"\s*(:|am|pm)", tail, re.I):
            continue              # that's a clock time, not a count
        nums.add(int(m.group(1)))
    if not nums:
        return quantity in (None, 0, 1)   # nothing asked → default 1 is right
    return quantity in nums


def _tag_ok(tags: list, title: str, classes, reference) -> "bool | None":
    """Tags are CLASSIFICATION over a finite class set (Gil, 2026-09-05) —
    the registry's tag names, not fuzzy words. Two objective checks:
    (a) every assigned tag must BE one of the classes (an out-of-set tag is an
    invented class → fail outright); (b) when the product's own deterministic
    classifier (`tagging.suggest_tags`, injected as `reference`) names an
    expected class for this title, the assignment must include it. A valid
    assignment the reference can't adjudicate is uncovered. Note the honest
    limit: the reference is the product's classifier, so this catches
    class-set violations and divergence (e.g. LLM-assigned tags), not the
    classifier's own quality."""
    if classes is None:
        return None
    assigned = [str(x) for x in (tags or [])]
    if any(a not in classes for a in assigned):
        return False
    expected = list(reference(title)) if reference else []
    if expected:
        return bool(set(assigned) & set(expected))
    return None


def score_item(action: dict, text: str, ts: float,
               tag_classes=None, tag_reference=None) -> "dict | None":
    """One created item → {'score': 0..1, 'parts': {...}} or None (not a create)."""
    name = action.get("action", "")
    p = action.get("parameters", {}) or {}
    if name.startswith("create_event"):
        comps, weights = {}, {}
        comps["when"] = _combine_bools(
            _time_ok(p.get("start_time", ""), transcript_clock_hours(text)),
            _date_ok(p.get("date", ""), text, ts))
        weights["when"] = 0.5
        comps["title"] = _title_sim(p.get("title", ""), text)
        weights["title"] = 0.3
        extras = [_grounded_or_absent(str(p.get(k, "")), text)
                  for k in ("location", "description", "attendees")]
        known = [e for e in extras if e is not None]
        comps["extras"] = (sum(known) / len(known)) if known else None
        weights["extras"] = 0.2
        return _weigh(comps, weights, kind="event")
    if name.startswith("create_todo"):
        titles = p.get("titles") or []
        qtys = p.get("quantities") or []
        scores = []
        for i, title in enumerate(titles):
            comps = {"title": _title_sim(str(title), text)}
            weights = {"title": 0.5, "qty": 0.3, "tag": 0.2}
            comps["qty"] = _qty_ok(qtys[i] if i < len(qtys) else 1, text)
            comps["tag"] = _tag_ok(p.get("tags") or [], str(title),
                                   tag_classes, tag_reference)
            scores.append(_weigh(comps, weights, kind="task"))
        if not scores:
            return None
        # a multi-title todo action scores as the mean of its items
        return {"score": sum(s["score"] for s in scores) / len(scores),
                "parts": scores[0]["parts"], "kind": "task", "n": len(scores)}
    return None


def _combine_bools(*vals) -> "float | None":
    known = [v for v in vals if v is not None]
    if not known:
        return None
    return sum(1.0 for v in known if v) / len(known)


def _weigh(comps: dict, weights: dict, kind: str) -> dict:
    covered = {k: v for k, v in comps.items() if v is not None}
    if not covered:
        return {"score": 1.0, "parts": {}, "kind": kind, "n": 1}   # nothing checkable
    total_w = sum(weights[k] for k in covered)
    score = sum(weights[k] * (float(v)) for k, v in covered.items()) / total_w
    return {"score": score, "parts": {k: round(float(v), 3) for k, v in covered.items()},
            "kind": kind, "n": 1}


_TIER_WEIGHT = {"simple": 1.0, "medium": 1.5, "complex": 2.0}


def score_run(rows, prov, tag_classes=None, tag_reference=None) -> dict:
    """rows: iterable of (transcript, actions_json, ts). Returns overall +
    per-tier field quality, the paramount when-component alone, coverage, and
    the difficulty-weighted headline (complex counts double a simple)."""
    per_tier: dict = {}
    when_hits = when_n = 0
    items_n = 0
    for text, actions_json, ts in rows:
        try:
            actions = json.loads(actions_json or "[]")
        except json.JSONDecodeError:
            actions = []
        tier = (prov.get(text) or {}).get("complexity", "unknown")
        for a in actions:
            s = score_item(a, text, ts or _dt.datetime.now().timestamp(),
                           tag_classes, tag_reference)
            if s is None:
                continue
            t = per_tier.setdefault(tier, [0.0, 0])
            t[0] += s["score"] * s["n"]; t[1] += s["n"]
            items_n += s["n"]
            if "when" in s["parts"]:
                when_hits += s["parts"]["when"]; when_n += 1
    tiers = {t: round(v[0] / v[1], 3) for t, v in per_tier.items() if v[1]}
    overall = (sum(v[0] for v in per_tier.values())
               / max(1, sum(v[1] for v in per_tier.values())))
    ww = [(tiers[t], _TIER_WEIGHT[t]) for t in ("simple", "medium", "complex") if t in tiers]
    weighted = (sum(s * w for s, w in ww) / sum(w for _, w in ww)) if ww else None
    return {"field_quality": round(overall, 3),
            "by_tier": tiers,
            "difficulty_weighted": round(weighted, 3) if weighted is not None else None,
            "when_ok": round(when_hits / when_n, 3) if when_n else None,
            "when_coverage": when_n, "items": items_n}
