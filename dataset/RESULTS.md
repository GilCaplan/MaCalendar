# Results log

---

# ═══ ERA 2 — post-integration (opens with the joint confirmation run) ═══

## Run 16 — the era-2 baseline (joint confirmation of the integration) · 2026-09-06 · effebeb · dev-fast-250

**Predicted:** more fast commits (0.80 bar, +2pp coverage per the sandbox
sweep) at flat-or-better correctness; F1/F3 gates re-route a few wrong-fast
rows to deep.

**Actual — prediction HALF right, and the half that missed is the
interesting one:** commit coverage went DOWN, not up (fast n 98→87): the
F1/F3 abstention gates removed more commits than the lower threshold added.
But what stayed committed got much safer — **fast correct-on-committed 79%
→ 90% (+11)** — and the headline is flat within the noise floor (raw
78.0→77.0 · adjusted 80.8→**80.0** · F1 82.0→81.1 · fieldq 85.3→84.5 ·
garbage 0%). Deep 78→71 is composition, not regression: it inherited ~11
hard rows fast used to get wrong (deep n 152→163). p50 8636 / p95 55073.

**Verdict: CONFIRMED — merged to main.**

## F12 (model iteration 1) — REGISTERED PREDICTION 2026-09-07

**Change:** features only, floors untouched. (a) K3b: class-targeted
operation features for the starved classes — query (61%) and remove (67%) —
e.g. bare-noun-phrase-with-?-forms, "off my/the" removal speak, "am i
free / is there anything" query openers; (b) kind model: close the gap to
K1's proven feature set (86.4% train vs K1's 99 — add occasion/list
signal parity). Re-fit (train-only, balanced), re-measure through FIXED
floors 2.5/1.5. **Predict:** operation train-acc 90.9 → 93+ with query/
remove ≥75% each; kind train-acc 86.4 → 92+; downstream, simple commit
72.5 → 74–77% at ≥91% correct; A-pool dual-gate within ±0.5 of 94.5.

## F13 (model iteration 2) — REGISTERED PREDICTION 2026-09-07

**Change, features only, floors fixed:** (a) kind model rebuilt on the
PROVEN K1 feature set — the segment stage's real regexes (occasion,
remindish, remind-to-verb, clockish, dated, task-phrase, encounter),
lazily imported, replacing my hand-approximations; (b) operation model
gains precision-side interaction features for query (query-opener AND
schedule-noun; create-verb/remind-speak as explicit anti-query signals) and
remove ("off my/the" tightened to schedule-ish objects). **Predict (TEST
eval):** kind macro-F1 82.6 → 86+; operation macro-F1 73.4 → 78+ (query P
57 → 70+, remove F1 62 → 70+); downstream test simple commit 72.0 → 73–75%
at ≥92% correct; A-pool dual-gate within ±0.5 of 94.3.

## F14 — ACTUAL + MODEL CAMPAIGN CLOSED (2026-09-07)

**F14 negative:** A-pool mixing cost B-test operation macro-F1 73.4 → 69.3
(query 62→50, remove 62→56) — A phrases those classes in its own dialect
and one linear boundary can't serve both; kind +0.2 (noise). Reverted;
machinery kept behind F14_MIX_A_POOL=False.

**Campaign verdict — CONVERGED at the F12 state.** Four levers tried under
registered predictions: class-balanced fit (KEPT — fixed the imbalance),
F12 features (kept — mixed but net-positive on recall), F13 feature swaps
(NEGATIVE ×2, reverted), F14 data mixing (NEGATIVE, reverted). Final model
state, B-test: **operation macro-F1 73.4 · kind macro-F1 82.6**; blended
router on test: **simple 72.0% commit at 92.4% correct**, A-pool dual-gate
94.3 adjusted. The models are at the ceiling of 16-feature linear capacity
on B-train alone. The two levers that could move them further are both
gated: EXTERNAL corpora variety (EXT1 — deferred as complex-tier work) and
model capacity (a design question for Gil). Re-eval lands on the enlarged
test half when the dataset agent delivers it.
# registered prediction (kept)

## F14 (model iteration 3 — the data lever) — REGISTERED PREDICTION 2026-09-07

**Change:** training-data variety, features untouched. The fit ingests the
A-pool's conventioned rows alongside B-train (sealed-300 texts excluded by
load_test_split; train-side only): kind labels via the K1 derivation
(calendar/set→event, lists/createoradd→task, e+e→event, t+t→task) and
operation labels for the classes A can teach (set/createoradd→new,
query→query, remove→remove — hundreds of REAL wordings for exactly the two
starved classes). **Predict (B-test eval):** query F1 62 → 72+, remove F1
62 → 70+, operation macro-F1 73.4 → 78+; kind macro-F1 82.6 → 85+;
downstream test simple commit 72.0 → 73–76% at ≥92%; A-pool dual-gate
IMPROVES or holds (the models now speak A's dialect).

## F13 — ACTUAL (2026-09-07): NEGATIVE on both fronts, banked

(a) Kind on segment's "proven" regexes REGRESSED on test (82.6 → 80.5;
union of both sets 81.4 — still worse): K1's features earned their 99% on
a different label task, and here they couple to wording families that
mislead on unseen ones. Reverted to the F12 set (82.6 restored).
(b) The operation precision-interaction features flipped ZERO test
predictions (too narrow) — removed as dead weight. **Lesson: the models'
test gap is not a feature-tinkering problem — it's a training-VARIETY
problem.** Next lever (F14): grow training data — the A-pool's 2,699
conventioned rows as additional kind/operation training text (train-side
only), attacking family-overfit with real-usage wording. Feature work
paused until the data lever is measured.

## TEST-EVAL SNAPSHOT (2026-09-07) — the reporting baseline going forward (Gil)

Reported numbers are B-TEST (full 1,200) from here on; train = tuning only.
Cumulative F7→F12 on TEST: **overall commit 44.8 → 47.2% · correct-on-
committed 82.9 → 83.4% · simple tier 72.0% commit at 92.4% correct** (train
simple 73.1/91.6 — the ~1pp train↔test gap says the batches GENERALIZE; no
train overfit in the blended system). Atomicity P 90.8 / R 49.4 · title
78.4 · labels cat 59.6.

Models on TEST: operation macro-F1 **73.4** (train 87.1 — a real
generalization gap; remove 62, query 62), kind macro-F1 **82.6** (train
86.2). The models overfit wording families harder than the rules do — the
margin floors are what keep the blend at 92.4% simple correctness anyway.
F13's brief: close the TEST macro-F1 gap (query/remove precision features,
train-mined evidence only).

## F12 — ACTUAL (2026-09-07): partial — P/R/F1 lens now standard (Gil's ask)

