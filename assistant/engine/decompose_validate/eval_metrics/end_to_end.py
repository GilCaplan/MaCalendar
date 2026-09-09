"""H · END TO END — this stage on REAL segmentation output, with blame attributed.

    python -m assistant.engine.decompose_validate.eval_metrics.end_to_end [train|test]

Every other board here feeds GOLD (text, time) pairs in, which excludes
segmentation error by construction. That is the right way to measure a resolver —
a segmentation slip must not be charged to it — but it means the headline says
nothing about what a speaker actually gets. This board asks that question, and it
is much harsher: 99.9% gold-fed became 51.6% end to end on the same rows
(2026-09-09).

**The attribution is what makes it usable.** A raw end-to-end number blames the
pair and tells you nothing about which half to fix, so every value error on a
MATCHED item is split:

    words AGREE and the value is wrong   -> a resolver bug, this stage's
    words DIFFER                          -> it answered a different question
                                             correctly; the fix is upstream

First run: 1,445 errors, 100% in the second bucket, 0 in the first. That is the
evidence that sent the work to segmentation rather than here — and if a future
change to `resolve.py` regresses, the FIRST bucket is where it will show up, which
is the reason to keep this board rather than the one-off script it started as.

Two malformed-item counts need no gold at all, so they are the cheapest signal in
the file: an action ending in a dangling joiner, and two clock times inside one
item (segmentation ARCHITECTURE.md §8.1).
"""
import os, sys, json, datetime as dt, collections
D = os.environ.get("MACALENDAR_SCRATCH", "/tmp")
os.environ.update(
    MACALENDAR_DB=os.path.join(D,"e.db"), MACALENDAR_MEMORY_DB=os.path.join(D,"e_m.db"),
    MACALENDAR_VOCAB=os.path.join(D,"e_v.json"), MACALENDAR_CATEGORIES=os.path.join(D,"e_c.json"),
    MACALENDAR_TRACE_BUS=os.path.join(D,"e_bus.jsonl"),
    MACALENDAR_NO_WARMUP="1", OMP_NUM_THREADS="1")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, ROOT)

from assistant.engine import segmentation as SEG
from assistant.engine.state import EngineState
from assistant.engine.decompose_validate import checks as C, resolve as R
from assistant.engine.decompose_validate.eval_metrics import score as S

rows = [json.loads(l) for l in open(os.path.join(
    ROOT, "assistant/engine/decompose_validate/datasets/generated.jsonl"))]
split = sys.argv[1] if len(sys.argv) > 1 else "train"
rows = [r for r in rows if r["split"] == split]

FIELDS = ("date", "start_time", "end_time", "recurrence", "quantity", "reminder_minutes")
gold_items = matched = 0
spurious = 0
field_ok = collections.Counter(); field_n = collections.Counter()
rows_all_ok = 0
malformed = collections.Counter()

for r in rows:
    anchor = dt.date.fromisoformat(r["today"])
    st = EngineState(raw_text=r["text"], text=r["text"], source="test")
    SEG.run(st, None)

    pred = []
    for it in st.items:
        said = it.time or ""
        own = f"{said} {it.text}".strip()
        v = R.resolve(said, anchor, own, action=it.text or "")
        pred.append({"kind": it.kind, "text": it.text or "", "time": said,
                     "date": v["date"], "start_time": v["start_time"],
                     "end_time": v["end_time"], "recurrence": v["recurrence"],
                     "recur_days": v.get("recur_days") or [],
                     "recur_until": v.get("recur_until"),
                     "quantity": R.resolve_quantity(it.text or ""),
                     "reminder_minutes": R.resolve_lead_time(said)
                                         or R.resolve_lead_time(it.text or "")})
        # a dangling joiner is a MALFORMED item, countable without gold
        t = (it.text or "").strip().lower()
        if t.endswith((" and", " then", " also", " plus", ",")):
            malformed["action ends in a joiner"] += 1
        # COUNT REFERENCES, not clock-shaped substrings. Counting substrings
        # flagged every legitimate RANGE -- "from 10am to 11:30am" contains two
        # clock expressions and is ONE reference -- so the 54 this reported were
        # mostly ranges rather than the §8.1 enumerations it was built to catch.
        # Segmentation's own reader knows the difference, so ask it.
        from assistant.engine.segmentation.fastseg.fastseg import find_time_refs
        clocks = [r for r in find_time_refs(said)
                  if r.kind in ("clock", "enum_clock")]
        if len(clocks) > 1:
            malformed["two clocks in one item"] += 1

    pred, _f, _g = C.run(pred, r["text"], anchor)
    pairs, unmatched_g, unmatched_p = S.match_items(r["gold"], pred)
    gold_items += len(r["gold"]); matched += len(pairs); spurious += len(unmatched_p)

    ok_row = not unmatched_g and not unmatched_p
    for gi, pi in pairs:
        g, p = r["gold"][gi], pred[pi]
        for f in FIELDS:
            if g.get(f) is None and p.get(f) is None:
                continue
            field_n[f] += 1
            if str(g.get(f)) == str(p.get(f)):
                field_ok[f] += 1
            else:
                ok_row = False
    rows_all_ok += ok_row

