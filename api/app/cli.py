"""Developer commands. Run from the api folder:

python -m app.cli seed
python -m app.cli create-admin --email someone@example.com --name "Their Name"
python -m app.cli send-reset --email admin@sgjio.example.com --scope admin
python -m app.cli prune-media
"""

import argparse
import getpass
import sys

from sqlalchemy import select

from app import media
from app.auth import normalise_email
from app.auth.reset import request_password_reset
from app.config import get_settings
from app.db import SessionLocal
from app.models import AuthScope, User, UserRole
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
    """Administrators are set up directly for now (open decision in SCRUM-68)."""
    email = normalise_email(args.email)
    password = args.password or getpass.getpass("Password for the new admin: ")
    failures = password_rule_failures(password)
    if failures:
        print("Password not accepted:\n  - " + "\n  - ".join(failures), file=sys.stderr)
        return 1
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user:
            user.role = UserRole.ADMIN
            print(f"{email} already existed and is now an administrator.")
        else:
            db.add(
                User(
                    name=args.name,
                    email=email,
                    password_hash=hash_password(password),
                    role=UserRole.ADMIN,
                )
            )
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


def cmd_prune_media(_: argparse.Namespace) -> int:
    """Delete uploaded images and audio that no lesson uses (SCRUM-19)."""
    with SessionLocal() as db:
        removed = media.prune(db)
    print(f"Deleted {removed} unused file(s)." if removed else "No unused files to delete.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="SGJio dev commands")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("seed", help="insert development seed data").set_defaults(func=cmd_seed)

    p = sub.add_parser("create-admin", help="create an administrator or promote a user")
    p.add_argument("--email", required=True)
    p.add_argument("--name", default="SGJio Admin")
    p.add_argument("--password", help="omit to be prompted")
    p.set_defaults(func=cmd_create_admin)

    p = sub.add_parser("send-reset", help="send a password reset email")
    p.add_argument("--email", required=True)
    p.add_argument("--scope", choices=[s.value for s in AuthScope], default="app")
    p.set_defaults(func=cmd_send_reset)

    sub.add_parser(
        "prune-media", help="delete uploaded images and audio that no lesson uses"
    ).set_defaults(func=cmd_prune_media)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
