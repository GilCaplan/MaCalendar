"""observance.enabled must survive the config loader.

Before ObservanceConfig declared the field, pydantic silently discarded the
yaml key (extra='ignore'), so `enabled: false` in config.yaml never reached
observance.is_enabled() — only the MACALENDAR_OBSERVANCE env override
actually worked. Found while wiring the settings checkbox.
"""

from __future__ import annotations

from assistant.config import ObservanceConfig


def test_enabled_false_survives_the_loader():
    assert ObservanceConfig(**{"enabled": False}).enabled is False


def test_enabled_defaults_true():
    assert ObservanceConfig().enabled is True
