"""Sandbox the FAST track alone — the rule parser (with its gates) scored as
a selective classifier, no deep track, no LLM, no execution.

    python -m scripts.fast_sandbox --max-rank 250      # seconds, not minutes
    python -m scripts.fast_sandbox --max-rank 600

Rows replay frozen at their recorded timestamps (same epoch conventions as
the main harness). Per row, generate.fast_propose() runs exactly as in
production — gates included — and the PROPOSED intents are scored against
the dataset's count expectations directly (create_event/create_todo intent
counts; nothing is executed, no db is touched).

The fast system's job is to ABSTAIN when unsure, so the numbers that matter
are commit rate and correctness-on-committed — an abstain is the deep
track's work, not a failure. The Goodhart rules (ITERATION_PROTOCOL.md,
fast-sandbox lane): tweaks batch under ONE registered prediction; every
batch gates on dev-full; nothing counts on the main board until a full
joint run confirms (a better parser shifts which rows reach deep).
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import os
import pathlib
import sqlite3
import sys
import tempfile

# Lane scripts run BESIDE live engine measurements by design (Gil: FastRule
# iteration never waits on the deep track). The BLAS single-thread pin is the
# guard that makes two model-loading processes safe together — structural
# here, not left to the caller.
for _blas in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_blas, "1")
from collections import Counter

# --- isolate BEFORE importing assistant (paths read at import time) --------
_TMP = tempfile.mkdtemp(prefix="fast_sandbox_")
for _v, _n in (("DB", "calendar.db"), ("MEMORY_DB", "mem.db"),
               ("VOCAB", "vocab.json"), ("CATEGORIES", "categories.json"),
               ("TRACE_BUS", "trace_bus.jsonl"), ("LOCATION", "location.json")):
    os.environ[f"MACALENDAR_{_v}"] = os.path.join(_TMP, _n)
os.environ["MACALENDAR_NO_WARMUP"] = "1"
os.environ["MACALENDAR_OBSERVANCE"] = "0"

ROOT = pathlib.Path(__file__).resolve().parents[1]
_S = "DOCUMENTATION/experiments/memory_scaling/output/dummy_3000.db"
SOURCE = ROOT / _S if (ROOT / _S).exists() else \
    pathlib.Path("/Users/USER/Desktop/Personal_Projects/MACalendar") / _S


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-rank", type=int, default=250)
    ap.add_argument("--min-rank", type=int, default=0)
    a = ap.parse_args()

    from freezegun import freeze_time

    from assistant.config import load_config
    from assistant.intent.rule_parser import RULE_THRESHOLD
    from assistant.engine.generate import generate
    from assistant.engine.state import EngineState
    from scripts.score_dataset_run import load_overrides, load_provenance

    cfg = load_config()
    prov = load_provenance()
    overrides = load_overrides()

    rp = generate._get_rule_parser()
    # Warm the recognizer's lazy first-analyze OUTSIDE any frozen clock —
    # the metaclass lesson from the main harness (epoch reset).

    if rp is not None:
        with contextlib.suppress(Exception):
            rp.analyze("book gym tomorrow at 7am", current_view="month")

    where = "tier_rank IS NOT NULL"
    if a.min_rank:
        where += f" AND tier_rank >= {int(a.min_rank)}"
    if a.max_rank:
        where += f" AND tier_rank <= {int(a.max_rank)}"
    with sqlite3.connect(f"file:{SOURCE}?mode=ro", uri=True) as c:
        rows = c.execute(
            "SELECT COALESCE(NULLIF(raw_transcript,''), transcript), ts, tier_rank "
            f"FROM examples WHERE {where} ORDER BY tier_rank").fetchall()
    # SEALED test split excluded always (fast_sandbox mines dev rows; a
    # --test milestone for FastRule uses its own dataset's test half).
    from scripts.score_dataset_run import load_test_split
    _test = load_test_split()
    rows = [r for r in rows if r[0] not in _test]

    n = len(rows)
    committed = correct = 0
    recov = abst_scored = gate_recov = 0
    split = {"dev": [0, 0, 0], "held-out": [0, 0, 0]}   # committed, raw-ok, adj-ok
    by_kind: Counter = Counter()
    adj_correct = [0]
    by_kind_ok: Counter = Counter()
    misses: list[tuple[str, str]] = []

    for text, ts, rank in rows:
        p = prov.get(text) or {}
        ctx = freeze_time(_dt.datetime.fromtimestamp(ts), tick=True) if ts \
            else contextlib.nullcontext()
        with ctx:
            st = EngineState(raw_text=text, text=text)
            ok_commit = False
            with contextlib.suppress(Exception):
                ok_commit = generate.fast_propose(st, cfg)
        if not ok_commit:
            # RECOVERABLE-ABSTAIN: would FastRule's raw parse have been right?
            # (the selective classifier's second error type — headroom +
            # wasted deep-track latency; dev+held-out counted, dev-only mined)
            try:
                rr = rp.analyze(text, current_view="month")
            except Exception:
                rr = None
            if rr and rr.intents:
                gate_ok = rr.confidence >= RULE_THRESHOLD and not rr.missing_slots
                ev = sum(1 for n, _ in rr.intents if n == "create_event")
                td = sum(1 for n, _ in rr.intents if n == "create_todo")
                pp = prov.get(text) or {}
                ii = pp.get("intent", ""); kk = pp.get("intent") if pp.get("scenario") == "compound" else None
                ex2 = {"event+event": (2, 0), "task+task": (0, 2), "event+task": (1, 1)}
                if kk in ex2: rok = ev >= ex2[kk][0] and td >= ex2[kk][1]
                elif ii in ("set", "createoradd"): rok = (ev + td) >= 1
                elif ii in ("query", "remove"): rok = (ev + td) == 0
                else: rok = None
                if rok is not None:
                    abst_scored += 1
                    if rok:
                        recov += 1
                        if gate_ok:
                            gate_recov += 1     # a GATE blocked a correct parse
                            if (rank or 0) <= 600:
                                misses.append(("GATE-OVERBLOCK", text[:70]))
            continue
        committed += 1
        n_ev = sum(1 for it in st.items if it.action == "create_event")
        n_td = sum(1 for it in st.items
                   if it.action == "create_todo")
        intent = p.get("intent", "")
        kind = p.get("intent") if p.get("scenario") == "compound" else intent
        exp = {"event+event": (2, 0), "task+task": (0, 2), "event+task": (1, 1)}
        if kind in exp:
            ok = n_ev >= exp[kind][0] and n_td >= exp[kind][1]
        elif intent in ("set", "createoradd"):
            ok = (n_ev + n_td) >= 1
        elif intent in ("query", "remove"):
            ok = (n_ev + n_td) == 0
        else:
            committed -= 1        # unknown provenance — not scored
            continue
        # adjusted verdict: the conventions-overrides layer, intent-count based
        ov = (overrides.get(text) or {}).get("treatment")
        total = n_ev + n_td
        if ov == "noop_ok":
            adj = total == 0 or total >= 1
        elif ov == "half_flexible":
            adj = total >= 1
        elif ov == "split_flexible":
            adj = total >= 2
        else:
            adj = ok
        seg = "dev" if (rank or 0) <= 600 else "held-out"
        split[seg][0] += 1
        split[seg][1] += 1 if ok else 0
        split[seg][2] += 1 if adj else 0
        by_kind[kind or intent] += 1
        if ok:
            correct += 1
            by_kind_ok[kind or intent] += 1
        if adj:
            adj_correct[0] += 1
        elif (rank or 0) <= 600:
            # HELD-OUT DISCIPLINE: rows past rank 600 are measured, never
            # mined - their failing transcripts are never printed.
            misses.append((kind or intent, text[:70]))

    print(f"rows {n} · committed {committed} ({committed/n:.0%}) · "
          f"correct-on-committed {correct}/{committed} "
          f"({(correct/committed) if committed else 0:.1%}) · "
          f"ADJUSTED {adj_correct[0]}/{committed} "
          f"({(adj_correct[0]/committed) if committed else 0:.1%})")
    for seg, (c_, r_, a_) in split.items():
        if c_:
            print(f"  {seg:<9} committed {c_:>4} · raw {r_/c_:.1%} · adjusted {a_/c_:.1%}")
    if abst_scored:
        print(f"  RECOVERABLE-ABSTAIN {recov}/{abst_scored} ({recov/abst_scored:.1%}) "
              f"— abstained rows the raw parse would nail (of which {gate_recov} "
              f"blocked by a GATE = over-abstention headroom)")
    print("misses below are ADJUSTED misses + GATE-OVERBLOCKs from DEV ONLY (held-out never mined)")
    for k in sorted(by_kind):
        print(f"  {k:<14} {by_kind_ok[k]:>3}/{by_kind[k]:<3} "
              f"({by_kind_ok[k]/by_kind[k]:.0%})")
    print("\nmisses (committed but wrong):")
    for k, t in misses[:15]:
        print(f"  [{k}] {t}")
    if len(misses) > 15:
        print(f"  … +{len(misses) - 15} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
