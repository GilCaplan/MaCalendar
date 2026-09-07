# Hypothesis queue — ranked, so cycles roll out fast

The planned experiments, best first. Each entry: the hypothesis, the ONE stage
it touches, the evidence it came from, the expected effect (metric + slice),
and effort/risk. A cycle takes the top unblocked entry, moves it to *In
flight*, and on verification the result goes to `RESULTS.md` + `loop_log.csv`
and the queue is **re-ranked** — fresh failures usually add entries.
**Re-rank and prune every ~3 cycles**; an entry that survives three re-ranks
untouched is probably not worth its slot.

Ranking = expected count-correct gain on dev-fast × confidence ÷ (effort +
risk). Product-convention questions are Gil's, never assumed — an entry
needing one is marked **[Gil]** and is blocked until asked.

## Done / in flight

- ✅ **C1 — remind + clock-time ⇒ event over LLM labels** (segment).
  73.2 → 76.0 overall; e+t 35 → 41. Predicted ~40 — on the nose.
- ✅ **C2 — dated occasion reminder ⇒ event** (segment; Gil's convention call
  2026-09-04). Actual @ 8a3e127: overall 76.8 (+1.2, predicted +1.5–2), e+e 59
  (predicted 63–67), e+t 43. Direction right everywhere; shortfall decomposed
  (see RESULTS.md): Friday-replay observance clash + garble halves + fast-path
  mangle. Graduated.

## The queue

**NEXT UP (2026-09-07, after the stage-isolation phase):**
- **[engine] A clean sealed-300 run** — the last one was partial and its
  latency was inflated by a bug since fixed. This is the baseline the
  resumed cycles are judged against.
- **[fast] ACCURACY, not coverage** — correct-on-handled has been ~72%
  through 13 batches while handle-rate climbed 8 points. The failures are
  operation/kind misroutes made CONFIDENTLY by rules, so the models are
  never consulted: wire rules-and-models-both-vote, and treat a confident
  disagreement as a defer signal (the Q10 design, still unbuilt).
- **[engine] Remove the retired brain's verifier** (~200 lines in
  intent/parser.py, no callers — engine audit).
- **[fast] Half-executed compounds 31 → 0** — the only non-atomic number
  that matters per Q13.
- **[engine] Answer the audit's 7 questions** (DOCUMENTATION/ENGINE_AUDIT.md
  §4) — several are Gil calls.

**LANE PRIORITY (Gil, 2026-09-07): SIMPLE FIRST.** FastRule focuses on
single-request add/edit/remove/complete/query — the felt-latency surface —
before any further complex-tier tuning. Working target: simple-tier commit
66% → **80%+ at ≥90% correct-on-committed** (train), title slot up from 83.
Simple-first order: F7 (rename/update/priority targeting) → R2 reliability
diagram + simple-slice threshold sweep → title-span quality (research idea
8) → K1b/K2 kind scorer (kind errors are a simple-tier disease). DEFERRED
until the simple target holds: gate-recall work, EXT0 compound synthesis,
further coordination tuning (complex ~28% commit is healthy by design —
deep's job). Complex regression floor still applies: no simple-first batch
may worsen the complex board.

*(FS-entries 2026-09-07 — the FastRule data plan, Gil-approved; protocol
§three-data-sources has the doctrine.)*

- **[infra] FS1 — field-level scorer for the generated 6000**: fast_sandbox
  (or a sibling) reads `dataset/fastrule/fastrule_6000.jsonl`; scores counts,
  action, ATOMIC flag per gate, slots, AND label-correctness (category
  acc + macro-PRF on events, tag micro-PRF on tasks, canonical fixture via
  MACALENDAR_CATEGORIES — Gil, 2026-09-07); per-family lines; test half
  aggregates-only by default. Prereq for everything below.
- **[fast] FS2 — fresh FastRule baseline on B-train** (4,800): the lane's
  new reference board; also run A-pool sandbox beside it (dual-gate anchor).
- **[fast] F6 — gate supervision, batch 1**: fix F5's two over-blocks using
  B's atomic flags (per-gate precision/recall by family — the first direct
  gate supervision). Dual-gated: win on B-train, no regress on A.
