"""Decompose · Validate — one folder, two functions kept separate (Gil).

`validate` still runs TWICE: a text pass before generate, and `run_objects`
after it, because its date rules need `item.intent` to exist.
See ARCHITECTURE.md.
"""
from assistant.engine.decompose_validate import decompose, validate  # noqa: F401
