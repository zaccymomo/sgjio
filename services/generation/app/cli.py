"""Generation's command-line tools:

    python -m app.cli health    exit 0 when the database and the broker answer

The compose healthcheck runs it every 10 seconds.
"""

import argparse
import sys

from sqlalchemy import text

from app.db import SessionLocal
from app.platform.broker import close_quietly, connect


def cmd_health(_: argparse.Namespace) -> int:
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
    except Exception as error:  # noqa: BLE001 - report any failure
        print(f"database: unavailable ({error})", file=sys.stderr)
        return 1
    connection = None
    try:
        connection = connect("health")
    except Exception as error:  # noqa: BLE001
        print(f"broker: unavailable ({error})", file=sys.stderr)
        return 1
    finally:
        close_quietly(connection)
    print("ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="SGJio generation")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("health", help="check the database and the broker").set_defaults(func=cmd_health)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
