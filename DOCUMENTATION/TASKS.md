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
| 48 | **A multi-item task command made one task.** "buy chicken and rice" became one task — the LLM merged it (sometimes into an invented "buy groceries"), the rule path kept the verb only on the first. One task per item now, verb shared out, tag inferred from each title | done 2026-08-31 | `assistant/intent/list_split.py`, `assistant/actions/todo/tagging.py` |
| 49 | **The trace was only visible if you were looking at the calendar** — which you are not when you speak to the assistant from your phone. It is its own always-on-top app now: never takes focus, translucent until hovered, works with the calendar closed | done 2026-08-31 | `assistant/thinking_hud.py`, streaming `assistant/trace_bus.py` |

| 50 | Same brain for both devices: the GUI stopped parsing locally and now POSTs to `assistant.api` like the phone does; ~1,200 lines of duplicated orchestration deleted | done 2026-09-01 | `assistant/pipeline.py`, `assistant/api/server.py` |
| 51 | The LLM now validates **every** command, not only low-confidence ones — a confident wrong parse was the one case nothing was checking | done 2026-09-01 | `verify_fast_path` in `config.example.yaml`, `server._run_transcript` |
| 52 | Thinking panel: stopped re-popping, keeps a searchable history of every run, filters by device / kind / outcome, and separates test traffic from real use | done 2026-09-01 | `assistant/calendar_ui/thinking_panel.py`, `assistant/thinking_hud.py`, `trace_bus.read_history` |
| 53 | Repeating events understand "every day at 7pm until Oct 6" — "until" exclusive unless stated, and occurrences on Shabbat and chag are skipped using locally-computed sundown (meals excepted, fasts not) | done 2026-09-01 | `assistant/db.py` `_skip_for_observance`, `assistant/observance.py` |
| 54 | Personal vocabulary gained two more powers beyond spelling fixes: expand an acronym, and carry a label used for task tags and event colours | done 2026-09-01 | `assistant/stt/vocab.py`, `assistant/actions/todo/tagging.py` |
| 55 | **Settings UI for the vocabulary** — view, edit and clear labels and acronyms on both iOS and macOS, with the user's permission required before anything is added | done 2026-09-03 | `VocabularyView.swift`, Mac Settings |
| 56 | **The harness** — `--memory` replays against a copy of the real history and `--memory-k N` changes the retrieval count, so k=0 vs k=4 is one flag. Originally: a memory-aware audit mode so the personalisation layer can be measured at all — does history help, is `k=4` right, are verified examples better | done 2026-09-03 | `scripts/audit_assistant.py --memory` |
| 57 | **Confidence calibration** — the score is now recorded (`examples.confidence`) and `scripts/calibration.py` reads it back; waiting on a week of real use to have anything to say. Originally: the multipliers in `_compute_confidence` are hand-picked and have never been checked against outcomes. The audit already records score and correctness, so bucketing by score answers it | todo | `assistant/intent/rule_parser.py` |
| 58 | Two-level label hierarchy (Exercise → Running / Gym) and promoting the planner's ad-hoc categories into the registry | todo | `categories.py`, `tagging.py` |
| 59 | Ask for 👍/👎 only when the self-check is unsure, instead of on every command — `scratchpad/flag_precision.py` measures whether its opinion agrees with the user's before this is built | todo | review flow |
| 60 | Few-shot pool: prefer verified examples, and stop recency from evicting corrections | todo | `assistant/intent/parser.py` `_few_shot_for` |
| 61 | Three iOS fixes committed but not installed on the device — poll storm, counter history sheet, speech continuing after it was turned off | done 2026-09-02 | `xcrun devicectl device install app` |
| 62 | Explainer artifacts: big-picture done; internals page still needs genericising, a first-time-reader rewrite, and interactive figures | done 2026-09-03 | `DOCUMENTATION/ARTIFACT_BUILDER.md` |
| 63 | **"pasta times 5" made five identical tasks.** Neither parse path could represent a count, so the only way the LLM could say "five" was to repeat the title five times — and five identical rows mean ticking one tells you nothing. Counts are now read from the words, repeats are folded, and the number shows on the task row | done 2026-09-02 | `assistant/intent/quantity.py`, `todos.quantity`, `TaskRowView.swift`, `todo_view.py` |
| 64 | **Sundown was computed for a hardcoded place.** `ObservanceSettings` defaults and the `observance:` config block held the same values but nothing connected them, so any call without an explicit settings object — including the recurrence Shabbat skipping — ignored the configuration | done 2026-09-03 | `observance.current_settings()`, `tests/unit/test_observance_settings.py` |
| 65 | Device location: the phone reports its coordinates so sundown follows you, off by default, with a Settings toggle that also clears it | done 2026-09-03 | `observance.set_location`, `/observance/location`, `DeviceLocation.swift` |
| 66 | Sundown verified against published times rather than trusted: fetched once from an authority, checked in, compared offline. 126 comparisons over 6 cities, worst disagreement 28 s — no fix needed | done 2026-09-03 | `scripts/fetch_zmanim_reference.py`, `tests/unit/test_zmanim_accuracy.py` |
| 67 | **Misheard names could never be learned.** Every failed name was already in the word list, but the matcher compared letters while speech fails phonetically, so no correction was made, none was learned, and the same command failed forever. A sound-code gate recovers 5 of 6 on first encounter, up from 1 | done 2026-09-03 | `vocab.phonetic_key`, `tests/unit/test_vocab_phonetic.py` |
| 68 | Third explainer: an explorable drawing rather than 6,600 words of prose | in review | `DOCUMENTATION/artifacts/explorer.html` |
| 69 | Explorer: the trace log opened the review panel's text (both carried the same panel id); storage panel too long to read; nothing described how several events in one sentence, or a queue of recordings, are handled | done 2026-09-03 | `DOCUMENTATION/artifacts/explorer.html` |
| 70 | Explorer named the deciding process "the brain" and the model host "model server", so a reader concluded the server held all three models. It holds one — spaCy and Whisper load inside the deciding process, which the drawing hid | done 2026-09-03 | `explorer.html`, `test_artifact_claims.py` |
| 71 | **Reformulation mining**: when a command is deleted and a near-identical one succeeds moments later, the pair is a correction the user already gave for free. Runs after every command, on a daemon thread. Finds nothing in the current history — the loose version found three pairs and two were nonsense | done 2026-09-03 | `assistant/intent/memory.py` |
| 72 | Four false starts ("Execute.", "No.", "I need a b-") were parsed, executed and remembered as real commands, teaching the model that junk is normal | done 2026-09-03 | `server.is_trivial_transcript` |
| 73 | **Ran the memory comparison.** k=4 98% vs k=0 97% over 89 commands — but the LLM path, the only place examples enter the prompt, is 100% in both arms, so the corpus cannot detect an effect on it. No measurable difference, and the instrument is the limitation | done 2026-09-03 | `ASSISTANT_AUDIT_SUMMARY.md` run 7 |
| 74 | Build a corpus from the real history's *failures* to measure the memory — the hand-written one is at ceiling on the path that matters, so it can only detect harm | in progress 2026-09-03 | `scripts/audit_assistant.py` corpus, see 75/76 |
| 75 | **Found and fixed while mining row 74**: editing one event in a same-typed batch ("book gym, then a meeting, then dinner") applied that edit's fields to every same-typed action in the batch, corrupting the others' stored correction — `example_records` only tracked action *type*, not which specific action a record came from. Two real corpus cases added from the same mining pass (duration arithmetic, a dropped self-correction), both still reproduce live | done 2026-09-03 | `assistant/intent/memory.py` `feedback_for_record`, `tests/unit/test_vocab_memory_trace.py` |
| 76 | **Memory scaling study, in progress overnight**: does retrieval pool *size* matter, and is any k>0 effect about personalisation specifically or just "having more examples"? Real history (74 commands, 65% from one day) can't grow, so built a second pool from HWU-64 (Liu et al. IWSDS 2019, CC BY 4.0) — 3000 real calendar/reminder utterances run through the actual parser against scratch DBs, nested tiers at 60/300/1000/3000. Comparing k-sweep on the real history, a held-out slice (dominant day + the row 75 bug's corrupted correction removed), and each external tier. Fixture and build script checked in, `.db` outputs regenerable and gitignored | in progress 2026-09-03 | `scripts/fetch_hwu64_sample.py`, `scripts/build_memory_scaling_pool.py`, `DOCUMENTATION/experiments/memory_scaling/` — results land in `ASSISTANT_AUDIT_SUMMARY.md` |
| 77 | **The audit's headline "N% accurate" collapsed two different failure modes**: missing something asked for vs. producing something extra. `_check()` now tracks each expected item individually and counts extra actions/task rows explicitly, so the report gets recall and precision — overall, by area, by parse path — plus a dedicated "produced more than expected" section. Confirmed it surfaces something real: tasks area is 95% recall but 79% precision, driven by the row 75/76-adjacent duplicate-task bug. Headline number also now labelled explicitly as case-level exact match against the hand-written corpus, not a real-usage or human-judged figure. `A_k0`/`A_k1` of the overnight run predate this and lack the breakdown — cheap to backfill (~15-20 min each) once the rest finishes | done 2026-09-03 | `scripts/audit_assistant.py` `_check`, `_recall_precision` |
| 78 | **Linux/PC host migration checked, deferred.** Core (parser, Ollama, spaCy, API, DB, GUI via PyQt6, default STT) is already cross-platform — no work needed. One real blocker: TTS shells out to macOS `say` directly, on by default, in the live voice pipeline (not just dev tooling) — needs swapping for a cross-platform engine (`pyttsx3` / `espeak`) before a Linux host would actually speak replies. Minor, non-blocking degradations: the thinking HUD's "join all Spaces" polish is an AppKit best-effort layer with no Linux equivalent yet (falls back to a normal always-on-top window); optional macOS Calendar.app import wouldn't apply; launch script and weekly-review scheduling are trivially cron-able | todo | `assistant/tts/speaker.py` |

