"""The ATOMIZER board — segment + decompose, scored as the thing they ARE.

The architecture splits in two halves. FastRule is the ATOMIC-ITEM EXECUTOR:
it handles exactly one event or task and defers anything else. The deep track
is the ATOMIZER: **segment** cuts a command into separate asks, **decompose**
breaks each into atomic items, and only then does anything create a row. So
the atomizer sets a CEILING on the whole system:

    under-split  ->  FastRule is handed a compound it must refuse, and the
                     command half-executes or falls through
    over-split   ->  the system manufactures garbage items ("meeting with Tal
                     and Sam" becoming two meetings) — immediate, visible harm

Until now everything known about these two stages was INFERRED from the
engine's headline number, which is precisely the "mystery drop" that
DOCUMENTATION/STAGE_ISOLATION_PLAN.md exists to abolish. This board gives
them a metric of their own.

WHAT IT MEASURES (all counts as well as rates — the errors are asymmetric)

    M1 count-correct   did the atomizer produce the RIGHT NUMBER of items?
    M2 UNDER-split     fewer items than asks.  Recoverable: decompose and
                       crosscheck each get another look.  The project's
                       stated bias.
    M3 OVER-split      more items than asks.  The dangerous one: a torn ask
                       is garbage the moment it is created.
    M4 mis-typed       right count, wrong kinds (event/task/review)
    M5 boundary        on compounds with distinguishable anchors: does each
                       item hold the whole of ONE ask and nothing of another?
                       clean / bleed (2 asks in 1 item) / lost / duplicated
    M6 LLM reachability  segment's deterministic delimiters never fire on
                       ordinary dictation, so its ENTIRE splitting power is
                       one gated LLM call.  A compound that never reaches
                       that call can never be split — this is the recall
                       CEILING of the gate, and it is free to measure.
    M7 decompose rescue / damage
                       rescue: compounds segment left merged that decompose
                       fixed — the empirical test of the under-split bias's
                       own justification ("a wrong merge gets two more
                       chances").
                       damage: atomic rows segment got right that decompose
                       then broke.

TWO DATASETS, reported separately

    B  dataset/fastrule/fastrule_7200.jsonl  — ground truth BY CONSTRUCTION,
       split by pattern family.  Test half is the reported number.
    P  dataset/personas/personas.jsonl — 6 synthetic speakers, TEST-ONLY
       forever (dataset/personas/PERSONAS.md).  Rambling vs terse speakers
       are exactly where an atomizer should differ.

GROUND TRUTH: neither set carries expected item SPANS, but both carry
`expect.atomic` plus per-sub-ask numbered slots (`title_2`, `time_phrase_2`,
...).  Ask count = 1 when atomic, else max(numbered-slot suffix, 2) — verified
against every pattern family's declared intent (three_ask -> 3, np_decoy -> 1,
and_compound -> 2, time-list -> 2, time-range -> 1).  No new dataset needed.

LEAKAGE: test halves print AGGREGATES ONLY.  Row text is printed only under
--split train (B).  Persona rows are test-only by construction and are never
printed.

OLLAMA: --llm is OFF by default.  segment's and decompose's model calls hit
the same single `ollama serve` an engine measurement run uses; firing at it
mid-run inflates that run's latency metric.  Run the deterministic board any
time; run --llm only when no measurement is in flight.

    python -m scripts.atomizer_board                    # B-test + personas, no LLM
    python -m scripts.atomizer_board --split train      # mining half (B only)
    python -m scripts.atomizer_board --llm              # with the model (SERIAL!)
    python -m scripts.atomizer_board --dataset P        # personas only
"""
from __future__ import annotations

import argparse
import collections
import datetime as _dt
import json
import os
import pathlib
import re
import sys
import tempfile

# --- scratch stores BEFORE importing anything from assistant ---------------
_T = tempfile.mkdtemp(prefix="atomizer_board_")
for _v, _n in (("DB", "c"), ("MEMORY_DB", "m"), ("VOCAB", "v"),
               ("CATEGORIES", "cat"), ("TRACE_BUS", "t"), ("LOCATION", "l")):
    os.environ[f"MACALENDAR_{_v}"] = os.path.join(_T, _n)
