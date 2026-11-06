"""Content's events: when each is written, and the version it carries (contracts/README.md).

Every function here writes to the outbox in the caller's transaction, so the event is
committed with the change it describes or not at all. The caller holds the row lock of the
aggregate it bumps (SELECT ... FOR UPDATE, or an UPDATE), so versions follow commit order.

Rules (docs/architecture/detailed-plan.md, section 2.2):
- topics: content.topic.changed on create, rename, describe, archive, restore, reorder (each
  moved topic), import and seed; content.topic.deleted on delete. Archive and restore also
  send content.lesson.changed for each of the topic's lessons that was ever published.
- lessons: content.lesson.changed only for lessons published at least once, when what it
  says changes. A publish that makes a version sends content.lesson_version.published first.
- aptitude questions: content.aptitude_question.changed, then one
  content.aptitude_bank.changed per transaction, after any topic.changed in it. Topic
  archive, restore, rename and reorder send the bank event too.
"""

import uuid

from sqlalchemy import exists, select, text, update
from sqlalchemy.orm import Session

from app import projections
from app.models import AptitudeQuestion, Lesson, LessonVersion, Topic
from app.platform.outbox import emit

TOPIC_CHANGED = "content.topic.changed"
TOPIC_DELETED = "content.topic.deleted"
LESSON_CHANGED = "content.lesson.changed"
VERSION_PUBLISHED = "content.lesson_version.published"
QUESTION_CHANGED = "content.aptitude_question.changed"
BANK_CHANGED = "content.aptitude_bank.changed"


# --- Topics --------------------------------------------------------------------------------


def topic_changed(db: Session, topic: Topic, *, bump: bool = True) -> None:
    """`bump=False` for a topic just created, which starts at version 1."""
    if bump:
        topic.version += 1
    db.flush()
    emit(
        db,
        type=TOPIC_CHANGED,
        aggregate_type="topic",
        aggregate_id=topic.id,
        aggregate_version=topic.version,
        data=projections.topic_projection(topic),
    )


def topic_deleted(db: Session, topic_id: uuid.UUID, version: int) -> None:
    """`version` is the deleted topic's last version; the tombstone is one past it."""
    emit(
        db,
        type=TOPIC_DELETED,
        aggregate_type="topic",
        aggregate_id=topic_id,
        aggregate_version=version + 1,
        data={"topic_id": topic_id},
    )


def topics_moved(db: Session, topic_ids: list[uuid.UUID]) -> None:
    """After a reorder: bump and announce each topic whose position changed. Their
    `updated_at` is kept, as the reorder keeps it (moving a topic is not editing it)."""
    if not topic_ids:
        return
    db.execute(
        update(Topic)
        .where(Topic.id.in_(topic_ids))
        .values(version=Topic.version + 1, updated_at=Topic.updated_at)
        .execution_options(synchronize_session=False)
    )
    moved = db.scalars(
        select(Topic)
        .where(Topic.id.in_(topic_ids))
        .order_by(Topic.position, Topic.created_at, Topic.id)
        .execution_options(populate_existing=True)
    )
    for topic in moved:
        topic_changed(db, topic, bump=False)


# --- Lessons -------------------------------------------------------------------------------


def _ever_published():
    """Lessons Learning has heard of: published at least once (and so in a topic)."""
    return Lesson.topic_id.is_not(None) & exists().where(LessonVersion.lesson_id == Lesson.id)


def lesson_changed(db: Session, lesson: Lesson, before: dict | None = None) -> bool:
    """Announce a lesson's learner-facing state if it was ever published and, when `before`
    (its projection before the change) is given, only if that state changed. Returns
    whether an event was written. The caller has the lesson locked."""
    db.flush()
    after = projections.lesson_projection(db, lesson)
    if after is None or after == before:
        return False
    lesson.version += 1
    db.flush()
    emit(
        db,
        type=LESSON_CHANGED,
        aggregate_type="lesson",
        aggregate_id=lesson.id,
        aggregate_version=lesson.version,
        data=after,
    )
    return True


def lessons_changed(db: Session, lesson_ids: list[uuid.UUID]) -> None:
    """Announce the ever-published lessons among `lesson_ids` (a reorder or a topic's
    archive or restore), bumping each version with an UPDATE that takes their row locks and
    keeps `updated_at`: neither is an edit of the lesson."""
    if not lesson_ids:
        return
    bumped = list(
        db.scalars(
            update(Lesson)
            .where(Lesson.id.in_(lesson_ids), _ever_published())
            .values(version=Lesson.version + 1, updated_at=Lesson.updated_at)
            .returning(Lesson.id)
            .execution_options(synchronize_session=False)
        )
    )
    if not bumped:
        return
    lessons = db.scalars(
        select(Lesson)
        .where(Lesson.id.in_(bumped))
        .order_by(Lesson.level, Lesson.position, Lesson.created_at, Lesson.id)
        .execution_options(populate_existing=True)
    )
    for lesson in lessons:
        emit(
            db,
            type=LESSON_CHANGED,
            aggregate_type="lesson",
            aggregate_id=lesson.id,
            aggregate_version=lesson.version,
            data=projections.lesson_projection(db, lesson),
        )


