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
    all_rows = [json.loads(l) for l in
                (ROOT / "dataset" / "fastrule" / "fastrule_6000.jsonl").open()]
    rows = [r for r in all_rows if r["split"] == "train"]

    # F14: the A-pool's real-usage wordings join the TRAINING text (never the
    # sealed 300 - load_test_split excludes them by text; B-test untouched).
    # A teaches the classes its labels support: kind via the K1 derivation,
    # operation for new/query/remove - hundreds of real phrasings for
    # exactly the starved classes.
    from scripts.score_dataset_run import load_provenance, load_test_split
    _sealed = load_test_split()
    A_KIND = {("calendar", "set"): "event", ("lists", "createoradd"): "task",
              ("compound", "event+event"): "event", ("compound", "task+task"): "task"}
    A_OP = {"set": "new", "createoradd": "new", "query": "query", "remove": "remove"}
    F14_MIX_A_POOL = False   # measured 2026-09-07: A-mixing costs B-test
                             # macro-F1 (op 73.4->69.3) - two dialects, one
                             # linear boundary. Kept as a switch for when a
                             # richer model or EXT variety changes the math.
    a_rows = []
    for r in (load_provenance().values() if F14_MIX_A_POOL else []):
        if r.get("tier_rank") is None or r["text"] in _sealed:
            continue
        sc, it = r.get("scenario", ""), r.get("intent", "")
        a_rows.append((r["text"], A_KIND.get((sc, it)),
                       A_OP.get(it) if sc != "compound" else None))
    op_X, op_y, k_X, k_y = [], [], [], []
    for text, kind, op in a_rows:
        if op:
            op_X.append(op_features(text)); op_y.append(op)
        if kind:
            k_X.append(kind_features(text)); k_y.append(kind)
    n_a_op, n_a_k = len(op_y), len(k_y)
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
    print(f"fit: operation on {len(op_y)} rows ({n_a_op} from A-pool) · "
          f"kind on {len(k_y)} rows ({n_a_k} from A-pool) -> {dest.name}")
    # train-side sanity (never test here)
    from assistant.intent.route_models import _scores, _top2

    def report(name, W, X, y, classes):
        preds = [_top2(_scores(W, x))[0] for x in X]
        acc = sum(p == t for p, t in zip(preds, y)) / len(y)
        print(f"{name} train-acc: {acc:.1%} · per-class P/R/F1:")
        f1s = []
        for c in classes:
            tp = sum(1 for p, t in zip(preds, y) if p == c and t == c)
            fp = sum(1 for p, t in zip(preds, y) if p == c and t != c)
            fn = sum(1 for p, t in zip(preds, y) if p != c and t == c)
            P = tp / (tp + fp) if tp + fp else 0.0
            R = tp / (tp + fn) if tp + fn else 0.0
            F = 2 * P * R / (P + R) if P + R else 0.0
            f1s.append(F)
            print(f"    {c:<9} P {P:.0%}  R {R:.0%}  F1 {F:.0%}  (n={tp+fn})")
        print(f"    macro-F1 {sum(f1s)/len(f1s):.1%}")

    report("operation (train, working numbers)", out["operation"], op_X, op_y, OPS)
    report("kind      (train, working numbers)", out["kind"], k_X, k_y, ("event", "task"))

    # ---- TEST EVAL (the reported numbers — Gil 2026-09-07): eval-only,
    # class-level rates, never row inspection, never a fit input ----------
    t_op_X, t_op_y, t_k_X, t_k_y = [], [], [], []
    for r in all_rows:
        if r["split"] != "test":
            continue
        e = r["expect"]; a = e.get("action", "")
        if a in ("mixed", "propose") or not e.get("atomic", True):
            continue
        op = _ACTION2OP.get(a) or ("query" if a == "query" else None)
        if op:
            t_op_X.append(op_features(r["text"])); t_op_y.append(op)
        kind = _ACTION2KIND.get(a)
        if kind:
            t_k_X.append(kind_features(r["text"])); t_k_y.append(kind)
    print("\n=== TEST EVAL (the reported numbers) ===")
    report("operation (TEST)", out["operation"], t_op_X, t_op_y, OPS)
    report("kind      (TEST)", out["kind"], t_k_X, t_k_y, ("event", "task"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
