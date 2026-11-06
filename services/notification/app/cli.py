"""Notification's command-line tools (detailed-plan 7.2):

    python -m app.cli health                  exit 0 when the database and the broker answer
    python -m app.cli prune-inbox [--days 30] delete processed_events rows older than that

The compose healthcheck runs it every 10 seconds.
"""

import argparse
import sys
from datetime import timedelta

from sqlalchemy import text

from app.db import SessionLocal
from app.handlers import INBOX_RETENTION, prune_inbox
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


def cmd_prune_inbox(args: argparse.Namespace) -> int:
    with SessionLocal() as session, session.begin():
        deleted = prune_inbox(session, timedelta(days=args.days))
    print(f"pruned {deleted} processed_events rows older than {args.days} days")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="SGJio notification")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("health", help="check the database and the broker").set_defaults(func=cmd_health)
    prune = sub.add_parser("prune-inbox", help="delete old processed_events rows")
    prune.add_argument(
        "--days", type=int, default=INBOX_RETENTION.days, help="keep this many days (default 30)"
    )
    prune.set_defaults(func=cmd_prune_inbox)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