def topic_lessons_changed(db: Session, topic_id: uuid.UUID) -> None:
    """A topic was archived or restored, so each of its lessons' `learner_visible` moved."""
    lessons_changed(db, list(db.scalars(select(Lesson.id).where(Lesson.topic_id == topic_id))))


def version_published(db: Session, version: LessonVersion) -> None:
    """A new, immutable version. Always version 1 of its own aggregate."""
    db.flush()
    emit(
        db,
        type=VERSION_PUBLISHED,
        aggregate_type="lesson_version",
        aggregate_id=version.id,
        aggregate_version=1,
        data=projections.version_projection(db, version),
    )


# --- Aptitude bank -------------------------------------------------------------------------


def question_changed(db: Session, question: AptitudeQuestion, *, bump: bool = True) -> None:
    """`bump=False` for a question just created, which starts at version 1. Follow it (once
    per transaction) with bank_changed."""
    if bump:
        question.version += 1
    db.flush()
    emit(
        db,
        type=QUESTION_CHANGED,
        aggregate_type="aptitude_question",
        aggregate_id=question.id,
        aggregate_version=question.version,
        data=projections.question_projection(question),
    )


def next_bank_revision(db: Session) -> int:
    """The bank's next revision. The upsert's row lock serialises concurrent bank changes,
    so revisions follow commit order."""
    return db.execute(
        text(
            "INSERT INTO aptitude_bank_state (id, revision) VALUES (1, 1) "
            "ON CONFLICT (id) DO UPDATE SET revision = aptitude_bank_state.revision + 1 "
            "RETURNING revision"
        )
    ).scalar_one()


def bank_changed(db: Session) -> None:
    """Whether the aptitude test is ready, and its topic order, as of this transaction."""
    revision = next_bank_revision(db)
    db.flush()
    emit(
        db,
        type=BANK_CHANGED,
        aggregate_type="aptitude_bank",
        aggregate_id=projections.APTITUDE_BANK_ID,
        aggregate_version=revision,
        data=projections.bank_projection(db),
    )


# --- Republishing --------------------------------------------------------------------------


def _emit_current(db: Session, lesson: Lesson) -> None:
    emit(
        db,
        type=LESSON_CHANGED,
        aggregate_type="lesson",
        aggregate_id=lesson.id,
        aggregate_version=lesson.version,
        data=projections.lesson_projection(db, lesson),
    )


def republish_catalog(db: Session) -> dict[str, int]:
    """Write the current state of everything Learning reads, at each aggregate's current
    version: every topic, every version, every lesson published at least once, every
    question and the bank (`python -m app.cli republish-catalog`). Nothing is bumped, so a
    consumer that is up to date ignores it all and one rebuilding its read models takes it
    all. Topics deleted earlier are not repeated: their rows are gone. Returns counts."""
    counts = dict.fromkeys(("topics", "versions", "lessons", "questions", "bank"), 0)
    for topic in db.scalars(select(Topic).order_by(Topic.position, Topic.created_at, Topic.id)):
        topic_changed(db, topic, bump=False)
        counts["topics"] += 1
    published = db.scalars(
        select(Lesson)
        .where(_ever_published())
        .order_by(Lesson.topic_id, Lesson.level, Lesson.position, Lesson.created_at, Lesson.id)
    ).all()
    for lesson in published:
        for version in db.scalars(
            select(LessonVersion)
            .where(LessonVersion.lesson_id == lesson.id)
            .order_by(LessonVersion.number)
        ):
            version_published(db, version)
            counts["versions"] += 1
        _emit_current(db, lesson)
        counts["lessons"] += 1
    for question in db.scalars(select(AptitudeQuestion).order_by(AptitudeQuestion.created_at)):
        question_changed(db, question, bump=False)
        counts["questions"] += 1
    revision = db.execute(
        text("SELECT revision FROM aptitude_bank_state WHERE id = 1 FOR UPDATE")
    ).scalar_one_or_none()
    if not revision:
        revision = next_bank_revision(db)
    emit(
        db,
        type=BANK_CHANGED,
        aggregate_type="aptitude_bank",
        aggregate_id=projections.APTITUDE_BANK_ID,
        aggregate_version=revision,
        data=projections.bank_projection(db),
    )
    counts["bank"] = 1
    return counts
