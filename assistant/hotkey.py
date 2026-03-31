"""Global keyboard shortcut listener using pynput."""

from __future__ import annotations

import logging
import threading
from typing import Callable, Set

from pynput import keyboard

from assistant.config import HotkeyConfig

logger = logging.getLogger(__name__)

_MODIFIER_MAP = {
    "cmd": {keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r},
    "shift": {keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r},
    "ctrl": {keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r},
    "alt": {keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r},
}


def _parse_trigger_key(key_str: str) -> keyboard.Key | keyboard.KeyCode:
    """Convert a config key string (e.g. 'space', 'a') to a pynput key."""
    # Check named keys first (space, enter, tab, etc.)
    try:
        return keyboard.Key[key_str]
    except KeyError:
        pass
    # Single character
    if len(key_str) == 1:
        return keyboard.KeyCode.from_char(key_str)
    raise ValueError(f"Unknown key: '{key_str}'")


class HotkeyListener:
    """
    Listens for a global keyboard shortcut and calls a callback.
    Runs in a daemon thread so it doesn't block the main thread.
    """

    def __init__(self, config: HotkeyConfig, callback: Callable[[], None]) -> None:
        self.callback = callback
        self._trigger_key = _parse_trigger_key(config.key)
        self._required_modifiers: Set[frozenset] = {
            frozenset(keys)
            for mod in config.modifiers
            for keys in [_MODIFIER_MAP[mod]]
        }
        self._pressed: Set = set()
        self._combo_active: bool = False  # debounce — fire once per press, not on repeat
        self._listener: keyboard.Listener | None = None

    def start(self) -> None:
        """Start the listener in a daemon thread."""
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.daemon = True
        self._listener.start()
        logger.info("Hotkey listener started.")

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()

    def _on_press(self, key) -> None:
        self._pressed.add(key)
        if self._is_combo_active():
            if not self._combo_active:
                self._combo_active = True
                logger.debug("Hotkey triggered.")
                threading.Thread(target=self.callback, daemon=True).start()
        else:
            self._combo_active = False

    def _on_release(self, key) -> None:
        self._pressed.discard(key)
        if not self._is_combo_active():
            self._combo_active = False

    def _is_combo_active(self) -> bool:
        """Return True if all required modifiers and the trigger key are held."""
        # Check trigger key
        trigger_held = (
            self._trigger_key in self._pressed
            or any(
                getattr(k, "char", None) == getattr(self._trigger_key, "char", None)
                for k in self._pressed
            )
        )
        if not trigger_held:
            return False

        # Check each modifier group — at least one key from each group must be held
        for modifier_group in self._required_modifiers:
            if not modifier_group.intersection(self._pressed):
                return False

        return True
