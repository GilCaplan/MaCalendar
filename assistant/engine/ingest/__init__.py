"""Ingest — everything between "what Whisper wrote" and "words worth parsing".

    coalesce.py   several queued recordings -> ONE input
    repair.py     vocabulary fixes, false starts, uncertain words

See ARCHITECTURE.md.
"""
from assistant.engine.ingest import repair                  # noqa: F401
from assistant.engine.ingest.coalesce import coalesce       # noqa: F401
