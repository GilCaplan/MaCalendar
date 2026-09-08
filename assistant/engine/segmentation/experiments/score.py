"""Score a segment decomposition against the gold rows — SIX boards.

`segment` takes ONE spoken command and returns a list of independent items,
each `(action, time, tag)`. This file is the only judge of whether it did.

Six boards, never one number — SPEC.md and DESIGN.md §6 both insist on it,
because a single figure hides WHICH WAY a run is failing, and the two ways
cost very different amounts:

    A  BOUNDARIES   did we cut in the right places
    B  ACTION/TIME  the invariant (invention · loss) + where the time landed
    C  TAG          event / task / review
    D  VERIFIER     does the model's correction pay for itself
    E  COST         model calls per row, wall clock
    F  COMPOSITION  what the score was computed OVER

Board F is not an afterthought. "Report the gold-count distribution beside
every score" (SPEC, Distribution) exists because a corpus with a
characteristic ask-count teaches the COUNT rather than the criterion — a
scorer that hides its composition lets that pass as a win.

    python assistant/engine/segmentation/experiments/score.py                   # self-test, proves the scorer
    python assistant/engine/segmentation/experiments/score.py --rows rows.jsonl # audit the GOLD labels

Imports are `json re argparse collections difflib` and nothing else — no
`assistant`, no spacy, no torch. Two model-loading jobs segfault this
project, so the scorer must be safe to import from anywhere, including from
inside a script that already holds a model. That is also why wall-clock on
board E is reported BY THE PREDICTOR rather than measured here: `time` is
outside the allowlist, and a predictor that cares about latency knows its
own timing better than a wrapper does.

Public API
----------
    score_rows(rows, predict, fastseg=None) -> dict
    format_board(result) -> str
    check_invariant(text, items) -> list[str]

`check_invariant` is deliberately exported: it is a METRIC here and a
RUNTIME GUARD in the ACCEPT stage (DESIGN §0 — "differs, invariant violated
→ KEEP FASTSEG'S"). One implementation, so the gate and the board can never
disagree about what the invariant is.
"""
from __future__ import annotations

import argparse
import collections
import difflib
import json
import re

# --------------------------------------------------------------------------
# Tokenisation
# --------------------------------------------------------------------------

#: Splitting the digit/letter boundary makes "3pm" and "3 pm" the same two
#: tokens. Without it a predictor that closes up a space it copied faithfully
#: gets scored for INVENTING "3pm", which is a formatting difference dressed
#: up as a contract violation. Real inventions ("19:00" for "at 7") survive
#: this normalisation untouched.
_SPLIT_DIGIT_ALPHA = re.compile(r"(?<=\d)(?=[a-z])")

#: "6:45" is ONE token — a clock time is a unit, and splitting it would let a
#: prediction of "6" score partial credit against a gold "6:45".
_TOKEN = re.compile(r"[a-z0-9]+(?::[0-9]{2})?")

#: Joiners may be dropped (SPEC, THE INVARIANT). They carry no content, so an
#: item that loses one has lost nothing; counting them would make every
#: correct split of "wash and fold the laundry" look lossy. "as well" is here
#: for the `as-well-as` trap, which is a two-word joiner.
_JOINERS = frozenset({"and", "then", "also", "plus", "as", "well"}
                     # Disfluencies are not content, so a predictor that
                     # strips "um so" from a title has not LOST anything. This
                     # set had drifted from `invariant.py`'s, and the gap was
                     # charging FastSeg 48 lost tokens for doing the right
                     # thing — the same three-copies problem the invariant had.
                     | {"um", "uh", "er", "hmm", "yeah", "yep", "okay", "ok",
                        "so", "like", "oh"})

#: The ONE token a correct answer may contain that the input does not: SPEC
#: rules that an item with no time reference of its own gets "today", and the
#: `interior-no-backscope` row ("gym session at 7, tomorrow meeting at 10" →
#: "today at 7") shows the default combining with a spoken clock time. So the
#: exemption is per-token, not per-time-string.
_DEFAULT_TIME_TOKENS = frozenset({"today"})

TAGS = ("event", "task", "review")

#: An item is matched to a gold item by token overlap on the ACTION. 0.5 is
#: Dice overlap — half the tokens shared — and it is REPORTED in the output
#: because every precision/recall number below is conditional on it.
MATCH_THRESHOLD = 0.5

#: A time that has been RESOLVED rather than captured. SPEC's "CAPTURE, DO
#: NOT RESOLVE": time holds the WORDS, never a date, a range or a clock
#: reading. This is a legibility shortcut — the no-invention check catches
#: these anyway, but "2026-09-18 is resolved, not captured" tells an
#: implementer what to fix and a bare invented-token list does not.
_RESOLVED = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}:\d{2}\s*[-–]\s*\d{1,2}:\d{2}\b")


def _norm(s) -> str:
    """Lowercase, strip punctuation, collapse whitespace — the comparison
    form. Everything that compares two phrases goes through here, so
    "At 7." and "at 7" can never be scored as a difference."""
    s = str(s or "").lower()
    s = _SPLIT_DIGIT_ALPHA.sub(" ", s)
    return " ".join(_TOKEN.findall(s))


def tokens(s) -> list:
    """Every token, joiners included — the form the no-INVENTION check uses,
    because inventing a joiner is still inventing."""
    return _norm(s).split()


def content_tokens(s) -> set:
    """Tokens that must survive — the form the no-LOSS check and the matcher
    use."""
    return {t for t in tokens(s) if t not in _JOINERS}


# --------------------------------------------------------------------------
# Item shape
# --------------------------------------------------------------------------

def as_item(raw) -> dict:
    """Coerce whatever a predictor returned into `{action, time, tag}`.

    Accepts the SPEC row shape, a 3-sequence, and the older `{text, kind}`
    naming that DESIGN §5 used before the contract was fixed — a stale
    predictor should score as WRONG on its content, not crash the board and
    look like a scorer bug.
    """
    if isinstance(raw, dict) and raw.get("malformed"):
        return raw          # idempotent: score_rows coerces before it checks,
                            # and re-coercing must not lose the diagnosis and
                            # leave three vague "empty field" messages behind
    if isinstance(raw, dict):
        action = raw.get("action", raw.get("text", ""))
        time_ = raw.get("time", raw.get("when", ""))
        tag = raw.get("tag", raw.get("kind", ""))
    elif isinstance(raw, (list, tuple)) and len(raw) == 3:
        action, time_, tag = raw
    else:
        return {"action": "", "time": "", "tag": "", "malformed": True}
    return {"action": str(action or "").strip(),
            "time": str(time_ or "").strip(),
            "tag": str(tag or "").strip().lower()}


