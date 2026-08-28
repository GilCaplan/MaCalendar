# Working on this project

Short version of the things that are easy to get wrong here. The architecture
lives in `DOCUMENTATION/SYSTEM.md` (and `SYSTEM_MAC.md` / `SYSTEM_IPHONE.md`);
this file is about the workflow.

## The shape of it

The Mac is the brain. Two processes run on it: the calendar GUI
(`python -m assistant.main`) and the Flask API the phone talks to
(`python -m assistant.api --tailscale`). `Launch Calendar.command` starts both.
The iPhone app is a client — it records audio and renders; every decision is
made on the Mac. The only network peer either app has is the other one, over
Tailscale.

Because they are separate processes, they cannot share state in memory. Where
the GUI needs to know what the API did — the thinking panel showing a command
that came from the phone — it goes through `assistant/trace_bus.py`.

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

## Testing

    pytest tests/unit                 # fast, no model needed
    pytest tests/integration          # needs Ollama; skips without it
    pytest tests/                     # what CI runs

Integration tests must skip when Ollama is not running — copy the `pytestmark`
guard from `tests/integration/test_ollama_intent.py`. CI has no Ollama, so a
test that fails instead of skipping turns the build red.

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
quietly regressed something else, and the corpus caught it.

Keep the conclusions in `DOCUMENTATION/ASSISTANT_AUDIT_SUMMARY.md` — the
generated report is overwritten on every run.

## Things that have bitten before

- **Don't run the audit and the test suite at once.** Both load spaCy and torch,
  and the combination used to segfault. `tests/conftest.py` pins BLAS to one
  thread, which fixed it, but the audit does not.
- **The API reference is generated.** After adding or changing an endpoint:
  `python scripts/gen_api_reference.py`.
- **Restart the Mac app** after changing anything under `assistant/` — it does
  not reload. The phone needs a reinstall (`xcrun devicectl device install app`
  is more reliable than Xcode's Run when the device is on Wi-Fi).
- **Deleting is destructive.** When the parser cannot identify what to delete,
  empty slots — which surface as "I couldn't find …" — are the right answer.
  Guessing is not.

## Conventions

Commit messages explain what was wrong and how it was found, not just what
changed. Branch rather than committing to `main`. `config.yaml` is gitignored;
mirror any new setting into `config.example.yaml`.
