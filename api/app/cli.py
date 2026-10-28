"""Developer commands. Run from the api folder:

python -m app.cli seed
python -m app.cli create-admin --email someone@example.com --name "Their Name"
python -m app.cli send-reset --email admin@sgjio.example.com --scope admin
python -m app.cli prune-media
python -m app.cli import-lessons [folder] [--publish]
python -m app.cli demo-activity
"""

import argparse
import getpass
import sys
from pathlib import Path

from sqlalchemy import select

from app import content_import, demo, media
from app.auth import normalise_email
from app.auth.reset import request_password_reset
from app.config import get_settings
from app.db import SessionLocal
from app.models import AdminAction, AdminEvent, AuthScope, User, UserRole
from app.security import hash_password, password_rule_failures
from app.seed import seed


def cmd_seed(_: argparse.Namespace) -> int:
    with SessionLocal() as db:
        created = seed(db)
    if created:
        print("Created:\n  - " + "\n  - ".join(created))
    else:
        print("Nothing to do: seed data already present.")
    return 0


def cmd_create_admin(args: argparse.Namespace) -> int:
    """Set up the first administrator, or let one back in, from the server (SCRUM-68).

    Everyday adding and removing happens on the portal's Administrators page (SCRUM-81).
    This stays for a new database, or if nobody can sign in: it sets the password of an
    existing administrator, restoring them if they were removed. Like the portal, it refuses
    a learner's email, since one email is one account.
    """
    email = normalise_email(args.email)
    password = args.password or getpass.getpass("Password for the administrator: ")
    failures = password_rule_failures(password)
    if failures:
        print("Password not accepted:\n  - " + "\n  - ".join(failures), file=sys.stderr)
        return 1
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user and user.role != UserRole.ADMIN:
            print(
                f"{email} belongs to a learner's account. Use a different email.",
                file=sys.stderr,
            )
            return 1
        if user:
            restored = user.is_removed
            user.removed_at = None
            user.invited_at = None
            user.password_hash = hash_password(password)
            if restored:
                db.add(AdminEvent(action=AdminAction.RESTORED, admin_id=user.id))
            print(f"{'Restored' if restored else 'Updated'} administrator {email}.")
        else:
            user = User(
                name=args.name,
                email=email,
                password_hash=hash_password(password),
                role=UserRole.ADMIN,
            )
            db.add(user)
            db.flush()
            db.add(AdminEvent(action=AdminAction.ADDED, admin_id=user.id))
            print(f"Created administrator {email}.")
        db.commit()
    return 0


def cmd_send_reset(args: argparse.Namespace) -> int:
    """Trigger a password reset email, to test email sending (SCRUM-74)."""
    scope = AuthScope(args.scope)
    with SessionLocal() as db:
        request_password_reset(db, args.email, scope)
    backend = get_settings().email_backend
    where = "http://localhost:8025" if backend == "smtp" else f"the {backend} backend"
    print(
        f"If {args.email} is a valid {scope.value} account, a reset email was sent. Check {where}."
    )
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


def cmd_demo_activity(_: argparse.Namespace) -> int:
    """Add demo learners and their lesson runs, for lesson insights (SCRUM-84). Replaces
    any demo learners already there, so dates are always relative to today."""
    with SessionLocal() as db:
        log = demo.demo_activity(db)
    print("Added:\n  - " + "\n  - ".join(log))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="SGJio dev commands")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("seed", help="insert development seed data").set_defaults(func=cmd_seed)

    p = sub.add_parser(
        "create-admin", help="set up an administrator, or reset or restore one (server only)"
    )
    p.add_argument("--email", required=True)
    p.add_argument("--name", default="SGJio Admin")
    p.add_argument("--password", help="omit to be prompted")
    p.set_defaults(func=cmd_create_admin)

    p = sub.add_parser("send-reset", help="send a password reset email")
    p.add_argument("--email", required=True)
    p.add_argument("--scope", choices=[s.value for s in AuthScope], default="app")
    p.set_defaults(func=cmd_send_reset)

    p = sub.add_parser("import-lessons", help="load lessons from files in content/")
    p.add_argument("folder", nargs="?", help="defaults to content/lessons")
    p.add_argument("--publish", action="store_true", help="publish new and changed lessons")
    p.set_defaults(func=cmd_import_lessons)

    sub.add_parser(
        "demo-activity", help="add demo learners and lesson runs (replaces earlier ones)"
    ).set_defaults(func=cmd_demo_activity)

    sub.add_parser(
        "prune-media", help="delete uploaded images and audio that no lesson uses"
    ).set_defaults(func=cmd_prune_media)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
