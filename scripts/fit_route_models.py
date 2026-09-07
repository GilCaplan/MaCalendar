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


def _atomicity_rows(rows):
    """(texts, labels) for layer 0 — EVERY row teaches it, compounds and
    propose rows included: the question is "one item or several", not "what
    action"."""
    return ([r["text"] for r in rows],
            ["atomic" if r["expect"].get("atomic", True) else "compound"
             for r in rows])


def _binary_board(model, texts, labels, floor: float, header: str) -> str:
    """Layer 0's own board at a given margin floor.

    The generic per-class report is the wrong lens here: this is one binary
    decision with an ASYMMETRIC cost, and the two error KINDS have to be
    counted separately. A said-atomic-but-compound half-executes a two-ask
    command in front of the user; a said-compound-but-atomic costs one
    slow-path row. Rates hide that; counts do not.
    """
    tp = fp = fn = tn = 0
    for t, y in zip(texts, labels):
        lab, margin = model.predict(t)
        said = (lab == "compound" and margin >= floor)
        is_c = (y == "compound")
        tp += said and is_c; fp += said and not is_c
        fn += (not said) and is_c; tn += (not said) and not is_c
    n = len(labels) or 1
    P = tp / (tp + fp) if tp + fp else 0.0
    R = tp / (tp + fn) if tp + fn else 0.0
    F = 2 * P * R / (P + R) if P + R else 0.0
    return (f"{header} (floor {floor}) acc {(tp+tn)/n:.1%}  compound "
            f"P {P:.1%} R {R:.1%} F1 {F:.1%}\n"
            f"    said-compound-but-atomic {fp:>4} (cheap: one slow-path row)\n"
            f"    said-atomic-but-COMPOUND {fn:>4} (expensive: a half-executed "
            f"two-ask command)")


def _floor_sweep(model, texts, labels, header: str) -> str:
    """The margin floor is a decision threshold; it must be justified against
    the asymmetric cost, not assumed. Reported on TRAIN — choosing it on the
    test half would be tuning against the seal."""
    scored = [model.predict(t) for t in texts]
    ys = [y == "compound" for y in labels]
    out = [f"{header} — margin-floor sweep (train; cost = FP + k·FN)",
           "   floor     P      R     FP   FN   cost k=3  k=5  k=10"]
    for fl in (0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0):
        tp = fp = fn = 0
        for (lab, mg), y in zip(scored, ys):
            said = lab == "compound" and mg >= fl
            tp += said and y; fp += said and not y; fn += (not said) and y
        P = tp / (tp + fp) if tp + fp else 0.0
        R = tp / (tp + fn) if tp + fn else 0.0
        out.append(f"   {fl:<6.2f} {P:6.1%} {R:6.1%} {fp:>5} {fn:>4} "
                   f"{fp+3*fn:>9} {fp+5*fn:>4} {fp+10*fn:>5}")
    return "\n".join(out)


def main() -> int:
    rows = [json.loads(line) for line in DATA.open()]
    train = [r for r in rows if r["split"] == "train"]
    test = [r for r in rows if r["split"] == "test"]

    op_t, op_y, k_t, k_y = _labels(train)
    router = ModelRouter()
    router.operation.fit(op_t, op_y)
    router.kind.fit(k_t, k_y)
    a_t, a_y = _atomicity_rows(train)
    router.atomicity.fit(a_t, a_y)
    router.save(note=f"{DATA.name} train half only (leakage rule)")
    print(f"fit: operation {len(op_y)} rows · kind {len(k_y)} rows · "
          f"atomicity {len(a_y)} rows -> {router.weights_path.name}\n")

    print("--- train (working numbers) ---")
    print(router.operation.report(op_t, op_y, "operation"))
    print(router.kind.report(k_t, k_y, "kind     "))
    print(_binary_board(router.atomicity, a_t, a_y,
                        ModelRouter.ATOMIC_MARGIN_FLOOR, "atomicity"))
    print(_floor_sweep(router.atomicity, a_t, a_y, "atomicity B-train"))

    # SECOND DATASET (Gil: "use more than one dataset"). The verification
    # pool's real utterances, sealed 300 removed, own deterministic split —
    # its compounds are REAL wordings, which is the generalization B's
    # template expansion cannot measure. Train half only here; A-test is
    # reported by scripts/atomicity_board.py.
    try:
        from scripts.atomicity_board import a_rows
        arows = a_rows("train")
        print("\n" + _floor_sweep(
            router.atomicity, [t for t, _ in arows],
            ["compound" if c else "atomic" for _, c in arows],
            "atomicity A-train (verification pool, real wordings)"))
    except Exception as exc:                       # pragma: no cover
        print(f"\n(A-pool sweep skipped: {exc})")

    t_op_t, t_op_y, t_k_t, t_k_y = _labels(test)
    t_a_t, t_a_y = _atomicity_rows(test)
    print("\n=== TEST EVAL (the reported numbers) ===")
    print(router.operation.report(t_op_t, t_op_y, "operation"))
    print(router.kind.report(t_k_t, t_k_y, "kind     "))
    print(_binary_board(router.atomicity, t_a_t, t_a_y,
                        ModelRouter.ATOMIC_MARGIN_FLOOR, "atomicity B-test"))
    print("\n(the LAYER's board — rules ∪ model, on both datasets — is "
          "`python -m scripts.atomicity_board`)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
