"""K1 (Q8, Gil-approved 2026-09-07) — can a tiny trained scorer beat the
event-vs-task regex family?

Offline experiment, no engine change: build (text → kind) labels from the
dataset's provenance (calendar/set = event, lists/createoradd = task,
event+event = event, task+task = task), score the CURRENT deterministic
labeler (segment's `_kind_of` + `_enforce_pinned_kinds`) as the baseline,
fit a logistic regression over hand features on the dev ranks (≤600), and
compare. Held-out ranks are reported as an AGGREGATE only, never mined.

The features ARE the existing regexes — the experiment asks whether a
weighted combination of the signals we already trust beats the hand-ordered
if-chain that combines them today. Pure-python gradient fit (no sklearn
dependency); the learned weights print so the model stays explainable.

    python -m scripts.kind_classifier_experiment
"""
from __future__ import annotations

import math
import os
import pathlib
import sys
import tempfile

_T = tempfile.mkdtemp(prefix="kind_exp_")
for _v, _n in (("DB", "c.db"), ("MEMORY_DB", "m.db"), ("VOCAB", "v.json"),
               ("CATEGORIES", "cat.json"), ("TRACE_BUS", "t.jsonl"),
               ("LOCATION", "l.json")):
    os.environ[f"MACALENDAR_{_v}"] = os.path.join(_T, _n)
os.environ["MACALENDAR_NO_WARMUP"] = "1"

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _features(text: str) -> "list[float]":
    """~15 binary signals, lifted from segment.py's own regex inventory."""
    import re
    from assistant.engine import segment as S

    t = text.strip()
    low = t.lower()
    return [
        1.0,                                               # bias
        1.0 if S._CLOCKISH_RE.search(t) else 0.0,          # clock time
        1.0 if S._DATED_RE.search(t) else 0.0,             # date reference
        1.0 if S._REMINDISH_RE.search(t) else 0.0,         # remind-flavour
        1.0 if S._REMIND_TO_VERB_RE.search(t) else 0.0,    # "remind me to <verb>"
        1.0 if S._OCCASION_RE.search(t) else 0.0,          # occasion noun
        1.0 if S._NEED_ENCOUNTER_RE.search(t) else 0.0,    # "i need to meet…"
        1.0 if S._TASK_RE.search(t) else 0.0,              # to-do phrasing
        1.0 if re.search(r"\b(?:buy|get|pick up|purchase|groceries)\b", low) else 0.0,
        1.0 if re.search(r"\b(?:list|to-?do|task)\b", low) else 0.0,
        1.0 if re.search(r"\b(?:calendar|schedule|book|appointment|invite)\b", low) else 0.0,
        1.0 if re.search(r"\bwith\s+[A-Z]?\w+\b", t) else 0.0,   # attendee-ish
        1.0 if re.search(r"\bat\s+\d", low) else 0.0,            # "at <num>"
        1.0 if re.search(r"\b(?:am|pm)\b", low) else 0.0,
        1.0 if re.search(r"\bevery\b", low) else 0.0,            # recurrence
        1.0 if len(t.split()) > 9 else 0.0,                      # long utterance
    ]


def _baseline_kind(text: str) -> str:
    """What the shipped deterministic labeler says today."""
    from assistant.engine import segment as S
    return S._enforce_pinned_kinds(S._kind_of(text), text)


def _fit(X: "list[list[float]]", y: "list[int]",
         epochs: int = 400, lr: float = 0.5) -> "list[float]":
    """Plain batch gradient descent on logistic loss — 16 weights, tiny data."""
    n, d = len(X), len(X[0])
    w = [0.0] * d
    for _ in range(epochs):
        grad = [0.0] * d
        for xi, yi in zip(X, y):
            z = sum(wj * xj for wj, xj in zip(w, xi))
            p = 1.0 / (1.0 + math.exp(-max(-30, min(30, z))))
            err = p - yi
            for j in range(d):
                grad[j] += err * xi[j]
        for j in range(d):
            w[j] -= lr * grad[j] / n
    return w


def _predict(w: "list[float]", x: "list[float]") -> int:
    z = sum(wj * xj for wj, xj in zip(w, x))
    return 1 if z >= 0 else 0


FEATURE_NAMES = ["bias", "clock", "dated", "remindish", "remind-to-verb",
                 "occasion", "encounter", "task-phrase", "buy-verbs",
                 "list-words", "calendar-words", "with-name", "at-num",
                 "am-pm", "every", "long"]


def main() -> int:
    from scripts.score_dataset_run import load_provenance

    KIND = {("calendar", "set"): "event", ("lists", "createoradd"): "task",
            ("compound", "event+event"): "event", ("compound", "task+task"): "task"}
    rows = []
    for r in load_provenance().values():
        k = KIND.get((r.get("scenario", ""), r.get("intent", "")))
        if k and r.get("tier_rank") is not None:
            rows.append((r["text"], k, r["tier_rank"]))
    dev = [(t, k) for t, k, rank in rows if rank <= 600]
    held = [(t, k) for t, k, rank in rows if rank > 600]
    print(f"labeled rows: {len(rows)} · dev {len(dev)} · held-out {len(held)}")

    # --- baseline: the shipped regex chain --------------------------------
    def acc_baseline(pairs):
        ok = sum(1 for t, k in pairs if _baseline_kind(t) == k)
        return ok / len(pairs)

    # --- classifier -------------------------------------------------------
    Xd = [_features(t) for t, _ in dev]
    yd = [1 if k == "event" else 0 for _, k in dev]
    w = _fit(Xd, yd)

    def acc_clf(pairs):
        ok = sum(1 for t, k in pairs
                 if _predict(w, _features(t)) == (1 if k == "event" else 0))
        return ok / len(pairs)

    b_dev, c_dev = acc_baseline(dev), acc_clf(dev)
    b_held, c_held = acc_baseline(held), acc_clf(held)
    print(f"dev      kind-accuracy: baseline {b_dev:.1%} · classifier {c_dev:.1%}")
    print(f"held-out kind-accuracy: baseline {b_held:.1%} · classifier {c_held:.1%}  (aggregate only)")
    print("\nlearned weights (positive → event):")
    for name, wj in sorted(zip(FEATURE_NAMES, w), key=lambda p: -abs(p[1])):
        print(f"  {name:16} {wj:+.2f}")

    # dev-only error mining: where does the WINNER still fail?
    print("\ndev disagreements with truth (classifier), first 10:")
    shown = 0
    for t, k in dev:
        if _predict(w, _features(t)) != (1 if k == "event" else 0) and shown < 10:
            print(f"  [{k}] {t[:70]}")
            shown += 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
