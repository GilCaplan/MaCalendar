# MACalendar — System Overview

| Platform | Doc |
|----------|-----|
| **Mac App** (PyQt6 voice assistant) | [SYSTEM_MAC.md](SYSTEM_MAC.md) |
| **iPhone App** (SwiftUI + Flask API) | [SYSTEM_IPHONE.md](SYSTEM_IPHONE.md) |
| **Code map** (file + line pointers for every subsystem) | [CODE_MAP.md](CODE_MAP.md) |

## For AI Agents Working on This Repo

Before fixing a bug or adding a feature, **read `CODE_MAP.md`** — it has precise file+line pointers for every subsystem so you can jump straight to relevant code without broad codebase searches.

**When to update `CODE_MAP.md`:** After touching a file in a non-trivial way (new class, moved method, changed a key line), update the relevant table row. Do this only for the specific rows that changed — don't rewrite the whole file. Skip it for cosmetic or one-liner fixes.

**Don't over-document:** Only record things that are *surprising*, *non-obvious*, or *hard to find by name search*. Common patterns, obvious method names, and things grep finds in one try don't need a pointer.

## Quick Facts
- **DB**: `~/.assistant_tools/calendar.db` (SQLite, Mac is source of truth)
- **GitHub**: `https://github.com/GilCaplan/MACalendar`
- **Mac launch**: `python -m assistant.main` or `Launch Calendar.command`
- **iPhone API**: `python -m assistant.api --tailscale` (auto-started by `Launch Calendar.command`)
- **Thinking HUD**: `python -m assistant.thinking_hud` (auto-started too) — an always-on-top card, deliberately its own app rather than part of the calendar window, so a command given from the phone is visible in whatever you were actually working in. Fed by `assistant/trace_bus.py`; never takes focus
- **LLM engine**: configured via `config.yaml` → `llm_engine` (ollama/openai/gemini/claude)
- **NLU Tracking**: `DOCUMENTATION/NLU_TRACKING.md` — auto-appended after every action (success + failure) from both Mac and iOS, labelled by parse method and source
- **Scenario Bugs**: `DOCUMENTATION/SCENARIO_BUG.md` — auto-appended on failures (parse errors, unknown intents, action errors) for regression review
- **Cross-Platform Sync**: Tasks and recurring events synchronized between Mac (PyQt) and iOS (SwiftUI).
- **Customizable Appearance**: Persistent Dark/Light mode and granular font size controls for all calendar views (Month, Week, Day, Tasks).
- **Dynamic Density**: Interactive "stretch/tighten" Settings dialog on Mac with a dedicated "Compact Layout" toggle.
- **Smart Recurrence**: Edit whole series or single instances with an intuitive prompt.
- **Task Management**: Native drag-and-drop reordering on both platforms.

## NLU Parse Path
```
Voice command
  → RuleBasedParser (7-phase, spaCy + Recognizers-Text)
       ├─ confidence ≥ 0.85 → execute immediately + background LLM verify
       │     └─ verify: ok (silent) | minor (patch) | major (undo + redo)
       ├─ partial → parse_with_context() [LLM fills gaps from pre-analysis]
       └─ skip/complex → full IntentParser.parse() [LLM from scratch]
```

## Log prefixes
- `🖥️` — Mac app logs (pipeline, audio, STT, LLM, actions)
- `📱` — iPhone API logs (audio received, transcript, parsed actions, response)

## Personalisation layer (added 2026-08-26)

