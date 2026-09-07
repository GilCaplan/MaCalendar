#!/usr/bin/env python3
"""Score the engine's fast track per PERSONA, and report the SPREAD.

The question this answers: does engine quality vary by who is speaking? The
claim under test is that a user's personal vocabulary lives in SLOTS and so
cannot move the trained classifiers, which read STRUCTURE. If that holds, every
persona's board looks the same and the variance rows are ~0. If it does not,
the variance rows say by how much, and which persona pays.

The metrics are `scripts/fastrule_shape.py`'s, unchanged and imported from it
rather than recopied, so a persona board and a FastRule board mean the same
thing:

  PRIMARY (atomic rows)      handled (committed) · correct-on-handled · deferred
  TIME                       explicit time right · invented a time
  DIAGNOSTIC (non-atomic)    deferred (knew / by accident) · covered · HALF-EXECUTED
  PROPOSE (Q9)               defer rate — a commit is a violation
  CLASSIFIERS                accuracy + macro-F1 for atomicity / operation / kind

TWO READINGS OF EVERY PRIMARY METRIC, and they answer different questions:

  natural mix       the persona's own distribution of asks (a parent really
                    does create more tasks). Product-realistic; a persona can
                    score low here just for asking harder things.
  structure-matched macro-average over the 33 SHARED structures, equal weight
                    each, restricted to structures every persona has a defined
                    value for. Composition is then identical by construction,
                    so the spread is attributable to WORDS AND PHRASING alone.
                    THIS is the number the vocabulary-independence claim lives
                    or dies on.

    python -m scripts.persona_board
    python -m scripts.persona_board --structures      # per-structure detail
    python -m scripts.persona_board --examples 6      # failing rows (synthetic; mining is fine)
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Importing this ALSO pins every MACALENDAR_* store at a scratch dir, sets
# MACALENDAR_NO_WARMUP and pins BLAS to one thread — see its module header.
# It must happen before anything under assistant/ is imported.
from scripts import fastrule_shape as FS       # noqa: E402

DATA = ROOT / "dataset" / "personas" / "personas.jsonl"
BASE = ["observant_student", "household_parent", "freelance_consultant",
        "retiree", "uni_student", "esl_speaker"]
#: filled from whichever file is scored — the ablation file's columns are
#: `vocab:<p>` / `phrase:<p>` cells, not personas
PERSONAS: list = []
SHORT: dict = {}


def set_columns(labels) -> None:
    """Column order: the persona order if this is the persona file, else the
    ablation's two blocks in that same order. Never the file's own order,
    which is shuffled."""
    global PERSONAS, SHORT
    labels = set(labels)
    order = [p for p in BASE if p in labels]
    for prefix in ("vocab:", "phrase:"):
        order += [prefix + p for p in BASE if prefix + p in labels]
    order += sorted(labels - set(order))
    PERSONAS = order
    alias = {"observant_student": "observant", "household_parent": "parent",
             "freelance_consultant": "consultant", "retiree": "retiree",
             "uni_student": "student", "esl_speaker": "esl"}
    SHORT = {}
    for p in order:
        pre, _, base = p.rpartition(":")
        tag = {"vocab": "v:", "phrase": "p:"}.get(pre, "")
        SHORT[p] = (tag + alias.get(base, base))[:14]


def blocks_of(labels):
    """The groups a variance spread is meaningful WITHIN. One block for the
    persona file; for the ablation, the vocab block and the phrase block are
    separate experiments and must never be pooled."""
    v = [p for p in labels if p.startswith("vocab:")]
    f = [p for p in labels if p.startswith("phrase:")]
    if v and f:
        return [("VOCABULARY VARIES, phrasing held at the control", v),
                ("PHRASING VARIES, vocabulary held at the control", f)]
    return [("across personas", list(labels))]


#: `\bam\b` does NOT match "8:45am" — digit and letter are both word
#: characters, so there is no boundary between them. The lookbehind is what
#: makes "8:45am" match while "program" does not.
_AMPM = re.compile(r"(?<![a-z])(?:am|pm)\b|\bnoon\b|\bmidnight\b|\bmidday\b", re.I)
_CLOCK24 = re.compile(r"^(?:at\s+)?(\d{1,2}):(\d{2})$")


def time_is_unambiguous(phrase: str) -> bool:
    """Does the speaker's own phrase FIX the half of the day?

    This split matters because the scorer's `_phrase_to_hhmm` resolves a
    spelled-out hour ('quarter past four') to AM, while the engine applies an
    afternoon preference — so a mismatch there is a CONVENTION disagreement,
    not a parse error, and it lands entirely on the personas who spell times
    out. Only the unambiguous half ('7pm', '07:00', 'noon') is evidence of a
    real defect, so the board reports the two separately and never mixes them.
    """
    s = (phrase or "").strip().lower()
    if _AMPM.search(s):
        return True
    m = _CLOCK24.match(s)
    if m:
        return int(m.group(1)) >= 13 or m.group(1).startswith("0")
    return False


class Bucket:
    """Counters for one (persona, structure) cell — or one whole persona."""

    def __init__(self) -> None:
        self.a_ok = self.a_wrong = self.a_miss = 0
        self.n_defer = self.n_defer_knew = self.n_commit = self.n_commit_ok = 0
        self.p_defer = self.p_commit = 0
        self.t_ok = self.t_n = 0
        self.t_ok_u = self.t_n_u = 0      # speaker fixed am/pm — real errors
        self.t_ok_a = self.t_n_a = 0      # spelled-out — convention-confounded
        self.invent = self.invent_n = 0

    def add(self, o: "Bucket") -> "Bucket":
        for k, v in vars(o).items():
            setattr(self, k, getattr(self, k) + v)
        return self

    # -- the metrics, each None when its denominator is empty ---------------
    @property
    def a_n(self):
        return self.a_ok + self.a_wrong + self.a_miss

    @property
    def handled(self):
        return (self.a_ok + self.a_wrong) / self.a_n if self.a_n else None

    @property
    def correct_on_handled(self):
        d = self.a_ok + self.a_wrong
        return self.a_ok / d if d else None

    @property
    def deferred(self):
        return self.a_miss / self.a_n if self.a_n else None

    @property
    def n_n(self):
        return self.n_defer + self.n_commit

    @property
    def defer_rate(self):
        return self.n_defer / self.n_n if self.n_n else None

    @property
    def knew(self):
        return self.n_defer_knew / self.n_n if self.n_n else None

    @property
    def covered(self):
        return self.n_commit_ok / self.n_n if self.n_n else None

    @property
    def half_executed(self):
        return (self.n_commit - self.n_commit_ok) / self.n_n if self.n_n else None

    @property
    def propose_defer(self):
        d = self.p_defer + self.p_commit
        return self.p_defer / d if d else None

    @property
    def time_right(self):
        return self.t_ok / self.t_n if self.t_n else None

    @property
    def time_right_unambiguous(self):
        return self.t_ok_u / self.t_n_u if self.t_n_u else None

    @property
    def time_right_ambiguous(self):
        return self.t_ok_a / self.t_n_a if self.t_n_a else None

    @property
    def invent_rate(self):
        return self.invent / self.invent_n if self.invent_n else None


#: metric key -> (label, direction) where direction is +1 if higher is better
METRICS = [
    ("handled", "atomic handle-rate", +1),
    ("correct_on_handled", "correct-on-handled", +1),
    ("deferred", "atomic deferred", -1),
    ("time_right", "explicit time right", +1),
    ("time_right_unambiguous", "  time right (am/pm said)", +1),
    ("invent_rate", "INVENTED a time", -1),
    ("defer_rate", "non-atomic deferred", +1),
    ("covered", "non-atomic covered", +1),
    ("half_executed", "HALF-EXECUTED", -1),
    ("propose_defer", "propose defer rate", +1),
]


def pc(x):
    return "   —  " if x is None else f"{x:6.1%}"


def score(rows, examples: int):
    """Run FastRule over every row once; bucket by (persona, structure)."""
    from freezegun import freeze_time
    from assistant.engine.fastrule import FastRule
    from assistant.intent.rule_parser import RULE_THRESHOLD

    fr = FastRule(RULE_THRESHOLD)
    fr.run("book gym tomorrow at 7am")          # warm outside the frozen clock

    cells: dict = collections.defaultdict(Bucket)
    fails: dict = collections.defaultdict(list)
    reasons: dict = collections.defaultdict(collections.Counter)
    preds: dict = collections.defaultdict(lambda: {"text": [], "op": [], "kind": [], "at": []})

    with freeze_time(FS._CLOCK):
        for r in rows:
            p, st, e = r["persona"], r["structure"], r["expect"]
            b = cells[(p, st)]
            act = e["action"]
            res = fr.run(r["text"])
            committed = bool(res and res.committed)

            g = r["gold"]
            preds[p]["text"].append(r["text"])
            preds[p]["at"].append(g["atomicity"])
            preds[p]["op"].append(g["operation"])
            preds[p]["kind"].append(g["kind"])

            if act == "propose":
                if committed:
                    b.p_commit += 1
                    if len(fails[(p, "propose-commit")]) < examples:
                        fails[(p, "propose-commit")].append(r["text"])
                else:
                    b.p_defer += 1
                continue

            if not e["atomic"]:
                if committed:
                    b.n_commit += 1
                    ev = sum(1 for n, _ in res.intents if n == "create_event")
                    td = sum(1 for n, _ in res.intents if n == "create_todo")
                    if ev >= e["events"] and td >= e["tasks"]:
                        b.n_commit_ok += 1
                    elif len(fails[(p, "half-executed")]) < examples:
                        fails[(p, "half-executed")].append(
                            f"[{st}] want e{e['events']}/t{e['tasks']} got e{ev}/t{td}  {r['text']}")
                else:
                    b.n_defer += 1
                    if (res.reason or "").split(":")[0] in FS._ATOMICITY_REASONS:
                        b.n_defer_knew += 1
                continue

            # --- atomic row
            if not committed:
                b.a_miss += 1
                reasons[p][(res.reason or "none").split(":")[0]] += 1
                if len(fails[(p, "atomic-deferred")]) < examples:
                    fails[(p, "atomic-deferred")].append(
                        f"[{st}/{(res.reason or '?').split(':')[0]}] {r['text']}")
                continue

            ev = sum(1 for n, _ in res.intents if n == "create_event")
            td = sum(1 for n, _ in res.intents if n == "create_todo")
            names = [n for n, _ in res.intents]
            if act in ("create_event", "create_todo"):
                ok = ev >= e["events"] and td >= e["tasks"]
            elif act == "query":
                ok = (ev + td) == 0 and any(n.startswith("query") for n in names)
            else:
                ok = (ev + td) == 0 and any(n.startswith(act.split("_")[0]) for n in names)

            if act == "create_event":
                first = next((i for n, i in res.intents if n == "create_event"), None)
                got_t = str(getattr(first, "start_time", "") or "")
                phrase = (e["slots"] or {}).get("time_phrase") or ""
                if phrase and FS._EXPLICIT_TIME_RE.search(phrase):
                    want = FS._phrase_to_hhmm(phrase)
                    if want and FS._HHMM.match(got_t):
                        b.t_n += 1
                        sure = time_is_unambiguous(phrase)
                        if sure:
                            b.t_n_u += 1
                        else:
                            b.t_n_a += 1
                        if got_t == want:
                            b.t_ok += 1
                            if sure:
                                b.t_ok_u += 1
                            else:
                                b.t_ok_a += 1
                        elif sure and len(fails[(p, "wrong-time-UNAMBIGUOUS")]) < examples:
                            fails[(p, "wrong-time-UNAMBIGUOUS")].append(
                                f"[{st}] said {phrase!r} -> want {want}, got {got_t}  {r['text']}")
                        elif len(fails[(p, "wrong-time")]) < examples:
                            fails[(p, "wrong-time")].append(
                                f"[{st}] said {phrase!r} -> want {want}, got {got_t}  {r['text']}")
                elif not phrase:
                    b.invent_n += 1
                    if FS._HHMM.match(got_t) and got_t != "00:00":
                        b.invent += 1
                        if len(fails[(p, "invented-time")]) < examples:
                            fails[(p, "invented-time")].append(
                                f"[{st}] no time said, produced {got_t}  {r['text']}")

            if ok:
                b.a_ok += 1
            else:
                b.a_wrong += 1
                if len(fails[(p, "atomic-wrong")]) < examples:
                    fails[(p, "atomic-wrong")].append(f"[{st}] want {act}, got {names}  {r['text']}")

    return cells, fails, reasons, preds


def classifier_board(preds):
    """The three trained classifiers, per persona. Raw argmax accuracy and
    macro-F1 — the models' own quality, before FastRule's margin floors decide
    whether to listen. `evaluate()` is the shipped LogisticModel's own."""
    from assistant.intent.classifier import ModelRouter
    router = ModelRouter()
    if not router.load():
        return None, None
    out = {}
    for p, d in preds.items():
        row = {}
        # gold is None wherever the row has no single right answer (a
        # cross-action compound is neither 'new' nor 'remove'); those rows are
        # EXCLUDED from that classifier's score rather than guessed at.
        for key, field, model in (("atomicity", "at", router.atomicity),
                                  ("operation", "op", router.operation),
                                  ("kind", "kind", router.kind)):
            pairs = [(t, y) for t, y in zip(d["text"], d[field]) if y]
            texts = [t for t, _ in pairs]
            labels = [y for _, y in pairs]
            row[key] = model.evaluate(texts, labels) if labels and model.weights else None
            row[key + "_n"] = len(labels)
        # the product-relevant one: layer 0 only ACTS on "compound"
        comp_tot = sum(1 for y in d["at"] if y == "compound")
        comp_hit = sum(1 for t, y in zip(d["text"], d["at"])
                       if y == "compound" and router.looks_compound(t))
        atom_tot = sum(1 for y in d["at"] if y == "atomic")
        atom_fp = sum(1 for t, y in zip(d["text"], d["at"])
                      if y == "atomic" and router.looks_compound(t))
        row["compound_recall_at_floor"] = comp_hit / comp_tot if comp_tot else None
        row["atomic_fp_at_floor"] = atom_fp / atom_tot if atom_tot else None

        # WHY a classifier does worse for one persona: how much EVIDENCE its
        # featurizer even sees. Every feature but the bias is a regex over the
        # words; a row that fires none of them can only receive the class
        # prior, whatever the weights are. This is the mechanism behind any
        # spread above, stated in the classifier's own terms.
        for key, fz in (("operation", router.operation.featurizer),
                        ("kind", router.kind.featurizer),
                        ("atomicity", router.atomicity.featurizer)):
            fired = [sum(fz.extract(t)[1:]) for t in d["text"]]
            row[key + "_fired"] = statistics.fmean(fired)
            row[key + "_blind"] = sum(1 for f in fired if f == 0) / len(fired)
        out[p] = row
    return out, router


