"""Entry point for the iPhone API server.

Usage:
    python -m assistant.api                # binds 127.0.0.1:8080 (local only)
    python -m assistant.api --lan          # binds 0.0.0.0:8080  (same Wi-Fi)
    python -m assistant.api --tailscale    # binds 0.0.0.0:8080 + prints Tailscale IP
    python -m assistant.api --port 8080
    python -m assistant.api --tailscale --reload   # restarts itself on source changes
"""

import argparse
import logging
import os
import subprocess

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)

logger = logging.getLogger(__name__)


def _tailscale_ip() -> str | None:
    """Return the Tailscale IPv4 address, or None if Tailscale isn't running."""
    try:
        result = subprocess.run(
            ["tailscale", "ip", "-4"],
            capture_output=True, text=True, timeout=3
        )
        ip = result.stdout.strip()
        return ip if ip and not result.returncode else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="MACalendar iPhone API server")
    parser.add_argument("--lan", action="store_true", help="Bind to 0.0.0.0 (same Wi-Fi access)")
    parser.add_argument("--tailscale", action="store_true", help="Bind to 0.0.0.0 and print Tailscale IP")
    parser.add_argument("--host", default=None, help="Override bind host explicitly")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--debug", action="store_true",
                        help="Werkzeug debugger AND reloader. Loopback binds only — "
                             "the debugger is a remote shell to anyone who can reach it.")
    parser.add_argument("--reload", action="store_true",
                        help="Restart the server when a source file changes. Safe to use "
                             "with --tailscale: this is the reloader without the debugger.")
    args = parser.parse_args()

    host = args.host or ("0.0.0.0" if (args.lan or args.tailscale) else "127.0.0.1")

    # The Werkzeug debugger executes arbitrary Python from the browser. On
    # 0.0.0.0 that is a shell for anyone on the tailnet, so it is refused
    # rather than warned about. --reload gives the useful half.
    if args.debug and host != "127.0.0.1":
        parser.error(
            f"--debug binds the Werkzeug debugger to {host}, which is a remote shell "
            "for anything that can reach this port. Use --reload for auto-restart, "
            "or --debug without --lan/--tailscale."
        )

    if args.tailscale:
        ts_ip = _tailscale_ip()
        if ts_ip:
            logger.info("Tailscale IP detected: %s", ts_ip)
            logger.info("Set iPhone server URL to: http://%s:%d", ts_ip, args.port)
        else:
            logger.warning(
                "Tailscale IP not found — is Tailscale installed and running? "
                "(brew install tailscale)"
            )

    reload = args.reload or args.debug
    if reload:
        # Tells create_app that a process without WERKZEUG_RUN_MAIN is the
        # watcher, not the server, and should skip loading the models.
        os.environ["MACALENDAR_RELOADING"] = "1"

    from assistant.api.server import create_app
    app = create_app()

    logger.info("Starting MACalendar API on http://%s:%d%s",
                host, args.port, "  (auto-reloading on source changes)" if reload else "")
    if reload:
        logger.info(
            "Editing anything under assistant/ restarts this server. A command "
            "already in flight when that happens is lost — its background "
            "self-check thread goes with the process."
        )
    # The reloader watches everything importable under the project, so editing
    # a test or a script restarted the server — and each restart reloads spaCy,
    # the date recogniser and Whisper, which is several seconds and a network
    # round trip for a file the server never imports. Only assistant/ can change
    # how it behaves, so only assistant/ should be able to restart it.
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # assistant/
    project = os.path.dirname(here)
    exclude = [
        os.path.join(project, "tests", "*"),
        os.path.join(project, "scripts", "*"),
        os.path.join(project, "DOCUMENTATION", "*"),
        os.path.join(project, "MACalendar-iOS", "*"),
        os.path.join(project, ".venv", "*"),
        os.path.join(project, ".git", "*"),
    ]

    app.run(host=host, port=args.port, debug=args.debug, use_reloader=reload,
            exclude_patterns=exclude if reload else None)


if __name__ == "__main__":
    main()
