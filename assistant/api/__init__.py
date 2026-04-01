"""Entry point for the iPhone API server.

Usage:
    python -m assistant.api           # binds 127.0.0.1:5000
    python -m assistant.api --lan     # binds 0.0.0.0:5000 (LAN access for iPhone)
    python -m assistant.api --port 8080
"""

import argparse
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)


def main() -> None:
    parser = argparse.ArgumentParser(description="MACalendar iPhone API server")
    parser.add_argument("--lan", action="store_true", help="Bind to 0.0.0.0 (LAN access)")
    parser.add_argument("--host", default=None, help="Override bind host")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    host = args.host or ("0.0.0.0" if args.lan else "127.0.0.1")

    from assistant.api.server import create_app
    app = create_app()

    logging.getLogger(__name__).info(
        "Starting MACalendar API on http://%s:%d", host, args.port
    )
    app.run(host=host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