def variance_table(title, values, direction, note=""):
    """values: {persona: metric|None}. Prints spread = best - worst in points."""
    live = {p: v for p, v in values.items() if v is not None}
    if len(live) < 2:
        return None
    best = max(live, key=lambda p: live[p] * direction)
    worst = min(live, key=lambda p: live[p] * direction)
    spread = abs(live[best] - live[worst]) * 100
    sd = statistics.pstdev(live.values()) * 100
    print(f"  {title:26s} {spread:6.1f} pt   sd {sd:5.1f}   "
          f"best {SHORT[best]:14s}{live[best]:6.1%}   "
          f"worst {SHORT[worst]:14s}{live[worst]:6.1%}   {note}")
    return spread


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--structures", action="store_true", help="per-structure detail")
    ap.add_argument("--examples", type=int, default=0,
                    help="print N failing rows per persona per bucket (synthetic data — mining is fine)")
    ap.add_argument("--persona", help="restrict the failing-row dump to one persona")
    ap.add_argument("--data", default=str(DATA),
                    help="jsonl to score (default the persona set; pass "
                         "dataset/personas/personas_ablation.jsonl for the "
                         "vocabulary-vs-phrasing ablation)")
    a = ap.parse_args()

    path = pathlib.Path(a.data).resolve()
    rows = [json.loads(l) for l in path.open(encoding="utf-8")]
    set_columns({r["persona"] for r in rows})
    structures = sorted({r["structure"] for r in rows})
    cells, fails, reasons, preds = score(rows, max(a.examples, 3))

    totals = {p: Bucket() for p in PERSONAS}
    for (p, st), b in cells.items():
        totals[p].add(b)

    # ---- one board per persona ----------------------------------------
    print("=" * 100)
    print(f"PERSONA BOARDS — {path.name} "
          f"({len(rows)} rows, {len(PERSONAS)} columns x {len(rows)//len(PERSONAS)}, "
          "TEST-ONLY)\nfast track only (FastRule + gates, no LLM, no execution) · "
          "metrics from scripts/fastrule_shape.py")
    print("=" * 100)
    hdr = f"{'':30s}" + "".join(f"{SHORT[p]:>15s}" for p in PERSONAS)
    print(hdr)

    def line(label, fn, indent=2):
        print(" " * indent + f"{label:{30-indent}s}"
              + "".join(f"{pc(fn(totals[p])):>15s}" for p in PERSONAS))

    print("\nATOMIC rows — should HANDLE  (n per persona: "
          + " ".join(str(totals[p].a_n) for p in PERSONAS) + ")")
    line("handled (committed)", lambda b: b.handled)
    line("correct-on-handled", lambda b: b.correct_on_handled)
    line("deferred (missed work)", lambda b: b.deferred)

    print("\nTIME CORRECTNESS (committed events)")
    line("explicit time right", lambda b: b.time_right)
    print(" " * 2 + f"{'  n scored':28s}"
          + "".join(f"{totals[p].t_n:>15d}" for p in PERSONAS))
    line("  ...speaker fixed am/pm", lambda b: b.time_right_unambiguous)
    print(" " * 2 + f"{'     n':28s}"
          + "".join(f"{totals[p].t_n_u:>15d}" for p in PERSONAS))
    line("  ...spelled out (see note)", lambda b: b.time_right_ambiguous)
    print(" " * 2 + f"{'     n':28s}"
          + "".join(f"{totals[p].t_n_a:>15d}" for p in PERSONAS))
    print("     (the spelled-out row is CONVENTION-CONFOUNDED: this scorer resolves "
          "'quarter past four'\n      to 04:15, the engine prefers the afternoon. "
          "Only the am/pm row is evidence of a defect.)")
    line("INVENTED a time", lambda b: b.invent_rate)
    print(" " * 2 + f"{'  n (no time said)':28s}"
          + "".join(f"{totals[p].invent_n:>15d}" for p in PERSONAS))

    print("\nNON-ATOMIC rows — diagnostic  (n per persona: "
          + " ".join(str(totals[p].n_n) for p in PERSONAS) + ")")
    line("deferred, handed up", lambda b: b.defer_rate)
    line("  ...knew it was compound", lambda b: b.knew)
    line("covered (all asks present)", lambda b: b.covered)
    line("HALF-EXECUTED", lambda b: b.half_executed)

    print("\nPROPOSE rows (Q9) — should DEFER  (n per persona: "
          + " ".join(str(totals[p].p_defer + totals[p].p_commit) for p in PERSONAS) + ")")
    line("defer rate", lambda b: b.propose_defer)

    # ---- the three trained classifiers --------------------------------
    cb, router = classifier_board(preds)
    if cb:
        print("\nTRAINED CLASSIFIERS (assistant/intent/classifier.py, raw argmax)")
        for key, label in (("atomicity", "atomicity"), ("operation", "operation"), ("kind", "kind")):
            print(f"  {label + ' accuracy':28s}"
                  + "".join(f"{pc(cb[p][key]['accuracy'] if cb[p][key] else None):>15s}"
                            for p in PERSONAS))
            print(f"  {'  macro-F1':28s}"
                  + "".join(f"{pc(cb[p][key]['macro_f1'] if cb[p][key] else None):>15s}"
                            for p in PERSONAS))
        print(f"  {'compound recall @floor':28s}"
              + "".join(f"{pc(cb[p]['compound_recall_at_floor']):>15s}" for p in PERSONAS))
        print(f"  {'atomic false-compound @floor':28s}"
              + "".join(f"{pc(cb[p]['atomic_fp_at_floor']):>15s}" for p in PERSONAS))
        print("\n  HOW MUCH EVIDENCE THE FEATURIZERS SEE (mean non-bias features fired "
              "per row,\n  and the share of rows that fire NONE — those can only get the "
              "class prior):")
        for key in ("operation", "kind", "atomicity"):
            print(f"    {key + ' features fired':26s}"
                  + "".join(f"{cb[p][key + '_fired']:>15.2f}" for p in PERSONAS))
            print(f"    {'  rows firing none':26s}"
                  + "".join(f"{pc(cb[p][key + '_blind']):>15s}" for p in PERSONAS))
    else:
        print("\n(no route_model_weights.json loaded — classifier board skipped)")

    # ---- structure-matched macro --------------------------------------
    print("\n" + "=" * 100)
    print("STRUCTURE-MATCHED MACRO — each of the 33 shared structures weighted equally,\n"
          "restricted to structures every persona has a defined value for. Composition is\n"
          "then identical across personas, so this spread is vocabulary + phrasing ONLY.")
    print("=" * 100)
    matched = {}
    for key, label, direction in METRICS:
        support = [st for st in structures
                   if all(getattr(cells.get((p, st), Bucket()), key) is not None
                          for p in PERSONAS)]
        if not support:
            matched[key] = (None, 0)
            continue
        matched[key] = ({p: statistics.fmean(
            getattr(cells[(p, st)], key) for st in support) for p in PERSONAS}, len(support))
    print(hdr)
    for key, label, direction in METRICS:
        vals, n = matched[key]
        if not vals:
            continue
        print(f"  {label + f' [{n}]':28s}" + "".join(f"{pc(vals[p]):>15s}" for p in PERSONAS))

    # ---- THE VARIANCE SUMMARY ------------------------------------------
    print("\n" + "=" * 100)
    print("VARIANCE — the spread IS the finding")
    print("=" * 100)
    for block_name, cols in blocks_of(PERSONAS):
        print(f"\n### {block_name}")
        print("\nNatural mix (each column's own distribution of asks):")
        for key, label, direction in METRICS:
            variance_table(label, {p: getattr(totals[p], key) for p in cols}, direction)
        if cb:
            for key in ("atomicity", "operation", "kind"):
                variance_table(f"{key} accuracy",
                               {p: (cb[p][key]["accuracy"] if cb[p][key] else None)
                                for p in cols}, +1)
            variance_table("compound recall @floor",
                           {p: cb[p]["compound_recall_at_floor"] for p in cols}, +1)
        print("\nStructure-matched (identical composition — the clean comparison):")
        for key, label, direction in METRICS:
            vals, n = matched[key]
            if vals:
                variance_table(label, {p: vals[p] for p in cols}, direction,
                               note=f"({n} structures)")

    # ---- per-structure detail ------------------------------------------
    if a.structures:
        print("\n" + "=" * 100)
        print("PER-STRUCTURE correct-on-handled (atomic) / covered (compound) — "
              "spread column names the structures that split the personas")
        print("=" * 100)
        print(f"{'structure':24s}" + "".join(f"{SHORT[p]:>15s}" for p in PERSONAS) + "   spread")
        scored = []
        for st in structures:
            key = ("correct_on_handled"
                   if any(cells.get((p, st), Bucket()).a_n for p in PERSONAS)
                   else "covered")
            vals = {p: getattr(cells.get((p, st), Bucket()), key) for p in PERSONAS}
            live = [v for v in vals.values() if v is not None]
            sp = (max(live) - min(live)) * 100 if len(live) > 1 else 0.0
            scored.append((sp, st, key, vals))
        for sp, st, key, vals in sorted(scored, reverse=True):
            print(f"{st:24s}" + "".join(f"{pc(vals[p]):>15s}" for p in PERSONAS)
                  + f"   {sp:5.1f} pt  ({key.replace('_', '-')})")

    # ---- failing rows ---------------------------------------------------
    if a.examples:
        print("\n" + "=" * 100)
        print("FAILING ROWS (synthetic data — mining these is allowed and is the point)")
        print("=" * 100)
        for p in PERSONAS:
            if a.persona and p != a.persona:
                continue
            print(f"\n### {p}")
            if reasons[p]:
                print("  atomic rows deferred, by reason: "
                      + ", ".join(f"{k}={v}" for k, v in reasons[p].most_common(6)))
            for bucket in ("atomic-wrong", "atomic-deferred", "half-executed",
                           "wrong-time-UNAMBIGUOUS", "wrong-time", "invented-time",
                           "propose-commit"):
                got = fails.get((p, bucket), [])[:a.examples]
                if got:
                    print(f"  {bucket}:")
                    for s in got:
                        print(f"     {s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
