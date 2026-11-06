"""Identity's data model: accounts, profiles, sessions, reset links, sign-in attempts,
the administrators' activity log, and the outbox (SCRUM-72, moved from the monolith).

Foreign keys and cascades stay as they were inside Identity. Nothing here refers to
another service's tables: other services know a user only by its id (a plain UUID), from
the identity.user.* events.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy import (
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.platform.outbox import define_outbox_table

# --- Enumerations -------------------------------------------------------------------------


class UserRole(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"


class UserType(str, enum.Enum):
    """Self-reported at registration (SCRUM-61). Administrators have none."""

    NEWCOMER = "newcomer"
    SINGAPOREAN = "singaporean"


class AdminAction(str, enum.Enum):
    """What happened to an administrator account, for the activity log (SCRUM-81)."""

    INVITED = "invited"
    INVITE_RESENT = "invite_resent"
    JOINED = "joined"  # chose a password from an invite
    INVITE_CANCELLED = "invite_cancelled"
    REMOVED = "removed"
    RESTORED = "restored"
    ADDED = "added"  # with `python -m app.cli create-admin`


class AuthScope(str, enum.Enum):
    """Which front end a session or reset link belongs to. They never mix."""

    APP = "app"
    ADMIN = "admin"


def _enum(enum_cls: type[enum.Enum], name: str) -> Enum:
    # Stored as VARCHAR + CHECK rather than a native Postgres enum, so adding a value
    # later is a one-line migration instead of an ALTER TYPE.
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        length=20,
        values_callable=lambda members: [m.value for m in members],
        validate_strings=True,
        create_constraint=True,
    )


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def _updated_at() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# --- Accounts -----------------------------------------------------------------------------


class User(Base):
    """Main-app users and administrators share one table, separated by `role`."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Always stored lower-case (see app.auth.normalise_email), so the unique index is
    # effectively case-insensitive.
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    # None for an account created with Google that has never had a password (SCRUM-92).
    password_hash: Mapped[str | None] = mapped_column(String(255))
    # Google's own id for the account ("sub"), set when someone signs in with Google
    # (SCRUM-92). Google's id rather than Firebase's, so links survive leaving Firebase.
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True)
    role: Mapped[UserRole] = mapped_column(
        _enum(UserRole, "user_role"), default=UserRole.USER, nullable=False
    )
    user_type: Mapped[UserType | None] = mapped_column(_enum(UserType, "user_type"))
    privacy_agreed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    privacy_notice_version: Mapped[str | None] = mapped_column(String(32))
    # An administrator who has been invited and has not yet chosen a password (SCRUM-81).
    # Set again by each new invite link, so it is when the latest one was sent.
    invited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # An administrator removed from the portal (SCRUM-81). The account is kept, closed, so
    # it can be restored and the activity log still names it; it cannot sign in anywhere.
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # When the introduction was finished or skipped (SCRUM-94); empty until then.
    intro_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    profile: Mapped["Profile | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )

    @property
    def is_removed(self) -> bool:
        return self.removed_at is not None

    @property
    def is_admin(self) -> bool:
        """An administrator who can use the portal: removed ones no longer count."""
        return self.role == UserRole.ADMIN and not self.is_removed

    @property
    def has_password(self) -> bool:
        return self.password_hash is not None

    @property
    def google_linked(self) -> bool:
        return self.google_sub is not None


class Profile(Base):
    """Matching preferences collected in onboarding (SCRUM-14)."""

    __tablename__ = "profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    neighbourhood: Mapped[str | None] = mapped_column(String(120))
    interests: Mapped[list[str]] = mapped_column(
        ARRAY(String(60)), server_default=sql_text("'{}'"), nullable=False
    )
    languages: Mapped[list[str]] = mapped_column(
        ARRAY(String(60)), server_default=sql_text("'{}'"), nullable=False
    )
    updated_at: Mapped[datetime] = _updated_at()

    user: Mapped[User] = relationship(back_populates="profile")


# --- Authentication support ---------------------------------------------------------------


class AuthSession(Base):
    """A signed-in browser. The cookie holds a random token; only its hash is stored."""

    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scope: Mapped[AuthScope] = mapped_column(_enum(AuthScope, "auth_scope"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = _created_at()
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped[User] = relationship()


class PasswordResetToken(Base):
    """A one-time password reset link (SCRUM-63, SCRUM-69). Only the hash is stored."""

    __tablename__ = "password_reset_tokens"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scope: Mapped[AuthScope] = mapped_column(_enum(AuthScope, "auth_scope"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()

    user: Mapped[User] = relationship()


class LoginAttempt(Base):
    """Every sign-in attempt, used to block repeated failures (SCRUM-62 AC5, SCRUM-68 AC5)."""

    __tablename__ = "login_attempts"
    __table_args__ = (Index("ix_login_attempts_lookup", "email", "scope", "attempted_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    scope: Mapped[AuthScope] = mapped_column(_enum(AuthScope, "auth_scope"), nullable=False)
    succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AdminEvent(Base):
    """One change to an administrator account, for the Administrators page (SCRUM-81).

    Rows are only ever added. `actor_id` is who made the change: empty when the account
    holder did it themselves (joined, or asked for a new invite link) or it came from the
    command line.
    """

    __tablename__ = "admin_events"

    id: Mapped[uuid.UUID] = _uuid_pk()
    action: Mapped[AdminAction] = mapped_column(_enum(AdminAction, "admin_action"), nullable=False)
    admin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    admin: Mapped[User] = relationship(foreign_keys=[admin_id])
    actor: Mapped[User | None] = relationship(foreign_keys=[actor_id])


# --- Events -------------------------------------------------------------------------------

# identity.* events, written in the same transaction as the change (app/events.py) and
# published by the relay thread (app/platform/outbox.py).
outbox = define_outbox_table(Base.metadata)
