"""Fit the Q10 route models and emit their versioned weights file.

TRAIN DATA ONLY (leakage rule): dataset B's train half — the test half and
the sealed real-pool 300 never enter a fit. Deterministic (fixed epochs, no
randomness), so the emitted `assistant/intent/route_model_weights.json` is
reproducible; commit it like any constant.

    python -m scripts.fit_route_models
"""
from __future__ import annotations

import json
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from assistant.intent.route_models import OPS, kind_features, op_features  # noqa: E402

_ACTION2OP = {"create_event": "new", "create_todo": "new",
              "update_event": "edit", "update_todo": "edit",
              "delete_event": "remove", "delete_todo": "remove",
              "complete_todo": "complete", "query": "query"}
_ACTION2KIND = {"create_event": "event", "update_event": "event",
                "delete_event": "event", "create_todo": "task",
                "update_todo": "task", "delete_todo": "task",
                "complete_todo": "task"}


def _fit_ovr(X, labels, classes, epochs=300, lr=0.5, balanced=True):
    n, d = len(X), len(X[0])
    counts = {c: max(1, sum(1 for l in labels if l == c)) for c in classes}
    W = {}
    for c in classes:
        # class-balanced: each class contributes equally to the gradient
        # (K3's lesson — 70% "new" rows drowned the starved classes)
        wpos = (n / (2.0 * counts[c])) if balanced else 1.0
        wneg = (n / (2.0 * (n - counts[c]))) if balanced and n > counts[c] else 1.0
        y = [1 if l == c else 0 for l in labels]
        w = [0.0] * d
        for _ in range(epochs):
            g = [0.0] * d
            for xi, yi in zip(X, y):
                z = sum(a * b for a, b in zip(w, xi))
                p = 1.0 / (1.0 + math.exp(-max(-30, min(30, z))))
                e = (p - yi) * (wpos if yi else wneg)
                for j in range(d):
                    g[j] += e * xi[j]
            for j in range(d):
                w[j] -= lr * g[j] / n
        W[c] = w
    return W


def main() -> int:
    rows = [json.loads(l) for l in
            (ROOT / "dataset" / "fastrule" / "fastrule_6000.jsonl").open()
            if '"train"' in l]
    op_X, op_y, k_X, k_y = [], [], [], []
    for r in rows:
        e = r["expect"]
        a = e.get("action", "")
        if a in ("mixed", "propose") or not e.get("atomic", True):
            continue
        op = _ACTION2OP.get(a) or ("query" if a == "query" else None)
        if op:
            op_X.append(op_features(r["text"])); op_y.append(op)
        kind = _ACTION2KIND.get(a)
        if kind:
            k_X.append(kind_features(r["text"])); k_y.append(kind)
    out = {
        "fitted_on": "fastrule_6000 train half only (leakage rule)",
        "operation": _fit_ovr(op_X, op_y, OPS),
        "kind": _fit_ovr(k_X, k_y, ("event", "task")),
    }
    dest = ROOT / "assistant" / "intent" / "route_model_weights.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"fit: operation on {len(op_y)} rows · kind on {len(k_y)} rows -> {dest.name}")
    # train-side sanity (never test here)
    from assistant.intent.route_models import _scores, _top2
    ok = sum(1 for x, y in zip(op_X, op_y) if _top2(_scores(out["operation"], x))[0] == y)
    print(f"operation train-acc (balanced fit): {ok/len(op_y):.1%}")
    ok = sum(1 for x, y in zip(k_X, k_y) if _top2(_scores(out["kind"], x))[0] == y)
    print(f"kind      train-acc: {ok/len(k_y):.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
