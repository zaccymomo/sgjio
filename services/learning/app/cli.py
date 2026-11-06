"""Learning's command-line tools (detailed plan 7.2). In compose:

docker compose exec learning python -m app.cli <command>

seed                                   learners' completions and aptitude results (after
                                       Identity's and Content's seeds; scripts/seed-all.sh)
wait-for-read-models [--timeout 60]    block until the read models hold what the seeds
                                       published (exit 0), or time out (exit 1)
demo-activity --run-nonce N [--count 60]
                                       lesson runs for Identity's demo learners of run N
                                       (same --count as Identity's seed-demo-learners)
reset-read-models [--yes]              empty the read models for a rebuild (never
                                       erased_learners); then run Content's
                                       republish-catalog and Identity's republish-learners
health                                 can this service reach its database and the broker
"""

import argparse
import sys

from sqlalchemy import text

from app import demo, read_models
from app.db import SessionLocal
from app.platform.broker import close_quietly, connect
from app.seed import SeedError, seed


def cmd_seed(_: argparse.Namespace) -> int:
    with SessionLocal() as db:
        try:
            created = seed(db)
        except SeedError as error:
            print(error, file=sys.stderr)
            return 1
    if created:
        print("Created:\n  - " + "\n  - ".join(created))
    else:
        print("Nothing to do: seed data already present.")
    return 0


def cmd_wait(args: argparse.Namespace) -> int:
    return 0 if read_models.wait(SessionLocal, args.timeout) else 1


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def cmd_demo_activity(args: argparse.Namespace) -> int:
    """Lesson runs for the demo learners, for lesson insights (SCRUM-84)."""
    with SessionLocal() as db:
        try:
            log = demo.demo_activity(db, args.run_nonce, timeout=args.timeout, count=args.count)
        except demo.DemoLearnersMissing as error:
            print(error, file=sys.stderr)
            return 1
    print("Added:\n  - " + "\n  - ".join(log))
    return 0


def cmd_reset_read_models(args: argparse.Namespace) -> int:
    if not args.yes:
        answer = input("Empty Learning's read models (learners' own data is kept)? [y/N] ")
        if answer.strip().lower() not in {"y", "yes"}:
            print("Nothing changed.")
            return 1
    with SessionLocal() as db:
        tables = read_models.reset(db)
    print("Emptied: " + ", ".join(tables))
    print(
        "Now republish: content `python -m app.cli republish-catalog`, identity "
        "`python -m app.cli republish-learners`, then `wait-for-read-models`."
    )
    return 0


def cmd_health(_: argparse.Namespace) -> int:
    healthy = True
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
            counts = read_models.counts(db)
        print(f"database: ok {counts}")
    except Exception as error:  # noqa: BLE001 - report whatever went wrong
        print(f"database: unavailable ({error.__class__.__name__}: {error})")
        healthy = False
    connection = None
    try:
        connection = connect("health")
        print("broker: ok")
    except Exception as error:  # noqa: BLE001
        print(f"broker: unavailable ({error.__class__.__name__})")
        healthy = False
    finally:
        close_quietly(connection)
    return 0 if healthy else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="SGJio Learning")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("seed", help="seed learners' completions and aptitude results").set_defaults(
        func=cmd_seed
    )

    p = sub.add_parser("wait-for-read-models", help="wait until the seeds' events have arrived")
    p.add_argument("--timeout", type=float, default=60.0, help="seconds (default 60)")
    p.set_defaults(func=cmd_wait)

    p = sub.add_parser("demo-activity", help="lesson runs for Identity's demo learners")
    p.add_argument("--run-nonce", required=True, help="the nonce seed-demo-learners printed")
    p.add_argument(
        "--count",
        type=_positive_int,
        default=demo.DEFAULT_COUNT,
        help=f"how many seed-demo-learners made (default {demo.DEFAULT_COUNT})",
    )
    p.add_argument("--timeout", type=float, default=60.0, help="seconds to wait for them")
    p.set_defaults(func=cmd_demo_activity)

    p = sub.add_parser("reset-read-models", help="empty the read models for a rebuild")
    p.add_argument("--yes", action="store_true", help="don't ask")
    p.set_defaults(func=cmd_reset_read_models)

    sub.add_parser("health", help="check the database and the broker").set_defaults(func=cmd_health)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
