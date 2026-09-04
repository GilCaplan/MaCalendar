# Working on this project

Short version of the things that are easy to get wrong here. The architecture
lives in `DOCUMENTATION/SYSTEM.md` (and `SYSTEM_MAC.md` / `SYSTEM_IPHONE.md`);
the engine's stage contracts live in `DOCUMENTATION/ENGINE.md`; this file is
about the workflow.

## The shape of it

**`assistant.api` is the brain's front door, and `assistant.engine` is the
brain.** The API server receives every command, wherever it came from, and
hands it to the engine — which parses, executes and checks it. Four processes
run on the Mac, started by `Launch Calendar.command`:

    ollama serve                     the model, localhost:11434
    python -m assistant.api          THE BRAIN, 0.0.0.0:8080 (--tailscale)
    python -m assistant.thinking_hud the floating card, reads trace_bus.jsonl
    python -m assistant.main         the calendar GUI

**Both the GUI and the iPhone are clients of the API.** The GUI records audio,
posts the transcript to `127.0.0.1:8080/voice/text`, and renders the answer;
the phone does the same over Tailscale. `source` — `"mac"` or `"ios"` — is the
only difference between them, and it only labels the trace, the vocabulary
corrections and the command memory.

Two rules keep this true, each bought with real drift:

- **Do not add parsing or execution to `pipeline.py`.** The GUI used to have
  its own copy of the whole pipeline, the two drifted, and every fix had to be
  written twice or the surfaces disagreed. If a behaviour needs to exist on
  the Mac, it belongs in the engine, where the phone gets it too.
- **Do not add parsing or execution to `server.py` either.** That is where the
  old brain accumulated ~800 lines of interleaved heuristics that took a
  rewrite to untangle. `server.py` is HTTP: routes, request shapes, CRUD. The
  brain is `assistant/engine/`.

The HUD is a fourth process and talks to nothing: it tails
`~/.assistant_tools/trace_bus.jsonl`, which the engine appends to. That is what
lets it float over a full-screen app with the calendar closed, and it is the
durable record the card's History view reads back.

`confirmation_level` no longer has any effect — the dialog belonged between
parse and execute, and both now happen in a process with no screen. The GUI
warns at startup if it is above 0.

## Working on the engine

`assistant/engine/` is the 7-step deep track: transcript repair → segment →
decompose → validate → generate → crosscheck → label, with a fast track that
commits a confident rule parse instantly. `DOCUMENTATION/ENGINE.md` is the
canonical contract reference — open it before touching any stage.

- **Stage I/O contracts are frozen.** `tests/unit/test_engine_contracts.py`
  pins them. Fix a weak stage inside its own module, against its own tests —
  never by reshaping `EngineState`, editing the orchestrator, or reaching into
  another stage. If the contract itself seems wrong, that is a design change:
  take it to TASKS.md, don't slip it into a fix.
- Each stage has its own test file (`test_engine_<stage>.py`) and its own
  trace step; the audit reports per-stage lines. A weak stage is found by its
  line, not by staring at the headline number.
- `scripts/engine_stage_check.py --stage <name>` re-verifies one stage in
  isolation against the real local LLM (Ollama-guarded, scratch stores,
  `source: "test"`).
- Deterministic-first everywhere: a stage may only call the LLM when its
  deterministic reading found nothing, and every LLM call is
  schema-constrained and grounded on the raw transcript.

## The review panel is downstream of the pipeline

The thinking panel and the iOS timeline draw a command's chain of thought from
its trace — so **the panel is downstream of the pipeline's shape, and a
revamp that does not update it draws the old system's chain for the new one.**
`assistant/trace.py` holds the single source of truth: `BRAIN_VERSION` (the
key the panel matches its render format to, stamped on every response and
trace-bus payload) and `CHAINS` (the ordered `(stage, label)` spec per version
that matches the explorer diagram).

When you change the pipeline's shape — add, rename or remove a stage; change
the order; split or merge steps — do all of these in the same change:

1. **Bump `BRAIN_VERSION`** so an old trace still renders in its old format.
2. **Update `CHAINS`** with the new version's chain, and any new stage's icon
   in `thinking_panel._STAGE_ICONS` (ship the `.svg`).
