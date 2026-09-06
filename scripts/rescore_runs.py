"""Rescore every archived run under the CURRENT scorer.

The archive (dataset/runs/, written by scripts/archive_run.py) exists so
that a metric added or fixed later can be recomputed over the whole history
instead of staying blank or — worse — wrong. This tool does that:

    python -m scripts.rescore_runs           # print the table
    python -m scripts.rescore_runs --write   # also backfill loop_log.csv

Prints, per archive: rows, raw count-correct, product-adjusted
count-correct, query-mutation violations, and — for archives mapped to a
loop_log run — the drift between the logged overall_pct and today's
recomputation (nonzero drift means the scorer changed since that run was
logged; the log keeps the historical value, the drift column tells you it
is stale). --write fills loop_log's BACKFILLABLE columns (currently
adj_pct) for mapped runs; it never rewrites overall_pct or any other
as-logged value.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import pathlib
import shutil
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNS = ROOT / "dataset" / "runs"
LOG = ROOT / "dataset" / "loop_log.csv"


def rescore_all() -> list[dict]:
    from scripts.score_dataset_run import load_provenance, score_db
    prov = load_provenance()
    out = []
    for mf in sorted(RUNS.glob("*/manifest.json")):
        man = json.loads(mf.read_text())
        gz = mf.parent / "engine_run.db.gz"
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            with gzip.open(gz, "rb") as fi:
                shutil.copyfileobj(fi, tmp)
            tmp.flush()
            agg = score_db(pathlib.Path(tmp.name), prov)["aggregate"]["overall"]
        out.append({
            "name": mf.parent.name, "loop_run": man.get("loop_run"),
            "n": man["n_rows"],
            "raw": agg.get("count_ok_rate"), "adj": agg.get("count_ok_adj_rate"),
            "qmut": agg.get("query_mutation_violations"),
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true",
                    help="backfill loop_log adj_pct for mapped runs")
    args = ap.parse_args()

    logged = {}
    if LOG.exists():
        rows = list(csv.DictReader(open(LOG)))
        logged = {int(r["run"]): r for r in rows if r.get("run")}

    results = rescore_all()
    print(f"{'archive':<34}{'n':>6}{'raw':>7}{'adj':>7}{'qmut':>6}  drift-vs-logged")
    for r in results:
        drift = ""
        lr = logged.get(r["loop_run"]) if r["loop_run"] else None
        if lr and lr.get("overall_pct") and r["raw"] is not None:
            d = r["raw"] * 100 - float(lr["overall_pct"])
            drift = f"{d:+.1f}pt" if abs(d) >= 0.05 else "none"
        raw = f"{r['raw']:.1%}" if r["raw"] is not None else "–"
        adj = f"{r['adj']:.1%}" if r["adj"] is not None else "–"
        print(f"{r['name']:<34}{r['n']:>6}{raw:>7}{adj:>7}{r['qmut']:>6}  {drift}")

    if args.write and logged:
        for r in results:
            lr = logged.get(r["loop_run"]) if r["loop_run"] else None
            if lr is not None and r["adj"] is not None:
                lr["adj_pct"] = f"{r['adj'] * 100:.1f}"
        with open(LOG, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
        print(f"\nwrote adj_pct for {sum(1 for r in results if r['loop_run'])} runs -> {LOG}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
