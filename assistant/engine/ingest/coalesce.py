"""Ingest, half two: several queued commands become ONE input.

Extracted from the orchestrator so that both halves of ingest — the queue and
the word repair — live together. Behaviour is unchanged; `test_engine_flow.py`
pins the budget, the overflow and the single-input case.
"""
from __future__ import annotations


def coalesce(texts: "list[str]", max_tokens: int = 300) -> "list[str]":
    """Queued inputs combined into ("…")and("…") batches up to a token budget
    (≈4 chars/token), so several short queued commands cost one parse instead
    of several; overflow runs in later batches. The wrapper is deterministic
    for segmentation to split — each command's logic stays independent."""
    batches: list[str] = []
    current: list[str] = []
    used = 0
    for text in texts:
        t = (text or "").strip()
        if not t:
            continue
        cost = max(1, len(t) // 4)
        if current and used + cost > max_tokens:
            batches.append(_wrap(current))
            current, used = [], 0
        current.append(t)
        used += cost
    if current:
        batches.append(_wrap(current))
    return batches


def _wrap(parts: "list[str]") -> str:
    if len(parts) == 1:
        return parts[0]
    return "and".join(f'("{p}")' for p in parts)