3. **Update the panel render** (`thinking_panel.py` + iOS `ThinkingView`) and
   the explorer diagram, per `DOCUMENTATION/ENGINE.md`'s render section.

**If you miss it, the build catches you.** `tests/unit/test_panel_agreement.py`
ties the engine's stage set, the panel's icons and `CHAINS` together and goes
red naming what to update; `test_engine_flow.py` pins that the version is
stamped on every command. Treat a red there like a red artifact-claim: it is
the panel telling you it no longer matches the machine.

## It never touches the internet

Whisper runs on the GPU from a cached model, the LLM is Ollama on localhost,
spaCy and the date recogniser are local, `pyluach` and `astral` are pure
Python, and the database is a file. `tests/unit/test_offline.py` blocks every
non-loopback socket and fails the build if that stops being true — it already
regressed once, when `mlx_whisper` was resolving its model against
huggingface.co on every start.

The exception is the phone reaching the Mac over Tailscale, which is a link
between two of your own machines rather than a dependency on a service.

## Personal data lives outside the repo

`~/.assistant_tools/` holds the calendar DB, the command memory, the personal
vocabulary and the event categories. **None of it is test data.** The
vocabulary is hand-curated and the command memory feeds the review flows, so
writing junk into either quietly degrades the assistant.

Every store honours an environment override, and `tests/conftest.py` points
all four at a scratch directory *before* importing anything from `assistant`
(the paths are read at import time, so a fixture is too late):

    MACALENDAR_DB  MACALENDAR_MEMORY_DB  MACALENDAR_VOCAB  MACALENDAR_CATEGORIES

Set them in any script that exercises the engine. If you are unsure whether
something wrote to the real files, check: `md5 ~/.assistant_tools/vocab.json`
before and after.

**`MACALENDAR_TRACE_BUS` is the fifth**, and it was missed for a long time.
`trace_bus.jsonl` is the durable log the thinking card's History reads back,
so a script that leaves it alone publishes its commands into the record of
what you actually asked the assistant. Anything driving the API
programmatically should also post `"source": "test"`, which the History
filters out by default.

## Testing

    pytest tests/unit                 # fast, no model needed
    pytest tests/integration          # needs Ollama; skips without it
    pytest tests/                     # what CI runs

Integration tests must skip when Ollama is not running — copy the `pytestmark`
guard from `tests/integration/test_ollama_intent.py`. CI has no Ollama, so a
test that fails instead of skipping turns the build red.

`conftest.py` sets `MACALENDAR_NO_WARMUP=1`: `create_app()` otherwise spawns a
thread that unzips Whisper and spaCy while the suite runs, and two model loads
on separate threads segfault the interpreter — the same collision the BLAS pin
guards against. The engine reads the same flag before starting any daemon
thread. A test that builds the app wants routes, not models.

## Measuring a change to the assistant

Do not judge an NLU change by trying a couple of phrasings. The harness runs a
corpus of ~89 commands through the real path and reports recall, precision and
accuracy by area and by parse path (`fast` / `deep`):

    python -m scripts.audit_assistant                 # full
    python -m scripts.audit_assistant --limit 20      # smoke
    python -m scripts.audit_assistant --area tasks

It writes `DOCUMENTATION/ASSISTANT_AUDIT.md` — overwritten every run, so
conclusions go in `DOCUMENTATION/ASSISTANT_AUDIT_SUMMARY.md`. That file also
holds the engine's baseline: the retired brain's last numbers (run 7, 98%
exact match), which is what a rebuilt stage has to beat. `--memory` replays
against a *copy* of the real history, `--memory-k N` sets the retrieval count;
run 7 measured no k=4 effect, so the engine defaults memory injection off.

**Read the shape table with the sample size next to it.** Several rows are
n=1, and a 0% there is one command, not a trend.

`scripts/weekly_review.py` reports real usage rather than the corpus, and is
the honest instrument for "is it actually any good". It reports a **flag
rate** and refuses to compute an accuracy below three approvals; it also
drops verdicts that arrive in bursts (a backlog being cleared is not a
judgement).

## Things that have bitten before

- **Don't run the audit and the test suite at once.** Both load spaCy and
  torch, and the combination used to segfault. `tests/conftest.py` pins BLAS
  to one thread, which fixed it, but the audit does not. The same applies to
  any two model-loading jobs side by side.
