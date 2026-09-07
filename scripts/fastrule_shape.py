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
            if ok:
                A_OK += 1
            else:
                A_WRONG += 1
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
