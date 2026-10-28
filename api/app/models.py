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


class ReportReason(str, enum.Enum):
    """Why a learner reported a card (SCRUM-82 AC1)."""

    WRONG = "wrong"  # wrong or outdated
    INSENSITIVE = "insensitive"
    TYPO = "typo"
    MEDIA = "media"  # image or audio not working
    OTHER = "other"


class ReportStatus(str, enum.Enum):
    """An open report waits for an administrator; the other two are kept for reference
    (SCRUM-83 AC3)."""

    OPEN = "open"
    FIXED = "fixed"
    DISMISSED = "dismissed"


class MediaKind(str, enum.Enum):
    IMAGE = "image"
    AUDIO = "audio"


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
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
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

    `description` is a line or two shown under the name on the topic's page (SCRUM-86).
    Empty means the topic has none; it is never null, like a lesson's `summary`.
    """

    __tablename__ = "topics"
    __table_args__ = (
        # SCRUM-57 AC4: no two topics with the same name, ignoring case.
        Index("uq_topics_name_lower", func.lower(sql_text("name")), unique=True),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(
        String(200), nullable=False, default="", server_default=""
    )
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

    A row is written the first time the user finishes the lesson's deck, however many of its
    questions they got right (AC3), so this table is the "completed" half of every progress
    circle. How well they did is kept separately as their *best* score so far: first-try
    correct answers out of the scored questions, compared as a percentage, with a tie
    keeping the most recent attempt (docs/decisions.md). A worse retake never lowers it
    (AC5).

    The unique constraint is what makes completion count once however many times the lesson
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
    # The best score so far. A lesson whose questions are all one-option taps has nothing
    # to score: 0 of 0, which counts as all correct.
    best_correct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    best_scored: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # The attempt that set the best score (SCRUM-54). Empty for rows written
    # before attempts were recorded.
    best_attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lesson_attempts.id", ondelete="SET NULL")
    )
    # When the lesson was first completed. Retakes update `updated_at`, not this.
    completed_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    user: Mapped[User] = relationship()
    lesson: Mapped[Lesson] = relationship()

    @property
    def mastered(self) -> bool:
        """Every scored question right first time, in the best attempt."""
        return self.best_correct == self.best_scored


class LessonAttempt(Base):
    """One run through a lesson's deck (SCRUM-16), started at its first answer.

    An attempt is tied to the version the learner was shown, so its answers are always
    checked against the questions they saw, even if a new version is published meanwhile.
    It is finished once every question has been answered and the learner reaches the end;
    only then does it count towards completion and the best score. Unfinished attempts are
    kept but count for nothing (SCRUM-15 AC4).
    """

    __tablename__ = "lesson_attempts"
    __table_args__ = (Index("ix_lesson_attempts_user_id_lesson_id", "user_id", "lesson_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    lesson_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lesson_versions.id", ondelete="CASCADE"), nullable=False
    )
    started_at: Mapped[datetime] = _created_at()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set when finished: first-try correct answers out of the scored questions.
    correct: Mapped[int | None] = mapped_column(Integer)
    scored: Mapped[int | None] = mapped_column(Integer)

    version: Mapped[LessonVersion] = relationship()
    answers: Mapped[list["AttemptAnswer"]] = relationship(
        back_populates="attempt", cascade="all, delete-orphan", order_by="AttemptAnswer.answered_at"
    )


class AttemptAnswer(Base):
    """The answer given to one question in one attempt. Only the first counts: the key
    means a second submission for the same question records nothing (SCRUM-16 AC6)."""

    __tablename__ = "attempt_answers"

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lesson_attempts.id", ondelete="CASCADE"), primary_key=True
    )
    # The ids from the lesson document (app/lesson_doc.py), which stay the same across edits.
    question_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    option_id: Mapped[str] = mapped_column(String(40), nullable=False)
    correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # False for a one-option tap, which is left out of the score.
    scored: Mapped[bool] = mapped_column(Boolean, nullable=False)
    answered_at: Mapped[datetime] = _created_at()

    attempt: Mapped[LessonAttempt] = relationship(back_populates="answers")


# --- Reported problems --------------------------------------------------------------------


class LessonReport(Base):
    """A problem a learner reported on one card of a lesson (SCRUM-82), for administrators to
    fix or dismiss (SCRUM-83).

    It names the version and the card it was sent from (AC3): card ids stay the same across
    edits, so the editor can open the same card in today's draft. Reports are never deleted
    when dealt with, only marked Fixed or Dismissed.

    `reporter_id` is kept so a report belongs to someone, but administrators are never shown
    who sent it (SCRUM-83 AC1).
    """

    __tablename__ = "lesson_reports"
    __table_args__ = (Index("ix_lesson_reports_status_created_at", "status", "created_at"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    lesson_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lesson_versions.id", ondelete="CASCADE"), nullable=False
    )
    card_id: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[ReportReason] = mapped_column(
        _enum(ReportReason, "report_reason"), nullable=False
    )
    note: Mapped[str] = mapped_column(String(500), nullable=False, default="", server_default="")
    reporter_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    status: Mapped[ReportStatus] = mapped_column(
        _enum(ReportStatus, "report_status"),
        nullable=False,
        default=ReportStatus.OPEN,
        server_default=ReportStatus.OPEN.value,
    )
    created_at: Mapped[datetime] = _created_at()
    # When, and by which administrator, it was marked Fixed or Dismissed.
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    lesson: Mapped[Lesson] = relationship()
    version: Mapped[LessonVersion] = relationship()


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
