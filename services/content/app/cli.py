"""Content's commands (docs/architecture/detailed-plan.md, section 7.2). In compose:

    docker compose exec content python -m app.cli seed
    docker compose exec content python -m app.cli import-lessons [folder] [--publish]
    docker compose exec content python -m app.cli prune-media
    docker compose exec content python -m app.cli republish-catalog
    docker compose exec content python -m app.cli health

Events these write go to the outbox; the running service's relay publishes them.
"""

import argparse
import sys
from pathlib import Path

from sqlalchemy import text

from app import content_import, events, media
from app.config import get_settings
from app.db import SessionLocal
from app.platform.broker import close_quietly, connect
from app.platform.config import configure, get_config
from app.seed import seed


def cmd_seed(_: argparse.Namespace) -> int:
    """Topics, the lessons in CONTENT_DIR (published) and the aptitude bank. Safe to rerun."""
    with SessionLocal() as db:
        created = seed(db)
    if created:
        print("Created:\n  - " + "\n  - ".join(created))
    else:
        print("Nothing to do: seed data already present.")
    return 0


def cmd_import_lessons(args: argparse.Namespace) -> int:
    """Load lessons from files (content/README.md), so they can be written without the admin
    portal. Safe to run again: unchanged files change nothing."""
    root = Path(args.folder) if args.folder else get_settings().content_dir
    if not root.is_dir():
        print(f"There is no folder {root}.", file=sys.stderr)
        return 1
    with SessionLocal() as db:
        results = content_import.import_folder(db, root, publish=args.publish)
    if not results:
        print(f"No lesson files found under {root}.")
    failed = False
    for result in results:
        print(result.describe())
        for problem in result.problems:
            print(f"    {problem}")
        failed = failed or result.action == "failed"
    return 1 if failed else 0


def cmd_prune_media(_: argparse.Namespace) -> int:
    """Delete uploaded images and audio that no lesson uses (SCRUM-19)."""
    with SessionLocal() as db:
        removed = media.prune(db)
    print(f"Deleted {removed} unused file(s)." if removed else "No unused files to delete.")
    return 0


def cmd_republish_catalog(_: argparse.Namespace) -> int:
    """Write current-state events for every topic, version, published lesson, question and
    the bank, so Learning can rebuild its read models."""
    with SessionLocal() as db:
        counts = events.republish_catalog(db)
        db.commit()
    print(
        "Republished {topics} topic(s), {versions} version(s), {lessons} lesson(s), "
        "{questions} question(s) and the aptitude bank.".format(**counts)
    )
    return 0


def cmd_health(_: argparse.Namespace) -> int:
    """Exit 0 when the database and the broker both answer."""
    healthy = True
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        print("database: ok")
    except Exception as error:  # noqa: BLE001 - report any failure
        print(f"database: unavailable ({error})")
        healthy = False
    connection = None
    try:
        connection = connect("health")
        print("broker: ok")
    except Exception as error:  # noqa: BLE001
        print(f"broker: unavailable ({error})")
        healthy = False
    finally:
        close_quietly(connection)
    return 0 if healthy else 1


def main(argv: list[str] | None = None) -> int:
    if get_config().service_name == "unknown":
        configure(service_name="content")
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="SGJio content commands")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser(
        "seed", help="topics, published lessons from CONTENT_DIR, the aptitude bank"
    ).set_defaults(func=cmd_seed)

    p = sub.add_parser("import-lessons", help="load lessons from files in content/")
    p.add_argument("folder", nargs="?", help="defaults to CONTENT_DIR")
    p.add_argument("--publish", action="store_true", help="publish new and changed lessons")
    p.set_defaults(func=cmd_import_lessons)

    sub.add_parser(
        "prune-media", help="delete uploaded images and audio that no lesson uses"
    ).set_defaults(func=cmd_prune_media)

    sub.add_parser(
        "republish-catalog", help="send every topic, lesson, version and question again"
    ).set_defaults(func=cmd_republish_catalog)

    sub.add_parser("health", help="check the database and the broker").set_defaults(func=cmd_health)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
