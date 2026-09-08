"""See ARCHITECTURE.md. The package exposes the stage module; callers that
need the module (attribute access, monkeypatching) import it directly:

    from assistant.engine.label import label
"""
from assistant.engine.label import label    # noqa: F401
