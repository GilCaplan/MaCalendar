# Model comparison — the same engine, different brains-for-hire

Gil's experiment (2026-09-06): hold the ENTIRE system constant — engine code,
prompts, dataset slice, frozen row-timestamps, observance off — and swap only
the LLM behind the deep track: local llama3.1:8b vs Claude Haiku 4.5 vs
Claude Sonnet. A harness-only simulation (`--llm claude:<model>`); the product
itself stays offline-only.

Sandboxing: each run gets its own scratch calendar/todo/memory instances (the
harness tempdir isolation), its own out-dir under
`DOCUMENTATION/experiments/engine_compare/model_<name>/`, and runs from the
app worktree so the improvement loop's checkout is untouched.

## Runs

| model | slice | count-correct | F1 | precision | recall | field quality | complex | e+e | t+t | e+t | p50 ms | wall-clock |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| llama3.1:8b (epoch baseline) | dev-fast 250 | *pending* | | | | | | | | | | |
| claude-haiku-4-5 | dev-fast 250 | *blocked on API key* | | | | | | | | | | |
| claude-sonnet | dev-fast 250 | *blocked on API key* | | | | | | | | | | |

## Reading

*(filled after the runs: where the small local model actually loses, whether
the engine's deterministic scaffolding narrows the gap, what latency money
buys, and which failure classes survive even a frontier model — those are the
engine's own bugs, not the model's.)*
