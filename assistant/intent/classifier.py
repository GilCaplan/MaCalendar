"""Small trainable components, as objects (Gil, 2026-09-07: "any model or
component should be its own object, especially if it's something redundant").

Before this module the same logistic regression existed FOUR times — in
route_models, fit_route_models and both experiment scripts — each with its
own copy of the featurizers, the gradient loop and the scoring. One
divergence between copies is a silent bug, so there is now exactly one of
each thing:

    Featurizer          .extract(text) -> [float];  .names for reporting
      OperationFeatures   new / edit / remove / complete / query signals
      KindFeatures        event / task signals
    LogisticModel       one-vs-rest logistic: .fit .predict .scores
                        .evaluate (per-class P/R/F1 + macro) .to_dict/.load
    ModelRouter         the two classifiers + their margin floors; the
                        routing fallthrough the rules tier calls

Fitting uses scikit-learn when available (better optimizer, real
regularization, proper class weights) with a pure-python fallback; INFERENCE
is always a hand-written dot product over a list of floats, because these
models run inside FastRule where the whole budget is ~50 ms and the shipped
engine carries no ML dependency. The trained artifact is just JSON weights.
"""
from __future__ import annotations

import json
import math
import pathlib
import re


# ---------------------------------------------------------------------------
# Featurizers
# ---------------------------------------------------------------------------

class Featurizer:
    """Turns text into a fixed vector of named signals."""

    names: "list[str]" = []

    def extract(self, text: str) -> "list[float]":  # pragma: no cover
        raise NotImplementedError

    def __len__(self) -> int:
        return len(self.names)


def _has(pattern: str, text: str) -> float:
    return 1.0 if re.search(pattern, text) else 0.0


class OperationFeatures(Featurizer):
    """Signals for new / edit / remove / complete / query."""

    names = ["bias", "create-verb", "remind-speak", "delete-verb", "from-my",
             "edit-verb", "to-when", "done-speak", "query-opener", "my-schedule",
             "qmark", "clock", "priority", "rename-speak", "recur", "buy-verb",
             "remove-speak2", "query-opener2", "availability", "cross-off",
             "done-query"]

    def extract(self, text: str) -> "list[float]":
        low = text.lower()
        h = lambda p: _has(p, low)          # noqa: E731
        return [
            1.0,
            h(r"^\s*(?:add|book|schedule|create|put|set up|plan|make|new)\b"),
            h(r"\b(?:remind me|need to|have to|remember to|don'?t forget)\b"),
            h(r"^\s*(?:delete|remove|cancel|drop|clear|erase|scratch)\b"),
            h(r"\bfrom\s+(?:my|the)\b"),
            h(r"^\s*(?:move|reschedule|change|update|push|shift|postpone|rename|extend|shorten)\b"),
            h(r"\bto\s+(?:\d|noon|midnight|next|this|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b"),
            h(r"\b(?:as\s+)?(?:done|complete[d]?|finished)\b|\bcheck(?:ed)?\s+off\b|\balready did\b|\bi'?m done\b"),
            h(r"^\s*(?:what|which|when|show|list|tell me|do i have|how many|is there|what'?s)\b"),
            h(r"\bmy (?:schedule|day|week|agenda|calendar)\b"),
            h(r"\?\s*$"),
            h(r"\bat\s+\d|(?:\d|\b)(?:am|pm)\b"),
            h(r"\bas\s+(?:high|medium|low)\s+priority\b"),
            h(r"\binstead of\b|\bcall it\b|\brename\b"),
            h(r"\bevery\b|\bdaily\b|\bweekly\b"),
            h(r"^\s*(?:buy|get|pick up|grab|order)\b"),
            h(r"\boff\s+(?:my|the)\b|\bget rid of\b|\bno longer\b|\bwipe\b|\bstrike\b"),
            h(r"^\s*(?:am i free|is there|any(?:thing)?\b|do i\b|have i\b)"),
            h(r"\bfree\b|\bbusy\b|\bavailable\b|\bcoming up\b|\bplanned\b"),
            h(r"^\s*(?:cross|take)\s+.+\s+off\b"),
            h(r"\bdid i\b|\bhave i\s+(?:done|finished)\b"),
        ]


