"""Entry point for the iPhone API server.

Usage:
    python -m assistant.api                # binds 127.0.0.1:8080 (local only)
    python -m assistant.api --lan          # binds 0.0.0.0:8080  (same Wi-Fi)
    python -m assistant.api --tailscale    # binds 0.0.0.0:8080 + prints Tailscale IP
    python -m assistant.api --port 8080
"""

import argparse
import logging
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
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    host = args.host or ("0.0.0.0" if (args.lan or args.tailscale) else "127.0.0.1")

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

    from assistant.api.server import create_app
    app = create_app()

    logger.info("Starting MACalendar API on http://%s:%d", host, args.port)
    app.run(host=host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
