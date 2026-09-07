"""FastRule v2 — the Q11 restructure (Gil-approved 2026-09-07).

The organizing idea: every judgment is the same tiered decision — rules
when confident, a tiny model when they can't, DEFER when neither is sure —
applied three times (atomic? which operation? which kind?). FastRule is the
ATOMIC-ITEM EXECUTOR; the deep system is the ATOMIZER (Gil's framing:
"the deep system's main idea is breaking down to atomic items so the
FastRule can then create the right event/task per item").

This file IS FastRule now. v1 is retired (2026-09-07, Gil) — its code is
kept at `retired/fastrule-v1/` and the last commit that ran it is tagged
`fastrule-v1`. The switch was an IDENTICAL-BEHAVIOR port (the Q7 lesson):
every regex and check came over unchanged and a diff harness proved 7,200 /
7,200 verdicts identical before v1 was stood down. The deltas the
structure is FOR — pre-parse atomicity, split-and-recurse, calibrated
Scorer signals, slot-specs-as-data — land as later measured batches.

    FastRule(threshold).run(text) -> FastRuleResult      # unchanged contract

    parse       — Normalizer+Router+SlotFiller, currently the composite
                  inside rule_parser.analyze() (extraction into separate
                  components is v2.x; the ROUTER's two-subsystem tier —
                  rules then models — already lives at rule_parser's
                  route fallthrough per Q10)
    Atomicity   — layer 0 (Gil): one item or several. Rules OR model, both
                  unconditional (F16). It answers only that question; what
                  routing does about a compound is `run`'s business, via
                  `_parse_covers_the_compound` — v1 had the two fused, and
                  the fusion cost the layer half its recall.
    Gatekeeper  — the intent-level vetoes (interrogative→defer,
                  rename-misroute, generic-target), v1 order preserved.
    Scorer      — the commit predicate (threshold + missing slots) and the
                  named-signal registry (documented here; refitting them is
                  R2's one-place job once calibration runs).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

#: `_parse_covers_the_compound` counts asks with the intent layer's joiner
#: pattern — the same one `AtomicityFeatures`' joiner-mid signal reads, so
#: routing and the model can never disagree about where a sentence divides.
from assistant.intent.coordination import ASK_JOINER_RE as _ASK_JOINER_RE

# The gate patterns and the verdict type (carried from v1 at retirement).
_STRONG_COMPOUND_RE = re.compile(
    r"\band\s+(?:then|also)\b"
    r"|[.;!?]\s+(?:also|then|plus|and)\b"
    r"|\s[—–]\s*and\b"
    r"|,\s*then\b",
    re.I)

_GENERIC_TARGET_RE = re.compile(
    r"^(?:my |the |a |an |this )?(?:reminder|alert|event|appointment|task|todo|list)s?$"
    r"|^(?:you|it|me|this|that|them)$",
    re.I)

# "Can you create/add/make …" is a polite imperative, not a question —
# the speaker wants the thing made (F4a; "Can you create a new list in my
# podcast?" was gate-blocked despite a correct create parse).
_POLITE_IMPERATIVE_RE = re.compile(
    r"^\s*(?:hey\s+\w+,?\s*)?(?:can|could|would|will)\s+you\s+(?:please\s+)?"
    r"(?:create|add|make|set|put|start|book|schedule|remind)\b", re.I)

_INTERROGATIVE_RE = re.compile(
    r"^\s*(?:hey\s+\w+,?\s*)?(?:who|what|when|where|which|whose|how|do|does|did|is|are|am|can|could|would|will|should)\b"
    r"|\bcould you (?:tell|let me know|check)\b|\bdo i have\b|\?\s*$",
    re.I)


@dataclass
class FastRuleResult:
    """A FastRule verdict. `committed` True ⇒ take `intents` on the fast
    track; False ⇒ defer to the deep track, `reason` says why."""
    committed: bool
    intents: list          # [(action_name, intent)]
    confidence: float
    reason: str | None = None      # None when committed; else the abstain cause
    missing_slots: list | None = None
    #: the raw RuleParseResult, so a caller handing off to the LLM can pass
    #: what the rules DID manage to read instead of starting from zero
    rule_result: object | None = None


#: The Scorer's signal registry — every confidence penalty, named. The
#: VALUES still live where they always did (rule_parser applies them during
#: parsing); this table is the single place that lists them, and the target
#: of R2's calibration refit. Keep in sync with rule_parser (test-pinned).
CONFIDENCE_SIGNALS = {
    "regex_date": 0.95,        # date came from regex, not the recognizer
    "domain_guessed": 0.85,    # domain inferred from the open view / model-routed
    "anaphora": 0.80,          # resolved "it"/"that one" to a past record
    "two_clock_times": 0.70,   # two times in one span — probably two events
}


#: What a deferral MEANS — the contract the deep track branches on.
#: Before this, every reason read the same downstream ("you deal with it"),
#: so the deep track re-read the raw text with the gates off and re-committed
#: things the front door had refused. The three classes want three different
#: handoffs.
REFUSAL = "refusal"        # correct reading, must not execute as stated:
                           # the deep track may RESOLVE the objection
                           # (anaphora → a real target) but never ignore it
INCAPACITY = "incapacity"  # "I couldn't read this" — the LLM should take over
STRUCTURE = "structure"    # "this is more than one item" — atomize, then
                           # hand each atom back to FastRule

_REASON_CLASS = {
    "generic-target": REFUSAL,
    "rename-misroute": REFUSAL,
    "interrogative-create": REFUSAL,
    "strong-compound": STRUCTURE,
    "clause-coordination": STRUCTURE,
    "mixed-mode-compound": STRUCTURE,
    "model-compound": STRUCTURE,
    "below-threshold": INCAPACITY,
    "missing-slots": INCAPACITY,
    "skip": INCAPACITY,
    "error": INCAPACITY,
    "no-parser": INCAPACITY,
}


def reason_class(reason: "str | None") -> "str | None":
    """The class of a deferral reason — None when it committed."""
    if not reason:
        return None
    return _REASON_CLASS.get(reason.split(":")[0], INCAPACITY)


class Atomicity:
    """Layer 0 (Gil): is this ONE atomic item, or several?

    Two tiers, and since F16 they are a UNION rather than a fallback chain:
    the gates read announced joiners and the dependency parse, the logistic
    reads the utterance's shape, and each catches compounds the other has no
    cue for. Scored on its own board — `scripts/atomicity_board.py`.
    """

    def rule_verdict(self, text: str, intents) -> "str | None":
        """The rules tier alone — the three gates, v1 semantics verbatim.

        Extracted from `judge` so the board
        (`scripts/atomicity_board.py`) can score rules, model and the wired
        layer as three separate predictors: when the layer scores worse than
        its own model, the WIRING is the bug, and only separate lines show
        that.
        """
        if len(intents) <= 1 and _STRONG_COMPOUND_RE.search(text):
            return "strong-compound"
        if len(intents) <= 1 and " and " in text.lower():
            from assistant.intent.coordination import has_clause_coordination
            if has_clause_coordination(text):
                return "clause-coordination"
        if (len(intents) >= 2 and _STRONG_COMPOUND_RE.search(text)
                and any(n.startswith("create_") for n, _ in intents)
                and any(n.startswith(("update_", "delete_", "complete_", "query_"))
                        for n, _ in intents)):
            return "mixed-mode-compound"
        return None

    def judge(self, text: str, intents) -> "str | None":
        """The MODEL LEADS; the rule gates are overrides for their own
        catches (F16, measured).

        Until F16 the model was a last resort behind `len(intents) <= 1`,
        and the layer scored WORSE than the model it contained — B-test
        compound recall 68.8% for the layer vs 83.4% for the model alone.
        110 of the layer's 195 misses there were one guard clause: rows the
        rule parser had split into ≥2 intents, every one of them compound,
        which the layer answered "atomic" for without ever asking the model.
        That guard was an EXECUTION judgement ("two intents parsed, so both
        can be run") wearing an ATOMICITY answer's clothes. Execution is the
        Scorer's business; this method answers one question only.

        So: rules OR model, both unconditional. The rules keep their own
        reason strings (a defer that names `strong-compound` is a different
        diagnosis from one that names `model-compound`, and the shape board
        splits on exactly that), and they still fire where the model is not
        decisive — the model reads the utterance's shape, the gates read an
        announced joiner and the dependency parse.
        """
        reason = self.rule_verdict(text, intents)
        if reason:
            return reason
        from assistant.intent.classifier import ROUTER
        if ROUTER.looks_compound(text):
            return "model-compound"
        return None


def _parse_covers_the_compound(reason: str, text: str, intents) -> bool:
    """Is this a compound the parse ALREADY answers in full? (F16)

    Layer 0 says "several items"; that is a fact about the sentence. What to
    DO about it is a routing question, and the answer is not always "defer":
    when the rule parser has itself read two requests and produced an intent
    for each, FastRule is not half-executing a two-ask command — it is
    executing all of it. Deferring there throws a complete, correct answer
    away, and with no LLM reachable it throws away the ONLY answer: measured
    2026-09-07, "book gym on tuesday at 7am and remind me to buy milk"
    routed to the deep track produces nothing at all when Ollama is down,
    where the fast track produced both records.

    So the carve-out is narrow and named, and it lives HERE — in routing —
    instead of inside the atomicity answer, which is where it used to hide
    (as `len(intents) <= 1` guarding the model tier) and where it cost the
    layer 110 of its 195 B-test misses.

    The RULE verdicts are never carved out: `strong-compound`,
    `clause-coordination` and `mixed-mode-compound` name a specific structure
    the gates recognised, and `mixed-mode-compound` in particular fires only
    on ≥2 intents already. Only `model-compound` — the shape classifier's
    opinion, which has no view of what the parse recovered — yields to a
    parse that covers the ask.

    "Covers" is not "≥2 intents". B-train mining (2026-09-07): of 381
    compound rows committed on a ≥2-intent parse, 276 covered the ask and
    **105 did not — and 80% of those 105 were THREE-ask families** where the
    parse found two intents and dropped the third ("book flu shot this
    morning, training session the 3rd, and remind me to …" → one event, one
    task, one ask lost). Those are the real half-executions. So the parse
    must produce at least as many intents as the sentence's joiners announce
    asks, which is the one thing that separates the two piles.
    """
    if reason != "model-compound" or len(intents) < 2:
        return False
    return len(intents) >= 1 + len(_ASK_JOINER_RE.findall(text))


class Gatekeeper:
    """Intent-level vetoes, v1 order: interrogative (with the polite
    exemption), rename-misroute, generic-target."""

    def judge(self, text: str, intents) -> "str | None":
        if (_INTERROGATIVE_RE.search(text)
                and not _POLITE_IMPERATIVE_RE.search(text)
                and any(n.startswith("create_") for n, _ in intents)):
            return "interrogative-create"
        if (re.match(r"^\s*(?:please\s+)?rename\b", text, re.I)
                and any(n.startswith("create_") for n, _ in intents)):
            return "rename-misroute"
        for name, intent in intents:
            if name.startswith(("update_", "delete_", "complete_")):
                target = str(getattr(intent, "match_title", "") or "").strip()
                if _GENERIC_TARGET_RE.match(target):
                    return f"generic-target:{target}"
        return None


class Scorer:
    """The commit predicate: confident AND clean. (Signal VALUES are applied
    during parsing; see CONFIDENCE_SIGNALS for the registry.)"""

    def __init__(self, threshold: float) -> None:
        self.threshold = threshold

    def commits(self, rr) -> bool:
        return (rr.confidence >= self.threshold
                and not rr.missing_slots and bool(rr.intents))


class FastRule:
    """The atomic-item executor, v2 structure — v1 behavior."""

    def __init__(self, threshold: float) -> None:
        self.threshold = threshold
        self.atomicity = Atomicity()
        self.gatekeeper = Gatekeeper()
        self.scorer = Scorer(threshold)

    def run(self, text: str, current_view: str = "month") -> FastRuleResult:
        from assistant.engine import generate as _generate
        from assistant.intent.rule_parser import RuleParserSkip

        rp = _generate._get_rule_parser()
        if rp is None:
            return FastRuleResult(False, [], 0.0, "no-parser")
        try:
            rr = rp.analyze(text, current_view=current_view)
        except RuleParserSkip as e:
            return FastRuleResult(False, [], 0.0, f"skip:{e}")
        except Exception as e:
            return FastRuleResult(False, [], 0.0, f"error:{e}")

        reason = self.atomicity.judge(text, rr.intents)
        # both halves of the merge: the coverage carve-out (a compound the
        # parse fully covers may still commit — Gil's Q13 "easy enough to
        # complete", and the only path that survives the LLM being down)
        # AND the raw parse riding along so the deep track inherits the work
        if reason and not _parse_covers_the_compound(reason, text, rr.intents):
            return FastRuleResult(False, rr.intents, float(rr.confidence), reason,
                                  rule_result=rr)
        reason = self.gatekeeper.judge(text, rr.intents)
        if reason:
            return FastRuleResult(False, rr.intents, float(rr.confidence), reason,
                                  rule_result=rr)
        if self.scorer.commits(rr):
            return FastRuleResult(True, rr.intents, float(rr.confidence), None,
                                  rule_result=rr)
        # v1's reason precedence: below-threshold outranks missing-slots
        if rr.confidence < self.threshold:
            return FastRuleResult(False, rr.intents, float(rr.confidence),
                                  "below-threshold",
                                  missing_slots=list(rr.missing_slots) or None,
                                  rule_result=rr)
        return FastRuleResult(False, rr.intents, float(rr.confidence),
                              "missing-slots",
                              missing_slots=list(rr.missing_slots) or None,
                              rule_result=rr)
