# Object-Based Brain — Design for Review

_2026-09-07. Proposal only — nothing is built until Gil approves._

Make the whole brain object-based like `FastRule`, and turn the session's
novel ideas — two-instance FastRule, rules-first-per-fragment, atomicity
detection, crosscheck-as-single-judge, path-B verify, per-instance tuning —
into **structure** instead of inline logic. The seven stage I/O contracts are
preserved exactly; this wraps them in classes, it never reshapes them.

## Contents

1. The algorithm in plain language ← start here
2. Overview — the shape
3. End-to-end flow (pseudo-code)
4. The object model
5. The novel ideas, as structure
6. Preserved vs. changed
7. Migration plan
8. Open questions for Gil

---

## 1 · The algorithm in plain language

The bare-bones flow, start to finish. Named pieces (**FastRule**, **the
judge**, …) are defined once in "Reusable pieces" below — the main flow just
refers to them, so you can read straight through and only drill into a piece
if you want to know how it works.

### Main flow — one command, arrival to answer

1. A command arrives — typed, or a spoken transcript — from the Mac or the
   phone.
2. **Ingest.** If other commands are queued they're merged into this one;
   filler and false-starts are dropped (and never remembered).
3. **Ask FastRule** — the deterministic front door. It either *commits* an
   answer or *defers*.
4. **If FastRule commits →** the answer is executed and returned to the user
   immediately (milliseconds, no AI model). Then, quietly in the background,
   **the judge** re-checks it and fixes or flags anything wrong. Done.
5. **If FastRule defers →** the command enters the *deep track*, the careful
   multi-step pipeline (steps 6–13).
6. **Repair the transcript** — fix mis-heard words against the user's personal
   vocabulary.
