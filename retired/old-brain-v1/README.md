# Retired: old brain (pre engine-v2)

The single-file brain the engine replaced. Every command used to be parsed and
executed by `server.py:_run_transcript` (~800 lines of interleaved heuristics)
plus `pipeline.py`'s GUI-side orchestration. Retired 2026-09-04 when the 8-stage
`assistant/engine/` became the brain.

- `server.py`, `pipeline.py` — the two files that carried the old brain, exactly
  as they were at the last pre-engine commit (`a987aba`). Everything else (db,
  actions, rule/LLM parsers, GUI, iOS) was shared and was NOT retired — the
  engine reuses it.
- **Full-fidelity revert of the entire old tree:** `git checkout pre-engine-v2`
  (tag on `a987aba`). This folder is the quick reference; the tag is the truth.

Why kept: to compare a component's old behaviour against the engine, or to
revert if the cutover regresses something the dataset did not catch.
