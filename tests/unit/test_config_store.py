"""The section-scoped, comment-preserving config writer."""
from __future__ import annotations

from assistant.config_store import set_values

SAMPLE = """# my config
tts:
  mute: false   # keep quiet?
  rate: 200
  voice: "Samantha"

ui:
  theme: "light"
  rate: 999     # a DIFFERENT rate — must never be touched by tts.rate

observance:
  latitude: 31.7683
"""


def _write(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(SAMPLE)
    return p


def test_rewrites_are_section_scoped(tmp_path):
    p = _write(tmp_path)
    assert set_values({"tts": {"rate": 180}}, str(p))
    out = p.read_text()
    assert "  rate: 180" in out
    assert "rate: 999     # a DIFFERENT rate" in out   # ui.rate untouched


def test_comments_survive_everywhere(tmp_path):
    p = _write(tmp_path)
    set_values({"tts": {"mute": True}}, str(p))
    out = p.read_text()
    assert "# my config" in out
    assert "mute: true   # keep quiet?" in out         # inline comment kept


def test_missing_key_is_inserted_into_its_section(tmp_path):
    p = _write(tmp_path)
    set_values({"observance": {"enabled": False}}, str(p))
    out = p.read_text()
    sec = out.split("observance:")[1]
    assert "enabled: false" in sec
    assert "latitude: 31.7683" in sec


def test_missing_section_is_appended(tmp_path):
    p = _write(tmp_path)
    set_values({"brandnew": {"key": "wren", "n": 3}}, str(p))
    out = p.read_text()
    assert "brandnew:\n  key: \"wren\"\n  n: 3" in out


def test_types_render_as_yaml_literals(tmp_path):
    p = _write(tmp_path)
    set_values({"tts": {"voice": "Daniel", "rate": 150, "mute": False}}, str(p))
    out = p.read_text()
    assert 'voice: "Daniel"' in out and "rate: 150" in out and "mute: false" in out


def test_missing_file_writes_nothing(tmp_path):
    assert set_values({"a": {"b": 1}}, str(tmp_path / "nope.yaml")) is False


def test_top_level_keys_and_lists(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("theme: \"light\"  # startup theme\nconfirmation_level: 1\n\naudio:\n  sample_rate: 16000\n")
    set_values({"": {"theme": "dark", "confirmation_level": 0},
                "audio": {"stop_phrases": ["execute", "done"]}}, str(p))
    out = p.read_text()
    assert 'theme: "dark"  # startup theme' in out          # comment kept
    assert "confirmation_level: 0" in out
    assert '  stop_phrases: ["execute", "done"]' in out     # inserted as flow list