print(f"END TO END — segmentation + decompose_validate, split={split}, {len(rows)} rows\n")
print(f"  ITEM RECALL      {100*matched/gold_items:5.1f}%  ({matched}/{gold_items} gold items "
      f"reached the stage)")
print(f"  spurious items   {spurious}")
print(f"  rows fully right {100*rows_all_ok/len(rows):5.1f}%  ({rows_all_ok}/{len(rows)})\n")
print("  VALUE ACCURACY on the items that DID match:")
for f in FIELDS:
    if field_n[f]:
        print(f"     {f:18s} {100*field_ok[f]/field_n[f]:5.1f}%  ({field_ok[f]}/{field_n[f]})")
print("\n  MALFORMED items segmentation emitted (no gold needed):")
for k, n in malformed.most_common():
    print(f"     {k:28s} {n}")


# ---------------------------------------------------------------------------
# The attribution: whose error is it?
# ---------------------------------------------------------------------------

def norm(s):
    return " ".join((s or "").lower().split())


agree_wrong = collections.Counter()
differ_wrong = collections.Counter()
for r in rows:
    anchor = dt.date.fromisoformat(r["today"])
    st = EngineState(raw_text=r["text"], text=r["text"], source="test")
    SEG.run(st, None)
    pred = []
    for it in st.items:
        said = it.time or ""
        own = f"{said} {it.text}".strip()
        v = R.resolve(said, anchor, own, action=it.text or "")
        pred.append({"kind": it.kind, "text": it.text or "", "time": said,
                     "date": v["date"], "start_time": v["start_time"],
                     "end_time": v["end_time"], "recurrence": v["recurrence"],
                     "recur_days": v.get("recur_days") or [],
                     "recur_until": v.get("recur_until"),
                     "quantity": R.resolve_quantity(it.text or ""),
                     "reminder_minutes": R.resolve_lead_time(said)
                                         or R.resolve_lead_time(it.text or "")})
    pred, _f2, _g2 = C.run(pred, r["text"], anchor)
    pairs, _ug, _up = S.match_items(r["gold"], pred)
    for gi, pi in pairs:
        g, p = r["gold"][gi], pred[pi]
        same = norm(g.get("time")) == norm(p.get("time")) and \
               norm(g.get("text")) == norm(p.get("text"))
        for f in FIELDS:
            if g.get(f) is None and p.get(f) is None:
                continue
            if str(g.get(f)) != str(p.get(f)):
                (agree_wrong if same else differ_wrong)[f] += 1

ta, td = sum(agree_wrong.values()), sum(differ_wrong.values())
print(f"\n  ATTRIBUTION of the {ta + td} value errors on matched items")
print(f"     words DIFFER -> upstream   {td:5d}  {100*td/max(1,ta+td):5.1f}%")
print(f"     words AGREE  -> THIS stage {ta:5d}  {100*ta/max(1,ta+td):5.1f}%"
      f"   <- must stay at 0")
if ta:
    print("     fields with a real resolver bug:",
          dict(agree_wrong.most_common()))
