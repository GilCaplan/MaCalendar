"""The ATOMICITY binary board — layer 0's own scorecard, on both datasets.

Layer 0 answers one binary question: **is this ONE atomic item, or several?**
Everything downstream rests on it — FastRule is the atomic-item executor and
the deep track is the atomizer — so it deserves a board of its own rather
than being read off the product-shape numbers.

The cost is ASYMMETRIC and the board says so in counts, not just rates:

    FN "said atomic, was compound"  -> FastRule half-executes a two-ask
                                       command. USER-FACING. Expensive.
    FP "said compound, was atomic"  -> the row takes the slow path. Cheap.

So compound RECALL is the metric to move, with precision as the guard rail.

Two datasets, reported separately (Gil, 2026-09-07 — "use more than one
dataset"):

    B = dataset/fastrule/fastrule_7200.jsonl   `expect.atomic` is ground
        truth BY CONSTRUCTION; split by pattern family, so the test half is
        wordings never trained on. Generated, so its compound phrasings are
        template-shaped.
    A = the verification pool (memory_scaling/hwu64_sample.json), REAL
        utterances; `scenario == "compound"` (event+event / task+task /
        event+task) is compound, every other scenario is atomic. The sealed
        300 are removed before anything else happens. A's compounds are real
        wordings — exactly the generalization B cannot measure.

A has no pattern families, so its train/test split is a deterministic
sha1-of-text bucket (25% test) — reproducible, no seed file, and the same
rows every run.

Three predictors are scored so the wiring can be blamed separately from the
model:

    rules   the three gates alone (strong-compound / clause-coordination /
            mixed-mode)
    model   ModelRouter.atomicity alone, at a given margin floor
    layer   Atomicity.judge() as actually wired — what the product does

    python -m scripts.atomicity_board                    # B-test + A-test
    python -m scripts.atomicity_board --split train      # mining half
    python -m scripts.atomicity_board --sweep            # margin-floor sweep
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import pathlib
import sys
import tempfile

_T = tempfile.mkdtemp(prefix="atom_board_")
for _v, _n in (("DB", "c"), ("MEMORY_DB", "m"), ("VOCAB", "v"),
               ("CATEGORIES", "cat"), ("TRACE_BUS", "t"), ("LOCATION", "l")):
    os.environ[f"MACALENDAR_{_v}"] = os.path.join(_T, _n)
os.environ["MACALENDAR_NO_WARMUP"] = "1"
for _b in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_b, "1")

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

B_DATA = ROOT / "dataset" / "fastrule" / "fastrule_7200.jsonl"
A_DATA = ROOT / "DOCUMENTATION" / "experiments" / "memory_scaling" / "hwu64_sample.json"
_CLOCK = _dt.datetime(2026, 9, 9, 10, 0)


# ---------------------------------------------------------------------------
# The two datasets, as (text, is_compound) with a train/test half each
# ---------------------------------------------------------------------------

def b_rows(split: str) -> "list[tuple[str, bool]]":
    """FastRule 7,200 — `expect.atomic` is ground truth by construction."""
    out = []
    for line in B_DATA.open():
        r = json.loads(line)
        if r["split"] != split:
            continue
        out.append((r["text"], not r["expect"].get("atomic", True)))
    return out


def a_bucket(text: str) -> str:
    """Deterministic 75/25 train/test bucket for a real-pool row."""
    h = int(hashlib.sha1(text.encode("utf-8")).hexdigest()[:8], 16)
    return "test" if h % 4 == 0 else "train"


def a_rows(split: str) -> "list[tuple[str, bool]]":
    """The verification pool minus the sealed 300. `scenario == "compound"`
    is the ground truth; every other scenario is one atomic item."""
    from scripts.score_dataset_run import load_test_split
    sealed = load_test_split()
    data = json.loads(A_DATA.read_text())
    out = []
    for r in data["rows"]:
        t = r["text"]
        if t in sealed:                       # the seal, honoured first
            continue
        if split != "all" and a_bucket(t) != split:
            continue
        out.append((t, r.get("scenario") == "compound"))
    return out


# ---------------------------------------------------------------------------
# The board
# ---------------------------------------------------------------------------

def score(preds, ys) -> dict:
    tp = sum(1 for p, y in zip(preds, ys) if p and y)
    fp = sum(1 for p, y in zip(preds, ys) if p and not y)
    fn = sum(1 for p, y in zip(preds, ys) if not p and y)
    tn = sum(1 for p, y in zip(preds, ys) if not p and not y)
    n = len(ys) or 1
    P = tp / (tp + fp) if tp + fp else 0.0
    R = tp / (tp + fn) if tp + fn else 0.0
    return {"n": len(ys), "acc": (tp + tn) / n, "P": P, "R": R,
            "f1": 2 * P * R / (P + R) if P + R else 0.0, "fp": fp, "fn": fn}


def line(name: str, m: dict) -> str:
    return (f"  {name:<26} acc {m['acc']:6.1%}   compound P {m['P']:5.1%} "
            f"R {m['R']:5.1%} F1 {m['f1']:5.1%}   "
            f"said-compound-but-atomic {m['fp']:>4}   "
            f"said-atomic-but-COMPOUND {m['fn']:>4}")


def predictions(rows, floor: "float | None" = None):
    """(rules, model, layer) boolean predictions for every row.

    One parse per row (the layer reads the rule parser's intent count), so
    all three predictors come out of the same pass.
    """
    from freezegun import freeze_time
    from assistant.engine import generate as _generate
    from assistant.engine.fastrule import Atomicity
    from assistant.intent.classifier import ROUTER

    atom = Atomicity()
    rp = _generate._get_rule_parser()
    ROUTER.load()
    fl = ROUTER.ATOMIC_MARGIN_FLOOR if floor is None else floor
    rules, model, layer = [], [], []
    # warm the parser outside the frozen clock
    rp.analyze("book gym tomorrow at 7am", current_view="month")
    with freeze_time(_CLOCK):
        for text, _y in rows:
            try:
                intents = rp.analyze(text, current_view="month").intents
            except Exception:
                intents = []
            rules.append(atom.rule_verdict(text, intents) is not None)
            lab, margin = ROUTER.atomicity.predict(text)
            model.append(lab == "compound" and margin >= fl)
            layer.append(atom.judge(text, intents) is not None)
    return rules, model, layer


def board(title: str, rows, floor: "float | None" = None) -> dict:
    ys = [y for _t, y in rows]
    rules, model, layer = predictions(rows, floor)
    n_c = sum(ys)
    print(f"\n{title}  (n={len(ys)}: {n_c} compound / {len(ys) - n_c} atomic)")
    out = {}
    for name, preds in (("rules only", rules), ("model only", model),
                        ("LAYER (shipped wiring)", layer)):
        out[name] = score(preds, ys)
        print(line(name, out[name]))
    return out


def sweep(rows, title: str) -> None:
    """Margin-floor sweep for the model tier — the floor is a decision
    threshold and must be justified, not assumed."""
    from assistant.intent.classifier import ROUTER
    ROUTER.load()
    ys = [y for _t, y in rows]
    scored = [ROUTER.atomicity.predict(t) for t, _ in rows]
    print(f"\n{title} — atomicity margin-floor sweep (model tier alone)")
    print("   floor    acc    P       R      F1    FP(cheap)  FN(EXPENSIVE)")
    for fl in (0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0):
        preds = [lab == "compound" and mg >= fl for lab, mg in scored]
        m = score(preds, ys)
        print(f"   {fl:<6.2f} {m['acc']:6.1%} {m['P']:6.1%} {m['R']:6.1%} "
              f"{m['f1']:6.1%}  {m['fp']:>8}  {m['fn']:>12}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=("train", "test"), default="test")
    ap.add_argument("--dataset", choices=("both", "B", "A"), default="both")
    ap.add_argument("--floor", type=float, default=None,
                    help="override the model tier's margin floor")
    ap.add_argument("--sweep", action="store_true")
    a = ap.parse_args()

    print(f"ATOMICITY BINARY BOARD — {a.split} halves"
          f"{'' if a.floor is None else f' (model floor {a.floor})'}")
    print("  FN = said atomic but COMPOUND = a half-executed two-ask command "
          "(expensive)\n  FP = said compound but atomic = one slow-path row "
          "(cheap)")
    if a.dataset in ("both", "B"):
        rows = b_rows(a.split)
        if a.sweep:
            sweep(rows, f"B (FastRule 7,200 {a.split})")
        board(f"B — FastRule 7,200, {a.split} half (generated, family-split)",
              rows, a.floor)
    if a.dataset in ("both", "A"):
        rows = a_rows(a.split)
        if a.sweep:
            sweep(rows, f"A (verification pool {a.split})")
        board(f"A — verification pool minus sealed 300, {a.split} half (REAL wordings)",
              rows, a.floor)
    if a.split == "test":
        print("\n(test halves: aggregates only — leakage guard)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