Models: operation train-acc 90.9 → 92.0 (predicted 93+, under), macro-F1
87.1; query recall fixed (61→87) but precision fell to 61 (over-firing
features); kind barely moved (86.4 → 86.8 vs predicted 92+ — parity
features didn't close it; the gap to K1's 99 is likely K1's segment-regex
features, F13 target). Downstream: **simple 72.5 → 73.1% at 91.6%** ·
A-pool adjusted 94.3 (+9 commits; in bound but −0.4 cumulative from the
94.7 baseline — the model tier's running tab, watched every batch).
Per-class P/R/F1 + macro-F1 now prints at every fit (metric discipline
extended to the model layer).

## F11 — ACTUAL (2026-09-07): Q10 router wired; dual-gate did its job

First cut: simple 74.7% commit but the A-pool dual-gate CAUGHT a violation
(26 model commits at ~77% → adjusted −1.0). Floors tightened 2.5/1.5:
**simple 71.5 → 72.5% at 91.6% correct · A-pool adjusted 94.5 (−0.2, in
bound) with +12 commits**. Prediction partially met (commit under the 75–80
range at the safe floors; correctness above the 89 floor). The ceiling now
belongs to F12+: improve the MODELS (features, K3b class fixes) so margins
rise on correct cases — commits then climb through unchanged floors.
ENGINE CYCLES PAUSED (Gil) — lane-only until further notice.
# registered prediction (kept)

## F11 (Q10 router wiring) — REGISTERED PREDICTION 2026-09-07

**Change:** the two-subsystem router lands in the lane. Rules tier
unchanged (every currently-confident route stays byte-identical); where
routing today finds NOTHING (the "skip"/no-action fallthrough), the two
models fire: K3-operation × K1-kind compose the action
(new×event=create_event … complete×task=complete_todo, query→query_*), the
parse proceeds through the normal slot machinery, and a model-routed parse
carries a confidence penalty (×0.85) so the 0.80 bar still guards. Weights
fit from TRAIN DATA ONLY (B-train; emitted to a versioned constants file by
a deterministic fit script). No disagreement-veto yet (F12 decides on train
evidence). **Predict (B-train simple):** commit 71.5 → 75–80% at ≥89%
correct (model-routed commits are less precise than rule-routed — the
penalty + bar keep the blend above the floor); dual-gate on A: flat ±0.5;
complex board flat (gates unchanged).

## K3 — ACTUAL (2026-09-07): direction confirmed, both predictions off in instructive ways

**Train operation-accuracy: router 51.7% · classifier 91.7%. Test (aggregate
only): router 60.2% · classifier 85.0%.** Predictions missed both ways: the
router baseline came in far BELOW 80–88 — because scored coverage-honestly,
its abstains count as misses, and on atomic single-op rows it abstains a
lot (that IS the Q10 case: a routing subsystem's job is to name the
operation). The classifier landed just under 92–96 with a real 6.7pp
train→test drop and weak classes under imbalance (new 100% of 2,411 rows;
query 61%, remove 67%). **Graduates into the Q10 router build as the
FALLTHROUGH tier only** — rules keep every confident answer they give
today; the model fires where rules abstain; per-class features + a
class-weighted fit are the K3b to-do before wiring. B-test never mined.
# registered prediction (kept)

## K3 (operation scorer, Q10 subsystem) — REGISTERED PREDICTION 2026-09-07

**Experiment (offline, K1's script pattern):** multiclass logistic
(one-vs-rest, pure python) over hand features (operation-verb inventory
hits, phrase shapes: from-my-X / as-done / to-‹when› / question openers /
list-words…) for OPERATION ∈ {new, edit, remove, complete, query}, trained
on B-train's atomic single-action rows (labels by construction; mixed/
propose excluded), judged against the CURRENT router's operation accuracy
on the same rows (its routed action mapped to an operation; an abstain
counts as a miss for coverage honesty). **Predict:** the current router
lands 80–88% (it's been patched hard by F6–F10); the model lands 92–96%;
the model's biggest wins are on edit/complete phrasings without inventory
verbs. Held-out = B-test aggregate only. Ships nothing — a win graduates it
into the Q10 two-subsystem router build.

## F9+F10 — ACTUAL (2026-09-07, fastlane 364b714 + f10)

**F9 (filler/courtesy strip, let's-do, measured misspellings):** simple
commit 65.7 → 69.6% AND correct 90.6 → 91.2 — both dials up (predicted
70–74 commit: met at the threshold). **F10 (mutation-phrase title
captures):** simple commit → **71.5% at 91.4%** (predicted 72–75: just
under). Full train correct-on-committed 81.9 → 83.1; dual-gate on the real
pool flat-to-up (92.5 raw / 94.7 adj). Simple-first scoreboard: commit
65.7 → 71.5 (+5.8pp today), correctness ≥90 held throughout. Remaining
simple abstain mass: missing-date family (misspellings/end-of-month
phrases), all-day shapes, missing-titles residue — F11+ targets.

## F10 (simple-first batch 4) — REGISTERED PREDICTION 2026-09-07

**Target: the 62-row missing:match_title bucket.** Noun-chunk extraction
fails on multi-word titles in mutation phrases ("delete WEDDING REHEARSAL
from my calendar", "reschedule HAIRCUT to this weekend", "mark WALK THE DOG
complete") while the phrase itself delimits the title exactly — the F6c
phrase-capture pattern, generalized to three shapes: delete/remove/cancel
X from my …, reschedule/move X to ‹when›, mark X (as )complete/finished.
**Predict (train simple):** commit 69.6 → 72–75% at ≥91% correct; dual-gate
flat; the deletes stay behind the generic-target veto (a generic X still
abstains — the capture feeds the veto, never bypasses it).

## F9 (simple-first batch 3) — REGISTERED PREDICTION 2026-09-07

**From the abstain-reason mining (simple train: 209 skip / 92 missing-date /
22 missing-titles):** three normalization families: (a) leading filler+
courtesy strip ("um/uh/so/well/ok," and "could you (tell me)?" before any
command) — anchored patterns (^route-overrides) never see past them;
(b) "let's do/have/get X" → "book X" (create-speak the verb map can't key);
(c) STT misspellings the expansion table lacks: tommorow, apointment,
remindar. **Predict (train simple):** commit 65.7 → 70–74% at ≥90%
correct-on-committed; dual-gate flat; complex board flat.

## F8 — ACTUAL (2026-09-07): NEGATIVE, and decisive

Sweep 0.85→0.55: simple commit moves only 62.4→66.0%, correctness flat.
**Prediction falsified** — FastRule is not under-confident near the bar;
confidence is bimodal (~0.95 or structural failure). The coverage lever is
NOT the threshold: it's slot-filling failures and unparseable phrasings.
Threshold stays 0.80 (no change ships). Coverage work redirects to abstain-
reason mining (F9+). Banked per protocol: a falsified prediction that
saves every future cycle from re-trying the obvious knob.

**Standing instruction (Gil): run the lane to F15 before the next engine
integration.**
# F8 registered prediction (kept)

## F8 (simple-first batch 2) — REGISTERED PREDICTION 2026-09-07: threshold sweep

**Experiment:** sweep the front-door bar over train with per-tier readout
(one parse pass, bars applied analytically). **Predict:** FastRule is
under-confident on simple commands (correct-on-committed 90.6% at the 0.80
bar says the committed pool is far from the edge): a bar in 0.60–0.75
raises simple commit 66 → 72–80% while holding ≥90% correct; complex
false-accepts stay bounded because the compound GATES (not the bar) do that
work. Dual-gate at any adopted bar: real-pool dev-600 must hold ≥92 raw.

## F7 (simple-first batch 1) — REGISTERED PREDICTION 2026-09-07, before implementation

**Targets (train mining, simple-tier false-accepts):** (a) "rename X to Y"
commits create_todo at 0.95 for BOTH event- and todo-renames — FastRule
cannot know which store holds X, so correct behavior is a gate: abstain to
deep, whose matcher searches both; (b) "set X as high/medium/low priority"
commits create_todo at 1.00 — the phrase is fully structured, deterministic
update_todo(match_title, priority).

**Predict (train, SIMPLE tier):** correct-on-committed 89.7 → 91–93 (two
false-accept families out: rename rows leave the committed pool, priority
rows flip to correct commits); commit 66.2 → 65–67 (renames abstain,
priorities stay); complex board flat (regression floor); dual-gate on the
real pool flat.

## Era-2 cycle 4 — ACTUAL (run 20): F6 CONFIRMED, new era-2 best

**Adjusted count-correct 81.0 → 82.0** (era-2 best; era started at 80.0) ·
raw 79.0 flat · F1 82.1 · routing 164 deep / 86 fast (predicted 82–86 ✓) ·
fast correct 91% (predicted 91–94 ✓) · e+e 67 → 70 · medium 90 → 91 · deep
73% holding while absorbing F6's deferrals · garbage 0% · p50 7.8s. The Q9
confirm gate rode along inert, exactly as the pool audit said it would.
**F6 now counts on the main board.** Era-2 running total: adjusted
80.0 → 82.0 in four cycles.
# registered prediction (kept)

## Era-2 cycle 4 — REGISTERED PREDICTION 2026-09-07: F6 joint confirmation

**Change under test:** the F6 integration (encounter route-override,
broadened date-marking, completion phrase-funnel) landing on the full
engine, alongside the already-merged Q9 confirm gate (inert on this pool by
audit). Routing effects on the 3000-pool: encounter-family rows FastRule
used to fast-commit as create_todo now route create_event and abstain on
missing start_time → deep completes them (Q1 rule + all-day path);
completion phrasings commit correctly instead of mis-acting.
**Predict (dev-fast 250 vs run 19):** fast n 86 → 82–86 (encounters move to
deep); fast correct-on-committed 91 → 91–94; deep n up a few, deep correct
flat ±2 (absorbing rows deep handles well); overall adjusted 81.0 flat to
+1.0; garbage 0%; no metric worse than noise.

## F6 — ACTUAL (2026-09-07, fastlane 6c2bca1): three families fixed, prediction narrowly under

**Train (4,800):** correct-on-committed **74.7 → 81.1%** (predicted 82–86 —
just short: the encounter family lands as correct-ABSTAINS rather than
commits, which raises precision but not the committed-correct numerator);
commit 42.0 → 40.7% (predicted 40–43 ✓); atomicity flat (predicted ✓);
title 82.8 → 83.0. **Test aggregate: 77.5 → 82.9% correct-on-committed** —
the fixes generalize to unseen wording families (+5.4pp, aggregates only,
never mined). **Dual-gate ✓:** old-pool dev-full byte-flat (92.4 raw /
94.7 adj). 59 unit tests green.

Fix layers, for the record: encounters = route override ABOVE the
need-to→todo row; date-marking = broadened F4b rewrite; completion speak =
rewrite-funnel into "mark X as done" + phrase-route + phrase-captured
match_title (noun-chunking fails on verb-led titles). FS1 (fastrule6k.py)
shipped alongside: all six metrics, per-family floors, test = aggregates
only by construction. Known residue for F7, from train mining: rename/
update targeting, "set X as high priority", interrogative-create policy
(dataset labels them creates; the F3 gate abstains them — a convention
tension for Gil), atomicity recall 45% (gates miss half the true compounds
— the R1 segment-side pre-split is the planned lever).

### The registered prediction (kept for the record)

**FS2 baseline (the new set is deliberately harder):** train 42.0% commit ·
74.7% correct-on-committed · atomicity gates P 87.2 / R 45.1 · title 82.8 ·
category 74.3. Test aggregates consistent (77.5% correct). Train mining →
three SYSTEMATIC false-accept families (whole families 16/16 wrong):
(a) encounters "i need to talk to Quinn friday" → create_todo;
(b) date-marking variants "mark next tuesday as / note christmas day as" →
complete_todo/update_event (F4b's regex only knew explicit month-days);
(c) completion speak "check off X → query_schedule(!), i'm done with X /
already did X → create_todo, complete X → update_event".

**Fix shape: rewrite-to-known-good-form normalizations** (the F2/F4b
pattern): encounters → "meeting with …" (routes event); date-marking →
"add ‹label› on ‹date›" with broadened verbs (mark|note) + date alternation
(relative/weekday/named-day) + optional "on my calendar" infix; completions
→ "mark ‹X› as done" (the one completion phrasing verified to route right).

**Predict (train 4,800):** correct-on-committed 74.7 → 82–86% (~200–250
wrong commits flip to correct or to abstain); commit 42% → 40–43%
(date-markings abstain to deep like F4b); atomicity metrics unchanged
(atomic-row fixes). Test half: aggregate reported after, never mined.

## K1 (Q8) — ACTUAL (2026-09-07): direction right, magnitude 6× the prediction

**Kind-accuracy on labeled create rows (1495: calendar/set=event,
lists/createoradd=task, e+e, t+t):** deterministic chain (`_kind_of` +
`_enforce_pinned_kinds`) **71.5% dev / 67.8% held-out**; the 16-feature
logistic scorer **99.0% dev / 98.5% held-out** (aggregate only). Predicted
+2–5pp; actual +27.5pp dev. No overfit signature (dev→held-out drop is
0.5pp). Weights are explainable and printed by the experiment (list-words
−4.90 dominates the task side; occasion +2.36 / remindish +2.11 / dated
+1.43 the event side). Remaining dev misses are genuinely ambiguous
("Make new playlist…").

**Honest caveats before wiring (K2):** (1) the engine's EFFECTIVE kind
accuracy is higher than this baseline — the deep track's LLM also labels
kinds, so the wired-in gain will be much smaller than +27pp; the win targets
the deterministic layer and LLM mis-kind overrides (the e+t missing-half
family). (2) The dataset's phrasings make "list" nearly a label giveaway —
legitimate for our distribution, thinner off it. **K2 wiring plan (next
deep cycle): the classifier arbitrates ONLY where the pinned convention
rules are silent** — Gil's rulings (remind+clock⇒event, Q1 encounters…)
stay authoritative; the scorer replaces the blind fallthrough, not the
conventions. Weights ship as a versioned constants file.

### The registered prediction (kept for the record)

**Change under test (offline first, no engine change):** a logistic
regression over ~15 hand features (segment's own regexes as features:
clockish, dated, remindish, remind-to-verb, occasion, encounter-verb,
task-verbs, list-words, calendar-words…) for the event-vs-task kind
decision, fit on dev labels (rank ≤600; calendar/set=event,
lists/createoradd=task, e+e=event, t+t=task), evaluated against the CURRENT
deterministic labeler (`_kind_of` + `_enforce_pinned_kinds`) on the same
rows. **Predict:** classifier beats the regex family's dev kind-accuracy by
+2–5pp (the regexes are precision-tuned patches, so their recall on unusual
phrasings should lag a weighted combination); held-out AGGREGATE confirms
the direction. If it loses, the negative result is banked and the regexes
stay. Only a dev win graduates it to a wired-in engine cycle (K2).

## Era-2 cycle 3 — ACTUAL (run 19, 2026-09-07): CONFIRMED, first real era-2 gain

**All four predicted directions correct, and the sizes beat the prediction:**
adjusted count-correct **80.0→81.0** · F1 **81.3→82.7** (P 85.9 / R 79.7) ·
**complex 52→56** · **event+task 46→51** · task+task 45→50 · fast n 87→86
(predicted 83–86 ✓) at **91%** correct (predicted 91–93 ✓) · deep 71→73
despite absorbing the harder deferred rows · garbage 0% · p50 8.1s.

**The mechanism worked as designed:** F5 defers plain-"and" compound swallows
to the deep track, where segment/decompose split them — that's the complex
and event+task movement, the two families that had been stuck since era 1.
F4+F5 are CONFIRMED on the main board; the sandbox numbers transferred.

### The registered prediction (kept for the record)

**Change under test:** the boundary integration (fast-lane merge). Routing
changes: F5's clause-coordination gate defers plain-"and" compounds the
regex missed; F4a commits polite imperatives; F4b removes the mark-a-date
false-accept. **Predict (dev-fast 250 vs run 18):** fast n 87 → 83–86 (F5
defers a few compound swallows; F4a adds ~1 back); fast correct-on-committed
90% → 91–93%; the deferred compounds land in deep where splitting can save
them — complex/e+t flat-to-up; overall raw flat ± noise; garbage stays 0%.

## F5 (sandbox) — ACTUAL (2026-09-07, fastlane 88c736b)

**Two of three predictions met.** Dev-full 600 vs F4: committed 230→225
(predicted −2–5 ✓), correct-on-committed **91.3→92.4 raw / 93.5→94.7
adjusted** (predicted +0.5–1.5 ✓), recoverable-abstain 7.9→**9.2** (predicted
flat ✗ — the new gate over-blocked 2 rows; the NP-guard is imperfect on
dataset text — F6 candidate). Dev-fast adjusted 94.2→95.3. Product framing:
3 wrong instant answers prevented per 600, at the cost of 2 correct answers
taking the slow path — the right trade at the front door, where deep is the
net. The research idea transferred as advertised (13/14 canonical probes;
the known limit — a wrong NP-parse of a true compound — is documented in
coordination.py). Graduated; integrates at the 2–3-cycle boundary with F4.

### The registered prediction (kept for the record)

**Change:** R1's coordination-type module (research-backed: multi-intent
boundary literature; spaCy conj/cc mechanism). New `coordination.py`:
classify each and/comma join as NP-coordination ("Tal and Sam" — one thing)
vs clause-coordination ("book X and remind me Y" — two asks) from the
dependency parse. FastRule's strong-compound gate extends to fire on
clause-coordination even without cue words (the regex only knows "and
then/also/plus…"-style joiners).

**Predict (dev-full 600):** committed-wrong compound rows −2–4 (correct-on-
committed +0.5–1.5pp raw); commit count −2–5 (those rows now abstain to
deep, which is the net); recoverable-abstain roughly flat (NP-coordination
awareness avoids new over-blocks); full-3000 held-out aggregate reported.
Risk named: parse quality on lowercase STT text — if spaCy mis-tags, the
gate could over-fire; the NP-check is the guard.

## Era-2 cycle 2 — ACTUAL (run 18, 2026-09-07)

**Mechanism confirmed, aggregate flat — prediction half met.** The direct
evidence is clean: the targeted rows are GONE from the misses (the party-in-
NY/conversation-with-Greg compound completes; items created 217→218, when-
coverage 71→73). But the predicted +1–2 aggregate rows didn't survive the
noise: e+e stayed 67% (a different row jittered out this run) and raw stayed
78.0. Adjusted 80.0 · F1 81.3 · routing identical 163/87 · p50 7.8s.

**Verdict: KEEP** (real bug, unit-tested, row-level proof) — but scored
honestly as board-neutral. Lesson re-learned: a 1–2 row hypothesis on
dev-fast is AT the noise floor; the next hypothesis should target a fatter
family (R1's coordination module, dev-full gate) or measure on the slice
where the family is dense.

### The registered prediction (kept for the record)

**Change:** all-day-speak coercion in CalendarIntent (the LLM answers a
dated-no-clock ask with the WORDS — start_time="all day" — and the HH:MM
rule threw the whole event away). "all day"-family → a 00:00–23:59 block;
vague non-times ("any time", "tbd") → missing, taking the normal defaults.
Field-aware (start→00:00, end→23:59). Found by cycle 1's Q1 row + F4b's
mark-date family hitting the same wall.

**Predict (dev-fast 250 vs run 17):** the dated-no-clock family completes
instead of apologizing — event+event +1–2 rows (67→70±), overall raw
+0.4–0.8; recall up a touch (dropped items return); everything else flat
within noise; routing unchanged (163/87 — intent-model change, no routing
input).

## Q7 object refactor — CONFIRMED behavior-identical (2026-09-07, merged)

Confirmation run on the refactored Engine/DeepSystem objects, dev-fast 250:
**routing fingerprint identical** (163 deep / 87 fast — the deterministic
path decided every row the same way), board within noise of run 17 (raw
77.0 · adjusted 80.0 · F1 81.2 · fieldq 85.9 · fast 90% · garbage 0%). Not
logged as a cycle row — it changed nothing by design; the era-2 baseline
stands. One real lesson banked in component.py's docstring: Stage must
late-bind through its module (eager function capture silently broke
monkeypatched stages — caught by test_engine_flow before it could ship).

## Era-2 cycle 1 — ACTUAL (run 17, 2026-09-06)

**Prediction met:** board flat within noise vs the era-2 baseline (raw
77.0→78.0 · adjusted 80.0 flat · F1 81.1→81.5 · fieldq 84.5→83.8 · routing
identical at 163 deep / 87 fast · fast correct 90% · garbage 0%). Tier
jitter (e+e +4, t+t −5) is single-row noise.

**The finding that matters:** the Q1 rule FIRED CORRECTLY — "on Monday, the
20th, I need to have a conversation with Greg" now parses its half as
create_event (was a task) — but a **dated-no-clock event fails validation
(no start_time) and is dropped** with an honest apology. The kind decision
is fixed; the family needs a default-time/all-day path in event
construction. This is the same gap F4b hit ("mark 〈date〉 as X" abstains for
the same reason). **Cycle 2 hypothesis: dated-no-clock events get a default
time (or all-day), in generate's event construction — expect the Q1/F4b
family (~2-3 dev rows) to complete instead of apologize; e+e +1-2 rows.**

### The registered prediction (kept for the record)

**Change under test:** Q1 convention (Gil's DEVQA ruling, committed 3235f48):
a dated "I need to <meet/talk/have a conversation>" is an event —
`_NEED_ENCOUNTER_RE` in segment's pinned kinds. **Predict (dev-fast 250 vs
run-16 baseline):** the encounter-family rows flip to the event side —
event+task +0–1 rows, everything else flat within the 1.5-pt noise floor
(adjusted 80.0 ± noise, fast share unchanged — the rule fires in segment,
deep track only). F4 is NOT aboard (sandbox-only, integrates on the 2–3
cycle cadence). Next deep hypothesis (dentist query-mutation) diagnosed
while this measures.

## F4 (sandbox, era 2) — REGISTERED PREDICTION 2026-09-06, before implementation

Two fixes, diagnosed from the run-16-era sandbox misses (dev-only mined):
**F4a** — the interrogative gate reads a leading polite imperative ("Can you
create a new list…") as a question; exempt "can/could/would/will you
<create-verb>". **F4b** — "mark 13 october of this year as my birthday"
fast-commits complete_todo at 0.95: "mark <date> as <occasion>" must be an
all-day create_event (and never complete_todo when the object is a date).

**Predict (dev-full 600):** committed +2–4 rows; correct-on-committed +0.3–0.8pp
(one false-accept removed, 1–2 over-blocks recovered); recoverable-abstain
down ~1pp. Held-out reported, never mined. Non-goals: the delete-veto
over-blocks stay (product safety beats the count metric); remind-and-then
mis-kinds deferred to F5 with their own diagnosis.
 The integration's promise was
precision-on-committed and it delivered exactly that; coverage is the open
debt, measured as recoverable-abstain (17.4% standalone), and is F4's
explicit target in the sandbox lane. These numbers are the era-2 baseline
all subsequent cycles compare to.


*2026-09-06 (Gil): big changes landed — FastRule object + F1/F2/F3 gates +
tuned 0.80/0.60 thresholds integrated into the engine (`effebeb`). History
above/below this line is kept and re-scorable, but era-2 boards are compared
to the era-2 baseline (the joint confirmation run) and to each other — never
cycle-vs-cycle against era 1. Era 1 = cycles 1–9.*

---


## Epoch baseline (2026-09-05, code @ 76cfd4f, banked @ d343a7c) — the anchor all cycles now compare to

Frozen row-timestamps + observance off + fast path alive (103/250 fast).
Count-correct **78.4%** (old brain 67.2) · **F1 82.1** (P 85.1 / R 79.3) ·
**field quality 84.6** (when-correct 85%, coverage 70 items) · complex 52 ·
e+e 63 / t+t 50 / e+t 46 · p50 7.2 s · garbage 1%. Curiosity for next
session: simple-tier field quality (75) is LOWER than complex (86). Row 8
(all-deep bug run) stays as the pure-deep A/B: deep-only buys ~+1 pt count
and cleaner e+t at ~1.8× the latency.

Every meaningful run, newest first.

## Threshold sweep (Gil's experiment, 2026-09-07) — two tuned operating points

Whole-command RULE_THRESHOLD 0.85→**0.80** (full-3000 sweep: commit 38→40%,
correct-on-committed flat 87%, false-accept flat 13%; degrades below 0.65).
Sub-item SUBITEM_RULE_THRESHOLD **0.60** confirmed optimal (simple-tier
sweep: commit 53→58%, flat 94%/6%; flatlines at 0.60 — near-binary
confidence). Two numbers for two populations: whole command conservative
(compounds, deep=net), fragment aggressive (simple, crosscheck=net). Both
join F1-F3 in the pending joint-confirmation run before landing on the
board.

## FastRule-native metrics + F4 diagnosis (2026-09-07)

FastRule is a SELECTIVE CLASSIFIER; the deep metrics scored only its
false-accepts. Added **recoverable-abstain** (of abstained rows, how many
the raw parse would nail — headroom + wasted latency): dev 19.8%, full-3000
17.4%, cause-split low-conf (threshold) vs gate-overblock (my own vetoes).

FastRule standalone full board (committed rows, full-3000): commit 38% ·
correct-on-committed 87.4% · simple 94 / medium 92 / complex 55 · garbage
0.4% · date-collapse 0.0% · **field quality 96.1% · when-correct 100%** —
a near-perfect specialist on what it commits (deterministic dates = perfect
when), honestly abstaining on compounds (e+e 8, e+t 23).

**F4 diagnosis (NOT a blind threshold drop):** the 6 dev gate-overblocks
("get rid of this list", "Please delete this event", "Do I need to be
reminded…") are query/remove/delete rows where committing scores correct
ONLY because query/remove pass by creating nothing — the vetoes send them
deep for anaphora resolution, which is defensible (latency, not
correctness). The real headroom is the ~20 dev low-conf recoverables, but
lowering the 0.85 bar trades against false-accepts (the AP finding: the
confidence signal is near-binary, so a blanket drop is unsafe). F4 must
find a SAFE sub-pattern (a specific confident-enough shape), not move the
threshold — teed up, next fast-lane batch.

## Sandbox batch F3 — interrogative-create veto (fast lane) — PREDICTION (registered before the change)

*Diagnosis (fast-lane, dev):* interrogatives commit CREATES — "COULD YOU
PLEASE TELL WHEN WE HAVE TO PAY FOR CAR INSURANCE?" → create_todo(["car
insurance"]); a question that creates is invention. Also "mark 13 october …
as my birthday" → complete_todo("this year") (a create-shaped 'mark X as Y'
misrouted). *Change [gate]:* a confident fast parse whose text is
interrogative (leading question word / "could you tell" / trailing "?") AND
whose intents include a create action routes deep — a real query commits
query_schedule (no create) and is unaffected. *Predicted (sandbox
dev-fast):* the 1–2 interrogative-create rows abstain; commit 35% → ~34%,
adjusted-on-committed 92.0% → **93–95%**; query slice (already 97) and real
query_schedule commits UNCHANGED; held-out aggregate ticks up.

## Cycle 9 — sub-item rules-first trust (Gil's architecture call) — PREDICTION (registered before the change)

*Stage:* generate `_parse_item` (internal; no contract change). Gil's
observation: after segment/decompose split a command, each fragment is a
SIMPLE shape — exactly where the sandbox proved the rule system ≥95% — yet
per-item rule parses are only accepted at the whole-command threshold
(0.85). Change: a FRAGMENT (item text ≠ command text) accepts its rule
parse at ≥0.60 (still no missing slots); stage-6 crosscheck (the LLM
extract-and-verify) remains the net — which is the "verify using an LLM"
half of the idea, already in the architecture. Rides along (C8 bugs,
exempt): courtesy-prefix cleanup after the reminder strip; fallback path
now applies slots. *Predicted:* deep-path p50 drops (fewer LLM calls):
7.5s → **6.0–7.0s**; deep-slice count-correct −1 to +2; overall
78.5–80.5 raw; fieldq holds ≥84.5. Judge: deep latency + deep count.

**ACTUAL (run 15): GOAL MET — GREEN LIGHT for cycle 10.** Deep-only p50
**15255 → 14118ms**, deep-only p95 **67213 → 57714ms** (~10s faster on the
hard compound rows — fewer per-fragment LLM calls, the mechanism); count
flat as predicted (78.0 raw / 80.8 adj); fieldq 85.3, when 86.6 (best-ever
band held). The direction pays: trusting FastRule more on fragments cuts
deep latency with no accuracy cost. Gil re-confirmed cycle 10 = the FULL
version (rules-first per fragment, LLM as end-judge only).
(Correction: the fast-lane merge conflicted, so F1+F2 are NOT aboard
this run — cycle 9 measures C9 alone; F1+F2 get their own joint run next.)

## Sandbox batch F2 — verb-map gap + pronoun targets (fast lane) — PREDICTION (registered before the change)

*Diagnosis (fast-lane tree):* "get rid of this list" parses as
create_todo(["get this list"]) — "get rid of" is missing from the removal
verb map, so the C6 veto (mutations only) never sees it; "Can you sync my
calendar with mark?" parses as complete_todo(match_title="you") — a
pronoun target. *Changes:* [internal] "get rid of" joins the removal verbs
(the generic-target veto then catches "this list"); [gate] pronouns
(you/it/me/this/that) join the generic-target set. *Predicted (sandbox
dev-fast):* both rows abstain; commit 36% → ~34–35%, adjusted-on-committed
89.9% → **91.5–94%**; simple-ask slices unchanged; full-3000 held-out
aggregate expected to tick up (same phrasings exist beyond dev).

## Fast-only, FULL 3000 (sandbox, pre-F1 code, 2026-09-07, ~3 min)

Gil's ruling: the deterministic fast lane may measure the full dataset.
Commit 1217/3000 (41%) · adjusted-on-committed **dev 84.5% / held-out
84.4%** — a zero generalization gap, the strongest evidence yet that rule
iteration on dev travels. By kind on committed (full): query 96 / remove
97 / createoradd 80 / set 80 / t+t 57 / e+t 19 / e+e 7 — the compound
weakness F1 (worktree) abstains from; the post-merge full read is the
before/after. Held-out reported as aggregates only, per discipline.

## Sandbox batch F1 — abstention cues (fast lane) — PREDICTION (registered before the change)

*Scope (gate-only, no parser internals — batch 2 takes those):* extend the
fast gate's abstention: (a) weak-joiner compound cues the C3 regex misses
("— and", "and also", ", and then" variants seen committing wrong in the
sandbox baseline); (b) C6's generic-target set gains "list" ("get rid of
this list" fast-commits a mutation at a generic noun). All changes make
the fast track SAY NOT-MINE more often; none change what it parses.
*Predicted (sandbox, dev-fast):* commit rate 39% → 33–36% (the ~8–12
committed-wrong compound/convention rows abstain), correct-on-committed
78.4% → **88–92%**; simple-ask slices (query/remove/createoradd) UNCHANGED.
Gate on sandbox dev-full before graduating; joint confirmation rides cycle
9's full run. Personalization note: static cues only — no personal-data
mining, so the shadow-mode rule isn't in play for this batch.

**SCOPE AMENDED before implementation (instrument first):** the assumed
missing joiner cues already exist in the gate — baseline misses are
TWO-intent wrong parses, and 4 of 21 were convention rows (sandbox now
scores adjusted: 82.5% baseline, 17 true errors). F1 is now two gate
rules: (a) **mixed-mode compound abstain** — a confident multi-intent fast
parse mixing a create half with a mutation/query half on compound wording
routes deep; (b) "list" joins C6's generic-target nouns. Revised
prediction: commit 39% → ~35%, ADJUSTED-on-committed 82.5% → **90–93%**,
simple-ask slices untouched.

**ACTUAL (sandbox, 2026-09-07): GRADUATED at sandbox level.** dev-fast:
commit 36% (band), adjusted-on-committed **89.9%** (edge of band), t+t on
committed 33 → 80. Dev-full gate: **90.1%** on 600 (commit 37%) —
consistent, no overfit signature. Residuals → F2: "get rid of this list"
still commits (veto miss to diagnose), "sync my calendar with mark"
(invention-shaped). Joint confirmation rides cycle 9's full run before
anything lands on the main board.

## Cycle 8 — voice lead-times, inline shape (notifications phase 3) — PREDICTION (written before the change)

*Stages:* decompose (clause strip → slot) + generate (`_apply_slots` →
`CalendarIntent.reminder_minutes`), TASKS row 80. The dataset's ground
truth has NO reminder expectations, so this is judged on stage tests plus
one row class: "Alert me 2 hours before my meeting on Tuesday…"-shaped
commands, where stripping the clause leaves a clean event ask.
*Predicted:* the full board FLAT within noise (count −0.4 to +0.4; the
alert-before rows may add +1 row); the until/through recurrence tests must
stay green (the strip exists precisely to protect `_EXCLUSIVE_END`);
garbage flat; p50 flat. The real deliverable is behavioral: a spoken lead
time lands on the event and flows out through `notify_at`.

## Dev-full anchor, epoch 1 (run 13, 2026-09-06 17:11, 600 rows)

The new epoch's first off-slice read, covering C5+C6+C7 together: **78.5
raw / 81.0 adjusted**. The three verdicts it delivers: (1) **low overfit** —
tuned half 79.6 vs untuned 77.7, a 1.9pt gap; (2) **the invention guard
generalizes** — precision 85.9 off-slice, matching dev-fast's 85.8; (3)
**cycle 7's field-quality dip was slice noise** — 84.2 on 600 rows, back
above the baseline's 84.6-adjacent band. Persisting anomalies: simple-tier
field quality (79.1) still below complex, and the dentist query-mutation
class appears 2 times at this scale. Held-out trigger status: this is
dev-full point ONE of the two flat points required — the next graduated
cycle's dev-full decides.

## Cycle 7 — invention guard (queue #5) — PREDICTION (written before the change)

*Stage:* generate — after the LLM parses an event-kind item, every content
word of the returned event TITLE must be grounded in the item's own words
(prefix-stem match, so "meeting" grounds on "meet"); an ungrounded title is
dropped, letting the item fall through to event_fallback or honest unknown.
Evidence: the garble row "new scenario, time or calendar to new list…"
produced a fabricated "New Event" in a conference room at 10:00–11:00 —
fields not in the words (cycle-5 byproduct list; hypothesis #5's original
row). *Predicted:* count-correct roughly FLAT (−0.4 to +0.4 — the guard
removes lucky garble passes and cannot add count wins; judged NOT by count
but by precision and the adjusted metric): precision 84.7 → **85.3–86.0**,
garbage-titles stays 0, adjusted flat-to-up (held garble rows pass
`noop_ok`-class overrides). Risk: over-blocking legitimate LLM titles that
paraphrase ("Lunch" from "eat with Dana at noon") — the stem match and
event_fallback net limit the damage; watched via down-flips on non-garble
rows, which must be ZERO.

## Cycle 6 — fast-path generic-target veto (queue 2b) — PREDICTION (written before the change)

*Stage:* generate `fast_propose` (a C3-style gate cue). Evidence (run 10):
"set reminder at 3 pm" fast-commits `update_todo(match_title="reminder")` —
"set" verb-mapped to update, the generic ask-noun became the target, the
time dropped. Rule: a confident fast MUTATION whose match_title is a bare
generic noun (reminder/alert/event/appointment/task/todo) has no real
target — route deep, where event_fallback and the not-found ethos handle
it. *Predicted:* the targeted row flips (fast→deep→Reminder@15:00); overall
+0.4–0.8 raw — BELOW the noise floor, so per cycle 5's lesson the verdict
is judged on the targeted rows directly, not the headline. No fast-path
regressions (fast-slice count-correct holds ≥79%); ≤2 rows migrate fast→deep
so p50 roughly flat. Risk: vetoing legitimate generic-anaphora edits
("delete the event" meaning the last one) — deep handles anaphora too, so
the cost is latency, not correctness.

**ACTUAL (run 11, 2026-09-06 10:05):** the causal chain worked end-to-end —
"set reminder at 3 pm" routed deep and event_fallback booked Reminder@15:00
(**+1, the designed flip; zero veto-caused regressions; fast slice held at
79% with 5 rows migrated fast→deep**). Headline raw 78.4 (−0.8) / adj 81.2:
the give-back is 3 deep-path garble rows that were ALREADY deep in run 10
("new scenario…", quoted-placeholder schedule, Hindi garble) — LLM replay
flicker, the documented noise. **GRADUATED on the targeted slice.**


**Deep-rescue analysis (2026-09-06, corrected same night):** first
published as 0/21 — WRONG, computed against a misidentified scratch db (run
2's, not row 8's; caught during the archive salvage via parse_path
fingerprints: the real all-deep db is 250/250 deep). True numbers, row 9
mixed × row 8 all-deep: **deep rescues 7/21 fast failures** (weak-joiner
compounds C3's gate misses — "Give an entry to this list", remind+remind —
plus "mark 13 october as my birthday") **and breaks 6/82 fast passes** — net
+1 row (+0.4pt, under noise). Routing more traffic deep is not free win;
the opportunity is extending C3's gate cues to the 7 rescuable shapes
without paying the 6 breaks. Repeatable: `python -m scripts.deep_rescue
<mixed.db> <alldeep.db>` — verify db identity via the archive manifest
first.

**Dataset conventions audit (2026-09-06):** 140/3000 rows (4.7%) encode
conventions our product deliberately rejects (bare list creation, standing
alerts, remind-to-as-event, placeholders). New overrides layer
(`dataset/inputs/convention_overrides.json`, rules mined from dev only,
applied mechanically) gives a product-adjusted count-correct next to raw:
**epoch baseline 78.4 raw → 81.2 adjusted**, and every overridden row on the
slice passes adjusted — the convention gap is fully accounted for. The new
query-no-mutation check caught a real bug (a query emitting `update_event`
on the dentist appointment). **Correction of the correction:** the "row 8 =
75.6" retraction earlier tonight was computed against the WRONG surviving
scratch db (actually run 2's — identified during the archive salvage by
mtime and parse_path fingerprint). The true row-8 db rescores at exactly its
logged 79.2; the original "all-deep ≈ +0.8pt raw over mixed" note stood all
along.
Full report: `dataset/DATASET_AUDIT.md`.

**Model-comparison cycle — closed on partial data (2026-09-06, Gil's
call):** swapping the deep track's LLM for Claude Sonnet/Haiku via a worker
bridge, same engine, same frozen slice. On identical cleanly-served rows the
tuned local llama WON, consistently across both models — deep-track rows:
llama 80% vs Sonnet 60% (n=25), llama 74% vs Haiku 53% (n=19). The engine's
llama tuning + Ollama's mechanical schema constraint outweigh raw model
strength; the remaining losses are convention rows, not model-competence
rows. Full table, caveats and the three-failure attempt log:
`dataset/MODEL_COMPARISON.md` (worktree). Partial dbs archived as
`dataset/runs/x_sim-{sonnet,haiku}-partial-a`. Cycle slot closes; the queue
resumes at hypothesis #2 (grounded default-title events). Do NOT respawn
the sim bridge — the experiment is closed by Gil's call.


## Cycle 5 — grounded default-title events (hypothesis #2) — PREDICTION (written before the change)

*Stage:* generate — the event twin of `task_fallback`, firing only after the
event-kind retry also comes back empty/unknown. Gate: the text literally
asks to set an event/reminder/appointment (the noun is the grounded default
title) AND the datetime recognizer finds a date or clock time in the words.
Never invents a time; no gate match ⇒ stays unknown (honest).
*Predicted:* overall count-correct 78.4 → **79.4–79.9** on dev-fast
(+1–1.5pt = 3–4 rows: "Set a event for the evening", "please set event on
Tuesday", "Set reminder for three o'clock" class — simple tier and the e+e/
e+t halves they sit in). Simple tier should move most; garbage-title rate
must NOT rise (the title is a literal word from the ask). Adjusted metric
expected to move in step (+1–1.5). Risk watched: invention-adjacent — any
new event on a garble row is a regression even if count says otherwise.

**ACTUAL (run 10, 2026-09-06 09:06):** raw **79.2** (+0.8, predicted
+1.0–1.5 — under band and UNDER the ~1.5pt noise floor), adjusted 82.0
(+0.8). Targeted-slice read (the honest judge): the fallback fired on
exactly 4 rows, but the hypothesis's evidence was partly STALE — "Set
reminder for three o'clock" and "please set event on Tuesday" already pass
under the new epoch (they were old-epoch failures), so the predicted 3–4
flip rows mostly weren't there to win. Where it fired: 2 sensible defaults
+ 2 loose groundings ("Remind me in the future of this", "Remind me of the
following event:" — the recognizer grounds vague futurity; both rows passed
anyway, but these are invention-adjacent and become evidence for the #5
guard). "Set a event for the evening" still fails honestly (the recognizer
can't ground "the evening" — by design, no invented time). **Verdict:
inconclusive on count — kept** (deterministic, honest, pinned by
test_engine_generate.py, documented in ENGINE.md), but not claimed as a
win. Novel finds: "set reminder at 3 pm" fails on the FAST path (rule
parser, not the deep track — new queue evidence), and complex +3 (52→55)
was the only slice that moved. Lesson for the queue: re-verify an entry's
evidence rows against the CURRENT epoch before spending a cycle on it.
 **Always: metric + slice + the commit that
produced it.** Baselines are replayed, not frozen — cite the score report and
md5, not "the dataset".

## Dev-full confirm of C3+C4 — the day's milestone (2026-09-04, @ f1c8d9d)

Count-correctness, dev-full 600 (6049 s): **78.0%** — +2.0 from C3+C4 off the
tuning slice, **+3.8 total for the day** vs the 74.2 pre-loop reference; old
brain 71% on the same rows. task+task generalises at +10 (47 → 57), complex
45 → 51, garbage titles 0%. All four cycles hold off-slice. Two rows took an
'error' parse path — to be glanced at next session. **Loop paused at this
milestone**: after midnight the replay clock is *Saturday* (a new variant of
the observance clash), so further measurement waits on the date-pinning
decision (queue #0).

## Cycle 4 — data-driven cue iteration (2026-09-04, base @ ce0c9b3)

**Hypothesis (queue #3):** three additions to segment's kind enforcement, each
justified by a live failing row, none speculative: (a) `notify` joins the
remind-cues — "notify me about any festival occurring next month" (0 events);
(b) `festival` joins the occasion-nouns (same row); (c) the unambiguous phrase
"calendar invite" ⇒ event on its own — "Will you send a calendar invite …
for brunch at 11 am on Tuesday" (0 events; no remind-word, so C1/C2 never
fire). **Expected:** event+task +2 rows (41 → ~46%); overall +~1 pt — at the
stated noise floor, so the verdict will be read on the targeted rows
themselves (do those two rows now pass?), not the headline. Everything else
flat. Watch: "notify" over-firing on non-calendar notifications.

**Actual (rerun @ f1c8d9d, 2373 s):** judged on the targets per the noise-floor
rule — **event+task 41 → 46%** (top of the predicted band ✓; the
calendar-invite row now creates *'Brunch with James and Alice', Tue 11 AM* —
exactly right), **event+event 63 → 67%** (+4 bonus: the cues catch e+e halves
too), complex 51 → **54**. Headline flat at 77.6 (task+task returned one
noise-class row, 55 → 50). The festival row's residual is a **semantic
boundary**, not a bug: the kind flip works, but generate reads "notify me
about any festival occurring next month" as a *schedule query* — a
standing-alert concept the product doesn't have — and the event-kind retry
rightly accepts queries as calendar-consistent. Accepted as a convention loss.
**Verdict: graduated.** Next measurement: dev-full confirm of C3+C4.

## Cycle 3 — the fast-path compound gate (2026-09-04, base @ 8a3e127)

**Hypothesis (queue #1):** the fast path confidently swallows compounds — every
observed mangle ("…at noon. **Also,** Please remind…", "…at 9am, **and then**
Remind me…" → a todo literally titled "then") is a **single-intent** parse of
text carrying a **strong joiner**. Gate `fast_propose`: when the text has a
strong compound joiner (". Also,", ", and then", " — and", "and also", a
sentence break + joiner) AND the confident parse read only ONE request, refuse
the instant commit and take the deep track (deep 81% vs fast 71% on dev-fast).
Weak joiners (a plain "and") never gate — "meeting with Tal and Ravid" stays
fast. **Expected:** overall +1–2 pt (→ ~78–79%); e+t +2–5, e+e +2–4, t+t +0–5
(tempered: deep still misreads some garbly halves); fast share drops ~5–8 rows
and those commands go instant → 10–30 s (accepted correctness trade). Watch:
any legit fast command slowed, and the fast/deep mix in the report.

**Actual (rerun @ ce0c9b3, 2365 s):** overall 76.8 → **77.6%** (+0.8, just
under the +1–2 band). The slices tell the real story: **task+task 35 → 55%
(+20 — far above the tempered +0–5)**: the gated ", and then" task compounds
went deep and split properly. event+event 59 → **63%** (top of band ✓).
complex 46 → **51**. Fast share 115 → 103 (−12, a little more than predicted);
fast-path correctness *rose* to 79% (the mangles left it). event+task 43 → 41
and simple 92 → 90 read as **regressions but diff as noise**: the flipped rows
("Remind me at the 15th of every month and pUT MILK…") involve no gate marker —
pure replay nondeterminism (the LLM is ~75% deterministic run-to-run).
**Noise floor made explicit:** on dev-fast a handful of rows flip between
identical-code runs, so overall deltas under ~1.5 pt are not signal; targeted
slice moves like +20 are. One real loss: "Open me a new list — and please add
milk…" was *accidentally passing* fast and now lands on the create-list
capability gap (queue #6 [Gil] gains a data point). **Verdict: graduated** —
targeted slices clearly up, the dips are noise-class, and the mangle class is
gone from the fast path. Next: queue #2, grounded default-title events.

## Dev-full confirm of C1+C2 (2026-09-04, @ 8a3e127)

Count-correctness, dev-full ranks 1–600 (5405 s): **76.0%** vs the pre-loop
dev-full reference 74.2% — **+1.8 pt on rows the loop never tuned against** —
and vs the old brain's 71% on the same slice. Slices: simple 90 / medium 89 /
complex 45; e+e 53, t+t 47, e+t 38; garbage titles 0%. Caveat: the pre-loop
reference ran on a different weekday, and the Friday/Shabbat replay clash
(cycle-2 finding) makes cross-day deltas approximate. **C1+C2 fully
graduated.** Next per the queue: the fast-path compound gate.

## Cycle 2 — the date-only occasion reminder (2026-09-04, base @ e956763)

**Reading (from cycle-1-fix failures):** 6 of 8 listed event+event failures and
several event+task ones hinge on one form — a reminder **about/of/for an
occasion-noun with a date but no clock time** ("set a reminder for my meeting
today", "remind me of my meeting tomorrow", "the get-together on Sunday").
Product convention decided by Gil (2026-09-04): **occasion-nouns → event** —
the about/of/for-noun form with any date reference becomes a calendar event;
"remind me to \<verb\> …" stays a task (clock time still flips it, per cycle 1).
Also flagged, not chased this cycle: the deep path *invented* a full event
("New Event", conference room, 10:00) from garbled text — an invention/precision
failure the count metric barely sees; and task+task's remaining failures are
mostly capability/convention gaps ("create a new list", contentless "give an
entry to this list") — low clean upside.

**Hypothesis (cycle 2):** extending segment's `_enforce_pinned_kinds` — flip an
LLM "task" label to "event" when the text is remind-ish, NOT the "remind me to
\<verb\>" form, and has an occasion-noun plus a date reference — will fix ~3 of
12 event+event failures and ~1–2 event+task ones. **Expected:** event+event
56% → ~63–67%, event+task 41% → ~44–46%, overall +1.5–2 pt (→ ~77.5–78%);
task+task flat; simple/medium flat-to-slightly-up (single date-only occasion
reminders also flip, and their provenance is calendar). Watch for: a
wanted-task row flipping to event (over-reach of the occasion list), and
invented default times on the new events.

**Actual (rerun @ 8a3e127, 2087 s):** direction confirmed on every slice,
magnitude under prediction — overall 75.6 → **76.8%** (+1.2 vs +1.5–2
predicted); event+event 56 → **59%** (predicted 63–67); event+task 41 →
**43%**; task+task 35 flat ✓; simple 91 → 92, medium flat ✓; complex 44 → 46;
deep path 79 → 81%. The flip itself works ("set a reminder for my meeting
today" → `create_event`, sensible 10:00 default). The shortfall decomposes
into three understood causes:
1. **Novel — the replay-date/observance clash:** today's replays run on a
   *Friday*, so every "tomorrow" event lands on Shabbat and the observance
   gate **correctly refuses** it ("I didn't book 'meeting': that lands on
   Shabbat") — the product is right, the dataset doesn't model Shabbat.
   Cycle 1–2 gains are *understated* on Friday runs, and runs replayed on
   different weekdays are not strictly comparable. Today's runs are all
   Friday-consistent, so within-day deltas hold.
2. Garble first-halves ("Mark reminder with these people" → `complete_todo`
   misread) keep their rows failing even when the fixed half now works — as
   predicted.
3. The fast path mangled a two-reminder compound into todos titled
   "meet james at work tomorrow at 9am" and literally **"then"** — queue #1's
   evidence grows.
**Verdict: graduated** (targeted slices clearly up, nothing down); dev-full
confirm of C1+C2 next. Queue re-ranked: replay-date pinning added as a
measurement-correctness item [Gil to confirm].

## Cycle 1 — dev-fast(250) baseline + hypothesis (2026-09-04, code @ 2588612)

**Measurement** (metric: count-correctness; slice: dev-fast ranks 1–250;
report `engine_compare/engine_run.score.md`, wall-clock 4882 s ≈ 81 min with
the app stack up):

- overall: engine **73.2%** vs old brain 67.2% (29 flipped better / 14 worse)
- by complexity: simple 89% · medium 91% · **complex 40%** (the frontier)
- by compound kind: event+event **52%** (n=27) · task+task **35%** (n=20) ·
  event+task **35%** (n=37)
- event+task missing half: **event missing 20** · task missing 4 · both present 13
- parse path: deep 76% · fast 70% · garbage titles 1%

**Interpretation** (from `actions_json` of the failing rows — the event half is
rarely *dropped*; it is created as the wrong kind, or held back):

- **(A) dominant: reminder-phrased event halves become todos, even with clock
  times.** "create a birthday wish reminder for tomorrow **at 10 AM**",
  "remind me to go to my doctors **at 4pm**", "my meeting **at 3pm**" — all
  `create_todo`. The pinned product rule (remind + clock time ⇒ event) is
  implemented in segment's deterministic `_kind_of`, but the LLM's kind label
  wins on the deep path and is never corrected — so generate's own
  event-kind-retry safety net (which exists and works) never fires, because the
  item arrives labeled "task".
- (B) smaller: vague event halves ("Set a event for the evening", "pencil me in
  for sarahs birthday thing") parse to unknown and are held back honestly.
- (C) a slice of "failures" are convention clashes: "remind me to \<verb\> +
  date-only" is a task-with-due-date by product design but an event in the
  dataset's ground truth. Consciously NOT chased — the product rule stands.
- Also seen: the fast path mangling a compound outright ("Remind me to read
  book next week — and…" → three garbage todos) — a separate pile for a later
  cycle.

**Hypothesis (cycle 1):** making the deep path obey the *existing* pinned rule
— override an LLM "task" label to "event" when the text has remind/reminder
phrasing AND a clock time (`segment.py` internals only; contracts frozen; it
makes the LLM path agree with `_kind_of`'s deterministic path, no new
convention) — will let generate's event-retry engage for those items.
**Expected:** event+event 52% → ~58–60%, event+task 35% → ~40%, overall
dev-fast +1–2 pt; simple/medium and task+task flat (the override touches only
remind+clock-time items). Modest by design: one narrow, attributable change.

**Actual (rerun @ e956763, 2265 s):** overall 73.2 → **76.0%** (+2.8 — above
the predicted +1–2); event+task 35 → **41%** (predicted ~40 — on the nose);
event+event 52 → **56%** (predicted ~58–60 — right direction, slightly under:
two of its failures are the `update_todo`-misread and no-remind-word forms the
narrow rule deliberately skips); task+task 35 → 35 flat ✓; simple 89 → 91 and
medium 91 → 92 — a small **unexpected** gain: the rule also catches
single-command timed reminders the LLM mislabels on the deep path, not only
compound halves. complex 40 → 44. event-missing halves 20 → 18. Also novel:
p50 latency 9.5 s → 5.7 s, p95 74 s → 31 s (plausibly less unknown/retry
churn now the event-kind retry succeeds; possibly partly warmer caches — not
claimed as a fix effect). **Verdict: confirmed → graduated; the dev-full
confirm will be batched with the next cycle's win. Next pile: task+task 35%
(n=20), untouched by this fix as predicted.**

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

## F15 (stage-isolation, FastRule) — REGISTERED PREDICTION 2026-09-07

**Mined from B-train atomic rows.** Handle-rate leak is dominated by
TIME/DATE VOCABULARY: 807 of ~1,430 atomic defers are missing date and/or
start_time — "quarter to nine", "late afternoon", "first thing", "all day",
named holidays, "every weekday at 3:45pm". Correctness leak is dominated by
"mark X **down** as Y" (69 rows: F6b's rewrite knows "mark ‹date› as Y" but
not the "down as" form) plus rename-speak ("call it X instead of Y" → create).
Secondary: "clear X off my calendar" (45 defers, unhandled mutation phrase),
serial-verb false compounds (88: "wash and fold the laundry"), lead-time
clauses eating titles (75).

**Fixes:** (a) spoken-time vocabulary — "quarter to/past N", "half past N",
vague dayparts (late morning / first thing / midday), "all day" as a
time-slot filler; (b) "mark|note|put ‹date› **down** as ‹label›" folded into
the F6b rewrite; (c) "clear/take ‹X› off my calendar|list" capture;
(d) serial-verb guard in the coordination check (shared object ⇒ one ask);
(e) "call it X instead of Y" → update route.

**Predict (B-test):** atomic handled 49.7 → 58–64%; correct-on-handled
71.8 → 76–80%; non-atomic defer rate holds ≥82% with the "knew" share up
(the serial-verb guard removes false compounds, not true ones); propose
defer unchanged.

## F16 (layer 0 — the WIRING) — REGISTERED PREDICTION 2026-09-07

**The instrument first.** `scripts/atomicity_board.py` scores layer 0's own
binary question — one atomic item or several — as three separate predictors
(rules alone / model alone / the wired layer) on two datasets: **B** (the
FastRule 7,200, `expect.atomic` by construction, family-split) and **A**
(the verification pool minus the sealed 300, `scenario == "compound"` as
ground truth, deterministic sha1 75/25 split). Error counts are reported
un-aggregated because the cost is asymmetric: an FN ("said atomic, was
compound") half-executes a two-ask command and reaches the user; an FP
("said compound, was atomic") costs one slow-path row.

**Baseline it exposes — the layer scores WORSE than the model it contains,
on both datasets:**

| dataset · slice | predictor | acc | compound P | R | F1 | FP cheap | FN expensive |
|---|---|---|---|---|---|---|---|
| B-test (2,400: 626 c / 1,774 a) | rules only | 84.3% | 87.8% | 46.2% | 60.5% | 40 | 337 |
| B-test | model only (floor 1.5) | 91.9% | 85.3% | 83.4% | 84.3% | 90 | **104** |
| B-test | LAYER as shipped | 88.0% | 82.1% | 68.8% | 74.9% | 94 | **195** |
| A-test (672: 227 c / 445 a) | rules only | 93.6% | 96.9% | 83.7% | 89.8% | 6 | 37 |
| A-test | model only (floor 1.5) | 98.2% | 95.4% | 99.6% | 97.4% | 11 | **1** |
| A-test | LAYER as shipped | 93.3% | 94.6% | 85.0% | 89.6% | 11 | **34** |

**Diagnosis (train-side mining only).** `judge()` consults the model only
behind `len(intents) <= 1`. In B-test **110 rows parse to ≥2 intents and
every one of them is compound**, and the layer calls all 110 atomic without
ever asking the model: 110 of its 195 misses are one guard clause. The
guard exists for a real reason (v1: "buy milk and buy bread" parses as two
intents and rightly commits) — but that is an EXECUTION judgement, not an
ATOMICITY judgement, and it was smuggled into the atomicity answer.

**Change:** the model LEADS and the rule gates become overrides for their
own catches — `judge()` becomes rules-OR-model, with the model's
`len(intents) <= 1` guard removed. No feature or weight change; wiring only.

**Predict (B-test):** layer recall 68.8 → 82–84% (it should land on the
model's own line), FN 195 → ~105, accuracy 88.0 → 91–92%, precision
82.1 → 84–86%. **(A-test):** layer recall 85.0 → 98–100%, FN 34 → ≤3,
accuracy 93.3 → 97–98%. **Downstream (`fastrule_shape`, B-test):**
non-atomic DEFER RATE 77.1 → 85–90% with the "knew it was compound" share
51.2 → 68–75%; routing violations 129 → 55–70. Atomic handle rate 53.5%
should fall by ≤1.5pp (no B-test atomic row parses to ≥2 intents, so the
only new defers there are model FPs already counted above);
correct-on-handled 73.1% flat or up.

## F16 — ACTUAL (2026-09-07): the wiring WAS the bug; the routing was a second, separate bug

**The atomicity board — predicted band beaten on B, met on A.**

| dataset · slice | predictor | acc | compound P | R | F1 | FP cheap | FN expensive |
|---|---|---|---|---|---|---|---|
| B-test | LAYER before | 88.0% | 82.1% | 68.8% | 74.9% | 94 | 195 |
| B-test | LAYER after | **92.5%** | **85.2%** | **86.4%** | **85.8%** | 94 | **85** |
| B-test | (model alone, for reference) | 91.9% | 85.3% | 83.4% | 84.3% | 90 | 104 |
| A-test | LAYER before | 93.3% | 94.6% | 85.0% | 89.6% | 11 | 34 |
| A-test | LAYER after | **98.1%** | **95.0%** | **99.6%** | **97.2%** | 12 | **1** |

Predicted B-test recall 82–84% (i.e. "it should land on the model's own
line"); **actual 86.4%, above the model alone**. The reason is the finding:
rules-OR-model is a genuine union — the gates catch compounds the classifier
is not decisive about, and the classifier catches the quiet ones the gates
have no cue for — so the wired layer now beats BOTH its parts (F1 85.8 vs
84.3 model / 60.5 rules). B-test half-executions 195 → 85, at zero
precision cost (FP 94 → 94). A-test met the band exactly: 34 → **1**
missed compound in 227.

**NOVEL EFFECT — and it changed the design.** Feeding the honest atomicity
verdict straight into ROUTING (defer on any compound) gave a much better
product-shape board — non-atomic defer 77.1 → **95.6%**, violations 129 →
25 — and was still WRONG. Two measurements said so:

1. Of the 104 rows it stopped committing, **96 had been producing the RIGHT
   counts** on the fast track (shape board's "of which produced right counts
   anyway": 103 → 7). Those are not half-executions; they are complete
   answers being thrown away.
2. With the LLM unreachable — CI, or Ollama down — "book gym on tuesday at
   7am and remind me to buy milk" routed to the deep track produces
   **nothing at all** (verified by raising from `engine.llm.call_json`),
   where the fast track produced both records. `test_a_two_intent_parse_
   keeps_fast_despite_a_joiner` and `test_a_mixed_command_is_answered_by_
   the_rules_alone` were red for exactly this reason, and they were right.

So the answer and the decision were split. `Atomicity.judge()` reports the
truth ("several items"); `_parse_covers_the_compound()` — in routing, where
it belongs — lets FastRule commit anyway when the parse already covers the
ask. **"Covers" is not "≥2 intents".** B-train mining: of 381 compound rows
committed on a ≥2-intent parse, 105 did NOT cover the ask and **80% of those
were three-ask families** ("book flu shot this morning, training session the
3rd, and remind me to …" → two intents, one ask lost). Requiring
`len(intents) ≥ 1 + ask-joiners` cuts that pile 105 → 14 on B-train, and the
14 survivors are KIND errors (event parsed as task), not lost asks.

**Downstream (`fastrule_shape`, B-test), with the split in place:** atomic
handle rate **53.5% → 53.5%** and correct-on-handled **73.1% → 73.1%** (the
brief's guard rail: untouched); non-atomic defer rate 77.1 → **77.8%**, the
"knew it was compound" share 51.2 → **52.0%**, routing violations 129 →
**125** — of which the half-executions (wrong counts) are **26 → 22** and
the complete-answer commits are 103 → 103. Propose defer 70.6% unchanged.
A modest downstream move is the honest price of not throwing away 96 correct
answers; the big number is the atomicity board's, which is what layer 0 is.

**Open product question for Gil (DEVQA):** `fastrule_shape` scores ANY
commit on a non-atomic row as a routing violation, including the 103 that
produce exactly the right records. If the ruling is "violation regardless",
delete `_parse_covers_the_compound` and the board jumps to 95.6% defer —
but the LLM-free path loses those commands entirely.

## F17 (layer 0 — the MODEL) — REGISTERED PREDICTION 2026-09-07

**Selection method (no test rows touched).** Candidate features were judged
by a **5-fold GroupKFold over B-train's pattern families** — the same unit
the real split uses, so a feature that only memorises a wording family
shows up as a fold loss — plus a fit on all of B-train scored against
**A-train**, a differently-shaped dataset. Because the cost is asymmetric,
they are compared at MATCHED RECALL (how many atomic rows must be wrongly
deferred to reach 90/95/98% compound recall) rather than at argmax, where
a precision-heavy feature can look good while losing the rows that matter.

**Banked negative, first: the syntactic block as a whole LOSES.** 15
dependency/structural features (clause coordination, conj counts, verb
counts, joiner counts and position, temporal subordinators, comma counts,
"to <verb>" counts) added together move B-train CV FP@R98 373 → **534** and
A-train FP@R99 54 → **67** — worse on both, at the operating point the cost
model actually selects. It is F13's lesson again: features that sharpen the
boundary on seen families blur it on unseen ones. Per-feature ablation
found only two that help, and only these two survive combination:

| feature set | B-train CV FP@R90 | FP@R95 | FP@R98 | A-train FP@R95 | FP@R99 |
|---|---|---|---|---|---|
| base 18 (shipped) | 210 | 327 | 373 | 19 | 54 |
| + all 15 syntactic | 179 | 286 | **534** | **29** | **67** |
| + joiner-mid | 220 | 294 | 334 | 16 | 56 |
| + clause-coord | 141 | 309 | 402 | 19 | 29 |
| **+ joiner-mid + clause-coord** | **138** | **290** | **347** | **16** | **29** |

**Change:** `AtomicityFeatures` gains exactly two signals, 18 → 20.
(a) **joiner-mid** — an ask-joiner falls in the middle 20–80% of the
sentence, i.e. the utterance has two HALVES rather than a trailing tag;
this is the "connective position" idea, and position is what separates
"meeting with Tal and Sam at 5" from "book the gym and remind me to call".
(b) **clause-coord** — `coordination.has_clause_coordination` as a FEATURE
rather than a gate, so the model can WEIGH the dependency parse's verdict
alongside the rest of the shape instead of it being an all-or-nothing veto.
The parse it needs is memoised so the gate and the feature share one spaCy
call.

**Predict.** *B-test, model tier alone at the shipped floor 1.5:* compound
recall 83.4 → 85–88%, said-atomic-but-COMPOUND 104 → 75–95, precision held
≥84% (FP 90 → ≤105). *B-test, the LAYER:* FN 85 → 70–80, accuracy 92.5 →
92.8–93.5%. *A-test:* recall stays ≥99% (it is already 99.6) with FP 12 →
≤10 — the A gain in CV was at the far-recall end, which A-test already
sits at, so I expect A to be FLAT and would read a drop as overfitting to
B. *Downstream (`fastrule_shape` B-test):* atomic handle rate within −1pp
of 53.5%, non-atomic defer rate 77.8 → 78–80%.

## F17 — ACTUAL (2026-09-07): the model improved on BOTH error kinds; the LAYER banked it as precision

**B-test, MODEL TIER alone at floor 1.5 — prediction met on every line:**
accuracy 91.9 → **93.1%**, compound P 85.3 → **87.4%**, R 83.4 → **86.1%**
(predicted 85–88), said-atomic-but-COMPOUND 104 → **87** (predicted 75–95),
said-compound-but-atomic 90 → **78**. Both error kinds fell — unusual, and
the sign that two features added information rather than moving the
boundary.

**B-test, the LAYER: accuracy 92.5 → 93.0%, P 85.2 → 87.0%, R 86.4 → 86.3%,
FP 94 → 81, FN 85 → 86.** Prediction MISSED on the expensive side: I said
FN 85 → 70–80 and it is flat. The reason is worth keeping: the compounds
the improved model newly catches were **already being caught by the rule
gates** — the union had them. What the better model bought is PRECISION,
so the gain shows up as 13 fewer atomic rows wrongly deferred, not as
fewer half-executions. Layer recall is now rules-limited, not model-limited.

**A-test: exactly flat** — accuracy 98.1%, R 99.6%, FN 1, FP 12 (predicted
flat; FP predicted ≤10, so a hair outside). A was already at ceiling: its
compounds are two real utterances joined by an announced connective (82%
carry "and", 36% "also", 22% "then"), so A measures "did you see the
joiner" and B measures the quiet compounds. Reporting them separately is
what makes that visible — a single blended number would have hidden it.

**Downstream (`fastrule_shape`, B-test):** atomic handle rate 53.5 →
**54.0%** (predicted "within −1pp"; it went UP, which is the precision gain
landing), correct-on-handled 73.1 → 72.7%, non-atomic defer rate 77.8%
FLAT (predicted 78–80 — missed, same reason as the layer FN), "knew" 51.8%,
violations 125, propose defer 70.6%.

**Two negatives banked.** (1) The 15-feature syntactic block, added
wholesale, is worse than no syntactic features at all at the recall the
cost model selects (B-train CV FP@R98 373 → 534, A-train FP@R99 54 → 67).
(2) Dropping `class_weight="balanced"` for atomicity — tested because the
balanced intercept was suspected of pushing featureless utterances to
"compound" — is a wash on B (CV FP@R98 348 vs 347) and clearly WORSE on A
(FP@R99 42 vs 29). Balanced stays.

**The margin floor is now justified, not assumed** (B-train sweep, printed
by `fit_route_models`). The sweep is a cliff, and the cliff is ONE
ambiguity bucket: 235 B-train rows share a single feature vector —
`{bias, and, joiner-mid}`, i.e. "there is an 'and' in the middle and
nothing else fires" — all at margin 0.64, and they are **160 atomic / 75
compound**. Floor 1.5 rejects the whole bucket; floor 0.5 accepts the whole
bucket. Priced on the product board (B-train): 1.5 → 0.5 buys 32 fewer
half-executions and 81 fewer layer FNs, and costs **97 correct fast
handles** (handle rate 59.7 → 56.6%) — roughly three lost fast-correct
answers per half-execution prevented, where the lost ones still get a
correct (slow) answer from deep and the half-executions are wrong in front
of the user. **Floor stays 1.5**: the bucket should be SPLIT, not bought
wholesale, which is F18.
