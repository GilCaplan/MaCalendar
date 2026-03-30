# Importing CreateEventAction triggers the @register decorator,
# which registers this action with the global ActionRegistry.
# main.py does `import assistant.actions.calendar` to activate this plugin.
from assistant.actions.calendar.action import CreateEventAction

__all__ = ["CreateEventAction"]
