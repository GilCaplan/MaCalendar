# Generate

Per item: FastRule's result when it was confident for that item, otherwise one
schema-constrained model call through the existing action registry. Execution
reuses the action classes untouched (`create_event`, `add_todo`,
`query_schedule`, `update_event`, `delete_event`, …).

Two properties that hold by construction:

- **Format errors are impossible** — every model call is schema-constrained, so
  only semantic errors reach LLMJudge.
- **Every stage is grounded** — the raw transcript travels alongside the
  structured input, so no stage can drift from what was actually said.

See `../fastrule/ARCHITECTURE.md` for what a FastRule deferral obliges this
stage to do; the verdict is a contract, not a suggestion.

## Status

Not yet dug into. Moved here for structure.
