"""The terminal client — the parts that need no running server."""
from __future__ import annotations

import pytest

from assistant import cli


def test_endpoints_lists_the_api_surface(capsys):
    rc = cli.main(["endpoints"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "/voice/text" in out and "/health" in out and "routes" in out


def test_say_needs_words():
    with pytest.raises(SystemExit):
        cli.main(["say"])            # argparse rejects: nargs='+'


def test_base_url_honours_the_env_port(monkeypatch):
    monkeypatch.setenv("MACALENDAR_API_PORT", "9999")
    assert cli._base_url().endswith(":9999")