- **The API reference is generated.** After adding or changing an endpoint:
  `python scripts/gen_api_reference.py`.
- **The API reloads itself; nothing else does.** It runs with `--reload`, so
  editing anything under `assistant/` restarts it (tests, scripts and
  DOCUMENTATION are excluded). The **calendar GUI and the thinking HUD do
  not** — restart them by hand, and remember that when a change "has no
  effect". The phone needs a reinstall (`xcrun devicectl device install app`
  is more reliable than Xcode's Run when the device is on Wi-Fi).
- **A UI test that never sends a mouse event tests nothing.** Three bugs in
  the HUD's history view shipped green because tests called handlers instead
  of clicking controls. Use `QTest.mouseClick` / `QTest.keyClicks`, and
  connect `clicked` through a lambda.
- **Deleting is destructive.** When the engine cannot identify what to delete,
  empty slots — which surface as "I couldn't find …" — are the right answer.
  Guessing is not.

## Recurring events

`recurrence` is only ever `daily`, `weekly` or `monthly`. Anything a speaker
says that is not one of those gets rounded to one that is, and the rounding is
announced in the reply rather than done quietly — "every other tuesday" became
one event before anyone noticed, and "every weekday" books Shabbat.

**"until" excludes the day it names; "through" and "including" keep it.**
English supports both readings, so the project picks one and applies it
everywhere rather than guessing per sentence. "until the end of September" is
inclusive — that phrase names the final day, not a boundary past it.

A weekly series starts on the soonest weekday the sentence names, not on
whatever date the model returned; it used to put "every sunday and tuesday" on
a Wednesday.

**Series skip Shabbat and yom tov**, bounded by candle lighting and tzeit at
the configured location (`hebrew_calendar` / `observance` settings in
config.yaml — latitude, longitude, timezone), not by midnight. Candle lighting
in Jerusalem is 18:43 in September and 16:20 in December, so a 19:00 Friday
event is outside Shabbat in one and inside it in the other; a date-only rule
gets a whole season wrong.

Three exceptions, each with a reason:

- **Meals are allowed** — they are what the day is for. Unless it is a fast,
  where a meal is the one thing that must not be booked; Yom Kippur is both
  and the fast wins.
- **A series anchored on Shabbat keeps it.** A Saturday shiur was put there on
  purpose, and skipping every instance would leave a weekly series with one
  event.
- **Nothing is skipped if observance cannot be computed.** A series quietly
  losing days is worse than one landing where it should not.

The engine adds a fourth rule for what *it* creates (never for manual edits):
a one-off event inside Shabbat / yom tov must be leyning, a meal or davening,
and on a fast day a meal must not be booked before the fast ends. The refusal
is explained in the reply — see the observance gate in `ENGINE.md`.

## The published pages are downstream of the code

`DOCUMENTATION/artifacts/*.html` are the explainers published to public URLs,
and they quote constants from the code. Those drift.
**`tests/unit/test_artifact_claims.py` enforces the agreement**, reading each
value out of the code and asserting the page says the same thing. If you
change a constant a page quotes, that test goes red and names the file to
edit. If you add a claim to a page, add its check.
`DOCUMENTATION/ARTIFACT_BUILDER.md` carries the full table and layering rules,
including: **no personal detail on a published page** (the check treats any
vocabulary word as a leak unless declared in `artifacts/public_words.txt`),
and **a measured number must cite a run that still exists**
(`ASSISTANT_AUDIT_SUMMARY.md`, never the overwritten report).

## Where the plan lives

`DOCUMENTATION/TASKS.md` is the tracker and carries the current order of play
at the bottom — read it before picking up work, and move a row rather than
starting a parallel list. `DOCUMENTATION/MODELS.md` is the canonical answer to
which models do what. `DOCUMENTATION/ENGINE.md` is the engine's stage-contract
reference. `DOCUMENTATION/ARTIFACT_BUILDER.md` is the brief for the published
explainer pages.

## Conventions

Commit messages explain what was wrong and how it was found, not just what
changed. Branch rather than committing to `main`. `config.yaml` is gitignored;
mirror any new setting into `config.example.yaml`.
