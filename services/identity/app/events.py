"""The identity.* events (contracts/events/identity.*.schema.json).

Each function adds one event to the outbox in the caller's transaction; the caller commits
it together with the change it describes. Users have no version column, so every event's
aggregate_version is fixed by the contract: registered 1, deleted 2, the email events 1.

The email events carry everything Notification's templates need (one-time links and
addresses included), so Notification never asks Identity anything. Reset tokens are
stored hashed, so a raw link left in the outbox would undo that: the relay deletes
EMAIL_EVENTS rows as soon as the broker has them (app/main.py), instead of keeping them
for 7 days like the other events.
"""

from datetime import UTC, datetime
from typing import Literal

from sqlalchemy.orm import Session

from app.models import User, UserRole
from app.platform.outbox import emit

USER = "user"

USER_REGISTERED = "identity.user.registered"
USER_DELETED = "identity.user.deleted"
PASSWORD_RESET_REQUESTED = "identity.password_reset.requested"
ADMIN_INVITATION_ISSUED = "identity.admin.invitation_issued"
ADMIN_REMOVED = "identity.admin.removed"
EMAIL_EVENTS = frozenset({PASSWORD_RESET_REQUESTED, ADMIN_INVITATION_ISSUED, ADMIN_REMOVED})

InviteTrigger = Literal["invited", "resent", "restored", "forgot_password"]


def user_registered(db: Session, user: User) -> None:
    """An account exists. Flushes first, so the id and created_at are known."""
    db.flush()
    is_admin = user.role == UserRole.ADMIN
    emit(
        db,
        type=USER_REGISTERED,
        aggregate_type=USER,
        aggregate_id=user.id,
        aggregate_version=1,
        data={
            "user_id": user.id,
            "role": user.role.value,
            # The contract: null exactly for administrators.
            "user_type": None if is_admin or user.user_type is None else user.user_type.value,
            "registered_at": user.created_at,
        },
    )


def user_deleted(db: Session, user_id, deleted_at: datetime | None = None) -> None:
    emit(
        db,
        type=USER_DELETED,
        aggregate_type=USER,
        aggregate_id=user_id,
        aggregate_version=2,
        data={"user_id": user_id, "deleted_at": deleted_at or datetime.now(UTC)},
    )


def password_reset_link(db: Session, user: User, *, audience: str, link: str, minutes: int):
    _password_reset(
        db, user, audience, {"method": "password", "link": link, "expires_in_minutes": minutes}
    )


def google_sign_in_reminder(db: Session, user: User, *, sign_in_url: str) -> None:
    """Forgot-password for an account created with Google: it has no password to reset."""
    _password_reset(db, user, "app", {"method": "google", "sign_in_url": sign_in_url})


def _password_reset(db: Session, user: User, audience: str, extra: dict) -> None:
    emit(
        db,
        type=PASSWORD_RESET_REQUESTED,
        aggregate_type=USER,
        aggregate_id=user.id,
        aggregate_version=1,
        data={
            "user_id": user.id,
            "email": user.email,
            "name": user.name,
            "audience": audience,
            **extra,
        },
    )


def admin_invitation_issued(
    db: Session,
    admin: User,
    *,
    inviter_name: str | None,
    link: str,
    hours: int,
    trigger: InviteTrigger,
) -> None:
    emit(
        db,
        type=ADMIN_INVITATION_ISSUED,
        aggregate_type=USER,
        aggregate_id=admin.id,
        aggregate_version=1,
        data={
            "admin_id": admin.id,
            "email": admin.email,
            "name": admin.name,
            "inviter_name": inviter_name,
            "link": link,
            "expires_in_hours": hours,
            "trigger": trigger,
        },
    )


def admin_removed(db: Session, admin: User, *, remover_name: str) -> None:
    emit(
        db,
        type=ADMIN_REMOVED,
        aggregate_type=USER,
        aggregate_id=admin.id,
        aggregate_version=1,
        data={
            "admin_id": admin.id,
            "email": admin.email,
            "name": admin.name,
            "remover_name": remover_name,
        },
    )