7. **Segment** — split the command into its separate things: events, tasks, a
   schedule question. When unsure it *under-splits* (safer to keep "Tal and
   Ravid" together than to shatter a name).
8. **Decompose** — break each of those into *atomic* pieces: two times → two
   events, "buy 5 apples" → one task of five, a recurrence → its cadence.
9. **Validate (text pass)** — clean up the pieces' text before they're made
   into objects (grammar, garbled fragments).
10. **Generate** — turn each atomic piece into a concrete event or task. For
    each piece, **ask FastRule first**; call the AI model only for the pieces
    FastRule can't read. If a piece still looks like two requests, it was never
    atomic — send it back to Decompose to be split again.
11. **Validate (object pass)** — run the ordered correctness rules: impossible dates, am/pm,
    until vs. through, round a recurrence and *say so*, and — *only when observance is
    turned on in settings* — the Shabbat / holiday rules for anything the AI
    itself created.
12. **The judge** — the AI reads the *original words* and lists what was asked;
    the code compares that to what was produced and finds anything missing,
    extra, or wrong. On a problem it goes back to whichever step caused it and
    re-runs (a few times at most).
13. **Label & commit** — colour and categorise events, tag tasks, write it all
    to the calendar / task list, and answer the user.

### Reusable pieces (read only if you want the detail)

**FastRule — the rule-based parser (used at step 3 and again at step 9).**
Deterministic, no AI: it normalizes shorthand, routes on verb+object tables
("remove"+calendar → delete an event), fills in dates/times, and scores its
own confidence. It *commits* only when confident **and** the parse is clean;
otherwise it *abstains* and hands off. It runs in two instances with different
confidence bars — strict at the front door (it's the whole, possibly-complex
command, and the deep track is its safety net), lenient on atomic fragments
(they're simple, and the judge is the net). Its abstain also carries a
*reason*, and one of those reasons — "this still looks like two requests" —
doubles as the "is this atomic?" check at step 9.

**The judge — the LLM crosscheck (used at step 11 and again in step 4's
background check).** The one place the AI *checks* instead of *guesses*: it
extracts what the raw words asked for, and deterministic code diffs that
against what was produced. It runs inline in the deep track before committing,
and in the background after every FastRule commit — the same piece, so
improving it improves both. When it disagrees it renames a placeholder title
silently, and for bigger corrections either applies them (once it's proven
precise enough — see path B) or flags them for one-tap review.

**Decompose & atomicity (step 8, re-entered from step 9).** Breaks a thing
into atomic pieces using free deterministic rules, one bounded pass. Step 9's
FastRule is what *detects* an incomplete break: a "fragment" that still reads
as two requests is sent back here to split again (bounded, so it can't loop
forever).

**The honest fallbacks (inside step 9).** When a piece can't be parsed
cleanly, the system never invents: a task-shaped piece becomes a task of its
own words; an event-shaped piece with a real time-word but no title becomes a
plainly-named event; and an AI title using words the command never said is
dropped rather than committed.

**The background verifier & path B (step 4).** After a fast commit, the judge
reviews it behind the answer. Today it mostly *advises* (fixes are surfaced
for one tap) because auto-applying them once did more harm than good; the plan
(path B) is to measure the judge's correction precision and, once it's safely
high, let it auto-apply.

---

## 2 · Overview — the shape

One brain, two tracks, every worker an object:

```
Engine(config)                              # replaces the run_transcript() function
  ├── front  : FastRule(0.80)               # the fast-track front door
  ├── deep   : the Engine's stage list(config)           # the 7-stage pipeline, as an object
  └── verify : Verifier(deep.crosscheck)    # path-B background judge
```

The flow in one sentence: **FastRule is asked first; if it commits, the client
gets an instant answer while the LLM judge audits it in the background; if it
defers, the deep pipeline runs — where FastRule is asked again per fragment,
the LLM parses only what FastRule can't, the compound gates catch fragments
that were never atomic, and one LLM crosscheck judges the result.**

---

## 3 · End-to-end flow (pseudo-code)

### 3.1 Entry — track selection

```
Engine.run(prompt, source, trace, view):
    state = EngineState(raw=prompt, text=prompt, source, trace, view)
    state = ingest(state)              # coalesce queued cmds, strip stop-words,
                                       # drop trivial false-starts (not remembered)

    r = self.front.run(state.text)     # FastRule(0.80): commit or defer
    if r.committed:
        # ── FAST TRACK ──
        state.items = items_from(r.intents)
        state.parse_path = "fast"
        execute(state)                             # db write, ~ms, no LLM
        spawn_background(self.verify.review, state)# LLM judge runs BEHIND the answer
        return respond(state)                      # instant answer to the client

    # ── DEEP TRACK ──  (r.reason: below-threshold / not-atomic / …)
    return self.deep.run(state)
```

### 3.2 The deep pipeline — ordered stages + loop-back

```
the Engine's stage list.run(state):
    reentries = 0
    for stage in self.stages:          # Transcript→Segment→Decompose→Validate(text)
                                       # →Generate→Validate(objects)→Crosscheck→Label
        if stage.can_skip(state):      # deterministic self-skip (no LLM)
            continue
        state = stage.run(state, cfg)  # each stage's FROZEN contract

        if stage is self.crosscheck:                   # the judge can send us back
            blame = route(state.findings)              # deterministic blame-by-type
            if blame and reentries < BUDGET:
                reentries += 1
                append_mistake_context(state, blame)
                rewind_to(blame.stage); continue
    execute(state)                     # commit the deep-track objects
    return respond(state)
```

### 3.3 The stages that matter (the rest are the frozen contracts unchanged)

```
Segment.run(state):                    # brackets/markers free; else 1 schema-LLM call
    state.items = split_into(events, tasks, review)    # under-split when unsure

Decompose.run(state):                  # one bounded pass, recursion depth ≤ 2
    for item: item.subitems = split_times / split_tasks / quantity(item)

Generate.run(state):                   # rules-first per fragment; LLM only on residue
    for item in fragments(state):
        r = self.fragment.run(item.text)              # FastRule(0.60)
        if r.committed:            item.take(r.intents)          # RULES — no LLM
        elif r.reason in COMPOUND: item.needs_breakdown = True   # NOT atomic
        else:                      item.take(llm_parse(item))    # hard → 1 LLM call
    if any(needs_breakdown) and depth < 2: rewind_to(Decompose)  # bounded re-split
    # honest fallbacks: event_fallback, task_fallback, invention_guard

Validate.run(state):                   # ordered named rules; each fix → trace
    for rule in [past_date_bump, am_pm_fix, end_before_start, until_through,
                 weekly_start_day, cadence_round, observance_gate, …]:
        state.items, fixes = rule(state.items, state.text); state.record(fixes)

Crosscheck.run(state):                 # the LLM extracts, code judges
    said = llm_extract(state.raw)      # what the RAW words asked for
    state.findings = diff(said, state.items)          # missing / extra / wrong_field
```

### 3.4 Background verify on a fast commit (path B)

```
Verifier.review(state):                # same Crosscheck object as the deep track
    for f in self.crosscheck.run(state):
        if   f.tier == "title": rename_in_place(f)    # always
        elif self.apply:        apply_patch(f)        # once precision earns the flip
        else:                   advise(f)             # "worth a look" + 1-tap
    publish(verify_token)              # client polls / HUD shows it
```

---

## 4 · The object model

### 4.1 Component — the shared interface

```
class Component(Protocol):
    name: str
    def run(self, x) -> Result         # FastRule.run(prompt) · Stage.run(state)
```

FastRule is already a Component; stages become Components. The system is
uniformly composable.

### 4.2 Engine — the brain's entry (replaces `run_transcript`)

```
class Engine:
    def __init__(self, config):
        self.front  = FastRule(config.fast.threshold)      # 0.80
        self.deep   = the Engine's stage list(config)
        self.verify = Verifier(self.deep.crosscheck, config)
    def run(self, prompt, source, trace, view) -> Response   # §2.1
```

### 4.3 the Engine's stage list — the deep track as an object

```
class the Engine's stage list:
    def __init__(self, config):
        self.stages = [Transcript(cfg), Segment(cfg), Decompose(cfg),
                       Validate(cfg), Generate(cfg), Crosscheck(cfg), Label(cfg)]
        # NB: Validate runs TWICE — a text pass (run) before Generate and an
        # object pass (run_objects) after; the list is schematic
        self.crosscheck = <the Crosscheck stage>   # exposed; also the verifier
    def run(self, state) -> state                   # §2.2
```

### 4.4 Stage — one step, frozen contract in a class

```
class Stage:
    name: str
    def can_skip(self, state) -> bool               # deterministic-first self-skip
    def run(self, state, cfg) -> state              # THE FROZEN I/O CONTRACT
    def metric(self, gold) -> StageScore            # per-stage audit, self-scored
```

A stage **owns its sub-components**: `Validate` owns its ordered rule objects,
`Generate` owns the fragment `FastRule`. Replacing a weak stage = swapping one
object, contract intact. `test_engine_contracts.py` keeps pinning every
stage's exact I/O.

---

## 5 · The novel ideas, as structure

1. **Rules-first-per-fragment + atomicity** — `Generate` holds `FastRule(0.60)`;
   a fragment that still trips the compound gate is one Decompose didn't
   finish, so its abstain-reason routes it back for another split instead of a
   committed mangle. The LLM sees only the residue FastRule can't read.
2. **Crosscheck = one judge, two callers** — inline before a deep commit, and
   in the background over every fast commit. Improving the one object improves
   both — the leverage.
3. **Verifier (path B)** — wraps Crosscheck + the tiered patcher; the flip to
   auto-apply is one config gate, opened only when the crosscheck-correction
   precision metric earns it.
4. **Per-instance / per-context tuning** — every FastRule and Stage is built
   from config, so thresholds and rule sets are per-instance today and could
   be per-context (`FastRule(cfg.by_context["query"].threshold)`) tomorrow.

---

## 6 · Preserved vs. changed

**Config flags an object receives (Gil, 2026-09-07):** the observance gate in
`Validate` fires **only when observance is enabled** (settings flag
`observance.enabled`, honoured via `observance.is_enabled()` — which also
respects the `MACALENDAR_OBSERVANCE` test override). `Validate(cfg)` already
receives config, so the gate reads the flag per run; off ⇒ the gate is a
no-op and the AI may book on Shabbat/yom tov like any other time. Same for the
recurring-series skip. This is why the dataset harness runs observance off.

**Preserved exactly (sacred):** the 7 stage I/O contracts · `EngineState` (the
single inter-stage object) · `BRAIN_VERSION` / `CHAINS` / the trace contract ·
the response contract (message/actions/refresh/parse/corrections/trace/
memory_id/verify_token) · the offline + pending rules.

**Changed (mechanically):**

| now (function) | after (object) |
|---|---|
| `run_transcript(text, …)` | `Engine(cfg).run(text, …)` (a shim keeps the name for `server.py`) |
| stage functions | `Stage` classes, same `run(state, cfg)` |
| `fast_propose` inline gates | `FastRule` object (done) |
| per-item LLM parse in generate | `Generate.fragment = FastRule(0.60)` + atomicity routing |
| background-verify inline block | `Verifier` over `Crosscheck` |
| per-stage audit lines | `Stage.metric()` collected by the audit |

---

## 7 · Migration plan (behaviour-preserving first)

1. **Refactor, no behaviour change:** add `Component`/`Stage`, wrap the 7 stage
   functions as classes (pure delegation), wrap `run_transcript` as
   `Engine`/the Engine's stage list. Gate: the dataset board is **byte-identical** (the
   FastRule-refactor discipline).
2. **Measured design changes, each its own cycle:** cycle-10
   rules-first-per-fragment + atomicity routing; then the path-B `Verifier`.

Steps 1 are pure refactors (verified identical); step 2 is the authorized
design changes, measured.

---

## 8 · Open questions for Gil

1. **First move:** the pure object refactor alone (steps 1), verified
   identical, *then* cycle 10 — or fold cycle 10 in? _(Recommend: separate, so
   "did the refactor break something" never mixes with "did the new algorithm
   help".)_
   ok sure as you recommend.
2. **Name:** keep a thin `run_transcript` shim so `server.py`'s HTTP layer is
   untouched? _(Recommend: yes.)_
   ok.
3. **`Component`:** worth the shared `.run()` interface, or keep FastRule and
   Stage as separate shapes?
   Stage is the parent class or inteface to all the different components of the systems architecture?

