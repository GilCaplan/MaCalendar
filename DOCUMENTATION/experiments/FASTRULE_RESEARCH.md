# FastRule & Segment research — techniques for a deterministic selective classifier

Research pass, 2026-09-06. Scope: concrete, implementation-level techniques for
(1) `assistant/intent/rule_parser.py` + `assistant/engine/fastrule.py`
("FastRule", the deterministic front door) and (2) `assistant/engine/segment.py`
(the deep track's SEGMENT stage). No architecture change proposed anywhere —
both stay deterministic-first with the existing abstention/under-split gates;
the LLM call in segment stays a single schema-constrained call. Every claim
below is cited; grounding in "our terms" comes from having read
`rule_parser.py`, `fastrule.py` and `segment.py` directly (line numbers cited
where a sketch hooks into existing code).

---

## Part 1 — FastRule (the deterministic rule parser)

Current shape, confirmed by reading the code: `rule_parser.py` routes on
`_ROUTE_OVERRIDES` + an `(lemma, domain)` map, fills slots with spaCy +
recognizers-text, and `_compute_confidence` (line 1409) multiplies a
base slot-fill fraction by hand-set penalties (0.95 regex-date, 0.85
domain-inferred, 0.80 anaphora, 0.70 two-clock-times). `fastrule.py` wraps
that in a `FastRule(threshold)` selective classifier with four always-on
abstention gates (strong-compound, mixed-mode-compound, interrogative-create,
generic-target). Two instances run today: 0.80 (whole-command fast track)
and 0.60 (per-fragment inside the deep track). No fuzzy matching exists
anywhere in `rule_parser.py` — `match_title` is compared as exact text only
matching is `_GENERIC_TARGET_RE`, a denylist, not a resolver. Fuzzy string
matching (`difflib.SequenceMatcher`) already exists elsewhere in the codebase
(`assistant/stt/vocab.py`), so it is an established, dependency-free pattern
here — just not applied to target resolution yet.

### Ranked ideas

**1. Dependency-based coordination-type check (NP-coordination vs
clause-coordination) — targets failure mode #1, both directions**

*What it is.* Use spaCy's dependency parse, not regex, to decide whether an
"and"/"," joins two noun phrases (don't split) or two independent
clauses/verb phrases (candidate split). spaCy marks a coordinating
conjunction as `cc` and the second conjunct as `conj`; the conjunct's `.head`
tells you what kind of thing was coordinated — `token.head.pos_ == "VERB"`
means verb/clause coordination, `token.head.pos_ in ("NOUN","PROPN")` means
NP coordination. This is spaCy's own documented mechanism, not a guess:
"conj" links a coordinated word/phrase to its conjunction, and checking
`token.head.pos_` on the conjunct is the standard way to tell noun-phrase
from verb-phrase coordination in spaCy dependency trees.

*Evidence it works.* This is exactly the distinction the multi-intent NLU
literature identifies as the core difficulty: prior rule-based
multi-intent splitters that split purely "based on the position of
conjunctions or punctuation marks" are called out as a "serious limitation"
in the intent-boundary-segmentation literature, precisely because they
cannot tell "meeting with Tal and Sam" from "book X and remind me Y" —
which is our failure mode #1 verbatim. The fix the field converged on is a
**boundary classifier over the parse**, not more regex: "a boundary
classifier uses labels to classify boundary input tokens that form
intermediate boundaries... based on words labeled by the boundary
classifier," i.e., a structural decision at the token/clause level rather
than a cue-word lookup.
Sources: [Systems and methods for machine learning-based multi-intent segmentation and classification (patent, describes the boundary-classifier framing)](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10824818), [spaCy dependency labels — conj/cc](https://towardsdatascience.com/mastering-nlp-with-spacy-part-2/), [Coordination (linguistics) — NP vs VP ambiguity](https://en.wikipedia.org/wiki/Coordination_(linguistics)).

*Implementation sketch (ours).* A new pure-function pass, e.g.
`assistant/engine/coordination.py`, used by both `rule_parser.py`'s target
extraction and `segment.py`'s pre-split gate (shared, so it's written and
tested once):
1. Run the spaCy doc already computed for the utterance (no extra parse cost
   — `rule_parser.py` already parses with spaCy).
2. For every `cc` token, look at `conj.head.pos_`. `NOUN`/`PROPN` → merge
   (this is one NP, e.g. "Tal and Sam"); `VERB` → candidate split point
   **only if** the conjunct clause also has its own subject or is a bare
   imperative verb (check for an `nsubj`/`nsubjpass` child of the conj verb,
   or accept an imperative with no subject as spaCy tags it — "remind me to
   buy milk" has no subject, which is expected imperative structure, not
   disqualifying).
3. Before step 2, run a merge pass: any `PERSON`/`ORG`/`GPE` entity spanning
   the conjunction (spaCy `ents`), or two `PROPN` conjuncts under a shared
   preposition (`pobj` of the same `prep`, e.g. "with Tal and Sam"), gets
   merged into one non-splittable span first — this is the direct fix for
   "meeting with Tal and Sam."
4. Feed the resulting split-or-no-split verdict into the existing
   `_STRONG_COMPOUND_RE` gate in `fastrule.py` as an additional necessary
   condition, not a replacement — the regex stays as the free, cheap first
   filter; the dependency check adjudicates the ambiguous middle where the
   regex currently over- or under-fires.

*Effort:* M (new module + unit tests against the existing gate's regression
set; no schema or contract change — it slots into `EngineState`'s existing
inputs).

*Metric it should move:* count-correctness on the event+task compound slice
(both directions: fewer false splits of "meeting with Tal and Sam"-style
NP-coordination, fewer missed splits of genuine two-request compounds) and,
per FastRule's own scoring, more of the compound population becomes eligible
to commit at the fast track instead of abstaining on `strong-compound` /
`mixed-mode-compound` purely because a regex couldn't tell the two apart.

---

**2. spaCy `DependencyMatcher` split-point patterns instead of a growing
regex family — targets failure mode #1 (and the general "regex family
growing case by case" complaint)**

*What it is.* spaCy ships a rule-based `DependencyMatcher` that matches
patterns over the dependency tree (not just token sequences), letting you
declare "a ROOT verb with a `conj` VERB child that itself has an `nsubj` or
`dobj`" as one maintainable, named pattern instead of accumulating ad hoc
regexes for every phrasing that appears in the dataset.

*Evidence it works.* This is spaCy's own documented rule-based matching
mechanism, purpose-built for exactly this class of structural pattern
("Rule-based matching" — spaCy usage docs), and it composes with idea #1
rather than replacing it: idea #1 answers "is this NP or VP coordination,"
this idea gives a declarative, testable place to encode the growing list of
"what counts as a second independent request" shapes ("book X and remind me
Y", "X, then Y", "X — and Y", list-of-tasks-after-colon) as named patterns
with individual unit tests, instead of one regex accreting alternations.
Source: [spaCy rule-based matching docs](https://spacy.io/usage/rule-based-matching).

*Implementation sketch.* Each pattern becomes one `DependencyMatcher` rule
with a name (`"verb_conj_with_own_subject"`, `"imperative_after_also"`,
etc.); a hit contributes a labeled split candidate, which then goes through
idea #1's NP-merge check as a veto. New phrasings discovered in dataset
review become new named patterns with their own test, mirroring how
`ENGINE.md`'s per-stage test convention already works — a maintenance win
over adding another alternation to `_STRONG_COMPOUND_RE`.

*Effort:* M.

*Metric:* count-correctness on event+task compounds; secondarily, fewer
regressions per cycle (patterns are additive and independently testable,
unlike one shared regex).

---

**3. Tiered cue-phrase inventory (strong vs weak joiners), informed by
discourse-connective category — targets failure mode #1**

*What it is.* Not every joiner carries the same evidence for "two separate
requests." The Penn Discourse Treebank's connective taxonomy already
distinguishes **coordinating conjunctions** ("and", "but") from **discourse
adverbials** ("also", "then", "however") as a separate, stronger class of
discourse-boundary signal — discourse adverbials are a distinct PDTB
category from bare coordinating conjunctions precisely because they more
reliably mark a new discourse unit rather than a same-clause continuation.
`fastrule.py`'s own `_STRONG_COMPOUND_RE` already encodes this intuition
informally (`and then`, `. also`, `— and`, `, then` are "strong"; bare `and`
is not) — this idea is to make that tiering explicit, complete, and testable
against the PDTB's connective list rather than whatever the dataset has
happened to surface so far.

*Evidence it works.* PDTB's own annotation manual classifies connectives
into subordinating conjunctions, coordinating conjunctions, and discourse
adverbials as three distinct categories with different discourse behavior.
Source: [Penn Discourse Treebank 3.0 Annotation Manual](https://catalog.ldc.upenn.edu/docs/LDC2019T05/PDTB3-Annotation-Manual.pdf), [PDTB overview / connective classification](https://catalog.ldc.upenn.edu/LDC2019T05).

*Implementation sketch.* Pull the PDTB connective list (public, in the
annotation manual), filter to the subset that occurs in casual spoken
English commands, and split `_COMPOUND_HINT`/`_STRONG_COMPOUND_RE` into two
explicit tiers with different downstream behavior: a *strong* tier (discourse
adverbials + explicit sequencing: "then", "also", "next", "after that",
"plus") is sufficient on its own to warrant idea #1's structural check; a
*weak* tier (bare "and", comma) requires the structural check to ALSO find
two independently-verbed clauses before it's treated as a split candidate at
all. This is a pure data/config change to existing regexes, not new
machinery.

*Effort:* S.

*Metric:* count-correctness on event+task compounds; also reduces false
`strong-compound` abstentions on single-item commands that merely contain a
weak-tier word (e.g. an item with an incidental "and" inside a title).

---

**4. Small hand-feature logistic-regression classifier for the event-vs-task
kind decision — targets failure mode #2**

*What it is.* Replace the growing regex cascade (`_TASK_RE`, `_CLOCKISH_RE`,
`_REMINDISH_RE`, `_REMIND_TO_VERB_RE`, `_NEED_ENCOUNTER_RE`, `_OCCASION_RE`,
`_DATED_RE`, chained through `_kind_of` and `_enforce_pinned_kinds` in
`segment.py`) with a single small logistic regression over the same hand
features those regexes already compute as booleans: `has_clock_time`,
`has_date_ref`, `verb_in_errand_lexicon`, `verb_in_occasion_lexicon`,
`remind_word_present`, `remind_to_verb_form`, `sentence_is_imperative`. This
is explicitly the class of model this project's own constraints allow ("a
small trainable component like logistic regression over hand features would
be acceptable").

*Evidence it works.* Two independent supports: (a) imperative mood is a
validated, strong signal for reminder/errand-type requests — a study of
reminder phrasing found the large majority of reminder-style utterances are
imperative in structure, and that "remind", "remember", and "don't forget"
cluster together as a distinguishable request type by their own
similarity/verb-phrase signal, i.e., the same handful of features the
current regex family encodes by hand are independently identifiable
features, which is exactly what a linear model over them would exploit
rather than an ever-growing pattern list. (b) Snips NLU's own design
rationale for choosing logistic regression + CRF over deep learning for
intent/slot decisions at this scale: "there was no significant gain using
deep learning versus CRFs for this task, so they favored the lightest
option" — validating that a small linear model, not more rules and not a
bigger model, is the right size of fix here.
Sources: [Authoring personalized reminders — imperative mood + verb clustering findings](https://arxiv.org/pdf/2605.23085), [Snips NLU architecture / design rationale](https://medium.com/snips-ai/an-introduction-to-snips-nlu-the-open-source-library-behind-snips-embedded-voice-platform-b12b1a60a41a).

*Implementation sketch.* Train offline (a scratch script, not shipped code)
on the dataset's labeled event/task rows using the existing feature
booleans as `X` and the ground-truth kind as `y`; export the fitted weight
vector as a small constant array in `segment.py` (or a sibling module) and
evaluate it at runtime as a dot product + sigmoid — still pure Python,
still microseconds, still fully inspectable (print the learned weight per
feature to sanity-check it, the way the hand-tuned regex priority order is
inspectable today). Falls back to the current regex cascade's *outcome* as
one of its own features during a transition period so the change is
gradual rather than a flag day.

*Effort:* M (mostly building the training script and the offline fit;
`sklearn.linear_model.LogisticRegression` is a reasonable one-time offline
dependency even though the runtime artifact is just a weight vector — no
new runtime dependency).

*Metric:* count-correctness specifically on the "kind-swap" failure class
(event mis-labeled task or vice versa) within the event+task slice — this
is the metric CLAUDE.md's failure list names directly ("event mis-kinded as
task").

---

**5. Fuzzy + phonetic target matching against known titles — targets
failure mode #3**

*What it is.* When a mutation command names a target ("remove 'father's
day' from calendar"), resolve the extracted `match_title` span against the
actual titles in the user's DB for the relevant window using string
similarity, instead of requiring an exact match. Two complementary layers:
(a) edit-distance / token-set similarity (`difflib.SequenceMatcher`, already
a dependency-free pattern used in `assistant/stt/vocab.py` at a documented
threshold of 0.80) for ordinary misspellings and truncated quotes; (b) a
phonetic key (Double Metaphone) as a secondary tie-break specifically for
STT mishearing errors, which edit distance is bad at — the vocab.py module's
own docstring already flags this exact gap ("speech recognition fails
phonetically and difflib compares letters"), so this closes a known,
self-documented hole rather than a hypothetical one.

*Evidence it works.* Token-set-style fuzzy ratio is the standard,
benchmarked choice for this class of entity-resolution problem — "research
comparing various fuzzy matching scoring functions... selected the
token-set-ratio function as the top-performing function for entity
resolution," with 70 as a common match threshold. Double Metaphone is the
standard general-purpose recommendation for phonetic fallback: "research
suggests Double Metaphone is recommended for general purpose phonetic
matching," and its whole value proposition over edit distance is names that
"sound the same, but have a very low edit distance percentage" (their own
example: Jean/Gene) — precisely the STT-mishearing failure class our own
vocab.py module already calls out as difflib's blind spot.
Sources: [RapidFuzz token_set_ratio — benchmarked as top entity-resolution scorer](https://strategicprojects.github.io/RapidFuzz/reference/fuzz_token_set_ratio.html), [Double Metaphone / phonetic matching recommendations](https://support.syniti.com/hc/en-us/articles/5875511093783-Fact-4-Conventional-Matching-Algorithms-Here-is-what-you-need-to-know), [Double Metaphone Search Algorithm](https://www.researchgate.net/publication/234803025_The_Double_Metaphone_Search_Algorithm).

*Implementation sketch.* In `rule_parser.py`, after extracting a raw
`match_title` span (quoted or bare), query the DB for candidate titles in a
bounded window (the same window the action would operate on — e.g. open
events/todos, not the whole history), score each with
`difflib.SequenceMatcher(None, norm(query), norm(candidate)).ratio()`
mirroring `vocab.py`'s existing convention, accept the best match above
~0.80, and only when nothing clears that bar, fall back to a Double
Metaphone key comparison (a small pure-Python implementation, ~100 lines,
no new heavy dependency) for a secondary pass. Record which layer resolved
the match in the trace so a wrong resolution is diagnosable, the same way
`_enforce_pinned_kinds` documents *why* each override fires.

*Effort:* S–M (Double Metaphone as a small vendored pure-Python function;
difflib layer is very small since the pattern already exists in the repo).

*Metric:* garbage-titles / count-correctness on the update/delete slice,
specifically commands with a quoted or misspelled target — currently these
either fail `_GENERIC_TARGET_RE` softly or produce a DB miss ("I couldn't
find...", which CLAUDE.md is explicit is the *correct* behavior when
genuinely unresolvable — this idea is about correctly resolving the cases
that are NOT genuinely ambiguous, just misspelled).

---

**6. Confidence calibration via logistic regression over logged
(feature → correct) pairs — targets failure mode #4**

*What it is.* Replace the five hand-chosen multiplicative penalties in
`_compute_confidence` (0.95 / 0.85 / 0.80 / 0.70, plus the slot-fill base)
with weights fit from data: log, for every FastRule verdict during dataset
runs, which penalty conditions fired (`regex_fallback`, `domain_inferred`,
`used_anaphora`, `two_clock_times`) plus the slot-fill fraction, alongside
whether the committed parse was actually correct (the dataset scorer
already determines this). Fit a logistic regression on those
feature/outcome pairs; the fitted weights replace the hand-picked constants.
This is precisely Platt scaling's use case generalized from binary
classifier scores to a multi-factor rule confidence: "Platt scaling is
essentially a logistic regression over any classifier which gives a raw
[score]... the new logistic regression learns weights accordingly and
produces calibrated probability," and it is explicitly noted to generalize
beyond SVMs to "any probabilistic model," including rule-based systems that
"produce confidence scores."

*Evidence it works.* Platt scaling is the standard technique for exactly
this transformation (uncalibrated score → validated probability), broadly
applicable beyond its original SVM setting. Separately, the correct
threshold to place on the resulting calibrated confidence is itself a
solved problem, not a guess: Chow's 1970 rule is the classical result that
the risk-minimizing policy is "the Bayes classifier abstaining from
prediction when the conditional expected risk exceeds the reject cost" —
i.e., once confidence is calibrated, the FastRule threshold (0.80 / 0.60)
should be derived from the actual cost of a wrong commit vs. the cost of an
unnecessary abstain, not picked by feel. Follow-on work formalizes this
further for classifiers exactly like FastRule (predict-or-defer with a
tunable cost).
Sources: [Platt Scaling explainer](https://www.blog.trainindata.com/complete-guide-to-platt-scaling/), [Platt scaling generalizes beyond SVMs to any probabilistic/rule-based scorer](https://medium.com/@boukamchahamdi/importance-of-platt-scaling-in-calibrating-confidence-rates-ad692c7c186f), [Chow's rule / optimal reject-option classifiers survey](https://arxiv.org/html/2107.11277v3), [Optimal Strategies for Reject Option Classifiers (JMLR)](https://jmlr.org/papers/volume24/21-0048/21-0048.pdf).

*Implementation sketch.* This is a natural extension of the dataset loop
already in place (`scripts/engine_dataset_compare.py`): add a log line per
FastRule verdict capturing the four penalty-trigger booleans + slot-fill
fraction + eventual correctness (already computed by the scorer), fit
`sklearn.linear_model.LogisticRegression` offline on accumulated runs,
export the weight vector into `_compute_confidence` as a dot product +
sigmoid replacing the current multiply-chain. The two live thresholds
(0.80, 0.60) get re-derived the same way idea below (#7) describes, from
the now-calibrated score's actual reliability curve rather than kept as
tuned magic numbers.

*Effort:* M (logging is cheap and mostly already available via the dataset
runner's per-row output; the fit itself is a small offline script).

*Metric:* per CLAUDE.md's own scoring formula (commit-rate × correct-on-
committed + recoverable-abstain headroom) — this idea's target metric is
literally "adjusted-correct" at a *fixed* commit-rate improving, or,
symmetrically, commit-rate rising at the current ~93% adjusted-correct
without a drop — i.e., moving the actual operating point rather than a
proxy. Named metric+slice: adjusted-correct-on-committed, whole-command
fast-track population.

---

**7. Reliability-diagram audit as the cheap precursor to #6**

*What it is.* Before fitting a full logistic regression, do the simpler
diagnostic step calibration literature recommends first: bucket committed
FastRule verdicts by their current confidence score and check, per bucket,
what fraction were actually correct (a reliability diagram). This is
standard practice in classifier-calibration work and is worth doing even if
#6 is deferred, because it directly answers "which of the four penalties is
miscalibrated, and in which direction" without needing a training pipeline
yet — e.g., it may show 0.85 (domain-inferred) is far too harsh or far too
lenient before any model-fitting is justified.

*Evidence it works.* Reliability-diagram-based auditing is the standard
first diagnostic in the classifier-calibration literature, used to assess
whether "predicted probabilities align with actual outcomes" before
choosing a calibration method.
Source: [Classifier Calibration: a survey](https://arxiv.org/pdf/2112.10327).

*Implementation sketch.* A one-off analysis script (not shipped code) over
existing dataset-run logs, bucketing by confidence decile and reporting
per-bucket correctness — directly informs whether to retune the four
constants by hand (fast, S effort) or whether the interactions are complex
enough to warrant #6's fitted model (M effort).

*Effort:* S.

*Metric:* diagnostic only — informs which of #6's constants most need
fixing and by how much, i.e., it's the hypothesis-generation step CLAUDE.md's
own iteration protocol asks for before spending a cycle on #6.

---

**8. Deterministic title-span extraction via feature-scored token windows
(a lightweight CRF-in-spirit, not a trained CRF) — targets failure mode #5**

*What it is.* Snips NLU's slot filler is a linear-chain CRF *per intent*,
trained on local per-token features (surrounding POS, surrounding words,
gazetteer membership) to tag each token as belonging to a slot or not — and
notably, their own finding was that this lightweight, classically-featured
model matched deep learning at no cost in accuracy. We can't add a trained
CRF library without disproportionate machinery for our scale, but the same
*idea* — score each token's slot membership from local hand features rather
than a single regex trying to capture the whole title span at once — is
directly portable as a small per-token classifier (or even a hand-set
scoring rule, à la idea #4) over spaCy's existing per-token POS/dependency
output: once the date/time recognizer has claimed its span and known filler
words (bare prepositions not inside a NP) are marked, score the remaining
tokens for TITLE vs FILLER using features already computed (POS, dep label,
distance from the claimed date span, whether it's inside a noun chunk
headed by the sentence's root or object).

*Evidence it works.* Snips NLU's own architecture write-up: the slot filler
"consists of several linear-chain CRFs... specifically trained to extract
the slots," and their explicit design rationale for staying this size
rather than going bigger ("no significant gain using deep learning versus
CRFs... favored the lightest option") is direct evidence that local,
hand-featured, linear scoring is sufficient for exactly this kind of span
extraction at this scale — the same argument that licenses skipping a full
trained CRF and using a much smaller hand-feature scorer instead.
Source: [Snips NLU introduction / architecture](https://medium.com/snips-ai/an-introduction-to-snips-nlu-the-open-source-library-behind-snips-embedded-voice-platform-b12b1a60a41a).

*Implementation sketch.* After date/time slots are filled (existing
recognizer output already marks their character spans), walk the remaining
tokens and classify each as TITLE/FILLER using a small fixed-weight or
logistic-regression score (same training path as idea #4, reusing the
labeled dataset's known event/task titles as ground truth for span
boundaries) rather than the current approach of carving the title out with
`_clean_title`/`_extend_title_with_whom`-style regex helpers case by case.
Contiguous TITLE-tagged tokens (after the claimed date/time span is
excised) become the title. Falls back to the existing regex helpers when
confidence is low, so this is additive, not a rip-and-replace.

*Effort:* L (needs labeled span boundaries, not just labeled kinds — more
data preparation than idea #4).

*Metric:* garbage-titles metric, across all slices (this metric is exactly
"did the title span come out clean" per CLAUDE.md's own metric list).

---

## Part 2 — the SEGMENT stage (deep track, step 2)

Read directly from `assistant/engine/segment.py`. Today: deterministic
delimiters first (`_COALESCE_RE`, `_BRACKET_RE`, configured separator — all
free and cannot be wrong per the module's own docstring); if none of those
split anything, a **single** schema-constrained LLM call
(`_SEGMENT_SYSTEM` + `_SEGMENT_SCHEMA`) is made, but *only* if the utterance
is ≥6 words AND matches `_COMPOUND_HINT` (`and|then|also|plus|after that|,|;`)
— i.e. any bare "and" already triggers an LLM call today, including for
pure NP-coordination like "meeting with Tal and Sam." The LLM returns
`{"items": [{"kind", "text"}]}` where `text` is **regenerated**, not a span
reference — the model retypes each item's words rather than pointing at
character offsets in `state.text`. A retry hook already exists:
`state.mistakes` is appended to the system prompt on a loop-back from
crosscheck (step 6), so a "you missed the event half last time" signal
already has a wire to follow, unused for a first-pass validation today.

The named failure (46% count-correct on event+task compounds, dominant
mode: one half of a two-ask utterance vanishing or mis-kinded) is exactly
what you'd expect from asking a small local model to both *detect* the
split points and *regenerate* each half's text in one unconstrained pass:
a dropped or merged half is invisible to the schema validator, because
`{"items":[{"kind":"task","text":"..."}]}` with only one entry is
perfectly valid JSON — nothing about the schema currently proves the count
is right.

### Ranked ideas

**1. Route the coordination-type check from Part 1 in *front* of the LLM
call, as a confident pre-split gate — targets the dominant miss directly**

*What it is.* The same dependency-based NP-vs-clause coordination check
(Part 1, idea 1) doubles as a **free, confident pre-split** here: when it
finds a genuine clause-level coordination (each side has its own verb, no
shared-entity merge blocks it) paired with a strong-tier cue (Part 1, idea
3), split deterministically and skip the LLM call entirely for that case.
This directly reduces the population that ever reaches the failure-prone
LLM call, and — because it is the *same* verified-safe check that already
protects against splitting "Tal and Sam" (Part 1's entity-merge pass runs
first) — it does not trade away the under-split-bias safety property: it
only fires when confidence is structurally high, and everything else still
falls through to the existing LLM call unchanged.

*Evidence it works.* This is the literature's own recommended fix for
rule-based-conjunction-position splitting being unreliable — not "add more
rules," but structural/parse-based boundary detection — applied here as a
gate rather than the final word, so it inherits the same evidence as Part
1 idea 1.
Sources: (shared with Part 1 idea 1) [multi-intent boundary classifier framing](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10824818), [DialogUSR — splits multi-intent utterances into single-intent sub-queries as a distinct, dedicated step before downstream processing](https://arxiv.org/abs/2210.11279).

*Implementation sketch.* In `segment.py`'s `run()`, between the existing
`_deterministic_segments` call and the `_llm_segments` fallback, insert a
call to the shared `coordination.py` module from Part 1. Only accept its
verdict as a genuine pre-split when it is unambiguous by both the
structural test AND a strong-tier cue word — anything softer still falls
through to the LLM path unchanged, preserving the current under-split bias
exactly. Log which path fired in the trace step, same convention as the
existing `how` variable (`"coalesced"` / `"batched"` / `"separator"` grows a
new `"coordination"` value).

*Effort:* M (shared cost with Part 1 idea 1 — if that module exists this is
mostly wiring).

*Metric:* **missing-half** (CLAUDE.md's own named metric for exactly this
failure) on the event+task slice, plus parse-path/latency (fewer LLM calls
issued at all for the population this gate confidently resolves).

---

**2. Span-offset extraction instead of regenerated text — targets the
"vanishing half" mechanism directly**

*What it is.* Change `_SEGMENT_SCHEMA` so each item carries `start`/`end`
character offsets into the ORIGINAL `state.text` instead of (or in addition
to) a freely retyped `text` field, and slice the substring yourself in
Python rather than trusting the model's retyped copy. This turns "did the
model quietly drop or paraphrase a segment" into a mechanically checkable
question: offsets must be non-overlapping, increasing, and their union must
cover the transcript (modulo whitespace/filler) — anything left uncovered
by any item's span is a **detectable, specific signal** of a probable
missing segment, which today is invisible because a shorter regenerated
`text` looks just as well-formed as a complete one.

*Evidence it works.* Span-copying via character offsets is the standard
mitigation for exactly this class of generation drift in extraction tasks:
"the use of character offsets for span copying provides a precise, grounded
approach compared to regenerated text, which may introduce additional
hallucinations through the generation process itself," and the standard
implementation pattern is "searching for extracted substrings in the full
model output and noting their start and end character indices" — directly
applicable here since our "document" is the already-known transcript, not
a retrieved passage, making offset validation even more reliable than the
general case.
Source: [span extraction via character offsets, grounding vs hallucination](https://arxiv.org/pdf/2504.04335) (span-level extraction and offset-grounding discussion), general practice also described in structured-extraction literature: [SLOT: Structuring the Output of LLMs](https://arxiv.org/html/2505.04016v1).

*Implementation sketch.* `_SEGMENT_SCHEMA`'s `items[].text` becomes
`items[].start` + `items[].end` (integers), with a short instruction added
to `_SEGMENT_SYSTEM` telling the model to report where each item begins and
ends in the ORIGINAL command rather than retype it (the existing prompt
already emphasizes "copy the speaker's own words" — this makes that
instruction mechanically enforced instead of aspirational). Post-call
validation in `_llm_segments`: reject (fall back to one-item, per the
existing under-split-bias contract) if spans overlap, are out of order, or
if a chunk of ≥N uncovered characters contains a verb per a quick spaCy
check — that last check is a strong, free signal that something was
dropped, and it can feed `state.mistakes` for the existing retry hook (idea
4 below) instead of silently accepting a short list.

*Effort:* S–M (schema change is small; the validation logic and its
interaction with the existing `_HEADER_RE`/`_schedule_only` filters —
which currently operate on retyped text and would need to operate on
sliced spans instead — is the real work).

*Metric:* **missing-half** on event+task compounds — named directly.

---

**3. Self-anchoring the split count using a deterministic clause count as a
prompt hint, still inside the one allowed call**

*What it is.* Before calling the LLM, run a cheap deterministic count of
independent top-level verb clauses using the same spaCy parse (count ROOT
verbs plus `conj` verbs attached at the top level, after the Part-1
entity-merge pass removes false positives from NP coordination). When that
count is unambiguous (e.g., exactly 2), pass it into the prompt as a hint
("this command contains exactly 2 independent requests — return exactly 2
items") rather than leaving the model to discover the count itself. This is
still the single schema-constrained call the design freezes — it just
grounds that one call with a piece of information we can already compute
for free, rather than asking the model to do detection AND extraction
unaided.

*Evidence it works.* This mirrors two related, evidenced patterns:
(a) schema/structure commitment improving small-model extraction
reliability — asking a model to commit to a structural fact (a count) before
free-text extraction is a known reliability lever in structured-output
work, and (b) DialogUSR's framing of utterance-splitting as its own
dedicated pre-step before downstream reformulation, rather than trusting a
single free pass to both notice and execute the split — we get a version of
that dedicated pre-step for free from the deterministic parse instead of a
second model pass, honoring the "one call" constraint.
Sources: [SLOT: Structuring the Output of LLMs — structural commitment before extraction](https://arxiv.org/html/2505.04016v1), [DialogUSR — utterance splitting as a distinct step](https://arxiv.org/abs/2210.11279).

*Implementation sketch.* In `_llm_segments`, compute
`expected_count = _count_top_level_clauses(doc)` (new small helper reusing
the Part-1 dependency scan) before building the prompt; when it returns a
confident number ≥2, append one line to the per-call user message ("The
command: {text}\n(This appears to contain exactly {n} separate requests.)")
— note this is a *hint*, not a hard constraint, since the deterministic
counter can itself be wrong on genuinely ambiguous input, and the design
explicitly prefers under-splitting to a confident wrong split. Only emit
the hint when the counter's own confidence is high (i.e., reuse Part 1
idea 1's structural certainty condition), so a bad hint is never forced
onto an ambiguous case.

*Effort:* S (reuses the clause-counting logic idea 1 already needs;
this is mostly prompt wiring).

*Metric:* **missing-half** on event+task compounds; secondarily
count-correctness broadly, since a bad hint is avoided by construction.

---

**4. Use the existing `state.mistakes` retry hook for a same-call
verb-coverage check, instead of leaving it dormant on the first pass**

*What it is.* `_llm_segments` already appends `state.mistakes` to the
system prompt "on a previous attempt at THIS command" — but that hook is
only fed by crosscheck (step 6) looping back, i.e., only *after* the
mistake has already propagated downstream and been caught late. Add a
same-stage, immediate check: after the LLM returns its items, compare
`len(items)` (or the total token/verb coverage of item texts) against the
deterministic clause count from idea 3. If items look short relative to
the deterministic estimate, retry the SAME single call once, this time with
a concrete, specific correction appended to the system prompt ("your last
attempt returned 1 item but the command has 2 independent requests — do not
drop the second one"), reusing the exact mechanism already wired for the
step-6 loop-back, just triggered locally and immediately instead of waiting
for a downstream stage to notice.

*Evidence it works.* This is the same self-correction principle the module
already trusts enough to have built (the `state.mistakes` mechanism
exists specifically because a second, informed attempt recovers errors a
first blind attempt makes) — this idea is "use it sooner," backed by the
same multi-intent-splitting literature's general point that detecting
*that* a split was likely missed is a tractable, separate signal from
getting the split right the first time (the boundary-classifier literature
treats "how many segments" as checkable independently of "where exactly are
they").

*Implementation sketch.* In `run()`, after getting `llm_items`, if
`len(llm_items) < expected_count` from idea 3's counter, call
`_llm_segments` again with a one-line addition to `state.mistakes`
(`f"returned {len(llm_items)} items but the command likely has "
f"{expected_count} independent requests"`) before falling through to
accepting the (possibly still short) result — capped at one retry to keep
latency bounded, matching the existing single-call design intent per
attempt.

*Effort:* S (pure control-flow change using code that already exists).

*Metric:* **missing-half** on event+task compounds; parse-path/latency
should be watched (one extra call only on the subset flagged short, not
across the board).

---

**5. Typed-segment (event/task/review) classification reused from Part 1**

*What it is.* The same hand-feature kind-classifier proposed in Part 1 idea
4 is literally the same code path here — `_kind_of` and
`_enforce_pinned_kinds` live in `segment.py` itself, not in `rule_parser.py`
— so this is one implementation serving both the FastRule slot-filling path
and the SEGMENT stage's first-reading kind label. No separate research
needed; cross-referenced here so the effort is costed once, not twice.

*Effort:* (shared with Part 1 idea 4 — costed there.)

*Metric:* count-correctness / kind-swap rate on the event+task slice,
specifically for the *first reading* kind (before step 5's settling pass),
since a wrong first-reading kind is what currently causes an event to be
mis-typed as a task inside a compound and then possibly dropped by a
downstream stage that filters on kind.

---

**6. A segment-only evaluation harness using boundary-tolerant matching —
separates SEGMENT's own error rate from downstream noise**

*What it is.* Today, "46% count-correct on event+task compounds" is an
end-to-end number — a wrong count could originate in SEGMENT, DECOMPOSE, or
CROSSCHECK, and the existing per-stage trace makes this diagnosable by
hand but not by a single number. Add a segment-specific metric, run via
`scripts/engine_stage_check.py --stage segment` (already the pattern
CLAUDE.md describes for isolated stage checks): compare predicted item
count AND (once idea 2's offsets exist) predicted span boundaries against
the dataset's expected item boundaries, using a **tolerance-based boundary
match** rather than exact-position match — a predicted boundary counts as
correct if it falls within a small token-distance window of a true
boundary, which is standard practice in dialogue/text segmentation
evaluation precisely because exact-position agreement over-penalizes
near-misses that don't actually matter downstream.

*Evidence it works.* Tolerance-based boundary matching for segmentation
evaluation is an established alternative to exact-match precision/recall:
dialogue-segmentation work explicitly adopts "the mF1B (mean F1 score of
boundary) metric... where a predicted boundary is considered correct if its
distance to a ground-truth boundary is less than a predefined threshold,"
and the broader text-segmentation evaluation literature notes that
"traditional classification metrics like F1 over-penalize near misses"
compared to boundary/window-based alternatives.
Sources: [When F1 Fails: Granularity-Aware Evaluation for Dialogue Topic Segmentation](https://arxiv.org/pdf/2512.17083), [SegEval documentation — boundary-based segmentation metrics](https://segeval.readthedocs.io/), [Recent Trends in Linear Text Segmentation: a Survey](https://arxiv.org/pdf/2411.16613).

*Implementation sketch.* Extend the dataset's per-row ground truth (which
already records expected event/task counts per CLAUDE.md's dataset
description) with expected item boundaries where feasible, or — as a
cheaper first cut requiring no new annotation — just report count-delta
(`|predicted_count - expected_count|`) as its own tracked figure per
compound row, separate from downstream correctness, so a cycle that
improves SEGMENT specifically can be measured without the noise of
DECOMPOSE/CROSSCHECK errors moving the same aggregate number.

*Effort:* S (count-delta cut) to M (full boundary-tolerant scoring, needs
span ground truth).

*Metric:* this idea defines the new instrument itself — "segment count-delta"
or "segment boundary F1" — to sit alongside missing-half as the
stage-isolated diagnostic CLAUDE.md's own philosophy asks for ("a weak
stage is found by its line, not by staring at the headline number").

---

**7. Entity-merge pre-filter on `_COMPOUND_HINT` itself — cuts wasted/risky
LLM calls for pure NP-coordination inputs**

*What it is.* `_COMPOUND_HINT` today fires on any bare "and", including
"meeting with Tal and Sam tomorrow" (10 words, contains "and") — which means
that utterance already reaches the LLM call today, relying entirely on the
prompt's explicit few-shot examples ("Never split people joined by 'and'")
to hold the line. Running Part 1's entity-merge pass (PERSON/ORG/GPE spans
across a conjunction) as a pre-filter on `_COMPOUND_HINT` lets pure
NP-coordination inputs skip the LLM call entirely — both a latency win and
a risk reduction, since the LLM is no longer the sole line of defense
against mis-splitting people's names for the population where the parser
is already structurally certain.

*Evidence it works.* Same evidence base as Part 1 idea 1 — the merge check
being verified deterministic and cheap is what makes it safe to use as a
short-circuit rather than just a signal.

*Implementation sketch.* Before the `len(text.split()) < 6 or not
_COMPOUND_HINT.search(text)` early-return in `_llm_segments`, run the merge
pass; if merging collapses every conjunction in the utterance into a single
non-splittable entity span, treat it as equivalent to "no compound hint
found" and return `None` (one item) without ever calling the LLM.

*Effort:* S (shared module with Part 1 idea 1; this is one more call site).

*Metric:* parse-path/latency (fewer LLM calls for a well-defined
population), plus a secondary false-split-rate check specifically on the
"names joined by and" regression class to confirm no regression versus
today's prompt-only defense.

---

## Part 3 — what the big systems do (shared background)

**Snips NLU** ran two parsers side by side: a **deterministic** regex-pattern
parser for exact/templated phrasings, and a **probabilistic** parser
(logistic regression for intent classification + one linear-chain CRF per
intent for slot filling) for everything else — explicitly choosing CRFs
over deep learning because deep learning gave no measurable accuracy gain
at their scale. This "deterministic first, small classical ML second" shape
is structurally identical to FastRule → LLM, just with the second tier
being a much smaller classical model rather than an LLM — evidence that the
project's existing shape is a well-trodden one, and that the "small
trainable component" carve-out in this project's constraints is exactly
where Snips also found the accuracy ceiling for this problem class to sit.
[Snips NLU architecture](https://medium.com/snips-ai/an-introduction-to-snips-nlu-the-open-source-library-behind-snips-embedded-voice-platform-b12b1a60a41a).

**Rasa** keeps a `RegexEntityExtractor` as a genuinely rule-based,
non-learning component specifically for entities that "follow a structured
pattern" and "don't really need an algorithm," alongside a `RulePolicy` for
deterministic conversation-flow handling — both live inside an otherwise
ML-heavy pipeline, i.e., even a fundamentally statistical framework
deliberately keeps hard-coded deterministic components where the pattern is
genuinely structured, rather than routing everything through the learned
path. [RegexEntityExtractor](https://dev.to/aniket_kuyate_15acc4e6587/understanding-the-regexentityextractor-in-rasa-4903), [Rasa policies overview](https://learning.rasa.com/archive/conversational-ai-with-rasa/pipeline/).

**Mycroft's two intent parsers** are a real-world example of exactly our
two-tier shape at consumer scale: **Adapt** is "a keyword based intent
parser" using small required/optional keyword groups — fast, deterministic,
prone to false matches on loose phrasing — while **Padatious** is trained
per-sentence on example utterances for looser matching. Mycroft runs both
and takes whichever is confident, matching the "deterministic tier commits
when confident, fuzzier tier as the net" pattern directly (though
Padatious's status as a small trained neural net is exactly the kind of
component this project's constraints rule out — see Dead Ends). [Adapt](https://github.com/MycroftAI/adapt), [Padatious](https://github.com/MycroftAI/padatious), [Adapt vs Padatious comparison](https://opensource.com/article/20/6/mycroft-intent-parsers).

**CMU's Phoenix parser** (1990s ATIS-era air travel dialog systems) used a
hand-written **domain-specific semantic grammar** to parse utterances into
frames, feeding a schema-based dialog manager (the Carnegie Mellon
Communicator). It is the historical proof-of-concept that a semantic
grammar can carry a real spoken dialog system — but see Dead Ends for why a
full grammar isn't recommended here. [CMU Communicator system description](http://www.cs.cmu.edu/~air/papers/SchemaDialog1998.pdf).

**Stanford's Genie/Almond/ThingTalk** is the modern descendant of the same
grammar idea, and its own trajectory is instructive: developers write a
**grammar** (ThingTalk + templates), but Genie then uses that grammar only
to **synthesize training data**, which trains an actual **neural semantic
parser** — i.e., even a grammar-forward, academically rigorous 2019 system
concluded that the grammar alone wasn't the end product for handling real
user phrasing variance; it became a data generator for a statistical
component layered on top. [Genie paper](https://arxiv.org/abs/1904.09020).

**Amazon Alexa's NLU** is hybrid at a different layer: finite-state
transducers / grammars handle exact-match and built-in structured slot
types (numbers, dates, standard entities), while a joint statistical
intent-classification-and-slot-filling model handles open-ended phrasing —
again the same "deterministic for the structured part, statistical for the
open part" split, just drawn at the slot-type boundary rather than the
whole-utterance boundary. [Alexa NLU architecture description](https://arxiv.org/pdf/1711.00549), [Amazon patent — rules-based grammar for slots + statistical model for preterminals](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/7603267).

**Common thread across all of them:** nobody ships pure-rules or pure-ML at
this problem's scale — every serious system keeps a deterministic layer for
the genuinely structured subset (dates, numbers, templated phrasings,
entity lists) and a fuzzier layer (classical ML or neural) for the open
tail, exactly the shape FastRule → LLM-pipeline already has. The research
above is about sharpening where that boundary sits and how each layer makes
its individual decisions — not about which side of the boundary to be on.

---

## Part 4 — dead ends ruled out

**A hand-written PEG/CFG semantic grammar (à la Phoenix) as a FastRule
replacement or supplement.** Ruled out for two reasons. First, the
historical trajectory argues against it: even Stanford's 2019
grammar-centric Genie/ThingTalk system ended up using its grammar only to
*synthesize training data* for a neural parser rather than as the
production-time parser itself, because natural phrasing variance in real
usage outgrows a hand-maintained rule set — and a transformer/neural parser
is explicitly disallowed here, so we'd inherit the grammar-maintenance
burden without the escape hatch Genie used. Second, and more fundamental to
this project's design: a CFG/PEG gives a binary parses/doesn't-parse
answer, not a continuous confidence score — but FastRule's entire selective-
classifier design depends on a graded confidence signal to decide
commit-vs-abstain (the 0.80/0.60 thresholds, the multiplicative penalties).
Retrofitting confidence onto a grammar (e.g., counting which optional rules
fired) is possible but is reinventing exactly the slot-fill-fraction scoring
`_compute_confidence` already does — better to keep scoring where it is and
improve its inputs (Part 1 ideas above) than to swap the whole matching
substrate. [Genie's grammar-generates-training-data pattern](https://arxiv.org/abs/1904.09020).

**Padatious-style trained neural intent matcher.** Explicitly a small
neural network with its own model file and training pipeline — it is
described plainly as "a neural network intent parser," which this
project's constraint set rules out regardless of size ("no new heavyweight
ML models allowed... a transformer is not [acceptable]," and while
Padatious itself is pre-transformer, it still requires maintaining a
trained model artifact and a retraining loop, more machinery than the
logistic-regression-over-hand-features carve-out this project explicitly
allows). Also worth noting: Padatious is itself now described as "legacy"
within its own ecosystem, with newer Mycroft-adjacent work favoring
fuzzy-matching engines instead of neural ones for new deployments — i.e.,
even the system that built it has moved away from this choice.
[Padatious repo](https://github.com/MycroftAI/padatious), [Padatious legacy status / fuzzy-matching successor note](https://pypi.org/project/ovos-padatious/2.1.0a3/).

**Self-consistency / majority-vote sampling for the SEGMENT LLM call.**
Ruled out on two independent grounds. First, it directly conflicts with the
frozen design constraint that segmentation stays a **single**
schema-constrained call — running the same prompt 3-5 times at temperature
>0 to vote is architecturally a different (heavier) call pattern, not an
implementation detail inside the existing one. Second, even setting the
architecture constraint aside, there is direct evidence the technique is
unreliable at the model size in play here: majority-vote self-consistency
has been shown to *backfire* specifically for smaller LLMs on hard
problems, sometimes making the aggregate answer worse than a single sample
— exactly the risk category our local llama3.1:8b sits in for this task.
[When Self-Consistency Backfires: Majority Vote Hurts the Majority of Hard Science Problems for Small LLMs](https://arxiv.org/html/2608.11403).

**Phonetic matching (Double Metaphone/Soundex) as the primary technique for
target resolution, rather than a secondary tie-break.** Ruled out as the
*primary* mechanism, kept only as a fallback (Part 1 idea 5), because our
targets arrive as text already transcribed by Whisper, not as raw audio —
most of the errors at this stage are letter-level transcription slips and
truncated/misquoted spans, which edit-distance-family matching (already the
established, dependency-free pattern in this codebase via `vocab.py`)
handles directly. Phonetic matching's actual value proposition is names
that sound alike but have very different spelling/edit-distance (their own
canonical example: Jean vs. Gene) — a narrower, secondary case, not the
common one, so it's additive rather than a replacement.
[Double Metaphone's specific value over edit distance](https://support.syniti.com/hc/en-us/articles/5875511093783-Fact-4-Conventional-Matching-Algorithms-Here-is-what-you-need-to-know).

**A fully trained per-intent CRF slot filler (replicating Snips exactly),
rather than a hand-feature scorer.** Ruled out at the effort/benefit ratio
for our scale. Snips' own justification for CRFs over deep learning was "no
significant gain" at *their* scale (a general-purpose assistant with many
intents and a large training corpus) — our corpus is a few thousand rows
over a handful of intents, meaningfully smaller, and a trained CRF still
requires a labeled-sequence training pipeline and a model file to version
and retrain, which is disproportionate machinery next to a hand-feature
logistic scorer built directly on spaCy's already-computed POS/dependency
output (Part 1 idea 8) that captures the same "local features vote on slot
membership" idea at a fraction of the engineering cost.
[Snips NLU architecture / CRF design rationale](https://medium.com/snips-ai/an-introduction-to-snips-nlu-the-open-source-library-behind-snips-embedded-voice-platform-b12b1a60a41a).

**Two separate LLM calls for the SEGMENT stage ("count first, extract
second").** Ruled out directly — it violates the frozen "ONE
schema-constrained LLM call" contract for this stage. Folded the useful
part of the idea (commit to a count before/alongside extraction) into
Part 2 idea 3 instead, which gets the same self-anchoring benefit from a
**deterministic** pre-computed count fed into the single existing call,
rather than a second model invocation.

**Full sentence-boundary retraining / fine-tuning any local model on
segmentation data.** Not seriously considered — training or fine-tuning a
model is explicitly out of scope ("no new heavyweight ML models allowed")
and unnecessary here: every SEGMENT idea above either stays purely
deterministic (spaCy dependency parse, entity merges, cue-word tiers) or
changes the *schema and grounding* of the existing single prompt call
rather than the model itself.
