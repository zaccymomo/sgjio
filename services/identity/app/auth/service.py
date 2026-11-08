"""Registering and signing in: credentials, lockout and the admin-only rule together."""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import events
from app.auth import normalise_email
from app.auth.lockout import blocked_until, record_attempt
from app.models import AuthScope, User, UserRole, UserType
from app.privacy import NOTICE_VERSION
from app.security import (
    hash_password,
    password_needs_rehash,
    password_rule_failures,
    verify_password,
)


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
    which emails are administrators (SCRUM-68 AC2). A removed administrator fails the same
    way on both front ends (SCRUM-81).
    """
    email = normalise_email(email)

    until = blocked_until(db, email, scope)
    if until is not None:
        return SignInResult(blocked_until=until)

    user = db.scalar(select(User).where(User.email == email))
    password_ok = verify_password(password, user.password_hash if user else None)
    allowed = (
        user is not None
        and password_ok
        and not user.is_removed
        and (scope != AuthScope.ADMIN or user.is_admin)
    )

    record_attempt(db, email, scope, succeeded=allowed, ip_address=ip_address)
    if not allowed:
        # This failure may be the one that starts a block; report it straight away.
        return SignInResult(blocked_until=blocked_until(db, email, scope))

    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        db.commit()
    return SignInResult(user=user)


# --- Registration (SCRUM-61) --------------------------------------------------------------


@dataclass(frozen=True)
class FieldProblem:
    """Why a registration was refused, named so the form can highlight the right field."""

    field: str
    code: str
    message: str
    #: One message per broken password rule, so the user is told the rule (AC4).
    failures: list[str] = field(default_factory=list)


@dataclass
class RegisterResult:
    user: User | None = None
    problem: FieldProblem | None = None

    @property
    def ok(self) -> bool:
        return self.user is not None


def new_password_problem(password: str, password_confirmation: str) -> FieldProblem | None:
    """Why a new password is refused, or None. Shared by registration (SCRUM-61 AC4-AC5)
    and the reset-password form (SCRUM-63 AC4, SCRUM-69 AC4)."""
    if password != password_confirmation:
        return FieldProblem(
            field="password_confirmation",
            code="password_mismatch",
            message="The passwords do not match.",
        )
    failures = password_rule_failures(password)
    if failures:
        return FieldProblem(
            field="password",
            code="weak_password",
            message=" ".join(failures),
            failures=failures,
        )
    return None


# Registration does say when an email is already in use, because the person needs to be
# offered the sign-in page instead (AC2). Sign-in and "forgot password" deliberately do
# not (SCRUM-62 AC2, SCRUM-63), so those pages cannot be used to check who has an account.
EMAIL_TAKEN = FieldProblem(
    field="email",
    code="email_taken",
    message="That email is already registered.",
)


def register(
    db: Session,
    name: str,
    email: str,
    password: str,
    password_confirmation: str,
    user_type: UserType,
    privacy_notice_version: str,
) -> RegisterResult:
    """Create a main-app account, or return the one problem that stopped it.

    Email format and the required fields are already checked by `RegisterRequest`; this
    covers the rules that need the database or the password policy. New accounts are
    always ordinary users: administrators are invited from the admin portal (SCRUM-81).
    """
    email = normalise_email(email)

    problem = new_password_problem(password, password_confirmation)
    if problem is not None:
        return RegisterResult(problem=problem)

    if privacy_notice_version != NOTICE_VERSION:
        return RegisterResult(
            problem=FieldProblem(
                field="privacy_consent",
                code="privacy_notice_changed",
                message=(
                    "The privacy notice has changed. "
                    "Please read the current version and agree again."
                ),
            )
        )

    if db.scalar(select(User.id).where(User.email == email)) is not None:
        return RegisterResult(problem=EMAIL_TAKEN)

    user = User(
        name=name.strip(),
        email=email,
        password_hash=hash_password(password),
        role=UserRole.USER,
        user_type=user_type,
        privacy_agreed_at=datetime.now(UTC),
        privacy_notice_version=NOTICE_VERSION,
    )
    db.add(user)
    try:
        # identity.user.registered goes out in the same transaction as the account.
        events.user_registered(db, user)
        db.commit()
    except IntegrityError:
        # The only unique constraint on users is the email, so two people registering the
        # same address at the same moment lands here rather than raising a 500.
        db.rollback()
        return RegisterResult(problem=EMAIL_TAKEN)
    db.refresh(user)
    return RegisterResult(user=user)
