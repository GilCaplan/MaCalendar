"""Step 6 — cross-check what was produced against what was said.

Contract (see DOCUMENTATION/ENGINE.md):
  reads   state.raw_text, state.text, state.items, state.executed
  writes  state.findings (CheckFinding), state.retries, state.mistakes,
          trace steps (VERIFY); in background mode, patches via the
          orchestrator's tiered-patch hooks

Design (fixed now, implemented at this stage's build gate — the sequencing
plan's phase 3):

  1. EXTRACT, don't judge: the LLM lists the items the RAW text mentions
     (schema-constrained). Small models extract far more reliably than they
     self-evaluate.
  2. COMPARE deterministically: code diffs that list against the produced
     objects → missing / extra / wrong_fields findings.
  3. BLAME by mismatch type, never by LLM opinion: missing/extra item →
     segment/decompose; wrong field values → generate; format violation →
     validate; generate when ambiguous. The orchestrator owns the loop-back
     (≤3 re-entries per command, the mistake carried into the retried
     stage's prompt).

It also owns what the old brain did in four separate bolt-ons: the background
verify, both placeholder-title fixers, and the not-found second opinion.

NOT YET ACTIVE: this build is the contract placeholder. It records nothing
and loops nothing — `scripts/engine_stage_check.py --stage crosscheck` is the
gate its real implementation must pass.
"""

from __future__ import annotations

from assistant.engine.state import EngineState

# The deterministic blame router: mismatch type → the stage re-run. The model
# never picks the stage.
BLAME = {
    "missing": "segment",
    "extra": "segment",
    "wrong_fields": "generate",
    "format": "validate",
}
MAX_REENTRIES = 3   # total per command, all stages combined


def run(state: EngineState, cfg) -> EngineState:
    return state
