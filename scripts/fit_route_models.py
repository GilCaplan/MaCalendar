"""Fit the routing models and emit their versioned weights file.

TRAIN DATA ONLY (leakage rule): dataset B's train half. The test half is
evaluated afterwards and REPORTED — never fitted on, never row-inspected.
Deterministic (fixed epochs, no randomness), so the emitted
`assistant/intent/route_model_weights.json` is reproducible; commit it like
any other constant.

The model, its features, the fit and the metrics all live in
`assistant/intent/classifier.py` — this script only assembles labels and
prints the report.

    python -m scripts.fit_route_models
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

_T = tempfile.mkdtemp(prefix="fit_route_")
for _v, _n in (("DB", "c"), ("MEMORY_DB", "m"), ("VOCAB", "v"),
               ("CATEGORIES", "cat"), ("TRACE_BUS", "t"), ("LOCATION", "l")):
    os.environ[f"MACALENDAR_{_v}"] = os.path.join(_T, _n)
os.environ["MACALENDAR_NO_WARMUP"] = "1"
for _b in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_b, "1")

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from assistant.intent.classifier import ModelRouter  # noqa: E402

DATA = ROOT / "dataset" / "fastrule" / "fastrule_7200.jsonl"

_ACTION2OP = {"create_event": "new", "create_todo": "new",
              "update_event": "edit", "update_todo": "edit",
              "delete_event": "remove", "delete_todo": "remove",
              "complete_todo": "complete", "query": "query"}
_ACTION2KIND = {"create_event": "event", "update_event": "event",
                "delete_event": "event", "create_todo": "task",
                "update_todo": "task", "delete_todo": "task",
                "complete_todo": "task"}


def _labels(rows):
    """(op_texts, op_labels, kind_texts, kind_labels) from atomic single-op
    rows. Compounds, and Q9's propose rows, teach nothing here: FastRule
    must DEFER on both, so training a router on them would teach the
    opposite of the product ruling."""
    op_t, op_y, k_t, k_y = [], [], [], []
    for r in rows:
        e = r["expect"]
        a = e.get("action", "")
        if a in ("mixed", "propose") or not e.get("atomic", True):
            continue
        op = _ACTION2OP.get(a) or ("query" if a == "query" else None)
        if op:
            op_t.append(r["text"]); op_y.append(op)
        kind = _ACTION2KIND.get(a)
        if kind:
            k_t.append(r["text"]); k_y.append(kind)
    return op_t, op_y, k_t, k_y


def main() -> int:
    rows = [json.loads(line) for line in DATA.open()]
    train = [r for r in rows if r["split"] == "train"]
    test = [r for r in rows if r["split"] == "test"]

    op_t, op_y, k_t, k_y = _labels(train)
    router = ModelRouter()
    router.operation.fit(op_t, op_y)
    router.kind.fit(k_t, k_y)
    # layer 0's model tier: every row teaches it, including compounds and
    # propose rows (the question is "one item or several", not "what action")
    a_t = [r["text"] for r in train]
    a_y = ["atomic" if r["expect"].get("atomic", True) else "compound" for r in train]
    router.atomicity.fit(a_t, a_y)
    router.save(note=f"{DATA.name} train half only (leakage rule)")
    print(f"fit: operation {len(op_y)} rows · kind {len(k_y)} rows "
          f"-> {router.weights_path.name}\n")

    print("--- train (working numbers) ---")
    print(router.operation.report(op_t, op_y, "operation"))
    print(router.kind.report(k_t, k_y, "kind     "))

    t_op_t, t_op_y, t_k_t, t_k_y = _labels(test)
    t_a_t = [r["text"] for r in test]
    t_a_y = ["atomic" if r["expect"].get("atomic", True) else "compound" for r in test]
    print("\n=== TEST EVAL (the reported numbers) ===")
    print(router.operation.report(t_op_t, t_op_y, "operation"))
    print(router.kind.report(t_k_t, t_k_y, "kind     "))
    print(router.atomicity.report(t_a_t, t_a_y, "atomicity"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
