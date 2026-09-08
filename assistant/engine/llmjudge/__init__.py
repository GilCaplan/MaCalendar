"""See ARCHITECTURE.md. The package exposes the stage module; callers that
need the module (attribute access, monkeypatching) import it directly:

    from assistant.engine.llmjudge import llmjudge
"""
from assistant.engine.llmjudge import llmjudge    # noqa: F401