os.environ["MACALENDAR_NO_WARMUP"] = "1"
# one BLAS thread — this board is expected to run beside a measurement job
for _b in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_b, "1")

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

B_DATA = ROOT / "dataset" / "fastrule" / "fastrule_7200.jsonl"
B_SIMPLE = ROOT / "dataset" / "fastrule" / "banks" / "simple_patterns.json"
B_COMPLEX = ROOT / "dataset" / "fastrule" / "banks" / "complex_patterns.json"
P_DATA = ROOT / "dataset" / "personas" / "personas.jsonl"

#: same frozen clock the FastRule boards use, so the three are comparable
_CLOCK = _dt.datetime(2026, 9, 9, 10, 0)

_SUFFIX_RE = re.compile(r"_(\d+)$")

#: kind implied by a single-action row.  `mixed` and `propose` are not here on
#: purpose — a mixed row's per-ask kinds are only recoverable when the
#: create counts account for every ask (see `want_kinds`).
_ACTION_KIND = {
    "create_event": "event", "delete_event": "event", "update_event": "event",
    "create_todo": "task", "delete_todo": "task", "update_todo": "task",
    "complete_todo": "task",
    "query": "review",
}


# ---------------------------------------------------------------------------
# Ground truth
# ---------------------------------------------------------------------------

def _suffix_max(slots: dict) -> int:
    m = 1
    for k in slots:
        g = _SUFFIX_RE.search(k)
        if g:
            m = max(m, int(g.group(1)))
    return m


def want_asks(row: dict) -> int:
    """How many ATOMIC items this utterance should become.

    `expect.atomic` is ground truth by construction; the numbered slot
    suffixes name each further sub-ask.  A compound with no suffixed slot at
    all is a mixed row whose second ask is a bare query/clear ("clear my
    to-do list and remind me to ...") — still two asks, hence the floor of 2.
    """
    e = row["expect"]
    if e.get("atomic", True):
        return 1
    return max(_suffix_max(e.get("slots") or {}), 2)


def want_kinds(row: dict, n: int) -> "collections.Counter | None":
    """Expected item-kind multiset, or None when the row cannot determine it.

    Determinable two ways: the create counts account for every ask (so the
    multiset is exactly events x "event" + tasks x "task"), or the row has a
    single non-mixed action whose kind applies to all of its asks.  A mixed
    compound with a non-create ask (a query joined to a create) is honestly
    left unscored rather than guessed at.
    """
    e = row["expect"]
    ev, td = int(e.get("events", 0) or 0), int(e.get("tasks", 0) or 0)
    if n > 0 and ev + td == n:
        return collections.Counter({"event": ev, "task": td}) - collections.Counter()
    k = _ACTION_KIND.get(e.get("action", ""))
    if k:
        return collections.Counter({k: n})
    return None


#: date phrases are DELIBERATELY excluded as boundary anchors — segment's own
#: prompt tells the model to repeat a shared date into every item, so a
#: duplicated date is designed behaviour, not a torn ask.
_ANCHOR_BASES = ("title", "time_phrase")


def anchors(row: dict, n: int) -> "list[str] | None":
    """n mutually-distinguishable strings, one per expected sub-ask.

    Requires every anchor present, all distinct, and none a substring of
    another — which is what disqualifies the NP-decoy shape (`title` =
    "apples and eggs", `title_2` = "eggs": two fillers, ONE ask).
    """
    if n < 2:
        return None
    s = row["expect"].get("slots") or {}
    for base in _ANCHOR_BASES:
        vals = []
        for i in range(1, n + 1):
            v = s.get(base if i == 1 else f"{base}_{i}")
            if not v:
                break
            vals.append(str(v).strip().lower())
        if len(vals) != n or len(set(vals)) != n:
            continue
        if any(a != b and a in b for a in vals for b in vals):
            continue
        return vals
    return None


def boundary(texts: "list[str]", vals: "list[str]") -> str:
    """clean | bleed | lost | duplicated — the first defect that applies."""
    low = [t.lower() for t in texts]
    hits = [[j for j, v in enumerate(vals) if v in t] for t in low]
    seen = collections.Counter(j for h in hits for j in h)
    if any(len(h) > 1 for h in hits):
        return "bleed"                       # >=2 asks living in one item
    if any(seen[j] == 0 for j in range(len(vals))):
        return "lost"                        # an ask's words survive nowhere
    if any(seen[j] > 1 for j in range(len(vals))):
        return "duplicated"                  # one ask smeared over two items
    if len(texts) != len(vals):
        return "lost"
    return "clean"


