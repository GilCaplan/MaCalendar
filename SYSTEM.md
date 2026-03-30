# MaCalendar Assistant System State

A **voice-controlled, privacy-first calendar assistant** for macOS. This document serves as the "brain" for the project, allowing any AI developer or assistant to resume work with full context.

## 🚀 Recent Core Improvements (Current Build)

- **Real-Time Streaming STT**: Modified `AudioCapture` to support background chunking. The pipeline now performs incremental transcription every 2.5s, allowing pro-active detection of stop-keywords (e.g., "execute", "done") to terminate the microphone mid-speech for instant responsiveness.
- **Universal LLM Intent Parser**: Refactored the core parser to support four backends: **Ollama (local)**, **OpenAI**, **Google Gemini**, and **Anthropic Claude**. The engine is routed via `config.llm_engine`.
- **Integrated Settings UI**: Replaced cluttered toolbar buttons with a single ⚙️ Settings gear. It opens a native popup for:
  - Toggling **Auto-Approve** (autonomous mode).
  - Selecting from all **macOS System Voices** (native list).
  - Adjusting **Talking Speed** (WPM) and **Mute**.
  - **Live Audio Testing** button.
- **Context Memory (Anaphora)**: The assistant now retains the ID of the most recently created or modified event. Users can use pronouns like *"Delete **it**"* or *"Move **that event** to 5pm"* for fluid conversation.
- **Fuzzy Token Matching**: Refactored event lookup to use token-based fuzzy scoring. This handles LLM hallucinations or trailing transcription words (like "...done") that aren't part of the event title.
- **Security & Defense**: Implemented a **Prompt Injection Defense** layer that sanitizes transcripts before LLM submission to prevent system-prompt poisoning via voice.

---

## 🛠 Project Architecture

### Data Flow
```
Hotkey (Cmd+Shift+Space) 
  → AudioCapture (records with 2.5s streaming window)
  → stream_checker() (Detects 'execute'/'done' → self.stop_recording())
  → Universal IntentParser (Ollama/OpenAI/Gemini/Claude → JSON)
  → ConfirmationHandler (Auto-Approve Check → level 0/1)
  → Action.execute() (Create/Update/Delete + Memory Tracking)
  → TTS Speaker (macOS 'say' with speed/voice/mute params)
  → DB persistence (SQLite) + UI Month/Week Refresh
```

### Key Components
- `assistant/pipeline.py`: Orchestrates the streaming STT and LLM handshake.
- `assistant/intent/parser.py`: Unified factory for local and cloud LLM providers.
- `assistant/actions/calendar/action.py`: Contains match logic and contextual memory hooks.
- `assistant/calendar_ui/window.py`: Main PyQt6 interface, including the new Settings Popup.
- `assistant/db.py`: Thread-safe SQLite store with `clear_all()` for testing.

---

## ⚙️ Configuration (`config.yaml`)

| Section | Key Settings |
|---------|--------------|
| `llm_engine` | `ollama` (default), `openai`, `gemini`, `claude` |
| `audio` | `sample_rate: 16000`, `silence_duration_sec: 20.0` |
| `tts` | `voice: "Eddy"`, `rate: 200`, `mute: false` |
| `confirmation_level` | `0` (Auto-Approve) or `1` (Manual) |

---

## 📋 Ongoing & Future Tasks

- **Persistence Layer**: Currently, `config.yaml` is updated via Regex in the UI. Consider moving to `ruamel.yaml` to ensure comment preservation.
- **GitHub Management**: Repo is synced to `https://github.com/GilCaplan/MaCalendar`. Always `git push` after major feature additions.
- **Microsoft Graph**: Auth code is present but integration into the main pipeline is pending.
- **Testing**: Use `tests/test_ollama_parser.py` (which includes multi-scenario suites) to verify reasoning logic.

## 🏁 Hand-off Summary
The project is in a stable, high-performance state. The "Streaming STT" and "Multi-LLM" features are fully operational. The database persists locally in `~/.assistant_tools/calendar.db`. Every launch starts clean, but the settings are saved in `config.yaml`.
