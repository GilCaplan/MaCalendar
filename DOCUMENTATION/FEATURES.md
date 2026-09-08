# Feature catalog

Every feature of the software, one entry each: what it is, where it lives
across the codebase, and how it's implemented. **When a feature ships, its
entry lands here in the same change** — this file is the inventory the rest of
the workflow (STATUS.md, TASKS.md) assumes exists. Deeper docs are linked
rather than duplicated.

Format per entry: **What** (brief) · **Where** (all surfaces) · **How**
(technical notes).

Entries are grouped by **layer**: pure UI (client-side only — the backend
needs no knowledge of them), hybrid (coordinated frontend + backend), and
purely backend (no client code beyond displaying the effects).

## The table

| layer | feature | in one line | mainly lives in |
|---|---|---|---|
| UI | [Navigation chrome](#navigation-chrome) | sidebar, mini calendar, tabs, Today | `sidebar.py`, `window.py` |
| UI | [Design system & theming](#design-system--theming) | light/dark, live accent, fonts, toasts | `styles.py`, `Theme.swift` |
| UI | [Direct editing & undo](#direct-manipulation-editing--undo) | drag-reschedule/resize, dbl-click create, ⌘Z | views, `window.py` |
| UI | [Morning briefing](#morning-briefing) | Brief Me: today summarised + spoken | `day_view.py` |
| UI | [Tasks power features](#tasks-power-features) | rich notes, sorts, reorder, cal→tasks sync | `todo_view.py` |
| UI | [Search & jump-to-date](#search--jump-to-date) | toolbar search over events/tasks; type a date to jump | `window.py`, `SearchView.swift` |
| UI | [Small conveniences](#small-conveniences) | duplicate event, week numbers, Timer CSV export | `event_dialog.py`, `month_view.py`, `timer_view.py` |
| hybrid | [Calendar views](#calendar-views-month--week--day) | month/week/day/agenda browsing + event CRUD, drag, undo | `calendar_ui/`, iOS views, `db.py` |
| hybrid | [Tasks](#tasks--to-dos) | Today/General lists, priorities, quantities | `db.py`, `TasksView` |
| hybrid | [Tag discovery](#tag-discovery--the-class-set-grows-with-consent) | consent-based new classes + history | `actions/todo/tag_discovery.py` |
| hybrid | [Share event as .ics](#share-event-as-ics) | one event → RFC 5545 file, both platforms | `ics_export.py`, `event_dialog.py` |
| hybrid | [Pre-event notifications](#pre-event-notifications) | phone rings from its cache; server computes policy; per-category mute; live "Up Next" lock-screen card | `notify.py`, `ReminderScheduler.swift`, `LiveActivityManager.swift` |
| hybrid | [Voice I/O & capture controls](#voice-in--voice-out--capture-controls) | hotkey/stop-phrases/review-bar; engine-selectable STT; spoken replies | `stt/`, `Voice/`, `tts/` |
| hybrid | [Edit-transcription gate](#the-edit-transcription-round-trip-needs_edit) | doubted words → editor → learned | `engine/ingest/repair.py` |
| hybrid | [Confirm-create gate](#the-confirm-create-gate-confirm_create) | "should I add yoga tomorrow?" → Add / No, never a silent guess | `engine/decompose_validate/validate.py`, `/voice/confirm` |
| hybrid | [Self-check & revert](#background-self-check--one-tap-revert) | background re-reasoning, one-tap undo | `engine/__init__.py`, panels |
| hybrid | [Review panel / HUD](#the-review-panel-thinking-hud--ios-timeline) | live chain-of-thought card + history | `thinking_hud.py`, `ThinkingView` |
| hybrid | [Personal vocabulary](#personal-vocabulary) | user's words fix transcripts first | `stt/vocab.py` |
| hybrid | [Command memory](#command-memory--feedback) | every command + verdicts, mined | `intent/memory.py` |
| hybrid | [Tag discovery](#tag-suggestion-history) | consent-based new classes + history | `actions/todo/tag_discovery.py` |
| hybrid | [Import & connected calendars](#calendar-import--connected-calendars) | .ics/macOS import; ICS subscribe; Outlook 2-way | `window.py`, `calendar_sync/` |
| hybrid | [Workout & training](#workout--training-scheduling) | templates, live sessions, observance-aware planning | `actions/workout*`, `Views/Workout/` |
| hybrid | [Timer](#timer-work-tracking) | per-project work + earnings | db `timers*`, `TimerView` |
| hybrid | [Counters](#counters) | tap counters + payouts | db `counters*` |
| hybrid | [Coursework](#coursework) | courses + assignments tab | db `courses*`, `CourseworkView` |
| hybrid | [iOS app & offline](#ios-app--offline-queues) | full client, 3 offline queues, Tailscale | `MACalendar-iOS/` |
| hybrid | [Health CLI & heartbeats](#heartbeats--the-health-cli) | `assistant doctor`, 6 layers | `cli.py`, `heartbeat.py` |
| backend | [The engine](#the-engine-engine-v2--the-brain) | the AI brain: fast track + 7-step deep track | `assistant/engine/` |
| backend | [The action set](#the-action-set) | the 15 things a command can do | `assistant/actions/` |
| backend | [Task tags](#task-tags--a-finite-classification) | closed-set classification w/ healing | `actions/todo/tagging.py` |
| backend | [Categories & stacking](#events-categories-colours--binder-stacking) | auto-colour/categorise; overlaps stack | `actions/calendar/categories.py` |
| backend | [Hebrew calendar & observance](#hebrew-calendar--observance) | sundown-bounded halachic windows + gate | `observance.py`, `hebrew_calendar.py` |
| backend | [Recurring events](#recurring-events) | daily/weekly/monthly, announced rounding | `db.py`, `engine/decompose_validate/validate.py` |
| backend | [API server](#the-api-server) | the single front door, 112 endpoints | `api/server.py` |
| backend | [Hosted calendar sync](#hosted-calendar-sync) | optional Outlook two-way / ICS read | `calendar_sync/` |
| backend | [Self-improvement loop](#the-self-improvement-loop) | the AI measures & improves itself | `dataset/`, `scripts/` |
| backend | [Diagnostics & logs](#diagnostics--self-observation-logs) | NLU tracking, LLM-judge bug log, audit, calibration | `scripts/` |
| backend | [Explainer pages](#published-explainer-pages) | public pages, build-enforced claims | `artifacts/*.html` |
| backend | [Weekly review](#weekly-review) | real-usage flag-rate report | `scripts/weekly_review.py` |

---

## UI features — client-side only

### Navigation chrome
**What:** Sidebar with one-click New Event and a mini month calendar
(wheel-scroll months, fade transitions); toolbar prev/next/Today, an eliding
title with Hebrew-date suffix, and segmented view tabs (Month / Week / Day /
Tasks / Timer / Coursework / Workout — the last three hideable in settings).
**Where:** `calendar_ui/sidebar.py`, `calendar_ui/window.py`.
**How:** Pure view-layer; tab visibility persists to config.

### Design system & theming
**What:** Light/dark theme (startup setting + one-click toolbar toggle with
toast), accent colour presets + custom picker applied live app-wide,
per-view font sizes, compact density, and centered auto-fading toasts;
theme-aware SVG icon tinting.
**Where:** `calendar_ui/styles.py` (`set_accent`, palettes),
`calendar_ui/icons.py` (rasterised per name/colour/size), settings popup in
`window.py`; iOS `Theme.swift` + `AppSettings.swift`.
**How:** One accent hex derives hover/pressed states; the whole QSS sheet
regenerates on toggle (cached per palette — the PyQt6 QSS-caching gotcha).

### Direct-manipulation editing & undo
**What:** Drag an event to another day/slot (30-min snap), drag its edges to
resize (15-min snap), double-click a cell/slot to create pre-filled; editing
or deleting a repeating event asks "this instance or the series?"; ⌘Z /
⇧⌘Z undo/redo with a toast naming what was reverted.
**Where:** month/week/day views + `calendar_ui/window.py`
(`_on_event_rescheduled`, `_on_undo/_on_redo`), `event_dialog.py`.
**How:** An undo stack of inverse operations over db writes; drag PATCHes
feed the same implicit-feedback hooks as any edit.

### Morning briefing
**What:** A "Brief Me" button on the Day view — the day's schedule
summarised as a toast and spoken aloud.
**Where:** `calendar_ui/day_view.py` + `window.py`
(`_on_briefing_requested`); TTS.
**How:** Reads the day's rows directly; honours the mute/voice settings.

### Tasks power features
**What:** Rich task notes (bold/italic, insert-link) auto-saved while
typing; Manual/Priority/Due-date sort modes; drag-to-reorder; Clear
Completed per section; priority dots and due-date picker; a Manage-tags
sheet on iOS (built-ins protected); calendar→tasks sync (pull today's or the
week's events into Today/General, with an auto mode).
**Where:** `calendar_ui/todo_view.py`; `db.sync_calendar_to_todos`; iOS
`TasksView`/`TaskRowView` + manage-tags sheet.
**How:** Synced rows carry `source='calendar_sync'` so they update rather
than duplicate; manual order is a `position` column, disabled under sorted
modes.


## Hybrid — coordinated frontend + backend

### Calendar views (month / week / day)
**What:** The Outlook-style calendar — browse, create, edit, drag-reschedule
events; undo/redo. A fourth Agenda mode (Mac only) lists the next 30 days'
events chronologically, grouped by day, with day headers skipping empty days.
**Where:** Mac `assistant/calendar_ui/` (`window.py`, `month_view` / week / day
/ `agenda_view.py` views, `styles.py`); iOS `Views/MonthGridView.swift`,
`WeekView.swift`, `DayView.swift`, `EventDetailView.swift`; data
`assistant/db.py` (`events`).
**How:** PyQt6 on Mac, SwiftUI on iOS; both are thin clients over the same
SQLite file via the API. Optimistic concurrency via `updated_at` stamps;
drag-reschedule PATCHes and records implicit feedback on voice-created rows.
Agenda anchors on a `set_start_date` date (Today resets it, nav arrows step a
week), clicking a row opens the same edit dialog as the other views, and day
headers append the Hebrew date when `hebrew_calendar.display_mode` isn't
`english` — same rule as the Week header cells.

### Tasks / to-dos
**What:** Two lists (Today, General) with priorities, due dates, notes,
attachments, quantities ("pasta ×5") and subtasks.
**Where:** `assistant/db.py` (`todos`, `subtasks`); Mac tasks pane; iOS
`Views/TasksView.swift`, `TaskRowView.swift`; API `/todos*`.
**How:** Quantities parse from speech or typed titles
(`assistant/intent/quantity.py`, `split_quantity`); list is a column, not a
table — the two-list design is deliberate (see tag classes for the axis that
does grow). **Creating a task is idempotent:** a client mints one
`client_token` per task the user asked for and repeats it on every attempt —
the live `POST /todos` and each replay of the same queued create — and the
server returns the row it already stored (200, `{"id": …, "duplicate": true}`)
instead of inserting a second one. `todos.client_token` carries the key with a
unique index over non-empty values; in-process creators (voice, calendar sync,
the Mac tasks pane) leave it empty because they never cross the wire. Added
2026-09-06 after 32 copies of one task accumulated in Today, one per repeated
`POST /todos`.
**A content fingerprint is the second net**, because that index only referees
*non-empty* tokens — a caller that sends none was still an unconditional
insert. A token-less `POST /todos` naming a task that is already open, spelled
the same (case- and spacing-insensitive), in the same list, created less than
`todo.duplicate_window_seconds` ago (default 120, 0 = off) returns that row
(200, `{"id": …, "duplicate": true, "reason": "recent-identical"}`).
Completed rows never match, so re-adding a task you ticked off still works, and
an explicit token always wins — two genuinely separate asks that say the same
thing are told apart by their tokens. Added 2026-09-07: the token-less caller
turned out to be the unit suite itself (see below), and by then the list held
45 copies.

### The test suite cannot write through the live API
**What:** No test may reach the `assistant.api` running on this Mac.
**Where:** `tests/conftest.py` (`_no_live_api_calls`, `LiveAPIBlocked`);
regression tests in `tests/unit/test_no_live_api_writes.py`.
**How:** The `MACALENDAR_*` scratch overrides redirect what the *test process*
opens; they cannot redirect an HTTP request, which is served by the live API
process holding the real `~/.assistant_tools` stores. An autouse session
fixture wraps both transports the codebase uses — `requests.Session.request`
and `urllib.request.urlopen` — and raises on any call to loopback at the API
port (Ollama's 11434 and the rest of loopback are untouched). Found 2026-09-07:
`test_thinking_hud.py` clicks the HUD's Revert button for real, the widget's
own `revert_requested → _on_revert` wiring is live in the fixture, and
`_on_revert` re-POSTs the captured body to `127.0.0.1:8080/todos` from a daemon
thread — so every `pytest tests/unit` run added one more "buy groceries" to the
real Today list, arriving 30 s–3 min after the run.
`cli.check_engine()`'s live probe was doing the same to the real command memory
and trace bus via `POST /voice/text`. `scripts/dedup_todos.py` cleans up rows
already made (dry-run by default; `--apply` backs the file up first).

### Tag discovery — the class set grows with consent
**What:** When ≥5 distinct untagged tasks share a theme no existing class
covers, the app asks once ("Add 'X' as a tag?") in a popup while the user is
actively there; a reviewable history allows reversing or hiding past verdicts.
**Where:** `assistant/actions/todo/tag_discovery.py`; API `/tags/suggestion`,
`/tags/suggestion/answer`, `/tags/suggestions/history`,
`/tags/suggestions/revise`; Mac popup in `calendar_ui/window.py`
(`_fetch_tag_suggestion`); iOS alert in `Views/ContentView.swift`.
**How:** Politeness is structural: evidence bar, ≤1 ask/7 days charged on
hand-out, refusals stored forever (`tag_suggestion_state` table), server never
pushes — clients pull only when foregrounded. Un-accepting from history
deletes the class again.

### Voice in / voice out — capture controls
**What:** Push-to-talk (mic button, ⌘J, or a global hotkey — default
⌘⇧Space) with configurable stop phrases, silence auto-stop (2–12 s), a
review-before-send Redo/Add-more/Send bar with countdown, a configurable
event-separator phrase ("next event"), instant placeholder-event keywords,
and mic multi-tap gestures (second tap within 400 ms cancels). Replies
optionally spoken (mute, voice picker, speaking rate, Test Audio preview).
**Where:** STT `assistant/stt/` (engine-selectable: local Whisper CPU,
Apple-GPU mlx-whisper, or opt-in Google cloud STT); Mac capture
`pipeline.py` + settings in `calendar_ui/window.py`; iOS
`Voice/VoiceRecorder.swift` (on-device stop-word recognition),
`SpeechPlayer.swift`; TTS `assistant/tts/speaker.py` (macOS `say`).
**How:** Audio never leaves the machine on the default engines; the phone
streams over Tailscale (`/voice/stream`, NDJSON). `test_offline.py` blocks
non-loopback sockets in the build.

### The edit-transcription round-trip (needs_edit)
**What:** When the vocabulary doubts words in a transcript, nothing executes —
the client shows an editor; the correction (or confirmation) is learned so the
gate fires less over time.
**Where:** gate in `assistant/engine/ingest/repair.py`; Mac dialog via
`pipeline.py` (`supports_edit: true`); iOS `EditTranscriptionSheet` in
`Views/VoiceButton.swift`; all `/voice*` routes forward `supports_edit`.
**How:** A changed word becomes a vocab alias + phonetic key immediately; an
unchanged resubmit counts toward whitelisting (2 confirmations); the resubmit
carries `edited_from` and bypasses the gate once.

### The confirm-create gate (confirm_create)
**What:** A question about creating something — "should I add yoga to my
calendar tomorrow?", "what if I booked town hall for the 3rd?" — is neither
executed nor silently dropped. The parse is finished and offered: the client
shows what it would create, Add creates it, No discards it.
**Where:** reader `is_interrogative_create` in `engine/segmentation/old_seg/segment.py`; rule
`interrogative_create_asks_first` in `engine/decompose_validate/validate.py`; short-circuit
`_confirm_proposal` / `_confirm_response` in `engine/__init__.py`; token store
and `POST /voice/confirm` in `api/server.py`; Mac `ask_create_confirm` in
`calendar_ui/window.py` (via `pipeline.py`, `supports_confirm: true`); iOS
"Add this?" alert in `Views/VoiceButton.swift`.
**How:** Gated on the client declaring `supports_confirm`, exactly like the
edit round-trip — an older client sees today's behaviour and nothing breaks.
The response carries `proposal`: ready-to-POST `/events` / `/todos` bodies,
the same trick one-tap revert uses, so accepting is a plain create through the
endpoints every client already speaks. Answering twice replays the first
answer, so a double-tapped Add creates once. A decline files the command
memory record as `rejected`, which feeds the review flows like any other bad
answer. Fires only when the question is the whole command; an interrogative
create never takes the fast track. Knob: `engine.confirm_create`.
*Ruling: Gil, 2026-09-07 (DEVQA Q9).*

### Background self-check & one-tap revert
**What:** Behind a fast answer, the deep track re-reasons: placeholder titles
renamed, missed asks added, suspected-extra rows reported (advisory by
default) — and when a destructive patch is applied, both surfaces show a
visible notice with one-tap revert.
**Where:** `_start_background_verify` in `assistant/engine/__init__.py`; poll
`GET /voice/verify/<token>`; Mac `_RevertBar` in `thinking_panel.py`; iOS
revert banner in `ThinkingView`.
**How:** Corrections carry ready-to-POST revert bodies captured before
deletion; revert is a plain re-create through the normal endpoints. Applied
changes echo to the Mac HUD as late trace steps.

### The review panel (thinking HUD) & iOS timeline
**What:** A floating always-on-top card (and the iOS sheet) showing every
step the assistant took, live, with timings — plus a searchable history of
every command ever run.
**Where:** `assistant/thinking_hud.py` + `calendar_ui/thinking_panel.py`;
trace source `assistant/trace.py` + `trace_bus.py`
(`~/.assistant_tools/trace_bus.jsonl`); iOS `ThinkingView` in
`Views/ThinkingView.swift` (moved out of `VocabularyView.swift` 2026-09-06).
**How:** The HUD talks to no process — it tails the bus file. Renders by
brain version: `CHAINS[BRAIN_VERSION]` scaffold rail with per-step ⓘ
(copy from `trace.STAGE_INFO`, mirrored in Swift, drift-pinned by
`test_stage_info_parity`). Red is reserved for fatal; review reads amber.
**Ergonomics:** menu-bar tray icon (show/hide/quit), sticky hide, corner
parking, drag-to-reposition persisted across launches, idle translucency
that solidifies on hover, minimise-to-header with live step count, joins
every macOS Space including over full-screen apps, right-click menu; result
cards carry click-to-fix word chips, uncertain-word candidate chips, Retry
now, 👍/👎, and the Revert bar.

### Personal vocabulary
**What:** The user's names/places/phrases; transcripts auto-correct through it
before the brain sees them.
**Where:** `assistant/stt/vocab.py`; store `~/.assistant_tools/vocab.json`;
editors: Mac panel tap-a-word + QuickFix, iOS `VocabularyView` /
`VocabImportView` / onboarding; API `/vocab*`.
**How:** Aliases + phonetic keys; learns from tap-a-word, the needs_edit
round-trip, and bulk import mining (contacts/messages candidates); iOS runs a
first-launch onboarding interview once the Mac is reachable. Doubt whitelist
counters live beside the store, never inside it.

### Command memory & feedback
**What:** Every command, what it did, and the user's verdict — explicit 👍/👎
or implicit (editing/deleting a voice-created row within 24h files as
corrected/rejected; a reformulated retry is mined as a correction pair).
**Where:** `assistant/intent/memory.py`; store
`~/.assistant_tools/nlu_memory.db`; hooks inside `db.update_/delete_*`;
review UIs: iOS `AssistantReviewView`, Mac panel feedback row.
**How:** Recorded per item (per-item attribution). Few-shot injection exists
but ships k=0 — measured to hurt the engine; the record feeds calibration
(TASKS row 57) and future fast-rule mining instead.

### Tag suggestion history
covered under **Tag discovery** above — the review/reverse/hide record.

### Calendar import & connected calendars
**What:** Import events from an `.ics` file or scan macOS Calendar.app;
subscribe read-only to any ICS/webcal link (Gmail, iCloud, Outlook.com…);
optional Outlook **two-way** sync via device-code OAuth, with Sync Now and a
15-minute background sync.
**Where:** Mac toolbar Import + Connected Calendars dialogs
(`calendar_ui/window.py`); `assistant/calendar_sync/outlook_sync.py`,
`actions/calendar/graph_client.py`; `calendar_sources` table.
**How:** Synced rows are marked by source; ICS rows render read-only with a
banner; Outlook dirty-row preservation protects local edits while two-way is
off.

### Workout & training scheduling
**What:** Workout templates, live sessions with set logging, stats, and an
observance-aware run/gym planner (fast days, motzei constraints, frequency
rules).
**Where:** `assistant/actions/workout_routine.py`, `schedule_workout.py`; db
`workout_*` tables; iOS `Views/Workout/*`, `Workout/WorkoutStore.swift`.
**How:** The planner reads the same observance windows as the calendar;
voice-triggered via `generate_workout_routine` / `schedule_workout` actions.

### Timer (work tracking)
**What:** Multi-project timers with earnings calculation and sub-sessions.
**Where:** db `timers`/`timer_sessions`; API `/timers*`, `/timer_sessions*`;
Mac Timer tab; iOS `Views/TimerView.swift`.
**How:** Local-only SQLite; sessions editable after the fact.

### Counters
**What:** Tap-counters with press history and payout tracking.
**Where:** db `counters`, `counter_presses`, `counter_payouts`; API
`/counters*`.
**How:** Same local-first pattern as timers.

### Coursework
**What:** Courses + assignments tracking (the university tab).
**Where:** db `courses`/`assignments`; Mac Coursework tab; iOS
`Views/CourseworkView.swift`, `CourseStore.swift`.
**How:** Toggleable tab (settings); feeds tags ("Coursework").

### iOS app & offline queues
**What:** The full iPhone client — calendar, tasks, voice, review, vocabulary,
workout, timer — working offline and syncing when the Mac returns.
**Where:** `MACalendar-iOS/`; queues in `LocalStore.swift`; polling via
`GET /changes/token`.
**How:** Three queues (CRUD ops with temp-id repointing, queued voice
recordings, pending LLM commands) plus a local event/todo/tag cache so views
work offline; lost-stream recovery (checks whether the Mac finished the
command anyway); a background assertion keeps a voice command alive when the
app is backgrounded; burst-refresh after actions; vertical-swipe month
change; guests via the system Contacts picker with per-guest
Message/WhatsApp actions; reaches the Mac over Tailscale only.

### Heartbeats & the health CLI
**What:** `assistant doctor` — is every layer wired: LLM, storage, engine,
panel, macOS app, external devices.
**Where:** `assistant/cli.py`; `assistant/heartbeat.py`
(`~/.assistant_tools/heartbeats/`); devices POST `/heartbeat`.
**How:** See `DOCUMENTATION/CLI.md`. The engine layer is version-tied to
`BRAIN_VERSION`; a redesign that forgets the doctor fails the build.


## Purely backend

### Search & jump-to-date

**What:** the Mac toolbar has a search box: type words to find events (title/
location/description) and tasks (title/notes), pick a result to jump to its
date or the Tasks tab; type a date ("2026-10-14", "14/10") to jump straight
there. iOS gets a magnifying-glass sheet over the offline cache, so it works
away from the Mac.
**Where:** Mac `calendar_ui/window.py` (`_on_search`, `_parse_jump_date`);
server `GET /search` (`db.search_events/search_todos`); iOS
`Views/SearchView.swift`.
**How:** substring LIKE queries, events soonest-first, open tasks first; the
Mac GUI queries its local db directly (same path as rendering), iOS filters
`LocalStore` — no network needed on either.

### Share event as .ics

**What:** one event exported as a standard calendar file — "Share .ics" in
the Mac event dialog (saves via file dialog), share-sheet on iOS.
**Where:** `assistant/ics_export.py` (pure), `GET /events/<id>.ics`
(`server.py`), Mac `event_dialog.py`, iOS `EventDetailView.swift`.
**How:** one row → one VEVENT deliberately: series are materialized rows
here, so an RRULE would double-book on re-import and can't express
observance skips. Floating local times (the store has no timezone), RFC 5545
escaping + 75-octet folding. Import's symmetric half.

### Small conveniences

**What:** duplicate event (dialog button → one-off copy, undoable); ISO week
numbers in the month grid (`ui.show_week_numbers`); Timer stats → CSV export
mirroring exactly what the panel shows.
**Where:** `event_dialog.py` + `window.py` (duplicate), `month_view.py`
(week numbers — the row's Monday names the ISO week, since a Sunday-first
row straddles two), `timer_view.py` (`_on_export_csv`).
**How:** duplicate strips series identity (a copied instance is a one-off,
same boundary as undo-restore); CSV derives rows from the panel's own
aggregation helper so file and tiles can't disagree.

### Pre-event notifications

**What:** "remind me before it starts." The server computes each event's
`notify_at` (lead resolution: event override → category lead **or mute — a
category can opt out entirely** → global default, shipped opt-in) and embeds
it in every event payload; the phone schedules local notifications from its
offline cache (fires with the app closed and the Mac asleep); the Mac shows
best-effort banners (+ optional spoken heads-up) while the calendar stack
runs. Quiet windows: evaluated on the FIRE time — an event inside
Shabbat/yom tov gets no reminder (reason in the payload), a motzei lead is
clamped past havdala, fasts don't suppress, fail-open like the series skip.
Additive on top of the banner: an **"Up Next" Live Activity** — a persistent
lock-screen card (and Dynamic Island) showing the next event's title, clock
time, category colour and a live countdown, flipping to "NOW" with a
count-up once it starts and then rolling on to the following event.
**Where:** policy `assistant/notify.py`; store `events.reminder_minutes` +
`reminder_log` (`db.py`); Mac thread `assistant/notifier.py` (osascript);
settings `settings_dialog.py` + iOS `SettingsView`; phone
`ReminderScheduler.swift` + `NotificationRouter` (tap deep-links to the
event); per-event picker in both edit surfaces; config `notifications:`
section (PATCH /config). Live Activity: app-side
`LiveActivityManager.swift`, shared contract
`MACalendar-iOS/Shared/UpNextActivityAttributes.swift` (compiled into both
targets), UI in the new `MACalendarWidgets` app-extension target
(`UpNextLiveActivity.swift`, bundle id `com.macalendar.app.widgets`,
deployment target 16.2, embedded via "Embed Foundation Extensions");
`NSSupportsLiveActivities` in the app's `Info.plist`.
**How:** no new sync surface — the event payload is the contract; the phone
reconciles ≤55 `UNCalendarNotificationTrigger`s (headroom under the 64 cap
for workout rest timers); `reminder_log` dedupes across `--reload`
restarts; late fires obey `catch_up_minutes`. The Live Activity needs no
push and never gets one: the countdown is `Text(timerInterval:)` /
`ProgressView(timerInterval:)`, which iOS re-renders on the lock screen with
the app not running — so the app only has to push content when the *event*
changes, which it does from the paths where it already wakes
(`ReminderScheduler.reconcile()`, ContentView's foreground handler, its
`/changes` branch and its 30 s tick), all funnelled through one debounced
`LiveActivityManager.sync()`. Cards carry a `staleDate` at exactly the
moment they stop being true, so a transition missed while the phone is
locked is dimmed by iOS rather than shown as a lie. Starts only within the
8 h ActivityKit cap, and respects the device-local reminders toggle. Voice
phrase → lead time (phase 3) lands after the next branch merge. Plan:
`NOTIFICATIONS_PLAN.md`.

### The engine (engine-v2) — the brain
**What:** Speech/text → events, tasks, answers. A fast track (confident rule
parse commits instantly, deep track verifies behind) and a 7-step deep track
(transcript repair → segment → decompose → validate → generate → crosscheck →
label) with loop-back on disagreement.
**Where:** `assistant/engine/` (one module per stage, `state.py` holds the
frozen contracts); entered only via `assistant.api` (`/voice*` routes).
**How:** `DOCUMENTATION/ENGINE.md` is the canonical stage-contract reference.
Deterministic-first everywhere; every LLM call schema-constrained and grounded
on the raw words; per-stage tests + `scripts/engine_stage_check.py`.
**Notable behaviours (each a named, tested rule):** ingest coalescing of
queued commands; stop-word stripping; trivial/false-start filtering (ignored
AND not remembered); anaphora ("the one I just made" → context memory);
"another one at 7" title carry-over; not-found honesty on updates/deletes
with one LLM second opinion — never a guess; am/pm correction; past-date
bump; move-time fill ("from 9:30 to 9"); cadence rounding announced, never
silent; question-creates-nothing and remove-echo guards; junk/placeholder
event drop; quantity extraction ("5 apples" → one task ×5); shared-verb list
splitting ("buy chicken and rice"); same-activity multi-time split ("walk
the dog at 9 and 2:30" → two events); prompt-injection defense (refuses
"ignore previous instructions" transcripts).

### The action set
**What:** What a voice command can *do* — 15 registered actions: create /
update / delete event, query_schedule, clarify (ask instead of guess),
create / update / complete / delete todo, add / complete / delete subtask,
query_todos, generate_workout_routine, schedule_workout.
**Where:** `assistant/actions/` — one package per domain, `@register`
plugin classes.
**How:** The registry auto-builds the LLM's system prompt from the action
schemas, so adding an action is one class; fuzzy title+date matching for
targets; deletes clear context memory.

### Task tags — a finite classification
**What:** Tasks classify into a closed set of classes (builtin: Groceries,
Coursework… + user customs) with per-tag colours, filtering, and "tag mode"
(auto-apply one tag to every voice task).
**Where:** registry `todo_tags` table (`db.py`); classifier
`assistant/actions/todo/tagging.py`; applied in
`assistant/actions/todo/action.py`; iOS tag UI in `TasksView`/`TaskRowView`.
**How:** Precedence: what the user said > tag mode > keyword inference
(`suggest_tags` over a large keyword→class map). `resolve_tags` heals LLM
near-misses to the closest class (case, plural stems incl. y↔ies, tight fuzzy
at 0.8) and drops far-off hallucinations — the finite set never grows by
accident.

### Events: categories, colours & binder stacking
**What:** Every event auto-categorised and coloured — adjacent events never
share a colour, hand-picked colours are never overridden; overlapping events
stack like binders.
**Where:** `assistant/actions/calendar/categories.py`; stacking Mac-side in the
views + iOS `Views/EventStacking.swift`; category registry
`~/.assistant_tools/categories.json`.
**How:** Deterministic classifier over title/attendees/location with a
per-category palette; `auto_category_and_color` runs inside event INSERTs so
every write path (voice, GUI, API) gets it.

### Hebrew calendar & observance
**What:** Jewish/Israeli holidays in the views; Shabbat/yom tov/fast windows
computed from the sky (candle lighting → tzeit) at the user's actual location;
the observance gate on AI-created events; recurring series skip holy days
(meals excepted, fasts inverted, Shabbat-anchored kept).
**Where:** `assistant/observance.py`, `hebrew_calendar.py`;
`db._skip_for_observance`; engine gate in `engine/decompose_validate/validate.py`; location from
the phone via `/observance/location`; iOS `HebrewDate.swift`,
`DeviceLocation.swift`.
**How:** `pyluach` + `astral`, sundown-bounded not midnight-bounded. All
gating sits behind `observance.enabled` (config, default on;
`MACALENDAR_OBSERVANCE` env override — the test harness turns it off).

### Recurring events
**What:** daily/weekly/monthly series — anything else is rounded and the
rounding is announced; "until" excludes its day, "through"/"including" keep
it; weekly series start on the soonest named weekday.
**Where:** `db.create_event`/series instancing; rules re-checked in
`engine/decompose_validate/validate.py`.
**How:** Series instances materialise as rows sharing `series_id`; observance
skipping applies per instance at creation.

### The API server
**What:** The single front door — 112 endpoints; every surface is its client.
**Where:** `assistant/api/server.py` (HTTP only — no parsing/execution);
generated reference `DOCUMENTATION/API_REFERENCE.md`
(`scripts/gen_api_reference.py`).
**How:** Flask with `--reload`; NDJSON streaming for voice; optional API key;
binds Tailscale with `--tailscale`. Colour-coded logs
(`api/log_color.py`, see `DOCUMENTATION/LOGGING.md`).

### Hosted calendar sync
**What:** Optional two-way Outlook sync and read-only ICS subscriptions —
supported, not required; the default posture is fully local.
**Where:** `assistant/calendar_sync/outlook_sync.py`,
`actions/calendar/graph_client.py`; `calendar_sources` table.
**How:** Dirty-row preservation when two-way is off; ICS rows are locked
read-only.

### The self-improvement loop
**What:** The AI system improves itself: measure against a 3,000-utterance
ground truth → read failures → predict → change one component → verify —
autonomous, with every score/change/decision recorded and plottable.
**Where:** `DOCUMENTATION/SELF_IMPROVEMENT.md` (the map);
`dataset/` (DATASET.md, HYPOTHESES.md, RESULTS.md, loop_log.csv,
loop_changes.csv); harness `scripts/engine_dataset_compare.py`,
`scripts/field_quality.py`, `scripts/plot_loop.py`; questions in `DEVQA.md`.
**How:** Frozen-clock replays at each row's recorded timestamp; metrics:
count-correctness, item-level P/R/F1, field quality (when-paramount,
similarity titles, classification tags), latency; noise floor and graduation
rules in `DOCUMENTATION/experiments/ITERATION_PROTOCOL.md`.

### Diagnostics & self-observation logs
**What:** The system writes evidence about itself: `NLU_TRACKING.md` (every
parse with path + source), `SCENARIO_BUG.md` (an LLM-as-judge records cases
where the rule parser and the model disagreed), the hand-written audit
corpus (regression floor), and a routing-confidence calibration checker.
**Where:** appended by the engine/server; `scripts/audit_assistant.py`,
`scripts/calibration.py`.
**How:** All read-only instruments — they observe the live system, never
steer it.

### Published explainer pages
**What:** Public artifact pages (architecture, explorer, internals) whose
quoted constants are build-enforced against the code.
**Where:** `DOCUMENTATION/artifacts/*.html`;
guard `tests/unit/test_artifact_claims.py`;
brief `DOCUMENTATION/ARTIFACT_BUILDER.md`.
**How:** Any drifting number (endpoint counts, thresholds) turns the build
red naming the page.

### Weekly review
**What:** A Wednesday 10:00 report over real usage — flag rate, honest
accuracy (refuses below 3 approvals, drops verdict bursts).
**Where:** `scripts/weekly_review.py`; LaunchAgent;
`WEEKLY_REVIEW.md` output.
**How:** The real-world scoreboard the dataset loop eventually hands off to.
