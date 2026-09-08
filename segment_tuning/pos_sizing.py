"""SIZING EXPERIMENT — would a POS/dependency parse fix FastSeg's tagger?

Not a component. A one-off measurement that answers ONE question before any
rewrite is paid for: task recall has sat at 70.7% all session (159 tasks called
events), and the proposal on the table is to rebuild FastSeg on spaCy. This
scores candidate taggers over the SAME matched items the board uses, so the
answer is in the board's own units.

The naive hypothesis is "root is a VERB -> task, root is a NOUN -> event". It
is tested here alongside its obvious failure mode: "book the dentist" is
VERB-rooted and an EVENT, because `book` is a calendar verb. If the lexical
variant beats the syntactic one, the tag problem is not syntactic and a POS
rewrite should not be sold on it.

    python -m segment_tuning.pos_sizing

Train half only — direction comes from the training pool.
"""
from __future__ import annotations

import collections
import glob
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Scratch stores before anything from `assistant` is imported (paths are read
# at import time, so setting them later is too late).
_SCRATCH = os.environ.get("TMPDIR", "/tmp") + "/segment_pos_sizing"
os.makedirs(_SCRATCH, exist_ok=True)
os.environ.setdefault("MACALENDAR_DB", f"{_SCRATCH}/cal.db")
os.environ.setdefault("MACALENDAR_MEMORY_DB", f"{_SCRATCH}/mem.db")
os.environ.setdefault("MACALENDAR_VOCAB", f"{_SCRATCH}/vocab.json")
os.environ.setdefault("MACALENDAR_CATEGORIES", f"{_SCRATCH}/cat.json")
os.environ.setdefault("MACALENDAR_TRACE_BUS", f"{_SCRATCH}/trace.jsonl")
os.environ.setdefault("MACALENDAR_NO_WARMUP", "1")

from segment_tuning import score as sc                 # noqa: E402
from segment_tuning.fastseg import fastseg, find_time_refs   # noqa: E402
from segment_tuning.run_board import assign_splits     # noqa: E402

#: Verbs that put something on the CALENDAR even though they are verbs. This
#: is the list the syntactic hypothesis has to beat — if it wins, the signal is
#: lexical and a parser is the wrong tool.
_CALENDAR_VERBS = {
    "book", "schedule", "plan", "arrange", "reschedule", "rebook",
    "cancel", "move", "postpone", "delete", "clear", "block",
}
#: Verbs that put something on the TO-DO LIST.
_TASK_VERBS = {
    "remind", "buy", "call", "email", "text", "pick", "collect", "grab",
    "wash", "clean", "fold", "pack", "sort", "file", "pay", "submit",
    "prepare", "print", "water", "walk", "take", "change", "top", "order",
    "renew", "return", "drop", "send", "finish", "write", "update", "check",
}


def _is_review(action: str) -> bool:
    """Review detection is already 100% precision / 87.5% recall on the board,
    so it is held FIXED across every variant — this experiment is about the
    event/task confusion and must not be credited for changing anything else."""
    a = action.lower()
    return (a.startswith(("what", "when", "where", "how many", "do i", "does "))
            or "on my calendar" in a or "my schedule" in a
            or "what do i have" in a)


def make_variants(nlp):
    """Each variant is `(name, fn(action, time) -> tag)`."""

    def head_token(doc):
        for t in doc:
            if t.dep_ == "ROOT":
                return t
        return doc[0] if len(doc) else None

    def v_syntactic(action, time_str):
        """THE HYPOTHESIS UNDER TEST: root VERB -> task, root NOUN -> event."""
        if _is_review(action):
            return "review"
        doc = nlp(action)
        root = head_token(doc)
        if root is None:
            return "event"
        return "task" if root.pos_ in ("VERB", "AUX") else "event"

    def v_lexical(action, time_str):
        """No parser at all: the first verb-ish token against two word lists."""
        if _is_review(action):
            return "review"
        for w in action.lower().replace(",", " ").split():
            if w in _CALENDAR_VERBS:
                return "event"
            if w in _TASK_VERBS:
                return "task"
        return "event"

    def v_lexical_then_syntactic(action, time_str):
        """Lexicon decides when it knows; the parse breaks the ties."""
        if _is_review(action):
            return "review"
        for w in action.lower().replace(",", " ").split():
            if w in _CALENDAR_VERBS:
                return "event"
            if w in _TASK_VERBS:
                return "task"
        doc = nlp(action)
        root = head_token(doc)
        if root is None:
            return "event"
        return "task" if root.pos_ in ("VERB", "AUX") else "event"

    def v_clock(action, time_str):
        """No syntax at all — does the item name a CLOCK time? Events happen at
        a time; tasks are due on a day. Included as the cheap control: if this
        matches the parser, the parser is not what is doing the work."""
        if _is_review(action):
            return "review"
        return "event" if any(r.kind == "clock"
                              for r in find_time_refs(time_str)) else "task"

    return [("syntactic (root POS)", v_syntactic),
            ("lexical (verb lists)", v_lexical),
            ("lexical -> syntactic", v_lexical_then_syntactic),
            ("clock-time control", v_clock)]


def main() -> None:
    rows = [r for r in assign_splits(
        sc.load_rows(sorted(glob.glob(f"{_HERE}/data/*.jsonl"))))
        if r["split"] == "train"]

    print(f"loading spaCy…", flush=True)
    import spacy
    nlp = spacy.load("en_core_web_sm", disable=["ner", "lemmatizer"])

    # Collect the SAME matched items the board scores over, so the numbers are
    # directly comparable to board C rather than to a different population.
    cases = []                     # (action, time, gold_tag, baseline_tag)
    for r in rows:
        pred = [sc.as_item(i) for i in fastseg(r["text"])]
        pairs, _mg, _mp = sc.match_items(r["gold"], pred)
        for gi, pi, _s in pairs:
            cases.append((pred[pi]["action"], pred[pi]["time"],
                          r["gold"][gi]["tag"], pred[pi]["tag"]))
    print(f"matched items: {len(cases)}\n")

    def board(name, tags):
        acc = sum(t == g for t, (_a, _t, g, _b) in zip(tags, cases)) / len(cases)
        conf = collections.Counter((g, t) for t, (_a, _tm, g, _b) in zip(tags, cases))
        line = f"  {name:24s} accuracy {acc:6.1%}"
        for cls in ("event", "task", "review"):
            tp = conf[(cls, cls)]
            n_gold = sum(v for (g, _p), v in conf.items() if g == cls)
            n_pred = sum(v for (_g, p), v in conf.items() if p == cls)
            rec = tp / n_gold if n_gold else 0.0
            prec = tp / n_pred if n_pred else 0.0
            line += f"   {cls[:4]} P{prec:5.1%} R{rec:5.1%}"
        print(line)
        return conf

    print("BASELINE — what the board reports today")
    base_conf = board("current tag()", [b for _a, _t, _g, b in cases])
    print(f"     the cell in question: gold=task predicted=event  "
          f"{base_conf[('task', 'event')]} items\n")

    print("CANDIDATES")
    results = {}
    for name, fn in make_variants(nlp):
        tags = [fn(a, t) for a, t, _g, _b in cases]
        results[name] = board(name, tags)
    print()
    for name, conf in results.items():
        fixed = base_conf[("task", "event")] - conf[("task", "event")]
        broke = conf[("event", "task")] - base_conf[("event", "task")]
        print(f"  {name:24s} task->event errors fixed {fixed:+4d}   "
              f"new event->task errors {broke:+4d}")

    # What the parser sees on the items the lexicon cannot decide — the honest
    # place to look for whether a parse adds anything the word lists do not.
    print("\nITEMS NO VERB LIST DECIDES (where a parser would have to earn it)")
    undecided = [c for c in cases
                 if not ({w for w in c[0].lower().split()}
                         & (_CALENDAR_VERBS | _TASK_VERBS)) and not _is_review(c[0])]
    print(f"  {len(undecided)} of {len(cases)} matched items")
    dist = collections.Counter(g for _a, _t, g, _b in undecided)
    print(f"  their gold tags: {dict(dist)}")
    for a, t, g, b in undecided[:10]:
        doc = nlp(a)
        root = next((x for x in doc if x.dep_ == "ROOT"), None)
        print(f"     {a[:42]:44s} gold={g:6s} root={root.text if root else '?'}"
              f"/{root.pos_ if root else '?'}")


if __name__ == "__main__":
    main()
