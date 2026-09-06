"""FastRule — the deterministic rule parser as a self-contained, thresholded
SELECTIVE CLASSIFIER: instantiate with a confidence bar and (optionally) a
reduced gate set; `.run(prompt)` returns a commit-or-abstain verdict.

Two live instances, tuned for their populations (see generate.py):
  FastRule(0.80)                      the whole-command fast track —
                                      conservative; the deep track is its net.
  FastRule(0.60, compound_gates=False) per-fragment inside the deep track —
                                      aggressive; a fragment is post-decompose
                                      and atomic, so the compound-splitting
                                      gates don't apply; crosscheck is its net.

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
    def __init__(self, threshold: float, *, compound_gates: bool = True):
        self.threshold = float(threshold)
        self.compound_gates = compound_gates

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

        # --- abstention gates, order preserved from the old fast_propose ---
        if self.compound_gates:
            if len(intents) <= 1 and _STRONG_COMPOUND_RE.search(text):
                return FastRuleResult(False, intents, conf, "strong-compound")
            if (len(intents) >= 2 and _STRONG_COMPOUND_RE.search(text)
                    and any(n.startswith("create_") for n, _ in intents)
                    and any(n.startswith(("update_", "delete_", "complete_", "query_"))
                            for n, _ in intents)):
                return FastRuleResult(False, intents, conf, "mixed-mode-compound")
            if (_INTERROGATIVE_RE.search(text)
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
