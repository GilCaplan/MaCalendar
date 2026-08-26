# Assistant audit — summary & gap list (2026-08-26)

Three runs of `scripts/audit_assistant.py` (84 generated commands + 8 audio, scratch DB, real vocabulary) on the M4 / llama3.1:8b setup. Raw per-run reports: `ASSISTANT_AUDIT.md` (latest) and the JSON next to it.

## Progression

| Run | Quick answer ✓ | Settled ✓ | First result p50 / p95 | Settled p50 | What changed before it |
|---|---:|---:|---:|---:|---|
| 1 | 45 % | 44 % | 9.5 s / 18.9 s | 26.8 s | baseline after num_ctx fix |
| 2 | 71 % | 69 % | 8.3 s / 17.9 s | 25.8 s | vocab false-positive guard; task-title extraction; sanity pass (past dates, recurrence, junk events); conservative self-check; prompt rules |
| 3 | **88 %** | **86 %** | **7.9 s / 15.8 s** | 24.1 s | deterministic relative-date resolution; self-check guards (no task→event flips); rule-parser titles with attendees; time-format normaliser |

By area, run 3: query 100 %, adversarial 100 %, mixed 100 %, events 90 %, update/delete 86 %, tasks 83 %, chat-phrasing 80 %.
By path: **rule fast path 91 % correct at 0.1 s**; LLM path 88 % at ~10 s; hybrid 75 %.

## Bugs found and fixed today (all verified by the harness or unit tests)

1. **Ollama context window** — default 4096 < our ~4k-token system prompt. Every call overflowed: prefix cache lost (30–60 s calls) and the date table truncated (wrong weekdays). `ollama.num_ctx: 8192`.
2. **Placeholder-date leak** — few-shot examples used `<resolve-from-today>`; the 8B model copied it into real events (two junk rows existed in the real calendar). Dates are now stripped from examples and `CalendarIntent` rejects non-ISO dates / normalises `12:00 PM`.
3. **Vocab auto-correct false positives** — with 300+ words, fuzzy matching rewrote *Shacharit→Nachman, Mincha→Liora, Tamar→Meshulam, Golda→Peleg* and learned bad aliases. Now: never rewrite an English or already-known word, stricter thresholds for short words, first letter must match, aliases only learned at ≥0.9 or when you teach them.
4. **Rule parser tasks** — "remind me to buy milk" produced a task titled *me*; "I need to…" routed to complete_todo; "put X on the groceries list" to query. Phrase-level extraction + route overrides; "remind me about X at 9 am" becomes an event.
5. **Relative dates** — the LLM picked yesterday's or today's weekday ~40 % of the time. Weekday/tomorrow/"the 19th" phrases are now resolved deterministically on the server and override the model; past dates are bumped.
6. **Recurrence** — "every monday / daily / mondays" never set `recurrence`; now set from the transcript.
7. **Self-check** — proposed a change on 98 % of commands, fixed 0–3, broke 2–4 per run. Patches are now filtered (times must be spoken in the command, no date/list changes, titles only over placeholders, no task→event flips) **and it is advisory by default** (`self_check_apply: false`): visible in the trace/log, not applied.
8. **Server/phone parity** — trailing "execute" stripped, keyword titles ("set meeting") fixed in the background, title-fixer no longer puts dates/times in titles, prompt-cache-friendly prompts for all three LLM call types.

## What is good

- The rule fast path is the star: 91 % correct, 100 ms, no LLM. Most single events, queries, deletes and simple tasks never touch the model.
- Multi-event commands (2–3 events, same or different days) now parse correctly on the LLM path in the large majority of cases.
- The trace makes every failure diagnosable from the phone; the harness reproduces them in minutes.
- Vocabulary + Whisper prompt: names that appear in the vocab come out right in audio tests (Ravid, Tal, Golda, Technion).

## Remaining gaps (ranked)

1. **Rule parser splits multi-event sentences into one** ("lunch with Tal on monday at noon and coffee with Ezra on friday at 9" → only lunch). It is confident (0.90), so the LLM never sees it. Fix: lower confidence when a span contains two time expressions, forcing hybrid.
2. **Ambiguous bare hours** ("Kems tomorrow at 8" → 8 AM). Fix: heuristic — evening-ish venues/words (dinner, Kems, drinks, pregame) or hours 1–6 without am/pm → PM; ask when truly ambiguous.
3. **Hybrid over-creation** for task lists with due dates ("two tasks due tomorrow…" adds an event; "buy a gift due thursday" becomes events). Fix: when the rule parser identified create_todo, forbid create_event in the hybrid prompt.
4. **update_event rename / "moved from 9:30 to 9"** — rename not supported by the rule slots; "moved from…to…" needs match_start_time=9:30, new_start_time=9:00.
5. **Disfluencies** ("at 2 sorry not 2, 3 pm") — the LLM usually gets it; the self-check "corrected" it back. Keep self-check advisory.
6. **Whisper** (3/8 audio correct with synthetic voices): "Talat noon", "Adjim" — beyond vocab's reach. Options: whisper-small when idle, or a second-pass STT on low-confidence segments.
7. **Latency** — LLM path ~8–10 s first result, dominated by ~15 tok/s generation of JSON with a 4k-token prompt. Options: trim the system prompt (schemas are verbose), a smaller JSON envelope, or a faster model for the first pass with the 8B as verifier once RAM allows.

## How to re-run

```
python -m scripts.audit_assistant --audio            # full, ~20 min
python -m scripts.audit_assistant --area tasks       # one area
python -m scripts.benchmark_models --history         # LLM models on your real history
```
