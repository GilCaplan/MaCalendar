# The `assistant` CLI — infrastructure health

`python -m assistant.cli` (console script: `assistant`). It is an
**infrastructure health harness, not a quality harness** — it never asks "is
the assistant smart / accurate". It answers one question: **is every layer of
the stack wired and healthy, so the infrastructure is correctly in place?**
(Quality is measured separately — `dataset/DATASET.md`.)

    assistant doctor              # check every layer, green/red summary
    assistant check <layer>       # one layer: llm | storage | engine | panel | macos | external
    assistant say "<command>"     # diagnostic: run one command, show the chain of thought
    assistant endpoints           # list the whole API surface

Each line is `✔` healthy · `✘` broken/not-running · `•` degraded/unverifiable ·
`ℹ` informational. `doctor` exits non-zero if any layer is `✘`.

## The six layers

| # | Layer | What "healthy" means | How it's checked |
|---|---|---|---|
| 1 | **llm** | the model the API talks to is reachable | Ollama: `/api/tags` + model pulled; cloud: api key present. Plus the local spaCy grammar model loads. (STT is exercised only on a real `/voice` audio call, so it's noted, not asserted.) |
| 2 | **storage** | the databases and trace log are connected + writable | open calendar.db read-only (events/todos tables), memory.db present, trace-log dir writable |
| 3 | **engine** | each stage of THIS engine version is wired, and the live path answers | every stage module imports; `CHAINS[BRAIN_VERSION]` is defined; a live read-only probe returns `brain=BRAIN_VERSION` with a coherent trace. `--deep` points at the per-stage gate |
| 4 | **panel** | the thinking HUD is running and beating | the HUD's heartbeat is fresh (< 30s); trace log readable |
| 5 | **macos** | the calendar GUI is beating; hosted-calendar sync valid if configured | the GUI's heartbeat is fresh; Microsoft Graph auth if a hosted calendar is set (else local-only, informational) |
| 6 | **external** | the phone / other clients have checked in; API reachable to them | per-client `/heartbeat` last-seen; Tailscale address present |

## Heartbeats — how the disconnected surfaces become checkable

The HUD, the GUI and the phone are separate processes/devices that expose
nothing to probe. Each emits a lightweight beat (`assistant/heartbeat.py`):
the HUD and GUI write a timestamped status file under
`~/.assistant_tools/heartbeats/`; a device POSTs `/heartbeat`. The doctor reads
"last seen" to tell *connected and healthy* from *maybe running*. A surface
that isn't up reports `✘` — that is correct, not a bug: launch it (or the whole
stack via `Launch Calendar.command`) and it goes green.

_iOS note: the `/heartbeat` endpoint exists; the iOS app posts it once its
client is updated to. Until then, layer 6 shows "no client checked in yet"._

## The engine layer is version-tied — update it when the engine changes

Layer 3 reads `assistant/trace.BRAIN_VERSION` and the stage list, so it is
**specific to the current engine design**. If the pipeline is redesigned:

1. bump `BRAIN_VERSION` and update `CHAINS` (same as the review panel — see
   CLAUDE.md "The review panel is downstream of the pipeline");
2. update the stage list in `cli.check_engine` if stages were added/renamed.

`tests/unit/test_cli.py` guards that `check_engine`'s stage list matches the
engine's real stages, so a redesign that forgets to update the doctor fails the
build — the same discipline as `test_panel_agreement`.