class KindFeatures(Featurizer):
    """Signals for event vs task."""

    names = ["bias", "clock", "dated", "remindish", "remind-to-verb", "occasion",
             "list-words", "buy-verbs", "calendar-words", "with-name", "recur",
             "long", "activity-noun", "at-num", "chore-noun", "for-me"]

    def extract(self, text: str) -> "list[float]":
        low = text.lower()
        h = lambda p: _has(p, low)          # noqa: E731
        return [
            1.0,
            h(r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b|\bat\s+\d{1,2}\b|\b(?:noon|midnight|tonight|morning|evening|afternoon)\b"),
            h(r"\b(?:today|tomorrow|tonight)\b|\b(?:next|this|on)\s+(?:week|month|monday|tuesday|wednesday|thursday|friday|saturday|sunday|weekend)\b"),
            h(r"\bremind(?:er)?s?\b|\bnotify\b"),
            h(r"\bremind\s+\w+\s+to\b"),
            h(r"\b(?:meeting|appointment|party|dinner|lunch|brunch|breakfast|birthday|anniversary|wedding|concert|interview|class|lesson|conference|session|call)\b"),
            h(r"\b(?:list|to-?do|task|shopping)\b"),
            h(r"\b(?:buy|get|pick up|purchase|groceries)\b"),
            h(r"\b(?:calendar|schedule|book|invite)\b"),
            h(r"\bwith\s+[a-z]+\b"),
            h(r"\bevery\b"),
            1.0 if len(text.split()) > 9 else 0.0,
            h(r"\b(?:shiur|recital|ceremony|festival|get-?together|funeral|checkup|check-?up|haircut|workout|gym|run|practice)\b"),
            h(r"\bat\s+\d{1,2}\b"),
            h(r"\b(?:errand|chore|homework|assignment|laundry|dishes|email|form|bill|report)\b"),
            h(r"\bfor\s+(?:me|us)\b|\bmy\s+(?:place|house|office)\b"),
        ]


# ---------------------------------------------------------------------------
# The model
# ---------------------------------------------------------------------------

class LogisticModel:
    """One-vs-rest logistic regression — the only copy in the codebase.

    Pure python by design (this runs inside FastRule's ~50 ms budget, and the
    product ships no ML dependency). Fitting is class-balanced by default:
    without it a 70%-majority class drowns the rest, which is exactly what
    the K3 experiment measured.
    """

    def __init__(self, name: str, classes, featurizer: Featurizer) -> None:
        self.name = name
        self.classes = tuple(classes)
        self.featurizer = featurizer
        self.weights: "dict[str, list[float]]" = {}

    # -- training (FIT TIME ONLY — see the class docstring) -----------------
    def fit(self, texts, labels, balanced: bool = True,
            C: float = 1.0, epochs: int = 300, lr: float = 0.5) -> "LogisticModel":
        """Fit with scikit-learn when it is installed (Gil: "just use the
        library version") — L-BFGS with L2 regularization and real class
        weighting beats a hand-rolled loop with a guessed learning rate. The
        pure-python fallback below keeps the fit script runnable anywhere,
        and INFERENCE never touches sklearn either way: fitting only ever
        produces a list of floats per class, which `predict` dots by hand.
        """
        X = [self.featurizer.extract(t) for t in texts]
        try:
            from sklearn.linear_model import LogisticRegression
        except ImportError:
            return self._fit_pure(X, labels, balanced, epochs, lr)
        for c in self.classes:
            y = [1 if l == c else 0 for l in labels]
            if not any(y) or all(y):
                self.weights[c] = [0.0] * len(self.featurizer)
                continue
            clf = LogisticRegression(
                C=C, max_iter=2000, solver="lbfgs", fit_intercept=False,
                class_weight="balanced" if balanced else None)
            clf.fit(X, y)
            self.weights[c] = [float(v) for v in clf.coef_[0]]
        return self

    def _fit_pure(self, X, labels, balanced, epochs, lr) -> "LogisticModel":
        """Dependency-free fallback (batch gradient descent)."""
        n, d = len(X), len(self.featurizer)
        counts = {c: max(1, sum(1 for l in labels if l == c)) for c in self.classes}
        for c in self.classes:
            wpos = (n / (2.0 * counts[c])) if balanced else 1.0
            wneg = (n / (2.0 * (n - counts[c]))) if balanced and n > counts[c] else 1.0
            y = [1 if l == c else 0 for l in labels]
            w = [0.0] * d
            for _ in range(epochs):
                g = [0.0] * d
                for xi, yi in zip(X, y):
                    z = sum(a * b for a, b in zip(w, xi))
                    p = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))
                    e = (p - yi) * (wpos if yi else wneg)
                    for j in range(d):
                        g[j] += e * xi[j]
                for j in range(d):
                    w[j] -= lr * g[j] / n
            self.weights[c] = w
        return self

    # -- inference ---------------------------------------------------------
    def scores(self, text: str) -> "dict[str, float]":
        x = self.featurizer.extract(text)
        return {c: sum(a * b for a, b in zip(w, x)) for c, w in self.weights.items()}

    def predict(self, text: str) -> "tuple[str | None, float]":
        """(label, margin) — margin is the gap to the runner-up, i.e. how
        decisive the call was. None when the model has no weights."""
        if not self.weights:
            return None, 0.0
        ranked = sorted(self.scores(text).items(), key=lambda p: -p[1])
        margin = (ranked[0][1] - ranked[1][1]) if len(ranked) > 1 else math.inf
        return ranked[0][0], margin

    # -- evaluation --------------------------------------------------------
    def evaluate(self, texts, labels) -> dict:
        """Accuracy + per-class precision/recall/F1 + macro-F1."""
        preds = [self.predict(t)[0] for t in texts]
        acc = sum(p == y for p, y in zip(preds, labels)) / len(labels) if labels else 0.0
        per, f1s = {}, []
        for c in self.classes:
            tp = sum(1 for p, y in zip(preds, labels) if p == c and y == c)
            fp = sum(1 for p, y in zip(preds, labels) if p == c and y != c)
            fn = sum(1 for p, y in zip(preds, labels) if p != c and y == c)
            P = tp / (tp + fp) if tp + fp else 0.0
            R = tp / (tp + fn) if tp + fn else 0.0
            F = 2 * P * R / (P + R) if P + R else 0.0
            per[c] = {"precision": P, "recall": R, "f1": F, "n": tp + fn}
            f1s.append(F)
        return {"accuracy": acc, "per_class": per,
                "macro_f1": sum(f1s) / len(f1s) if f1s else 0.0}

    def report(self, texts, labels, header: str = "") -> str:
        m = self.evaluate(texts, labels)
        out = [f"{header or self.name} acc {m['accuracy']:.1%} · per-class P/R/F1:"]
        for c, s in m["per_class"].items():
            out.append(f"    {c:<9} P {s['precision']:.0%}  R {s['recall']:.0%}  "
                       f"F1 {s['f1']:.0%}  (n={s['n']})")
        out.append(f"    macro-F1 {m['macro_f1']:.1%}")
        return "\n".join(out)

    # -- persistence -------------------------------------------------------
    def to_dict(self) -> dict:
        return {"classes": list(self.classes), "weights": self.weights}

    def load(self, blob: dict) -> "LogisticModel":
        self.weights = {k: list(v) for k, v in blob.get("weights", blob).items()}
        return self


