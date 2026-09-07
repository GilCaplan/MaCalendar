"""K3 (Q10, Gil 2026-09-07) — the OPERATION subsystem's model, offline.

Q10 splits stage-2 routing into two tiered subsystems (KIND and OPERATION),
each rules-first with a logistic fallthrough. K1 proved the kind model; this
is the operation twin: OPERATION ∈ {new, edit, remove, complete, query},
trained on dataset B's train half (labels by construction; atomic
single-action rows only — mixed/propose excluded), judged against the
CURRENT router's operation accuracy on the same rows. B-test is reported as
an AGGREGATE only. Ships nothing — a win graduates into the Q10 router.

    python -m scripts.operation_classifier_experiment
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import os
import pathlib
import sys
import tempfile

_T = tempfile.mkdtemp(prefix="k3_")
for _v, _n in (("DB", "c"), ("MEMORY_DB", "m"), ("VOCAB", "v"),
               ("CATEGORIES", "cat"), ("TRACE_BUS", "t"), ("LOCATION", "l")):
    os.environ[f"MACALENDAR_{_v}"] = os.path.join(_T, _n)
os.environ["MACALENDAR_NO_WARMUP"] = "1"
for _b in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_b, "1")

ROOT = pathlib.Path(__file__).resolve().parents[1]
OPS = ("new", "edit", "remove", "complete", "query")
_ACTION2OP = {"create_event": "new", "create_todo": "new",
              "update_event": "edit", "update_todo": "edit",
              "delete_event": "remove", "delete_todo": "remove",
              "complete_todo": "complete", "query": "query"}


def _features(text: str) -> "list[float]":
    import re
    low = text.lower()
    def has(p): return 1.0 if re.search(p, low) else 0.0
    return [
        1.0,
        has(r"^\s*(?:add|book|schedule|create|put|set up|plan|make|new)\b"),
        has(r"\b(?:remind me|need to|have to|remember to|don'?t forget)\b"),
        has(r"^\s*(?:delete|remove|cancel|drop|clear|erase|scratch)\b"),
        has(r"\bfrom\s+(?:my|the)\b"),
        has(r"^\s*(?:move|reschedule|change|update|push|shift|postpone|rename|extend|shorten)\b"),
        has(r"\bto\s+(?:\d|noon|midnight|next|this|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b"),
        has(r"\b(?:as\s+)?(?:done|complete[d]?|finished)\b|\bcheck(?:ed)?\s+off\b|\balready did\b|\bi'?m done\b"),
        has(r"^\s*(?:what|which|when|show|list|tell me|do i have|how many|is there|what'?s)\b"),
        has(r"\bmy (?:schedule|day|week|agenda|calendar)\b"),
        has(r"\?\s*$"),
        has(r"\bat\s+\d|(?:\d|\b)(?:am|pm)\b"),
        has(r"\bas\s+(?:high|medium|low)\s+priority\b"),
        has(r"\binstead of\b|\bcall it\b|\brename\b"),
        has(r"\bevery\b|\bdaily\b|\bweekly\b"),
        has(r"^\s*(?:buy|get|pick up|grab|order)\b"),
    ]


FEATURE_NAMES = ["bias", "create-verb", "remind-speak", "delete-verb", "from-my",
                 "edit-verb", "to-when", "done-speak", "query-opener", "my-schedule",
                 "qmark", "clock", "priority", "rename-speak", "recur", "buy-verb"]


def _fit_ovr(X, labels):
    """One-vs-rest logistic, plain gradient descent — 5 × 16 weights."""
    W = {}
    n, d = len(X), len(X[0])
    for op in OPS:
        y = [1 if l == op else 0 for l in labels]
        w = [0.0] * d
        for _ in range(300):
            g = [0.0] * d
            for xi, yi in zip(X, y):
                z = sum(a * b for a, b in zip(w, xi))
                pz = 1.0 / (1.0 + math.exp(-max(-30, min(30, z))))
                e = pz - yi
                for j in range(d):
                    g[j] += e * xi[j]
            for j in range(d):
                w[j] -= 0.5 * g[j] / n
        W[op] = w
    return W


def _predict(W, x):
    return max(OPS, key=lambda op: sum(a * b for a, b in zip(W[op], x)))


def main() -> int:
    from freezegun import freeze_time
    from assistant.engine.fastrule import FastRule
    from assistant.intent.rule_parser import RULE_THRESHOLD

    FastRule(RULE_THRESHOLD).run("warm gym tomorrow at 7am")

    rows = [json.loads(l) for l in (ROOT / "dataset" / "fastrule" / "fastrule_7200.jsonl").open()]
    def op_of(r):
        a = r["expect"].get("action", "")
        if a in ("mixed", "propose") or not r["expect"].get("atomic", True):
            return None
        return _ACTION2OP.get(a) or ("query" if a == "query" else None)
    labeled = [(r, op_of(r)) for r in rows]
    train = [(r, o) for r, o in labeled if o and r["split"] == "train"]
    test = [(r, o) for r, o in labeled if o and r["split"] == "test"]
    print(f"atomic single-op rows: train {len(train)} · test {len(test)}")

    # --- baseline: the CURRENT router, coverage-honest -----------------
    fr = FastRule(0.01)     # floor bar: routing visible even where conf low
    def baseline_acc(pairs):
        ok = 0
        with freeze_time(_dt.datetime(2026, 9, 9, 10, 0)):
            for r, o in pairs:
                try:
                    res = fr.run(r["text"])
                except Exception:
                    continue
                if res and res.intents:
                    got = _ACTION2OP.get(res.intents[0][0],
                                         "query" if res.intents[0][0].startswith("query") else None)
                    ok += got == o
        return ok / len(pairs)

    Xtr = [_features(r["text"]) for r, _ in train]
    ytr = [o for _, o in train]
    W = _fit_ovr(Xtr, ytr)

    def clf_acc(pairs):
        return sum(_predict(W, _features(r["text"])) == o for r, o in pairs) / len(pairs)

    b_tr, c_tr = baseline_acc(train), clf_acc(train)
    b_te, c_te = baseline_acc(test), clf_acc(test)
    print(f"train    operation-accuracy: router {b_tr:.1%} · classifier {c_tr:.1%}")
    print(f"test     operation-accuracy: router {b_te:.1%} · classifier {c_te:.1%}  (aggregate only)")
    import collections
    per = collections.Counter(); tot = collections.Counter()
    for r, o in train:
        tot[o] += 1
        if _predict(W, _features(r["text"])) == o: per[o] += 1
    print("classifier per-class (train): " +
          " · ".join(f"{op} {per[op]/tot[op]:.0%}({tot[op]})" for op in OPS if tot[op]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
