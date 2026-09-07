"""FastRule — the deterministic rule parser as a self-contained, thresholded
SELECTIVE CLASSIFIER: instantiate with a confidence bar and (optionally) a
reduced gate set; `.run(prompt)` returns a commit-or-abstain verdict.

Two live instances, tuned for their populations (see generate.py):
  FastRule(0.80)                      the whole-command fast track —
                                      conservative; the deep track is its net.
  FastRule(0.60)                      per-fragment inside the deep track —
                                      aggressive; crosscheck is its net.

The abstention gates ALWAYS run — on a fragment they double as the atomicity
check: a fragment that still trips the compound gate is one decompose did
NOT fully break down, so FastRule abstains with reason "strong-compound" /
"mixed-mode-compound" and the caller routes it for further breakdown (or the
LLM). Safe on real fragments because the strong-compound regex keys on true
joiners ("and then", ". also", "— and"), never a bare conjunction. The two
instances differ ONLY in their confidence threshold.

All abstention gates live here in ONE place, so both instances behave
identically and the sandbox can iterate the class directly instead of
threading an EngineState. Behaviour is exactly the old fast_propose — this
is an encapsulation refactor, verified by identical sandbox numbers.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Gate regexes live with the class now (moved from generate.py).
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


class FastRule:
    def __init__(self, threshold: float):
        self.threshold = float(threshold)

    def run(self, text: str, current_view: str = "month") -> FastRuleResult:
        from assistant.engine.generate import _get_rule_parser
        from assistant.intent.rule_parser import RuleParserSkip
        parser = _get_rule_parser()
        if parser is None:
            return FastRuleResult(False, [], 0.0, "no-parser")
        try:
            rr = parser.analyze(text, current_view=current_view)
        except RuleParserSkip as e:
            return FastRuleResult(False, [], 0.0, f"skip:{e}")
        except Exception as e:                      # a fast-path bug loses no command
            return FastRuleResult(False, [], 0.0, f"error:{e}")

        conf = float(rr.confidence)
        intents = rr.intents

        # --- abstention gates (always on; on a fragment they double as the
        # "is this atomic, or does it need more breakdown?" check) ---
        if len(intents) <= 1 and _STRONG_COMPOUND_RE.search(text):
            # not atomic — decompose (or the caller) should split further
            return FastRuleResult(False, intents, conf, "strong-compound")
        if len(intents) <= 1 and " and " in text.lower():
            # F5 (research-backed): the cue-word regex only knows announced
            # joiners ("and then/also/plus…"); a plain "and" joining two
            # CLAUSES swallows a second ask silently. The dependency parse
            # tells clause- from NP-coordination ("Tal and Sam" never
            # splits) — see intent/coordination.py for the rule and its
            # measured limits.
            from assistant.intent.coordination import has_clause_coordination
            if has_clause_coordination(text):
                return FastRuleResult(False, intents, conf, "clause-coordination")
        if (len(intents) >= 2 and _STRONG_COMPOUND_RE.search(text)
                and any(n.startswith("create_") for n, _ in intents)
                and any(n.startswith(("update_", "delete_", "complete_", "query_"))
                        for n, _ in intents)):
            return FastRuleResult(False, intents, conf, "mixed-mode-compound")
        if (_INTERROGATIVE_RE.search(text)
                and not _POLITE_IMPERATIVE_RE.search(text)
                and any(n.startswith("create_") for n, _ in intents)):
            return FastRuleResult(False, intents, conf, "interrogative-create")
        for name, intent in intents:
            if name.startswith(("update_", "delete_", "complete_")):
                target = str(getattr(intent, "match_title", "") or "").strip()
                if _GENERIC_TARGET_RE.match(target):
                    return FastRuleResult(False, intents, conf, f"generic-target:{target}")

        if conf >= self.threshold and not rr.missing_slots and intents:
            return FastRuleResult(True, intents, conf, None)
        return FastRuleResult(
            False, intents, conf,
            "below-threshold" if conf < self.threshold else "missing-slots",
            missing_slots=list(rr.missing_slots) or None)
