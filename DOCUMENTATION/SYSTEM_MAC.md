# MACalendar — Mac App

A **voice-controlled, privacy-first calendar and task assistant** for macOS built with PyQt6.

---

## Log Prefix
All Mac app log lines are prefixed with `🖥️` to distinguish from iPhone API logs (`📱`).

---

## Recent Core Features

- **Hybrid NLU Fast-Path**: `RuleBasedParser` (spaCy + Microsoft Recognizers-Text) handles ~80% of common commands in <10ms without any LLM call. 7-phase algorithm: preprocess → multi-intent split → temporal extraction → intent routing → slot filling → anaphora → confidence scoring.
- **Recurrence Logic**: Support for series-wide updates and intelligent rescheduling.
- **Theme Support**: Persistent dark/light toggle in the Gear settings menu.
- **Dynamic Settings UI**: Resizable settings window with vertical "stretching" spacers and a dedicated **Compact Layout** toggle for high-density setups.
- **Font Controls**: Separate font size adjustments for Month, Week, Day, and Tasks in the Gear settings menu.
- **Background LLM Verification**: After a fast-path result is spoken, a daemon thread sends it to the LLM as a judge. Three tiers: **ok** (silent), **minor** (silent PATCH of wrong fields), **major** (undo fast-path create + full LLM re-execute). Guard: checks if the user already changed the record before applying any correction.
- **Structured Partial Handoff**: When rule confidence < 0.85 or slots are missing, pre-analysis context (filled/empty slots, transcript, confidence) is prepended to the LLM prompt so the LLM only fills gaps.
- **iPhone Companion App**: SwiftUI app with full offline support — local JSON cache + pending write queue that auto-syncs when Mac is reachable. See [SYSTEM_IPHONE.md](SYSTEM_IPHONE.md).
- **iPhone API auto-start**: `Launch Calendar.command` starts the Flask API (`--tailscale --port 8080`) in the background alongside the Mac app. Tailscale IP is printed to terminal.
- **Todo Integration (Tasks View)**: Apple Reminders-style Tasks panel (Today + General). Voice CRUD, inline editing, calendar sync, anaphoric memory ("delete it").
- **Day View & Morning Briefing**: Hourly timeline with live current-time indicator and 🌅 Brief Me button.
- **Real-Time Streaming STT**: Incremental transcription every 2.5s with stop-keyword early termination ("done", "execute", "go").
- **Voice Session Queuing**: Press mic while busy → queues a new session or combine mode (appends to previous transcript). Cycles: queue → combine → cancel.
- **Event Resize by Drag**: Top/bottom 8px handles on event blocks change start/end time live, snapping to 15-min grid.
- **Universal LLM Intent Parser**: Ollama (local), OpenAI, Gemini, Anthropic Claude — routed via `config.llm_engine`.
- **Audio Device Probe**: `assistant/audio/probe.py` runs once at startup, detects native sample rate, permissions, dtype. Resamples to 16 kHz for Whisper if needed.
- **Integrated Settings UI**: ⚙️ gear popup for Auto-Approve, voice selection, talking speed, mute, startup theme choice, live audio test.
- **Series-Wide Editing**: When editing recurring events, chooses between "This instance" or "Entire series" with automatic recurrence-end re-generation.
- **Context Memory (Anaphora)**: `ContextMemory` Borg singleton (`assistant/intent/context.py`) retains last event/todo ID/title for pronoun resolution ("move it", "delete that").
- **Prompt Injection Defense**: Sanitizes transcripts before LLM submission.

---

## Data Flow

```
Hotkey (Ctrl+J) or Mic Button
  → AudioCapture (records at native rate, resamples to 16kHz)
  → stream_checker() (detects stop keywords → stop_recording())
  → [TASKS VIEW] prefix injected if current_view == "todo"
  → WhisperSTT.transcribe() [reuses stream-checker result if fresh]
  → RuleBasedParser.analyze() [<10ms, 7-phase NLU]
       ├─ confidence ≥ 0.85 + no missing slots → fast-path execute (no LLM)
       │     └─ Background: LLM verifies (tier 1/2/3 → silent/patch/undo+redo)
       ├─ partial match → parse_with_context() [LLM fills gaps only]
       └─ skip/complex → IntentParser.parse() [full LLM]
  → ConfirmationHandler (level 0 = auto-approve)
  → Action.execute() → CalendarDB (singleton via get_db())
  → TTS Speaker (macOS 'say')
  → DB persistence (SQLite) + UI refresh
  → Pipeline timing logged: ⏱ Recording / Transcription / Parse / Execute / Total
```

---

## Key Components

