# Assistant audit — accuracy, latency, self-check

_Generated 2026-09-03 01:30 · 1 commands · scratch DB · vocabulary 374 words · machine arm64. Re-run: `python -m scripts.audit_assistant`._

## Headline

- **Correct after the quick answer:** 100%  ·  **correct once settled (after self-check):** 100%
- **Time to first result:** p50 0.0 s · p95 0.0 s  ·  **time to settled:** p50 12.1 s · p95 12.1 s
- Parse paths: rule 1, hybrid 0, llm 0, error 0

## By area

| Area | n | quick ✓ | settled ✓ | first p50 | first p95 | settled p50 |
|---|---:|---:|---:|---:|---:|---:|
| events | 1 | 100% | 100% | 0.0 s | 0.0 s | 12.1 s |

## By parse path

| Path | n | quick ✓ | settled ✓ | first p50 | first p95 | LLM ms p50 |
|---|---:|---:|---:|---:|---:|---:|
| rule | 1 | 100% | 100% | 0.0 s | 0.0 s | 0 |

## Quick answer vs self-check

- Self-check ran on 1 commands; it proposed a correction on 0 (0 applied).
- **Fixed by self-check:** 0  ·  **broken by self-check:** 0

## By shape (failures first)

| Shape | n | settled ✓ | first p50 |
|---|---:|---:|---:|
| single/explicit-time | 1 | 100% | 0.0 s |

## Failures

None.
## Slowest 10

| s | path | command |
|---:|---|---|
| 0.0 | rule | set a meeting tomorrow at 2 pm with Ravid at Kems |

## Raw

Full per-case JSON: `DOCUMENTATION/ASSISTANT_AUDIT.md.json`