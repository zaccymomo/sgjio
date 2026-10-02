"""Topic management for administrators (SCRUM-57), and the one rule users depend on.

Routes stay thin: they call these functions and turn a TopicProblem into an HTTP error.

- names are trimmed by the request schema, 1-80 characters, and unique ignoring case
  (SCRUM-57 AC4). Archived topics still reserve their name and can still be renamed.
- a topic is archived (hidden from users, lessons and progress kept) or, only when it has
  no lessons of any status, deleted. Deleting never falls back to archiving.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Lesson, LessonStatus, Topic


class TopicProblem(Exception):
    """A rule the request broke. `status_code` is the HTTP status the route answers with."""

    def __init__(self, code: str, message: str, status_code: int, field: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.field = field


def _not_found() -> TopicProblem:
    return TopicProblem("topic_not_found", "That topic does not exist.", 404)


def _name_taken() -> TopicProblem:
    return TopicProblem(
        "topic_name_taken", "A topic with this name already exists.", 409, field="name"
    )


def _not_empty() -> TopicProblem:
    return TopicProblem(
        "topic_not_empty",
        "This topic has lessons, so it cannot be deleted. Archive it instead.",
        409,
    )


@dataclass(frozen=True)
class TopicSummary:
    id: uuid.UUID
    name: str
    archived_at: datetime | None
    lesson_count: int
    published_count: int


def visible_to_users(query: Select) -> Select:
    """Restrict a query on Topic to topics users may see: those that are not archived.

    Every user-facing read of topics goes through this, so the rule lives in one place.
    """
    return query.where(Topic.archived_at.is_(None))


def _get(db: Session, topic_id: uuid.UUID) -> Topic:
    topic = db.get(Topic, topic_id)
    if topic is None:
        raise _not_found()
    return topic


def _name_in_use(db: Session, name: str, except_id: uuid.UUID | None = None) -> bool:
    query = select(Topic.id).where(func.lower(Topic.name) == name.lower())
    if except_id is not None:
        # A topic never clashes with itself, so a case-only rename is allowed.
        query = query.where(Topic.id != except_id)
    return db.scalar(query) is not None


def _summary_query() -> Select:
    # Outer join so a topic with no lessons still appears, with zeros.
    return (
        select(
            Topic.id,
            Topic.name,
            Topic.archived_at,
            func.count(Lesson.id).label("lesson_count"),
            func.count(Lesson.id)
            .filter(Lesson.status == LessonStatus.PUBLISHED)
            .label("published_count"),
        )
        .outerjoin(Lesson, Lesson.topic_id == Topic.id)
        .group_by(Topic.id)
        .order_by(func.lower(Topic.name))
    )


def _summary(db: Session, topic_id: uuid.UUID) -> TopicSummary:
    return TopicSummary(*db.execute(_summary_query().where(Topic.id == topic_id)).one())


def list_topics(db: Session) -> list[TopicSummary]:
    """Every topic, archived included, with lesson counts over every status."""
    return [TopicSummary(*row) for row in db.execute(_summary_query()).all()]


def create_topic(db: Session, name: str) -> TopicSummary:
    if _name_in_use(db, name):
        raise _name_taken()
    topic = Topic(name=name)
    db.add(topic)
    _commit_name(db)
    return _summary(db, topic.id)


def rename_topic(db: Session, topic_id: uuid.UUID, name: str) -> TopicSummary:
    topic = _get(db, topic_id)
    if _name_in_use(db, name, except_id=topic.id):
        raise _name_taken()
    topic.name = name
    _commit_name(db)
    return _summary(db, topic.id)


def _commit_name(db: Session) -> None:
    # The check above can lose a race with another request; the unique index decides.
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _name_taken() from None


def archive_topic(db: Session, topic_id: uuid.UUID) -> TopicSummary:
    """Idempotent: archiving an archived topic keeps its original archived date."""
    topic = _get(db, topic_id)
    if topic.archived_at is None:
        topic.archived_at = datetime.now(UTC)
        db.commit()
    return _summary(db, topic.id)


def restore_topic(db: Session, topic_id: uuid.UUID) -> TopicSummary:
    """Idempotent: restoring an active topic changes nothing."""
    topic = _get(db, topic_id)
    if topic.archived_at is not None:
        topic.archived_at = None
        db.commit()
    return _summary(db, topic.id)


def delete_topic(db: Session, topic_id: uuid.UUID) -> None:
    """Only a topic with no lessons of any status. Otherwise the admin must archive it."""
    topic = _get(db, topic_id)
    if db.scalar(select(func.count(Lesson.id)).where(Lesson.topic_id == topic.id)):
        raise _not_empty()
    db.delete(topic)
    try:
        db.commit()
    except IntegrityError:
        # A lesson was linked after the check; lessons.topic_id is ON DELETE RESTRICT.
        db.rollback()
        raise _not_empty() from None
