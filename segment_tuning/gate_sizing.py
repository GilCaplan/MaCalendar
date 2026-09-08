"""WHERE should LLMSeg run? A selective-classifier study over the run cache.

The 150-row board said LLMSeg is net-negative overall (exact-row 47.2% ->
40.9%) and that all of the loss sits in the rows where ACCEPT took the model's
answer. That is an average over a population, and an average is the wrong
object: the question is whether some identifiable SUBSET is helped enough to
pay for the rest being left alone.

So this scores a GATE, not a model. For every candidate rule "call LLMSeg only
when <feature>", it reports what the component would have scored under that
policy and what it would have cost. The winning gate is the one that beats
FastSeg-alone on exact-row while calling the model on as few rows as possible.

TWO RULES THIS FILE OBEYS, because both are easy to violate by accident:

  1. EVERY FEATURE IS COMPUTABLE AT RUNTIME. No gold, no trap labels, no
     "rows where FastSeg was wrong". A gate that needs the answer to decide
     whether to ask the question is not a gate. Trap labels ARE reported, but
     only in a clearly-marked diagnostic section that no policy may use.
  2. NO NEW MODEL CALLS. Everything replays from `runs/llmseg_cache.jsonl`,
     so this is free and repeatable, and the same cache can be re-mined as
     new gates are proposed.

    python -m segment_tuning.gate_sizing
"""
from __future__ import annotations

import collections
import glob
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_S = "/tmp/seg_gate"
os.makedirs(_S, exist_ok=True)
for k, v in dict(MACALENDAR_DB=f"{_S}/c.db", MACALENDAR_MEMORY_DB=f"{_S}/m.db",
                 MACALENDAR_VOCAB=f"{_S}/v.json", MACALENDAR_CATEGORIES=f"{_S}/g.json",
                 MACALENDAR_TRACE_BUS=f"{_S}/t.jsonl",
                 MACALENDAR_NO_WARMUP="1").items():
    os.environ.setdefault(k, v)

from segment_tuning import score as sc                      # noqa: E402
from segment_tuning.fastseg import fastseg, find_time_refs, cut   # noqa: E402
from segment_tuning.run_board import assign_splits, _load_cache   # noqa: E402


# ---------------------------------------------------------------------------
# Runtime-computable features. Each is cheap (regex / the cut we already ran).
# ---------------------------------------------------------------------------

_JOINER_WORD = re.compile(r"\b(and then|and also|as well as|and|then|also|plus)\b", re.I)
_LIST_MARK = re.compile(r"\b(remind me to|i need to|on my list|to my list|to-?do)\b", re.I)
_CAL_MARK = re.compile(r"\b(to my calendar|on my calendar|schedule|book)\b", re.I)
_QUESTION = re.compile(r"^\s*(what|when|where|how|do i|does|is there|am i)\b", re.I)
_WRAPPER = re.compile(r"\b(can you|could you|would you|please|hey|i was thinking|maybe|should i)\b", re.I)


def features(text: str) -> dict:
    pieces = cut(text)
    refs = find_time_refs(text)
    toks = text.split()
    return {
        "pieces": len(pieces),
        "multi_piece": len(pieces) > 1,
        "n_times": len(refs),
        "no_time": len(refs) == 0,
        "many_times": len(refs) >= 2,
        "n_joiners": len(_JOINER_WORD.findall(text)),
        "has_joiner": bool(_JOINER_WORD.search(text)),
        "has_comma": "," in text,
        "long": len(toks) >= 12,
        "very_long": len(toks) >= 16,
        "list_marker": bool(_LIST_MARK.search(text)),
        "cal_marker": bool(_CAL_MARK.search(text)),
        "both_markers": bool(_LIST_MARK.search(text)) and bool(_CAL_MARK.search(text)),
        "question": bool(_QUESTION.search(text)),
        "wrapper": bool(_WRAPPER.search(text)),
        # The disagreement itself is runtime-computable: FastSeg cut into N
        # pieces but found more time references than pieces, which is the
        # shape it most often gets wrong.
        "times_exceed_pieces": len(refs) > len(pieces),
    }


def exact(gold, pred) -> bool:
    return (sc._bag([sc.as_item(g) for g in gold])
            == sc._bag([sc.as_item(p) for p in pred]))


