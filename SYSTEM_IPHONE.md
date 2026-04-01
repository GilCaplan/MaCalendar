# MACalendar — iPhone App

SwiftUI native iOS app backed by a Flask REST API running on the same Mac. The Mac is the single source of truth for the SQLite DB.

---

## Architecture

```
iPhone (SwiftUI)
  ↕ HTTP/LAN (Wi-Fi / USB tunnel)
Mac Flask API  (assistant/api/server.py)
  ↕ Python imports
Existing Mac logic: IntentParser, WhisperSTT, CalendarDB, Actions
```

The Mac app and iPhone API server run simultaneously. The iPhone never touches the DB directly — all reads/writes go through the API.

---

## Flask API (`assistant/api/`)

### Starting the server
```bash
python -m assistant.api            # binds 127.0.0.1:5000 (local only)
python -m assistant.api --lan      # binds 0.0.0.0:5000  (LAN access for iPhone)
```

Or launched automatically alongside the Mac app via `Launch Calendar.command`.

### Endpoints

#### Voice
| Method | Path | Body | Returns |
|--------|------|------|---------|
| POST | `/voice` | multipart WAV/m4a audio | `{message, actions, refresh}` |
| POST | `/voice/text` | `{transcript: str}` | `{message, actions, refresh}` |

`refresh` is one of `"events"`, `"todos"`, `"both"`, `""` — tells the iOS app what to reload.

#### Events
| Method | Path | Query / Body |
|--------|------|------|
| GET | `/events` | `?year=&month=` or `?date=YYYY-MM-DD` or `?week_start=YYYY-MM-DD` |
| GET | `/events/<id>` | — |
| POST | `/events` | `{title, date, start_time, end_time, ...}` |
| PATCH | `/events/<id>` | any subset of event fields |
| DELETE | `/events/<id>` | — |

#### Todos
| Method | Path | Query / Body |
|--------|------|------|
| GET | `/todos` | `?list=today\|general\|all&include_completed=true` |
| POST | `/todos` | `{title, list_name, priority, due_date}` |
| PATCH | `/todos/<id>` | any subset of todo fields |
| PATCH | `/todos/<id>/toggle` | — (toggles completed) |
| DELETE | `/todos/<id>` | — |
| POST | `/todos/sync` | `{list_name}` |

#### Config / Health
| Method | Path |
|--------|------|
| GET | `/config` |
| PATCH | `/config` |
| GET | `/health` |

### Key implementation files
| File | Role |
|------|------|
| `assistant/api/server.py` | Flask app, all route handlers |
| `assistant/api/audio_utils.py` | Decode WAV/m4a bytes → float32 numpy array at 16kHz |
| `assistant/api/__init__.py` | `python -m assistant.api` entry point |

### Security
- Default: binds to `127.0.0.1` (safe, USB tunnel or same-machine only)
- LAN mode: `--lan` flag binds `0.0.0.0`
- Optional `X-API-Key` header matched against `config.yaml`

---

## SwiftUI App (`MACalendar-iOS/`)

Xcode project at repo root.

### Structure
```
MACalendar-iOS/
  MACalendarApp.swift       @main, injects APIClient as EnvironmentObject
  API/
    APIClient.swift         URLSession wrapper for all endpoints
    Models.swift            CalendarEvent, Todo, VoiceResponse (Codable)
  Views/
    ContentView.swift       TabView: Calendar | Tasks | Settings
    CalendarView.swift      Month/Week/Day switcher
    MonthGridView.swift     7-col grid (Sun first), tap → day detail
    WeekView.swift          Horizontal week strip
    DayView.swift           Hourly timeline
    EventDetailView.swift   View + edit single event
    TasksView.swift         Today + General sections
    TaskRowView.swift       Checkbox row + swipe-to-delete
    VoiceButton.swift       Mic button with status ring
    SettingsView.swift      Server URL, API key, TTS voice, theme
  Voice/
    VoiceRecorder.swift     AVAudioRecorder → WAV bytes
    SpeechPlayer.swift      AVSpeechSynthesizer reads response.message
  Settings/
    AppSettings.swift       @AppStorage: serverURL, apiKey, ttsVoice
```

### VoiceButton flow
1. Tap → `AVAudioRecorder` starts recording to temp WAV
2. Tap again OR 6s silence → stop
3. POST WAV to `/voice` (multipart)
4. Response `message` → `AVSpeechSynthesizer.speak()`
5. `refresh` field → reload events/todos accordingly

### Models
```swift
struct CalendarEvent: Identifiable, Codable {
    let id: Int
    var title, date, startTime, endTime: String   // CodingKeys map snake_case
    var attendees, location, color: String
    var recurrence, recurrenceEnd: String
}
struct Todo: Identifiable, Codable {
    let id: Int
    var title, list: String
    var completed: Int          // 0 or 1
    var priority, dueDate: String
}
struct VoiceResponse: Codable {
    let message: String
    let actions: [String]
    let refresh: String
}
```

---

## DB Sync Roadmap (not yet implemented)

The iPhone currently has no local DB — all data comes from the Mac API over the network.

Future options (in order of complexity):
1. **Always-online** (current) — iPhone calls Mac API, Mac must be reachable
2. **iCloud SQLite sync** — share the `.db` file via `NSFileManager` + iCloud Drive; both apps observe file changes
3. **CloudKit** — mirror the `events` and `todos` tables as CloudKit records; full offline support with conflict resolution

Decision deferred. Architecture is designed so the iOS `APIClient` is the only place that needs changing when sync is added.

---

## Running

```bash
# Terminal 1 — Mac app
python -m assistant.main

# Terminal 2 — iPhone API
python -m assistant.api --lan

# Or both together via:
./Launch\ Calendar.command
```

iPhone: set Server URL in Settings to `http://<mac-ip>:5000`.
