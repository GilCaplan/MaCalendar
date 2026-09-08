"""FastRule — the ATOMIC-ITEM EXECUTOR, and the stage that uses it.

    stage.py     the STAGE: X3 items -> X4 objects ready to commit
    objects.py   per-item object building (FastRule first, model as fallback)
    fastrule.py  the FastRule class itself — rules, gates, scorer

See ARCHITECTURE.md for the tiered decision and what a DEFER verdict obliges.
"""
from assistant.engine.fastrule import fastrule      # noqa: F401