# ---------------------------------------------------------------------------
# The router that composes them
# ---------------------------------------------------------------------------

class ModelRouter:
    """The routing fallthrough: OPERATION × KIND → action, but only when both
    calls are decisive (margins above their floors). Otherwise None, and the
    caller's old behavior — defer — stands."""

    COMPOSE = {
        ("new", "event"): "create_event", ("new", "task"): "create_todo",
        ("edit", "event"): "update_event", ("edit", "task"): "update_todo",
        ("remove", "event"): "delete_event", ("remove", "task"): "delete_todo",
        ("complete", "task"): "complete_todo", ("complete", "event"): "complete_todo",
        ("query", "event"): "query_schedule", ("query", "task"): "query_todos",
    }
    OPS = ("new", "edit", "remove", "complete", "query")
    KINDS = ("event", "task")
    #: floors tightened 2026-09-07 after the A-pool dual-gate caught 26 loose
    #: commits at ~77% — the models may speak only when SURE.
    OP_MARGIN_FLOOR = 2.5
    KIND_MARGIN_FLOOR = 1.5

    def __init__(self, weights_path: "pathlib.Path | None" = None) -> None:
        self.operation = LogisticModel("operation", self.OPS, OperationFeatures())
        self.kind = LogisticModel("kind", self.KINDS, KindFeatures())
        self.weights_path = weights_path or (
            pathlib.Path(__file__).with_name("route_model_weights.json"))
        self._loaded = False

    def load(self) -> bool:
        if self._loaded:
            return bool(self.operation.weights)
        try:
            blob = json.loads(self.weights_path.read_text())
            self.operation.load({"weights": blob["operation"]})
            self.kind.load({"weights": blob["kind"]})
        except Exception:
            pass
        self._loaded = True
        return bool(self.operation.weights)

    def save(self, note: str = "") -> None:
        self.weights_path.write_text(json.dumps({
            "fitted_on": note,
            "operation": self.operation.weights,
            "kind": self.kind.weights,
        }, indent=1))

    def route(self, text: str) -> "str | None":
        if not self.load():
            return None
        op, op_margin = self.operation.predict(text)
        kind, kind_margin = self.kind.predict(text)
        if op is None or kind is None:
            return None
        if op_margin < self.OP_MARGIN_FLOOR or kind_margin < self.KIND_MARGIN_FLOOR:
            return None
        return self.COMPOSE.get((op, kind))


#: process-wide instance — weights load once, lazily
ROUTER = ModelRouter()
