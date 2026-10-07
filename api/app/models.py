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
    LargeBinary,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
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


class MediaKind(str, enum.Enum):
    IMAGE = "image"
    AUDIO = "audio"


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
    """A cultural topic, shown as one progress circle on the landing page (SCRUM-57).

    `archived_at` is empty for an active topic and holds the time it was archived
    otherwise. An archived topic is hidden from users but keeps its lessons, their
    completions and its name (the unique index below still covers it). A topic with no
    lessons at all can be deleted instead.

    `position` is the order administrators set (SCRUM-66), which is also the order of
    the circles users see. It is a sort key, not unique: reads break ties by `created_at`,
    so a gap or a duplicate can never break a page.
    """

    __tablename__ = "topics"
    __table_args__ = (
        # SCRUM-57 AC4: no two topics with the same name, ignoring case.
        Index("uq_topics_name_lower", func.lower(sql_text("name")), unique=True),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Defaults to 0 so rows built directly (tests, scripts) still work; the API appends.
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    lessons: Mapped[list["Lesson"]] = relationship(back_populates="topic")


class Lesson(Base):
    """A short lesson: a deck of cards with at least one question (SCRUM-19, SCRUM-64).

    The cards are a JSON document (see app/lesson_doc.py). `draft` is the working copy
    administrators edit; publishing copies it into a new `LessonVersion`, which is what
    users see. Editing a published lesson therefore never changes what users see until it
    is published again (SCRUM-52), and every version is kept, so a learner's history can
    always show the version they answered.

    `title` and `summary` belong to the draft too; each version keeps its own copy.
    `topic_id` and `position` are not versioned: they place the lesson rather than make it
    up, so moving a lesson takes effect straight away, like reordering.

    `topic_id` may be empty while a lesson has never been published; publishing requires it
    (SCRUM-56). Each lesson belongs to exactly one topic (the assumption in SCRUM-56).

    `position` orders lessons within their topic, and lessons with no topic among
    themselves (SCRUM-66). Like `Topic.position` it is a sort key, not unique.

    `key` names a lesson loaded from a file in content/, so loading the file again updates
    that lesson instead of adding another.
    """

    __tablename__ = "lessons"
    __table_args__ = (Index("ix_lessons_topic_id_position", "topic_id", "position"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    key: Mapped[str | None] = mapped_column(String(200), unique=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    # One line saying what the lesson is about, for lesson lists and suggestions.
    summary: Mapped[str] = mapped_column(String(160), nullable=False, default="", server_default="")
    draft: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=lambda: {"cards": []},
        server_default=sql_text("""'{"cards": []}'::jsonb"""),
    )
    # True when the draft differs from the latest version: there is something to publish.
    # Always false for a lesson that has never been published.
    has_unpublished_changes: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sql_text("false")
    )
    topic_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("topics.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[LessonStatus] = mapped_column(
        _enum(LessonStatus, "lesson_status"), default=LessonStatus.DRAFT, nullable=False, index=True
    )
    # When it last went live (published or restored), and when it was last withdrawn.
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = _created_at()
    # Indexed because the admin lesson list sorts by it (SCRUM-66 AC3). Reordering
    # deliberately leaves it alone: moving a lesson is not editing it.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        index=True,
    )

    topic: Mapped[Topic | None] = relationship(back_populates="lessons")
    versions: Mapped[list["LessonVersion"]] = relationship(
        back_populates="lesson",
        cascade="all, delete-orphan",
        order_by="LessonVersion.number",
    )


class LessonVersion(Base):
    """One published state of a lesson, kept for good (SCRUM-52).

    Numbers count up from 1 per lesson. The latest version is what users see while the
    lesson is published, and what restoring a withdrawn lesson brings back.
    """

    __tablename__ = "lesson_versions"
    __table_args__ = (UniqueConstraint("lesson_id", "number"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    lesson_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    doc: Mapped[dict] = mapped_column(JSONB, nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    lesson: Mapped[Lesson] = relationship(back_populates="versions")


class MediaAsset(Base):
    """An image or audio file a lesson card uses (SCRUM-19).

    The file itself is kept in the database, so media is backed up, reset and moved with
    everything else and needs no setup. Files never change once stored: a new upload is a
    new asset, so browsers can cache them for good. Uploading the same file twice gives back
    the first asset (`sha256` is of the file as uploaded).

    Images are stored as WebP at most 1600px wide, with their EXIF data (which can include
    where a photo was taken) removed. `placeholder` is a tiny blurred copy to show while the
    image loads, and `color` its main colour, which the lesson player tints cards with.
    """

    __tablename__ = "media_assets"

    id: Mapped[uuid.UUID] = _uuid_pk()
    kind: Mapped[MediaKind] = mapped_column(_enum(MediaKind, "media_kind"), nullable=False)
    mime: Mapped[str] = mapped_column(String(60), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # Only loaded when the file is served, never when lessons are listed or edited.
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, deferred=True)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    placeholder: Mapped[str | None] = mapped_column(String(2000))
    color: Mapped[str | None] = mapped_column(String(7))
    filename: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = _created_at()


# --- Progress -----------------------------------------------------------------------------


class LessonCompletion(Base):
    """One row per lesson a user has finished (SCRUM-16).

    A row is written the first time the user answers the lesson's quiz question, right or
    wrong (AC3), so this table is the "completed" half of every progress circle. Whether
    they were right is kept separately in `answered_correctly`, which holds the *best*
    result so far: a later wrong answer never clears an earlier correct one (AC5).

    The unique constraint is what makes completion count once however many times the quiz
    is retaken, and makes a repeated submission harmless (AC5, AC6).
    """

    __tablename__ = "lesson_completions"
    __table_args__ = (UniqueConstraint("user_id", "lesson_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # A withdrawn lesson stays in the user's history (SCRUM-52), so this is never deleted
    # when a lesson leaves the published set; the progress query filters by status instead.
    lesson_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    answered_correctly: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # When the lesson was first completed. Retakes update `updated_at`, not this.
    completed_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    user: Mapped[User] = relationship()
    lesson: Mapped[Lesson] = relationship()


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
