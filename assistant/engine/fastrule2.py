"""FastRule v2 — the Q11 restructure (Gil-approved 2026-09-07).

The organizing idea: every judgment is the same tiered decision — rules
when confident, a tiny model when they can't, DEFER when neither is sure —
applied three times (atomic? which operation? which kind?). FastRule is the
ATOMIC-ITEM EXECUTOR; the deep system is the ATOMIZER (Gil's framing:
"the deep system's main idea is breaking down to atomic items so the
FastRule can then create the right event/task per item").

v2.0 is the IDENTICAL-BEHAVIOR port (the Q7 lesson): the components exist
as named seams, every regex and check is v1's own (imported, so drift is
impossible), and the flow order is preserved exactly. The deltas the
structure is FOR — pre-parse atomicity, split-and-recurse, calibrated
Scorer signals, slot-specs-as-data — land as later measured batches.

    FastRule(threshold).run(text) -> FastRuleResult      # unchanged contract

    parse       — Normalizer+Router+SlotFiller, currently the composite
                  inside rule_parser.analyze() (extraction into separate
                  components is v2.x; the ROUTER's two-subsystem tier —
                  rules then models — already lives at rule_parser's
                  route fallthrough per Q10)
    Atomicity   — layer 0 (Gil): the compound gates. Runs post-parse in
                  v2.0 because v1's gates read the intent count ("buy milk
                  and buy bread" parses as TWO intents and rightly
                  commits; only a single-intent parse of compound wording
                  defers).
    Gatekeeper  — the intent-level vetoes (interrogative→defer,
                  rename-misroute, generic-target), v1 order preserved.
    Scorer      — the commit predicate (threshold + missing slots) and the
                  named-signal registry (documented here; refitting them is
                  R2's one-place job once calibration runs).
"""
from __future__ import annotations

# v1's own patterns and result type — imported, not copied, so v2.0 cannot
# drift from the behavior it ports. When v1 retires, these move here.
from assistant.engine.fastrule import (  # noqa: F401
    FastRuleResult,
    _GENERIC_TARGET_RE,
    _INTERROGATIVE_RE,
    _POLITE_IMPERATIVE_RE,
    _STRONG_COMPOUND_RE,
)
import re


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


class Atomicity:
    """Layer 0 (Gil): is this ONE atomic item? Rules tier = the compound
    gates, verbatim v1 semantics. Model tier (the atomicity logistic on
    dataset B's atomic flags) is a later measured batch."""

    def judge(self, text: str, intents) -> "str | None":
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
        if reason:
            return FastRuleResult(False, rr.intents, float(rr.confidence), reason)
        reason = self.gatekeeper.judge(text, rr.intents)
        if reason:
            return FastRuleResult(False, rr.intents, float(rr.confidence), reason)
        if self.scorer.commits(rr):
            return FastRuleResult(True, rr.intents, float(rr.confidence), None)
        # v1's reason precedence: below-threshold outranks missing-slots
        if rr.confidence < self.threshold:
            return FastRuleResult(False, rr.intents, float(rr.confidence),
                                  "below-threshold",
                                  missing_slots=list(rr.missing_slots) or None)
        return FastRuleResult(False, rr.intents, float(rr.confidence),
                              "missing-slots",
                              missing_slots=list(rr.missing_slots) or None)
