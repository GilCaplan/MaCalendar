# Results log

Every meaningful run, newest first. **Always: metric + slice + the commit that
produced it.** Baselines are replayed, not frozen — cite the score report and
md5, not "the dataset".

## Baseline — old brain on the full 3000 (verified 2026-09-04 20:56)

- **count-correct 70%** overall — `baseline/dummy_3000.db`
  (md5 `2511537fb93c32d28b87fe1998f77275`), report `dummy_3000.score.md`.
- Caveats (per the dataset owner): the db is not bit-reproducible (~75%
  determinism on regen); one row (tier_rank 2022, "Open calendar. Set event.")
  was replayed post-build and parses differently — negligible for aggregates.
- Frozen inputs: `inputs/history_3000.json`, `inputs/hwu64_sample.json`.

## engine-v2 vs baseline — count-correctness (metric #1)

| run | code @ | slice | old | engine | note |
|---|---|---|---|---|---|
| full-3000 | (round 5) | overall | 70.0% | **74.0%** | 252 better / 135 worse |
| full-3000 | (round 5) | held-out 601–3000 (n=2400, sealed) | 69.5% | **73.5%** | +4.0, generalises |
| full-3000 | (round 5) | complex | 29% | **39%** | the frontier |
| full-3000 | (round 5) | event+event | 20% | **36%** | decompose gain |
| full-3000 | (round 5) | event+task | 17% | **35%** | decompose gain |
| dev-full 600 | (cycles 2–3) | overall | 71% | 74.2% | invention guards — flat on this metric (they fix precision, not count) |

Other metrics on the full-3000 engine run: garbage titles ≤1%, cross-event
date collapse ≤2%, missing-half = the *event* dropped in 72% of event+task
failures, parse-path fast 76% / deep 71%.

## Reading note

The invention-guard cycles (remove-echo, question-creates-nothing, quote-shed)
did not move count-correctness — they fix *invention* (precision), which this
metric barely sees. Right fix, wrong ruler: a precision-class change needs a
precision metric. This is why every entry names its metric.
