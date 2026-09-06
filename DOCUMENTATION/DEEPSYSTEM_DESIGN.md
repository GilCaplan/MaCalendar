# DeepSystem — object-based structure (design for review, 2026-09-07)

Proposal only. Nothing built until Gil approves. The goal: make the brain
object-based like `FastRule`, and make the session's novel ideas
(two-instance FastRule, rules-first-per-fragment, atomicity detection,
crosscheck-as-single-judge, path-B verify, per-instance tuning) **structural**
rather than inline logic. The frozen stage I/O contracts are preserved
exactly — this wraps them in classes, it does not reshape them.

## The shape: one brain, two tracks, both objects

```
Engine(config)                         # replaces the run_transcript() function
  .run(prompt, source, trace, view) -> Response
  │
  ├── front  : FastRule(cfg.fast.threshold)        # 0.80 — the front door
  ├── deep   : DeepSystem(config)                  # the 7-stage pipeline object
  └── verify : Verifier(deep.crosscheck, cfg)      # path B (background + inline)

  run(prompt):
     r = front.run(prompt)
     if r.committed:                # FAST TRACK
        commit(r.intents)
        verify.in_background(state) # crosscheck judges every fast commit
        return answer
     return deep.run(state)         # DEEP TRACK
```

Every worker in the system now shares one tiny interface — a **Component**:

```
class Component(Protocol):
    name: str
    def run(self, x) -> Result      # FastRule.run(prompt), Stage.run(state), ...
```

FastRule is already a Component. Stages become Components. The system is
uniformly composable.

## DeepSystem — the deep track as an object

```
class DeepSystem:
    def __init__(self, config):
        self.cfg = config
        self.stages = [               # ordered; each an independent object
            Transcript(cfg), Segment(cfg), Decompose(cfg),
            Validate(cfg), Generate(cfg), Crosscheck(cfg), Label(cfg),
        ]
        self.crosscheck = self.stages[5]   # exposed: it is also the verifier

    def run(self, state) -> state:
        for stage in self.stages:
            if stage.can_skip(state):      # deterministic self-skip, unchanged
                continue
            state = stage.run(state, self.cfg)
            state = self._maybe_loopback(state)   # crosscheck blame → re-enter
        return state
```

`_maybe_loopback` is the existing crosscheck router (blame → re-run the
blamed stage with the mistake in context), now a method, with the same
bounded re-entry budget.

## Stage — each step, frozen contract wrapped in a class

```
class Stage:
    name: str                         # "segment", "decompose", …
    def can_skip(self, state) -> bool # the deterministic-first self-skip
    def run(self, state, cfg) -> state  # THE FROZEN I/O CONTRACT — unchanged
    def metric(self, gold) -> StageScore  # per-stage accuracy/latency (audit)
```

- Same `run(state, cfg) -> state` signature every stage already has —
  `test_engine_contracts.py` keeps pinning the exact I/O fields.
- A stage OWNS its sub-components: `Validate` holds its ordered list of named
  rule objects (past_date_bump, until_exclusive, the observance gate…);
  `Generate` holds the fragment FastRule (below). Replacing a weak stage =
  swapping one object, contract intact.
- `metric()` makes the per-stage audit object-based too — each stage scores
  itself; the audit just collects them.

## The novel ideas, now structural

### 1. Rules-first-per-fragment + atomicity detection (the cycle-10 vision)

`Generate` holds a second FastRule instance and uses it per fragment:

```
class Generate(Stage):
    def __init__(self, cfg):
        self.fragment = FastRule(cfg.fragment.threshold)   # 0.60
    def run(self, state, cfg):
        for item in state.items:                # fragments from Decompose
            r = self.fragment.run(item.text)
            if r.committed:
                item.take(r.intents)            # RULES parsed it — no LLM
            elif r.reason in ("strong-compound", "mixed-mode-compound"):
                item.needs_breakdown = True     # NOT atomic → back to Decompose
            else:
                item.take(self._llm_parse(item))# genuinely hard → one LLM parse
        return state
```

The gates inside FastRule double as the **atomicity check** (Gil's point):
a "fragment" that still trips the compound gate is one Decompose didn't
finish, so it routes back for another (bounded) split instead of committing
a mangle. The LLM is called only on the residue FastRule can't read.

### 2. Crosscheck = the single universal judge

`Crosscheck` is one object with two callers:
- **inline** in `DeepSystem.run` — judges the assembled deep-track objects
  before commit;
- **background** via `Verifier` — judges every FastRule fast-commit.

Improving `Crosscheck` improves both at once — that is the leverage.

### 3. Verifier (path B — verify-and-auto-update, safely)

```
class Verifier:
    def __init__(self, crosscheck, cfg):
        self.crosscheck = crosscheck
        self.apply = cfg.self_check_apply     # off until crosscheck precision earns it
    def review(self, state):                  # runs on a fast commit
        findings = self.crosscheck.run(state)
        for f in findings:
            if f.tier == "title":  self._rename(f)          # always
            elif self.apply:       self._apply(f)           # add/remove when trusted
            else:                  self._advise(f)          # "worth a look" otherwise
```

The flip to `apply=True` is gated on the crosscheck-correction-precision
metric (the path-B loop target). Same object, so the loop improves the judge
and the auto-updater together.

### 4. Per-instance / per-context tuning

Because FastRule and every Stage are built from config, thresholds and rule
sets are per-instance — and could be per-context:

```
front            = FastRule(cfg.fast.threshold)      # 0.80
generate.fragment= FastRule(cfg.fragment.threshold)  # 0.60
# future: FastRule(cfg.by_context["query"].threshold) etc.
```

## Preserved exactly (sacred)

- The **7 stage I/O contracts** — frozen; classes wrap, never reshape.
- **EngineState** — the single inter-stage object.
- **BRAIN_VERSION / CHAINS / trace contract** — the panel stays downstream.
- The **response contract** (message/actions/refresh/parse/corrections/
  trace/memory_id/verify_token) and the offline/pending rules.

## What changes (mechanically)

| now (function) | after (object) |
|---|---|
| `run_transcript(text, …)` | `Engine(cfg).run(text, …)` |
| stage functions `stage.run(state)` | `Stage` classes, same `run(state,cfg)` |
| `fast_propose` inline gates | `FastRule` object (done) |
| per-item LLM parse in generate | `Generate.fragment = FastRule(0.60)` + atomicity routing |
| background verify inline block | `Verifier` object over `Crosscheck` |
| per-stage audit lines | `Stage.metric()` collected by the audit |

## Migration (if approved) — behaviour-preserving, stage by stage

1. Introduce `Component`/`Stage` base + wrap the 7 existing stage functions
   as classes (pure delegation) — verify the dataset board is byte-identical.
2. `Engine`/`DeepSystem` objects wrapping `run_transcript` — identical board.
3. THEN the behavioural changes as their own measured cycles: cycle-10
   rules-first-per-fragment + atomicity routing; path-B Verifier.

Steps 1–2 are pure refactors (verified identical, like the FastRule refactor);
step 3 is the authorized design changes, each measured.

## Open questions for Gil

1. Scope of the first move: the pure object refactor (steps 1–2, no behaviour
   change) as one integration, THEN cycle 10 — or fold cycle 10 in?
2. `Engine` vs keep the name `run_transcript` as a thin wrapper for the API
   (server.py calls it) — I'd keep a `run_transcript` shim so the HTTP layer
   is untouched.
3. Is `Component` (the shared `.run()` interface) worth it, or keep FastRule
   and Stage as separate shapes?
