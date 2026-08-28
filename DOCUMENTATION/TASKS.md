# Task tracker

Running list of user-reported issues and feature requests, with status. Update when working on the app.

| # | Item | Status | Where |
|---|------|--------|-------|
| 1 | Event categories with per-category colours; adjacent events never the same colour | done 2026-08-26 | `assistant/actions/calendar/categories.py`, iOS Settings → Event colours |
| 2 | Binder-style stacking of overlapping events (tap to pop out, tap again to edit) | done 2026-08-26 | `assistant/calendar_ui/stack_layout.py`, `EventStacking.swift` |
| 3 | iOS Timer tab synced with the Mac (timers, sessions, counters, cash-out) | done 2026-08-26 | `/timers`, `/counters`, `TimerView.swift` |
| 4 | Review screen shows real event dates; dismiss stale backlog | done 2026-08-26 | `/memory/unreviewed`, `AssistantReviewView.swift` |
| 5 | Review banner overlapping screen titles | done 2026-08-26 | `ContentView.swift` |
| 6 | Mic / + buttons misaligned when the "Show what it did" chip shows | done 2026-08-27 | `VoiceButton.swift` (chip is an overlay) |
| 7 | "Wrong" on review shows a spurious "unreachable (cancelled)" error | done 2026-08-27 | ignore cancelled requests |
| 8 | Timer sync latency: 3 s poll while a timer runs; Mac reloads its Timer tab on DB change | done 2026-08-27 | `TimerView.swift`, `window.py` |
| 9 | Adaptive sync: 1 s polling for 45 s after a voice command / 10 s after an edit, else 30 s | done 2026-08-27 | `APIClient.burstRefresh`, `ContentView` poll loop |
| 10 | Voice edit changed the wrong event ("the event I just made") | done 2026-08-27 | `_normalise_intents` anaphor/date guard; `_find_event` scores distinctive words only |
| 11 | Recording: Redo / Add more / Send after stop; option to disable silence auto-stop | done 2026-08-27 | `VoiceButton.swift`, Settings → Voice |
| 12 | Guests on events: names from voice, Contacts lookup, invite via Messages / WhatsApp / Mail / .ics share | done 2026-08-27 | `GuestsSection.swift` |
| 13 | Swift Sendable warnings (AVFoundation, UserNotifications) | done 2026-08-27 | `@preconcurrency import` |
| 14 | Verify every claim in the .md docs against the code | in progress | see commit history |
| 15 | Weekly assistant review | scheduled 2026-09-02 | `scripts/weekly_review.py`, LaunchAgent |
| 16 | Mac gets the iOS thinking timeline: live stage-by-stage panel, result card, tap-a-word fix, 👍/👎 | done 2026-08-27 | `assistant/calendar_ui/thinking_panel.py`, `Pipeline` trace |
| 17 | Mac "Review commands" backlog (👍 / 👎 / Fix…) — was iOS-only | done 2026-08-27 | `assistant/calendar_ui/review_dialog.py` |
| 18 | Mac "Event Colours & Categories" editor — was iOS-only | done 2026-08-27 | `assistant/calendar_ui/categories_dialog.py` |
| 19 | Mac dropped voice commands when the LLM was offline (phone queued them); now queued + retryable | done 2026-08-27 | `Pipeline._queue_pending`, `retry_pending` |
| 20 | Leaving the iOS app mid-command killed the stream and froze the timeline | done 2026-08-27 | `BackgroundAssertion`, `VoiceButton.recoverLostStream` |
| 21 | Mac Assistant Settings overflowed: the Font Sizes grid rendered at zero height | done 2026-08-27 | `window.py` settings dialog now scrolls |
| 22 | Mac Assistant Settings regrouped into the iPhone's sections (Appearance / Tabs / Hebrew / Voice / Assistant) | done 2026-08-27 | `window.py` `_on_settings_popup` |
| 23 | Redo / Add more / Send bar on the Mac; a spoken stop word ("execute") sends with no wait, on both apps | done 2026-08-27 | `Pipeline._await_review`, `ReviewBar`, `VoiceRecorder.stopReason` |
| 24 | Thinking panel placement configurable (auto-open vs chip only, which corner) | done 2026-08-27 | Settings → Assistant |
| 25 | iOS could not edit a timer/counter after creating it, or log time it forgot to start | done 2026-08-27 | `POST /timers/<id>/sessions`, `LogPastTimeSheet`, edit mode in `NewTimerSheet` |
| 26 | iOS Tasks had no calendar→tasks sync (endpoint existed, was never called) | done 2026-08-27 | `syncTodosFromCalendar`, Tasks toolbar menu |
| 27 | **iOS never polled at all**: `.task` captured `scenePhase`, frozen at `.inactive`, so the 30 s sync loop was dead — Mac changes only appeared after backgrounding the app | done 2026-08-27 | `ContentView` polls `UIApplication.shared.applicationState` |
| 28 | Cross-device latency 30 s → ~2 s via a cheap change token instead of blind refetching | done 2026-08-27 | `GET /changes`, `APIClient.changeToken` |
| 29 | "August 12 2026" (a past date) became *today*; "the 12th of August" became 12 Sep | done 2026-08-27 | `server.py` past-date bump + month-aware ordinal guard |
| 30 | The test suite wrote "buy milk" / gibberish into the real command memory and vocabulary on every run | done 2026-08-27 | `MACALENDAR_VOCAB` / `MACALENDAR_CATEGORIES` + scratch paths in `tests/conftest.py` |
| 31 | Redundant `@Published` writes re-rendered the whole app on every failed poll | done 2026-08-27 | `APIClient.request` assigns only on change |
| 32 | **Offline queue lost work**: a change made offline to an item *created* offline (tick off a new task) referenced a temporary negative id, 404'd on replay, and — since sync stopped at the first failure — blocked every later change for ever | done 2026-08-28 | `LocalStore.remapTemporaryID`, `syncPending` drops un-retryable entries |
| 33 | Offline-created rows appeared twice after syncing (local placeholder + the Mac's copy) | done 2026-08-28 | `cacheTodos`/`cacheEvents` drop a placeholder whose twin arrived |
| 34 | Voice commands spoken while the Mac was away were thrown away; now queued, replayed on reconnect, with a banner, a "Queued commands" screen and a local notification | done 2026-08-28 | `PendingVoiceCommand`, `syncPendingVoice`, `VoiceQueueView` |
| 35 | Stop-word listener fell back to Apple's servers when on-device recognition wasn't available, against the local-only rule | done 2026-08-28 | `VoiceRecorder` requires `supportsOnDeviceRecognition` |
| 36 | Queued work waited up to 30 s after reconnect; now flushes the moment the Mac answers | done 2026-08-28 | `APIClient.request` offline→online transition |
| 37 | The Mac's thinking panel was blind to commands run from the phone (separate processes); it now tails a trace bus and labels them "from your iPhone" | done 2026-08-28 | `assistant/trace_bus.py`, `CalendarWindow._poll_phone_traces` |
| 38 | Editing the same event on both devices while apart silently lost one side's change; the Mac now refuses a stale edit (409) and the phone says so | done 2026-08-28 | `base_updated_at` on `PATCH /events/<id>`, `updated_at` stamped at creation |
| 39 | The review bar's raw status string ("3\|add lunch…") leaked into the Mac's toast | done 2026-08-28 | `_handle_status` handles STATUS_REVIEW before toasting |
| 40 | Optimistic-concurrency guard extended from events to tasks | done 2026-08-28 | `base_updated_at` on `PATCH /todos/<id>` |
| 41 | **A spoken "7am" was booked at 7 PM.** The exemption for an explicit morning time tested `\b(am\|a.m.)\b`, which cannot match "7am" (no boundary after the digit) or "a.m." (none after the dot). Morning words had no say either, so Shacharit at 7 became 7 PM | done 2026-08-28 | `rule_parser._extract_temporal`, 15 regression tests |
| 42 | `scripts/audit_assistant.py` wrote replayed transcripts and learned aliases into the real vocabulary; it now audits against a copy | done 2026-08-28 | `MACALENDAR_VOCAB` copy in the audit harness |
| 43 | **"from 9 to 10" crashed the rule parser** with an unhandled AttributeError (the recogniser returns a match with no resolution). Callers only caught `RuleParserSkip`, so the command died instead of falling back to the LLM | done 2026-08-28 | `rule_parser._extract_temporal` guards; both callers now fall back on any parser error |
| 44 | "lunch from 12 to 1" produced 12:00–01:00 — an event ending before it starts | done 2026-08-28 | end-before-start post-pass (leaves genuine overnight ranges alone) |
| 45 | "rename X to Y" answered "No changes specified" — even "rename gym to workout". Read literally now, with a guard so "rename the meeting to 3pm" stays a reschedule | done 2026-08-28 | `_RENAME_RE` in `rule_parser._fill_slots` |
| 46 | **Voice edits hit the wrong event.** "the meeting with Ima" reached the matcher as just "meeting", so it scored a generic word and took the nearest meeting (Shaul's) | done 2026-08-28 | `_extend_title_with_whom` keeps the person in `match_title` |
| 47 | **Naming an event that isn't on the day given edited whatever else was.** "move the gym on Sunday" moved "Meeting with Ima". A named-but-missing event now reports not-found; the day fallback only applies to a generic title ("the event on Sunday") | done 2026-08-28 | `_find_event` gates the date fallback on `meaningful_words` |

Working agreements
- Everything on the phone is local: no third-party services; the only network peer is the Mac over Tailscale.
- Prefer doing work directly over spawning sub-agents; keep context small (`/compact` between big tasks).
