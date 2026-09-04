"""Command-line client for the running assistant.

Drive the engine and inspect state from the terminal, instead of curl — it
talks to the running API (the same one the phone and GUI use) and renders the
engine's chain of thought and results in colour.

    python -m assistant.cli say "book gym tomorrow at 7am"   # run a command, show the trace
    python -m assistant.cli health                           # is the stack up?
    python -m assistant.cli events [--days N]                # what's on the calendar
    python -m assistant.cli todos                            # the task list
    python -m assistant.cli vocab                            # the personal word list
    python -m assistant.cli pending                          # commands queued while offline
    python -m assistant.cli endpoints                        # every API route, by method

`say` posts to /voice/text and renders each stage the engine went through
(the same trace the thinking panel draws), colour-coded by kind, then the
answer. Colour is on only when stdout is a terminal (NO_COLOR to force off).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

# --- colour (matches DOCUMENTATION/LOGGING.md's philosophy) -----------------
_TTY = sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def _c(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m" if _TTY else s


# trace stage -> (glyph, colour) — the engine's chain of thought
_STAGE = {
    "stt": ("🎙", "36"), "vocab": ("✎", "36"), "rule": ("⚡", "33"),
    "memory": ("≡", "35"), "llm": ("◆", "35"), "validate": ("✓", "34"),
    "execute": ("▸", "32"), "verify": ("⟳", "33"), "done": ("●", "32"),
    "error": ("✗", "31"),
}


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


def _request(method: str, path: str, body: "dict | None" = None) -> dict:
    url = _base_url() + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    key = _api_key()
    if key:
        req.add_header("X-API-Key", key)
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}", "body": e.read().decode()[:200]}
    except (urllib.error.URLError, OSError) as e:
        print(_c("31", f"Cannot reach the assistant API at {_base_url()} — is it running? "
                       "(Launch Calendar.command)"), file=sys.stderr)
        print(_c("2", f"  {e}"), file=sys.stderr)
        raise SystemExit(2)


# --- commands ---------------------------------------------------------------

def cmd_say(args) -> int:
    text = " ".join(args.words).strip()
    if not text:
        print("say what? e.g.  assistant say \"book gym tomorrow at 7am\"", file=sys.stderr)
        return 2
    resp = _request("POST", "/voice/text", {"transcript": text, "source": args.source,
                                            "supports_edit": False})
    if "error" in resp:
        print(_c("31", f"error: {resp['error']} {resp.get('body','')}"), file=sys.stderr)
        return 1
    brain = resp.get("brain", "?")
    print(_c("2", f"— chain of thought ({brain}) —"))
    for st in resp.get("trace", []):
        glyph, colour = _STAGE.get(st.get("stage", ""), ("·", "0"))
        ms = st.get("ms", 0)
        line = f"  {glyph} {st.get('title','')}"
        detail = (st.get("detail") or "").strip()
        print(_c(colour, line) + (f"  {_c('2', detail)}" if detail else "")
              + _c("2", f"   {ms}ms"))
    msg = (resp.get("message") or "").strip()
    parse = resp.get("parse", "?")
    print()
    print(_c("32" if resp.get("actions") else "33", f"➜ {msg or '(no message)'}"))
    print(_c("2", f"  parse={parse} · actions={resp.get('actions')} · refresh={resp.get('refresh')}"))
    return 0


def cmd_health(args) -> int:
    h = _request("GET", "/health")
    ok = h.get("status") == "ok"
    print(_c("32" if ok else "31", f"status: {h.get('status','?')}"))
    print(f"  llm: {h.get('llm','?')}")
    print(f"  db:  {h.get('db','?')}")
    return 0 if ok else 1


def cmd_events(args) -> int:
    evs = _request("GET", f"/events?days={args.days}")
    rows = evs if isinstance(evs, list) else evs.get("events", [])
    if not rows:
        print(_c("2", f"no events in the next {args.days} days")); return 0
    for e in rows:
        when = f"{e.get('date','')} {e.get('start_time','')}".strip()
        print(f"  {_c('36', when):<28} {e.get('title','')}"
              + (_c("2", f"  @{e['location']}") if e.get("location") else ""))
    return 0


def cmd_todos(args) -> int:
    td = _request("GET", "/todos")
    rows = td if isinstance(td, list) else td.get("todos", [])
    if not rows:
        print(_c("2", "no tasks")); return 0
    for t in rows:
        mark = _c("32", "✓") if t.get("completed") else "○"
        tags = _c("2", " ".join(f"#{x}" for x in (t.get("tags") or [])))
        print(f"  {mark} {t.get('title','')}  {tags}".rstrip())
    return 0


def cmd_vocab(args) -> int:
    v = _request("GET", "/vocab")
    rows = v if isinstance(v, list) else v.get("words", v.get("entries", []))
    print(_c("2", f"{len(rows)} personal words"))
    for w in rows[: args.limit]:
        word = w.get("word", w) if isinstance(w, dict) else w
        aliases = w.get("aliases", []) if isinstance(w, dict) else []
        print(f"  {word}" + (_c("2", f"  ← {', '.join(aliases)}") if aliases else ""))
    return 0


def cmd_pending(args) -> int:
    p = _request("GET", "/pending")
    rows = p if isinstance(p, list) else p.get("pending", [])
    if not rows:
        print(_c("32", "nothing queued")); return 0
    for r in rows:
        print(f"  {_c('33', '⧗')} #{r.get('id')} {r.get('transcript','')[:60]}"
              + _c("2", f"  (tries {r.get('attempts',0)})"))
    return 0


def cmd_endpoints(args) -> int:
    """List the API surface — read from the server module, no server needed."""
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

    s = sub.add_parser("say", help="run a voice/text command through the engine")
    s.add_argument("words", nargs="+")
    s.add_argument("--source", default="mac", choices=["mac", "ios", "test"])
    s.set_defaults(fn=cmd_say)

    sub.add_parser("health", help="is the stack up?").set_defaults(fn=cmd_health)

    e = sub.add_parser("events", help="upcoming calendar events")
    e.add_argument("--days", type=int, default=7)
    e.set_defaults(fn=cmd_events)

    sub.add_parser("todos", help="the task list").set_defaults(fn=cmd_todos)

    v = sub.add_parser("vocab", help="the personal word list")
    v.add_argument("--limit", type=int, default=40)
    v.set_defaults(fn=cmd_vocab)

    sub.add_parser("pending", help="commands queued while offline").set_defaults(fn=cmd_pending)
    sub.add_parser("endpoints", help="list the API surface").set_defaults(fn=cmd_endpoints)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
