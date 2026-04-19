# MACalendar — iPhone App

SwiftUI native iOS app backed by a Flask REST API running on the same Mac. The Mac is the single source of truth for the SQLite DB. The iPhone has a local JSON cache and offline write queue so it works without a Mac connection.

---

## Architecture

```
iPhone (SwiftUI)
  ↕ HTTP  (Tailscale VPN — Wi-Fi or cellular)
Mac Flask API  (assistant/api/server.py)
  ↕ Python imports
Existing Mac logic: IntentParser, WhisperSTT, CalendarDB, Actions
```

```
iPhone offline mode:
  LocalStore (JSON cache on device)
    mc_events.json   — cached events (temp IDs < 0 for unsynced)
    mc_todos.json    — cached todos
    mc_pending.json  — queued writes to replay on reconnect
```

The Mac app and iPhone API server run simultaneously. The iPhone never touches the DB directly — all reads/writes go through the API. When offline, reads serve from local cache and writes are queued; the queue is replayed automatically when the Mac is reachable (on app foreground).

---

## Connectivity & Networking

| Mode | Command | Best for... |
|------|---------|-------------|
| **Tailscale** | `python -m assistant.api --tailscale` | **Recommended**. Works anywhere. |
| Same Wi-Fi | `python -m assistant.api --lan` | Local home testing only. |
| USB tunnel | `iproxy 8080 8080` + `--lan` | No internet, debug only. |

### 1. Tailscale Setup (One-time)