# ---------------------------------------------------------------------------
# The datasets
# ---------------------------------------------------------------------------

def _b_family_nuance() -> dict:
    out = {}
    for f in json.loads(B_SIMPLE.read_text()):
        out[f["family"]] = f"simple:{f.get('action', '?')}"
    for f in json.loads(B_COMPLEX.read_text()):
        out[f["family"]] = f.get("nuance", "complex:?")
    return out


def b_rows(split: str) -> list:
    nuance = _b_family_nuance()
    out = []
    for line in B_DATA.open():
        r = json.loads(line)
        if split != "all" and r["split"] != split:
            continue
        r["_group"] = nuance.get(r["family"], "?")
        r["_tier"] = r.get("tier", "?")
        out.append(r)
    return out


def p_rows(_split: str) -> list:
    out = []
    for line in P_DATA.open():
        r = json.loads(line)
        r["_group"] = r.get("persona", "?")
        r["_tier"] = r.get("tier", "?")
        out.append(r)
    return out


# ---------------------------------------------------------------------------
# Driving the two stages in isolation
# ---------------------------------------------------------------------------

class LLMGate:
    """Wraps `assistant.engine.llm.call_json` to (a) count how often a stage
    ATTEMPTS a model call — which is exactly the reachability metric, read off
    the shipped gate rather than a reimplementation of it — and (b) refuse the
    call in deterministic mode.  Both stages already treat an exception as
    "keep one item", which is their real offline behaviour."""

    def __init__(self, allow: bool):
        self.allow = allow
        self.attempts = 0
        self._real = None

    def install(self):
        from assistant.engine import llm as _llm
        self._real = _llm.call_json
        _llm.call_json = self._call
        return self

    def _call(self, cfg, system, user, schema):
        self.attempts += 1
        if not self.allow:
            raise RuntimeError("atomizer_board: LLM disabled")
        return self._real(cfg, system, user, schema)


class Runner:
    def __init__(self, gate: LLMGate, use_fastrule: bool = True):
        from assistant.engine import load_config
        self.cfg = load_config()
        self.gate = gate
        self.use_fastrule = use_fastrule
        self.fr = None
        if use_fastrule:
            from assistant.engine.fastrule import FastRule
            from assistant.intent.rule_parser import RULE_THRESHOLD
            self.fr = FastRule(RULE_THRESHOLD)
            self.fr.run("book gym tomorrow at 7am")   # warm off the frozen clock

    def state(self, text: str):
        """Everything the deep track has when segment receives the command:
        the repaired transcript, and FastRule's verdict travelling forward."""
        from assistant.engine import transcript
        from assistant.engine.state import EngineState
        st = EngineState(raw_text=text, text=text, source="test")
        transcript.run(st, self.cfg)
        committed = False
        if self.fr is not None:
            from assistant.engine.fastrule import reason_class
            res = self.fr.run(st.text)
            if res and res.committed:
                committed = True
            elif res is not None:
                st.fastrule_verdict = {
                    "reason": res.reason,
                    "reason_class": reason_class(res.reason),
                    "confidence": res.confidence,
                    "actions": [n for n, _ in res.intents],
                }
        return st, committed

    def run_row(self, text: str) -> dict:
        """One row through segment, then decompose.  Returns both snapshots
        plus the model-call attempt counts per stage."""
        from assistant.engine import decompose, segment
        st, committed = self.state(text)
        if st.ignored:
            return {"ignored": True, "fast": committed}
        a0 = self.gate.attempts
        segment.run(st, self.cfg)
        seg_calls = self.gate.attempts - a0
        seg = [(i.kind, i.text) for i in st.items]
        a1 = self.gate.attempts
        decompose.run(st, self.cfg)
        dec_calls = self.gate.attempts - a1
        dec = [(i.kind, i.text) for i in st.items]
        return {"ignored": False, "fast": committed, "seg": seg, "dec": dec,
                "seg_calls": seg_calls, "dec_calls": dec_calls}


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

