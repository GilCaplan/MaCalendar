"""Routing fallthrough — the call site's thin face over `classifier.ROUTER`.

The models, their features, the fit and the margin floors all live in
`assistant/intent/classifier.py` (one object each, Gil 2026-09-07). This
module exists only so `rule_parser` has a stable, obvious import at the
place where the rules tier gives up:

    from assistant.intent import route_models
    guessed = route_models.route(span_text)     # None => defer, as before

A model-routed action is an INFERENCE and is billed like one — the caller
returns it through the domain-inferred (×0.85) channel, so FastRule's
threshold still guards every commit.
"""
from __future__ import annotations

from assistant.intent.classifier import ROUTER


def route(text: str) -> "str | None":
    """The composed action, or None when either model isn't decisive."""
    return ROUTER.route(text)