#: Where exactly the time reference ends and the action begins is a JUDGEMENT
#: CALL, not a fact — "yoga class at late afternoon" can be cut after "class"
#: or after "late" and both readings are defensible. Exact-row treats a
#: one-token disagreement as a total loss, which is why `action+time` is its
#: single largest failure bucket (136 rows) even though the reading is nearly
#: right. So the action is ALSO compared softly, by Dice overlap on content
#: tokens, and reported beside the strict number rather than instead of it.
ACTION_SIMILAR = 0.80


def action_similarity(gold_action: str, pred_action: str) -> float:
    """Dice overlap on content tokens. 1.0 = same words, 0.0 = disjoint."""
    a, b = content_tokens(gold_action), content_tokens(pred_action)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return 2 * len(a & b) / (len(a) + len(b))


def action_boundary_only(gold: dict, pred: dict) -> bool:
    """True when the action's ONLY disagreement is where the time was cut.

    This replaced a Dice threshold, and the sweep is why. Similarity turned out
    to be the wrong AXIS: at 0.80 it admitted 140 real errors while rejecting
    85 genuine judgement calls, because the two populations overlap in Dice
    space and no threshold separates them.

        admitted at 0.80 (sim 0.82) — a whole other item swallowed:
            gold 'add water the plants to my list'
            pred 'schedule budget review and add water the plants to my list'
        rejected at 0.80 (sim 0.67) — purely a boundary judgement:
            gold 'yoga class'   pred 'yoga class at late'

    What actually distinguishes them is not HOW MUCH differs but WHAT KIND of
    token differs. The subjectivity Gil identified is specifically about where
    the time reference is removed, so the test is: every token the two actions
    disagree on must be a TIME token — and the time fields of the two items are
    exactly where those tokens are to be found. Content words in the diff mean
    a real error, however small.
    """
    ga, pa = content_tokens(gold["action"]), content_tokens(pred["action"])
    diff = ga ^ pa
    if not diff:
        return True
    return diff <= (content_tokens(gold["time"]) | content_tokens(pred["time"]))


def field_hits(gold: dict, pred: dict) -> "tuple[bool, bool, bool]":
    """(action_boundary_ok, time_exact, tag_exact) for one matched pair.

    Only the ACTION is soft, and only in the one way that is genuinely
    subjective. Time and tag stay exact on purpose: a time is a copied span
    with a right answer and a tag is one of three words, so softening either
    would only hide errors.
    """
    return (action_boundary_only(gold, pred),
            _norm(gold["time"]) == _norm(pred["time"]),
            gold["tag"] == pred["tag"])


def _triple(item: dict) -> tuple:
    return (_norm(item["action"]), _norm(item["time"]), item["tag"])


def _bag(items) -> collections.Counter:
    """A decomposition as a multiset of normalised triples. A multiset, not a
    set: two identical items is a different answer from one, and a set would
    silently forgive an over-split that duplicated a piece."""
    return collections.Counter(_triple(i) for i in items)


# --------------------------------------------------------------------------
# The invariant — metric here, runtime guard in ACCEPT
# --------------------------------------------------------------------------

def check_invariant(text: str, items, strict: bool = False) -> list:
    """Return human-readable violations of the output contract. Empty list
    means the decomposition is admissible.

    HARD violations only by default, because the ACCEPT stage uses this as a
    veto and a false veto costs a correct correction:

      * shape    — three strings, tag in event|task|review, neither empty
      * INVENTION — a token in action or time that is not in `text`
      * resolution — a time expressed as a date or a range instead of words

    `strict=True` adds a DROPPED advisory: content of the input that reached
    no item at all. It is an advisory rather than a violation on purpose —
    the `enumeration-header`, `completion-marker`, `tag-question` and
    `anaphoric-tail` traps all require dropping input words, so a gate that
    treated dropping as a violation would reject correct answers on exactly
    the shapes the corpus was hand-built to test.

    NOTE the per-item NO-LOSS check is not here and cannot be: it asks
    whether a GOLD item's content survived, and at runtime there is no gold.
    Board B scores it.
    """
    out = []
    present = set(tokens(text))
    covered = set()
    for idx, raw in enumerate(items or []):
        item = as_item(raw)
        if item.get("malformed"):
            out.append(f"item {idx}: not an (action, time, tag) — got {raw!r}")
            continue
        label = f"item {idx} [{item['action'][:40] or '<empty>'}]"
        if not item["action"]:
            out.append(f"{label}: EMPTY action — an item with no ask is not an item")
        if not item["time"]:
            out.append(f"{label}: EMPTY time — the SPEC default is the literal "
                       f"string 'today', not a blank")
        if item["tag"] not in TAGS:
            out.append(f"{label}: tag {item['tag']!r} is not one of "
                       f"{'/'.join(TAGS)}")

        resolved = bool(_RESOLVED.search(item["time"])) and not _RESOLVED.search(text)
        if resolved:
            out.append(f"{label}: time {item['time']!r} is RESOLVED, not "
                       f"captured — segment copies the words the speaker said")

        # Invention is checked over action + time. When the time was already
        # reported as resolved we skip re-listing its tokens, or one mistake
        # prints twice and the second message is the less useful one.
        suspect = tokens(item["action"]) + ([] if resolved else tokens(item["time"]))
        invented = [t for t in suspect
                    if t not in present and t not in _DEFAULT_TIME_TOKENS]
        if invented:
            out.append(f"{label}: INVENTED {sorted(set(invented))} — not in the "
                       f"input")
        covered |= content_tokens(item["action"]) | content_tokens(item["time"])

    if strict:
        dropped = sorted(content_tokens(text) - covered)
        if dropped:
            out.append(f"DROPPED (advisory) {dropped} — input content that "
                       f"reached no item")
    return out


def _invented_tokens(text: str, item: dict) -> list:
    present = set(tokens(text))
    return [t for t in tokens(item["action"]) + tokens(item["time"])
            if t not in present and t not in _DEFAULT_TIME_TOKENS]


def _lost_tokens(gold: dict, pred: dict) -> list:
    """Content of a matched gold item that reached NEITHER the predicted
    action nor its time. This is the no-loss half of the invariant, and it is
    the half that needs gold: only the label knows which words belonged to
    this item rather than to its neighbour."""
    got = content_tokens(pred["action"]) | content_tokens(pred["time"])
    want = content_tokens(gold["action"]) | content_tokens(gold["time"])
    return sorted(want - got)


