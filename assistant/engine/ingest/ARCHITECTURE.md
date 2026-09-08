# Ingest

**The step between "what Whisper wrote" and "words worth parsing."** Everything
Segmentation sees has been through here.

Two jobs, and they were in two different places before this folder existed:

```
   audio transcript(s)
          |
          v
   +-------------------+
   |      INGEST       |
   |  coalesce.py      |  several queued recordings -> ONE input
   |  repair.py        |  vocabulary fixes, false starts, uncertain words
   +-------------------+
          |
          v      state.text, state.corrections, state.needs_edit
      SEGMENTATION
```

## coalesce.py — concatenation

Commands arriving while a run is in progress are queued (FIFO). Before the next
run starts, queued inputs are coalesced up to a token budget
(`engine.coalesce_max_tokens`) into one input as `("…")and("…")`. The wrapper
keeps each command's logic independent for Segmentation, and is deterministic
to split back. Overflow beyond the budget stays queued and runs sequentially.
The phone's bracket-batched requests feed the same mechanism.

## repair.py — the words

Reads `state.raw_text`, `state.source`, `state.supports_edit`; writes
`state.text`, `state.corrections`, `state.needs_edit`, `state.ignored`, and
`VOCAB` trace steps.

- trailing stop keywords go
- false starts are declared trivial — **and never remembered**, because
  recording one teaches the model that junk is normal
- the personal vocabulary repairs what it is confident about
- what it is **not** confident about is surfaced: as `needs_edit` when the
  client can show an editor and the setting asks for one, as advisory
  `uncertain_words` otherwise

The vocabulary is hand-curated and lives outside the repo in
`~/.assistant_tools/`. Writing junk into it quietly degrades the assistant, so
any script exercising this stage must set `MACALENDAR_VOCAB` to a scratch path.

## Status

Not yet dug into. Moved here for structure; no dataset, no board of its own.
