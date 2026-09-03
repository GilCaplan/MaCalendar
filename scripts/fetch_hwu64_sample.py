"""Fetch a stratified sample of real calendar/reminder phrasing, once, to build
a retrieval pool that is NOT this user's own history.

The command-memory / few-shot feature retrieves from this one user's real
command history (`~/.assistant_tools/nlu_memory.db`, 74 commands over 8 days,
65% of them from a single day). That is fine for the feature itself — a
personal assistant only has one person to personalise to — but it means every
measurement of "does retrieval help" so far has used a small, narrow, single-
source pool. This script builds an outside comparison pool so a scaling study
(does pool SIZE matter, independent of whether it's personalised) has
something real, diverse, and much larger to compare against.

The source is HWU-64 (Liu, Eshghi, Swietojanski & Rieser, IWSDS 2019),
calendar/alarm/lists domains — real crowdsourced "what would you tell your
PDA" utterances, annotated with intent and entities. CC BY 4.0. Pinned to a
commit so re-running this script reproduces the same fixture:
https://github.com/xliuhw/NLU-Evaluation-Data/blob/6e495bf0d371d18b611398f205bf53ddb9b1ad5d/AnnotatedData/NLU-Data-Home-Domain-Annotated-All.csv

So this script — and ONLY this script — goes to the network. It downloads the
CSV, drops rows too short or with leftover template brackets ("[event]"),
stratified-samples up to N per (scenario, intent) bucket in proportion to how
much of that bucket actually exists, shuffles once with a fixed seed, and
tags each row with a `tier_rank` (its position in the shuffle) and a synthetic
`ts` spread over the past ~180 days — so a scaling study can slice nested
tiers (rank <= 60, <= 300, ...) straight out of one fixture, and the pool
looks like it accumulated over time rather than arriving in one burst.

    python -m scripts.fetch_hwu64_sample              # refresh the fixture (n=3000)
    python -m scripts.fetch_hwu64_sample --n 500       # a smaller fixture
    python -m scripts.fetch_hwu64_sample --check       # verify, write nothing

Run it when the sample size changes, or never — the fixture is checked in.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import pathlib
import random
import sys
import time
import urllib.error
import urllib.request

COMMIT = "6e495bf0d371d18b611398f205bf53ddb9b1ad5d"
URL = (f"https://raw.githubusercontent.com/xliuhw/NLU-Evaluation-Data/{COMMIT}/"
       "AnnotatedData/NLU-Data-Home-Domain-Annotated-All.csv")
EXP_DIR = pathlib.Path(__file__).resolve().parents[1] / "DOCUMENTATION" / "experiments" / "memory_scaling"
FIXTURE = EXP_DIR / "hwu64_sample.json"           # raw fetch + sample — provenance/license record
DATASET_DIR = EXP_DIR / "dataset"                 # what actually gets replayed — see write_histories()

#: Each size is one *history*: a self-contained, ordered (input, timestamp)
#: sequence that means something on its own — not a slice that only makes
#: sense next to the others. Nested by construction (history_300 starts with
#: every row of history_60) purely so building the larger ones doesn't
#: recompute what a smaller one already covers; each file still stands alone.
TIERS = [60, 300, 1000, 3000]

#: (scenario, intent) buckets to draw from, and roughly how much weight each
#: gets relative to the others — proportional to how often it occurs in the
#: source data, computed at sample time from what's actually available so this
#: doesn't silently break if the dataset changes. Excludes calendar/lists rows
#: whose intent is 'remove' or bare 'query' with no content words — those need
#: a pre-existing record to act on and don't make sense as standalone
#: retrieval examples the way a create-style command does.
BUCKETS = [
    ("calendar", "set"), ("calendar", "query"), ("calendar", "remove"),
    ("lists", "createoradd"), ("lists", "query"), ("lists", "remove"),
]

SEED = 20260903
HISTORY_SPAN_DAYS = 180


def _fetch() -> str:
    req = urllib.request.Request(URL, headers={"User-Agent": "macalendar-audit/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


#: Word-count cut point separating "simple" from "medium" single-action
#: utterances (p50=7 in the actual cleaned source data). There is no
#: single-utterance "complex" tier — HWU-64 was elicited one action per
#: utterance ("what would you tell your PDA to do X"), so a longer sentence
#: there is just a more detailed description of ONE thing, not genuinely
#: harder. What actually stresses this system — multiple events, multiple
#: tasks, or a mix of the two in one command — doesn't occur naturally in
#: the source at all; _compose_complex builds it directly instead.
def _complexity(text: str) -> str:
    return "simple" if len(text.split()) <= 6 else "medium"


def _clean_rows(csv_text: str) -> list[dict]:
    rows = list(csv.DictReader(io.StringIO(csv_text), delimiter=";"))
    out = []
    for row in rows:
        text = (row.get("answer") or "").strip()
        if not text or len(text.split()) < 4:
            continue
        if "[" in text or "]" in text:
            continue  # leftover template placeholder, not real spoken text
        out.append({"scenario": row["scenario"], "intent": row["intent"], "text": text,
                    "complexity": _complexity(text)})
    return out


_CONNECTIVES = [" and ", " and also ", ", and then ", ". Also, ", " — and "]


def _join_two(a: str, b: str, rnd: random.Random) -> str:
    a = a.strip().rstrip(".!?")
    b = b.strip()
    conn = rnd.choice(_CONNECTIVES)
    if conn[0] == "." or conn[0] == ",":
        pass                                  # sentence-final connective keeps b's own casing
    else:
        b = b[0].lower() + b[1:] if b else b  # mid-sentence join reads as one command
    return f"{a}{conn}{b}"


def _compose_complex(rows: list[dict], rnd: random.Random, n: int) -> list[dict]:
    """Build n genuinely multi-action prompts: two real utterances joined.

    Even thirds across event+event ("book gym... and a meeting..."), task+
    task ("add milk... and also remind me to..."), and event+task — the
    system's own domain split (calendar events vs. todo/task items, which
    separately carry tags and due dates). Drawn with replacement: HWU-64
    only has 257 usable lists/createoradd utterances, not enough to build
    thousands of unique pairs without reusing components — accepted here
    since the pairING is what makes each one distinct, not the raw halves.
    """
    cal = [r["text"] for r in rows if r["scenario"] == "calendar" and r["intent"] == "set"]
    tsk = [r["text"] for r in rows if r["scenario"] == "lists" and r["intent"] == "createoradd"]
    if not cal or not tsk:
        return []
    kinds = (["event+event"] * (n - 2 * (n // 3))) + (["task+task"] * (n // 3)) + (["event+task"] * (n // 3))
    rnd.shuffle(kinds)
    out = []
    for kind in kinds:
        if kind == "event+event":
            a, b = rnd.choice(cal), rnd.choice(cal)
        elif kind == "task+task":
            a, b = rnd.choice(tsk), rnd.choice(tsk)
        else:
            a, b = rnd.choice(cal), rnd.choice(tsk)
        out.append({"scenario": "compound", "intent": kind,
                    "text": _join_two(a, b, rnd), "complexity": "complex"})
    return out


def build_sample(n: int, rows: list[dict], seed: int = SEED) -> list[dict]:
    rnd = random.Random(seed)
    # Roughly equal thirds: simple/medium as single real utterances (scenario/
    # intent proportions preserved within each), complex as composed pairs.
    want_tier = round(n / 3)
    sample: list[dict] = []
    for tier in ("simple", "medium"):
        tier_rows = [r for r in rows if r["complexity"] == tier]
        by_bucket = {b: [r for r in tier_rows if (r["scenario"], r["intent"]) == b] for b in BUCKETS}
        total = sum(len(v) for v in by_bucket.values())
        if total == 0:
            continue
        for bucket, items in by_bucket.items():
            want = round(want_tier * len(items) / total)
            rnd.shuffle(items)
            sample.extend(items[:want])
    sample.extend(_compose_complex(rows, rnd, n - len(sample)))

    rnd.shuffle(sample)
    sample = sample[:n]
    now = time.time()
    # Monotonic with tier_rank — rank 1 is the oldest, rank n the most recent —
    # so "replay in rank order" and "replay in timestamp order" are the same
    # thing. Independently-random timestamps (the first version of this) let
    # the two disagree, which matters once "run every input at its given
    # timestamp" is the actual definition of what a history *is*.
    span = HISTORY_SPAN_DAYS * 86400
    for i, row in enumerate(sample):
        row["tier_rank"] = i + 1
        row["ts"] = now - span * (1 - (i + 1) / len(sample))
    return sample


def write_histories(sample: list[dict], source_note: str, source_url: str) -> None:
    """Split the raw sample into self-contained history/<N>.json files.

    Each one is the complete dataset for one run: an ordered list of
    (input, timestamp) pairs and nothing else — no reference to the raw
    fixture or to any other history file. Replaying history_N.json's rows,
    in order, through the real assistant against a fresh scratch DB is
    what "the dataset" means here; the resulting DB is that history's
    dummy_N.db (built by scripts/build_memory_scaling_pool.py).
    """
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    ordered = sorted(sample, key=lambda r: r["tier_rank"])
    for n in TIERS:
        if n > len(ordered):
            continue
        rows = ordered[:n]
        out = DATASET_DIR / f"history_{n}.json"
        out.write_text(json.dumps({
            "name": f"history_{n}",
            "n": len(rows),
            "source": source_note,
            "source_url": source_url,
            "rows": [{"seq": i + 1, "text": r["text"], "ts": r["ts"]}
                     for i, r in enumerate(rows)],
        }, indent=1, ensure_ascii=False))
        print(f"wrote {out} ({len(rows)} rows)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=3000, help="sample size")
    ap.add_argument("--check", action="store_true", help="verify only, write nothing")
    args = ap.parse_args()

    try:
        csv_text = _fetch()
    except urllib.error.URLError as e:
        raise SystemExit(f"could not reach GitHub: {e}")

    rows = _clean_rows(csv_text)
    print(f"{len(rows)} usable rows after cleaning "
          f"(from {csv_text.count(chr(10))} raw lines)")
    for b in BUCKETS:
        n_b = sum(1 for r in rows if (r["scenario"], r["intent"]) == b)
        print(f"  {b[0]}/{b[1]:<12s} {n_b}")

    sample = build_sample(args.n, rows)
    print(f"\nsampled {len(sample)} (requested {args.n})")

    if args.check:
        if FIXTURE.exists():
            existing = json.loads(FIXTURE.read_text())
            same = len(existing) == len(sample)
            print(f"fixture has {len(existing)} rows; {'matches' if same else 'DIFFERS'} in count")
        else:
            print("no fixture written yet")
        return

    source_note = "HWU-64 (Liu, Eshghi, Swietojanski & Rieser, IWSDS 2019), CC BY 4.0"
    source_url = f"https://github.com/xliuhw/NLU-Evaluation-Data/tree/{COMMIT}"
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(json.dumps({
        "source": source_note,
        "source_url": source_url,
        "seed": SEED,
        "history_span_days": HISTORY_SPAN_DAYS,
        "rows": sample,
    }, indent=1, ensure_ascii=False))
    print(f"wrote {FIXTURE}")
    write_histories(sample, source_note, source_url)


if __name__ == "__main__":
    main()
