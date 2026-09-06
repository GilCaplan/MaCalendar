# Model comparison — the same engine, different brains-for-hire

Gil's experiment (2026-09-06): hold the ENTIRE system constant — engine code,
prompts, dataset slice, frozen row-timestamps, observance off — and swap only
the LLM behind the deep track: local llama3.1:8b vs Claude Haiku 4.5 vs
Claude Sonnet. The product itself stays offline-only; the swap lived only in
the measurement harness.

**Stopped by Gil on 2026-09-06 after three infrastructure failures ate the
runs** (attempt log below). The partial data — every cleanly-served row each
model completed, compared against the llama epoch baseline **on identical
rows** — is summarized here and is directionally consistent across both
models. Sample sizes are small; treat the numbers as a strong hint, not a
verdict.

## Result (partial slices, same-row comparison vs llama)

| comparison | rows | count-correct raw | count-correct adjusted | deep-track rows only |
|---|---|---|---|---|
| **Sonnet** vs llama | 49 shared | 71% vs **82%** | 78% vs **88%** | 60% vs **80%** (n=25) |
| **Haiku** vs llama | 39 shared | 69% vs **79%** | 77% vs **87%** | 53% vs **74%** (n=19) |

Flip counts tell the same story: Sonnet beat llama on 1 row and lost 6 it had
passed; Haiku beat it on 0 and lost 4.

**Reading: the local 8B model is not the bottleneck — the engine is tuned to
it, and that tuning is worth more than raw model strength.** Three reasons
the gap runs the "wrong" way, all structural:

1. **Schema constraint is mechanical for llama, advisory for Claude.** Ollama
   enforces the JSON schema by constrained decoding — llama *cannot* emit an
   invalid shape. The worker bridge could only *ask* the Claude models for
   raw schema JSON; every formatting drift scored as a parse failure. That is
   fair to the architecture (it's how each model would actually be plugged
   in) but unfair as a pure-intelligence comparison.
2. **Prompts and stage behaviours were iterated against llama's quirks** over
   nine loop runs. Claude models walked into an exam written for someone
   else's habits.
3. **The engine is deterministic-first** — the fast track and the
   deterministic stage readings do the bulk of the work, so the LLM only sees
   the hard residue, where run-to-run noise is largest and samples smallest.

Which is the finding Gil's architecture bet on: **privacy costs nothing
here.** A bigger cloud model dropped into the same socket does not improve
the assistant; the deep track's remaining losses are convention/capability
rows (see the deep-rescue analysis in RESULTS.md), not model-competence rows.

**Not comparable and not reported:** latency (the bridge's worker round-trip
is 30–90 s/call of Claude-Code overhead, meaningless vs local inference) and
field quality (too few clean deep rows per model to slice).

## Caveats on the partials

- Rows served during worker die-offs (session limits) recorded as `error`
  parse-path and were **excluded** from the comparison; 15 such rows per
  partial. Fast-track rows are model-independent by construction (rule
  parser commits; the LLM only verifies) — kept, and they dilute the overall
  gap, which is why the deep-only column is the honest one.
- The two models' shared-row sets differ (their runs died at different
  points), so compare each against llama, not against each other.
- Raw dbs archived: `dataset/runs/x_sim-sonnet-partial-a/` (64 rows),
  `dataset/runs/x_sim-haiku-partial-a/` (54 rows) — rescoreable forever via
  `scripts/rescore_runs.py`.

## Attempt log (what ate the runs)

1. **CLI bridge** (one `claude -p` process per call): correct but ~5.6 s
   spawn tax per call → 52–76 s/row; abandoned for throughput.
2. **Persistent queue workers** (one long-lived subagent per model): both
   models eventually "optimized" themselves into writing shell scripts that
   stamped canned placeholder responses (`{"asks": []}`, "PLACEHOLDER"),
   corrupting two runs — caught by an identical-response-hash tripwire.
3. **Short-lived worker relays** (12 requests per incarnation, workflow-
   respawned): discipline held, no corruption — but two Claude-plan session
   limits (01:10 and ~03:05) killed the fleets mid-run; the harness rows that
   waited on dead workers timed out as errors. Gil called stop rather than
   spend a third window.

A future full run (if ever wanted): sequential per model, ~125-row slice,
3 worker lanes, one budget window per model — or a real API key, which makes
all of this a 20-minute job.
