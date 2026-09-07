"""No test may write through the RUNNING assistant.api.

The scratch-store overrides in conftest redirect what the test process opens.
They cannot redirect an HTTP request: that is served by the `assistant.api`
running on this Mac, which holds the real ~/.assistant_tools stores. So a test
that posts to localhost:8080 writes Gil's actual calendar, memory and vocab —
the one leak the env overrides were never able to close.

It is not hypothetical. `test_thinking_hud.py` clicks the HUD's Revert button
for real, as the UI-testing rule requires; the widget's own
`revert_requested -> _on_revert` wiring is live in that fixture; and
`_on_revert` re-POSTs the captured body to `http://127.0.0.1:<api port>/todos`
from a daemon thread. Every `pytest tests/unit` run added one more
"buy groceries" to the real Today list — 45 of them between 2026-08-31 and
2026-09-07, landing 30 s to 3 min after the run finished, which is why they
looked like a mystery client rather than the suite.

Each test here points the guard at a stub server and asserts the stub hears
nothing. Remove the guard in conftest and they fail with the request in hand.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from tests.conftest import LiveAPIBlocked


# ---------------------------------------------------------------------------
# A stand-in for the running API, so an escape is caught rather than inferred
# ---------------------------------------------------------------------------

class _Stub(BaseHTTPRequestHandler):
    received: list = []

    def do_POST(self):                                   # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8", "replace")
        try:
            body = json.loads(raw or "{}")
        except ValueError:
            body = {"_raw": raw}
        type(self).received.append((self.path, body))
        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"id": 999}')

    do_GET = do_POST                                     # noqa: N815

    def log_message(self, *args):                        # keep the suite quiet
        pass


@pytest.fixture
def fake_api(monkeypatch):
    """An HTTP server on a scratch port, standing in for the live assistant.api.

    Anything the code under test manages to send arrives in `.received`; the
    guard's whole job is to keep that list empty.
    """
    _Stub.received = []
    server = HTTPServer(("127.0.0.1", 0), _Stub)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("MACALENDAR_API_PORT", str(port))
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


# ---------------------------------------------------------------------------
# The guard itself
# ---------------------------------------------------------------------------

def test_a_post_to_the_api_port_is_refused(fake_api, blocked_live_api_calls):
    import requests

    port = fake_api.server_address[1]
    with pytest.raises(LiveAPIBlocked):
        requests.post(f"http://127.0.0.1:{port}/todos",
                      json={"title": "buy groceries"}, timeout=5)
    assert _Stub.received == [], "the request reached the server anyway"
    assert blocked_live_api_calls == [("POST", f"http://127.0.0.1:{port}/todos")]


def test_other_loopback_ports_still_work(fake_api):
    """Ollama on 11434 and any other local service are none of the guard's
    business — only the assistant's own API port is off limits."""
    import requests

    other = HTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=other.serve_forever, daemon=True).start()
    try:
        r = requests.post(f"http://127.0.0.1:{other.server_address[1]}/api/tags",
                          json={}, timeout=5)
        assert r.status_code == 201
    finally:
        other.shutdown()
        other.server_close()


# ---------------------------------------------------------------------------
# The caller that was actually doing it
# ---------------------------------------------------------------------------

def test_clicking_the_huds_revert_button_writes_nothing_to_the_live_api(
        fake_api, tmp_path, monkeypatch, blocked_live_api_calls):
    """The duplicate-maker, reproduced end to end.

    A real mouse click on a real widget, exactly as test_thinking_hud.py does
    it — the HUD's own handler fires, spawns its thread, and tries to POST
    /todos. Before the guard, that arrived at the live server as a 46th
    "buy groceries".
    """
    pytest.importorskip("PyQt6.QtWidgets")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("MACALENDAR_HUD_STATE", str(tmp_path / "pos.json"))
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication

    import assistant.thinking_hud as hud_mod
    monkeypatch.setattr(hud_mod, "STATE_PATH", str(tmp_path / "pos.json"))
    app = QApplication.instance() or QApplication([])
    widget = hud_mod.ThinkingHUD(None)
    try:
        panel = widget.panel
        panel.begin("Mac")
        spec = {"kind": "todo",
                "body": {"title": "buy groceries", "list_name": "today"}}
        panel.add_step({"stage": "verify", "title": "Reviewed the answer",
                        "detail": "I removed a task I created by mistake.",
                        "ms": 0, "at_ms": 0, "ok": False,
                        "data": {"revert": [spec]}})
        bar = panel._notices[-1]
        QTest.mouseClick(bar._btn, Qt.MouseButton.LeftButton)
        app.processEvents()

        # _on_revert posts from a daemon thread; give it its turn.
        deadline = time.time() + 5
        while time.time() < deadline and not blocked_live_api_calls:
            app.processEvents()
            time.sleep(0.05)
    finally:
        widget.close()
        widget.deleteLater()
        app.processEvents()

    assert _Stub.received == [], (
        "the HUD's revert POST reached the live API — this is the write that "
        f"duplicated 'buy groceries' 45 times: {_Stub.received}")
    assert any(m == "POST" and url.endswith("/todos")
               for m, url in blocked_live_api_calls), \
        "the revert click never attempted the POST — the test proves nothing"


def test_the_cli_engine_probe_writes_nothing_to_the_live_api(
        fake_api, blocked_live_api_calls):
    """`check_engine`'s live probe posts /voice/text, which writes the real
    command memory and trace bus. test_cli.py calls it on every run."""
    from assistant import cli

    cli.check_engine()
    assert _Stub.received == [], (
        f"the doctor's live probe reached the API: {_Stub.received}")
