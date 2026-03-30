# MaCalendar Assistant System State

A **voice-controlled, privacy-first calendar and task assistant** for macOS. This document serves as the "brain" for the project, allowing any AI developer or assistant to resume work with full context.

## 🚀 Recent Core Improvements (Current Build)

- **Todo Integration (Tasks View)**: Added a full Apple Reminders-style **Tasks panel** as a fourth view (alongside Month/Week/Day). Features:
  - Two sections: **Today** and **General** task lists
  - **🔄 Sync Today** button — pulls today's calendar events into the Today list as tasks instantly
  - Inline editing (click title to edit), circular checkboxes, hover-to-reveal delete, `+ New Task` row
  - **Voice CRUD**: create (single and multi-task), complete, delete, update, query — all via voice
  - **Context-aware mic**: switching to Tasks tab sets `pipeline.current_view = "todo"`, which prepends `[TASKS VIEW]` to the transcript so the LLM strongly prefers todo actions for ambiguous phrases
  - **Anaphoric memory** for tasks: "delete it", "mark that done" resolve to the last touched task
  - Calendar sync: `db.sync_calendar_to_todos()` pulls events; `source='calendar_sync'` column protects manual tasks from being wiped on re-sync
  - Config section `todo.sync.mode` persists sync preference across launches
- **Day View & Morning Briefing**: Added a full hourly **Day view** (single-date timeline) alongside Month/Week. Features a live red current-time indicator and a **🌅 Brief Me** button that reads today's full schedule aloud via TTS. Voice queries like *"What does my day look like?"* or *"When is my first meeting?"* automatically switch to the Day view and speak the answer.
- **Real-Time Streaming STT**: Modified `AudioCapture` to support background chunking. The pipeline now performs incremental transcription every 2.5s, allowing pro-active detection of stop-keywords (e.g., "execute", "done") to terminate the microphone mid-speech for instant responsiveness.
- **Universal LLM Intent Parser**: Refactored the core parser to support four backends: **Ollama (local)**, **OpenAI**, **Google Gemini**, and **Anthropic Claude**. The engine is routed via `config.llm_engine`.
- **Integrated Settings UI**: Replaced cluttered toolbar buttons with a single ⚙️ Settings gear. It opens a native popup for:
  - Toggling **Auto-Approve** (autonomous mode).
  - Selecting from all **macOS System Voices** (native list).
  - Adjusting **Talking Speed** (WPM) and **Mute**.
  - **Live Audio Testing** button.
- **Context Memory (Anaphora)**: The assistant now retains the ID of the most recently created or modified event/task. Users can use pronouns like *"Delete **it**"* or *"Move **that event** to 5pm"* for fluid conversation.
- **Fuzzy Token Matching**: Refactored event lookup to use token-based fuzzy scoring. This handles LLM hallucinations or trailing transcription words (like "...done") that aren't part of the event title.
- **Security & Defense**: Implemented a **Prompt Injection Defense** layer that sanitizes transcripts before LLM submission to prevent system-prompt poisoning via voice.

---

## 🛠 Project Architecture

### Data Flow
```
Hotkey (Cmd+Shift+Space)
  → AudioCapture (records with 2.5s streaming window)
  → stream_checker() (Detects 'execute'/'done' → self.stop_recording())
  → [TASKS VIEW] prefix injected if pipeline.current_view == "todo"
  → Universal IntentParser (Ollama/OpenAI/Gemini/Claude → JSON)
  → ConfirmationHandler (Auto-Approve Check → level 0/1)
  → Action.execute() (Create/Update/Delete/Query + Memory Tracking)
  → action.view_switch? → Pipeline sends STATUS_SWITCH_TODAY / STATUS_SWITCH_TODO (or "refresh")
  → TTS Speaker (macOS 'say' with speed/voice/mute params)
  → DB persistence (SQLite) + UI Month/Week/Day/Tasks Refresh
```

