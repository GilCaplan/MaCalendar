# LLMJudge

**`PLAN.md` is what is coming to this stage (2026-09-09)**: `Gatekeeper` moves here
from FastRule and becomes prompt CONTEXT rather than a veto, and the per-item LLM
fallback moves here too — because FastRule's job is only `Item -> object`, and *"if
there's an issue it tells the LLMVerify"* (Gil). This file is how it works today.

**The last check before anything is committed.** Formerly `crosscheck`.

Designed so the model does the job it is good at (extraction) and deterministic
code does the one it is bad at (judgement and blame):

1. **Extract, don't judge.** The model is asked to list the items the RAW TEXT
   mentions — not "is this right?". Small models extract far more reliably than
   they self-evaluate; asking an 8B to self-assess invites the accept bias that
   ADaPT measured at 30+ points.
2. **Compare deterministically.** Code diffs that list against the produced
   objects → `missing`, `extra`, `wrong_fields`.
3. **Blame by mismatch type, not by opinion.** A deterministic router maps the
   finding to a stage. The model never picks the stage.

On failure it loops back with the mistake appended to that stage's prompt
context, bounded at 3 re-entries per command. On exhaustion it commits the best
attempt, says so, and marks the memory record uncertain.

Patches are **tiered**: additive fixes (title rename, tag, missing end time)
apply silently with a trace step; destructive ones (move, undo+redo, remove)
apply but surface a visible notice with one-tap revert.

## Planned change — not yet implemented

Gil, 2026-09-08: LLMJudge should **verify, and when it finds a problem hand
back a repaired string version of the original prompt and re-enter at
Segmentation** — rather than routing blame across several stages as it does
today. Awaiting the details before the behaviour changes.

Note the naming gap this leaves: the folder and module are `llmjudge`, but the
`Stage("crosscheck")` identifier is unchanged, because `trace.py`'s
`BRAIN_VERSION` / `CHAINS` and `test_panel_agreement.py` pin the trace-visible
stage set. Renaming that is its own change with the full panel procedure.