| 79 | **Engine v2 — the brain rebuilt as the 7-step deep track** (branch `engine-v2`). The old `_run_transcript` (~800 lines of interleaved heuristics, plus four background bolt-ons) retired and replaced by `assistant/engine/`: frozen per-stage contracts (`state.py`, `ENGINE.md`, `test_engine_contracts.py`), fast track (instant rule-parser commit) + deep track (segment → decompose → validate → generate → commit → label → crosscheck), every old named rule ported into `validate.py` with its regression tests, observance gate for AI-created events (leyning/meals/davening on holy days, fasts exclude meals), `needs_edit` transcript-confirmation round-trip gated on `supports_edit`. Done so far: contracts + skeleton + strip + docs rebuild, 970 unit tests green. Remaining, stage-gated: LLM segmentation (2), LLM decomposition (3), text repair (4), crosscheck build w/ tiered patches + verify token (6), step-1 learning loop + Mac edit dialog, intake coalescing (0), per-stage audit lines, full audit vs run-7 baseline | in progress 2026-09-03 | `assistant/engine/`, `DOCUMENTATION/ENGINE.md` |

## How we are working right now

**Row 79 (engine v2) is the current thread on branch `engine-v2`** — the plan
lives in the row; contracts are frozen, remaining work is stage-gated
(build → independent test vs real Ollama → revamp → next stage), and the
merge gate is the full audit beating the recorded run-7 baseline in
`ASSISTANT_AUDIT_SUMMARY.md`. No audits until the row-76 overnight jobs
finish — two model-loading jobs side by side segfault.

