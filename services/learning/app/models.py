"""Learning's tables: its own data, and the read models other services' events fill in.

Own data (written by learners' requests):
- lesson_attempts, attempt_answers, lesson_completions (SCRUM-15, SCRUM-16)
- aptitude_attempts, topic_exemptions (Epic 6, SCRUM-113)
- generated_lessons, generated_lesson_attempts, generated_lesson_answers,
  generated_lesson_reports (AI-generated lessons, docs/ai-lessons-plan.md)
- outbox: the events Learning publishes (learning.lesson_generation.requested)

Ids of users, lessons, versions and topics are plain UUIDs: they belong to Identity and
Content, so there are no foreign keys to them. Foreign keys inside Learning stay.

Read models (written only by app/consumers.py, from contracts/events):
- learnable_topics       content.topic.changed / deleted       version-guarded, tombstoned
- learnable_lessons      content.lesson.changed                version-guarded
- lesson_decks           content.lesson_version.published      insert if absent (immutable)
- quiz_questions         content.aptitude_question.changed     version-guarded
- quiz_bank              content.aptitude_bank.changed         revision-guarded, one row
- learners               identity.user.registered (role user)  insert if absent, never if erased
- erased_learners        identity.user.deleted                 the erasure tombstone, for good
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.platform.outbox import define_outbox_table

# --- Levels (SCRUM-110) ----------------------------------------------------------------------

# Lessons and aptitude questions share one scale of Level 1 to 5 (Epic 6, SCRUM-93). Users
# have no level of their own: each topic has an exemption level instead (SCRUM-113).
MIN_LEVEL = 1
MAX_LEVEL = 5
# 0 means nothing in the topic is exempted: the user missed its Level 1 question (SCRUM-99).
NO_EXEMPTION = 0

# The values Identity and Content send (contracts/events). Stored as VARCHAR + CHECK.
USER_TYPES = ("newcomer", "singaporean")
PUBLICATION_STATES = ("published", "withdrawn")
NEWCOMER = "newcomer"
SINGAPOREAN = "singaporean"
PUBLISHED = "published"


def _level_check(column: str = "level", lowest: int = MIN_LEVEL) -> CheckConstraint:
    return CheckConstraint(f"{column} BETWEEN {lowest} AND {MAX_LEVEL}", name=f"{column}_range")


def _one_of(column: str, values: tuple[str, ...], name: str) -> CheckConstraint:
    listed = ", ".join(f"'{value}'" for value in values)
    return CheckConstraint(f"{column} IN ({listed})", name=name)


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def _updated_at() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# --- Progress (own data) --------------------------------------------------------------------


class LessonCompletion(Base):
    """One row per lesson a user has finished (SCRUM-16).

    A row is written the first time the user finishes the lesson's deck, however many of its
    questions they got right (AC3), so this table is the "completed" half of every progress
    circle. How well they did is kept separately as their *best* score so far: first-try
    correct answers out of the scored questions, compared as a percentage, with a tie
    keeping the most recent attempt. A worse retake never lowers it (AC5).

    The unique constraint is what makes completion count once however many times the lesson
    is retaken, and makes a repeated submission harmless (AC5, AC6). A withdrawn lesson stays
    in the user's history (SCRUM-52), so a completion is never deleted when its lesson stops
    being visible; the progress queries filter by visibility instead.
    """

    __tablename__ = "lesson_completions"
    __table_args__ = (UniqueConstraint("user_id", "lesson_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    lesson_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    # The best score so far. A lesson whose questions are all one-option taps has nothing
    # to score: 0 of 0, which counts as all correct.
    best_correct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    best_scored: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # The attempt that set the best score (SCRUM-54). Empty for seeded completions.
    best_attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lesson_attempts.id", ondelete="SET NULL")
    )
    # When the lesson was first completed. Retakes update `updated_at`, not this.
    completed_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    @property
    def mastered(self) -> bool:
        """Every scored question right first time, in the best attempt."""
        return self.best_correct == self.best_scored


class LessonAttempt(Base):
    """One run through a lesson's deck (SCRUM-16), started at its first answer.

    An attempt is tied to the version (deck) the learner was shown, so its answers are always
    checked against the questions they saw, even if a new version is published meanwhile.
    It is finished once every question has been answered and the learner reaches the end;
    only then does it count towards completion and the best score. Unfinished attempts are
    kept but count for nothing (SCRUM-15 AC4).
    """

    __tablename__ = "lesson_attempts"
    __table_args__ = (
        Index("ix_lesson_attempts_user_id_lesson_id", "user_id", "lesson_id"),
        # Lesson insights read every attempt at one lesson.
        Index("ix_lesson_attempts_lesson_id", "lesson_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    lesson_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # A lesson_decks id; decks are never deleted, so it always resolves once delivered.
    version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    started_at: Mapped[datetime] = _created_at()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set when finished: first-try correct answers out of the scored questions.
    correct: Mapped[int | None] = mapped_column(Integer)
    scored: Mapped[int | None] = mapped_column(Integer)

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
    # The ids from the lesson document, which stay the same across edits.
    question_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    option_id: Mapped[str] = mapped_column(String(40), nullable=False)
    correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # False for a one-option tap, which is left out of the score.
    scored: Mapped[bool] = mapped_column(Boolean, nullable=False)
    answered_at: Mapped[datetime] = _created_at()

    attempt: Mapped[LessonAttempt] = relationship(back_populates="answers")


# --- Aptitude quiz (own data, Epic 6) --------------------------------------------------------


class AptitudeAttempt(Base):
    """A user's aptitude quiz (SCRUM-97). The quiz is taken once, so a user has at most one,
    and only a completed quiz is stored (SCRUM-113 AC2, SCRUM-99 AC7): a user who has set up
    their profile and has none has skipped it (SCRUM-98).

    `results` is a list with one entry per question given, in order, each a copy of what
    mattered at the time, so editing or deactivating a question never changes a past result
    (SCRUM-110 AC5). What the quiz gave is in `topic_exemptions`, saved with it.
    """

    __tablename__ = "aptitude_attempts"
    __table_args__ = (CheckConstraint("jsonb_typeof(results) = 'array'", name="results_list"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    # Unique: one completed quiz per user (SCRUM-113 AC2).
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, unique=True)
    taken_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    results: Mapped[list] = mapped_column(JSONB, nullable=False)


class TopicExemption(Base):
    """How far a user is exempted in one topic (SCRUM-113): every published lesson in the
    topic at or below `level` counts as exempted for them (SCRUM-104). 0 exempts nothing.

    Set once, when the aptitude quiz is completed (SCRUM-99 AC6), one row per topic the quiz
    covered. Exempted lessons are worked out from this and each lesson's fixed level
    (`app/exemptions.py`) rather than stored.

    `user_id` refers to the user's quiz, so an exemption can only exist alongside a completed
    quiz. `topic_id` is Content's topic; Content never deletes a topic that has ever had an
    aptitude question (`topics.assessed_at`), so it can't be left pointing at nothing.
    """

    __tablename__ = "topic_exemptions"
    __table_args__ = (
        _level_check(lowest=NO_EXEMPTION),
        ForeignKeyConstraint(["user_id"], ["aptitude_attempts.user_id"], ondelete="CASCADE"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    topic_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, index=True)
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False)


# --- AI-generated lessons (own data, docs/ai-lessons-plan.md) ---------------------------------

# A request is waiting while requested, writing or checking; then ready, failed or cancelled.
GENERATION_WAITING = ("requested", "writing", "checking")
GENERATION_STATUSES = (*GENERATION_WAITING, "ready", "failed", "cancelled")
GENERATION_FOCUSES = ("new", "mistakes")
GENERATION_DIFFICULTIES = ("easier", "right", "harder")
GENERATION_LENGTHS = ("short", "usual")
GENERATION_FAILURES = ("off_topic", "invalid_output", "unsafe", "provider", "timeout")
# What the rating's reasons may be (contracts: the brief's feedback reasons).
RATING_REASONS = (
    "right_level",
    "clear",
    "more_like_this",
    "too_easy",
    "too_hard",
    "not_relevant",
    "something_wrong",
)
# Content's ReportReason, as ReportProblemDialog offers them.
REPORT_REASONS = ("wrong", "insensitive", "typo", "media", "other")


class GeneratedLesson(Base):
    """One learner's request for an AI-generated lesson, and the lesson once it arrives.

    Private to the learner and never counted toward circles, tiers, review or search: no
    progress query reads this table. `version` is the newest generation event applied (0 at
    request; 1 writing, 2 checking, 3 the result), so a stale or repeated event changes
    nothing. `brief` is what was sent to Generation; `covers` the mistakes it was built from.
    """

    __tablename__ = "generated_lessons"
    __table_args__ = (
        Index("ix_generated_lessons_user_id_created_at", "user_id", "created_at"),
        _one_of("status", GENERATION_STATUSES, "status_known"),
        _one_of("focus", GENERATION_FOCUSES, "focus_known"),
        _one_of("difficulty", GENERATION_DIFFICULTIES, "difficulty_known"),
        _one_of("length", GENERATION_LENGTHS, "length_known"),
        _one_of("failure_code", GENERATION_FAILURES, "failure_code_known"),
        _level_check(),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    topic_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="requested")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    focus: Mapped[str] = mapped_column(String(20), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False)
    length: Mapped[str] = mapped_column(String(20), nullable=False)
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    ask: Mapped[str | None] = mapped_column(String(200))
    brief: Mapped[dict] = mapped_column(JSONB, nullable=False)
    covers: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # The lesson, once Generation sent it (generation.lesson.generated).
    title: Mapped[str | None] = mapped_column(String(200))
    summary: Mapped[str | None] = mapped_column(String(160))
    learning_points: Mapped[list | None] = mapped_column(JSONB)
    doc: Mapped[dict | None] = mapped_column(JSONB)
    questions: Mapped[list | None] = mapped_column(JSONB)
    reading_seconds: Mapped[int | None] = mapped_column(Integer)
    failure_code: Mapped[str | None] = mapped_column(String(20))
    # The best finished attempt: first-try correct answers out of the scored questions.
    best_correct: Mapped[int | None] = mapped_column(Integer)
    best_scored: Mapped[int | None] = mapped_column(Integer)
    rating_useful: Mapped[bool | None] = mapped_column(Boolean)
    rating_reasons: Mapped[list | None] = mapped_column(JSONB)
    rated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GeneratedLessonAttempt(Base):
    """One run through a generated lesson, like `lesson_attempts`."""

    __tablename__ = "generated_lesson_attempts"

    id: Mapped[uuid.UUID] = _uuid_pk()
    generated_lesson_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("generated_lessons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    started_at: Mapped[datetime] = _created_at()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    correct: Mapped[int | None] = mapped_column(Integer)
    scored: Mapped[int | None] = mapped_column(Integer)

    answers: Mapped[list["GeneratedLessonAnswer"]] = relationship(
        cascade="all, delete-orphan", order_by="GeneratedLessonAnswer.answered_at"
    )


class GeneratedLessonAnswer(Base):
    """The first answer to one question in one attempt, like `attempt_answers`."""

    __tablename__ = "generated_lesson_answers"

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("generated_lesson_attempts.id", ondelete="CASCADE"), primary_key=True
    )
    question_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    option_id: Mapped[str] = mapped_column(String(40), nullable=False)
    correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    scored: Mapped[bool] = mapped_column(Boolean, nullable=False)
    answered_at: Mapped[datetime] = _created_at()


class GeneratedLessonReport(Base):
    """A learner's flag on a card of their generated lesson. No admin screen yet (D17)."""

    __tablename__ = "generated_lesson_reports"
    __table_args__ = (_one_of("reason", REPORT_REASONS, "reason_known"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    generated_lesson_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("generated_lessons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    card_id: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    created_at: Mapped[datetime] = _created_at()


# --- Read models (written only by app/consumers.py) ------------------------------------------


class LearnableTopic(Base):
    """A topic as Content last described it (content.topic.changed). `deleted` is the
    tombstone content.topic.deleted leaves, so a stale `changed` can't bring it back."""

    __tablename__ = "learnable_topics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sql_text("false")
    )
    version: Mapped[int] = mapped_column(BigInteger, nullable=False)


class LearnableLesson(Base):
    """A lesson that has been published at least once, as Content last described it
    (content.lesson.changed). `learner_visible` is Content's own rule (published, in a topic
    that is not archived); Learning never works it out again."""

    __tablename__ = "learnable_lessons"
    __table_args__ = (
        Index("ix_learnable_lessons_topic_id_position", "topic_id", "position"),
        _level_check(),
        _one_of("publication_state", PUBLICATION_STATES, "publication_state_known"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    # Natural key of a lesson loaded from content/ (the seed finds lessons by it).
    key: Mapped[str | None] = mapped_column(String(200), index=True)
    topic_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    # Content's lessons.created_at: the last tie-breaker when lessons are ordered.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # The draft title administrators see, for the insights header; learners see the deck's.
    display_title: Mapped[str] = mapped_column(String(200), nullable=False)
    publication_state: Mapped[str] = mapped_column(String(20), nullable=False)
    learner_visible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    first_published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latest_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    latest_version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False)


class LessonDeck(Base):
    """One published version of a lesson, exactly as published (content.lesson_version
    .published). Versions never change, so a deck is inserted once and never updated.

    `doc` is the stored document, right answers included: it is checked here and shown to
    administrators in insights, and never sent to learners as it is. `questions` says for
    each question whether it is scored and which option is right; `reading_seconds`,
    `scored_questions`, `assets` and `cards_plain_text` were worked out by Content."""

    __tablename__ = "lesson_decks"
    __table_args__ = (UniqueConstraint("lesson_id", "number"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    lesson_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    doc: Mapped[dict] = mapped_column(JSONB, nullable=False)
    questions: Mapped[list] = mapped_column(JSONB, nullable=False)
    reading_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    scored_questions: Mapped[int] = mapped_column(Integer, nullable=False)
    assets: Mapped[dict] = mapped_column(JSONB, nullable=False)
    cards_plain_text: Mapped[list] = mapped_column(JSONB, nullable=False)


class QuizQuestion(Base):
    """An aptitude question as Content last described it (content.aptitude_question
    .changed). `options` are as authored, without the quiz's own "I'm not sure"."""

    __tablename__ = "quiz_questions"
    __table_args__ = (
        _level_check(),
        # Picking a quiz question reads the active questions of one topic at one level.
        Index("ix_quiz_questions_topic_id_level_is_active", "topic_id", "level", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    topic_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list] = mapped_column(JSONB, nullable=False)
    correct_option_id: Mapped[str] = mapped_column(String(40), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    seed_key: Mapped[str | None] = mapped_column(String(120), index=True)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False)


class QuizBank(Base):
    """Whether the aptitude test is ready, and the order it asks topics in, as Content's rule
    decided (content.aptitude_bank.changed). One row, keyed by the bank's fixed id."""

    __tablename__ = "quiz_bank"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ready: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # [{"topic_id", "ready"}] in quiz order, used as given.
    topics: Mapped[list] = mapped_column(JSONB, nullable=False)


class Learner(Base):
    """A learner account (role user) Identity registered. Administrators are never kept, so
    they never count in insights. No personal data beyond the kind of learner."""

    __tablename__ = "learners"
    __table_args__ = (_one_of("user_type", USER_TYPES, "user_type_known"),)

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ErasedLearner(Base):
    """A deleted account, kept for good so a replayed `user.registered` can never bring the
    learner back. Only the id: no personal data."""

    __tablename__ = "erased_learners"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    erased_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


READ_MODELS = (
    LearnableTopic,
    LearnableLesson,
    LessonDeck,
    QuizQuestion,
    QuizBank,
    Learner,
)

outbox = define_outbox_table(Base.metadata)
