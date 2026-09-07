"""The health CLI — logic that needs no running server, and the guard that
keeps the engine layer in step with the engine (like test_panel_agreement)."""
from __future__ import annotations

import pytest

from assistant import cli


def test_info_lines_never_drag_a_layer_to_warning():
    c = cli.Check("x")
    c.add(True, "ok"); c.info("just so you know")
    assert c.status is True                      # info is weightless
    c.add(None, "a real warning")
    assert c.status is None
    c.add(False, "broken")
    assert c.status is False


def test_endpoints_lists_the_api_surface(capsys):
    assert cli.main(["endpoints"]) == 0
    out = capsys.readouterr().out
    assert "/voice/text" in out and "/heartbeat" in out and "routes" in out


def test_storage_and_engine_layers_run_without_a_server():
    # these read local files / import modules; no API needed
    assert cli.check_storage().status in (True, False, None)
    eng = cli.check_engine()
    assert any("brain version" in t for _s, t in eng.rows)


def test_base_url_honours_the_env_port(monkeypatch):
    monkeypatch.setenv("MACALENDAR_API_PORT", "9191")
    assert cli._base_url().endswith(":9191")


# --- the version-coupling guard ---------------------------------------------

def test_the_engine_layer_covers_every_real_engine_stage():
    """check_engine hard-codes the stage list it verifies is wired. If the
    engine gains/renames a stage module and the doctor is not updated, this
    fails — so the health check can never silently miss a new component."""
    import inspect
    src = inspect.getsource(cli.check_engine)
    # the stage modules the engine actually ships
    import pkgutil
    import assistant.engine as E
    real = {m.name for m in pkgutil.iter_modules(E.__path__)
            if m.name not in ("state", "llm", "fastrule", "component", "__init__")}
    for stage in real:
        assert f'"{stage}"' in src, (
            f"engine stage '{stage}' exists but cli.check_engine does not verify it — "
            "add it to the stage list (see DOCUMENTATION/CLI.md, version-tied)")
