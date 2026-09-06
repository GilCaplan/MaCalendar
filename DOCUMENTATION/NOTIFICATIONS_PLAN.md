# Notifications — the plan

_2026-09-06. Status: **BUILDING — Gil greenlit ("implement when ready",
same day) with one addition: per-category MUTE — `category_leads` value 0
turns a whole category's notifications off, mirroring the event-level 0.
Q4–Q6 stand unanswered, so the build uses this plan's safe defaults (no
launch-model change — the phone is the only always-on ringer; global
default 0 = opt-in; in-Shabbat events suppressed with the reason announced)
— all three reversible in config whenever Gil rules. Phase 1 (policy core,
notify.py + data model + payload fields) landed @ 7ec34a6; phases 2 (iOS)
and 4 (Mac notifier + settings) in flight; phase 3 (voice) waits for the
cycle-boundary merge since it touches engine files the loop owns.** Produced by a design panel (4 read-only code sweeps → 3
independent designs: iOS-first / server-first / UX-first → adversarial judge
+ synthesis). The winning skeleton is the UX-first design (thinnest client
data flow — `notify_at` embedded in event payloads, no second sync surface),
with the strongest mechanics grafted from the other two (motzei clamp,
`/changes`-token reschedule trigger, catch-up policy, NO_WARMUP gating)._

**Visual preview (what the user sees, both platforms + settings):**
https://claude.ai/code/artifact/07952f0f-f7cd-4390-891f-fedeb15a178c
_The preview shows some elements beyond this plan's v1 (morning digest,
night quiet, snooze) — those are tagged in the preview as later-phase or
proposals for Gil to keep or kill._

Line references below were verified read-only against both trees on
2026-09-06 (recurrence instances are materialized rows; `PATCH /config`
exists; validate's `_EXCLUSIVE_END` regex reads a bare "before" as a
recurrence-end marker — which is why decompose must strip the reminder
clause first).

# SYNTHESIZED FINAL DESIGN — Pre-Event Notifications

**Design center:** the iPhone is the reliable ringer — it schedules absolute-time local notifications ahead from its offline event cache and fires with the app closed and the Mac asleep. The server (`assistant/notify.py`) is the single source of policy: it computes `notify_at` per event row and embeds it in every event payload. The Mac banner is a best-effort bonus while the calendar stack is up. No push, no internet, ever.

## Data model

**`events` table** (`assistant/db.py`, existing migration pattern near :108):
- `reminder_minutes INTEGER NULL` — `NULL` = inherit (category default, then global), `0` = explicitly none, `N>0` = fire N min before `start_time`. Events with no `start_time`: no reminder.
- Add `"reminder_minutes"` to the `update_event` allowed-set (db.py:1043 — unknown keys are silently dropped today).
- Series need nothing special: instances are rows (verified), each carries/inherits its own resolution.

