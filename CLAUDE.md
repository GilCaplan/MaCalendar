# Working on this project

Short version of the things that are easy to get wrong here. The architecture
lives in `DOCUMENTATION/SYSTEM.md` (and `SYSTEM_MAC.md` / `SYSTEM_IPHONE.md`);
this file is about the workflow.

## The shape of it

**`assistant.api` is the brain, and it is the only one.** It parses, executes
and self-checks every command, wherever the command came from. Four processes
run on the Mac, started by `Launch Calendar.command`:

    ollama serve                     the model, localhost:11434
    python -m assistant.api          THE BRAIN, 0.0.0.0:8080 (--tailscale)
    python -m assistant.thinking_hud the floating card, reads trace_bus.jsonl
    python -m assistant.main         the calendar GUI

**Both the GUI and the iPhone are clients of the API.** The GUI records audio,
posts the transcript to `127.0.0.1:8080/voice/text`, and renders the answer; the
phone does the same over Tailscale. `source` — `"mac"` or `"ios"` — is the only
difference between them, and it only labels the trace, the vocabulary
corrections and the command memory.

This is recent and worth respecting: the GUI used to have its own copy of the
whole pipeline, the two drifted, and every fix had to be written twice or the
surfaces disagreed. **Do not add parsing or execution to `pipeline.py`.** If a
behaviour needs to exist on the Mac, it belongs in `assistant/api/server.py`,
where the phone gets it too.

The HUD is a fourth process and talks to nothing: it tails
`~/.assistant_tools/trace_bus.jsonl`, which the API appends to. That is what
lets it float over a full-screen app with the calendar closed, and it is the
durable record the card's History view reads back.

`confirmation_level` no longer has any effect — the dialog belonged between
parse and execute, and both now happen in a process with no screen. The GUI
warns at startup if it is above 0.

## It never touches the internet

Whisper runs on the GPU from a cached model, the LLM is Ollama on localhost,
spaCy and the date recogniser are local, `pyluach` and `astral` are pure Python,
and the database is a file. `tests/unit/test_offline.py` blocks every
non-loopback socket and fails the build if that stops being true — it already
regressed once, when `mlx_whisper` was resolving its model against
huggingface.co on every start.

The exception is the phone reaching the Mac over Tailscale, which is a link
between two of your own machines rather than a dependency on a service.

## Personal data lives outside the repo

`~/.assistant_tools/` holds the calendar DB, the command memory, the personal
vocabulary and the event categories. **None of it is test data.** The vocabulary
is hand-curated and the command memory feeds the few-shot examples the parser
learns from, so writing junk into either quietly degrades the assistant.

Every store honours an environment override, and `tests/conftest.py` points all
four at a scratch directory *before* importing anything from `assistant` (the
paths are read at import time, so a fixture is too late):

    MACALENDAR_DB  MACALENDAR_MEMORY_DB  MACALENDAR_VOCAB  MACALENDAR_CATEGORIES

Set them in any script that exercises the pipeline. If you are unsure whether
something wrote to the real files, check: `md5 ~/.assistant_tools/vocab.json`
before and after.

**`MACALENDAR_TRACE_BUS` is the fifth**, and it was missed for a long time.
`trace_bus.jsonl` is the durable log the thinking card's History reads back, so
a script that leaves it alone publishes its commands into the record of what
you actually asked the assistant. The audit was doing exactly that — 89
synthetic commands per run, until the bus held more corpus than usage. Anything
driving the API programmatically should also post `"source": "test"`, which the
History filters out by default.

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
guards against. A test that builds the app wants routes, not models.

## Measuring a change to the assistant

Do not judge an NLU change by trying a couple of phrasings. The harness runs a
corpus of ~84 commands through the real path and reports accuracy by area and
by parse path:

    python -m scripts.audit_assistant                 # full, ~10 min
    python -m scripts.audit_assistant --limit 20      # smoke
    python -m scripts.audit_assistant --area tasks

It writes `DOCUMENTATION/ASSISTANT_AUDIT.md`. It runs against scratch databases
and a *copy* of the real vocabulary, so it measures your actual word list
without changing it. Re-run it after a parser change: twice now a fix has
quietly regressed something else, and the corpus caught it. It takes ~25 min
now that the self-check runs on every command, not the ~10 it used to.

Keep the conclusions in `DOCUMENTATION/ASSISTANT_AUDIT_SUMMARY.md` — the
generated report is overwritten on every run.

**Read the shape table with the sample size next to it.** Several rows are
n=1, and a 0% there is one command, not a trend. Two of them were chased as
real failures before anyone noticed they were the self-check overwriting a
correct answer rather than a parse problem at all.

`scripts/weekly_review.py` reports real usage rather than the corpus, and is
the honest instrument for "is it actually any good". It reports a **flag rate**
and refuses to compute an accuracy below three approvals: the ratio divides by
approvals, a thumbs-up is work with no reward, and with none of them the
formula reads 0% however well it did. It also drops verdicts that arrive in
bursts of five within three seconds — a backlog being cleared is not a
judgement, and 24 such rejections once put the headline at 9%.

## Things that have bitten before

- **Don't run the audit and the test suite at once.** Both load spaCy and torch,
  and the combination used to segfault. `tests/conftest.py` pins BLAS to one
  thread, which fixed it, but the audit does not.
- **The API reference is generated.** After adding or changing an endpoint:
  `python scripts/gen_api_reference.py`.
- **The API reloads itself; nothing else does.** It runs with `--reload`, so
  editing anything under `assistant/` restarts it (tests, scripts and
  DOCUMENTATION are excluded, or writing a test would bounce the server). The
  **calendar GUI and the thinking HUD do not** — restart them by hand, and
  remember that when a change "has no effect". The phone needs a reinstall
  (`xcrun devicectl device install app` is more reliable than Xcode's Run when
  the device is on Wi-Fi).

- **A UI test that never sends a mouse event tests nothing.** Three bugs in the
  HUD's history view shipped green: a signal connected straight to a slot that
  took the `checked` bool as its first argument, rows built as a `QPushButton`
  containing a layout (a button sizes to its text, so they collapsed to 15px),
  and both times the tests called the handler instead of clicking the control.
  Use `QTest.mouseClick` / `QTest.keyClicks`, and connect `clicked` through a
  lambda.
- **Deleting is destructive.** When the parser cannot identify what to delete,
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

## Conventions

Commit messages explain what was wrong and how it was found, not just what
changed. Branch rather than committing to `main`. `config.yaml` is gitignored;
mirror any new setting into `config.example.yaml`.