class Tally:
    """One stage's scorecard over one slice."""

    def __init__(self):
        self.n = 0
        self.exact = 0
        self.under = 0
        self.over = 0
        self.mistyped = 0
        self.kind_n = 0
        self.bound = collections.Counter()
        self.confusion = collections.Counter()
        self.n_compound = 0
        self.compound_exact = 0
        self.n_atomic = 0
        self.atomic_exact = 0

    def add(self, want_n, got_kinds, wk, anch, texts):
        got_n = len(got_kinds)
        self.n += 1
        if want_n == 1:
            self.n_atomic += 1
        else:
            self.n_compound += 1
        if got_n == want_n:
            self.exact += 1
            if want_n == 1:
                self.atomic_exact += 1
            else:
                self.compound_exact += 1
            if wk is not None:
                self.kind_n += 1
                gk = collections.Counter(got_kinds)
                if gk != wk:
                    self.mistyped += 1
                    self.confusion[(_ks(wk), _ks(gk))] += 1
        elif got_n < want_n:
            self.under += 1
        else:
            self.over += 1
        if anch:
            self.bound[boundary(texts, anch)] += 1

    def pc(self, x):
        return f"{x / self.n:6.1%}" if self.n else "     —"


def _ks(c: "collections.Counter") -> str:
    return "+".join(f"{k}x{v}" if v > 1 else k for k, v in sorted(c.items()) if v)


def _fmt(t: Tally, name: str) -> str:
    return (f"  {name:<24} n {t.n:>5}   count-correct {t.pc(t.exact)}"
            f"   UNDER {t.under:>4} ({t.pc(t.under).strip()})"
            f"   OVER {t.over:>4} ({t.pc(t.over).strip()})"
            f"   mis-typed {t.mistyped:>4}/{t.kind_n}")