Previous thread, as of 2026-09-03 (still relevant on `main`):

**Row 76 is running unattended overnight.** If you're picking this up cold:
`DOCUMENTATION/experiments/memory_scaling/build.log` has the pool-build
progress; `scripts/build_memory_scaling_pool.py` is resumable, so if it died
just re-run it. Once the pool exists, `--slice-tiers` exports the nested
60/300/1000/3000 dbs, then each tier runs through
`scripts/audit_assistant.py --memory --memory-source <tier db>` at k=4 (k=0
only needs running once — pool size cannot affect it, nothing is retrieved).
Conclusions go in `ASSISTANT_AUDIT_SUMMARY.md`, not the overwritten
`ASSISTANT_AUDIT.md`. Also queued, same session: the k=0/1/2/4/8 sweep on the
real history (dataset A) and the held-out-day check (dataset B) from before
the scaling study was scoped up — see the run log in that summary once it
lands.

Decisions still waiting on a number, not yet worth arguing about: `k` itself,
the eviction policy, the confidence weights (row 57, also waiting on a week
of real use), whether labelling should move to the LLM.

## Working agreements
- Everything on the phone is local: no third-party services; the only network peer is the Mac over Tailscale.
- Prefer doing work directly over spawning sub-agents; keep context small (`/compact` between big tasks).