| Piece | File | What it does |
|---|---|---|
| Vocabulary | `assistant/stt/vocab.py` | Personal words (names, Hebrew, places). Fed to Whisper as `initial_prompt`; transcripts auto-corrected via learned aliases + fuzzy match (difflib ≥ 0.80, protected common words). Every fuzzy fix is remembered as an alias. Store: `~/.assistant_tools/vocab.json` (local only). |
| Onboarding | `assistant/stt/vocab_onboarding.py` | First-run interview (6 questions) + opt-in starter packs (prayer/Shabbat, holidays, Israeli life, family, life events). iOS `VocabOnboardingView`, Mac `VocabDialog › Set up…`. |
| Command memory (RAG) | `assistant/intent/memory.py` | Every command → executed intents → result → timings in `~/.assistant_tools/nlu_memory.db`. Edits/deletes of a voice-created record within 24 h become `corrected`/`rejected` feedback (hooked in `db.update_event/delete_event/update_todo/delete_todo`). `few_shot_block()` injects the k most similar examples (dates masked) into the LLM system prompt (`nlu.memory_examples`). Also holds the **pending queue** of commands that failed because the LLM was offline; the API server retries them every 30 s. |
| Trace | `assistant/trace.py` | Stage-by-stage "thinking" log with ms timings. Returned in `/voice` responses and streamed live as NDJSON from `POST /voice/stream` (iOS `ThinkingView`, toggle in Settings › Voice). |
| Self-check | `IntentParser.verify_actions_async` + `server._run_server_verify` | After execution on **any** path, a background LLM call re-reasons over transcript + executed actions + user history and applies minor patches / undo-redo on the Mac; phone polls `GET /voice/verify/<token>` for the outcome. |
| Benchmark | `scripts/benchmark_models.py` → `DOCUMENTATION/MODEL_BENCHMARK.md` | Accuracy + latency of Ollama models on real commands. |

New endpoints: `GET/POST /vocab`, `POST /vocab/alias`, `DELETE /vocab/<word>[?alias=]`, `PATCH /vocab/settings`, `POST /vocab/preview`, `GET/POST /vocab/onboarding`, `GET /memory`, `GET /memory/similar?q=`, `POST /memory/<id>/feedback`, `DELETE /memory/<id>`, `GET /pending`, `POST /pending/<id>/retry`, `DELETE /pending/<id>`, `POST /voice/stream`. `/health` now reports `llm_status` (`ok` / `offline` / model not pulled).

Speed: Ollama `keep_alive` (`-1` = keep loaded forever, or e.g. `"30m"`; `config.yaml` currently uses `30m`) + startup warm-up of Whisper, spaCy and the LLM (`warm_up_components`) remove the cold-start cost that made the first phone command take 10–20 s.

## Event categories & colours

`assistant/actions/calendar/categories.py` tags every new event (Work, Study, Meeting, Social, Family, Prayer, Fitness, Health, Errand, Meal, Travel, Personal) from its title/attendees/location with a keyword classifier — "Personal" when unsure — and picks the category colour. If the event immediately before or after on the same day already has that colour, the category's alternate shade is used, so two adjacent events never look the same. A colour chosen by hand is never overridden. Users add/remove categories, change colours and keywords from iOS → Settings → *Event colours* (stored in `~/.assistant_tools/categories.json`, local only). API: `GET/POST /categories`, `DELETE /categories/<name>`, `POST /categories/classify`, `POST /categories/recolor[?force=1]` (backfills existing events).

## Sync between Mac and phone

Both apps read and write the same SQLite file (`~/.assistant_tools/calendar.db`) — the phone through the Mac's API. The Mac app polls the DB's modification time every 5 s and reloads calendar, tasks and the Timer tab when it changes. The phone polls every 30 s while idle, and drops to **1 s for 45 s after a voice command** (10 s after a manual edit) via `APIClient.burstRefresh`, so both sides settle together; the Timer tab polls every 3 s while any timer is running.

## Guests and invitations

`attendees` on an event is a comma-separated list of names (the voice assistant fills it from "meeting with Noa"). On the phone, Edit Event → Guests looks up each name in the phone's own Contacts (permission asked once; nothing stored or uploaded) and offers Messages (`sms:`), WhatsApp (`wa.me`), Mail (`mailto:`) or a share sheet with an `.ics` file. There is no server-side mail/SMS integration and no online dependency.

## Recording controls (phone)

