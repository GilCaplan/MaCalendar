# MACalendar — System Overview

| Platform | Doc |
|----------|-----|
| **Mac App** (PyQt6 voice assistant) | [SYSTEM_MAC.md](SYSTEM_MAC.md) |
| **iPhone App** (SwiftUI + Flask API) | [SYSTEM_IPHONE.md](SYSTEM_IPHONE.md) |

## Quick Facts
- **DB**: `~/.assistant_tools/calendar.db` (SQLite, Mac is source of truth)
- **GitHub**: `https://github.com/GilCaplan/MACalendar`
- **Mac launch**: `python -m assistant.main` or `Launch Calendar.command`
- **iPhone API**: `python -m assistant.api --lan`
- **LLM engine**: configured via `config.yaml` → `llm_engine` (ollama/openai/gemini/claude)