def main() -> None:
    cache = _load_cache()
    rows = [r for r in assign_splits(
        sc.load_rows(sorted(glob.glob(f"{_HERE}/data/*.jsonl"))))
        if r["split"] == "train" and r["text"] in cache]
    if not rows:
        raise SystemExit("cache is empty — run the segment board first")

    data = []
    for r in rows:
        fs = fastseg(r["text"])
        sg = cache[r["text"]]["items"]
        data.append({"text": r["text"], "traps": r.get("traps") or [],
                     "fs_ok": exact(r["gold"], fs), "sg_ok": exact(r["gold"], sg),
                     "route": cache[r["text"]]["route"].split(":")[0],
                     "sec": cache[r["text"]].get("seconds") or 0.0,
                     "f": features(r["text"])})

    n = len(data)
    base = sum(d["fs_ok"] for d in data)
    allm = sum(d["sg_ok"] for d in data)
    print(f"cache: {n} rows (TRAIN half)\n")
    print(f"  FastSeg alone      exact-row {base / n:6.1%}   0.00 calls/row")
    print(f"  LLMSeg on ALL rows exact-row {allm / n:6.1%}   1.00 calls/row"
          f"   ({allm - base:+d} rows)\n")

    # ---- every single feature as a gate -----------------------------------
    print("GATE = call LLMSeg only when the feature is TRUE, else keep FastSeg")
    print(f"  {'feature':<22}{'fires':>6}{'exact-row':>11}{'vs base':>9}"
          f"{'calls/row':>11}   on the fired rows")
    print("  " + "-" * 84)
    keys = [k for k in data[0]["f"] if isinstance(data[0]["f"][k], bool)]
    scored = []
    for k in keys:
        fired = [d for d in data if d["f"][k]]
        if not fired or len(fired) == n:
            continue
        hits = sum(d["sg_ok"] if d["f"][k] else d["fs_ok"] for d in data)
        f_fs = sum(d["fs_ok"] for d in fired)
        f_sg = sum(d["sg_ok"] for d in fired)
        scored.append((hits, k, len(fired), f_fs, f_sg))
    for hits, k, nf, f_fs, f_sg in sorted(scored, reverse=True):
        print(f"  {k:<22}{nf:>6}{hits / n:>11.1%}{hits - base:>+9d}"
              f"{nf / n:>11.2f}   FastSeg {f_fs}/{nf} -> LLMSeg {f_sg}/{nf}")

    # ---- the inverse: gate on the feature being FALSE ----------------------
    print("\nGATE = call LLMSeg only when the feature is FALSE")
    inv = []
    for k in keys:
        fired = [d for d in data if not d["f"][k]]
        if not fired or len(fired) == n:
            continue
        hits = sum(d["sg_ok"] if not d["f"][k] else d["fs_ok"] for d in data)
        inv.append((hits, k, len(fired)))
    for hits, k, nf in sorted(inv, reverse=True)[:6]:
        print(f"  NOT {k:<18}{nf:>6}{hits / n:>11.1%}{hits - base:>+9d}"
              f"{nf / n:>11.2f}")

    # ---- the ceiling: how good could ANY gate be? --------------------------
    helps = sum(1 for d in data if d["sg_ok"] and not d["fs_ok"])
    hurts = sum(1 for d in data if d["fs_ok"] and not d["sg_ok"])
    print(f"\nTHE CEILING — an ORACLE gate that calls LLMSeg only when it helps")
    print(f"  rows LLMSeg FIXES that FastSeg got wrong : {helps}")
    print(f"  rows LLMSeg BREAKS that FastSeg got right: {hurts}")
    print(f"  oracle exact-row {(base + helps) / n:.1%} at {helps / n:.2f} calls/row")
    print(f"  => even a PERFECT gate can only add {helps} rows ({helps / n:+.1%}). "
          f"That is the whole prize.")

    # ---- diagnostic only: which SHAPES does it fix? ------------------------
    print("\nDIAGNOSTIC ONLY — trap labels are gold-side, no gate may use them")
    fix = collections.Counter()
    brk = collections.Counter()
    for d in data:
        for t in (d["traps"] or ["(none)"]):
            if d["sg_ok"] and not d["fs_ok"]:
                fix[t] += 1
            elif d["fs_ok"] and not d["sg_ok"]:
                brk[t] += 1
    print(f"  {'trap':<32}{'fixed':>7}{'broken':>8}")
    for t in sorted(set(fix) | set(brk), key=lambda t: -(fix[t] - brk[t])):
        print(f"  {t:<32}{fix[t]:>7}{brk[t]:>8}")

    print("\nROWS LLMSeg FIXED (what it is actually good for)")
    for d in data:
        if d["sg_ok"] and not d["fs_ok"]:
            print(f"   [{d['route']}] {d['text'][:76]}")


if __name__ == "__main__":
    main()
