# FastRule v1 — retired 2026-09-07

The first FastRule: the deterministic rule parser as a thresholded selective
classifier. Superseded by the Q11 restructure (now `assistant/engine/
fastrule.py`), which keeps every behaviour and reorganises it into named
components — Atomicity (layer 0: is this ONE atomic item?), Gatekeeper
(intent-level vetoes), Scorer (the commit predicate + the signal registry).

**Why it was replaced** — not because it was wrong, but because fourteen
improvement batches (F1–F14) had accreted onto a shape designed before we
knew what FastRule had to be: semantic rewrites hiding in the normalization
list, four accreted routing tiers, slot captures patched into branches at
various depths. The behaviour was good; the structure could no longer be
reasoned about.

**Fidelity of the switch** — a diff harness ran both versions over all
7,200 dataset rows: **7,200 / 7,200 verdicts identical** before v1 was stood
down. (The first pass was 75% and revealed a real regression — v2 had
changed which reason wins when a parse is both below-threshold AND missing
slots. Fixed, then re-proved.)

**What lives here** — `fastrule.py` exactly as it ran. The full-fidelity
truth is the git tag `fastrule-v1`, which marks the last commit where the
engine actually used it (`git show fastrule-v1`). Its gate patterns and the
`FastRuleResult` type were carried into v2 unchanged.
