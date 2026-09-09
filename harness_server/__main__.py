"""Run the harness server:  python -m harness_server  (--reload supported)."""

import argparse
import os
import sys


def main() -> None:
    parser = argparse.ArgumentParser(prog="harness_server", description="Blender Harness server")
    parser.add_argument("--host", default=None, help="Bind host (default: env HARNESS_HOST or 127.0.0.1)")
    parser.add_argument("--port", type=int, default=None, help="Bind port (default: env HARNESS_PORT or 9876)")
    parser.add_argument("--reload", action="store_true", help="Auto reload on code change (dev)")
    parser.add_argument("--log-level", default=None, help="DEBUG/INFO/WARNING/ERROR")
    args = parser.parse_args()

    host = args.host or os.getenv("HARNESS_HOST", "127.0.0.1")
    port = args.port or int(os.getenv("HARNESS_PORT", "9876"))

    import uvicorn

    uvicorn.run(
        "harness_server.app:create_app",
        factory=True,
        host=host,
        port=port,
        reload=args.reload,
        log_level=(args.log_level or os.getenv("LOG_LEVEL", "info")).lower(),
    )


if __name__ == "__main__":
    sys.exit(main())
