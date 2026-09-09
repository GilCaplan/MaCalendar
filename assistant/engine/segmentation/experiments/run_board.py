"""Run a segment implementation over the corpus and print its six boards.

    python -m assistant.engine.segmentation.experiments.run_board --predictor fastseg          # no model
    python -m assistant.engine.segmentation.experiments.run_board --predictor segment          # + LLMSeg

Two rules this runner enforces so the numbers stay honest:

SPLIT BY FAMILY. The generated rows come six-per-template, so putting rows
rather than families on either side of the boundary would leave near-identical
sentences in both halves — the test score would then be measuring memorisation
of a template, which is the one thing a held-out half exists to prevent. The
hand-written rows keep the split their author gave them.

TRAIN DETAIL, TEST AGGREGATES. `--test` prints the headline lines only and
never the failing rows, per the project rule that direction comes from the
training pool alone. A run that could show you which held-out rows to fix is a
run that lets you fit the test set.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from assistant.engine.segmentation.experiments import score as scorer               # noqa: E402

#: Fraction of families held out. Matches the hand-written files' own ~40%,
#: which were split before this runner existed.
_TEST_FRACTION = 0.40


def assign_splits(rows: "list[dict]") -> "list[dict]":
    """Stamp a split on any row that lacks one, keeping a family together."""
    for row in rows:
        if row.get("split"):
            continue
        key = row.get("family") or row.get("id", "")
        digest = hashlib.sha1(key.encode()).hexdigest()
        bucket = int(digest[:8], 16) / 0xFFFFFFFF
        row["split"] = "test" if bucket < _TEST_FRACTION else "train"
    return rows


#: Every trap must reach at least this many rows before the sample is spent on
#: matching the pool's proportions. A slice that is proportional but leaves 13
#: of 44 traps EMPTY cannot test a hypothesis about the shapes in them — the
#: 159-row prompt slice had exactly that hole, and the missing traps
#: (serial-verb, two-times-one-activity, name-coordination) were the ones most
#: likely to REFUTE the boundaries prompt. Proportional sampling is the right
#: default for a headline number and the wrong one for an experiment.
MIN_PER_TRAP = 6


def stratified_sample(rows: "list[dict]", size: int,
                      by_trap: bool = True, seed: int = 20260908) -> "list[dict]":
    """A slice that keeps board F's shape AND covers every trap.

    Two passes. The first fills each trap up to `MIN_PER_TRAP` so no shape is
    absent; the second spends what is left proportionally over (ask-count,
    provenance) so the headline still resembles the pool.
    """
    import collections
    import random

    rng = random.Random(seed)
    picked: "dict[str, dict]" = {}

    def key(r):
        return r.get("id") or r["text"]

    if by_trap:
        by: dict = collections.defaultdict(list)
        for r in rows:
            for t in (r.get("traps") or ["(none)"]):
                by[t].append(r)
        for trap in sorted(by):
            pool = sorted(by[trap], key=key)
            for r in rng.sample(pool, min(MIN_PER_TRAP, len(pool))):
                picked[key(r)] = r

    buckets: dict = collections.defaultdict(list)
    for r in rows:
        buckets[(len(r["gold"]), r.get("source", "handwritten"))].append(r)
    remaining = max(0, size - len(picked))
    for bk in sorted(buckets, key=lambda k: (k[0], str(k[1]))):
        pool = [r for r in sorted(buckets[bk], key=key) if key(r) not in picked]
        take = min(len(pool), round(remaining * len(buckets[bk]) / len(rows)))
        for r in rng.sample(pool, take) if take else []:
            picked[key(r)] = r
    return sorted(picked.values(), key=key)


_CACHE = os.path.join(_HERE, "experiments", "runs", "llmseg_cache.jsonl")


def _load_cache() -> dict:
    """Every model answer we have ever recorded, keyed by command text."""
    out: dict = {}
    try:
        with open(_CACHE, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue            # a half-written last line after a kill
                out[rec["text"]] = rec["result"]
    except OSError:
        pass
    return out


def _append_cache(text: str, result: dict) -> None:
    os.makedirs(os.path.dirname(_CACHE), exist_ok=True)
    with open(_CACHE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"text": text, "result": result}) + "\n")
        fh.flush()
        os.fsync(fh.fileno())           # survive a SIGKILL, not just an exit


def build_predictor(name: str):
    """A predictor is `text -> list[item]`, plus the call count for board E."""
    # Latency is timed HERE, not in the scorer: `time` is outside score.py's
    # import allowlist, so the predictor reports `seconds` and board E
    # aggregates it into a per-row average.
    if name == "fastseg":
        from assistant.engine.segmentation.fastseg.fastseg import fastseg

        def predict(text):
            t0 = time.perf_counter()
            items = fastseg(text)
            return {"items": items, "calls": 0,
                    "seconds": time.perf_counter() - t0, "tier": "fastseg"}
        return predict, "FastSeg alone (deterministic, no model)"
    if name == "segment":
        from assistant.engine.segmentation.llmseg.llmseg import segment

        # A model pass costs ~19s a row, so a 150-row board is 45 minutes and a
        # killed run used to lose all of it. Every answer is cached on disk by
        # command text: a re-run replays instantly, a partial run is not wasted,
        # and the cache doubles as the record of what the model actually said.
        cache = _load_cache()

        def predict(text):
            hit = cache.get(text)
            if hit is not None:
                return dict(hit, cached=True)
            t0 = time.perf_counter()
            # use_model=True EXPLICITLY: LLMSeg is off by default, and a
            # board that inherited the default would quietly report FastSeg's
            # numbers under LLMSeg's name.
            out = segment(text, use_model=True)
            rec = {"items": out["items"], "calls": 1,
                   "seconds": time.perf_counter() - t0,
                   "tier": out["route"], "route": out["route"]}
            _append_cache(text, rec)
            cache[text] = rec
            return rec
        return predict, "Segment = FastSeg -> LLMSeg -> accept"
    raise SystemExit(f"unknown predictor {name!r}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--predictor", default="fastseg", choices=("fastseg", "segment"))
    ap.add_argument("--test", action="store_true",
                    help="score the HELD-OUT half (aggregates only)")
    ap.add_argument("--limit", type=int, default=0, help="0 = no cap")
    ap.add_argument("--sample", type=int, default=0,
                    help="deterministic sample: every trap to MIN_PER_TRAP "
                         "first, then proportional by ask-count/provenance")
    ap.add_argument("--by-count", action="store_true",
                    help="proportional only, no per-trap floor (the old "
                         "behaviour; leaves rare traps unrepresented)")
    ap.add_argument("--source", choices=("handwritten", "generated"),
                    help="score only one provenance")
    ap.add_argument("--samples", type=int, default=12)
    a = ap.parse_args()

    rows = assign_splits(scorer.load_rows(sorted(glob.glob(f"{_HERE}/datasets/*.jsonl"))))
    want = "test" if a.test else "train"
    rows = [r for r in rows if r["split"] == want]
    if a.source:
        rows = [r for r in rows if r.get("source", "handwritten") == a.source]
    if a.sample:
        rows = stratified_sample(rows, a.sample, by_trap=not a.by_count)
    if a.limit:
        rows = rows[:a.limit]

    predict, label = build_predictor(a.predictor)
    print(f"\n{'='*74}\n{label}\n"
          f"corpus: {len(rows)} rows · {want.upper()} half"
          + (f" · {a.source} only" if a.source else "") + f"\n{'='*74}")
    if a.test:
        print("HELD-OUT: aggregates only, no row detail, no hypotheses.\n")

    started = time.time()
    result = scorer.score_rows(rows, predict, samples=0 if a.test else a.samples)
    result["wall_seconds"] = round(time.time() - started, 1)

    board = scorer.format_board(result)
    if a.test:
        # BELT AND BRACES. `samples=0` above is the real guard — no failing row
        # is ever collected — but if that ever regresses, the appendix must not
        # reach a held-out report. Truncating at the appendix's own header is
        # exact; the previous version filtered by line PREFIX and matched none
        # of the lines it was meant to remove, so it looked like a guard while
        # doing nothing.
        marker = "--- reading the failures"
        if marker in board:
            board = board[:board.index(marker)].rstrip()
    print(board)
    print(f"\nwall clock: {result['wall_seconds']}s")


if __name__ == "__main__":
    main()
