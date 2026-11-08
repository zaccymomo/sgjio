"""Temporary blocking after repeated failed sign-ins (SCRUM-62 AC5, SCRUM-68 AC5).

Rule (proposed default, see docs/decisions.md): after LOGIN_MAX_FAILURES failed attempts
in a row for the same email on the same front end, further attempts are refused for
LOGIN_LOCKOUT_MINUTES, counted from the last failure. A successful sign-in resets the
count. Attempts made while blocked are refused without checking the password and are not
recorded, so waiting out the block always works.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AuthScope, LoginAttempt


def blocked_until(db: Session, email: str, scope: AuthScope) -> datetime | None:
    """When the block on this email lifts, or None if it is not blocked."""
    settings = get_settings()
    window = timedelta(minutes=settings.login_lockout_minutes)
    now = datetime.now(UTC)
    recent = db.scalars(
        select(LoginAttempt)
        .where(
            LoginAttempt.email == email,
            LoginAttempt.scope == scope,
            LoginAttempt.attempted_at > now - window,
        )
        .order_by(LoginAttempt.attempted_at.desc())
        .limit(settings.login_max_failures)
    ).all()
    if len(recent) < settings.login_max_failures or any(a.succeeded for a in recent):
        return None
    until = recent[0].attempted_at + window
    return until if until > now else None


def record_attempt(
    db: Session, email: str, scope: AuthScope, succeeded: bool, ip_address: str | None
) -> None:
    db.add(
        LoginAttempt(
            email=email,
            scope=scope,
            succeeded=succeeded,
            # The column holds an IPv6 address at most; anything longer is not one.
            ip_address=ip_address[:45] if ip_address else ip_address,
            attempted_at=datetime.now(UTC),
        )
    )
    db.commit()