| File | Role |
|------|------|
| `assistant/pipeline.py` | Orchestrates full voice flow. Session queuing (`_queued`: None/new/combine), per-phase timing logs. |
| `assistant/audio/capture.py` | Records at device-native rate, resamples to 16kHz. Reuses stream-checker transcript when fresh (<3s). |
| `assistant/audio/probe.py` | One-time startup probe: finds working sample rate, checks mic permissions, caches as `AudioDeviceProfile`. |
| `assistant/stt/whisper_stt.py` | `faster-whisper` base model, int8, beam_size=1 (greedy). |
| `assistant/intent/rule_parser.py` | `RuleBasedParser` — 7-phase hybrid NLU. spaCy + Microsoft Recognizers-Text. `RULE_THRESHOLD=0.85`. Raises `RuleParserSkip` for complex commands. |
| `assistant/intent/context.py` | `ContextMemory` Borg singleton — thread-safe last event/todo ID+title for anaphora resolution across actions and rule parser. |
| `assistant/intent/parser.py` | Multi-backend LLM parser. System prompt cached daily. `parse_with_context()` for partial handoff. `verify_fast_path_async()` for background severity judgment. |
| `assistant/actions/calendar/action.py` | Create/update/delete/query calendar events. Fuzzy token matching, anaphoric memory. |
| `assistant/actions/todo/action.py` | 5 todo actions (create/complete/delete/update/query). Multi-task create via `titles: List[str]`. |
| `assistant/actions/__init__.py` | `ActionRegistry` Borg singleton. Builds system prompt for LLM. |
| `assistant/db.py` | Thread-safe SQLite. `get_db()` singleton. Indexes on `events(date)`, `events(series_id)`, `todos(list, completed)`. |
| `assistant/calendar_ui/window.py` | Main PyQt6 window. Four-view stack: Month/Week/Day/Tasks. |
| `assistant/calendar_ui/day_view.py` | Hourly timeline, resize handles (8px top/bottom), drag-to-move. |
| `assistant/calendar_ui/week_view.py` | 7-column week grid, resize handles, drag-to-move. |
| `assistant/calendar_ui/month_view.py` | Month grid, shades Sun/Tue/Thu/Sat columns. |
| `assistant/calendar_ui/todo_view.py` | Tasks panel. All signals deferred via `QTimer.singleShot(0)` to prevent re-entrant crashes. `TodoItemWidget` (L700) has inline `▸` expand button → `TodoDetailPanel` (L160) with notes/subtasks/attachments/due-date/priority. |

---

## Configuration (`config.yaml`)

| Section | Key Settings |
|---------|--------------|
| `llm_engine` | `ollama` (default), `openai`, `gemini`, `claude` |
| `ollama.timeout_seconds` | `60` default; scales dynamically +15s per extra detected action |
| `verify_fast_path` | `true` (default) — enables background LLM judgment of rule-parser results |
| `audio.silence_duration_sec` | `6.0` — stops 6s after speech ends (or on keyword) |
| `whisper.beam_size` | `1` — greedy decode, ~4× faster than beam_size=5 |
| `tts` | `voice`, `rate`, `mute` |
| `confirmation_level` | `0` (Auto-Approve) or `1` (Manual) |
| `todo.sync.mode` | `"off"` / `"today"` / `"general"` |

---

## Architecture Notes

### Adding New Actions
1. Add intent model to `assistant/actions/<domain>/intent.py`
2. Add `@register` class to `assistant/actions/<domain>/action.py`
3. Re-export from `assistant/actions/<domain>/__init__.py`
4. Optionally set `view_switch: ClassVar[str]` to auto-switch UI view post-execution

### View-Switching Actions
Set `view_switch = "switch_today"` / `"switch_todo"` on a `BaseAction` subclass. Pipeline sends it to the UI after execution. Handle in `window.py`'s `_handle_status()`.

### Crash Prevention Pattern
All signals that trigger widget rebuild (`todo_changed`, `resized`) are deferred with `QTimer.singleShot(0, signal.emit)` to prevent use-after-free from re-entrant `deleteLater()` calls.

### Code Map
For precise file + line pointers across all subsystems see **[CODE_MAP.md](CODE_MAP.md)**.

---

## Repo & Running

- **GitHub**: `https://github.com/GilCaplan/MACalendar`
- **Launch**: Double-click `Launch Calendar.command` or `python -m assistant.main`
- **DB**: `~/.assistant_tools/calendar.db` (SQLite)
- **Logs**: `~/.assistant_tools/assistant.log`
- **Tests**: `tests/test_ollama_parser.py`, `tests/test_todo_parser.py`
