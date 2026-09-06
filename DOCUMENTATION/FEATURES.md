# Feature catalog

Every feature of the software, one entry each: what it is, where it lives
across the codebase, and how it's implemented. **When a feature ships, its
entry lands here in the same change** — this file is the inventory the rest of
the workflow (STATUS.md, TASKS.md) assumes exists. Deeper docs are linked
rather than duplicated.

Format per entry: **What** (brief) · **Where** (all surfaces) · **How**
(technical notes).

## The table

| feature | in one line | mainly lives in |
|---|---|---|
| [Calendar views](#calendar-views-month--week--day) | month/week/day browsing + event CRUD, drag, undo | `calendar_ui/`, iOS views, `db.py` |
| [Categories & stacking](#events-categories-colours--binder-stacking) | auto-colour/categorise; overlaps stack | `actions/calendar/categories.py` |
| [Tasks](#tasks--to-dos) | Today/General lists, priorities, quantities | `db.py`, `TasksView` |
| [Task tags](#task-tags--a-finite-classification) | closed-set classification w/ healing | `actions/todo/tagging.py` |
| [Tag discovery](#tag-discovery--the-class-set-grows-with-consent) | consent-based new classes + history | `actions/todo/tag_discovery.py` |
| [The engine](#the-engine-engine-v2--the-brain) | the AI brain: fast track + 7-step deep track | `assistant/engine/` |
| [Voice I/O](#voice-in--voice-out) | local Whisper in, `say` out, streaming | `stt/`, `Voice/`, `tts/` |
| [Edit-transcription gate](#the-edit-transcription-round-trip-needs_edit) | doubted words → editor → learned | `engine/transcript.py` |
| [Self-check & revert](#background-self-check--one-tap-revert) | background re-reasoning, one-tap undo | `engine/__init__.py`, panels |
| [Review panel / HUD](#the-review-panel-thinking-hud--ios-timeline) | live chain-of-thought card + history | `thinking_hud.py`, `ThinkingView` |
| [Personal vocabulary](#personal-vocabulary) | user's words fix transcripts first | `stt/vocab.py` |
| [Command memory](#command-memory--feedback) | every command + verdicts, mined | `intent/memory.py` |
| [Hebrew calendar & observance](#hebrew-calendar--observance) | sundown-bounded halachic windows + gate | `observance.py`, `hebrew_calendar.py` |
| [Recurring events](#recurring-events) | daily/weekly/monthly, announced rounding | `db.py`, `engine/validate.py` |
| [Workout & training](#workout--training-scheduling) | templates, live sessions, observance-aware planning | `actions/workout*`, `Views/Workout/` |
| [Timer](#timer-work-tracking) | per-project work + earnings | db `timers*`, `TimerView` |
| [Counters](#counters) | tap counters + payouts | db `counters*` |
| [Coursework](#coursework) | courses + assignments tab | db `courses*`, `CourseworkView` |
| [API server](#the-api-server) | the single front door, 109 endpoints | `api/server.py` |
| [iOS app & offline](#ios-app--offline-queues) | full client, 3 offline queues, Tailscale | `MACalendar-iOS/` |
| [Hosted calendar sync](#hosted-calendar-sync) | optional Outlook two-way / ICS read | `calendar_sync/` |
| [Health CLI & heartbeats](#heartbeats--the-health-cli) | `assistant doctor`, 6 layers | `cli.py`, `heartbeat.py` |
| [Self-improvement loop](#the-self-improvement-loop) | the AI measures & improves itself | `dataset/`, `scripts/` |
| [Explainer pages](#published-explainer-pages) | public pages, build-enforced claims | `artifacts/*.html` |
| [Weekly review](#weekly-review) | real-usage flag-rate report | `scripts/weekly_review.py` |

---

## Core calendar & tasks

### Calendar views (month / week / day)
**What:** The Outlook-style calendar — browse, create, edit, drag-reschedule
events; undo/redo.
**Where:** Mac `assistant/calendar_ui/` (`window.py`, `month_view` / week / day
views, `styles.py`); iOS `Views/MonthGridView.swift`, `WeekView.swift`,
`DayView.swift`, `EventDetailView.swift`; data `assistant/db.py` (`events`).
**How:** PyQt6 on Mac, SwiftUI on iOS; both are thin clients over the same
SQLite file via the API. Optimistic concurrency via `updated_at` stamps;
drag-reschedule PATCHes and records implicit feedback on voice-created rows.

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

### Tasks / to-dos
**What:** Two lists (Today, General) with priorities, due dates, notes,
attachments, quantities ("pasta ×5") and subtasks.
**Where:** `assistant/db.py` (`todos`, `subtasks`); Mac tasks pane; iOS
`Views/TasksView.swift`, `TaskRowView.swift`; API `/todos*`.
**How:** Quantities parse from speech or typed titles
(`assistant/intent/quantity.py`, `split_quantity`); list is a column, not a
table — the two-list design is deliberate (see tag classes for the axis that
does grow).

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

## The AI assistant

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

### Voice in / voice out
**What:** Push-to-talk (⌘J on Mac, mic button on iPhone) with stop-words,
silence auto-stop and a review-before-send countdown; replies optionally
spoken.
**Where:** STT `assistant/stt/` (mlx-whisper, GPU, cached model); Mac capture
in `pipeline.py`; iOS `Voice/VoiceRecorder.swift`, `SpeechPlayer.swift`; TTS
`assistant/tts/speaker.py` (macOS `say`).
**How:** Audio never leaves the machine; the phone streams to the Mac over
Tailscale (`/voice/stream`, NDJSON step events). `test_offline.py` blocks any
non-loopback socket in the build.

### The edit-transcription round-trip (needs_edit)
**What:** When the vocabulary doubts words in a transcript, nothing executes —
the client shows an editor; the correction (or confirmation) is learned so the
gate fires less over time.
**Where:** gate in `assistant/engine/transcript.py`; Mac dialog via
`pipeline.py` (`supports_edit: true`); iOS `EditTranscriptionSheet` in
`Views/VoiceButton.swift`; all `/voice*` routes forward `supports_edit`.
**How:** A changed word becomes a vocab alias + phonetic key immediately; an
unchanged resubmit counts toward whitelisting (2 confirmations); the resubmit
carries `edited_from` and bypasses the gate once.

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
`Views/VocabularyView.swift`.
**How:** The HUD talks to no process — it tails the bus file. Renders by
brain version: `CHAINS[BRAIN_VERSION]` scaffold rail with per-step ⓘ
(copy from `trace.STAGE_INFO`, mirrored in Swift, drift-pinned by
`test_stage_info_parity`). Red is reserved for fatal; review reads amber.

## Personalisation & learning

### Personal vocabulary
**What:** The user's names/places/phrases; transcripts auto-correct through it
before the brain sees them.
**Where:** `assistant/stt/vocab.py`; store `~/.assistant_tools/vocab.json`;
editors: Mac panel tap-a-word + QuickFix, iOS `VocabularyView` /
`VocabImportView` / onboarding; API `/vocab*`.
**How:** Aliases + phonetic keys; learns from tap-a-word, the needs_edit
round-trip, and bulk import mining (contacts/messages candidates). Doubt
whitelist counters live beside the store, never inside it.

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

## Time, halacha & scheduling

### Hebrew calendar & observance
**What:** Jewish/Israeli holidays in the views; Shabbat/yom tov/fast windows
computed from the sky (candle lighting → tzeit) at the user's actual location;
the observance gate on AI-created events; recurring series skip holy days
(meals excepted, fasts inverted, Shabbat-anchored kept).
**Where:** `assistant/observance.py`, `hebrew_calendar.py`;
`db._skip_for_observance`; engine gate in `engine/validate.py`; location from
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
`engine/validate.py`.
**How:** Series instances materialise as rows sharing `series_id`; observance
skipping applies per instance at creation.

### Workout & training scheduling
**What:** Workout templates, live sessions with set logging, stats, and an
observance-aware run/gym planner (fast days, motzei constraints, frequency
rules).
**Where:** `assistant/actions/workout_routine.py`, `schedule_workout.py`; db
`workout_*` tables; iOS `Views/Workout/*`, `Workout/WorkoutStore.swift`.
**How:** The planner reads the same observance windows as the calendar;
voice-triggered via `generate_workout_routine` / `schedule_workout` actions.

## Other tabs

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

## Surfaces & infrastructure

### The API server
**What:** The single front door — 109 endpoints; every surface is its client.
**Where:** `assistant/api/server.py` (HTTP only — no parsing/execution);
generated reference `DOCUMENTATION/API_REFERENCE.md`
(`scripts/gen_api_reference.py`).
**How:** Flask with `--reload`; NDJSON streaming for voice; optional API key;
binds Tailscale with `--tailscale`. Colour-coded logs
(`api/log_color.py`, see `DOCUMENTATION/LOGGING.md`).

### iOS app & offline queues
**What:** The full iPhone client — calendar, tasks, voice, review, vocabulary,
workout, timer — working offline and syncing when the Mac returns.
**Where:** `MACalendar-iOS/`; queues in `LocalStore.swift`; polling via
`GET /changes/token`.
**How:** Three queues (CRUD ops with temp-id repointing, queued voice
recordings, pending LLM commands); burst-refresh after actions; reaches the
Mac over Tailscale only.

### Hosted calendar sync
**What:** Optional two-way Outlook sync and read-only ICS subscriptions —
supported, not required; the default posture is fully local.
**Where:** `assistant/calendar_sync/outlook_sync.py`,
`actions/calendar/graph_client.py`; `calendar_sources` table.
**How:** Dirty-row preservation when two-way is off; ICS rows are locked
read-only.

### Heartbeats & the health CLI
**What:** `assistant doctor` — is every layer wired: LLM, storage, engine,
panel, macOS app, external devices.
**Where:** `assistant/cli.py`; `assistant/heartbeat.py`
(`~/.assistant_tools/heartbeats/`); devices POST `/heartbeat`.
**How:** See `DOCUMENTATION/CLI.md`. The engine layer is version-tied to
`BRAIN_VERSION`; a redesign that forgets the doctor fails the build.

## Development & quality systems

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