**`reminder_log` table** (same DB — covered by `MACALENDAR_DB` override for free): `(event_id, fires_at, fired_at, outcome)` , unique `(event_id, fires_at)`, outcome ∈ `fired|suppressed|missed`. DB-backed because `--reload` restarts the API on every source edit; an in-memory fired-set re-fires constantly during development (C's insight).

**Intents** (`assistant/actions/calendar/intent.py`, `action.py:34-51`): `CalendarIntent.reminder_minutes: Optional[int]`, `UpdateEventIntent.new_reminder_minutes: Optional[int]`, mirrored into `CreateEventAction.parameters_schema` for the schema-constrained LLM path. Validate clamps to 0–1440. Pin the additions in `test_engine_contracts.py`'s field lists in the same change.

**Config** (`assistant/config.py` `NotificationsConfig` beside `ObservanceConfig`; mirror into `config.example.yaml` next to `observance:` ~:123):

```yaml
notifications:
  enabled: true              # master switch; env MACALENDAR_NOTIFICATIONS=0 for harnesses
  default_lead_minutes: 0    # 0 = opt-in only (see Open Question 2)
  category_leads: {}         # e.g. Coursework: 60
  respect_observance: true   # quiet-window suppression/clamp
  catch_up_minutes: 10       # Mac: fire late if missed by <= this and event not started
  sound: true
  speak: false               # Mac only: also read via tts/speaker.py
```

**iOS models** (`API/Models.swift`, `LocalStore.swift`): `CalendarEvent` gains `reminderMinutes: Int?`, `notifyAt: String?`, `notifySuppressedReason: String?` — all optional so existing `mc_events.json` caches decode unchanged.

## Endpoint contracts (all additive; run `python scripts/gen_api_reference.py` after)

- **`GET /events*`**: each event gains `reminder_minutes` (stored override, nullable), `notify_at` (ISO local datetime, or null when no effective lead / already started / suppressed), `notify_suppressed_reason` (`"shabbat" | "yom_tov:<name>" | null`). Computed by `assistant/notify.py` at serialization; `server.py` stays routes-only.
- **`POST /events` / `PATCH /events/{id}`**: accept `reminder_minutes` (null clears). Existing optimistic-concurrency and iOS `PendingChange` offline-queue machinery unchanged. Any write bumps the DB mtime → the `/changes` token flips → the phone re-pulls and reconciles, free.
- **`PATCH /config`** (exists, server.py:1599): carries the `notifications` section so iOS Settings can edit the global default and observance toggle.
- **No new scheduling endpoint.** Schedule is derived state; the event payload is the contract.

## Scheduling mechanics

**iOS — primary.** New `ReminderScheduler.swift` (manual `PBXFileReference`/`PBXBuildFile`/`PBXGroup` entries — classic pbxproj, no sync groups). `reconcile()` runs after `cacheEvents`/`insertEvent`/`patchEvent`/`removeEvent`, on the foreground `.task` sync, **and when the existing `/changes` token poll detects a change** (B's graft). It takes cached events with `notify_at > now`, nearest-first, schedules up to **55** `UNCalendarNotificationTrigger(dateMatching:, repeats: false)` requests with identifier `evt-<id>` (WorkoutStore :508-541 cancel-by-id precedent), removing stale `evt-*` ids first; headroom reserved for WorkoutStore rest timers and `APIClient.notify` under the shared 64 cap. Body: `In 30 min · 15:00 · <location>`; the event time in the content makes a stale fire self-evident (A). Tap deep-links `macalendar://event/<id>` via the existing `.onOpenURL`. Add a `UNUserNotificationCenterDelegate` (none exists) for foreground banners; lift `requestNotificationPermissionIfNeeded()` from WorkoutStore into a shared helper, requested when the user first enables reminders, not at launch. Offline-created events: naive local `start − lead` fallback, no observance check, repaired at next sync (fail-open, documented).

**Mac — best-effort.** `assistant/notifier.py` daemon thread started from `create_app()` (the `start_pending_retry_loop` idiom, server.py:105-146), **gated by `MACALENDAR_NO_WARMUP`** so tests never start it. Every 30s: select events with `notify_at` in `(watermark, now]` and no `reminder_log` row; deliver via `subprocess.run(["osascript", "-e", "display notification …"])` (loopback-free, no dependency; attribution to "Script Editor" accepted for v1 — signed-bundle upgrade deferred); optional `say` when `speak: true`. Late tick (wake from sleep): fire if within `catch_up_minutes` and event not started ("starting now" wording), else log `outcome=missed` silently. Every fire/suppress appends a trace-bus step (`{"stage":"notify","action":"fired|suppressed","reason":…}`, source `"mac"`) so HUD History explains why. Honest limit, stated in docs: the API dies with the GUI (`Launch Calendar.command` kills by PID) — Mac banners fire only while the calendar stack is up; the phone covers absence.

## Quiet-window rules (`assistant/notify.py`, evaluated on the **fire time**, mirroring `db._skip_for_observance`, db.py:498-560)

1. Gate: `notifications.respect_observance` **and** `observance.is_enabled()` — two kill switches.
2. Quiet iff fire time falls inside [`candle_lighting(erev)`, `tzeit(last day)`] using real clock boundaries, never date-only (Jerusalem candle lighting: 18:43 Sep, 16:20 Dec); evening-of-erev governed by the next day's status per `availability()`'s two-slot model.
3. **Event itself inside the window** (Shabbat lunch): reminder **suppressed**, reason recorded and surfaced (`notify_suppressed_reason`) — never silently.
4. **Event after the window, reminder inside it** (motzei event, lead lands before tzeit): **clamp** `fire_at` to `tzeit + motzei_buffer_minutes` (A's graft; buffer already in `ObservanceSettings`), reason notes the shift.
5. **Fasts**: no suppression — a reminder is not a booking; Yom Kippur covered by the yom-tov check (**verify by unit test**, per C, don't assume).
6. **Fail open**: any exception or `None` solar data → notify normally (`observance.py`'s stated philosophy verbatim).
7. Voice replies **announce** suppression/clamping at creation ("…note the Friday one falls after candle lighting, so it won't ring") — the recurrence-rounding convention applied here.

## Voice (engine hook)

Current misparse (all three designs agree, verified line refs): `_TASK_RE` (segment.py:39-41) needs "remind me **to**"; verb table `("remind", None) → create_todo` (rule_parser.py:208); clock-time reroute (:1257-1265) ignores relative durations → garbage todo.

- **Decompose strips the clause first** — `remind me (?:(\d+|a|an|half an) )?(minute|hour)s? (?:before|ahead of|earlier)` (+ "with a reminder") removed from item text into `slots["reminder_minutes"]` **before validate runs**, because validate's `_EXCLUSIVE_END` (validate.py:63, verified) would read the surviving "before" as a recurrence-end marker and corrupt until/through semantics (C's catch — the decisive implementation detail).
- Inline shape → `CalendarIntent.reminder_minutes`; standalone ("remind me 30 minutes before my meeting") → rule-parser pattern routing to `update_event` with `match_title` + `new_reminder_minutes`; no match → "I couldn't find…" — never guess (deletion-rule ethos). The duration+"before" anchor keeps "remind me to buy milk" on the todo path.
- No pipeline-shape change → **no `BRAIN_VERSION` bump, no `CHAINS`/panel edits**; but the intent-field additions touch contract pins, so file the TASKS.md design row first (CLAUDE.md rule).

## Settings

- **iOS `SettingsView`**: Reminders section — enable toggle (device-local), permission status row + request/deep-link, default lead picker (Off/5/10/15/30/60) and "Quiet on Shabbat & chagim" toggle written via `PATCH /config`. `EventDetailView`: reminder row (Inherit / None / N min) → `PATCH /events/{id}`.
- **Mac**: Notifications section built in **the worktree's `../MACalendar-app/assistant/calendar_ui/settings_dialog.py`** (never main's inline dialog — guaranteed merge collision otherwise); persists via `config_store.set_values({"notifications": {...}})` (auto-creates the section). Note: config.yaml is not under `assistant/`, so `--reload` does not pick edits up — v1 accepts an API restart.

## Phases

| # | Scope | Files | Effort |
|---|---|---|---|
| **1 — Server policy core** | `reminder_minutes` column + migration + allowed-set (`assistant/db.py`); `reminder_log`; `NotificationsConfig` (`assistant/config.py`, `config.example.yaml`); **new `assistant/notify.py`** (resolution chain → fire time → quiet-window suppress/clamp, pure functions); event serialization + `PATCH /config` section (`assistant/api/server.py`); `gen_api_reference.py`; unit tests incl. seasonal candle-lighting boundaries and the YK check | main repo | ~1 session |
| **2 — iOS lock screen (the headline)** | `ReminderScheduler.swift` (new + pbxproj entries), `Models.swift`/`LocalStore.swift` fields, `UNUserNotificationCenterDelegate` + deep-link route (`MACalendarApp.swift`), shared permission helper, reconcile hooks (`ContentView.swift` + `/changes` poll), `EventDetailView` picker, `SettingsView` section, 55-cap budget | MACalendar-app worktree | ~1.5–2 sessions |
| **3 — Voice** | TASKS.md design row → decompose stripping (`engine/decompose.py`), rule-parser patterns (`intent/rule_parser.py`), intent/schema fields + contract-pin updates, update-path matching, announced-suppression replies, stage tests + audit rows, dev-fast run | main repo | ~1.5 sessions |
| **4 — Mac banners** | `assistant/notifier.py` thread (NO_WARMUP-gated), osascript delivery, catch-up policy, trace-bus steps, Mac settings section (worktree `settings_dialog.py`), FEATURES.md entries for shipped phases | both | ~1 session |
| **5 — Hardening (each behind an owner decision)** | ~~Live Activity "Up Next" card~~ **(done, see below)**; LaunchAgent detachment of `assistant.api` (weekly-review-agent precedent); `BGAppRefreshTask` + `UIBackgroundModes: fetch` (Info.plist verified clean today); snooze action; pre-Shabbat digest mode | both | ~1–2 sessions |

### Phase 5 — partially done: the "Up Next" Live Activity (2026-09-06)

Gil saw the pre-event banner fire on his lock screen and asked for the
Google-Maps / Starbucks experience: a persistent, self-updating card. Shipped
in the `MACalendar-app` worktree, **additive — the notification scheduling was
not touched.**

- **New target `MACalendarWidgets`** (app extension, `com.macalendar.app.widgets`,
  deployment target 16.2, embedded through an "Embed Foundation Extensions"
  copy phase). Sources: `MACalendarWidgetsBundle.swift`,
  `UpNextLiveActivity.swift`, plus the shared
  `MACalendar-iOS/Shared/UpNextActivityAttributes.swift` compiled into **both**
  targets. No asset catalog, no app-only imports — the extension links nothing
  of the app's.
- **The local-only trick.** Live Activities are normally kept alive by APNs,
  which this project will never use. It does not need to: the countdown is
  drawn by the *system* (`Text(timerInterval:)`, `ProgressView(timerInterval:)`)
  and ticks on the lock screen with the app not running. The app only pushes
  content when the *event* changes — a handful of updates a day.
- **The cost of no push**, stated honestly: those updates only happen when iOS
  gives the app execution time. `LiveActivityManager.sync()` is called from
  `ReminderScheduler.reconcile()` (so every cache write), ContentView's
  foreground handler, its `/changes` token branch, and its 30 s tick. Every
  card carries a `staleDate` at the exact moment it stops being true, so a
  transition missed while the phone is locked is **dimmed by iOS**, not shown
  as a stale countdown.
- **Policy:** starts only when reminders are enabled *and* something is running
  or starts within 8 h (the ActivityKit cap); ends when neither holds; an
  in-progress event wins over an upcoming one.

**Still open in phase 5:** `BGAppRefreshTask` would let the card roll between
events while the phone is locked, and is the natural next increment — it is
also the one that makes the `staleDate` fallback rare rather than routine.

**Not verified on device.** Simulator proof is complete (start / flip to NOW /
roll to next / end, plus the Dynamic Island rendering the live countdown), but
the extension's bundle id has never been provisioned: only
`com.macalendar.app` has a profile on this Mac, and a headless `xcodebuild`
cannot mint a new one ("No Accounts"). **One Run from Xcode.app with the phone
reachable creates it**; after that `xcrun devicectl device install app` works
as usual.

Each shipped phase adds its `DOCUMENTATION/FEATURES.md` entry in the same change; branch, never commit to main.

## Test strategy

- **Offline test**: `tests/unit/test_offline.py` must stay green — `notify.py` is pure Python + `observance.py` (local), delivery is `subprocess`/osascript (no sockets). Add an explicit unit test asserting the notifier module opens no socket, and that `MACALENDAR_NO_WARMUP=1` prevents the thread from starting under `create_app()` (same reason as the Whisper warmup gate).
- **`notify.py` unit tests** (fast, no model): resolution-chain precedence (event > category > global; `0` beats a category default); September-vs-December Friday boundary cases; motzei clamp; fail-open on `None` solar data; Yom Kippur in the yom-tov set (C's verify-don't-assume); no-`start_time` events.
- **Harness hygiene**: any script exercising this sets all five env overrides (`MACALENDAR_DB/MEMORY_DB/VOCAB/CATEGORIES/TRACE_BUS`) and posts `source: "test"`.
- **Engine phase**: pin new intent fields in `test_engine_contracts.py`; stage tests in `test_engine_decompose.py`/`test_engine_generate.py` including "remind me to buy milk" staying a todo and an until/through sentence with a reminder clause keeping correct recurrence-end semantics; audit-corpus rows; dataset guard = dev-fast (`--limit 0 --max-rank 250`), hypothesis "garbage-titles rate drops on remind-before utterances; task-slice count-correct holds", logged in `dataset/RESULTS.md`. **Note (C):** the 3000-row ground truth has no reminder field — the audit floor + unit tests are the regression net for this phrasing.
- **Mac settings UI**: `QTest.mouseClick`/`keyClicks`, never handler calls (three HUD bugs shipped green that way).
- **iOS cap test**: reconcile with >55 upcoming reminders while a WorkoutStore rest timer is pending — assert the rest timer survives and `evt-*` count ≤ 55.
- **`--reload` dedupe**: touch a source file mid-test-window; assert `reminder_log` prevents a duplicate fire.

## Open questions for the product owner (max 3, genuinely his)

1. **Do you want Mac reminders with the calendar closed?** That requires detaching `assistant.api` into a launchd LaunchAgent — a launch-model change affecting `--reload`, the HUD, and shutdown ownership. If no, Phase 5's biggest item disappears and the phone is officially the only always-on surface.
2. **Global default lead: opt-in (`0`, reminders only where asked) or blanket (e.g. 30 min before everything)?** Ships as `0`; a blanket default changes the feature's character and its noise level on a dense calendar.
3. **Reminders for events *inside* Shabbat/yom tov (e.g. Shabbat lunch): suppress entirely (shipped default), or roll into a single pre-candle-lighting digest banner?** This is an observance-lifestyle call, not an engineering one.