def report(title: str, rows, results, groups_label: str, mining: bool):
    seg_all, dec_all = Tally(), Tally()
    seg_deep, dec_deep = Tally(), Tally()    # rows FastRule declined = what
                                             # the atomizer actually receives
    seg_by, dec_by = collections.defaultdict(Tally), collections.defaultdict(Tally)
    dec_tier = collections.defaultdict(Tally)
    seg_tier = collections.defaultdict(Tally)
    ask_tally = collections.defaultdict(Tally)

    reach_c = reach_c_hit = 0            # M6: compounds whose segment call fired
    reach_a = reach_a_hit = 0            # ... and atomic rows (a cost, not a gain)
    rescued = rescue_pool = 0            # M7
    damaged = damage_pool = 0
    dec_helped = dec_hurt = dec_touched = 0
    fast_committed = ignored = 0
    seg_calls = dec_calls = 0
    ask_hist = collections.Counter()
    samples = collections.defaultdict(list)

    for row, res in zip(rows, results):
        if res.get("ignored"):
            ignored += 1
            continue
        if res.get("fast"):
            fast_committed += 1
        n = want_asks(row)
        wk = want_kinds(row, n)
        anch = anchors(row, n)
        ask_hist[n] += 1
        seg_kinds = [k for k, _ in res["seg"]]
        seg_texts = [t for _, t in res["seg"]]
        dec_kinds = [k for k, _ in res["dec"]]
        dec_texts = [t for _, t in res["dec"]]

        seg_all.add(n, seg_kinds, wk, anch, seg_texts)
        dec_all.add(n, dec_kinds, wk, anch, dec_texts)
        ask_tally[n].add(n, dec_kinds, wk, anch, dec_texts)
        if not res.get("fast"):
            seg_deep.add(n, seg_kinds, wk, anch, seg_texts)
            dec_deep.add(n, dec_kinds, wk, anch, dec_texts)
        g = row["_group"]
        seg_by[g].add(n, seg_kinds, wk, anch, seg_texts)
        dec_by[g].add(n, dec_kinds, wk, anch, dec_texts)
        seg_tier[row["_tier"]].add(n, seg_kinds, wk, anch, seg_texts)
        dec_tier[row["_tier"]].add(n, dec_kinds, wk, anch, dec_texts)

        seg_calls += res["seg_calls"]
        dec_calls += res["dec_calls"]
        if n > 1:
            reach_c += 1
            reach_c_hit += 1 if res["seg_calls"] else 0
        else:
            reach_a += 1
            reach_a_hit += 1 if res["seg_calls"] else 0

        ns, nd = len(seg_kinds), len(dec_kinds)
        if nd != ns:
            dec_touched += 1
            before, after = abs(ns - n), abs(nd - n)
            if after < before:
                dec_helped += 1
            elif after > before:
                dec_hurt += 1
        if n > 1 and ns < n:                       # segment under-split
            rescue_pool += 1
            if nd == n:
                rescued += 1
        if n == 1 and ns == 1:                     # segment got an atomic row right
            damage_pool += 1
            if nd > 1:
                damaged += 1

        if mining and len(samples["over"]) < 10 and len(dec_kinds) > n:
            samples["over"].append(f"[want {n} got {len(dec_kinds)}] {row['text'][:64]}"
                                   f"  -> {dec_texts}")
        if mining and len(samples["bleed"]) < 8 and anch \
                and boundary(dec_texts, anch) == "bleed":
            samples["bleed"].append(f"[want {n} got {len(dec_kinds)}] {row['text'][:70]}")
        if mining and len(samples["mistyped"]) < 8 and wk is not None \
                and len(dec_kinds) == n and collections.Counter(dec_kinds) != wk:
            samples["mistyped"].append(
                f"[want {dict(wk)} got {dict(collections.Counter(dec_kinds))}] {row['text'][:60]}")

    n_used = seg_all.n
    print(f"\n{'=' * 92}\n{title}\n{'=' * 92}")
    print(f"rows {n_used}   (ignored by the transcript gate: {ignored}"
          f" · FastRule committed on the fast track: {fast_committed}"
          f" = {fast_committed / n_used:.1%} — these never reach the atomizer in production)")
    print(f"expected atomic-item counts: "
          + " · ".join(f"{k} ask{'s' if k > 1 else ''}: {v}" for k, v in sorted(ask_hist.items())))

    print(f"\nM1-M3 — the two stages, whole slice")
    print(_fmt(seg_all, "SEGMENT (step 2)"))
    print(_fmt(dec_all, "ATOMIZER (2 then 3)"))
    print(_fmt(seg_deep, "  ...segment, deep only"))
    print(_fmt(dec_deep, "  ...atomizer, deep only")
          + "   <- what the atomizer is actually handed in production")
    if dec_all.n_atomic:
        print(f"\n  atomic rows kept at 1              "
              f"{dec_all.atomic_exact:>5}/{dec_all.n_atomic}"
              f" ({dec_all.atomic_exact / dec_all.n_atomic:.1%})")
    if dec_all.n_compound:
        print(f"  COMPOUND rows atomized correctly  "
              f"{dec_all.compound_exact:>5}/{dec_all.n_compound}"
              f" ({dec_all.compound_exact / dec_all.n_compound:.1%})"
              f"   <- the ceiling FastRule's executor sits under")

    print(f"\nM1 by expected ask count — ATOMIZER")
    for k in sorted(ask_tally):
        print(_fmt(ask_tally[k], f"{k} ask{'s' if k > 1 else ''}"))

    print(f"\nM4 — mis-typed (right count, wrong kinds; aggregate confusion)")
    print(f"  atomizer  {dec_all.mistyped}/{dec_all.kind_n} "
          f"({dec_all.mistyped / dec_all.kind_n:.1%} of count-correct, "
          f"kind-determinable rows)" if dec_all.kind_n else "  (none scorable)")
    for (w, g), v in dec_all.confusion.most_common(8):
        print(f"     {v:>5}   want {w:<16} got {g}")

    print(f"\nM5 — boundary integrity (compounds with distinguishable anchors)")
    tot = sum(dec_all.bound.values())
    if tot:
        for k in ("clean", "bleed", "lost", "duplicated"):
            v = dec_all.bound.get(k, 0)
            note = {"clean": "each item holds exactly one whole ask",
                    "bleed": "TWO asks inside one item (under-split)",
                    "lost": "an ask's own words survive in no item (torn/dropped)",
                    "duplicated": "one ask smeared across two items"}[k]
            print(f"  {k:<12} {v:>5} ({v / tot:5.1%})   {note}")
    else:
        print("  (no anchored compounds in this slice)")

    print(f"\nM6 — LLM reachability (segment's splitting power is ONE gated call)")
    print(f"  compound rows reaching the call   {reach_c_hit:>5}/{reach_c}"
          f" ({reach_c_hit / reach_c:.1%})   <- RECALL CEILING: the rest can never be split"
          if reach_c else "  (no compounds)")
    if reach_a:
        print(f"  atomic rows reaching the call     {reach_a_hit:>5}/{reach_a}"
              f" ({reach_a_hit / reach_a:.1%})   (pure cost: a call that should return 1 item)")
    print(f"  model calls attempted             segment {seg_calls} · decompose {dec_calls}")

    print(f"\nM7 — decompose's own contribution")
    print(f"  changed the item count            {dec_touched:>5}"
          f"   (helped {dec_helped} · hurt {dec_hurt})")
    print(f"  RESCUE  segment under-split, decompose fixed it   "
          f"{rescued:>5}/{rescue_pool}"
          f" ({rescued / rescue_pool:.1%})" if rescue_pool else
          "  RESCUE  (no under-split rows)")
    print(f"  DAMAGE  segment right at 1, decompose split it    "
          f"{damaged:>5}/{damage_pool}"
          f" ({damaged / damage_pool:.1%})" if damage_pool else
          "  DAMAGE  (no atomic rows)")

    print(f"\nBy tier — ATOMIZER")
    for k in sorted(dec_tier):
        print(_fmt(dec_tier[k], k))

    print(f"\nBy {groups_label} — ATOMIZER (worst count-correct first)")
    order = sorted(dec_by, key=lambda g: (dec_by[g].exact / dec_by[g].n) if dec_by[g].n else 1)
    for g in order:
        t = dec_by[g]
        if t.n < 8:
            continue
        s = seg_by[g]
        print(_fmt(t, g) + f"   [segment {s.pc(s.exact).strip()}]")

    if mining:
        print("\n--- mining (train half only) ---")
        for k in ("over", "bleed", "mistyped"):
            if samples[k]:
                print(f"\n{k}:")
                for s in samples[k]:
                    print(f"   {s}")
    return {"seg": seg_all, "dec": dec_all}


# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=("train", "test", "all"), default="test")
    ap.add_argument("--dataset", choices=("both", "B", "P"), default="both")
    ap.add_argument("--llm", action="store_true",
                    help="allow segment/decompose model calls (SERIAL — never "
                         "beside an engine measurement run)")
    ap.add_argument("--no-fastrule", action="store_true",
                    help="skip FastRule; segment then sees no verdict (measures "
                         "the cue-word gate alone)")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    from freezegun import freeze_time

    gate = LLMGate(allow=a.llm).install()
    runner = Runner(gate, use_fastrule=not a.no_fastrule)

    print("ATOMIZER BOARD — segment (step 2) + decompose (step 3), in isolation")
    print(f"  LLM: {'ENABLED' if a.llm else 'DISABLED (deterministic path only)'}"
          f"   ·  FastRule verdict fed forward: {not a.no_fastrule}"
          f"   ·  clock frozen at {_CLOCK:%Y-%m-%d %H:%M}")
    print("  UNDER-split is the cheap error (two more recovery chances); "
          "OVER-split creates garbage immediately.")

    sets = []
    if a.dataset in ("both", "B"):
        sets.append(("B", b_rows(a.split), "nuance family"))
    if a.dataset in ("both", "P"):
        sets.append(("P", p_rows("test"), "persona"))

    for name, rows, glabel in sets:
        if a.limit:
            rows = rows[:a.limit]
        with freeze_time(_CLOCK):
            results = [runner.run_row(r["text"]) for r in rows]
        mining = (name == "B" and a.split == "train")
        title = ({"B": f"B — FastRule 7,200, {a.split} half (generated, family-split)",
                  "P": "P — persona sets, 6 speakers (TEST-ONLY, never mined)"}[name])
        report(title, rows, results, glabel, mining)

    if a.split != "train":
        print("\n(test halves: aggregates only — leakage guard)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
