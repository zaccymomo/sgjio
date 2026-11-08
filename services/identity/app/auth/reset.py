"""One-time password reset links (supports SCRUM-63 and SCRUM-69).

- A link is valid for RESET_TOKEN_MINUTES (15 on the microservices branch, 5 in the
  monolith: the email is now sent asynchronously, so it needs longer to arrive).
- Requesting a new link makes any earlier unused link for that account and front end
  stop working (SCRUM-63 AC7, SCRUM-69 AC7).
- A link works once (AC6).
- Admin-portal links are only ever issued to administrator accounts (SCRUM-69).
- Removed administrators get no links, and their old ones stop working (SCRUM-81).
- An account created with Google has no password: it is emailed how it signs in instead
  (SCRUM-92).
- Invites to the admin portal are the same kind of link, lasting INVITE_LINK_HOURS
  (SCRUM-81). An invited administrator who asks for a reset link is sent a new invite.

Identity no longer sends email itself. Each email is an event written to the outbox in the
same transaction as the link it carries (app/events.py); Notification sends it.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import events
from app.auth import normalise_email
from app.auth.sessions import end_all_sessions
from app.config import get_settings
from app.models import AdminAction, AdminEvent, AuthScope, PasswordResetToken, User
from app.security import hash_password, hash_token, new_token


def reset_link(scope: AuthScope, token: str, page: str = "reset-password") -> str:
    settings = get_settings()
    base = settings.admin_url if scope == AuthScope.ADMIN else settings.web_url
    return f"{base.rstrip('/')}/{page}?token={token}"


def issue_reset_token(
    db: Session,
    user: User,
    scope: AuthScope,
    lifetime: timedelta | None = None,
    commit: bool = True,
) -> str:
    """Create a new reset token for the user, cancelling earlier unused ones. It lasts
    `lifetime`, or RESET_TOKEN_MINUTES. With `commit=False` the caller commits it, together
    with the event that carries the link."""
    db.execute(
        delete(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.scope == scope,
            PasswordResetToken.used_at.is_(None),
        )
    )
    token = new_token()
    lifetime = lifetime or timedelta(minutes=get_settings().reset_token_minutes)
    db.add(
        PasswordResetToken(
            user_id=user.id,
            scope=scope,
            token_hash=hash_token(token),
            expires_at=datetime.now(UTC) + lifetime,
        )
    )
    if commit:
        db.commit()
    return token


def request_password_reset(db: Session, email: str, scope: AuthScope) -> None:
    """Email a reset link if the account exists (and is an admin, for the admin portal).

    Always returns nothing and never raises for an unknown email, so the page can show
    the same confirmation either way (SCRUM-63 AC2, SCRUM-69 AC2).
    """
    user = db.scalar(select(User).where(User.email == normalise_email(email)))
    if user is None or user.is_removed or (scope == AuthScope.ADMIN and not user.is_admin):
        return
    if scope == AuthScope.ADMIN and user.invited_at is not None:
        # They have no password to reset yet: send what they are waiting for instead.
        db.add(AdminEvent(action=AdminAction.INVITE_RESENT, admin_id=user.id))
        send_admin_invite(db, user, inviter=None, trigger="forgot_password")
        return
    if not user.has_password:
        # Created with Google (SCRUM-92): nothing to reset, so say how they sign in.
        sign_in = f"{get_settings().web_url.rstrip('/')}/sign-in"
        events.google_sign_in_reminder(db, user, sign_in_url=sign_in)
        db.commit()
        return
    token = issue_reset_token(db, user, scope, commit=False)
    events.password_reset_link(
        db,
        user,
        audience=scope.value,
        link=reset_link(scope, token),
        minutes=get_settings().reset_token_minutes,
    )
    db.commit()


def send_admin_invite(
    db: Session,
    user: User,
    inviter: User | None,
    trigger: events.InviteTrigger,
) -> None:
    """Email an administrator a link to choose their password (SCRUM-81), cancelling any
    earlier link. Marks the account as waiting for that, from now, and commits.

    `trigger` says why: invited, resent, restored (the wording says access is back), or
    forgot_password (they asked for a new link themselves, so there is no inviter)."""
    hours = get_settings().invite_link_hours
    token = issue_reset_token(db, user, AuthScope.ADMIN, timedelta(hours=hours), commit=False)
    user.invited_at = datetime.now(UTC)
    events.admin_invitation_issued(
        db,
        user,
        inviter_name=inviter.name if inviter else None,
        link=reset_link(AuthScope.ADMIN, token, page="set-password"),
        hours=hours,
        trigger=trigger,
    )
    db.commit()


def check_reset_token(db: Session, token: str, scope: AuthScope) -> User | None:
    """Return the user if the link is still usable, without using it up."""
    record = _live_token(db, token, scope)
    return record.user if record else None


def consume_reset_token(db: Session, token: str, scope: AuthScope) -> User | None:
    """Use up a reset link. Returns the user, or None if the link is not valid."""
    record = _live_token(db, token, scope)
    if record is None:
        return None
    record.used_at = datetime.now(UTC)
    db.commit()
    return record.user


def set_new_password(db: Session, user: User, new_password: str) -> None:
    """Save a new password and sign the user out of every browser (SCRUM-63 AC5).

    An invited administrator choosing their first password has joined (SCRUM-81)."""
    user.password_hash = hash_password(new_password)
    if user.invited_at is not None:
        user.invited_at = None
        db.add(AdminEvent(action=AdminAction.JOINED, admin_id=user.id))
    db.commit()
    end_all_sessions(db, user)


def _live_token(db: Session, token: str, scope: AuthScope) -> PasswordResetToken | None:
    record = db.scalar(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == hash_token(token),
            PasswordResetToken.scope == scope,
        )
    )
    if record is None or record.used_at is not None or record.user.is_removed:
        return None
    if record.expires_at <= datetime.now(UTC):
        return None
    return record
