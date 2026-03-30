# assistant_tools

A **voice-controlled calendar assistant** for macOS. Speak a command (e.g. "Add a standup Monday at 9 and a review Friday at 3, done"), the app transcribes it, parses the intent with a local LLM, confirms, and saves to a SQLite-backed PyQt6 calendar UI.

---

## How it works

```
Hotkey (Cmd+Shift+Space) or Mic button
  → AudioCapture (records until stop keyword / button re-press / 20s silence)
  → STT (faster-whisper local or Google Cloud fallback)
  → _strip_stop_keyword()  (strips "done"/"end"/"execute" etc. from tail)
  → OllamaIntentParser (local LLM → JSON → Pydantic validation)
      supports single:  {"action": "...", "parameters": {...}}
      supports multi:   {"actions": [{"action": "...", "parameters": {...}}, ...]}
  → ConfirmationHandler (macOS native dialog, level 0–3)
  → Action.execute() loop  (create / update / delete → CalendarDB → SQLite)
  → TTS feedback (macOS `say`) + UI toast + calendar refresh
```

Pipeline pushes `(status, message)` tuples to `status_queue`; `CalendarWindow` drains it every 100ms and shows the message as a toast.

---

## Key files

| File | Role |
|------|------|
| `assistant/main.py` | Entry point — wires everything, launches PyQt6 window |
| `assistant/pipeline.py` | Core orchestrator; multi-action loop; `stop_recording()` |
| `assistant/config.py` | Pydantic config schema; supports YAML + env var overrides |
| `assistant/db.py` | `CalendarDB` — SQLite at `~/.assistant_tools/calendar.db` |
| `assistant/actions/__init__.py` | `ActionRegistry` Borg singleton + `@register` decorator |
| `assistant/actions/base.py` | `BaseAction` + `BaseIntent` abstract base classes |
| `assistant/actions/calendar/action.py` | `CreateEventAction`, `UpdateEventAction`, `DeleteEventAction` |
| `assistant/actions/calendar/intent.py` | `CalendarIntent`, `UpdateEventIntent`, `DeleteEventIntent` |
| `assistant/intent/parser.py` | Calls Ollama; returns `list[(action_name, intent)]`; handles single + multi-action JSON |
| `assistant/audio/capture.py` | `AudioCapture` — records until 20s silence, `stop()` call, or hard cap (120s) |
| `assistant/stt/whisper_stt.py` | `WhisperSTT` — faster-whisper, Apple Silicon optimized |
| `assistant/hotkey.py` | `HotkeyListener` — global shortcut via pynput |
| `assistant/confirmation/handler.py` | macOS `osascript` dialogs at 4 confirmation levels |
| `assistant/tts/speaker.py` | Wraps macOS `say` command |
| `assistant/calendar_ui/window.py` | `CalendarWindow` — month/week views, dark mode toggle, import button, live voice toasts |
| `assistant/calendar_ui/styles.py` | Light + dark palette constants + `get_app_style(dark)` |
| `assistant/calendar_ui/month_view.py` | Month grid; `apply_theme(dark)` |
| `assistant/calendar_ui/week_view.py` | Week view with time axis; `apply_theme(dark)` |
| `assistant/calendar_ui/sidebar.py` | Mini-calendar sidebar; `apply_theme(dark)` |
| `assistant/calendar_ui/importer.py` | ICS parser + macOS Calendar scanner + `import_events()` |
| `assistant/calendar_ui/event_dialog.py` | Create/edit dialog with 🗑 Delete button (edit mode only) |
| `assistant/exceptions.py` | Custom exception hierarchy |
| `config.yaml` | Active configuration |
| `config.example.yaml` | Template — copy to `config.yaml` to get started |
| `Launch Calendar.command` | Double-clickable macOS launcher (auto-activates `.venv`) |

---

## Voice recording controls

| Method | Effect |
|--------|--------|
| Press hotkey / mic button | Start recording |
| Press mic button again | Stop recording immediately |
| Say `end`, `done`, `execute`, `set event`, `set events`, `stop`, `that's it` | Stop recording; keyword stripped before parsing |
| 20 seconds of silence | Auto-stop (configurable via `audio.silence_duration_sec`) |
| 120 seconds elapsed | Hard cap (configurable via `audio.max_recording_sec`) |

Multi-event example: *"Create a standup Monday at 9am and a team review Friday at 3pm, done"*
Update example: *"Move my standup to 10am"*
Delete example: *"Cancel the team review on Friday"*

---

## Adding a new voice action (plugin system)

1. Create `assistant/actions/<name>/` with an `__init__.py`
2. Define `<Name>Intent(BaseIntent)` with Pydantic fields
3. Define `<Name>Action(BaseAction)` with the `@register` decorator
4. Implement `execute(intent, config) -> str` (returns a TTS confirmation string)
5. Import the module in `assistant/main.py`

No changes to the pipeline or intent parser needed — Ollama learns about the new action automatically from the registry.

---

## External dependencies (must be running)

- **Ollama** — `ollama serve` (default: `http://localhost:11434`)
- **Ollama model** — must match `config.yaml → ollama.model`; pull with `ollama pull llama3.2:3b`
- **Whisper model** — auto-downloaded on first run (~74MB for `base`)

---

## Configuration

`config.yaml` (copy from `config.example.yaml`). Key fields:

```yaml
stt_engine: "whisper"         # or "google"
ollama:
  model: "llama3.2:3b"        # must match a pulled Ollama model
confirmation_level: 1         # 0=none 1=simple 2=full 3=editable
audio:
  silence_threshold: 0.01
  silence_duration_sec: 20.0  # auto-stop after 20s of silence
  max_recording_sec: 120      # hard cap
```

Env var overrides: `ASSISTANT_OLLAMA_MODEL`, `ASSISTANT_STT_ENGINE`, `ASSISTANT_CONFIRMATION`

Logs: `~/.assistant_tools/assistant.log`

---

## Setup (first run)

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Or just double-click **`Launch Calendar.command`** — it handles venv activation automatically.

---

## Not yet wired up

- Microsoft Graph API sync (auth + client code exists in `assistant/actions/calendar/`)
