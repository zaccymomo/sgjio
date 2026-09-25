"""Core data model for SGJio (SCRUM-72).

One table per entity the Sprint 1 stories write to. See docs/data-model.md for the
diagram and the reasoning behind each choice.
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
    Text,
    func,
)
from sqlalchemy import (
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

# --- Enumerations -------------------------------------------------------------------------


class UserRole(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"


class UserType(str, enum.Enum):
    """Self-reported at registration (SCRUM-61). Administrators have none."""

    NEWCOMER = "newcomer"
    SINGAPOREAN = "singaporean"


class LessonStatus(str, enum.Enum):
    """SCRUM-66 lists these three statuses."""

    DRAFT = "draft"
    PUBLISHED = "published"
    WITHDRAWN = "withdrawn"


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
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        _enum(UserRole, "user_role"), default=UserRole.USER, nullable=False
    )
    user_type: Mapped[UserType | None] = mapped_column(_enum(UserType, "user_type"))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    profile: Mapped["Profile | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN


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


# --- Content ------------------------------------------------------------------------------


class Topic(Base):
    """A cultural topic, shown as one progress circle on the landing page (SCRUM-57)."""

    __tablename__ = "topics"
    __table_args__ = (
        # SCRUM-57 AC4: no two topics with the same name, ignoring case.
        Index("uq_topics_name_lower", func.lower(sql_text("name")), unique=True),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    lessons: Mapped[list["Lesson"]] = relationship(back_populates="topic")


class Lesson(Base):
    """A short lesson ending in one quiz question (SCRUM-58, SCRUM-64).

    `topic_id` may be empty while a lesson is a draft; publishing requires it (SCRUM-56).
    Each lesson belongs to exactly one topic (the assumption in SCRUM-56).
    """

    __tablename__ = "lessons"

    id: Mapped[uuid.UUID] = _uuid_pk()
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    topic_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("topics.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[LessonStatus] = mapped_column(
        _enum(LessonStatus, "lesson_status"), default=LessonStatus.DRAFT, nullable=False, index=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()
    # Indexed because the admin lesson list sorts by it (SCRUM-66 AC3).
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        index=True,
    )

    topic: Mapped[Topic | None] = relationship(back_populates="lessons")
    question: Mapped["QuizQuestion | None"] = relationship(
        back_populates="lesson", cascade="all, delete-orphan", uselist=False
    )


class QuizQuestion(Base):
    """The single quiz question at the end of a lesson (SCRUM-15)."""

    __tablename__ = "quiz_questions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    lesson_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lessons.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Shown after answering: why the correct option is the norm (SCRUM-15 AC6-7).
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    lesson: Mapped[Lesson] = relationship(back_populates="question")
    options: Mapped[list["QuizOption"]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="QuizOption.position",
    )


class QuizOption(Base):
    __tablename__ = "quiz_options"
    __table_args__ = (
        # Only one option per question can be marked correct (SCRUM-15 AC2).
        Index(
            "uq_quiz_options_one_correct",
            "question_id",
            unique=True,
            postgresql_where=sql_text("is_correct"),
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quiz_questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(String(300), nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    question: Mapped[QuizQuestion] = relationship(back_populates="options")


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
