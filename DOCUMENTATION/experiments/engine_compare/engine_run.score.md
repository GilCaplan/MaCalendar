# Dataset run score — `/var/folders/0f/nk3dnvrd54jbjz_qn40_ynwh0000gn/T/engine_compare_b5i3h9m8/engine_run.db`

**SEALED TEST RUN — aggregates only. Row-level detail is
suppressed by design: test results are never mined, and a
test score never spawns a hypothesis (leakage guard).**

- product-adjusted count-correct **82%** (12 overridden rows; raw below is the comparable number)
- **301 prompts** scored · count-correct **83%** · garbage-title rate **0%**
- total_ms p50 12034 · p95 70390
- parse paths: {'deep': 166, 'fast': 135}

## By complexity

| Tier | n | count-correct | garbage titles | total_ms p50 |
|---|---:|---:|---:|---:|
| simple | 97 | 90% | 0% | 4174 |
| medium | 101 | 92% | 0% | 3313 |
| complex | 103 | 67% | 1% | 30247 |

## By compound kind

| Kind | n | count-correct | garbage titles | dates collapsed |
|---|---:|---:|---:|---:|
| event+event | 35 | 63% | 0% | 6% |
| task+task | 36 | 78% | 3% | 0% |
| event+task | 32 | 59% | 0% | 0% |

## event+task: which half goes missing when it fails

- both present: 19 · event missing: 9 · task missing: 4 · both missing: 0

## Correctness by parse path

| Path | count-correct |
|---|---:|
| deep | 77% |
| fast | 90% |

## Count-mismatch failures (52)


## Comparison

- 300 shared prompts (2699 only in A, 0 only in B)
- count-correct rate: 70% → 83%
- **13 got worse**, **50 got better**, 198 still pass, 39 still fail