Recording stops on tap, on a stop word ("execute", "done"…) or after silence (Settings → Voice; the silence auto-stop can be turned off). With "Ask before sending" on, a Redo / Add more / Send bar appears for 4 s — *Add more* resumes the same recording so a sentence cut off early can be finished.

## Referring to events by voice

`_normalise_intents` in `assistant/api/server.py` pins `update_event`/`delete_event` to what was said: "the event I just made / the last one" → the last created event; a weekday named in the sentence → `match_date`, so "fix the meeting on Sunday" cannot land on a different day's meeting. `_find_event` scores only distinctive title words (generic words like "meeting" never pick an arbitrary event).

## Training plans around Shabbat and the chagim (added 2026-09-01)

| Piece | File | What it does |
|---|---|---|
| Observance rules | `assistant/observance.py` | Answers "may I train on this day, and when?" — distinct from `hebrew_calendar.py`, which answers "what is this day called?" for display. Classifies Shabbat, yom tov, chol hamoed and fasts, and returns the run-able `TimeWindow`s for a date. Sunset/nightfall via `astral` (pure Python, offline); location and buffers from `config.yaml › observance`. |
| Scheduler | `assistant/workout_plan.py` | Places `SessionSpec`s on legal dates and materialises them into calendar events. Holds *training policy* (the arguable half) as distinct from observance (the computed half). |
| Program content | `assistant/programs/` | Session content with *preferred* dates only. `autumn_5k.py` is the 2 Sep – 17 Oct 2026 base block ending in a 5K time trial. |
| AI entry point | `assistant/actions/schedule_workout/` | "add an easy 8k Thursday morning", "plan four more weeks". The LLM proposes dated sessions; every date is re-placed by the scheduler before it reaches the calendar. |
| Seeding | `scripts/seed_running_plan.py` | Previews a block by default; `--commit` writes it, `--replace` re-seeds without duplicating. |

**The distinction that makes this work.** `hebrew_calendar.enumerate_holidays()` collapses consecutive days sharing a name into one span, so Sukkot 2026 comes back as a single block from 25 Sep to 2 Oct. Scheduling against that would blank out all of chol hamoed — the freest training week of the autumn. `observance.py` instead uses `HebrewDate.festival(israel=True, include_working_days=False)`, which names a day only when work is forbidden and returns `None` on chol hamoed, Chanukah and Purim.

**The evening belongs to the next day.** A civil date is modelled as two independently governed slots: its daylight, governed by itself, and its evening, governed by the *following* date. That is why motzei Shabbat is available on Sat 3 Oct 2026 (Shmini Atzeret ends) but not on Sat 12 Sep 2026 (Rosh Hashanah II follows).

**Yom Kippur is both a festival and a fast.** pyluach files it under `festival()` and returns `None` from `fast_day()`; `observance.fast_day_name()` normalises it back so either question gets a true answer. Tisha B'Av is spelled `"9 of Av"`.

**Observance is computed, policy is arguable.** Only halacha lives in `observance.py`. "A minor fast is a full rest day", "motzei Shabbat is a last resort", "48 hours between hard sessions", "no heavy legs the day before a long run" are all `SchedulePolicy` in `workout_plan.py`, configurable and overridable. Keeping the line sharp is what lets the scheduler trust the observance answers absolutely — an LLM may propose dates, but placement is deterministic and re-validated.

**Running sessions.** `workout_template_sets` gained `distance_m` and `target_pace_sec_per_km` (set `type` `'distance'`), so an interval session reuses the existing block/set/session/log machinery — and the follow-along that rides on it — rather than duplicating it. The iOS Swift models do not yet carry these fields; running templates are Mac/backend-only until they do.

New endpoints: `GET /workout/plans`, `GET/DELETE /workout/plans/<id>`, `GET /workout/plan-items`, `PATCH /workout/plan-items/<id>`, `GET /observance?start_date=&end_date=` (per-day availability, so a client can show *why* a day is blocked without reimplementing the Hebrew calendar).