# --------------------------------------------------------------------------
# Matching
# --------------------------------------------------------------------------

def _overlap(a: set, b: set) -> float:
    """Dice overlap. Symmetric on purpose: a prediction that swallowed its
    neighbour ("buy milk and call the dentist" against gold "buy milk")
    should be PENALISED for the extra content, and a containment measure
    would score it 1.0 and hide the under-split."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return 2 * len(a & b) / (len(a) + len(b))


def match_items(gold, pred, threshold: float = MATCH_THRESHOLD):
    """Greedily pair predicted items to gold items by action overlap, best
    pair first. Returns `(pairs, unmatched_gold, unmatched_pred)` where pairs
    is a list of `(gold_index, pred_index, score)`.

    Greedy-best-first rather than optimal assignment: it is deterministic,
    explainable ("this piece matched that one, at 0.75") and the difference
    from an optimal matching only shows up when two gold items are near
    duplicates — which the corpus does not contain by construction.
    """
    gtok = [content_tokens(g["action"]) for g in gold]
    ptok = [content_tokens(p["action"]) for p in pred]
    cands = []
    for gi, gt in enumerate(gtok):
        for pi, pt in enumerate(ptok):
            s = _overlap(gt, pt)
            if s < threshold:
                continue
            # difflib breaks ties on surface form, so "call the plumber" wins
            # over "call the doctor" when both share the same token score.
            tie = difflib.SequenceMatcher(
                None, _norm(gold[gi]["action"]), _norm(pred[pi]["action"])).ratio()
            cands.append((-s, -tie, gi, pi))
    cands.sort()
    used_g, used_p, pairs = set(), set(), []
    for neg_s, _tie, gi, pi in cands:
        if gi in used_g or pi in used_p:
            continue
        used_g.add(gi)
        used_p.add(pi)
        pairs.append((gi, pi, -neg_s))
    return (pairs,
            [i for i in range(len(gold)) if i not in used_g],
            [i for i in range(len(pred)) if i not in used_p])


# --------------------------------------------------------------------------
# Predictor plumbing
# --------------------------------------------------------------------------

def call_predictor(predict, text: str):
    """Run a predictor and separate its items from anything it reports about
    its own cost. Three accepted return shapes, so board E is opt-in and a
    plain predictor needs to know nothing about it:

        [item, ...]                       — no cost reported
        ([item, ...], {"calls": 1, ...})  — a TUPLE carries the meta
        {"items": [...], "calls": 1, "seconds": 0.9, "tier": "fastseg"}

    A tuple means (items, meta) and a list means items — that is the whole
    disambiguation rule, and it is why the meta form must not be a list.
    """
    out = predict(text)
    meta = {}
    if isinstance(out, dict):
        items, meta = out.get("items") or [], out
    elif isinstance(out, tuple) and len(out) == 2 and isinstance(out[1], dict):
        items, meta = out[0] or [], out[1]
    else:
        items = out or []
    return [as_item(i) for i in items], meta


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

#: No `os` / `pathlib` (allowlist), so the default is derived from __file__
#: by string surgery and there is no globbing here — the SHELL globs, which
#: is why --rows takes several paths. The corpus is written a trap-group at a
#: time by different hands, so "the corpus" is normally `data/*.jsonl` rather
#: than one file.
_HERE = __file__.rsplit("/", 1)[0] if "/" in __file__ else "."
_CANDIDATES = ("data/rows.jsonl", "rows.jsonl", "data/segment_rows.jsonl",
               "segment_rows.jsonl")


def load_rows(paths=None, split: str = None, family: str = None,
              trap: str = None) -> list:
    """Load the JSONL corpus from one path or several. Blank lines and `#`
    comment lines are skipped, so a hand-edited file with a section header
    still parses.

    Each row keeps a `_file` so a violation can be traced back to the file
    that carries it — with the corpus spread over several files written in
    parallel, "which row" is not much use without "which file".

    Filters are AND-ed. `split` is the leakage boundary: scoring the test
    half is a milestone, not the working loop, and a caller that wants it
    must ask for it by name.
    """
    if isinstance(paths, str):
        paths = [paths]
    explicit = bool(paths)
    if not explicit:
        paths = [f"{_HERE}/{c}" for c in _CANDIDATES]

    rows, tried, opened = [], [], 0
    for cand in paths:
        tried.append(cand)
        try:
            with open(cand, "r", encoding="utf-8") as fh:
                raw = fh.read()
        except OSError:
            # A named file that is missing is an error; a CANDIDATE that is
            # missing is just the next guess.
            if explicit:
                raise SystemExit(f"cannot read {cand}")
            continue
        opened += 1
        for n, line in enumerate(raw.splitlines(), start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                row = json.loads(line)
            except ValueError as exc:
                raise SystemExit(f"{cand}:{n}: not JSON — {exc}")
            row["_file"] = cand.rsplit("/", 1)[-1]
            if split and row.get("split") != split:
                continue
            if family and row.get("family") != family:
                continue
            if trap and trap not in (row.get("traps") or []):
                continue
            row["gold"] = [as_item(g) for g in (row.get("gold") or [])]
            rows.append(row)
        if not explicit:
            break               # first candidate that exists wins
    if not opened:
        raise SystemExit("no rows file found; tried:\n  " + "\n  ".join(tried)
                         + "\nPass them with --rows <file> [<file> ...] "
                           "(the shell globs: assistant/engine/segmentation/datasets/*.jsonl).")
    return rows


# --------------------------------------------------------------------------
# The boards
# --------------------------------------------------------------------------

def _why(viol, gold, pred, miss_g, miss_p) -> list:
    """One line saying what went wrong on a failing row, most diagnostic
    first. An invariant violation outranks a boundary miss because it is the
    thing that must be 0; a missing gold item outranks a spurious one because
    it is the loss the user notices."""
    if viol:
        return viol[:2]
    if miss_g:
        return [f"unmatched gold: {[gold[i]['action'] for i in miss_g]}"]
    if miss_p:
        return [f"spurious: {[pred[i]['action'] for i in miss_p]}"]
    return ["right items, wrong time or tag"]


def _prf(tp: int, n_pred: int, n_gold: int) -> tuple:
    p = tp / n_pred if n_pred else 0.0
    r = tp / n_gold if n_gold else 0.0
    f = 2 * p * r / (p + r) if (p + r) else 0.0
    return p, r, f


def score_rows(rows, predict, fastseg=None, samples: int = 10) -> dict:
    """Score `predict` over `rows`, optionally with board D.

    `predict(text)` returns the items (see `call_predictor` for the accepted
    shapes). `fastseg(text)`, when given, is the DETERMINISTIC answer that
    `predict` is allowed to overrule — supplying both is what turns board D
    on, because correction recall and precision are undefined without a
    before and an after.

    `samples=0` suppresses the failing-row appendix. Pass it when scoring a
    held-out split: aggregates travel, rows do not.
    """
    rows = [r for r in rows if r.get("gold")]
    n_rows = len(rows)

    # A — boundaries
    exact_set = exact_row = count_right = 0
    tp = n_pred = n_gold = 0
    over_rows = under_rows = over_items = under_items = 0
    # B — action/time
    inv_items = inv_tokens = inv_rows = 0
    loss_items = loss_tokens = loss_rows = 0
    shape_viol = shape_rows = empty_time = 0
    matched = time_exact = time_bag = 0
    # 2-of-3 partial credit, plus WHICH field is the one being missed. The
    # breakdown is not decoration: "2 of 3" can be passed by failing the SAME
    # field on every item, so a system that never extracts a time at all could
    # score well on it. Reporting the missed field makes that visible.
    soft2 = soft3 = 0
    miss_field = collections.Counter()
    soft_rows = 0
    t_def_n = t_def_ok = t_spoken_n = t_spoken_ok = 0
    # C — tag
    tag_n = tag_ok = 0
    confusion = collections.defaultdict(collections.Counter)
    # E — cost
    cost_rows = cost_calls = 0
    cost_secs = []
    tiers = collections.Counter()
    # F — composition
    counts = collections.Counter()
    by_count = collections.Counter()
    # [rows, exact, seconds] — latency is carried per trap so board F can show
    # which SHAPES are expensive, not just the corpus average.
    by_trap = collections.defaultdict(lambda: [0, 0, 0.0])
    # D — verifier
    fs_wrong = fs_fixed = fs_unchanged_wrong = 0
    changed = improved = broke = neutral = 0
    fails = []

    for row in rows:
        text, gold = row["text"], row["gold"]
        pred, meta = call_predictor(predict, text)

        # ---- A
        n_gold += len(gold)
        n_pred += len(pred)
        if len(pred) > len(gold):
            over_rows += 1
            over_items += len(pred) - len(gold)
        elif len(pred) < len(gold):
            under_rows += 1
            under_items += len(gold) - len(pred)
        else:
            count_right += 1
        set_ok = (collections.Counter(_norm(g["action"]) for g in gold)
                  == collections.Counter(_norm(p["action"]) for p in pred))
        row_ok = _bag(gold) == _bag(pred)
        exact_set += set_ok
        exact_row += row_ok

        pairs, miss_g, miss_p = match_items(gold, pred)
        tp += len(pairs)

        # ---- B (the invariant is per PREDICTED item; loss needs the pair)
        viol = check_invariant(text, pred)
        if viol:
            shape_viol += sum(1 for v in viol if "INVENTED" not in v)
            shape_rows += 1
        row_inv = row_loss = 0
        for p in pred:
            if not p["time"]:
                empty_time += 1
            bad = _invented_tokens(text, p)
            if bad:
                inv_items += 1
                inv_tokens += len(bad)
                row_inv += 1
        row_soft: list = []
        for gi, pi, _s in pairs:
            g, p = gold[gi], pred[pi]
            lost = _lost_tokens(g, p)
            if lost:
                loss_items += 1
                loss_tokens += len(lost)
                row_loss += 1
            matched += 1
            gtime, ptime = _norm(g["time"]), _norm(p["time"])
            hit = gtime == ptime
            time_exact += hit
            # Same tokens in another order is a weaker pass, reported apart:
            # a copied edge word can land either side of a clock time
            # ("tomorrow at 7" / "at 7 tomorrow") without being a defect.
            time_bag += (set(gtime.split()) == set(ptime.split()))
            if gtime in ("today", ""):
                t_def_n += 1
                t_def_ok += hit
            else:
                t_spoken_n += 1
                t_spoken_ok += hit
            # ---- C
            tag_n += 1
            tag_ok += (g["tag"] == p["tag"])
            confusion[g["tag"]][p["tag"] or "<empty>"] += 1
            # ---- A2 partial credit
            ha, ht, hg = field_hits(g, p)
            nhits = ha + ht + hg
            soft3 += (nhits == 3)
            soft2 += (nhits >= 2)
            if nhits == 2:
                miss_field["action" if not ha else "time" if not ht else "tag"] += 1
            elif nhits < 2:
                miss_field["two or more"] += 1
            row_soft.append(nhits >= 2)
        inv_rows += bool(row_inv)
        loss_rows += bool(row_loss)
        # A ROW passes 2-of-3 only if the CUT is right and every item passes —
        # partial credit on fields, none on boundaries.
        soft_rows += bool(row_soft) and all(row_soft) and not miss_g and not miss_p

        # ---- E
        if "calls" in meta or "seconds" in meta:
            cost_rows += 1
            cost_calls += int(meta.get("calls") or 0)
            if meta.get("seconds") is not None:
                cost_secs.append(float(meta["seconds"]))
        if meta.get("tier"):
            tiers[str(meta["tier"])] += 1

        # ---- F
        key = len(gold) if len(gold) < 4 else 4
        counts[key] += 1
        by_count[key] += row_ok
        for tr in (row.get("traps") or ["(none)"]):
            by_trap[tr][0] += 1
            by_trap[tr][1] += row_ok
            by_trap[tr][2] += meta.get("seconds") or 0.0

        # ---- D
        if fastseg is not None:
            fs, _fmeta = call_predictor(fastseg, text)
            fs_ok = _bag(gold) == _bag(fs)
            same = _bag(fs) == _bag(pred)
            if not fs_ok:
                fs_wrong += 1
                fs_fixed += row_ok
                fs_unchanged_wrong += same
            if not same:
                changed += 1
                if row_ok and not fs_ok:
                    improved += 1
                elif fs_ok and not row_ok:
                    broke += 1
                else:
                    neutral += 1

        if samples and not row_ok and len(fails) < samples:
            fails.append({
                "id": row.get("id", "?"), "text": text,
                "traps": row.get("traps") or [],
                "gold": [(g["action"], g["time"], g["tag"]) for g in gold],
                "pred": [(p["action"], p["time"], p["tag"]) for p in pred],
                "why": _why(viol, gold, pred, miss_g, miss_p),
            })

    p, r, f1 = _prf(tp, n_pred, n_gold)
    result = {
        "n_rows": n_rows,
        "match_threshold": MATCH_THRESHOLD,
        "boundaries": {
            "exact_set": exact_set, "exact_row": exact_row,
            "count_right": count_right,
            "tp": tp, "n_pred": n_pred, "n_gold": n_gold,
            "precision": p, "recall": r, "f1": f1,
            "over_rows": over_rows, "over_items": over_items,
            "under_rows": under_rows, "under_items": under_items,
        },
        "action_time": {
            "matched": matched,
            "soft2": soft2, "soft3": soft3, "soft_rows": soft_rows,
            "miss_field": dict(miss_field),
            "action_similar_threshold": ACTION_SIMILAR,
            "invention_items": inv_items, "invention_tokens": inv_tokens,
            "invention_rows": inv_rows,
            "loss_items": loss_items, "loss_tokens": loss_tokens,
            "loss_rows": loss_rows,
            "shape_violations": shape_viol, "shape_rows": shape_rows,
            "empty_time": empty_time,
            "time_exact": time_exact, "time_tokenset": time_bag,
            "time_default_n": t_def_n, "time_default_ok": t_def_ok,
            "time_spoken_n": t_spoken_n, "time_spoken_ok": t_spoken_ok,
        },
        "tag": {
            "n": tag_n, "correct": tag_ok,
            "confusion": {g: dict(c) for g, c in confusion.items()},
            "per_class": {},
        },
        "verifier": None,
        "cost": {
            "rows_reporting": cost_rows, "calls": cost_calls,
            "calls_per_row": (cost_calls / cost_rows) if cost_rows else None,
            "seconds": sum(cost_secs) if cost_secs else None,
            "seconds_per_row": (sum(cost_secs) / len(cost_secs))
                               if cost_secs else None,
            "seconds_max": max(cost_secs) if cost_secs else None,
            "tiers": dict(tiers),
        },
        "composition": {
            "counts": {str(k) if k < 4 else "4+": v
                       for k, v in sorted(counts.items())},
            "exact_by_count": {str(k) if k < 4 else "4+": (by_count[k], counts[k])
                               for k in sorted(counts)},
            "traps": {k: {"n": v[0], "exact": v[1],
                          "seconds": v[2] if v[2] else None}
                      for k, v in sorted(by_trap.items(),
                                         key=lambda kv: -kv[1][0])},
        },
        "failures": fails,
    }

    # per-class P/R/F1 over MATCHED items — an unmatched item has no gold tag
    # to be right or wrong about, so folding it in here would mix a boundary
    # error into the tag board and make both unreadable.
    seen = set(confusion) | {p for c in confusion.values() for p in c}
    for tag in sorted(seen):
        c_tp = confusion.get(tag, {}).get(tag, 0)
        c_fp = sum(c.get(tag, 0) for g, c in confusion.items() if g != tag)
        c_fn = sum(v for k, v in confusion.get(tag, {}).items() if k != tag)
        cp, cr, cf = _prf(c_tp, c_tp + c_fp, c_tp + c_fn)
        result["tag"]["per_class"][tag] = {
            "support": c_tp + c_fn, "precision": cp, "recall": cr, "f1": cf}

    if fastseg is not None:
        result["verifier"] = {
            "fastseg_wrong": fs_wrong, "fixed": fs_fixed,
            "correction_recall": (fs_fixed / fs_wrong) if fs_wrong else None,
            "unchanged_on_wrong": fs_unchanged_wrong,
            "unchanged_rate": (fs_unchanged_wrong / fs_wrong) if fs_wrong else None,
            "changed": changed, "improved": improved, "broke": broke,
            "neutral": neutral,
            "correction_precision": (improved / changed) if changed else None,
            "net": improved - broke,
        }
    return result


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def _pc(x, n) -> str:
    return f"{x / n:6.1%}" if n else "     —"


def format_board(result: dict) -> str:
    """The six boards as one printable report. Every rate carries its
    denominator, because a percentage without an n is the thing this project
    keeps banning."""
    b = result["boundaries"]
    a = result["action_time"]
    t = result["tag"]
    c = result["cost"]
    comp = result["composition"]
    n = result["n_rows"]
    L = []
    add = L.append

    add(f"segment board — {n} rows, "
        f"{b['n_gold']} gold items, {b['n_pred']} predicted items")
    add(f"(items matched by action token-overlap ≥ "
        f"{result['match_threshold']:.2f}, Dice)")

    add("\nA · BOUNDARIES — did we cut in the right places")
    add(f"   exact-set match (actions)  {_pc(b['exact_set'], n)}  "
        f"({b['exact_set']}/{n})   <- the headline")
    add(f"   exact-row (action+time+tag){_pc(b['exact_row'], n)}  "
        f"({b['exact_row']}/{n})")
    add(f"   right ITEM COUNT           {_pc(b['count_right'], n)}  "
        f"({b['count_right']}/{n})   <- the CUT alone")
    # A gold action is "the item's words with the TIME REFERENCE REMOVED"
    # (SPEC), so exact-set demands the cut AND the lift. Said out loud
    # because the two lines above differ by a lot for anything that leaves
    # the time inside the action, and that gap is a diagnosis, not noise.
    add("   (exact-set needs the time lifted OUT of the action too; the "
        "count line is the cut on its own)")
    add(f"   item precision             {b['precision']:6.1%}  "
        f"({b['tp']}/{b['n_pred']})")
    add(f"   item recall                {b['recall']:6.1%}  "
        f"({b['tp']}/{b['n_gold']})")
    add(f"   item F1                    {b['f1']:6.1%}")
    add(f"   OVER-split                 {b['over_rows']} rows "
        f"(+{b['over_items']} items)   <- garbage immediately")
    add(f"   UNDER-split                {b['under_rows']} rows "
        f"(-{b['under_items']} items)   <- two more chances downstream")
    add("   (never summed: the two failures do not cost the same)")

    add("\nA2 · PARTIAL CREDIT — 2 of 3 fields, action compared SOFTLY")
    add("   (action counts as correct when the ONLY tokens it disagrees on are "
        "TIME tokens —")
    add("    i.e. the two readings differ just in where the time was cut; "
        "time and tag stay EXACT)")
    add(f"   items all 3 fields right    {_pc(a['soft3'], a['matched'])}"
        f"  ({a['soft3']}/{a['matched']} matched items)")
    add(f"   items >= 2 of 3 right       {_pc(a['soft2'], a['matched'])}"
        f"  ({a['soft2']}/{a['matched']})")
    add(f"   ROWS: right cut AND every item >= 2 of 3   "
        f"{_pc(a['soft_rows'], result['n_rows'])}")
    if a["miss_field"]:
        add("   which field is being missed (the 2-of-3 passes):")
        for k, v in sorted(a["miss_field"].items(), key=lambda kv: -kv[1]):
            add(f"      {k:<14} {v}")
        add("   ^ if ONE field dominates here, 2-of-3 is being passed by "
            "failing that field every time — read it, do not just take the rate")

    add("\nB · ACTION/TIME — the invariant, and where the time landed")
    add(f"   NO-INVENTION violations    {a['invention_items']} items "
        f"({a['invention_tokens']} tokens, {a['invention_rows']} rows)"
        f"   {'MUST BE 0' if a['invention_items'] else 'ok'}")
    add(f"   NO-LOSS violations         {a['loss_items']} items "
        f"({a['loss_tokens']} tokens, {a['loss_rows']} rows)"
        f"   {'MUST BE 0' if a['loss_items'] else 'ok'}")
    if a["shape_violations"] or a["empty_time"]:
        add(f"   shape violations           {a['shape_violations']} "
            f"(empty time on {a['empty_time']} items — the default is the "
            f"word 'today')")
    add(f"   time-assignment accuracy   {_pc(a['time_exact'], a['matched'])}  "
        f"({a['time_exact']}/{a['matched']} matched items)")
    add(f"     same tokens, any order   {_pc(a['time_tokenset'], a['matched'])}"
        f"  (a copied edge word may land either side)")
    add(f"     on DEFAULT 'today'       {_pc(a['time_default_ok'], a['time_default_n'])}"
        f"  (n={a['time_default_n']})")
    add(f"     on a SPOKEN time         {_pc(a['time_spoken_ok'], a['time_spoken_n'])}"
        f"  (n={a['time_spoken_n']})  <- the one that cannot be guessed")

    add("\nC · TAG — event | task | review")
    add(f"   accuracy                   {_pc(t['correct'], t['n'])}  "
        f"({t['correct']}/{t['n']} matched items)")
    for tag, m in t["per_class"].items():
        add(f"   {tag:<12} P {m['precision']:6.1%}  R {m['recall']:6.1%}  "
            f"F1 {m['f1']:6.1%}   (support {m['support']})")
    if t["confusion"]:
        cols = sorted({p for row in t["confusion"].values() for p in row})
        add("   confusion (gold ↓ / predicted →)")
        add("        " + "".join(f"{c:>10}" for c in cols))
        for g in sorted(t["confusion"]):
            add(f"   {g:<5}" + "".join(f"{t['confusion'][g].get(c, 0):>10}"
                                       for c in cols))

    add("\nD · VERIFIER — does the correction pay for itself")
    v = result["verifier"]
    if not v:
        add("   not run (needs BOTH a fastseg and a final prediction)")
    else:
        add(f"   fastseg wrong on           {v['fastseg_wrong']} rows")
        add(f"   correction RECALL          "
            f"{_pc(v['fixed'], v['fastseg_wrong'])}  "
            f"({v['fixed']}/{v['fastseg_wrong']} fixed)")
        add(f"   correction PRECISION       "
            f"{_pc(v['improved'], v['changed'])}  "
            f"({v['improved']}/{v['changed']} changed rows improved)")
        add(f"     improved {v['improved']} · BROKE {v['broke']} · "
            f"still wrong {v['neutral']}   net {v['net']:+d}")
        add(f"   left fastseg's answer on a known-wrong row  "
            f"{_pc(v['unchanged_on_wrong'], v['fastseg_wrong'])}  "
            f"({v['unchanged_on_wrong']}/{v['fastseg_wrong']})")
        add("   (net ≤ 0 means the verifier is not worth its latency — "
            "correct answers vastly outnumber wrong ones)")

    add("\nE · COST")
    if not c["rows_reporting"]:
        add("   not reported by the predictor")
    else:
        add(f"   model calls / row          {c['calls_per_row']:.2f}  "
            f"({c['calls']} calls over {c['rows_reporting']} rows)")
        if c["seconds"] is not None:
            add(f"   wall clock / row           {c['seconds_per_row']:.2f}s  "
                f"(total {c['seconds']:.1f}s, max {c['seconds_max']:.2f}s)")
        if c["tiers"]:
            add("   decided by                 " + " · ".join(
                f"{k} {v}" for k, v in sorted(c["tiers"].items())))

    add("\nF · COMPOSITION — what the numbers above were computed OVER")
    add("   gold-count distribution (asks per row)")
    for k, v in comp["counts"].items():
        ok, tot = comp["exact_by_count"][k]
        add(f"      {k:<3} ask   {v:>4} rows ({v / n:5.1%})   "
            f"exact-row {_pc(ok, tot)}")
    add("   by trap")
    for trap, m in comp["traps"].items():
        line = (f"      {trap:<32} n={m['n']:<5} exact-row "
                f"{_pc(m['exact'], m['n'])}")
        # Latency per trap, when the predictor reported it: a shape that is
        # both wrong AND slow is a different problem from one that is merely
        # wrong, and the averages hide which is which.
        if m.get("seconds") is not None and m["n"]:
            line += f"   {m['seconds'] / m['n'] * 1000:7.0f}ms"
        add(line)

    if result.get("failures"):
        add("\n--- reading the failures (not a board; a pointer) ---")
        for f in result["failures"]:
            add(f"   [{f['id']}] {f['text']}")
            add(f"      traps {f['traps']}")
            add(f"      gold  {f['gold']}")
            add(f"      pred  {f['pred']}")
            add(f"      why   {f['why']}")
    return "\n".join(L)


# --------------------------------------------------------------------------
# Self-test — running this file proves the scorer works
# --------------------------------------------------------------------------

#: Seven rows covering the trap classes the boards must be able to see: an
#: edge date that distributes, a trailing deadline, an interior reference
#: that must NOT reach back, a must-not-split name coordination, a mixed-kind
#: pair, a three-ask comma list, and a review. Inline rather than loaded, so
#: the self-test still runs before the corpus file exists.
_SELF_ROWS = [
    {"id": "st-01", "text": "tomorrow gym at 7 and meeting at 11",
     "family": "shared-date-leading-edge", "traps": ["shared-date-leading-edge"],
     "gold": [{"action": "gym", "time": "tomorrow at 7", "tag": "event"},
              {"action": "meeting", "time": "tomorrow at 11", "tag": "event"}]},
    {"id": "st-02", "text": "submit the grades and prepare the slides by friday",
     "family": "shared-deadline-trailing-edge",
     "traps": ["shared-deadline-trailing-edge"],
     "gold": [{"action": "submit the grades", "time": "by friday", "tag": "task"},
              {"action": "prepare the slides", "time": "by friday", "tag": "task"}]},
    {"id": "st-03", "text": "gym session at 7, tomorrow meeting at 10",
     "family": "interior-no-backscope", "traps": ["interior-no-backscope"],
     "gold": [{"action": "gym session", "time": "today at 7", "tag": "event"},
              {"action": "meeting", "time": "tomorrow at 10", "tag": "event"}]},
    {"id": "st-04", "text": "meeting with sam and alex at 8",
     "family": "name-coordination", "traps": ["name-coordination"],
     "gold": [{"action": "meeting with sam and alex", "time": "at 8",
               "tag": "event"}]},
    {"id": "st-05",
     "text": "add dentist tomorrow at 3 and put milk on the shopping list",
     "family": "mixed-kind", "traps": ["mixed-kind"],
     "gold": [{"action": "add dentist", "time": "tomorrow at 3", "tag": "event"},
              {"action": "put milk on the shopping list", "time": "today",
               "tag": "task"}]},
    {"id": "st-06", "text": "add gym tomorrow, buy milk, and call the dentist",
     "family": "comma-list", "traps": ["comma-list", "interior-no-backscope"],
     "gold": [{"action": "add gym", "time": "tomorrow", "tag": "event"},
              {"action": "buy milk", "time": "today", "tag": "task"},
              {"action": "call the dentist", "time": "today", "tag": "task"}]},
    {"id": "st-07", "text": "whats on my calendar tomorrow",
     "family": "review", "traps": ["review"],
     "gold": [{"action": "whats on my calendar", "time": "tomorrow",
               "tag": "review"}]},
]

_BY_TEXT = {r["text"]: r["gold"] for r in _SELF_ROWS}


def _perfect(text):
    return [dict(g) for g in _BY_TEXT[text]]


#: Each deviation below is a DIFFERENT board's failure, so a green self-test
#: proves each board can actually see its own defect rather than that the
#: totals happen to add up.
_SLOPPY = {
    # dropped the distributed edge date -> NO-LOSS on item 2
    "tomorrow gym at 7 and meeting at 11": [
        {"action": "gym", "time": "tomorrow at 7", "tag": "event"},
        {"action": "meeting", "time": "at 11", "tag": "event"}],
    # dropped the default -> NO-LOSS on item 1
    "gym session at 7, tomorrow meeting at 10": [
        {"action": "gym session", "time": "at 7", "tag": "event"},
        {"action": "meeting", "time": "tomorrow at 10", "tag": "event"}],
    # split two people into two asks -> OVER-split
    "meeting with sam and alex at 8": [
        {"action": "meeting with sam", "time": "at 8", "tag": "event"},
        {"action": "alex", "time": "at 8", "tag": "event"}],
    # resolved the clock -> INVENTION
    "add dentist tomorrow at 3 and put milk on the shopping list": [
        {"action": "add dentist", "time": "15:00", "tag": "event"},
        {"action": "put milk on the shopping list", "time": "today",
         "tag": "task"}],
    # swallowed the third ask -> UNDER-split
    "add gym tomorrow, buy milk, and call the dentist": [
        {"action": "add gym", "time": "tomorrow", "tag": "event"},
        {"action": "buy milk and call the dentist", "time": "today",
         "tag": "task"}],
    # a query booked as an appointment -> TAG error
    "whats on my calendar tomorrow": [
        {"action": "whats on my calendar", "time": "tomorrow", "tag": "event"}],
}


def _sloppy(text):
    return [dict(i) for i in _SLOPPY.get(text, _BY_TEXT[text])]


def _selftest() -> int:
    fails = []

    def want(label, got, exp):
        if got != exp:
            fails.append(f"{label}: got {got!r}, expected {exp!r}")

    # --- the invariant helper, on its own
    want("invariant/clean",
         check_invariant("tomorrow gym at 7",
                         [{"action": "gym", "time": "tomorrow at 7",
                           "tag": "event"}]), [])
    want("invariant/default-today",
         check_invariant("buy milk",
                         [{"action": "buy milk", "time": "today",
                           "tag": "task"}]), [])
    want("invariant/invention",
         len(check_invariant("buy milk",
                             [{"action": "buy bread", "time": "today",
                               "tag": "task"}])), 1)
    want("invariant/resolved",
         len(check_invariant("gym at 7",
                             [{"action": "gym", "time": "2026-09-18",
                               "tag": "event"}])), 1)
    want("invariant/bad-tag",
         len(check_invariant("gym at 7", [{"action": "gym", "time": "at 7",
                                           "tag": "appointment"}])), 1)
    want("invariant/malformed",
         len(check_invariant("buy milk", ["just a string"])), 1)
    want("invariant/malformed-survives-coercion",
         len(check_invariant("buy milk", [as_item("just a string")])), 1)
    # the advisory is OFF by default — the enumeration-header trap drops words
    hdr = "two tasks due tomorrow buy groceries and return the book"
    items = [{"action": "buy groceries", "time": "tomorrow", "tag": "task"},
             {"action": "return the book", "time": "tomorrow", "tag": "task"}]
    want("invariant/drop-not-a-violation", check_invariant(hdr, items), [])
    want("invariant/drop-visible-in-strict",
         len(check_invariant(hdr, items, strict=True)), 1)

    # --- the matcher
    pairs, mg, mp = match_items(
        [{"action": "buy milk"}, {"action": "call the dentist"}],
        [{"action": "buy milk and call the dentist"}])
    want("match/greedy-best-first", [(g, p) for g, p, _ in pairs], [(1, 0)])
    want("match/unmatched-gold", mg, [0])
    want("match/unmatched-pred", mp, [])

    # --- a perfect predictor scores perfectly, on every board
    good = score_rows(_SELF_ROWS, _perfect)
    want("perfect/exact-row", good["boundaries"]["exact_row"], 7)
    want("perfect/f1", round(good["boundaries"]["f1"], 6), 1.0)
    want("perfect/invention", good["action_time"]["invention_items"], 0)
    want("perfect/loss", good["action_time"]["loss_items"], 0)
    want("perfect/time", good["action_time"]["time_exact"],
         good["action_time"]["matched"])
    want("perfect/tag", good["tag"]["correct"], good["tag"]["n"])
    want("perfect/over", good["boundaries"]["over_rows"], 0)
    want("perfect/under", good["boundaries"]["under_rows"], 0)
    want("perfect/composition",
         good["composition"]["counts"], {"1": 2, "2": 4, "3": 1})

    # --- and every planted defect shows up on ITS OWN board
    bad = score_rows(_SELF_ROWS, _sloppy)
    want("sloppy/exact-row", bad["boundaries"]["exact_row"], 1)   # only st-02
    want("sloppy/over-rows", bad["boundaries"]["over_rows"], 1)   # st-04
    want("sloppy/under-rows", bad["boundaries"]["under_rows"], 1)  # st-06
    want("sloppy/invention-items", bad["action_time"]["invention_items"], 1)
    want("sloppy/tag-errors",
         bad["tag"]["n"] - bad["tag"]["correct"], 1)
    want("sloppy/tp", bad["boundaries"]["tp"], 12)
    want("sloppy/n-pred", bad["boundaries"]["n_pred"], 13)
    want("sloppy/n-gold", bad["boundaries"]["n_gold"], 13)
    # FOUR loss items, not two, and the extra two are the point: an
    # over-split loses the content it left behind (st-04 drops "alex" from
    # the item it matched), and a RESOLVED time loses the words it replaced
    # (st-05 drops "tomorrow at 3" for "15:00"). A resolved time therefore
    # scores on BOTH board-B lines — it invented one token and lost three —
    # which is the honest reading, not a double count.
    want("sloppy/loss-items", bad["action_time"]["loss_items"], 4)
    want("sloppy/loss-tokens", bad["action_time"]["loss_tokens"], 6)

    # --- board D: fastseg wrong on 2 rows; the final fixes one, leaves one
    # untouched, and BREAKS a row that was already right.
    def _fastseg(text):
        out = dict(_BY_TEXT)
        out["meeting with sam and alex at 8"] = _SLOPPY[
            "meeting with sam and alex at 8"]
        out["add gym tomorrow, buy milk, and call the dentist"] = _SLOPPY[
            "add gym tomorrow, buy milk, and call the dentist"]
        return ([dict(i) for i in out[text]], {"calls": 0, "tier": "fastseg"})

    def _final(text):
        out = dict(_BY_TEXT)
        out["add gym tomorrow, buy milk, and call the dentist"] = _SLOPPY[
            "add gym tomorrow, buy milk, and call the dentist"]
        out["submit the grades and prepare the slides by friday"] = [
            {"action": "submit the grades", "time": "by friday", "tag": "task"},
            {"action": "prepare", "time": "by friday", "tag": "task"},
            {"action": "the slides", "time": "by friday", "tag": "task"}]
        return {"items": [dict(i) for i in out[text]], "calls": 1,
                "seconds": 0.9, "tier": "llmseg"}

    two_pass = score_rows(_SELF_ROWS, _final, fastseg=_fastseg, samples=0)
    ver = two_pass["verifier"]
    want("verifier/fastseg-wrong", ver["fastseg_wrong"], 2)
    want("verifier/recall", ver["correction_recall"], 0.5)
    want("verifier/changed", ver["changed"], 2)
    want("verifier/precision", ver["correction_precision"], 0.5)
    want("verifier/broke", ver["broke"], 1)
    want("verifier/net", ver["net"], 0)
    want("verifier/unchanged-on-wrong", ver["unchanged_rate"], 0.5)

    cost = score_rows(_SELF_ROWS, _final)["cost"]
    want("cost/calls-per-row", cost["calls_per_row"], 1.0)
    want("cost/seconds-per-row", round(cost["seconds_per_row"], 2), 0.9)

    # Two reports, because one predictor cannot exercise all six boards: the
    # first has the boundary/invariant/tag defects, the second is the only
    # one that can populate D and E.
    print("### one-pass predictor with planted defects — boards A B C F\n")
    print(format_board(bad))
    print("\n\n### fastseg + verifier — boards D and E\n")
    print(format_board(two_pass))
    print("\n" + "=" * 72)
    if fails:
        print(f"SELF-TEST FAILED — {len(fails)} check(s):")
        for f in fails:
            print(f"   {f}")
        return 1
    print("self-test PASSED — every board sees its own defect "
          "(7 inline rows, planted errors, expected values asserted)")
    return 0


def _audit(rows) -> int:
    """Audit the GOLD labels against the invariant. SPEC: 'a row violating it
    is a bug' — so this runs over the labels themselves, with no predictor in
    sight, and is the cheapest way to catch a labelling slip before a number
    is computed on top of it."""
    bad = 0
    for row in rows:
        viol = check_invariant(row["text"], row["gold"])
        if not row.get("gold"):
            viol = viol + ["no gold items — the row scores nothing"]
        if viol:
            bad += 1
            print(f"[{row.get('id', '?')} · {row.get('_file', '?')}] {row['text']}")
            for v in viol:
                print(f"     {v}")
    # Duplicate ids matter more than they look: the corpus is written a file
    # at a time by different hands, and two rows sharing an id make a
    # per-row failure impossible to point at.
    dup = [i for i, n in collections.Counter(
        r.get("id") for r in rows).items() if n > 1]
    counts = collections.Counter(len(r["gold"]) for r in rows)
    disputed = sum(1 for r in rows if r.get("disputed"))
    traps = collections.Counter(t for r in rows for t in (r.get("traps") or []))
    files = collections.Counter(r.get("_file", "?") for r in rows)
    print(f"\n{len(rows)} rows · {sum(len(r['gold']) for r in rows)} gold items"
          f" · {len(files)} file(s)")
    for f, v in sorted(files.items()):
        print(f"   {v:>5}  {f}")
    print("gold-count distribution: " + " · ".join(
        f"{k if k < 4 else '4+'} ask ×{v}" for k, v in sorted(counts.items())))
    print(f"traps covered: {len(traps)}  ·  disputed rows: {disputed}")
    if dup:
        print(f"DUPLICATE IDS: {len(dup)}  {sorted(dup)[:6]}")
    print(f"INVARIANT VIOLATIONS IN THE GOLD: {bad}"
          + ("   <- these are labelling bugs" if bad else "   (clean)"))
    return 1 if (bad or dup) else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--rows", nargs="+",
                    help="JSONL corpus file(s); audits the gold labels. "
                         "The shell globs: assistant/engine/segmentation/datasets/*.jsonl")
    ap.add_argument("--split", choices=("train", "test"))
    ap.add_argument("--family")
    ap.add_argument("--trap")
    a = ap.parse_args(argv)
    if not a.rows and not (a.split or a.family or a.trap):
        return _selftest()
    return _audit(load_rows(a.rows, split=a.split, family=a.family,
                            trap=a.trap))


if __name__ == "__main__":
    raise SystemExit(main())
