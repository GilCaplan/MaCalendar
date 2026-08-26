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

Speed: Ollama `keep_alive: -1` + startup warm-up of Whisper, spaCy and the LLM (`warm_up_components`) remove the cold-start cost that made the first phone command take 10–20 s.
