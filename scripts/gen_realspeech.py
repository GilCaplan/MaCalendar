#!/usr/bin/env python3
"""Generate the REAL-SPEECH dataset (dataset/realspeech/).

WHY THIS EXISTS
---------------
Every board we own measures well-formed prompts. `dataset/fastrule/`'s 7,200
rows are clean single-clause commands; the 3,000-row verification pool is
tidied history. Meanwhile `scripts/weekly_review.py` — the only instrument
pointed at REAL usage — reads a 50% flag rate against benchmarks in the
80s. The benchmarks are not lying; they are measuring a different input
distribution.

This builds the missing one. The author's real command store
(~/.assistant_tools/nlu_memory.db) was read ONCE, READ-ONLY, and reduced to
aggregate SHAPE statistics: how many asks an utterance carries, how often a
speaker opens with a filler, corrects themselves mid-sentence, restates a
date three ways, and how often speech recognition damages the words — and in
which of eight measurable ways. Those shapes are rebuilt here over generic
fillers, so the DISTRIBUTION is real and the CONTENT is invented.

PRIVACY IS THE HARD CONSTRAINT. Not one real utterance, name, place or piece
of personal shorthand is copied into the generated set or into
dataset/realspeech/REALSPEECH.md. `--leak-check` (on by default) reads the
author's real vocabulary read-only and FAILS THE BUILD if any word of it
(>= 5 chars, word-boundary — the same standard as
tests/unit/test_artifact_claims.py) reaches a generated row. It reuses
scripts/gen_personas.py's gate rather than reimplementing it.

GROUND TRUTH BY CONSTRUCTION, exactly as dataset/fastrule/ does: this script
composed the asks, so it knows how many events and tasks the utterance
should produce, which action it is, whether it is atomic, and what went into
every slot. The speech layer that damages the surface NEVER changes what was
meant — it changes what was heard, which is the whole point.

    python -m scripts.gen_realspeech             # generate + verify + write
    python -m scripts.gen_realspeech --no-write  # same, without writing
    python -m scripts.gen_realspeech --shapes    # print the shape-rate table

See dataset/realspeech/REALSPEECH.md for the derivation, the schema, the
measured-vs-generated shape table and the leakage rules.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Reuse the FastRule generator's slot contract and the persona generator's leak
# gate rather than reimplementing either — one copy of each is the only safe
# number. Both imports are read-only; this script writes nothing of theirs.
from scripts.gen_fastrule_dataset import (      # noqa: E402
    distribute_quota,
    placeholder_info,
    stable_int,
    stratified_split,
)
from scripts.gen_personas import (              # noqa: E402
    read_vocab_words,
)

DATA_DIR = ROOT / "dataset" / "realspeech"
BANKS = DATA_DIR / "banks"
OUT = DATA_DIR / "realspeech_1200.jsonl"
ALLOWED_WORDS = DATA_DIR / "allowed_words.txt"

#: Changing this reseeds every row. Don't, without regenerating and noting it
#: in REALSPEECH.md.
SEED = "realspeech-v1"

TOKEN_RE = re.compile(r"\{(\w+)\}")

# ---------------------------------------------------------------------------
# The measured input distribution (see REALSPEECH.md "How the shapes were
# derived"). n = 83 real utterances, source != 'test', read read-only.
# ---------------------------------------------------------------------------

#: asks-per-utterance, hand-annotated over all 83 real rows.
MEASURED_ASK_MIX = {0: 0.048, 1: 0.795, 2: 0.120, 3: 0.012, 4: 0.024}
#: ...as row counts for the faithful pool: round(FAITHFUL_ROWS * fraction),
#: with the rounding residual given to the thinnest bucket so the pool is
#: exactly FAITHFUL_ROWS rows and the filename stays honest.
FAITHFUL_COUNTS = {0: 38, 1: 636, 2: 96, 3: 10, 4: 20}
STRESS_COUNTS = {1: 40, 2: 160, 3: 120, 4: 80}

#: The FAITHFUL pool reproduces MEASURED_ASK_MIX, so its board is a
#: real-usage proxy. The STRESS pool oversamples the multi-ask tail, which
#: the real sample is too thin to slice (1 three-ask row, 2 four-ask rows).
#: Kept as separate pools, never blended into a headline, so a reader always
#: knows which number is the proxy and which is the microscope.
FAITHFUL_ROWS = 800
STRESS_ROWS = 400
STRESS_ASK_MIX = {1: 0.10, 2: 0.40, 3: 0.30, 4: 0.20}

TRAIN_FRAC = 0.8

#: Probability a shape fires GIVEN the row is eligible for it. Tuned once so
#: the achieved marginal (printed by --shapes) lands on the measured
#: marginal; the measured column is in REALSPEECH.md's table.
RATES = {
    "opener_filler":      0.076,
    "mid_filler":         0.06,
    "selfcorrection":     0.086,
    "date_restatement":   0.60,
    "decimal_time":       0.62,
    "fused_digit_time":   0.62,
    "spelled_oclock":     0.85,
    "trailing_dangler":   0.07,
    "trailing_hedge":     0.058,
    "meta_tail":          0.028,
    "cutoff_tail":        0.07,
    "apology_tail":       0.04,
    "stutter":            0.03,
    "wake_bleed":         0.05,
    "ui_tag":             0.014,
    "wake_suffix_raw":    0.36,
    # --- speech-recognition damage
    "name_mangle":        0.80,
    "verb_mangle":        0.14,
    # possessive / compound / loanword damage fires on rows whose title was
    # drawn from the matching damageable bank
    "content_damage":     0.62,
}

TITLE_BANKS = {"event": "event_titles", "task": "task_titles", "item": "items"}
DAMAGEABLE = {"possessive": "possessive_templates",
              "compound": "compound_titles",
              "loanword": "loanword_titles"}


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------

def load_json(name: str):
    with open(BANKS / name, encoding="utf-8") as f:
        return json.load(f)


def allowed_words() -> set:
    if not ALLOWED_WORDS.exists():
        return set()
    return {ln.split("#")[0].strip().lower()
            for ln in ALLOWED_WORDS.read_text().splitlines()
            if ln.strip() and not ln.strip().startswith("#")} - {""}


def read_vocab_aliases() -> set:
    """The vocabulary's ALIAS side, read-only — a STRICTER gate than the
    persona generator's, and necessary here specifically.

    `gen_personas.read_vocab_words()` checks the corrected words only, which
    is the right standard for a dataset whose content is invented nouns. This
    dataset's whole job is generating MANGLED SURFACE FORMS, and a vocabulary
    alias IS a real mangled surface form of a real personal word — the one
    string a speech-damage generator could plausibly collide with while the
    word-side gate stayed green. So both sides are checked.
    """
    from scripts.gen_personas import VOCAB_PATH
    if not VOCAB_PATH.exists():
        return set()
    try:
        raw = json.loads(VOCAB_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return set()
    out = set()
    for entry in (raw.get("entries") if isinstance(raw, dict) else raw) or []:
        if not isinstance(entry, dict):
            continue
        for a in entry.get("aliases") or []:
            if isinstance(a, str) and a.strip():
                out.add(a.strip().lower())
    return out


def leak_check(rows) -> dict:
    """Every author-vocabulary word that survived into a generated row.

    Same standard as scripts/gen_personas.leak_check and
    tests/unit/test_artifact_claims.py, plus the alias side (see
    read_vocab_aliases): a vocabulary word is a leak unless
    declared general in allowed_words.txt, and only words of >= 5 characters
    are checked (shorter entries collide with ordinary English). Checks the
    damaged text AND the clean base AND every ground-truth slot value, since
    a leak in a slot is as public as a leak in the sentence.
    """
    words = read_vocab_words() | read_vocab_aliases()
    if not words:
        return {}
    candidates = sorted(w for w in words - allowed_words() if len(w) >= 5)
    if not candidates:
        return {}
    pattern = re.compile(r"\b(" + "|".join(re.escape(w) for w in candidates) + r")\b")
    hits = defaultdict(list)
    for r in rows:
        blob = " ".join([r["text"], r.get("clean", ""),
                         json.dumps(r["expect"], ensure_ascii=False),
                         r.get("raw_text", "")]).lower()
        for m in pattern.finditer(blob):
            if len(hits[m.group(1)]) < 3:
                hits[m.group(1)].append(r["id"])
    return dict(hits)


# ---------------------------------------------------------------------------
# the speech layer — text-only transforms; ground truth is never touched
# ---------------------------------------------------------------------------

_HHMM_RE = re.compile(r"^(\d{1,2}):(\d{2})(am|pm)?$")
_HOUR_RE = re.compile(r"^(\d{1,2})(am|pm)$")


def surface_time(canonical: str, rng, fired: set) -> str:
    """Render a canonical time phrase as it might have been HEARD.

    Number-format damage is 9.6% of real rows and is the damage kind that
    hits the field users care most about. Three measured variants:
    the decimal point for the colon ("4.30 pm" — 18.1% of real rows), fused
    digits ("910am" — 7.2%), and the bare hour spoken as "N o'clock"
    (14.5%), which drops the am/pm the speaker never said out loud.
    """
    m = _HHMM_RE.match(canonical)
    if m and rng.random() < RATES["decimal_time"]:
        fired.add("decimal_time")
        h, mm, ap = m.groups()
        return f"{h}.{mm}" + (f" {ap[0]}.{ap[1]}." if ap else "")
    if m and rng.random() < RATES["fused_digit_time"]:
        fired.add("fused_digit_time")
        h, mm, ap = m.groups()
        return f"{h}{mm}" + (ap.upper() if ap else "")
    h2 = _HOUR_RE.match(canonical)
    # Only afternoon/evening hours 1-8 take the bare "o'clock" surface: those
    # are the ones a reader still recovers from context. Applying it to an
    # am hour would make the row unanswerable rather than merely damaged.
    if h2 and h2.group(2) == "pm" and 1 <= int(h2.group(1)) <= 8 \
            and rng.random() < RATES["spelled_oclock"]:
        fired.add("spelled_oclock")
        return f"{h2.group(1)} o'clock"
    return canonical


def surface_date(canonical: str, rng, fired: set) -> str:
    """Render a canonical date phrase as it might have been SAID.

    27.7% of real utterances name the same day two or three ways ("next week
    on monday on the 13th"). Only CONSISTENT restatements are generated —
    the real store also contains self-contradicting ones, which have no
    single right answer and so are deliberately left out (REALSPEECH.md,
    "What was deliberately left out").
    """
    if rng.random() >= RATES["date_restatement"]:
        return canonical
    m = re.match(r"^(next|this) (\w+day)$", canonical)
    if m:
        fired.add("date_restatement")
        which, day = m.group(1), m.group(2)
        # Restatement must be MEANING-PRESERVING. An earlier draft let
        # "this tuesday" surface as "next week on tuesday", which silently
        # made the ground truth wrong for those rows — the one failure mode a
        # generated dataset cannot afford, since nothing downstream can catch
        # it. Each canonical form now restates only within its own week.
        if which == "next":
            return rng.choice([f"next week on {day}", f"next {day}, on {day}",
                               f"on {day} next week", f"next week, on {day}"])
        return rng.choice([f"this coming {day}", f"this week on {day}",
                           f"this {day}, on {day}", f"on {day}, this {day}"])
    m = re.match(r"^(\w+) (\d{1,2})$", canonical)          # "september 17"
    if m:
        fired.add("date_restatement")
        d = m.group(2)
        suf = "th" if d[-1] not in "123" or d in ("11", "12", "13") else \
            {"1": "st", "2": "nd", "3": "rd"}[d[-1]]
        return rng.choice([f"on the {d}{suf} of {m.group(1)}",
                           f"the {d}{suf} of {m.group(1)}",
                           f"{m.group(1)} the {d}{suf}"])
    if canonical in ("today", "tomorrow"):
        fired.add("date_restatement")
        return rng.choice([f"{canonical}, {canonical}",
                           f"{canonical}, later {canonical}",
                           f"{canonical} — {canonical}"])
    return canonical


def mangle_name(name: str, mangles: dict, rng, fired: set) -> str:
    """Proper-noun homophone substitution — 19.3% of real rows, the most
    frequent damage kind measured. The GROUND TRUTH becomes the surface
    form: nothing in the sentence lets a parser recover the intended
    spelling, so extracting what was said is the correct behaviour and
    repairing it is the vocabulary layer's job."""
    if name in mangles and rng.random() < RATES["name_mangle"]:
        fired.add("name_mangle")
        return rng.choice(mangles[name])
    return name


def mangle_verb(text: str, verb_mangles: dict, rng, fired: set) -> str:
    """Command-verb damage — 7.2% of real rows, and the worst kind: the
    imperative itself is heard as content, so a rule parser has no verb
    left to key on. Longest key first, applied at most once."""
    if rng.random() >= RATES["verb_mangle"]:
        return text
    for key in sorted(verb_mangles, key=len, reverse=True):
        if text.lower().startswith(key) or f" {key}" in text.lower():
            i = text.lower().find(key)
            fired.add("verb_mangle")
            return text[:i] + rng.choice(verb_mangles[key]) + text[i + len(key):]
    return text


def insert_selfcorrection(text: str, slots: dict, speech: dict, rng, fired: set) -> str:
    """A speaker naming the wrong value and fixing it in the same breath —
    10.8% of real rows. The corrected value is the truth; the wrong one is
    surface noise the parser has to discard rather than book."""
    cue = rng.choice(speech["correction_cues"])
    date_v, time_v = slots.get("_date_surface"), slots.get("_time_surface")
    choices = []
    if date_v and date_v in text:
        wrong = rng.choice([w for w in speech["wrong_dates"] if w != date_v] or ["monday"])
        choices.append((date_v, f"{wrong}. {cue} not {wrong}, {date_v}"))
    if time_v and time_v in text:
        wrong = rng.choice(speech["wrong_times"])
        choices.append((time_v, f"{wrong} {cue} {time_v}"))
    att = slots.get("_attendee_surface")
    if att and att in text:
        wrong = rng.choice([n for n in speech["name_mangles"] if n != att] or ["Alex"])
        choices.append((att, f"{wrong} {cue} {att}"))
    if not choices:
        # nothing nameable to correct: the speaker just stalls instead, which
        # the store shows them doing too ("let's see, it is...")
        fired.add("selfcorrection")
        return text.replace(" at ", f" at {rng.choice(speech['stall_phrases'])} ", 1) \
            if " at " in text else f"{text} {rng.choice(speech['stall_phrases'])}"
    target, repl = rng.choice(choices)
    fired.add("selfcorrection")
    return text.replace(target, repl, 1)


def apply_row_shapes(text: str, speech: dict, rng, fired: set, is_task: bool) -> str:
    """Whole-utterance disfluency: openers, mid-sentence fillers, stutters,
    trailing danglers and hedges, the wake word bleeding into content, and
    the view tag the Mac app prefixes onto a task-pane command."""
    if rng.random() < RATES["ui_tag"]:
        fired.add("ui_tag")
        text = (speech["ui_tags"][0] if is_task else speech["ui_tags"][1]) + text
    if rng.random() < RATES["opener_filler"]:
        fired.add("opener_filler")
        text = f"{rng.choice(speech['openers'])} {text}"
    if rng.random() < RATES["mid_filler"]:
        words = text.split()
        if len(words) > 4:
            fired.add("mid_filler")
            i = rng.randrange(2, len(words) - 1)
            words.insert(i, rng.choice(speech["mid_fillers"]) + ",")
            text = " ".join(words)
    if rng.random() < RATES["stutter"]:
        words = text.split()
        if len(words) > 3:
            fired.add("stutter")
            i = rng.randrange(1, len(words) - 1)
            words.insert(i, words[i])
            text = " ".join(words)
    if rng.random() < RATES["wake_bleed"]:
        fired.add("wake_bleed")
        text = f"{text} {rng.choice(speech['wake_bleed'])}"
    if rng.random() < RATES["cutoff_tail"]:
        fired.add("cutoff_tail")
        text = f"{text}, {rng.choice(speech['cutoff_tails'])}"
    if rng.random() < RATES["apology_tail"]:
        fired.add("apology_tail")
        text = f"{text} {rng.choice(speech['apology_tails'])}"
    if rng.random() < RATES["meta_tail"]:
        fired.add("meta_tail")
        text = f"{text}, {rng.choice(speech['meta_tails'])}"
    if rng.random() < RATES["trailing_hedge"]:
        fired.add("trailing_hedge")
        text = f"{text}, {rng.choice(speech['hedge_tails'])}"
    if rng.random() < RATES["trailing_dangler"]:
        fired.add("trailing_dangler")
        text = f"{text} {rng.choice(speech['dangler_tails'])}"
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------------
# composition
# ---------------------------------------------------------------------------

def draw_title(content: str, fillers: dict, speech: dict, rng, fired: set,
               used: set) -> tuple[str, str | None]:
    """(surface_title, intended_title_or_None) for one ask.

    A 'damageable' content class (possessive / compound / loanword) draws a
    clean title and its measured damaged surfaces; when the damage fires,
    the SURFACE becomes the ground-truth title and the clean form is kept as
    `intended_title` for diagnosis only.
    """
    if content in TITLE_BANKS:
        bank = fillers[TITLE_BANKS[content]]
        for _ in range(40):
            v = rng.choice(bank)
            if v not in used:
                used.add(v)
                return v, None
        return rng.choice(bank), None
    entry = rng.choice(speech[DAMAGEABLE[content]])
    clean = entry["clean"]
    if content == "possessive":
        clean = clean.format(name=rng.choice(fillers["names"]))
    if rng.random() < RATES["content_damage"]:
        fired.add(f"{content}_damage")
        dmg = rng.choice(entry["damaged"])
        if content == "possessive":
            dmg = dmg.format(name=clean.split("'s")[0].split()[-1])
        return dmg, clean
    return clean, None


def render_ask(ask: dict, fillers: dict, speech: dict, rng, fired: set,
               used: set) -> tuple[str, dict, str]:
    """One sub-ask -> (surface text, semantic slots, action)."""
    tokens = [t for t in dict.fromkeys(TOKEN_RE.findall(ask["template"]))]
    values, slots = {}, {}
    intended = {}
    for tok in tokens:
        bank_key, semantic, _ = placeholder_info(tok)
        if tok in ("event_title", "task_title", "item"):
            surf, intent = draw_title(ask.get("content", "event"), fillers,
                                      speech, rng, fired, used)
            values[tok] = surf
            slots[semantic] = surf
            if intent:
                intended["intended_title"] = intent
            continue
        if tok == "name":
            real = rng.choice(fillers["names"])
            surf = mangle_name(real, speech["name_mangles"], rng, fired)
            values[tok] = surf
            slots[semantic] = surf
            slots["_attendee_surface"] = surf
            if surf != real:
                intended["intended_attendee"] = real
            continue
        if tok == "date":
            canon = rng.choice(fillers["dates"])
            # A relative weekday ("next thursday") has TWO defensible
            # readings — the soonest such weekday, or the one in next
            # calendar week — and the project has never ruled between them
            # (REALSPEECH.md, "The one convention this dataset does not
            # settle"). Flagged so a board can be read with the dispute
            # excluded; declared here, before any score was seen, so
            # excluding it is not outcome-selection.
            if re.match(r"^(next|this) \w+day$", canon):
                fired.add("date_weekday_relative")
            surf = surface_date(canon, rng, fired)
            values[tok] = surf
            slots[semantic] = canon              # truth = what was MEANT
            slots["_date_surface"] = surf
            continue
        if tok == "time":
            canon = rng.choice(fillers["times"])
            surf = surface_time(canon, rng, fired)
            values[tok] = surf
            slots[semantic] = canon              # truth = what was MEANT
            slots["_time_surface"] = surf
            continue
        v = rng.choice(fillers[bank_key])
        values[tok] = v
        if semantic:
            slots[semantic] = v
    text = ask["template"].format(**values)
    text = mangle_verb(text, speech["verb_mangles"], rng, fired)
    if rng.random() < RATES["selfcorrection"]:
        text = insert_selfcorrection(text, slots, speech, rng, fired)
    slots.update(intended)
    return re.sub(r"\s+", " ", text).strip(), slots, ask["action"]


CLASS_ACTION = {"e": "create_event", "t": "create_todo", "q": "query",
                "u": "update_event", "d": "delete_event"}
EXPECT_COUNTS = {"create_event": (1, 0), "create_todo": (0, 1)}


def compose_row(fam: dict, patterns: dict, fillers: dict, speech: dict,
                rng) -> tuple[str, str, dict, list[str]]:
    """(surface text, clean base text, expect, shapes-that-fired)."""
    fired: set = set()
    used: set = set()
    asks_out, slots_out, actions = [], [], []
    clean_parts = []
    for pos, cls in enumerate(fam["asks"]):
        pool = [k for k, a in sorted(patterns["asks"].items())
                if a["action"] == CLASS_ACTION[cls]
                and a["register"] == fam["register"]]
        if not pool:                                   # register not offered
            pool = [k for k, a in sorted(patterns["asks"].items())
                    if a["action"] == CLASS_ACTION[cls]]
        key = pool[stable_int(SEED, fam["family"], str(pos),
                              str(rng.random())) % len(pool)]
        ask = dict(patterns["asks"][key])
        text, slots, action = render_ask(ask, fillers, speech, rng, fired, used)
        clean_parts.append(ask["template"])
        asks_out.append(text)
        slots_out.append(slots)
        actions.append(action)

    join = speech["joins"][fam["join"]]
    text = join.join(asks_out)
    is_task = any(a == "create_todo" for a in actions)
    text = apply_row_shapes(text, speech, rng, fired, is_task)

    events = sum(EXPECT_COUNTS.get(a, (0, 0))[0] for a in actions)
    tasks = sum(EXPECT_COUNTS.get(a, (0, 0))[1] for a in actions)
    action = actions[0] if len(set(actions)) == 1 else "mixed"

    merged: dict = {}
    for i, slots in enumerate(slots_out):
        for k, v in slots.items():
            if k.startswith("_"):
                continue
            merged[k if i == 0 else f"{k}_{i + 1}"] = v
    expect = {"events": events, "tasks": tasks, "action": action,
              "atomic": len(fam["asks"]) == 1, "slots": merged}
    return text, join.join(clean_parts), expect, sorted(fired)


# ---------------------------------------------------------------------------
# families
# ---------------------------------------------------------------------------

def build_families(patterns: dict, speech: dict) -> list[dict]:
    """A family is one (structure, register, join) construction. The
    train/test split is BY FAMILY, so a test row is an unseen construction,
    not an unseen filler of a construction already trained on."""
    joins = sorted(speech["joins"])
    single_join = "period"
    fams = []
    for sname in sorted(patterns["structures"]):
        st = patterns["structures"][sname]
        n = len(st["asks"])
        for reg in st["registers"]:
            if n == 1:
                fams.append({"family": f"rs_{sname}_{reg}", "asks": st["asks"],
                             "register": reg, "join": single_join,
                             "structure": sname, "n_asks": n})
                continue
            # multi-ask families fan out over join styles: how two asks are
            # chained is itself a construction, and the real store shows
            # every one of these joiners in use.
            pick = [j for j in joins if j != "period"]
            k = stable_int(SEED, "join", sname, reg) % len(pick)
            for off in range(3 if n == 2 else 2):
                j = pick[(k + off * 3) % len(pick)]
                fams.append({"family": f"rs_{sname}_{reg}_{j}", "asks": st["asks"],
                             "register": reg, "join": j, "structure": sname,
                             "n_asks": n})
    return fams


def null_rows(patterns: dict, speech: dict, quota: int, split: str,
              global_seen: set) -> list[dict]:
    """Rows carrying NO ask — 4.8% of the real store. Scored in the
    `propose` bucket, whose semantics are exactly right here (a defer is
    correct, any commit is a violation); `null_input` marks them so a future
    scorer can separate the two populations."""
    rng = random.Random(f"{SEED}:null:{split}")
    out = []
    texts = patterns["null_texts"]
    i = 0
    while len(out) < quota and i < quota * 40:
        i += 1
        base = texts[rng.randrange(len(texts))]
        t = base
        if rng.random() < 0.4:
            t = f"{rng.choice(speech['openers'])} {base}"
        if rng.random() < 0.3:
            t = f"{t} {rng.choice(speech['cutoff_tails'])}"
        t = re.sub(r"\s+", " ", t).strip()
        if t in global_seen:
            continue
        global_seen.add(t)
        # two families, one per side: a family must never straddle the
        # split (verify() enforces it), and the test side's job is unseen
        # constructions, so the null rows follow the same rule as the rest.
        fam = "rs_null" if split == "train" else "rs_null_unseen"
        row = {"id": f"{fam}-{len(out):03d}",
               "text": t, "clean": base, "split": split, "tier": "realspeech",
               "pool": "faithful", "family": fam, "n_asks": 0,
               "shapes": [], "null_input": True,
               "expect": {"events": 0, "tasks": 0, "action": "propose",
                          "atomic": True, "must_not_commit": True, "slots": {}}}
        if rng.random() < RATES["wake_suffix_raw"]:
            row["raw_text"] = t + rng.choice(speech["wake_suffix"])
        out.append(row)
    return out


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------

def build(patterns: dict, fillers: dict, speech: dict) -> list[dict]:
    fams = build_families(patterns, speech)
    by_slug = {f["family"]: f for f in fams}

    # split by family, stratified over (ask-count, primary action) so both
    # halves see every structure class
    strat_input = [{"family": f["family"], "tier": f"n{f['n_asks']}",
                    "action": CLASS_ACTION[f["asks"][0]]} for f in fams]
    split_of = stratified_split(strat_input)

    rows: list[dict] = []
    global_seen: set = set()
    for pool, counts in (("faithful", FAITHFUL_COUNTS),
                         ("stress", STRESS_COUNTS)):
        for n_asks, quota in sorted(counts.items()):
            if n_asks == 0:
                ntrain = round(quota * TRAIN_FRAC)
                rows += null_rows(patterns, speech, ntrain, "train", global_seen)
                rows += null_rows(patterns, speech, quota - ntrain, "test", global_seen)
                continue
            group = sorted(f["family"] for f in fams if f["n_asks"] == n_asks)
            caps = {f: 5000 for f in group}
            quotas = distribute_quota(quota, group, caps)
            for slug in group:
                fam = by_slug[slug]
                rng = random.Random(f"{SEED}:{pool}:{slug}")
                made = 0
                tries = 0
                while made < quotas[slug] and tries < quotas[slug] * 60 + 200:
                    tries += 1
                    text, clean, expect, fired = compose_row(
                        fam, patterns, fillers, speech, rng)
                    if text in global_seen:
                        continue
                    global_seen.add(text)
                    row = {"id": f"{slug}-{pool[0]}{made:03d}", "text": text,
                           "clean": clean, "split": split_of[slug],
                           "tier": "realspeech", "pool": pool, "family": slug,
                           "n_asks": fam["n_asks"], "register": fam["register"],
                           "join": fam["join"], "shapes": fired, "expect": expect}
                    if rng.random() < RATES["wake_suffix_raw"]:
                        row["raw_text"] = text + rng.choice(speech["wake_suffix"])
                    rows.append(row)
                    made += 1
    rows.sort(key=lambda r: (r["pool"], r["family"], r["id"]))
    return rows


def verify(rows: list[dict]) -> None:
    """Self-checks that must hold before anything is written — the same
    discipline as the FastRule generator: a violation raises instead of
    silently writing a bad file."""
    texts = [r["text"] for r in rows]
    assert len(set(texts)) == len(texts), "duplicate texts"
    ids = [r["id"] for r in rows]
    assert len(set(ids)) == len(ids), "duplicate ids"
    fam_split = {}
    for r in rows:
        prev = fam_split.setdefault(r["family"], r["split"])
        assert prev == r["split"], f"family {r['family']} straddles the split"
    tr = sum(1 for r in rows if r["split"] == "train")
    frac = tr / len(rows)
    assert 0.70 <= frac <= 0.88, f"train fraction {frac:.1%} outside [70%, 88%]"
    big = Counter(r["family"] for r in rows).most_common(1)[0]
    assert big[1] / len(rows) <= 0.05, f"family {big[0]} is {big[1]/len(rows):.1%} of the set"
    for r in rows:
        e = r["expect"]
        if r["n_asks"]:
            assert e["atomic"] == (r["n_asks"] == 1), f"{r['id']}: atomic/n_asks disagree"
        else:
            # a null row carries no ask; it is scored in the propose bucket,
            # where `atomic: true` simply means "one utterance, must not commit"
            assert e["action"] == "propose" and r.get("null_input")
        assert set(e) >= {"events", "tasks", "action", "atomic", "slots"}
        assert not any(k.startswith("_") for k in e["slots"]), f"{r['id']}: internal slot leaked"
        if e["action"] in ("create_event", "create_todo") and r["n_asks"]:
            assert e["events"] + e["tasks"] == r["n_asks"], f"{r['id']}: count/asks disagree"


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------

#: measured marginals from the real store (n=83) — printed beside the
#: achieved rate so a drift in either is visible at a glance.
MEASURED_MARGINALS = {
    "opener_filler": 0.072, "selfcorrection": 0.108, "date_restatement": 0.277,
    "decimal_time": 0.181, "fused_digit_time": 0.072, "spelled_oclock": 0.145,
    "trailing_dangler": 0.072, "trailing_hedge": 0.060, "meta_tail": 0.036,
    "cutoff_tail": 0.072, "stutter": 0.024, "ui_tag": 0.012,
    "name_mangle": 0.193, "verb_mangle": 0.072,
}
DAMAGE_SHAPES = {"name_mangle", "verb_mangle", "possessive_damage",
                 "compound_damage", "loanword_damage", "decimal_time",
                 "fused_digit_time", "cutoff_tail"}


def report(rows: list[dict], shapes_only: bool = False) -> None:
    n = len(rows)
    print(f"\nrealspeech: {n} rows  ({sum(1 for r in rows if r['split']=='train')} train / "
          f"{sum(1 for r in rows if r['split']=='test')} test), "
          f"{len(set(r['family'] for r in rows))} families\n")
    faith = [r for r in rows if r["pool"] == "faithful"]
    fired, ffired = Counter(), Counter()
    for r in rows:
        for s in r["shapes"]:
            fired[s] += 1
    for r in faith:
        for s in r["shapes"]:
            ffired[s] += 1
    nf = len(faith)
    # The FAITHFUL pool is the calibration target: it reproduces the measured
    # asks-per-utterance mix, so its shape marginals are the ones that should
    # land on the real store's. The stress pool runs the same per-ask rates
    # over more asks per row, so its marginals are higher by construction.
    print(f"{'shape':<22} {'faithful':>9} {'measured':>9} {'all rows':>9}")
    for s in sorted(set(fired) | set(MEASURED_MARGINALS)):
        m = MEASURED_MARGINALS.get(s)
        print(f"  {s:<20} {ffired[s]/nf:>8.1%} "
              f"{(f'{m:.1%}' if m is not None else '—'):>9} {fired[s]/n:>9.1%}")
    dmg = sum(1 for r in rows if DAMAGE_SHAPES & set(r["shapes"]))
    fdmg = sum(1 for r in faith if DAMAGE_SHAPES & set(r["shapes"]))
    print(f"  {'ANY STT damage':<20} {fdmg/nf:>8.1%} {'47.0%':>9} {dmg/n:>9.1%}")
    if shapes_only:
        return
    print("\nby pool x asks-per-utterance")
    pa = Counter((r["pool"], r["n_asks"]) for r in rows)
    for pool in ("faithful", "stress"):
        sub = {k[1]: v for k, v in pa.items() if k[0] == pool}
        tot = sum(sub.values())
        if not tot:
            continue
        print(f"  {pool:<9} n={tot:<5} " +
              "  ".join(f"{k}-ask {v} ({v/tot:.0%})" for k, v in sorted(sub.items())))
    print("\nby action")
    for k, v in Counter(r["expect"]["action"] for r in rows).most_common():
        print(f"  {k:<14} {v:>5}  {v/n:6.1%}")
    print("\nby register")
    for k, v in Counter(r.get("register", "—") for r in rows).most_common():
        print(f"  {k:<14} {v:>5}  {v/n:6.1%}")
    for label, sub in (("faithful", faith), ("all rows", rows)):
        lens = sorted(len(r["text"].split()) for r in sub)
        k = len(lens)
        print(f"length ({label}): mean {sum(lens)/k:.1f}  median {lens[k//2]}  "
              f"p90 {lens[int(.9*k)]}  max {lens[-1]}"
              + ("   (real: mean 15.3, median 12, p90 28, max 92)" if label == "faithful" else ""))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--shapes", action="store_true", help="print the shape table only")
    ap.add_argument("--no-leak-check", action="store_true",
                    help="skip the vocabulary leak gate (CI has no vocabulary; "
                         "never pass this on the author's machine)")
    a = ap.parse_args()

    patterns = load_json("ask_patterns.json")
    fillers = load_json("fillers.json")
    speech = load_json("speech.json")
    rows = build(patterns, fillers, speech)
    verify(rows)

    leaks = {} if a.no_leak_check else leak_check(rows)
    if leaks:
        lines = "\n".join(f"    {w!r}  e.g. {ex}" for w, ex in sorted(leaks.items()))
        raise SystemExit(
            "LEAK GATE FAILED — the author's own vocabulary reached a generated "
            f"row.\n{lines}\nEither change the bank word, or declare it general "
            f"in {ALLOWED_WORDS.relative_to(ROOT)} with a reason.")

    report(rows, shapes_only=a.shapes)
    nvocab = len(read_vocab_words())
    print(f"\nLeak gate: {'SKIPPED' if a.no_leak_check else 'clean'} "
          f"({nvocab} author words + {len(read_vocab_aliases())} aliases "
          f"checked, >=5 chars, word-boundary)")
    if a.no_write or a.shapes:
        print("(--no-write: nothing written)" if a.no_write else "")
        return 0
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}  ({os.path.getsize(OUT)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
