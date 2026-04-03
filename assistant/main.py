"""Entry point — launches the PyQt6 calendar app with integrated voice assistant."""

from __future__ import annotations

import logging
import os
import sys

# ---------------------------------------------------------------------------
# Register action plugins — add new `import assistant.actions.<name>` lines
# here to activate additional plugins.
# ---------------------------------------------------------------------------
import assistant.actions.calendar  # noqa: F401, PLC0415  registers CreateEventAction
import assistant.actions.todo      # noqa: F401, PLC0415  registers todo actions
import assistant.actions.clarify   # noqa: F401, PLC0415  registers ClarifyAction

from assistant.actions import registry
from assistant.calendar_ui.window import CalendarWindow
from assistant.config import load_config
from assistant.hotkey import HotkeyListener
from assistant.pipeline import Pipeline

os.makedirs(os.path.expanduser("~/.assistant_tools"), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            os.path.expanduser("~/.assistant_tools/assistant.log"),
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger(__name__)


def main() -> None:
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setApplicationName("Calendar")
    app.setOrganizationName("VoiceAssistant")

    # ------------------------------------------------------------------
    # Load config
    # ------------------------------------------------------------------
    config_path = os.path.abspath("config.yaml")
    try:
        config = load_config(config_path)
    except Exception as e:
        print(f"[Error] {e}", file=sys.stderr)
        sys.exit(1)

    logger.info("🖥️ Loaded config from %s", config_path)

    # ------------------------------------------------------------------
    # Audio device probe — detect native rate, dtype, permissions once
    # so the first recording never hits a PortAudio / AUHAL error.
    # ------------------------------------------------------------------
    from assistant.audio.probe import probe_audio
    audio_profile = probe_audio()
    logger.info("🖥️ Audio device probe:\n%s", audio_profile)
    for w in audio_profile.warnings:
        logger.warning("🖥️ Audio probe: %s", w)

    # ------------------------------------------------------------------
    # Build pipeline + hotkey
    # ------------------------------------------------------------------
    pipeline = Pipeline(config, registry)

    if not pipeline.health_check().get("ollama", True):
        logger.warning(
            "Ollama is not reachable at %s. Local voice commands will not work until "
            "Ollama is running (`ollama serve`).",
            config.ollama.base_url,
        )

    hotkey = HotkeyListener(config.hotkey, callback=pipeline.trigger)
    hotkey.start()
    logger.info("🖥️ Hotkey: %s+%s", "+".join(config.hotkey.modifiers), config.hotkey.key)

    # ------------------------------------------------------------------
    # Launch calendar window (blocks until closed)
    # ------------------------------------------------------------------
    window = CalendarWindow(pipeline, config=config)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