1. **Mac**: Install Tailscale via Homebrew (`brew install tailscale`) or from [tailscale.com](https://tailscale.com).
2. **iPhone**: Download the **Tailscale** app from the App Store.
3. Sign in with the same account on both devices.
4. Verify connection: `tailscale status` on Mac should show your iPhone.

Starting the API with `--tailscale` will automatically detect your Tailscale IP (starts with `100.x.x.x`) and print it to the terminal.

---

## Deployment (via Xcode)

Xcode project at `MACalendar-iOS/MACalendar-iOS.xcodeproj`.

### 1. Signing & Capabilities

1. Open `MACalendar-iOS/MACalendar-iOS.xcodeproj` in Xcode.
2. Click the top-level `MACalendar-iOS` target → **Signing & Capabilities**.
3. Sign in with your Apple ID and select your Team.
4. Xcode will auto-generate a Provisioning Profile.

### 2. Deploy to iPhone

1. Connect iPhone via USB-C. Select it in the **Run Destination** dropdown.
2. Press **Run (▶)**.
3. *First time only*: iPhone → **Settings → General → VPN & Device Management** → tap your Apple ID → **Trust**.
4. Run again. After install, USB cable can be unplugged — app runs standalone.

### 3. iOS Compatibility

Deployment target is **iOS 16.0**. Tested on iPhone 16e (iOS 26.x). `AVAudioApplication.requestRecordPermission` is used on iOS 17+ with automatic fallback to `AVAudioSession` on iOS 16.

---

## Configuration

1. **Start the Mac API** (via `Launch Calendar.command` or manually):
   ```bash
   python -m assistant.api --tailscale --port 8080
   ```
2. **Find the IP**: Look for `Tailscale IP detected: 100.x.x.x` in terminal.
3. **Enter in iPhone**: App → **Settings** → **Server URL** → `http://100.x.x.x:8080`
   - Must be `http://` not `https://` (plain HTTP, no TLS)
   - The app auto-corrects `https://` → `http://` if mistyped
4. **Health Check**: Tap **Test Connection** → should show `✓ ollama` (or your LLM engine).

### Port Collisions

If `8080` is already in use:
```bash
python -m assistant.api --tailscale --port 8081
```
Update the Server URL on iPhone to match.

---

## Offline Mode

The app works fully without a Mac connection:

| Operation | Offline behaviour |
|-----------|------------------|
| View events/todos | Served from local JSON cache |
| Create event/todo | Saved locally with temp ID (negative int) |
| Edit / delete | Applied locally immediately |
| Voice commands | Requires Mac (Whisper + LLM run on Mac) |

An orange **"Offline — N changes pending sync"** banner appears at the top when the Mac is unreachable.

**Auto-sync**: Every time the app comes to the foreground (`scenePhase == .active`), it calls `syncPending()` which replays all queued writes to the Mac in order and refreshes the local cache. Temp IDs are replaced by real server IDs on next refresh.

---

## Flask API (`assistant/api/`)

### Starting the server
```bash
python -m assistant.api                # binds 127.0.0.1:8080 (local only)
python -m assistant.api --lan          # binds 0.0.0.0:8080  (LAN access for iPhone)
python -m assistant.api --tailscale    # binds 0.0.0.0:8080 + prints Tailscale IP
```

Launched automatically alongside the Mac app via `Launch Calendar.command`.

### Endpoints

#### Voice
| Method | Path | Body | Returns |
|--------|------|------|---------|
| POST | `/voice` | multipart WAV/m4a audio | `{message, actions, refresh, parse, verify_token?}` |
| POST | `/voice/text` | `{transcript: str}` | `{message, actions, refresh, parse, verify_token?}` |
| GET | `/voice/verify/<token>` | — | `{pending?}` or `{ok}` or correction object |

`parse` is `"rule"` / `"hybrid"` / `"llm"` / `"error"` — how the command was processed.

`verify_token` is only present when `parse == "rule"`. iOS should poll `/voice/verify/<token>` every 4 s (up to ~40 s) to check if the background LLM verifier found a correction. Response:
- `{"pending": true}` — LLM still running, retry
- `{"ok": true}` — rule parser was correct, no action needed
- `{"ok": false, "severity": "minor", "patch": {...}, "speech": "...", "refresh": "..."}` — iOS patches the existing record via REST + plays `speech`
- `{"ok": false, "severity": "major", "action": "...", "parameters": {...}, "speech": "...", "refresh": "..."}` — iOS undoes the fast-path via REST, re-executes the corrected action, plays `speech`

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
| `assistant/api/server.py` | Flask app, all route handlers. Logs prefixed with 📱. |
| `assistant/api/audio_utils.py` | Decode WAV/m4a bytes → float32 numpy array at 16kHz |
| `assistant/api/__init__.py` | `python -m assistant.api` entry point, Tailscale IP detection |

### Security
- Default: binds to `127.0.0.1` (safe)
- LAN/Tailscale mode: binds `0.0.0.0`
- Optional `X-API-Key` header matched against `config.yaml`
- `NSAppTransportSecurity: NSAllowsArbitraryLoads = true` in Info.plist (private VPN use)

---

## SwiftUI App (`MACalendar-iOS/`)

### Structure
```
MACalendar-iOS/
  MACalendarApp.swift       @main, injects APIClient + AppSettings as EnvironmentObjects
  LocalStore.swift          JSON cache + offline pending queue (singleton)
  API/
    APIClient.swift         URLSession wrapper — offline-aware, falls back to LocalStore
    Models.swift            CalendarEvent, Todo, VoiceResponse, HealthResponse (Codable)
  CourseStore.swift         Local-only JSON store for Course + Assignment (singleton, no Mac sync)
  Views/
    ContentView.swift       TabView: Calendar | Tasks | Coursework | Settings + offline banner
    CalendarView.swift      Month/Week/Day switcher
    MonthGridView.swift     7-col grid (Sun first), tap → day detail
    WeekView.swift          Horizontal week strip
    DayView.swift           Hourly timeline
    EventDetailView.swift   View + edit single event
    TasksView.swift         Today + General sections
    TaskRowView.swift       Checkbox row + swipe-to-delete
    CourseworkView.swift    Course list with assignments, due dates, calendar sync
    VoiceButton.swift       Mic button — records WAV, POSTs to /voice, speaks response
    SettingsView.swift      Server URL, API key, TTS voice (3 options), Test Connection
  Voice/
    VoiceRecorder.swift     AVAudioRecorder → 16kHz mono WAV bytes
    SpeechPlayer.swift      AVSpeechSynthesizer reads response.message
  Settings/
    AppSettings.swift       @AppStorage: serverURL, apiKey, ttsVoice, theme, fontMonth, fontWeek, fontDay, fontTasks
```

### Offline flow (LocalStore)
```
Write offline → LocalStore.insertEvent(fields) → temp id (-1, -2, ...)
             → LocalStore.enqueue("POST", "/events", fields)

App foreground → APIClient.syncPending()
              → replay each PendingChange in order
              → on success: LocalStore.removePending(id)
              → on failure: stop, keep remainder queued
              → refresh UI from server
```

### TTS Voices (hardcoded, no speechVoices() call)
| Label | Language code |
|-------|--------------|
| Samantha (US) | en-US |
| Daniel (UK) | en-GB |
| Karen (AU) | en-AU |

Uses `AVSpeechSynthesisVoice(language:)` — always resolves on device, no decode errors.

### VoiceButton flow
1. Tap → `AVAudioRecorder` records 16kHz mono WAV
2. Tap again → stop, POST WAV to `/voice` (multipart)
3. Response `message` → `AVSpeechSynthesizer.speak()`
4. `refresh` field → reload events/todos accordingly
5. Mic permission: `AVAudioApplication` on iOS 17+, `AVAudioSession` fallback on iOS 16

### Models
```swift
struct CalendarEvent: Identifiable, Codable, Equatable {
    let id: Int          // negative = local temp, positive = server ID
    var title, date, startTime, endTime: String   // CodingKeys map snake_case
    var attendees, location, description, color: String
    var recurrence, recurrenceEnd: String
}
struct Todo: Identifiable, Codable, Equatable {
    let id: Int          // negative = local temp
    var title, list: String
    var completed: Int   // 0 or 1
    var priority, dueDate: String
}
struct VoiceResponse: Codable {
    let message: String; let actions: [String]; let refresh: String
    let parse: String           // "rule" | "hybrid" | "llm" | "error"
    let verifyToken: String?    // present only when parse == "rule"
}
struct VerifyResult: Codable {
    let pending: Bool?          // true = LLM still running
    let ok: Bool?               // true = no correction needed
    let severity: String?       // "minor" | "major"
    let patch: [String: String]? // minor: fields to PATCH on existing record
    let action: String?         // major: corrected action
    let parameters: [String: AnyCodable]? // major: corrected params
    let speech: String?         // TTS string to play
    let refresh: String?        // "events" | "todos"
}
struct HealthResponse: Codable { let status, llm, db: String }
```

### Background Verification (APIClient)
```swift
// After receiving a VoiceResponse with parse == "rule":
apiClient.pollVerify(token: response.verifyToken!) { result in
    // play result.speech via AVSpeechSynthesizer
    // if minor: PATCH existing record
    // if major: DELETE fast-path record + POST corrected record
    // then refresh events/todos
}
```
`pollVerify` retries every 4 s for up to 40 s then silently gives up.

---

## Running

```bash
# Terminal 1 — Mac app + iPhone API (recommended)
./Launch\ Calendar.command

# Or separately:
# Terminal 1 — Mac app
python -m assistant.main

# Terminal 2 — iPhone API
python -m assistant.api --tailscale
```

iPhone: set Server URL in Settings to `http://<tailscale-ip>:8080`.
iPhone can be disconnected from USB after first install — app runs standalone.

---

## Coursework Tab

A local-only feature (no Mac API endpoints). All data lives in the app's Documents directory; nothing syncs to the Mac server except when the user explicitly pushes an assignment deadline to the main calendar.

### Data models (`API/Models.swift`)

```swift
struct Course: Identifiable, Codable, Equatable {
    let id: UUID           // auto-generated
    var number: String     // e.g. "00960336"
    var name: String       // course title (supports Hebrew RTL)
    var color: String      // hex e.g. "#4BA8A0"
    var partners: [String] // classmate names
}

struct Assignment: Identifiable, Codable, Equatable {
    let id: UUID
    var courseId: UUID
    var title: String
    var dueDate: String        // "YYYY-MM-DD" or "" if none
    var completed: Bool
    var calendarEventId: Int?  // set when synced to main calendar
}
```

### Storage (`CourseStore.swift`)

`@MainActor` singleton, pattern mirrors `LocalStore`. Persists to:
- `mc_courses.json` — array of Course
- `mc_assignments.json` — array of Assignment

No offline queue needed (local-only). Calendar sync calls `api.createEvent()` via the existing events API.

### CourseworkView.swift — key interactions

| Action | How |
|--------|-----|
| Add course | `+` button (nav bar) → `CourseEditSheet` |
| Edit course | Pencil icon in section header → `CourseEditSheet` |
| Delete course | Edit button (nav bar) → swipe-to-delete on course row; **or** edit sheet → Delete button. Deleting a course also deletes all its assignments. |
| Add assignment | "Add Assignment" row at bottom of each course section |
| Delete assignment | Swipe left on assignment row |
| Toggle complete | Tap circle checkbox |
| Set due date | Tap calendar icon on assignment → `DueDatePickerSheet` (graphical date picker, clear option) |
| Sync to calendar | Tap export icon (only shown when due date is set and not yet synced) → creates CalendarEvent via `api.createEvent()` with title "📚 [title]", all-day-style at 23:59 |

### Due date color coding
- > 3 days away: secondary gray
- ≤ 3 days: orange
- Today or overdue: red

### Calendar sync
Calls `api.createEvent(fields)` with:
- `title`: `"📚 \(assignment.title)"`
- `date`: `assignment.dueDate`
- `start_time` / `end_time`: `"23:59"`
- `color`: course hex color
- `description`: `"\(course.number) — \(course.name)"`

On success, stores the returned event ID in `assignment.calendarEventId` (disables re-sync). Changing the due date resets `calendarEventId = nil`.
