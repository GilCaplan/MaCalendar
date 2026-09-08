"""Prompt experiments for LLMSeg, scored against the ONE thing that matters.

The gate study (`gate_sizing.py`) found the ceiling, not a routing problem: on
159 cached rows LLMSeg fixes 6 and breaks 16, so even an oracle gate is worth
+3.8%. Routing cannot rescue that. The prompt has to make the model produce
more correct answers before where-to-call-it is an interesting question.

THE HYPOTHESIS UNDER TEST
-------------------------
FastSeg is excellent at COPYING (0 invention violations, 96.2% item precision)
and weaker at CUTTING (88.7% item-count). An 8B is the other way round —
DialogUSR measured a 28-point gap between a model's cut and copy accuracy on
exactly this task shape. The current V3 prompt asks the model to do BOTH, so
its copying mistakes (dropping "remind" in 12 of 37 rejections) throw away its
cutting wins.

    P1  v3-full      re-emit the whole decomposition        (today's prompt)
    P2  boundaries   return ONLY where to cut; FastSeg copies
    P3  count        return ONLY how many items there are
    P4  v3-surgical  v3 + "the proposal is usually right"

P2 and P3 never let the model touch the words at all, so no-loss and
no-invention violations are impossible by construction; FastSeg re-derives
action/time/tag from the model's boundaries. If the hypothesis is right, P2
keeps the 6 fixes and loses far fewer than 16.

    python -m assistant.engine.segmentation.experiments.prompt_lab --variants boundaries count
    python -m assistant.engine.segmentation.experiments.prompt_lab --limit 40      # a quick look

ONE llama job at a time. Answers are cached per (variant, text) so a killed
run is never wasted.
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import re
import sys
import time

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_S = "/tmp/seg_prompt_lab"
os.makedirs(_S, exist_ok=True)
for k, v in dict(MACALENDAR_DB=f"{_S}/c.db", MACALENDAR_MEMORY_DB=f"{_S}/m.db",
                 MACALENDAR_VOCAB=f"{_S}/v.json", MACALENDAR_CATEGORIES=f"{_S}/g.json",
                 MACALENDAR_TRACE_BUS=f"{_S}/t.jsonl",
                 MACALENDAR_NO_WARMUP="1").items():
    os.environ.setdefault(k, v)

from assistant.engine.segmentation.llmseg import llmseg
from assistant.engine.segmentation.experiments import score as sc              # noqa: E402
from assistant.engine.segmentation.fastseg.fastseg import (fastseg, assign_times,  # noqa: E402
                                    tag as fs_tag, _tidy)
from assistant.engine.segmentation.experiments.run_board import (assign_splits,          # noqa: E402
                                      stratified_sample)

_CACHE = os.path.join(_HERE, "experiments", "runs", "prompt_lab_cache.jsonl")


def _cache_load() -> dict:
    out = {}
    try:
        with open(_CACHE, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                out[(rec["variant"], rec["text"])] = rec["raw"]
    except OSError:
        pass
    return out


def _cache_put(variant: str, text: str, raw: str) -> None:
    with open(_CACHE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"variant": variant, "text": text, "raw": raw}) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


# ---------------------------------------------------------------------------
# P2 / P3 — the model only says WHERE to cut. FastSeg does every other job.
# ---------------------------------------------------------------------------

_BOUNDARY_PROMPT = """Split this command into the separate things the speaker asked for.

COMMAND: {text}

An "ask" is ONE independent thing to do. Split ONLY between separate asks.
Do NOT split:
  - two people joined by "and"   ("meeting with Sam and Alex" = ONE)
  - two verbs sharing one object ("wash and fold the laundry" = ONE)
  - two things bought together   ("buy milk and eggs" = ONE)
  - a time range                 ("from 3 to 4pm" = ONE)
Do split:
  - separate activities, even without a verb
    ("gym at 7 and dinner at 9" = TWO)

Copy each piece EXACTLY as it appears in the command, changing nothing and
leaving out nothing except the joining word. Output a JSON list of the pieces
and nothing else.

Example: "gym at 7 and dinner at 9"
["gym at 7", "dinner at 9"]"""

_COUNT_PROMPT = """How many separate things does this command ask for?

COMMAND: {text}

Two people joined by "and" is ONE thing. Two verbs sharing one object is ONE
thing. Two items bought together is ONE thing. A time range is ONE thing.
Two separate activities are TWO things, even if the second has no verb.

Output only a single digit and nothing else."""

_SURGICAL_EXTRA = """
IMPORTANT: the proposal above is usually CORRECT. Change it only where you are
certain it is wrong. Never delete a word the speaker said - "remind me to buy
milk" keeps "remind me to". If you are unsure, output the proposal unchanged."""


def build(variant: str, text: str, proposal):
    if variant == "v4-full":
        return llmseg.build_prompt(text, proposal)
    if variant == "boundaries":
        return _BOUNDARY_PROMPT.format(text=text)
    if variant == "count":
        return _COUNT_PROMPT.format(text=text)
    base = llmseg.build_prompt(text, proposal)
    if variant == "v4-surgical":
        return base.replace("Output the CORRECT decomposition",
                            _SURGICAL_EXTRA + "\n\nOutput the CORRECT decomposition")
    return base


def _items_from_pieces(text: str, pieces: "list[str]"):
    """FastSeg's own phases 2 and 3 over someone else's cut."""
    pieces = [p for p in (q.strip() for q in pieces) if p]
    if not pieces:
        return None
    out = []
    for action, time_str in assign_times(text, pieces):
        action = _tidy(action)
        if not action:
            continue
        out.append({"action": action, "time": time_str,
                    "tag": fs_tag(action, time_str)})
    return out or None


