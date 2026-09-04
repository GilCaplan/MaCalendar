"""`assistant` — the infrastructure health CLI.

This is NOT a quality harness — it never asks "is the assistant smart". It
checks that every layer of the stack is **wired and healthy**, so the
infrastructure is correctly in place. See DOCUMENTATION/CLI.md.

    assistant doctor                 # check every layer, green/red summary
    assistant check <layer>          # one layer: llm | storage | engine | panel | macos | external
    assistant say "<command>"        # diagnostic: run one command, show the engine's chain of thought
    assistant endpoints              # list the API surface

`doctor` walks six layers:
  1 llm       the model the API talks to (local Ollama or a cloud key) + local STT
  2 storage   calendar + memory DBs and the trace log are connected and writable
  3 engine    each stage of THIS engine version is wired and the live path answers
  4 panel     the thinking HUD is running and beating
  5 macos     the calendar GUI is beating, and the hosted-calendar sync (if configured)
  6 external  the phone / other clients have checked in, and the API is reachable to them
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

_TTY = sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def _c(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m" if _TTY else s


def _mark(status) -> str:
    return {True: _c("32", "✔"), False: _c("31", "✘"),
            None: _c("33", "•"), "info": _c("2", "ℹ")}[status]


# --- API client -------------------------------------------------------------

def _base_url() -> str:
    port = os.environ.get("MACALENDAR_API_PORT")
    if not port:
        try:
            from assistant.api.server import load_config
            port = str(getattr(load_config().api, "port", 8080))
        except Exception:
            port = "8080"
    return f"http://127.0.0.1:{port}"


def _api_key() -> "str | None":
    try:
        from assistant.api.server import load_config
        return getattr(load_config().api, "key", None) or None
    except Exception:
        return None


def _request(method: str, path: str, body=None, timeout=90):
    req = urllib.request.Request(
        _base_url() + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method, headers={"Content-Type": "application/json"})
    key = _api_key()
    if key:
        req.add_header("X-API-Key", key)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode() or "{}")


def _api_up() -> bool:
    try:
        _request("GET", "/health", timeout=4)
        return True
    except Exception:
        return False


# --- a check result ---------------------------------------------------------

class Check:
    def __init__(self, name: str):
        self.name = name
        self.rows: list = []   # (status, text)

    def add(self, status, text: str):
        self.rows.append((status, text))
        return self

    def info(self, text: str):
        """A purely informational line — grey, never affects layer status."""
        self.rows.append(("info", text))
        return self

    @property
    def status(self):
        st = [s for s, _ in self.rows if s != "info"]
        if any(s is False for s in st):
            return False
        if any(s is None for s in st):
            return None
        return True

    def render(self) -> str:
        head = f"{_mark(self.status)} {_c('1', self.name)}"
        body = "\n".join(f"    {_mark(s)} {t}" for s, t in self.rows)
        return head + ("\n" + body if body else "")


# --- the six layers ---------------------------------------------------------

def check_llm() -> Check:
    """Layer 1 — the model(s) the API talks to."""
    c = Check("llm — the language model connection")
    from assistant.api.server import load_config
    cfg = load_config()
    engine = cfg.llm_engine
    if engine == "ollama":
        try:
            import requests
            r = requests.get(f"{cfg.ollama.base_url}/api/tags", timeout=3)
            names = [m.get("name", "") for m in r.json().get("models", [])]
            want = cfg.ollama.model
            pulled = any(n.startswith(want.split(":")[0]) for n in names)
            c.add(True, f"ollama reachable at {cfg.ollama.base_url}")
            c.add(pulled, f"model {want} {'pulled' if pulled else 'NOT pulled'}")
        except Exception as e:
            c.add(False, f"ollama unreachable at {cfg.ollama.base_url} — {e}")
    else:
        key = getattr(getattr(cfg, engine, object()), "api_key", "")
        c.add(bool(key), f"{engine} api key {'present' if key else 'MISSING'}")
    # local speech + grammar models
    try:
        from assistant.intent.rule_parser import _RULE_PARSER_AVAILABLE
        c.add(_RULE_PARSER_AVAILABLE, f"spaCy grammar model {'loaded' if _RULE_PARSER_AVAILABLE else 'MISSING'}")
    except Exception as e:
        c.add(False, f"spaCy import failed — {e}")
    c.info(f"speech model: {cfg.stt_engine} (verified on a real /voice call, not here)")
    return c


def check_storage() -> Check:
    """Layer 2 — the DB files and the trace log."""
    import sqlite3
    c = Check("storage — databases and the trace log")
    from assistant.db import get_db
    from assistant import trace_bus
    try:
        db = get_db()
        with sqlite3.connect(f"file:{db.path}?mode=ro", uri=True) as conn:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        c.add("events" in tables and "todos" in tables,
              f"calendar db open ({db.path}) — {len(tables)} tables")
    except Exception as e:
        c.add(False, f"calendar db not readable — {e}")
    try:
        mem = os.environ.get("MACALENDAR_MEMORY_DB") or os.path.expanduser("~/.assistant_tools/nlu_memory.db")
        ok = os.path.exists(mem)
        c.add(ok, f"memory db {'present' if ok else 'MISSING'} ({mem})")
    except Exception as e:
        c.add(False, f"memory db check failed — {e}")
    try:
        p = trace_bus.BUS_PATH
        d = os.path.dirname(p)
        writable = os.access(d, os.W_OK)
        c.add(writable, f"trace log dir writable ({p})")
        c.add(os.path.exists(p) or None, "trace log exists" if os.path.exists(p)
              else "trace log not yet written (fine on a fresh install)")
    except Exception as e:
        c.add(False, f"trace log check failed — {e}")
    return c


def check_engine(deep: bool = False) -> Check:
    """Layer 3 — each stage of THIS engine version is wired, and the live path
    answers. Version-tied: reads CHAINS[BRAIN_VERSION]. See DOCUMENTATION/CLI.md."""
    c = Check("engine — the assistant pipeline (this version)")
    from assistant.trace import BRAIN_VERSION, CHAINS
    c.add(True, f"brain version: {BRAIN_VERSION}")
    # every stage module imports (wired)
    stages = ["transcript", "segment", "decompose", "validate", "generate", "crosscheck", "label"]
    import importlib
    for st in stages:
        try:
            importlib.import_module(f"assistant.engine.{st}")
            c.add(True, f"stage wired: {st}")
        except Exception as e:
            c.add(False, f"stage MISSING: {st} — {e}")
    # the version has a documented chain of thought
    c.add(BRAIN_VERSION in CHAINS, f"chain-of-thought spec defined for {BRAIN_VERSION}")
    # the live path answers with a coherent trace + the right version
    if _api_up():
        try:
            r = _request("POST", "/voice/text",
                         {"transcript": "what do I have today", "source": "test"}, timeout=60)
            got_brain = r.get("brain")
            trace_stages = {s.get("stage") for s in r.get("trace", [])}
            c.add(got_brain == BRAIN_VERSION, f"live path answers, tagged brain={got_brain}")
            c.add(bool(trace_stages), f"trace produced ({len(trace_stages)} stages: {', '.join(sorted(trace_stages))})")
        except Exception as e:
            c.add(False, f"live engine probe failed — {e}")
    else:
        c.add(None, "API not running — live engine probe skipped (start it, or run against a launched stack)")
    if deep:
        c.info("deep per-stage firing: run `python -m scripts.engine_stage_check --stage all` (needs Ollama, slow)")
    return c


def check_panel() -> Check:
    """Layer 4 — the thinking HUD (review panel)."""
    c = Check("panel — the thinking HUD (review panel)")
    from assistant.heartbeat import last_seen, FRESH_SECONDS
    hb = last_seen("hud")
    if hb is None:
        c.add(False, "HUD has never beaten — not running (start: python -m assistant.thinking_hud)")
    else:
        fresh = hb["age"] <= FRESH_SECONDS
        c.add(fresh, f"HUD beating {int(hb['age'])}s ago (pid {hb.get('pid')})"
              + ("" if fresh else " — STALE, likely stopped"))
    from assistant import trace_bus
    c.add(os.access(os.path.dirname(trace_bus.BUS_PATH), os.R_OK),
          "trace log readable by the HUD")
    return c


def check_macos() -> Check:
    """Layer 5 — the calendar GUI, and hosted-calendar sync if configured."""
    c = Check("macos — the calendar app and hosted-calendar sync")
    from assistant.heartbeat import last_seen, FRESH_SECONDS
    hb = last_seen("gui")
    if hb is None:
        c.add(False, "calendar GUI has never beaten — not running (start: python -m assistant.main)")
    else:
        fresh = hb["age"] <= FRESH_SECONDS
        c.add(fresh, f"calendar GUI beating {int(hb['age'])}s ago"
              + ("" if fresh else " — STALE"))
    from assistant.api.server import load_config
    cfg = load_config()
    if getattr(cfg, "microsoft", None):
        try:
            from assistant.actions.calendar.auth import has_valid_token  # best-effort
            ok = bool(has_valid_token())
            c.add(ok, f"hosted-calendar (Microsoft Graph) auth {'valid' if ok else 'EXPIRED — re-auth'}")
        except Exception:
            c.add(None, "hosted-calendar configured, but auth state could not be read here")
    else:
        c.info("hosted-calendar sync not configured — local-only (fine)")
    return c


def check_external() -> Check:
    """Layer 6 — the phone / other clients, and API reachability to them."""
    c = Check("external — phone / other devices")
    from assistant.heartbeat import last_seen, FRESH_SECONDS
    import glob
    beats = []
    hb_dir = os.environ.get("MACALENDAR_HEARTBEATS") or os.path.expanduser("~/.assistant_tools/heartbeats")
    for f in glob.glob(os.path.join(hb_dir, "client-*.json")):
        name = os.path.basename(f)[:-5]
        hb = last_seen(name)
        if hb:
            beats.append((name, hb))
    if not beats:
        c.add(None, "no client has checked in via /heartbeat yet (iOS app posts it once updated)")
    for name, hb in beats:
        fresh = hb["age"] <= FRESH_SECONDS * 20   # a phone beats far less often
        c.add(fresh or None, f"{name} seen {int(hb['age'])}s ago")
    # reachability: is the API bound so a device could reach it?
    try:
        import subprocess
        ip = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=3)
        addr = (ip.stdout or "").strip().splitlines()[0] if ip.stdout.strip() else ""
        c.info(f"tailscale address: {addr}") if addr else c.add(None, "tailscale address not available (is tailscale up?)")
    except Exception:
        c.add(None, "tailscale not checked (CLI or daemon absent)")
    return c


_LAYERS = {
    "llm": check_llm, "storage": check_storage, "engine": check_engine,
    "panel": check_panel, "macos": check_macos, "external": check_external,
}


# --- commands ---------------------------------------------------------------

def cmd_doctor(args) -> int:
    print(_c("1", "assistant doctor") + _c("2", f"  ({_base_url()})\n"))
    checks = [fn() for fn in _LAYERS.values()]
    for chk in checks:
        print(chk.render())
    n_fail = sum(1 for c in checks if c.status is False)
    n_warn = sum(1 for c in checks if c.status is None)
    print()
    if n_fail:
        print(_c("31", f"✘ {n_fail} layer(s) unhealthy") + (_c("33", f" · {n_warn} with warnings") if n_warn else ""))
        return 1
    print(_c("32", "✔ all layers healthy") + (_c("33", f" · {n_warn} with warnings") if n_warn else ""))
    return 0


def cmd_check(args) -> int:
    fn = _LAYERS[args.layer]
    chk = fn(deep=args.deep) if args.layer == "engine" and args.deep else fn()
    print(chk.render())
    return 0 if chk.status is not False else 1


def cmd_say(args) -> int:
    text = " ".join(args.words).strip()
    try:
        r = _request("POST", "/voice/text", {"transcript": text, "source": args.source})
    except Exception as e:
        print(_c("31", f"cannot reach the API — {e}"), file=sys.stderr)
        return 2
    print(_c("2", f"— chain of thought ({r.get('brain','?')}) —"))
    glyphs = {"vocab": "✎", "rule": "⚡", "llm": "◆", "validate": "✓",
              "execute": "▸", "verify": "⟳", "done": "●", "error": "✗", "memory": "≡", "stt": "🎙"}
    for st in r.get("trace", []):
        g = glyphs.get(st.get("stage", ""), "·")
        print(f"  {g} {st.get('title','')}  {_c('2', (st.get('detail') or '')[:70])}")
    print("\n" + _c("32" if r.get("actions") else "33", f"➜ {(r.get('message') or '').strip()}"))
    print(_c("2", f"  parse={r.get('parse')} · actions={r.get('actions')}"))
    return 0


def cmd_endpoints(args) -> int:
    import re
    import pathlib
    src = (pathlib.Path(__file__).parent / "api" / "server.py").read_text()
    routes = sorted(set(re.findall(r'@app\.(get|post|delete|patch)\("([^"]+)"', src)),
                    key=lambda r: (r[1], r[0]))
    for method, path in routes:
        print(f"  {_c('33', method.upper()):<7} {path}")
    print(_c("2", f"\n  {len(routes)} routes"))
    return 0


def main(argv: "list[str] | None" = None) -> int:
    p = argparse.ArgumentParser(prog="assistant", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor", help="check every layer of the stack").set_defaults(fn=cmd_doctor)
    ch = sub.add_parser("check", help="check one layer")
    ch.add_argument("layer", choices=list(_LAYERS))
    ch.add_argument("--deep", action="store_true", help="engine: also note the per-stage gate")
    ch.set_defaults(fn=cmd_check)
    s = sub.add_parser("say", help="diagnostic: run one command through the engine")
    s.add_argument("words", nargs="+")
    s.add_argument("--source", default="test", choices=["mac", "ios", "test"])
    s.set_defaults(fn=cmd_say)
    sub.add_parser("endpoints", help="list the API surface").set_defaults(fn=cmd_endpoints)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