### Key Components
- `assistant/pipeline.py`: Orchestrates the streaming STT and LLM handshake. Tracks `current_view` to inject context into transcripts. Checks `action.view_switch` after execution to signal UI view changes.
- `assistant/intent/parser.py`: Unified factory for local and cloud LLM providers.
- `assistant/actions/calendar/action.py`: Contains match logic, contextual memory hooks, and `QueryScheduleAction`.
- `assistant/actions/todo/action.py`: Five todo actions (create/complete/delete/update/query) with fuzzy matching and anaphoric memory. `CreateTodoAction` supports `titles: List[str]` for multi-task voice creation.
- `assistant/actions/todo/intent.py`: Pydantic intent models for todo voice commands.
- `assistant/actions/base.py`: `BaseAction` base class. Optional `view_switch: ClassVar[Optional[str]]` on any action signals the window to switch views post-execution.
- `assistant/actions/__init__.py`: ActionRegistry Borg singleton. System prompt now includes a `[TASKS VIEW]` context note that biases todo routing when in Tasks tab.
- `assistant/calendar_ui/window.py`: Main PyQt6 interface, including the Settings Popup and four-view stack (Month/Week/Day/Tasks). Sets `pipeline.current_view` on every view switch.
- `assistant/calendar_ui/todo_view.py`: Apple Reminders-style Tasks panel. `TodoView` contains `SectionHeader` (with 🔄 Sync Today button + ⚙ gear), `TodoListWidget`, and `TodoItemWidget` (inline edit, circular checkbox, hover-delete).
- `assistant/calendar_ui/day_view.py`: Single-day hourly timeline with live current-time indicator and Morning Briefing button.
- `assistant/db.py`: Thread-safe SQLite store. Now includes `todos` table with `source` column (manual vs calendar_sync), full CRUD, `toggle_todo_complete()`, and `sync_calendar_to_todos()`.

---

## ⚙️ Configuration (`config.yaml`)

| Section | Key Settings |
|---------|--------------|
| `llm_engine` | `ollama` (default), `openai`, `gemini`, `claude` |
| `audio` | `sample_rate: 16000`, `silence_duration_sec: 20.0` |
| `tts` | `voice: "Eddy"`, `rate: 200`, `mute: false` |
| `confirmation_level` | `0` (Auto-Approve) or `1` (Manual) |
| `todo.sync.mode` | `"off"` (default), `"today"` (sync calendar→Today), `"general"` (sync week→General) |
| `todo.sync.auto_sync_on_open` | `false` — set `true` to auto-sync todos from calendar on every app launch |
| `todo.show_completed` | `false` — set `true` to show completed tasks in the list |
| `todo.default_list` | `"today"` or `"general"` — which list new voice tasks go to |

---

## 📋 Ongoing & Future Tasks

- **Persistence Layer**: Currently, `config.yaml` is updated via Regex in the UI. Consider moving to `ruamel.yaml` to ensure comment preservation.
- **GitHub Management**: Repo is synced to `https://github.com/GilCaplan/MaCalendar`. Always `git push` after major feature additions.
- **Microsoft Graph**: Auth code is present but integration into the main pipeline is pending.
- **Testing**: Use `tests/test_ollama_parser.py` and `tests/test_todo_parser.py` to verify reasoning logic. Run `tests/test_todo_parser.py --direct` for no-LLM todo feature verification.
- **Todo polish**: Priority visualization (colored dots already in place), due-date picker, completed-tasks toggle button in the Tasks toolbar.

## 🏁 Hand-off Summary
The project is in a stable, high-performance state. The "Streaming STT", "Multi-LLM", "Day View / Morning Briefing", and **"Tasks / Todo Integration"** features are fully operational. The database persists locally in `~/.assistant_tools/calendar.db`. Every launch starts clean, but the settings are saved in `config.yaml`.

### Adding New View-Switching Actions
Set `view_switch: ClassVar[str] = "switch_today"` (or `"switch_todo"`, or any future status string) on a `BaseAction` subclass. The pipeline automatically sends that status to the UI after execution. Add a handler in `window.py`'s `_handle_status()` to react.

### Adding New Todo Actions
Follow the same plugin pattern as calendar actions:
1. Add intent model to `assistant/actions/todo/intent.py`
2. Add `@register` action class to `assistant/actions/todo/action.py`
3. Re-export from `assistant/actions/todo/__init__.py`
The LLM system prompt auto-updates — no core changes needed.
