"""Base classes for the action plugin system."""

from abc import ABC, abstractmethod
from typing import Any, ClassVar, Optional, Type

from pydantic import BaseModel


class BaseIntent(BaseModel):
    """Every action defines a BaseIntent subclass with its own fields."""
    pass


class BaseAction(ABC):
    """
    Base class for all action plugins.

    To add a new action:
    1. Create assistant/actions/<name>/
    2. Define an IntentModel(BaseIntent) with the fields you need
    3. Define an Action(BaseAction) with @register
    4. Import it in assistant/actions/<name>/__init__.py
    5. Add `import assistant.actions.<name>` in main.py

    That's it — no changes to core pipeline code.
    """

    # Every subclass MUST declare these at class level.
    action_name: ClassVar[str]
    description: ClassVar[str]
    intent_model: ClassVar[Type[BaseIntent]]
    # JSON Schema fragment describing the 'parameters' object.
    # Used in the Ollama system prompt to teach the LLM what fields to emit.
    parameters_schema: ClassVar[dict]
    # Optional: set to a status string (e.g. "switch_today") to signal the UI
    # to perform a view switch after this action executes.
    view_switch: ClassVar[Optional[str]] = None

    @abstractmethod
    def execute(self, intent: BaseIntent, config: Any) -> str:
        """
        Perform the action. Returns a human-readable TTS confirmation string.
        Raises AssistantError subclasses on failure.
        """
        ...
