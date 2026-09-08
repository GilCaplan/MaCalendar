"""FastRule — the ATOMIC-ITEM EXECUTOR. See ARCHITECTURE.md.

The implementation is `fastrule.fastrule`; callers import from there directly
because several reach for module-private names (`_GENERIC_TARGET_RE`,
`_parse_covers_the_compound`), which a re-export would not carry.
"""
from assistant.engine.fastrule import fastrule       # noqa: F401