def interpret(variant: str, raw: str, text: str, proposal):
    """Model reply -> items, per variant."""
    if variant == "count":
        m = re.search(r"\d+", raw or "")
        if not m:
            return None
        want = max(1, min(6, int(m.group())))
        if want == len(proposal):
            return proposal
        # The model only supplied a COUNT, so the only honest use of it is as
        # a stopping condition on FastSeg's own splitter. It cannot invent a
        # boundary FastSeg could not find; it can decline one it did.
        if want < len(proposal):
            merged = _items_from_pieces(text, [text])
            return merged
        return proposal
    if variant == "boundaries":
        try:
            blob = json.loads(raw[raw.index("["):raw.rindex("]") + 1])
        except Exception:
            return None
        if not isinstance(blob, list) or not blob:
            return None
        return _items_from_pieces(text, [str(x) for x in blob])
    return llmseg.parse_items(raw, proposal)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", nargs="+",
                    default=["boundaries", "count", "v4-full", "v4-surgical"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sample", type=int, default=300,
                    help="trap-stratified sample size from the TRAIN pool")
    a = ap.parse_args()

    pool = [r for r in assign_splits(
        sc.load_rows(sorted(glob.glob(f"{_HERE}/datasets/*.jsonl"))))
        if r["split"] == "train"]
    # TRAP-STRATIFIED, not proportional. The first prompt slice was
    # proportional and left 13 of 44 traps EMPTY — including serial-verb,
    # two-times-one-activity and name-coordination, which are exactly the
    # shapes most likely to REFUTE a boundaries-only prompt. Measuring a
    # hypothesis on a set that excludes its failure mode is not a measurement.
    rows = stratified_sample(pool, a.sample)
    if a.limit:
        rows = rows[:a.limit]

    def exact(gold, pred):
        return (sc._bag([sc.as_item(g) for g in gold])
                == sc._bag([sc.as_item(p) for p in pred]))

    def counts_ok(gold, pred):
        return len(gold) == len(pred)

    n = len(rows)
    traps = collections.Counter(t for r in rows for t in (r.get("traps") or ["(none)"]))
    pool_traps = collections.Counter(
        t for r in pool for t in (r.get("traps") or ["(none)"]))
    hw = sum(1 for r in rows if r.get("source", "handwritten") == "handwritten")
    fs_ok = {r["text"]: exact(r["gold"], fastseg(r["text"])) for r in rows}
    fs_cut = {r["text"]: counts_ok(r["gold"], fastseg(r["text"])) for r in rows}
    print(f"rows: {n} of {len(pool)} TRAIN   traps {len(traps)}/{len(pool_traps)}"
          f"   hand-written {hw} ({hw / n:.0%})"
          f"   95% CI +/-{1.96 * (0.45 * 0.55 / n) ** 0.5:.1%}")
    print(f"  FastSeg alone   exact-row {sum(fs_ok.values()) / n:6.1%}"
          f"   item-count {sum(fs_cut.values()) / n:6.1%}\n")

    # v3's answers from the segment board are keyed by text and reused, so
    # rerunning it here costs only the rows that slice never covered.
    cache = _cache_load()
    for variant in a.variants:
        ok = fixes = breaks = unusable = skipped = cut_ok = 0
        scored = 0
        secs = 0.0
        for i, r in enumerate(rows, 1):
            text = r["text"]
            raw = cache.get((variant, text))
            if raw is None:
                t0 = time.perf_counter()
                # A timeout is a hiccup, not a verdict. Retrying once and
                # then SKIPPING the row keeps the run going; the old code
                # `break`-ed and still divided by the full n, which reported
                # boundaries at 1.4% after completing 68 of 294 rows — a
                # number that looks like a catastrophic result and is really
                # an unfinished loop.
                raw = None
                for attempt in (1, 2):
                    try:
                        raw = llmseg.call_model(
                            build(variant, text, fastseg(text)), timeout=240)
                        break
                    except Exception as exc:
                        err = type(exc).__name__
                        if attempt == 2:
                            print(f"    {variant}: {err} on row {i}, skipping",
                                  flush=True)
                if raw is None:
                    skipped += 1
                    continue
                secs += time.perf_counter() - t0
                _cache_put(variant, text, raw)
                cache[(variant, text)] = raw
            items = interpret(variant, raw, text, fastseg(text))
            if items is None:
                unusable += 1
                items = fastseg(text)          # unusable reply -> keep FastSeg
            # The accept guard still applies: a variant may not overwrite a
            # proposal with something that loses or invents words.
            final, _why = llmseg.accept(text, fastseg(text), items)
            good = exact(r["gold"], final)
            scored += 1
            ok += good
            cut_ok += counts_ok(r["gold"], final)
            if good and not fs_ok[text]:
                fixes += 1
            elif fs_ok[text] and not good:
                breaks += 1
            if i % 25 == 0:
                print(f"    …{variant} {i}/{n}", flush=True)
        # Rate over rows actually SCORED, never over the intended n.
        denom = max(1, scored)
        note = "" if scored == n else f"  [INCOMPLETE {scored}/{n}]"
        print(f"  {variant:<14}  exact-row {ok / denom:6.1%}"
              f"   item-count {cut_ok / denom:6.1%}"
              f"   fixes {fixes} / breaks {breaks}"
              f"   unusable {unusable}  skipped {skipped}"
              f"   {secs / denom:.1f}s/row{note}", flush=True)


if __name__ == "__main__":
    main()
