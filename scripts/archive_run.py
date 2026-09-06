"""Archive a measurement run's scratch files so metrics stay recomputable.

Every metric we report is computed FROM a run's scratch files — losing them
means a metric added or fixed later can never be backfilled, and an
unlabeled surviving scratch is worse: on 2026-09-06 an all-deep A/B analysis
was silently computed against the WRONG scratch db (a mixed cycle-1 run with
a similar row count), publishing a 0/21 deep-rescue figure whose true value
was 7/21. Identity must be recorded at archive time, never inferred later.

    python -m scripts.archive_run <scratch_dir> --run 9 --label epoch-baseline
    python -m scripts.archive_run <scratch_dir> --label full3000-sweep

Copies engine_run.db, calendar.db and trace_bus.jsonl (gzipped; the data files are gitignored per Gil's call — local-only,
while each manifest.json is committed as the durable identity record)
into dataset/runs/<name>/ with a manifest.json recording provenance:
row count, parse-path fingerprint, source path, mtimes, md5s, and the
loop_log run number when given. scripts/rescore_runs.py replays the CURRENT
scorer over every archive and can refresh loop_log's metric columns.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import pathlib
import shutil
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNS = ROOT / "dataset" / "runs"
FILES = ("engine_run.db", "calendar.db", "trace_bus.jsonl")


def archive(scratch: pathlib.Path, run: "int | None", label: str) -> pathlib.Path:
    db = scratch / "engine_run.db"
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as c:
        n = c.execute("SELECT COUNT(*) FROM examples").fetchone()[0]
        paths = Counter(p for (p,) in c.execute("SELECT parse_path FROM examples"))
        ts_min, ts_max = c.execute("SELECT MIN(ts), MAX(ts) FROM examples").fetchone()
    name = (f"run{run:02d}_{label}" if run is not None else f"x_{label}")
    dest = RUNS / name
    dest.mkdir(parents=True, exist_ok=True)
    files = {}
    for fn in FILES:
        src = scratch / fn
        if not src.exists():
            continue
        out = dest / (fn + ".gz")
        with open(src, "rb") as fi, gzip.open(out, "wb", compresslevel=9) as fo:
            shutil.copyfileobj(fi, fo)
        files[fn] = {"md5": hashlib.md5(src.read_bytes()).hexdigest(),
                     "bytes": src.stat().st_size}
    manifest = {
        "loop_run": run, "label": label,
        "source": str(scratch),
        "source_mtime": datetime.fromtimestamp(db.stat().st_mtime).isoformat(timespec="seconds"),
        "archived_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_rows": n, "parse_paths": dict(paths),
        "row_ts_range": [ts_min, ts_max],
        "files": files,
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    return dest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("scratch", type=pathlib.Path)
    ap.add_argument("--run", type=int, default=None,
                    help="loop_log run number this scratch belongs to")
    ap.add_argument("--label", required=True)
    a = ap.parse_args()
    dest = archive(a.scratch, a.run, a.label)
    print(f"archived -> {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
