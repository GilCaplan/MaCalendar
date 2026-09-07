#!/usr/bin/env python3
"""Generate the FastRule 6,000-row eval/train dataset from pattern + filler
banks under dataset/fastrule/banks/.

WHY a generator instead of 6000 hand-written rows: the banks are the
authored artifact (pattern SKELETONS + generic slot fillers); this script
deterministically expands them into concrete rows and assigns ground truth
BY CONSTRUCTION — it knows exactly which filler it dropped into which slot,
so no row needs human labelling. That includes label-level ground truth
(event `category`, task `tags`): each family declares which of its title
slots are real CREATED events/tasks (excluding delete/update/query/complete
targets), and this script classifies those titles by calling the actual
`assistant.actions.calendar.categories.classify()` /
`assistant.actions.todo.tagging` scoring functions against this dataset's
own frozen `banks/categories_fixture.json` — see `setup_label_env()`.

Determinism: a fixed SEED plus the banks' on-disk content are the only
inputs (no network, no wall-clock, no dict-iteration-order dependence —
every RNG stream is reseeded from a stable string key). Regenerating
reproduces the previous fastrule_6000.jsonl byte-for-byte. Stable ids are
"<family>-<counter>", counter local to that family's rows in the order
generated.

Usage:
    python -m scripts.gen_fastrule_dataset            # generate + verify
    python -m scripts.gen_fastrule_dataset --no-write  # verify-only dry run

See dataset/fastrule/DATASET.md for the schema and design rationale, and
dataset/fastrule/SPLIT.md for how the 80/20 train/test split is built and
why TEST ROWS MUST NEVER BE MINED (Gil's ruling — see that file).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANKS = ROOT / "dataset" / "fastrule" / "banks"
OUT = ROOT / "dataset" / "fastrule" / "fastrule_6000.jsonl"
CATEGORIES_FIXTURE = BANKS / "categories_fixture.json"

# Changing SEED changes every row's fillers and the split assignment — only
# do it deliberately, and note the regen in SPLIT.md / DATASET.md.
SEED = "fastrule-6000-v1"

SIMPLE_TOTAL = 2000
COMPLEX_TOTAL = 4000
TRAIN_FRAC = 0.8

# action -> (atomic, events, tasks) for SIMPLE-tier families, which are
# single-intent by construction so this is fully determined by the action.
# COMPLEX-tier families state atomic/events/tasks explicitly in their bank
# entry instead (compounds vary too much to default).
ACTION_DEFAULTS = {
    "create_event": (True, 1, 0),
    "create_todo": (True, 0, 1),
    "query": (True, 0, 0),
    "delete_event": (True, 0, 0),
    "delete_todo": (True, 0, 0),
    "complete_todo": (True, 0, 0),
    "update_event": (True, 0, 0),
    "update_todo": (True, 0, 0),
}
ALL_ACTIONS = set(ACTION_DEFAULTS) | {"mixed", "propose"}   # propose: Q9 - a question proposes, user confirms

# placeholder base name -> (filler bank key, semantic slot key | None).
# None means the placeholder is cosmetic text only (not ground truth).
# A placeholder like "{event_title2}" reuses the "event_title" base bank
# and writes to "title_2" instead of "title" — see _placeholder_info().
BASE_INFO = {
    "event_title": ("event_titles", "title"),
    "task_title": ("task_titles", "title"),
    "item": ("items", "title"),
    "qty": ("quantities", "quantity"),
    "date": ("dates", "date_phrase"),
    "time": ("times", "time_phrase"),
    "time_range": ("time_ranges", "time_phrase"),
    "recurrence": ("recurrences", "recurrence"),
    "name": ("names", "attendee"),
    "occasion": ("occasions", "title"),
    "lead_time": ("lead_times", "lead_time"),
    "duration": ("durations", "duration"),
    "quoted_item": ("quotable", "title"),
    "generic_target": ("generic_targets", "title"),
    "query_range": ("query_ranges", "date_phrase"),
    "filler": ("filler_words", None),
}

# Recurrence must round to daily/weekly/monthly (CLAUDE.md convention).
# recurrence_rounded records what the engine's output SHOULD be; the raw
# `recurrence` slot keeps exactly what the speaker said.
RECURRENCE_ROUND = {
    "every day": "daily", "daily": "daily",
    "every week": "weekly", "weekly": "weekly", "every monday": "weekly",
    "every tuesday and thursday": "weekly", "every other week": "weekly",
    "every other tuesday": "weekly", "every weekday": "weekly",
    "every weekend": "weekly", "once a week": "weekly",
    "twice a week": "weekly", "every sunday": "weekly",
    "monthly": "monthly", "every month": "monthly",
}

TOKEN_RE = re.compile(r"\{(\w+)\}")
TITLE_KEY_RE = re.compile(r"^title(_(\d+))?$")
_WORD_CLEAN_RE = re.compile(r"[^\w\s'-]")


def load_json(name: str):
    with open(BANKS / name, encoding="utf-8") as f:
        return json.load(f)


def setup_label_env():
    """Category/tag ground truth is computed by calling the REAL
    assistant.actions.calendar.categories.classify() and
    assistant.actions.todo.tagging._score() against this dataset's own
    frozen banks/categories_fixture.json — not a reimplementation of their
    scoring math, so the ground truth can never subtly drift from what the
    product actually does. `categories.classify()` reads its keyword scheme
    from CATEGORIES_PATH (env MACALENDAR_CATEGORIES), so pointing that at
    the fixture is exactly the mechanism a real scoring run would use too
    (see DATASET.md). `tagging.py` has no equivalent file-based override —
    its KEYWORDS is a hardcoded module dict — so the fixture's `task_tags`
    section is a dataset-only companion, consumed only by this script.

    Per CLAUDE.md, every store honours an environment override; all of them
    are pointed at a throwaway scratch directory here so nothing this
    script imports (categories.py's people-name fallback in particular)
    can ever read or write ~/.assistant_tools/.
    """
    import sys
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    scratch = Path(tempfile.mkdtemp(prefix="fastrule_gen_"))
    os.environ["MACALENDAR_CATEGORIES"] = str(CATEGORIES_FIXTURE)
    os.environ.setdefault("MACALENDAR_VOCAB", str(scratch / "vocab.json"))
    os.environ.setdefault("MACALENDAR_DB", str(scratch / "calendar.db"))
    os.environ.setdefault("MACALENDAR_MEMORY_DB", str(scratch / "memory.db"))
    os.environ.setdefault("MACALENDAR_TRACE_BUS", str(scratch / "trace_bus.jsonl"))
    from assistant.actions.calendar import categories as categories_mod
    from assistant.actions.todo import tagging as tagging_mod
    return categories_mod, tagging_mod


def classify_event_category(categories_mod, title: str) -> str:
    return categories_mod.classify(title)


def classify_task_tags(tagging_mod, task_tag_keywords: dict[str, list[str]], title: str) -> list[str]:
    """Every tag whose keyword score is > 0 against `title`, using the
    product's own per-tag scoring function (`tagging._score`) — NOT just
    the single argmax `tagging.infer_tag()` returns, since ground truth
    here is intentionally multi-label (Gil's schema addition: "tags (a
    list, may be empty or multi)") while the shipped product currently only
    ever assigns one. Sorted by score desc, name asc for determinism."""
    text = " " + _WORD_CLEAN_RE.sub(" ", title.lower()) + " "
    text = re.sub(r"\s+", " ", text)
    scored = []
    for name, keywords in task_tag_keywords.items():
        score = tagging_mod._score(text, keywords)
        if score > 0:
            scored.append((score, name))
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    return [name for _, name in scored]


def title_like_keys(fam: dict) -> list[str]:
    """Every semantic slot key this family can produce that looks like
    title/title_2/title_3 — from template placeholders AND from
    `fixed_slots` overrides (a family can synthesize e.g. title_2 purely via
    fixed_slots, as the time-list-split families do when duplicating one
    title across two occurrences at different times). Ordered title,
    title_2, title_3, ..."""
    tokens = family_tokens(fam["template"])
    keys = set()
    for tok in tokens:
        _, semantic, _ = placeholder_info(tok)
        if semantic and TITLE_KEY_RE.match(semantic):
            keys.add(semantic)
    for key in fam.get("fixed_slots", {}):
        if TITLE_KEY_RE.match(key):
            keys.add(key)

    def sort_key(key: str) -> int:
        m = TITLE_KEY_RE.match(key)
        return int(m.group(2)) if m.group(2) else 1
    return sorted(keys, key=sort_key)


def resolve_label_sources(fam: dict) -> tuple[list[str], list[str]]:
    """(event_label_sources, task_label_sources): the ordered semantic slot
    keys whose VALUE is the title of a CREATED event / task in this family's
    rows — i.e. exactly what category/tags should be computed from.

    An explicit family-level override wins (required for every `action:
    "mixed"` family, since a single title-ish key there could belong to
    either an event or a task ask, or to a delete/update/complete TARGET
    that was never created and so must be excluded from labelling
    entirely — see the `mixed_mode` families in complex_patterns.json).
    Otherwise auto-derived from a homogeneous create_event/create_todo
    action, where every title-ish key present belongs to that one type.
    A family may also override for a homogeneous action when a title-ish
    key is a redundant duplicate already folded into another (the NP-decoy
    "buy {item} and {item2}" families: item2 exists only to render the
    sentence, not as a second countable task).
    """
    if "event_label_sources" in fam or "task_label_sources" in fam:
        ev = fam.get("event_label_sources", [])
        ta = fam.get("task_label_sources", [])
    elif fam["action"] == "create_event":
        ev, ta = title_like_keys(fam), []
    elif fam["action"] == "create_todo":
        ev, ta = [], title_like_keys(fam)
    else:
        ev, ta = [], []
    if len(ev) != fam["events"] or len(ta) != fam["tasks"]:
        raise ValueError(
            f"family {fam['family']}: label sources event={ev} task={ta} "
            f"don't match declared events={fam['events']} tasks={fam['tasks']} "
            f"— add explicit event_label_sources/task_label_sources")
    return ev, ta


def add_labels(fam: dict, slots: dict, categories_mod, tagging_mod, task_tag_keywords: dict) -> None:
    """Mutate `slots` in place: category/category_2/... for each expected
    event (from `fam['_label_sources'][0]`, in order), tags/tags_2/... for
    each expected task. Absent when events/tasks is 0, matching every other
    "not applicable to this row" slot key."""
    ev_sources, ta_sources = fam["_label_sources"]
    for i, key in enumerate(ev_sources):
        title_text = str(slots.get(key, ""))
        out_key = "category" if i == 0 else f"category_{i + 1}"
        slots[out_key] = classify_event_category(categories_mod, title_text)
    for i, key in enumerate(ta_sources):
        title_text = str(slots.get(key, ""))
        out_key = "tags" if i == 0 else f"tags_{i + 1}"
        slots[out_key] = classify_task_tags(tagging_mod, task_tag_keywords, title_text)


def stable_int(*parts: str) -> int:
    """A deterministic integer from arbitrary strings — independent of
    PYTHONHASHSEED / dict order, unlike the builtin hash()."""
    h = hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()
    return int(h[:16], 16)


def placeholder_info(token: str):
    """Resolve a template token ('event_title2') to (bank_key, semantic_key,
    base_name). Trailing digit N>=2 suffixes the semantic key ('title_2')
    while reusing the base's bank. Raises on an unknown placeholder."""
    if token in BASE_INFO:
        bank_key, semantic = BASE_INFO[token]
        return bank_key, semantic, token
    m = re.match(r"^(.+?)(\d)$", token)
    if m and m.group(1) in BASE_INFO:
        base = m.group(1)
        bank_key, semantic = BASE_INFO[base]
        digit = m.group(2)
        if semantic is not None:
            semantic = f"{semantic}_{digit}"
        return bank_key, semantic, base
    raise ValueError(f"unknown placeholder token: {{{token}}}")


def family_tokens(template: str):
    seen = []
    for tok in TOKEN_RE.findall(template):
        if tok not in seen:
            seen.append(tok)
    return seen


def validate_family(fam: dict, fillers: dict):
    """Catch authoring bugs early: two different placeholders writing the
    same semantic slot key (the second would silently clobber the first)."""
    tokens = family_tokens(fam["template"])
    semantic_keys = []
    for tok in tokens:
        bank_key, semantic, _ = placeholder_info(tok)
        if bank_key not in fillers:
            raise ValueError(f"family {fam['family']}: unknown bank '{bank_key}'")
        if semantic is not None:
            semantic_keys.append(semantic)
    dupes = [k for k, n in Counter(semantic_keys).items() if n > 1]
    if dupes:
        raise ValueError(
            f"family {fam['family']}: template writes slot(s) {dupes} from "
            f"two different placeholders — suffix the second ask's token "
            f"(e.g. task_title2) so it doesn't clobber the first")


def family_capacity(fam: dict, fillers: dict) -> int:
    """Rough upper bound on unique renderable rows for this family — the
    product of each distinct placeholder's bank size, capped so one
    enormous family can't be asked to swallow the whole quota."""
    tokens = family_tokens(fam["template"])
    if not tokens:
        return 1
    cap = 1
    for tok in tokens:
        bank_key, _, _ = placeholder_info(tok)
        cap *= max(1, len(fillers[bank_key]))
        if cap > 5000:
            return 5000
    return cap


def resolve_slots(fam: dict, values: dict, tokens: list[str]) -> dict:
    slots = {}
    for tok in tokens:
        _, semantic, _ = placeholder_info(tok)
        if semantic is not None:
            slots[semantic] = values[tok]
    # fixed_slots may reference the row's own picks via {token} — resolved
    # AFTER the auto slots so an explicit override wins on key collision.
    for key, wren in fam.get("fixed_slots", {}).items():
        if isinstance(wren, str) and "{" in wren:
            wren = wren.format(**values)
        slots[key] = wren
    for key, wren in fam.get("flags", {}).items():
        slots[key] = wren
    if "quoted_item" in tokens:
        slots["quoted"] = True
    if "generic_target" in tokens:
        slots["generic_target"] = True
    raw_recurrence = slots.get("recurrence")
    if raw_recurrence and raw_recurrence in RECURRENCE_ROUND:
        slots.setdefault("recurrence_rounded", RECURRENCE_ROUND[raw_recurrence])
    return slots


def gen_family_rows(fam: dict, quota: int, fillers: dict, global_seen: set) -> list[tuple[str, dict]]:
    tokens = family_tokens(fam["template"])
    value_lists = {}
    for tok in tokens:
        bank_key, _, _ = placeholder_info(tok)
        value_lists[tok] = fillers[bank_key]

    rng = random.Random(f"{SEED}:{fam['family']}")
    rows: list[tuple[str, dict]] = []
    seen_combo = set()
    attempts = 0
    max_attempts = max(200, quota * 60)
    while len(rows) < quota and attempts < max_attempts:
        attempts += 1
        if tokens:
            combo = tuple(rng.choice(value_lists[t]) for t in tokens)
        else:
            combo = ()
        if combo in seen_combo:
            continue
        seen_combo.add(combo)
        values = dict(zip(tokens, combo))
        text = fam["template"].format(**values).strip()
        text = re.sub(r"\s+", " ", text)
        if text in global_seen:
            continue
        slots = resolve_slots(fam, values, tokens)
        global_seen.add(text)
        rows.append((text, slots))
    return rows


def distribute_quota(total: int, families: list[str], capacities: dict[str, int]) -> dict[str, int]:
    """Largest-remainder distribution of `total` rows across `families`,
    each capped at its own capacity, with any resulting deficit spread
    round-robin (deterministic order) across families with spare room. Sums
    to exactly `total` as long as aggregate capacity allows it."""
    order = sorted(families, key=lambda f: stable_int(SEED, "order", f))
    n = len(order)
    base, rem = divmod(total, n)
    quotas = {f: base for f in order}
    for f in order[:rem]:
        quotas[f] += 1

    deficit = 0
    for f in order:
        cap = capacities[f]
        if quotas[f] > cap:
            deficit += quotas[f] - cap
            quotas[f] = cap

    if deficit:
        i = 0
        guard = 0
        while deficit > 0 and guard < 1_000_000:
            guard += 1
            f = order[i % n]
            i += 1
            if quotas[f] < capacities[f]:
                quotas[f] += 1
                deficit -= 1
        if deficit:
            raise ValueError(
                f"cannot fit {total} rows into families {order}: "
                f"total capacity {sum(capacities[f] for f in order)}")
    assert sum(quotas.values()) == total
    return quotas


def stratified_split(families: list[dict]) -> dict[str, str]:
    """Family -> 'train'|'test'. Stratified by (tier, action) so every
    action type present in a tier has representation on both sides — the
    held-out set must measure generalisation to UNSEEN pattern families,
    never just unseen fillers of a family the model already trained on."""
    buckets = defaultdict(list)
    for fam in families:
        buckets[(fam["tier"], fam["action"])].append(fam["family"])

    split = {}
    for key, fams in buckets.items():
        order = sorted(fams, key=lambda f: stable_int(SEED, "split", *key, f))
        n = len(order)
        if n == 1:
            # can't split a singleton bucket without losing coverage on one
            # side; keep it in train (train is where mining happens).
            test_n = 0
        else:
            test_n = max(1, round(0.2 * n))
            test_n = min(test_n, n - 1)  # always leave >=1 in train
        for f in order[:test_n]:
            split[f] = "test"
        for f in order[test_n:]:
            split[f] = "train"
    return split


def build_tier(tier: str, patterns: list[dict], total: int, fillers: dict, global_seen: set,
                categories_mod, tagging_mod, task_tag_keywords: dict):
    for fam in patterns:
        fam["tier"] = tier
        validate_family(fam, fillers)
        if tier == "simple":
            atomic, events, tasks = ACTION_DEFAULTS[fam["action"]]
            fam.setdefault("atomic", atomic)
            fam.setdefault("events", events)
            fam.setdefault("tasks", tasks)
        assert fam["action"] in ALL_ACTIONS, f"{fam['family']}: bad action {fam['action']}"
        assert isinstance(fam["atomic"], bool)
        assert isinstance(fam["events"], int) and isinstance(fam["tasks"], int)
        fam["_label_sources"] = resolve_label_sources(fam)

    split_of = stratified_split(patterns)
    for fam in patterns:
        fam["split"] = split_of[fam["family"]]

    capacities = {fam["family"]: family_capacity(fam, fillers) for fam in patterns}

    rows = []
    for split_name, target in (("train", round(total * TRAIN_FRAC)), ("test", total - round(total * TRAIN_FRAC))):
        fams = [fam for fam in patterns if fam["split"] == split_name]
        quotas = distribute_quota(target, [f["family"] for f in fams], capacities)
        for fam in fams:
            fam_rows = gen_family_rows(fam, quotas[fam["family"]], fillers, global_seen)
            if len(fam_rows) < quotas[fam["family"]]:
                raise ValueError(
                    f"family {fam['family']} only produced {len(fam_rows)}/"
                    f"{quotas[fam['family']]} unique rows (capacity "
                    f"{capacities[fam['family']]}) — widen its filler banks")
            counter = 0
            for text, slots in fam_rows:
                counter += 1
                add_labels(fam, slots, categories_mod, tagging_mod, task_tag_keywords)
                rows.append({
                    "id": f"{fam['family']}-{counter:03d}",
                    "text": text,
                    "split": split_name,
                    "tier": tier,
                    "family": fam["family"],
                    "expect": {
                        "events": fam["events"],
                        "tasks": fam["tasks"],
                        "action": fam["action"],
                        "atomic": fam["atomic"],
                        "slots": slots,
                    },
                })
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-write", action="store_true",
                     help="build and verify in memory but don't write the jsonl")
    args = ap.parse_args()

    fillers = load_json("fillers.json")
    simple_patterns = load_json("simple_patterns.json")
    complex_patterns = load_json("complex_patterns.json")
    categories_fixture = load_json("categories_fixture.json")
    task_tag_keywords = {t["name"]: t["keywords"] for t in categories_fixture["task_tags"]}
    categories_mod, tagging_mod = setup_label_env()

    global_seen: set[str] = set()
    rows = []
    rows += build_tier("simple", simple_patterns, SIMPLE_TOTAL, fillers, global_seen,
                        categories_mod, tagging_mod, task_tag_keywords)
    rows += build_tier("complex", complex_patterns, COMPLEX_TOTAL, fillers, global_seen,
                        categories_mod, tagging_mod, task_tag_keywords)

    # Final deterministic shuffle so consecutive rows aren't bursts from one
    # family — still 100% reproducible from SEED.
    order_rng = random.Random(f"{SEED}:final-order")
    order_rng.shuffle(rows)

    # ---- verification -----------------------------------------------
    texts = [r["text"] for r in rows]
    assert len(rows) == SIMPLE_TOTAL + COMPLEX_TOTAL, len(rows)
    assert len(set(texts)) == len(texts), "duplicate text rows"

    by_split = Counter(r["split"] for r in rows)
    train_n, test_n = by_split["train"], by_split["test"]
    total = len(rows)
    test_frac = test_n / total
    if not (0.19 <= test_frac <= 0.21):
        raise ValueError(f"split fraction out of tolerance: test={test_frac:.4f}")

    fam_counts = Counter(r["family"] for r in rows)
    max_family_frac = max(fam_counts.values()) / total
    if max_family_frac > 0.03:
        worst = fam_counts.most_common(1)[0]
        raise ValueError(f"family {worst} exceeds 3% of total ({max_family_frac:.2%})")

    train_families = {r["family"] for r in rows if r["split"] == "train"}
    test_families = {r["family"] for r in rows if r["split"] == "test"}
    leaked = train_families & test_families
    if leaked:
        raise ValueError(f"families present in both train and test: {leaked}")

    ids = [r["id"] for r in rows]
    assert len(set(ids)) == len(ids), "duplicate ids"

    # ---- composition table -------------------------------------------
    print(f"TOTAL rows: {total}  (simple {SIMPLE_TOTAL} / complex {COMPLEX_TOTAL})")
    print(f"Split: train={train_n} ({train_n/total:.1%})  test={test_n} ({test_n/total:.1%})")
    print(f"Unique texts: {len(set(texts))}/{total}")
    print(f"Families: {len(fam_counts)} total "
          f"({len(train_families)} train, {len(test_families)} test, "
          f"{len(leaked)} leaked)")
    print(f"Largest family: {fam_counts.most_common(1)[0][0]} = "
          f"{fam_counts.most_common(1)[0][1]} rows "
          f"({max_family_frac:.2%} of total)")
    print()
    print("By tier x split:")
    tier_split = Counter((r["tier"], r["split"]) for r in rows)
    for tier in ("simple", "complex"):
        print(f"  {tier:8s}  train={tier_split[(tier,'train')]:5d}  "
              f"test={tier_split[(tier,'test')]:5d}")
    print()
    print("By action x tier (row counts):")
    action_tier = Counter((r["expect"]["action"], r["tier"]) for r in rows)
    actions_sorted = sorted(ALL_ACTIONS)
    print(f"  {'action':16s} {'simple':>8s} {'complex':>8s} {'total':>8s}")
    for act in actions_sorted:
        s = action_tier[(act, "simple")]
        c = action_tier[(act, "complex")]
        print(f"  {act:16s} {s:8d} {c:8d} {s+c:8d}")
    print()
    print("By atomic flag x tier:")
    atomic_tier = Counter((r["tier"], r["expect"]["atomic"]) for r in rows)
    for tier in ("simple", "complex"):
        print(f"  {tier:8s}  atomic={atomic_tier[(tier, True)]:5d}  "
              f"compound={atomic_tier[(tier, False)]:5d}")
    print()
    print("Nuance families (complex tier):")
    nuance_fam = defaultdict(set)
    nuance_rows = Counter()
    for fam in complex_patterns:
        nuance_fam[fam.get("nuance", "?")].add(fam["family"])
    for r in rows:
        if r["tier"] == "complex":
            fam = next(f for f in complex_patterns if f["family"] == r["family"])
            nuance_rows[fam.get("nuance", "?")] += 1
    for nuance in sorted(nuance_fam):
        print(f"  {nuance:24s} families={len(nuance_fam[nuance]):3d}  "
              f"rows={nuance_rows[nuance]:4d}")

    print()
    print("Event category coverage (rows with >=1 expected event):")
    cat_counts = Counter()
    events_expected = 0
    for r in rows:
        n = r["expect"]["events"]
        events_expected += n
        for i in range(1, n + 1):
            key = "category" if i == 1 else f"category_{i}"
            cat_counts[r["expect"]["slots"].get(key, "<MISSING>")] += 1
    for cat, n in cat_counts.most_common():
        print(f"  {cat:12s} {n:5d}  ({n/max(1,events_expected):.1%})")
    print()
    print("Task tag coverage (rows with >=1 expected task):")
    tasks_expected = 0
    untagged = 0
    tag_counts = Counter()
    multi_tag = 0
    for r in rows:
        n = r["expect"]["tasks"]
        tasks_expected += n
        for i in range(1, n + 1):
            key = "tags" if i == 1 else f"tags_{i}"
            tags = r["expect"]["slots"].get(key, None)
            if tags is None:
                raise ValueError(f"row {r['id']}: expected task #{i} has no '{key}'")
            if not tags:
                untagged += 1
            else:
                tag_counts.update(tags)
                if len(tags) > 1:
                    multi_tag += 1
    print(f"  untagged (empty list): {untagged:5d}  ({untagged/max(1,tasks_expected):.1%})")
    print(f"  multi-tag (2+ tags):   {multi_tag:5d}  ({multi_tag/max(1,tasks_expected):.1%})")
    for tag, n in tag_counts.most_common():
        print(f"  {tag:12s} {n:5d}")

    if args.no_write:
        print("\n--no-write: skipping file output")
        return

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True))
            f.write("\n")
    print(f"\nWrote {total} rows to {OUT}")


if __name__ == "__main__":
    main()
