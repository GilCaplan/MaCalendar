# MACalendar — System Overview

| Platform | Doc |
|----------|-----|
| **Mac App** (PyQt6 voice assistant) | [SYSTEM_MAC.md](SYSTEM_MAC.md) |
| **iPhone App** (SwiftUI + Flask API) | [SYSTEM_IPHONE.md](SYSTEM_IPHONE.md) |

## Quick Facts
- **DB**: `~/.assistant_tools/calendar.db` (SQLite, Mac is source of truth)
- **GitHub**: `https://github.com/GilCaplan/MACalendar`
- **Mac launch**: `python -m assistant.main` or `Launch Calendar.command`
- **iPhone API**: `python -m assistant.api --tailscale` (auto-started by `Launch Calendar.command`)
- **LLM engine**: configured via `config.yaml` → `llm_engine` (ollama/openai/gemini/claude)
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
