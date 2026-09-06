"""Deep-rescue analysis: of the rows the FAST path failed, would DEEP pass?

    python -m scripts.deep_rescue <mixed_run.db> <alldeep_run.db>

Joins a mixed fast/deep run against an all-deep companion run of the same
slice (same frozen-clock harness) by verbatim transcript. Reports the rescue
rate (fast failures the deep track passes) and the breakage rate (fast passes
deep would lose). First measured 2026-09-06 on the epoch baseline vs the
row-8 all-deep A/B: 0/21 rescued, 0/82 broken — cycle 3's compound gate had
already routed every deep-rescuable fast failure to the deep track, and the
fast path's remaining failures are convention/capability losses no track
fixes. Rerun whenever a fresh all-deep companion exists; if the rescue rate
ever rises above ~0 again, the fast/deep routing has a new harvestable gap.
"""
from __future__ import annotations

import pathlib
import sqlite3
import sys


def main() -> int:
    mixed_db, alldeep_db = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    from scripts.score_dataset_run import load_provenance, score_db
    root = pathlib.Path(__file__).resolve().parents[1]
    prov = load_provenance(root / "dataset" / "inputs" / "hwu64_sample.json")
    mixed = score_db(mixed_db, prov)
    deep = {r["transcript"]: r for r in score_db(alldeep_db, prov)["per_prompt"]}
    with sqlite3.connect(f"file:{mixed_db}?mode=ro", uri=True) as c:
        paths = dict(c.execute(
            "SELECT COALESCE(NULLIF(raw_transcript,''),transcript), parse_path "
            "FROM examples").fetchall())
    ff = fr = fp = pb = 0
    stuck = []
    for r in mixed["per_prompt"]:
        if r["count_ok"] is None or paths.get(r["transcript"]) != "fast":
            continue
        d = deep.get(r["transcript"])
        if d is None or d["count_ok"] is None:
            continue
        if r["count_ok"]:
            fp += 1
            pb += 0 if d["count_ok"] else 1
        else:
            ff += 1
            if d["count_ok"]:
                fr += 1
            else:
                stuck.append(r["transcript"][:70])
    print(f"fast rows: {fp + ff} (pass {fp} / fail {ff})")
    print(f"deep rescues {fr}/{ff} fast failures"
          + (f" ({fr / ff:.0%})" if ff else ""))
    print(f"deep breaks {pb}/{fp} fast passes")
    if stuck:
        print("track-independent failures (sample):")
        for s in stuck[:6]:
            print("  -", s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
