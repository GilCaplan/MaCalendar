"""Shared LLM transport for engine stages — infrastructure, not a stage.

Stages must not import each other's internals, but they all speak to the same
local model. This module is the one sanctioned door (documented in
DOCUMENTATION/ENGINE.md alongside state.py): a schema-constrained JSON call,
grounded on whatever the caller passes, riding the exact per-provider paths
`IntentParser` already maintains — no second HTTP client to drift.

Every call is loopback-only by construction (the parser's transports are), so
tests/unit/test_offline.py keeps holding.
"""

from __future__ import annotations

import json

_parser = None


def _get_parser(cfg):
    global _parser
    if _parser is None:
        from assistant.engine.generate.generate import get_registry
        from assistant.intent.parser import IntentParser
        _parser = IntentParser(cfg, get_registry())
    return _parser


def reset() -> None:
    global _parser
    _parser = None


def call_json(cfg, system: str, user: str, schema: "dict | None" = None) -> "tuple[dict, int]":
    """One structured-output call. Returns (parsed dict, elapsed ms).

    With a schema and Ollama, the model is format-constrained (it CANNOT emit
    malformed JSON, only wrong content); other engines fall back to the
    free-JSON path. Raises AssistantError subclasses on transport failure —
    the caller decides whether that skips the stage or fails the command.
    """
    import os
    import time

    if os.environ.get("MACALENDAR_LLM_DISABLED") == "1":
        from assistant.exceptions import OllamaUnavailableError
        raise OllamaUnavailableError("engine LLM calls are disabled (MACALENDAR_LLM_DISABLED)")
    parser = _get_parser(cfg)
    t0 = time.perf_counter()
    if schema is not None and cfg.llm_engine == "ollama":
        raw = parser._call_ollama(system, user, schema)
        out = json.loads(parser._extract_json(raw))
    else:
        out = parser.call_llm_json(system, user)
    return out, int((time.perf_counter() - t0) * 1000)
