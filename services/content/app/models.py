"""Content's data model: topics, lessons and their versions, media, reported problems and the
aptitude question bank, plus the outbox its events leave through.

Moved from the monolith's models.py (see docs/data-model.md for the reasoning behind each
choice). What changed with the split (docs/architecture/detailed-plan.md, section 2.2):

- no foreign keys to users: `published_by`, `created_by`, `reporter_id` and `resolved_by`
  are plain UUIDs, nulled when Identity says a user was deleted (app/consumers.py).
- `topics.version`, `lessons.version` and `aptitude_questions.version` order the events
  each aggregate publishes (contracts/README.md, "Ordering"). They are bumped in the same
  transaction, and under the same row lock, as the change the event describes.
- `topics.assessed_at` is set when a topic first gets an aptitude question and never
  cleared: such a topic can never be deleted, even after its questions move elsewhere.
- `aptitude_bank_state` is one row whose `revision` orders content.aptitude_bank.changed.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.platform.outbox import define_outbox_table

# --- Enumerations -------------------------------------------------------------------------


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


# --- Levels (SCRUM-110) ----------------------------------------------------------------------

# Lessons and aptitude questions share one scale of Level 1 to 5 (Epic 6, SCRUM-93).
MIN_LEVEL = 1
MAX_LEVEL = 5


def _level_check(column: str = "level", lowest: int = MIN_LEVEL) -> CheckConstraint:
    return CheckConstraint(f"{column} BETWEEN {lowest} AND {MAX_LEVEL}", name=f"{column}_range")


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


def _version(start: int) -> Mapped[int]:
    """The aggregate's event version (contracts/README.md, "Ordering")."""
    return mapped_column(
        BigInteger, nullable=False, default=start, server_default=sql_text(str(start))
    )


# --- Content ------------------------------------------------------------------------------


class Topic(Base):
    """A cultural topic, shown as one progress circle on the landing page (SCRUM-57).

    `archived_at` is empty for an active topic and holds the time it was archived
    otherwise. An archived topic is hidden from users but keeps its lessons, their
    completions and its name (the unique index below still covers it). A topic that never
    had a lesson or an aptitude question can be deleted instead.

    `position` is the order administrators set (SCRUM-66), which is also the order of
    the circles users see. It is a sort key, not unique: reads break ties by `created_at`,
    so a gap or a duplicate can never break a page.

    `description` is a line or two shown under the name on the topic's page (SCRUM-86).
    Empty means the topic has none; it is never null, like a lesson's `summary`.

    `version` starts at 1 (content.topic.changed on create) and `assessed_at` is set once,
    by its first aptitude question (see the module docstring).
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
    assessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = _version(1)
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

    `level` (1 to 5) decides which users are exempted from the lesson (SCRUM-104); every
    user still sees it. It is chosen when the lesson is created and can change only until
    the lesson is first published, so nobody's exemptions shift afterwards (SCRUM-103).

    `version` is 0 until the first publish: a lesson that was never published is never
    sent to Learning (content.lesson.changed), so it has no event version yet.
    """

    __tablename__ = "lessons"
    __table_args__ = (
        Index("ix_lessons_topic_id_position", "topic_id", "position"),
        _level_check(),
    )

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
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=MIN_LEVEL)
    version: Mapped[int] = _version(0)
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
    # The administrator (Identity's user id); nulled if that account is deleted.
    published_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

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
    # The administrator who uploaded it (Identity's user id); nulled if deleted.
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = _created_at()


# --- Reported problems --------------------------------------------------------------------


class LessonReport(Base):
    """A problem a learner reported on one card of a lesson (SCRUM-82), for administrators to
    fix or dismiss (SCRUM-83).

    It names the version and the card it was sent from (AC3): card ids stay the same across
    edits, so the editor can open the same card in today's draft. Reports are never deleted
    when dealt with, only marked Fixed or Dismissed.

    `reporter_id` is kept so a report belongs to someone, but administrators are never shown
    who sent it (SCRUM-83 AC1). It and `resolved_by` are Identity's user ids, nulled when
    that account is deleted.
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
    reporter_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    status: Mapped[ReportStatus] = mapped_column(
        _enum(ReportStatus, "report_status"),
        nullable=False,
        default=ReportStatus.OPEN,
        server_default=ReportStatus.OPEN.value,
    )
    created_at: Mapped[datetime] = _created_at()
    # When, and by which administrator, it was marked Fixed or Dismissed.
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    lesson: Mapped[Lesson] = relationship()
    version: Mapped[LessonVersion] = relationship()


# --- Aptitude question bank (Epic 6) --------------------------------------------------------


class AptitudeQuestion(Base):
    """One question in the aptitude quiz's bank (SCRUM-96), kept apart from lesson questions.

    `options` is a list of {"id", "text"}; `correct_option_id` names exactly one of them,
    which the database checks. A quiz gives one active question at each level (SCRUM-97),
    so `level` is required and, like a lesson's, never changed once set.

    Questions are deactivated rather than deleted. The quiz itself runs in Learning, from
    the content.aptitude_question.changed events this bank publishes.
    """

    __tablename__ = "aptitude_questions"
    __table_args__ = (
        _level_check(),
        CheckConstraint("jsonb_typeof(options) = 'array'", name="options_list"),
        CheckConstraint(
            "options @> jsonb_build_array(jsonb_build_object('id', correct_option_id))",
            name="correct_option_listed",
        ),
        Index("ix_aptitude_questions_level_is_active", "level", "is_active"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    # Stable identifier for a question loaded from content/aptitude_questions.yaml.
    # Admin-authored questions leave this empty.
    seed_key: Mapped[str | None] = mapped_column(String(120), unique=True)
    topic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("topics.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list] = mapped_column(JSONB, nullable=False)
    correct_option_id: Mapped[str] = mapped_column(String(40), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=sql_text("true")
    )
    version: Mapped[int] = _version(1)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    topic: Mapped[Topic] = relationship()


class AptitudeBankState(Base):
    """One row (id 1): `revision` orders content.aptitude_bank.changed. Every bank event
    takes the next revision with an upsert, whose row lock serialises concurrent changes."""

    __tablename__ = "aptitude_bank_state"
    __table_args__ = (CheckConstraint("id = 1", name="single_row"),)

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False, default=1)
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)


class ErasedUser(Base):
    """An account deleted in Identity (identity.user.deleted), kept for good so a report
    still in flight when the event is handled can't record the id again (app/erasure.py).
    Only the id: no personal data."""

    __tablename__ = "erased_users"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    erased_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# --- Events ---------------------------------------------------------------------------------

outbox = define_outbox_table(Base.metadata)
