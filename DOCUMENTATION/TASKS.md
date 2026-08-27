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

Working agreements
- Everything on the phone is local: no third-party services; the only network peer is the Mac over Tailscale.
- Prefer doing work directly over spawning sub-agents; keep context small (`/compact` between big tasks).