- **[fast] K3 — OPERATION scorer (Gil's proposal, 2026-09-07): the K1
  recipe for add/edit/remove/complete/query.** Dataset B carries the action
  label by construction, so a small multiclass logistic over hand features
  (verb-inventory hits, "as done"/"from my X"/"to ‹when›" phrase shapes,
  question form…) trains for free. Use exactly as K1: the verb table and
  Gil's rulings stay authoritative; the scorer arbitrates the fallthrough —
  and a table-vs-scorer DISAGREEMENT is a cheap abstain signal aimed at our
  worst failure mode (confident wrong-action commits: rename→create at
  0.95, set-priority→create at 1.00 were exactly this). Offline experiment
  first (K1 pattern), wire only on a measured win.
- **[fast] K1b — retrain the kind scorer on A's 2,699** (~4× data), refresh
  weights; feeds K2's wiring cycle.
- **[measure] R2 on A — reliability diagram** of the confidence multipliers
  over the full train pool; calibration refit only if it shows miscalibration.
- **[data] EXT0 — the MixSNIPS recipe on OUR OWN rows** (report's sleeper
  insight): manufacture labeled compounds by gluing pairs of our already-
  conventioned single-intent train rows ("<set row> and <createoradd row>" →
  e+t, atomic=false, counts by construction). ZERO conventions-pass needed,
  zero external label noise — our rulings ride in with the source rows.
  Cheapest new compound data available; feeds the coordination gate + segment.
- **[data] EXT1 — external-corpus adoption, UNBLOCKED (report:
  `EXTERNAL_DATASETS.md`).** Ranked: (1) **TOPv2** — 87k alarm/reminder/event
  rows with REAL nested multi-intent, CC-BY-SA, direct download; (2)
  **MASSIVE en-US** — 4.3k calendar/lists rows, near-1:1 action mapping,
  CC-BY; (3) NLU-Evaluation-Data (+2.9k calendar after dedup); (4) CLINC150
  (kind-decision + out-of-scope rows). Each per the C-pipeline: converter →
  STT normalization → conventions pass to Gil → train-only. Dead ends
  confirmed: MultiWOZ/Taskmaster (no calendar), ThingTalk (toolchain),
  ATIS-family (license murk).

*(R-entries added 2026-09-06 from the research sweep —
`DOCUMENTATION/experiments/FASTRULE_RESEARCH.md`, all URL-cited; evidence
grade in brackets: paper > production-system > pattern.)*

- **[fast+deep] R1 — coordination-type module: NP- vs clause-coordination by
  dependency parse** [paper: multi-intent boundary-classification literature;
  spaCy-documented mechanism]. ONE module, three call sites: (a) FastRule's
  strong-compound gate stops being a cue-word regex and asks the parse
  whether "and" joins noun phrases ("Tal and Sam" — don't split) or clauses
  ("book X and remind me Y" — split); (b) segment gets it as a free
  deterministic pre-split in front of the LLM; (c) the compound-hint filter
  reuses it. *Expected:* gate-overblock recoverable-abstain down + event+task
  missing-half down. *Effort:* M. Sandbox-first (the gate side = F5), segment
  call-site rides a deep cycle.
- **[measure] R2 — reliability-diagram audit of FastRule confidence** [paper:
  calibration literature; Chow's rule for abstention]. We already log
  confidence + correctness per command; bucket and plot before touching the
  hand-chosen multipliers. *Effort:* S — the diagnostic precedes any
  calibration fit (R2b: logistic calibration, only if the diagram shows
  miscalibration). *Expected:* evidence, not a board move.
- **[deep] R3 — span-offset segmentation: the LLM returns character offsets
  into the raw transcript, code slices the text** [extraction-vs-generation;
  kills regeneration loss at the root]. Targets missing-half on event+task
  (46%). *Effort:* S–M. Schema change is internal to segment (contract
  output unchanged).
- **[fast] R4 — fuzzy + phonetic target matching for quoted/misspelled
  targets** [production-standard: token-set ratio + Double Metaphone
  fallback; vocab.py already documents the phonetic blind spot]. Targets
  "remove 'father's day' from calender"-class fast misses. *Effort:* S–M.
- **[deep] R5 — same-call segment retry via the dormant `state.mistakes`
  hook** [code already exists; control-flow only]. A segment output failing
  a deterministic sanity check (clause-count anchor, R1) retries once with
  the mistake named, instead of waiting for the downstream judge. *Effort:* S.
- **[ASK GIL] R6 — small logistic-regression kind classifier (event-vs-task)
  over hand features** [paper-grade technique; replaces the growing regex
  family that Q1 just extended]. Deterministic at inference, but introduces
  a trained component + fit script into a rules-only layer — design-adjacent,
  so queued behind a DEVQA yes/no.


*(Re-ranked 2026-09-06 for the POST-INTEGRATION system: FastRule object +
F1/F2/F3 + 0.80/0.60 are IN the engine now — any entry below citing "0.85"
or "not yet integrated" predates that. Era 2: new baseline = the joint
confirmation run. The FastRule lane keeps iterating in parallel on full-3000
in its worktree; graduates integrate every 2–3 cycles. Order of play:
(1) joint confirmation lands → era-2 baseline; (2) Gil reviews the
DeepSystem structure [his checkpoint — cycle 10 blocked on it]; (3) cycle 10
full rules-first-per-fragment [DESIGN CHANGE, Gil-authorized if step 1 paid,
which cycle 9 confirmed]; (4) path-B crosscheck precision; (5) F4+ sandbox
batches ride alongside throughout.)*

- **[deep] Crosscheck-correction precision → then auto-apply** (Gil chose
  path B, 2026-09-07). The LLM verify runs on every fast commit already;
  auto-applying its fix is off because the old auto-applier fixed 0 / broke
  1. Make correction precision (proposed-and-right / proposed) a measured
  loop target on the dataset — improve crosscheck.py's extract + blame until
  false-corrections are rare + the retracted-time regression is pinned, THEN
  flip self_check_apply:true. First step: instrument the metric (needs
  ground-truth 'what should the verify have changed' — likely a small
  hand-labeled slice, since the dataset has no correction labels).

- **[deep] ✅ C8 — spoken lead-times, inline** (decompose+generate, run 14).
  Board flat as predicted; fieldq 85.3 + when 86.1 best-ever (clause strip
  cleans titles); behavioral goal delivered (reminder_minutes flows out
  through notify_at). Two exempt bugs found+fixed (courtesy-prefix mangle,
  fallback slot-apply).
- **[DESIGN CHANGE · Gil-authorized] 🔄 C9 — sub-item rules-first trust, step 1** (generate
  `_parse_item`, IN FLIGHT). Fragments accept rule parses at 0.60 vs the
  whole-command 0.85; crosscheck stays the net. Prediction: deep p50
  6.0-7.0s, deep count -1..+2. Step 2 (full rules-first-per-fragment, LLM as
  end-judge) is cycle 10 — a further DESIGN CHANGE, Gil-authorized IF step 1 pays.

*(Entries are tagged **[fast]** / **[deep]** / **[routing]** since 2026-09-07:
a cycle may pair one [fast] + one [deep]; [routing] rides alone — see the
protocol's Paired-track section.)*

- **[fast] Quoted/misspelled targets on the rule path** — evidence (runs
  11–12 tails): "remove 'father's day' from calender" and "mark 13 october
  of this year as my birthday" fail ON the fast path — quoted titles and
  misspellings inside otherwise-confident parses. Rule-parser internal.
  *Expected:* +0.5–1 pt on the fast slice. *Effort:* low-medium.

- **[fast] ✅ F1 — mixed-mode compound abstain + "list" generic target**
  (sandbox-graduated 2026-09-07 @ 68e349d: adjusted-on-committed 82.5 →
  89.9 dev-fast / 90.1 dev-full gate; joint confirmation rides the next
  full cycle run). **F2 residuals:** "get rid of this list" still commits
  (diagnose the veto miss), "sync my calendar with mark"
  (invention-shaped).


- **BUG (open; found 2026-09-06 by the query-no-mutation check): queries can
  emit mutations.** "Is my appointment to the dentist still on for tomorrow
  morning?" → deep produced `update_event(match_title="dentist")` — a
  question that MOVES the appointment on a real calendar. Present in every
  archived run (14 hits on the full-3000 sweep). Deterministic guard: an
  interrogative with no imperative verb must not generate
  delete_*/update_*/complete_* actions. Bugs are exempt from
  one-change-per-cycle; fix when the engine tree is next idle.


0. ✅ **Resolved (Gil, 2026-09-05) — frozen replay clock + observance flag.**
   Better than pinning to an arbitrary Tuesday: each row now replays AT ITS
   RECORDED TIMESTAMP (the dataset is a history), and Shabbat gating stands
   down in tests via the user flag `observance.enabled` /
   MACALENDAR_OBSERVANCE=0. **Measurement epoch reset**: results from
   2026-09-05 onward are not comparable to earlier rows in loop_log.csv — the
   re-baseline run marks the boundary.

1. ✅ **C3 — fast-path compound gate** (generate `fast_propose`, @ ce0c9b3).
   Actual: task+task 35 → 55 (+20), e+e 59 → 63, overall +0.8; fast-path
   correctness rose to 79% with the mangles gone. Graduated. Learning for the
   queue: dips elsewhere diffed as replay nondeterminism — overall deltas
   under ~1.5 pt on dev-fast are noise; judge cycles by their targeted slice.

2. ⚖️ **C5 — grounded default-title events** (generate `event_fallback`,
   @ b3c6656, run 10). Actual: +0.8 raw / +0.8 adj — under the noise floor;
   evidence rows were partly stale (already passing under the new epoch).
   KEPT (honest, deterministic, pinned) but not claimed. Byproducts for the
   queue: (a) loose groundings ("in the future", "the following event")
   create default events → direct evidence for #5's invention guard;
   (b) "set reminder at 3 pm" fails on the FAST path — a rule-parser gap,
   new entry below. Process lesson: re-verify evidence rows against the
   current epoch before taking an entry.

2b. ✅ **C6 — generic-target veto** (fast gate, @ 13edcce, run 11). A
   confident fast MUTATION whose match_title is a bare ask-noun routes deep.
   Targeted row flipped as designed, zero veto regressions, fast held 79%;
   headline −0.8 = garble-row flicker (noise). Graduated.

3. ✅ **C4 — cue iteration** (segment, @ f1c8d9d). notify + festival +
   "calendar invite". Actual: e+t 41 → 46 (top of band; the calendar-invite
   row creates a real brunch event), e+e 63 → 67, complex 51 → 54; headline
   flat (one t+t noise give-back). Festival residual accepted as a semantic
   boundary (standing-alert reads as a query). Graduated.

4. **List-op misreads** — stage: generate (or rule-parser mapping).
   *Evidence:* "update work out list with new items" → `update_todo` (found
   nothing); "Give an entry to this list" → `query_todos`. Dataset wants
   creates.
   *Expected:* +0.5–1 pt on task+task. *Effort:* medium. *Risk:* fuzzy —
   "update X with new items" as create is defensible; "give an entry" has no
   content to create (clarify may be the honest answer). Partial [Gil].

5. ✅ **C7 — invention guard** (generate, @ 160e9a4, run 12). GRADUATED:
   precision 85.8 (in band), raw 80.0 best-ever, +4/−0 flips — all four the
   garble-fabrication rows, resolving correctly once inventions dropped.
   Novel effect logged: the guard unlocks wins rather than merely trading
   count for honesty.

6. ✅ **Resolved (Gil, 2026-09-05): NO** — lists stay Today/General + tags,
   no separate lists by voice. The "create a new list" dataset rows are
   accepted convention losses, permanently. (Informs #4: "update the workout
   list with new items" should read as create-todos-with-tag, not a new list.)

7. **[DEVQA Q1] dated "I need to <meet/talk>…" ⇒ event** — convention edge,
   parked in DEVQA.md for Gil's inline answer. One row on this slice.

## Standing process items (not hypotheses)

- **Research-backed experiments (Gil, 2026-09-06):** ideas from the parsing/
  segmentation research sweep (`DOCUMENTATION/experiments/FASTRULE_RESEARCH.md`)
  convert into queue entries and RUN IN UPCOMING CYCLES, prioritized by
  evidence strength — **research-paper-backed first**, then
  proven-in-production systems, then blog-grade. Every one still enters as a
  registered prediction on its named metric+slice; implementation-level ideas
  are the loop's initiative, anything touching the frozen design goes to Gil
  first, as always. An idea we try cites its source in RESULTS.md so the
  outcome feeds back to the evidence.

- **Dev-full confirm** (`--limit 0 --max-rank 600`): after every couple of
  graduated wins, to confirm off the tuning slice.
- **Merge the loop branch into `main` every few graduated cycles** (Gil,
  2026-09-05). First merge done @ a425ca2.
- **Questions go to DEVQA.md**, never blocking prompts (Gil, 2026-09-05).
- **Diminishing returns → upsize** (Gil): when dev-fast cycles stop moving
  their targeted slices (two cycles < ~2 rows), the working slice becomes
  dev-full, with held-out for milestones.
- **Held-out check** (sealed): only at a milestone, never mined.
- **Re-rank this file** after every verification rerun; prune on every third.
