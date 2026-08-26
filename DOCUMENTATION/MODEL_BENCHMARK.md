# LLM model benchmark — intent parsing

_Generated 2026-08-26 11:20 · 10 commands · best of 2 run(s) per command · memory few-shot OFF · machine: arm64_

Re-run with `python -m scripts.benchmark_models` (see flags in the file header).

## Summary

| Model | Exact | Action | Fields | p50 latency | max latency | errors |
|---|---:|---:|---:|---:|---:|---:|
| `llama3.1:8b` | 90% | 90% | 100% | 5.79 s | 56.26 s | 0 |
| `llama3.2:3b` | 60% | 70% | 33% | 2.11 s | 7.66 s | 0 |

**Exact** = right actions *and* every checked field. **Action** = right action sequence. **Fields** = share of checked fields (date/time/recurrence) that were correct. Latency is the full parse call (prompt → validated intents) with the model kept warm.

## `llama3.2:3b`

| ✓ | s | command | parsed as | notes |
|---|---:|---|---|---|
| ✗ | 7.66 | walk Kyra the dog at 3:30 pm today and then go to Shaul for Minchat Maariv at 7:30 pm | create_event | fields 0/4 |
| ✗ | 2.31 | set a meeting for me tomorrow at 1 p.m. set another one at 4 p.m. and then pizza at 6:30 p.m. tomorrow | create_event | fields 0/6 |
| ✓ | 2.59 | set a meeting for me next week on wednesday at 2pm with technion regarding project funds for ta costs | create_event |  |
| ✓ | 2.34 | add on the 19th at 9 a.m. exam for eurovision course online | create_event |  |
| ✗ | 1.63 | remind me to buy groceries and call the dentist | create_event | fields 0/0 |
| ✓ | 1.16 | move my 1pm meeting tomorrow to 3pm | update_event |  |
| ✓ | 0.66 | delete the pizza party on friday | delete_event |  |
| ✓ | 0.82 | what do I have on tomorrow | query_schedule |  |
| ✓ | 2.48 | schedule gym every monday at 6 am | create_event |  |
| ✗ | 1.92 | lunch with Amichai at noon on thursday at edo's | create_event | fields 0/2 |

## `llama3.1:8b`

| ✓ | s | command | parsed as | notes |
|---|---:|---|---|---|
| ✓ | 42.90 | walk Kyra the dog at 3:30 pm today and then go to Shaul for Minchat Maariv at 7:30 pm | create_event, create_event |  |
| ✓ | 56.26 | set a meeting for me tomorrow at 1 p.m. set another one at 4 p.m. and then pizza at 6:30 p.m. tomorrow | create_event, create_event, create_event |  |
| ✓ | 26.64 | set a meeting for me next week on wednesday at 2pm with technion regarding project funds for ta costs | create_event |  |
| ✓ | 5.70 | add on the 19th at 9 a.m. exam for eurovision course online | create_event |  |
| ✗ | 5.93 | remind me to buy groceries and call the dentist | create_todo, create_todo | fields 0/0 |
| ✓ | 3.89 | move my 1pm meeting tomorrow to 3pm | update_event |  |
| ✓ | 3.26 | delete the pizza party on friday | delete_event |  |
| ✓ | 2.29 | what do I have on tomorrow | query_schedule |  |
| ✓ | 5.89 | schedule gym every monday at 6 am | create_event |  |
| ✓ | 5.53 | lunch with Amichai at noon on thursday at edo's | create_event |  |

## Notes and decisions (2026-08-26)

- **Run 1** (all four models, single run) overlapped with the API server warm-up and a Whisper comparison; with two 5 GB models resident on a 16 GB M4 it swapped, so its latencies were meaningless. Accuracy ranking from that run: llama3.1:8b 90 % > llama3.2:3b 80 % > qwen2.5:7b 60 % > qwen2.5:3b 50 %.
- **Run 2** (table above, one model resident at a time, best of 2): llama3.1:8b 90 % exact / 100 % of fields; llama3.2:3b 60 % — it collapses multi-event commands into one event, which is this user's most common shape. The 3B model is not usable as the first-pass parser; two-tier (3B first, 8B verify) was rejected.
- llama3.1:8b latencies in run 2 were still contention-affected (42–56 s on multi-event cases). Measured again in isolation with the model warm: **2.3–2.6 s** for a query, **5–6 s** single event, **~11 s** for three events (~15 tok/s generation; prompt eval is cached because the 17 k-char system prompt is byte-identical between calls — the memory few-shot block is placed in the user turn for exactly this reason).
- Both llamas fail the same case: "remind me to buy groceries and call the dentist" → two `create_todo` actions instead of one with two titles (harmless: two tasks are created). Expected-answer in the case set may be too strict.
- Decision: `model: llama3.1:8b`, `verify_model: null`, `keep_alive: "30m"`. qwen2.5:7b/3b and llama3.2:3b removed from disk.

## STT engines (same day, two synthetic clips via macOS `say`)

| Engine | Latency / clip | Accuracy on names + Hebrew terms |
|---|---:|---|
| faster-whisper base, int8 CPU (previous default) | 3.3–3.5 s | good |
| **mlx-whisper base, Apple GPU (new default, `stt_engine: mlx`)** | **1.9–2.1 s** | same as CPU base |
| mlx-whisper small, GPU | 5.0 s | slightly worse on Hebrew terms |
| mlx-whisper large-v3-turbo, GPU | 7.5 s | no better |

Latencies were measured while the LLM benchmark was also using the GPU; ranking is robust, absolute numbers are pessimistic. The vocabulary `initial_prompt` was active in all rows (it is what made "Yotam"/"Kyra" come out right).
