"""Adding and removing administrators from the admin portal (SCRUM-81).

- Every administrator has the same access: any of them can invite, remove or restore any
  other, except themselves. There is always at least one left.
- Inviting creates the account with a password nobody knows and emails a link to choose one
  (INVITE_LINK_HOURS). Until then the account is "invited" (`users.invited_at`).
- An email that already belongs to a learner is refused: one email is one account, and a
  learner's password and history should not become an administrator's (AC3).
- Removing closes the account rather than deleting it (`users.removed_at`): their sessions
  end everywhere, their links stop working, their password is replaced, and they are told
  who removed them. Restoring opens it again with a fresh link, never the old password.
- Every change is written to `admin_events`, so the page can show who did what, and when.

Emails are events in the outbox, written in the same transaction as the change
(identity.admin.invitation_issued, identity.admin.removed); Notification sends them. A
new administrator is also an identity.user.registered.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import events
from app.auth.reset import check_reset_token, send_admin_invite
from app.config import get_settings
from app.models import (
    AdminAction,
    AdminEvent,
    AuthScope,
    AuthSession,
    LoginAttempt,
    PasswordResetToken,
    User,
    UserRole,
)
from app.platform.errors import Problem
from app.security import hash_password, new_token

# How many recent changes the page lists.
ACTIVITY_LIMIT = 30

# Who added an account, and who removed it, come from these entries in the log.
_ADDED = (AdminAction.INVITED, AdminAction.ADDED)
_REMOVED = (AdminAction.REMOVED, AdminAction.INVITE_CANCELLED)
_SENT_LINK = (AdminAction.INVITED, AdminAction.INVITE_RESENT, AdminAction.RESTORED)


@dataclass
class AdminSummary:
    id: uuid.UUID
    name: str
    email: str
    status: str  # "active" | "invited" | "removed"
    added_at: datetime
    added_by: str | None
    last_sign_in_at: datetime | None
    invited_at: datetime | None
    invite_expires_at: datetime | None
    removed_at: datetime | None
    removed_by: str | None
    is_you: bool


@dataclass
class ActivityEntry:
    id: uuid.UUID
    action: AdminAction
    at: datetime
    admin_id: uuid.UUID
    admin_name: str
    actor_id: uuid.UUID | None
    actor_name: str | None


@dataclass
class AdminsPage:
    admins: list[AdminSummary]
    removed: list[AdminSummary]
    activity: list[ActivityEntry]
    email_domain: str | None
    invite_hours: int


# --- Problems -----------------------------------------------------------------------------


def _not_found() -> Problem:
    return Problem("admin_not_found", "That administrator no longer exists.", 404)


def _unusable_password() -> str:
    """A password nobody knows, for an account that must not be signed in to yet."""
    return hash_password(new_token())


# --- Reading ------------------------------------------------------------------------------


def list_admins(db: Session, viewer: User) -> AdminsPage:
    """Every administrator, the removed ones apart, and the latest changes (AC1)."""
    people = db.scalars(select(User).where(User.role == UserRole.ADMIN)).all()
    by_id = {person.id: person for person in people}

    # The latest successful sign-in to the portal, by email (sign-in is recorded by email).
    last_sign_in = dict(
        db.execute(
            select(LoginAttempt.email, func.max(LoginAttempt.attempted_at))
            .where(LoginAttempt.scope == AuthScope.ADMIN, LoginAttempt.succeeded.is_(True))
            .group_by(LoginAttempt.email)
        ).all()
    )
    # When each waiting invite's link stops working.
    invite_expiry = dict(
        db.execute(
            select(PasswordResetToken.user_id, func.max(PasswordResetToken.expires_at))
            .where(
                PasswordResetToken.scope == AuthScope.ADMIN,
                PasswordResetToken.used_at.is_(None),
            )
            .group_by(PasswordResetToken.user_id)
        ).all()
    )
    events = db.scalars(select(AdminEvent).order_by(AdminEvent.created_at, AdminEvent.id)).all()
    names = {person.id: person.name for person in people}
    # Actors are administrators too, but load any that are not (e.g. a since-changed role).
    missing = {e.actor_id for e in events if e.actor_id and e.actor_id not in names}
    if missing:
        names.update(db.execute(select(User.id, User.name).where(User.id.in_(missing))).all())

    added_by: dict[uuid.UUID, str | None] = {}
    removed_by: dict[uuid.UUID, str | None] = {}
    for event in events:
        actor = names.get(event.actor_id) if event.actor_id else None
        if event.action in _ADDED and event.admin_id not in added_by:
            added_by[event.admin_id] = actor
        if event.action in _REMOVED:
            removed_by[event.admin_id] = actor

    def summary(person: User) -> AdminSummary:
        status = "removed" if person.is_removed else "invited" if person.invited_at else "active"
        return AdminSummary(
            id=person.id,
            name=person.name,
            email=person.email,
            status=status,
            added_at=person.created_at,
            added_by=added_by.get(person.id),
            last_sign_in_at=last_sign_in.get(person.email),
            invited_at=person.invited_at,
            invite_expires_at=invite_expiry.get(person.id) if status == "invited" else None,
            removed_at=person.removed_at,
            removed_by=removed_by.get(person.id) if status == "removed" else None,
            is_you=person.id == viewer.id,
        )

    current = sorted(
        (summary(p) for p in people if not p.is_removed), key=lambda a: a.name.casefold()
    )
    removed = sorted(
        (summary(p) for p in people if p.is_removed),
        key=lambda a: a.removed_at or a.added_at,
        reverse=True,
    )
    activity = [
        ActivityEntry(
            id=event.id,
            action=event.action,
            at=event.created_at,
            admin_id=event.admin_id,
            admin_name=by_id[event.admin_id].name if event.admin_id in by_id else "",
            actor_id=event.actor_id,
            actor_name=names.get(event.actor_id) if event.actor_id else None,
        )
        for event in reversed(events[-ACTIVITY_LIMIT:])
    ]
    settings = get_settings()
    return AdminsPage(
        admins=current,
        removed=removed,
        activity=activity,
        email_domain=settings.admin_email_domain.strip().lower() or None,
        invite_hours=settings.invite_link_hours,
    )


def get_summary(db: Session, viewer: User, admin_id: uuid.UUID) -> AdminSummary:
    page = list_admins(db, viewer)
    for admin in page.admins + page.removed:
        if admin.id == admin_id:
            return admin
    raise _not_found()


# --- Inviting -----------------------------------------------------------------------------


def _outside_domain(email: str) -> str | None:
    """The domain the email should have been at, if it is outside it."""
    domain = get_settings().admin_email_domain.strip().lower()
    if domain and email.rsplit("@", 1)[-1] != domain:
        return domain
    return None


def _email_taken(person: User) -> Problem:
    """Why an email that already has an account cannot be invited (AC3)."""
    if person.role != UserRole.ADMIN:
        return Problem(
            "email_in_use",
            "That email belongs to a learner's account. Administrators need an email of "
            "their own, so use a different one.",
            409,
            field="email",
        )
    if person.is_removed:
        return Problem(
            "admin_removed",
            f"{person.name} was removed as an administrator. Restore them instead.",
            409,
            field="email",
            extra={"admin_id": str(person.id)},
        )
    if person.invited_at is not None:
        return Problem(
            "already_invited",
            f"{person.name} has already been invited. You can send the invite again.",
            409,
            field="email",
            extra={"admin_id": str(person.id)},
        )
    return Problem(
        "already_admin",
        f"{person.name} is already an administrator.",
        409,
        field="email",
        extra={"admin_id": str(person.id)},
    )


def invite_admin(
    db: Session, actor: User, name: str, email: str, allow_other_domain: bool = False
) -> User:
    """Create an administrator and email them a link to choose a password (AC2).

    `email` arrives normalised. One outside ADMIN_EMAIL_DOMAIN is refused with
    `outside_domain` until the request says it was confirmed.
    """
    existing = db.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise _email_taken(existing)
    domain = _outside_domain(email)
    if domain and not allow_other_domain:
        raise Problem(
            "outside_domain",
            f"That email isn't at {domain}. Check it belongs to your team, then add them anyway.",
            422,
            field="email",
            extra={"domain": domain},
        )

    admin = User(name=name, email=email, password_hash=_unusable_password(), role=UserRole.ADMIN)
    db.add(admin)
    try:
        db.flush()
    except IntegrityError:
        # Someone else used the email at the same moment; answer as if it had been first.
        db.rollback()
        existing = db.scalar(select(User).where(User.email == email))
        if existing is None:
            raise
        raise _email_taken(existing) from None
    events.user_registered(db, admin)
    db.add(AdminEvent(action=AdminAction.INVITED, admin_id=admin.id, actor_id=actor.id))
    send_admin_invite(db, admin, inviter=actor, trigger="invited")
    return admin


def _find(db: Session, admin_id: uuid.UUID, lock: bool = False) -> User:
    query = select(User).where(User.id == admin_id, User.role == UserRole.ADMIN)
    admin = db.scalar(query.with_for_update() if lock else query)
    if admin is None:
        raise _not_found()
    return admin


def resend_invite(db: Session, actor: User, admin_id: uuid.UUID) -> User:
    """Send a waiting administrator a new link. The earlier one stops working."""
    admin = _find(db, admin_id)
    if admin.is_removed or admin.invited_at is None:
        raise Problem(
            "not_invited",
            f"{admin.name} has already set up their account, so there is no invite to send.",
            409,
        )
    db.add(AdminEvent(action=AdminAction.INVITE_RESENT, admin_id=admin.id, actor_id=actor.id))
    send_admin_invite(db, admin, inviter=actor, trigger="resent")
    return admin


def invite_for_token(db: Session, token: str) -> tuple[User, str | None] | None:
    """The invited administrator an invite link belongs to, and who invited them, or None
    if the link is no longer valid or they have already set up their account."""
    admin = check_reset_token(db, token, AuthScope.ADMIN)
    if admin is None or admin.invited_at is None:
        return None
    inviter = db.scalar(
        select(User.name)
        .join(AdminEvent, AdminEvent.actor_id == User.id)
        .where(AdminEvent.admin_id == admin.id, AdminEvent.action.in_(_SENT_LINK))
        .order_by(AdminEvent.created_at.desc())
        .limit(1)
    )
    return admin, inviter


# --- Removing and restoring ---------------------------------------------------------------


def remove_admin(db: Session, actor: User, admin_id: uuid.UUID) -> User:
    """Close another administrator's account (AC4), or cancel their invite. Safe to repeat.

    Refused for yourself, and for the last administrator (AC5). The administrators are
    locked first, so two removing each other at the same moment cannot both succeed.
    """
    active = db.scalars(
        select(User)
        .where(User.role == UserRole.ADMIN, User.removed_at.is_(None))
        .order_by(User.id)
        .with_for_update()
    ).all()
    admin = next((person for person in active if person.id == admin_id), None)
    if admin is None:
        db.rollback()
        return _find(db, admin_id)  # already removed, or 404
    if admin.id == actor.id:
        db.rollback()
        raise Problem(
            "cannot_remove_self",
            "You can't remove yourself. Ask another administrator to do it.",
            409,
        )
    if len(active) <= 1 or actor.id not in {person.id for person in active}:
        db.rollback()
        raise Problem(
            "last_admin",
            "There must always be at least one administrator, so this one can't be removed.",
            409,
        )

    was_invited = admin.invited_at is not None
    admin.removed_at = datetime.now(UTC)
    admin.invited_at = None
    admin.password_hash = _unusable_password()
    db.execute(delete(AuthSession).where(AuthSession.user_id == admin.id))
    db.execute(
        delete(PasswordResetToken).where(
            PasswordResetToken.user_id == admin.id, PasswordResetToken.used_at.is_(None)
        )
    )
    action = AdminAction.INVITE_CANCELLED if was_invited else AdminAction.REMOVED
    db.add(AdminEvent(action=action, admin_id=admin.id, actor_id=actor.id))
    if not was_invited:
        events.admin_removed(db, admin, remover_name=actor.name)
    db.commit()
    return admin


def restore_admin(db: Session, actor: User, admin_id: uuid.UUID) -> User:
    """Give a removed administrator access again. They choose a new password from a fresh
    link, so whoever controls the inbox now is who gets in. Safe to repeat."""
    admin = _find(db, admin_id, lock=True)
    if not admin.is_removed:
        db.rollback()
        return admin
    admin.removed_at = None
    db.add(AdminEvent(action=AdminAction.RESTORED, admin_id=admin.id, actor_id=actor.id))
    send_admin_invite(db, admin, inviter=actor, trigger="restored")
    return admin
