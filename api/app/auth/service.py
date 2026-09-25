"""Sign-in for either front end: credentials, lockout and the admin-only rule together."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import normalise_email
from app.auth.lockout import blocked_until, record_attempt
from app.models import AuthScope, User
from app.security import hash_password, password_needs_rehash, verify_password


@dataclass
class SignInResult:
    user: User | None = None
    # Set when the email is temporarily blocked (SCRUM-62 AC5, SCRUM-68 AC5).
    blocked_until: datetime | None = None

    @property
    def ok(self) -> bool:
        return self.user is not None


def sign_in(
    db: Session, email: str, password: str, scope: AuthScope, ip_address: str | None = None
) -> SignInResult:
    """Check credentials for the main app or the admin portal.

    For the admin portal, a correct password on a non-administrator account fails in
    exactly the same way as a wrong password, so the page cannot be used to discover
    which emails are administrators (SCRUM-68 AC2).
    """
    email = normalise_email(email)

    until = blocked_until(db, email, scope)
    if until is not None:
        return SignInResult(blocked_until=until)

    user = db.scalar(select(User).where(User.email == email))
    password_ok = verify_password(password, user.password_hash if user else None)
    allowed = user is not None and password_ok and (scope != AuthScope.ADMIN or user.is_admin)

    record_attempt(db, email, scope, succeeded=allowed, ip_address=ip_address)
    if not allowed:
        # This failure may be the one that starts a block; report it straight away.
        return SignInResult(blocked_until=blocked_until(db, email, scope))

    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        db.commit()
    return SignInResult(user=user)
