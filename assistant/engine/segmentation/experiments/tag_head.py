"""Is the logistic `kind` head a better TAG than the hand-built reader?

    python -m assistant.engine.segmentation.experiments.tag_head

Recorded as a candidate in ARCHITECTURE §2 Phase 3 and never measured, which is
worth nothing. This measures it, and the design answers the three ways the
comparison could lie:

**1 · The head has TWO classes; TAG has three.** `kind` is event/task and `review`
is absent. The review test is deterministic and deliberately SHARED with LLMSeg so
the two cannot disagree about what a review looks like — so every arm below keeps
the existing review pre-check and only the event-vs-task decision is contested.

**2 · Provenance overlaps.** The head was fitted on `fastrule_7200`'s train half,
and segmentation's generated rows are rendered from the same filler banks. Verbatim
overlap is small (43 of 1,051 texts, 4.1%) but the wording SKELETONS are shared, so
three slices are reported: all rows, rows whose text is not in the head's fitting
data, and the hand-written rows alone — which cannot be in FastRule at all and are
therefore the strictest read.

**3 · The baseline must be the one that SHIPS.** Not the engine reader alone
(84.7%) — the reader plus lexicon-over-`event`, which is what `tag()` does. Beating
the weaker number would be an artifact, and it is the artifact this file exists to
avoid.

TAG IS SCORED ON GOLD ITEMS, not on FastSeg's output. Tagging is a decision about
an item's words, so feeding it the gold action isolates it from the cut and the
span; otherwise a cut error would be charged to the tagger.

THE FOUR ARMS. Arm D exists because of a measured lesson the lexicon already
taught: overriding in BOTH directions lost more events than it gained tasks
(82.4% against 87.5%), so a signal is worth more as a one-way veto than as a
verdict. If that generalises, it applies to the head too.
"""
from __future__ import annotations

import collections
import glob
import json
import os
import sys

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

for _k, _v in (("MACALENDAR_DB", "/tmp/th.db"), ("MACALENDAR_MEMORY_DB", "/tmp/th_m.db"),
               ("MACALENDAR_VOCAB", "/tmp/th_v.json"),
               ("MACALENDAR_CATEGORIES", "/tmp/th_c.json"),
               ("MACALENDAR_TRACE_BUS", "/tmp/th_bus.jsonl"),
               ("MACALENDAR_NO_WARMUP", "1"), ("OMP_NUM_THREADS", "1")):
    os.environ.setdefault(_k, _v)

from assistant.engine.segmentation.experiments import run_board as RB      # noqa: E402
from assistant.engine.segmentation.fastseg.fastseg import tag as shipped_tag  # noqa: E402

#: How decisive the head must be before it is allowed to speak, for arms C and D.
#: FastRule's own floor for its atomicity head is the precedent for having one at
#: all: a model that answers every row also answers the rows it should decline.
MARGIN = 0.25


def _rows():
    rows = []
    for p in glob.glob(os.path.join(_HERE, "datasets", "*.jsonl")):
        for line in open(p):
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    return [r for r in RB.assign_splits(rows) if r.get("split") != "test"]


def _fitting_texts() -> set:
    """The texts the head was actually fitted on — its train half."""
    out = set()
    path = os.path.join(_ROOT, "assistant", "engine", "fastrule", "datasets",
                        "fastrule_7200.jsonl")
    for line in open(path):
        r = json.loads(line)
        if r.get("split") == "train":
            out.add(r["text"].strip().lower())
    return out


def _review_precheck(action: str) -> "str | None":
    """The deterministic review test the shipped tagger uses, unchanged."""
    from assistant.engine.segmentation.old_seg.segment import (
        _enforce_pinned_kinds, _kind_of)
    kind = _enforce_pinned_kinds(_kind_of(action), action)
    return "review" if kind == "review" else None


def arms():
    from assistant.intent.classifier import ROUTER
    ROUTER.load()

    def head(action):
        label, margin = ROUTER.kind.predict(action)
        return label, margin

    def A(action, time_str):                       # the shipped tagger
        return shipped_tag(action, time_str)

    def B(action, time_str):                       # review, then the head decides
        pre = _review_precheck(action)
        if pre:
            return pre
        return head(action)[0]

    def C(action, time_str):                       # the head only when decisive
        pre = _review_precheck(action)
        if pre:
            return pre
        label, margin = head(action)
        return label if margin >= MARGIN else shipped_tag(action, time_str)

    def D(action, time_str):                       # a one-way veto over `event`
        shipped = shipped_tag(action, time_str)
        if shipped != "event":
            return shipped
        label, margin = head(action)
        return "task" if label == "task" and margin >= MARGIN else shipped

    return {"A shipped tagger": A,
            "B review + head": B,
            f"C head when margin>={MARGIN}": C,
            f"D head vetoes 'event' only": D}


def score(rows, fn):
    ok = n = 0
    conf = collections.Counter()
    per = collections.defaultdict(lambda: collections.Counter())
    for r in rows:
        for g in r["gold"]:
            g = g if isinstance(g, dict) else {"action": g[0], "time": g[1], "tag": g[2]}
            got = fn(g["action"], g["time"])
            want = g["tag"]
            n += 1
            ok += got == want
            conf[(want, got)] += 1
            per[want]["support"] += 1
            if got == want:
                per[want]["tp"] += 1
            else:
                per[got]["fp"] += 1
    return ok, n, conf, per


def main() -> None:
    rows = _rows()
    fitted = _fitting_texts()
    slices = {
        f"ALL train items ({len(rows)} rows)": rows,
        "NOT in the head's fitting data":
            [r for r in rows if r["text"].strip().lower() not in fitted],
        "hand-written only (cannot be in FastRule)":
            [r for r in rows if r.get("source") == "handwritten"],
    }
    every = arms()
    for label, subset in slices.items():
        print(f"\n{'=' * 74}\n{label} — {len(subset)} rows\n{'=' * 74}")
        for name, fn in every.items():
            ok, n, conf, per = score(subset, fn)
            line = f"  {name:32s} {100 * ok / max(1, n):5.1f}%  ({ok}/{n})"
            # task recall is the number the lexicon experiment turned on
            tr = conf[("task", "task")]
            tn = sum(v for (w, _g), v in conf.items() if w == "task")
            ev = conf[("event", "event")]
            en = sum(v for (w, _g), v in conf.items() if w == "event")
            print(f"{line}   task recall {100 * tr / max(1, tn):5.1f}%"
                  f"   event recall {100 * ev / max(1, en):5.1f}%")
        # the confusion for the shipped arm and the best challenger, side by side
        if subset is rows:
            for name in ("A shipped tagger", "B review + head"):
                _ok, _n, conf, _p = score(subset, every[name])
                print(f"\n  confusion — {name} (gold -> predicted)")
                for w in ("event", "task", "review"):
                    row = "  ".join(f"{g}:{conf[(w, g)]:4d}"
                                    for g in ("event", "task", "review"))
                    print(f"     {w:8s} {row}")


if __name__ == "__main__":
    main()
