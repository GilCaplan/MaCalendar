"""See ARCHITECTURE.md. The package exposes the stage module; callers that
need the module (attribute access, monkeypatching) import it directly:

    from assistant.engine.generate import generate
"""
from assistant.engine.generate import generate    # noqa: F401
