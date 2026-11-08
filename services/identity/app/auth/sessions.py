"""Server-side sessions stored in the auth_sessions table.

The browser keeps a random token in an HttpOnly cookie. The database keeps only the
token's hash, the user, the front end it belongs to (scope) and when it expires. A
session is extended each time it is used, so people who keep using SGJio stay signed in,
and it expires after a period without use.
"""

from datetime import UTC, datetime, timedelta

from fastapi import Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AuthScope, AuthSession, User
from app.security import hash_token, new_token

# Cookie names differ per front end. Browsers share cookies across ports on localhost, so
# one shared name would let a main-app session leak into the admin portal.
COOKIE_NAMES = {AuthScope.APP: "sgjio_session", AuthScope.ADMIN: "sgjio_admin_session"}
# Each cookie is only sent to its own part of the API.
COOKIE_PATHS = {AuthScope.APP: "/api", AuthScope.ADMIN: "/api/admin"}

# Avoid a database write on every request: only extend when this much time has passed.
_EXTEND_AFTER = timedelta(minutes=1)


def session_lifetime(scope: AuthScope) -> timedelta:
    settings = get_settings()
    if scope == AuthScope.ADMIN:
        return timedelta(hours=settings.admin_session_hours)
    return timedelta(days=settings.app_session_days)


def _now() -> datetime:
    return datetime.now(UTC)


def create_session(db: Session, user: User, scope: AuthScope) -> tuple[str, AuthSession]:
    """Start a session and return the raw token to put in the cookie."""
    token = new_token()
    now = _now()
    auth_session = AuthSession(
        user_id=user.id,
        scope=scope,
        token_hash=hash_token(token),
        last_seen_at=now,
        expires_at=now + session_lifetime(scope),
    )
    db.add(auth_session)
    db.commit()
    return token, auth_session


def resolve_session(db: Session, token: str | None, scope: AuthScope) -> AuthSession | None:
    """Return the live session for a cookie token, extending it, or None."""
    if not token:
        return None
    auth_session = db.scalar(
        select(AuthSession).where(
            AuthSession.token_hash == hash_token(token), AuthSession.scope == scope
        )
    )
    if auth_session is None:
        return None
    now = _now()
    if auth_session.expires_at <= now:
        db.delete(auth_session)
        db.commit()
        return None
    if now - auth_session.last_seen_at >= _EXTEND_AFTER:
        auth_session.last_seen_at = now
        auth_session.expires_at = now + session_lifetime(scope)
        db.commit()
    return auth_session


def end_session(db: Session, token: str | None, scope: AuthScope) -> None:
    """Sign out one browser (SCRUM-59, SCRUM-68 AC8)."""
    if not token:
        return
    db.execute(
        delete(AuthSession).where(
            AuthSession.token_hash == hash_token(token), AuthSession.scope == scope
        )
    )
    db.commit()


def end_all_sessions(db: Session, user: User) -> None:
    """Sign a user out everywhere, e.g. after a password reset."""
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    db.commit()


# --- Cookies ------------------------------------------------------------------------------


def set_session_cookie(response: Response, scope: AuthScope, token: str) -> None:
    """Persistent cookie, so closing the tab keeps you signed in (SCRUM-62 AC6, SCRUM-68 AC7).

    It is re-sent on every signed-in request so the browser's copy keeps pace with the
    server-side expiry, which moves forward each time the session is used.
    """
    response.set_cookie(
        key=COOKIE_NAMES[scope],
        value=token,
        max_age=int(session_lifetime(scope).total_seconds()),
        path=COOKIE_PATHS[scope],
        httponly=True,  # not readable from JavaScript
        samesite="lax",
        secure=get_settings().cookie_secure,
    )


def clear_session_cookie(response: Response, scope: AuthScope) -> None:
    response.delete_cookie(
        key=COOKIE_NAMES[scope],
        path=COOKIE_PATHS[scope],
        httponly=True,
        samesite="lax",
        secure=get_settings().cookie_secure,
    )
