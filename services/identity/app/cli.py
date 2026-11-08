"""Identity's command-line tools. Run from services/identity, or in the container:

docker compose exec identity python -m app.cli seed
python -m app.cli create-admin --email someone@example.com --name "Their Name"
python -m app.cli send-reset --email admin@sgjio.example.com --scope admin
python -m app.cli seed-demo-learners [--count 60] [--run-nonce abc123]
python -m app.cli clear-demo-learners
python -m app.cli republish-learners
python -m app.cli health

Commands that change accounts write their identity.* events to the outbox in the same
transaction; the running service's relay publishes them (contracts/README.md).
"""

import argparse
import getpass
import sys

from sqlalchemy import select, text

from app import demo, events
from app.auth import normalise_email
from app.auth.reset import request_password_reset
from app.db import SessionLocal
from app.models import AdminAction, AdminEvent, AuthScope, User, UserRole
from app.platform.broker import close_quietly, connect
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
            events.user_registered(db, user)
            db.add(AdminEvent(action=AdminAction.ADDED, admin_id=user.id))
            print(f"Created administrator {email}.")
        db.commit()
    return 0


def cmd_send_reset(args: argparse.Namespace) -> int:
    """Trigger a password reset email, to test email sending (SCRUM-74)."""
    scope = AuthScope(args.scope)
    with SessionLocal() as db:
        request_password_reset(db, args.email, scope)
    print(
        f"If {args.email} is a valid {scope.value} account, a reset email was queued "
        "(identity.password_reset.requested). Notification sends it: check "
        "http://localhost:8025."
    )
    return 0


def cmd_seed_demo_learners(args: argparse.Namespace) -> int:
    """Replace the demo learners (SCRUM-84). Pass the printed nonce to Learning's
    demo-activity."""
    if args.count < 1:
        print("--count must be at least 1.", file=sys.stderr)
        return 1
    with SessionLocal() as db:
        nonce, log = demo.seed_demo_learners(db, args.count, args.run_nonce)
    print("Done:\n  - " + "\n  - ".join(log))
    print(f"run nonce: {nonce}")
    return 0


def cmd_clear_demo_learners(_: argparse.Namespace) -> int:
    with SessionLocal() as db:
        removed = demo.clear_demo_learners(db)
    print(f"Deleted {removed} demo learner(s)." if removed else "No demo learners to delete.")
    return 0


def cmd_republish_learners(_: argparse.Namespace) -> int:
    """Write identity.user.registered again for every account, so Learning can rebuild its
    `learners` read model (it inserts if absent, and never brings back an erased one)."""
    with SessionLocal() as db:
        users = db.scalars(select(User).order_by(User.created_at, User.id)).all()
        for user in users:
            events.user_registered(db, user)
        db.commit()
    print(f"Queued identity.user.registered for {len(users)} account(s).")
    return 0


def cmd_health(_: argparse.Namespace) -> int:
    """Exit 0 when the database and the broker both answer."""
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
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
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="SGJio identity")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("seed", help="insert development seed accounts").set_defaults(func=cmd_seed)

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

    p = sub.add_parser(
        "seed-demo-learners", help="replace the demo learners (prints the run nonce)"
    )
    p.add_argument("--count", type=int, default=demo.DEFAULT_COUNT)
    p.add_argument("--run-nonce", help="defaults to a fresh random one")
    p.set_defaults(func=cmd_seed_demo_learners)

    sub.add_parser("clear-demo-learners", help="delete the demo learners").set_defaults(
        func=cmd_clear_demo_learners
    )
    sub.add_parser(
        "republish-learners", help="publish identity.user.registered for every account again"
    ).set_defaults(func=cmd_republish_learners)
    sub.add_parser("health", help="check the database and the broker").set_defaults(func=cmd_health)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
