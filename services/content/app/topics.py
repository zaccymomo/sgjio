"""Topic management for administrators (SCRUM-57), and the one rule users depend on.

Routes stay thin: they call these functions and turn a ContentProblem into an HTTP error.

- names are trimmed by the request schema, 1-80 characters, and unique ignoring case
  (SCRUM-57 AC4). Archived topics still reserve their name and can still be renamed.
- a description is optional, trimmed, up to 200 characters, and empty when there is none
  (SCRUM-86). Editing a topic without one in the request keeps the current one.
- a topic is archived (hidden from users, lessons and progress kept) or, only when it has
  no lessons of any status and has never had an aptitude question (`assessed_at`),
  deleted. Deleting never falls back to archiving.
- order (SCRUM-66): a new topic goes to the end, and so does a restored one, so the order
  administrators set only ever covers active topics. A reorder must list every active
  topic exactly once, and say which order it replaces; a page that was out of date is
  refused rather than guessed at.
- every change is announced in the same transaction (app/events.py): content.topic.changed,
  plus content.lesson.changed for the topic's published lessons on archive and restore, and
  content.aptitude_bank.changed when the quiz's topics or their order may have moved.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Select, case, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import events
from app.models import MAX_LEVEL, MIN_LEVEL, Lesson, LessonStatus, Topic
from app.problems import ContentProblem, check_reorder, topic_not_found


def _name_taken() -> ContentProblem:
    return ContentProblem(
        "topic_name_taken", "A topic with this name already exists.", 409, field="name"
    )


def _not_empty() -> ContentProblem:
    return ContentProblem(
        "topic_not_empty",
        "This topic has lessons, so it cannot be deleted. Archive it instead.",
        409,
    )


LEVELS = range(MIN_LEVEL, MAX_LEVEL + 1)


@dataclass(frozen=True)
class TopicSummary:
    id: uuid.UUID
    name: str
    description: str
    archived_at: datetime | None
    position: int
    lesson_count: int
    published_count: int
    # Published lessons at Level 1 to 5, in that order (SCRUM-103 AC5).
    published_by_level: list[int]


def visible_to_users(query: Select) -> Select:
    """Restrict a query on Topic to topics users may see: those that are not archived.

    Every user-facing read of topics goes through this, so the rule lives in one place.
    """
    return query.where(Topic.archived_at.is_(None))


def _get(db: Session, topic_id: uuid.UUID) -> Topic:
    """The topic, locked for the rest of the transaction: its version is about to move."""
    topic = db.get(Topic, topic_id, with_for_update=True)
    if topic is None:
        raise topic_not_found()
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
            Topic.description,
            Topic.archived_at,
            Topic.position,
            func.count(Lesson.id).label("lesson_count"),
            func.count(Lesson.id)
            .filter(Lesson.status == LessonStatus.PUBLISHED)
            .label("published_count"),
            *(
                func.count(Lesson.id).filter(
                    Lesson.status == LessonStatus.PUBLISHED, Lesson.level == level
                )
                for level in LEVELS
            ),
        )
        .outerjoin(Lesson, Lesson.topic_id == Topic.id)
        .group_by(Topic.id)
        .order_by(Topic.position, Topic.created_at, Topic.id)
    )


def _from_row(row) -> TopicSummary:
    """A row of _summary_query: the topic's fields, then one count per level."""
    fields = tuple(row)
    split = len(fields) - len(LEVELS)
    return TopicSummary(*fields[:split], published_by_level=list(fields[split:]))


def _summary(db: Session, topic_id: uuid.UUID) -> TopicSummary:
    return _from_row(db.execute(_summary_query().where(Topic.id == topic_id)).one())


def list_topics(db: Session) -> list[TopicSummary]:
    """Every topic, archived included, in order, with lesson counts over every status and
    published lessons at each level."""
    return [_from_row(row) for row in db.execute(_summary_query()).all()]


def next_topic_position(db: Session) -> int:
    """One past the highest position of any topic, archived ones included.

    Counting archived topics means a restored topic lands after every position in use,
    so it never ties with an active topic.
    """
    return db.scalar(select(func.coalesce(func.max(Topic.position) + 1, 0)))


def create_topic(db: Session, name: str, description: str = "") -> TopicSummary:
    if _name_in_use(db, name):
        raise _name_taken()
    topic = Topic(name=name, description=description, position=next_topic_position(db))
    db.add(topic)
    try:
        events.topic_changed(db, topic, bump=False)
    except IntegrityError:
        db.rollback()
        raise _name_taken() from None
    _commit_name(db)
    return _summary(db, topic.id)


def update_topic(
    db: Session, topic_id: uuid.UUID, name: str, description: str | None = None
) -> TopicSummary:
    """Rename a topic and, unless `description` is None, replace its description."""
    topic = _get(db, topic_id)
    if _name_in_use(db, name, except_id=topic.id):
        db.rollback()
        raise _name_taken()
    renamed = topic.name != name
    described = description is not None and topic.description != description
    topic.name = name
    if description is not None:
        topic.description = description
    if renamed or described:
        try:
            events.topic_changed(db, topic)
            if renamed:  # the name breaks ties in the quiz's topic order
                events.bank_changed(db)
        except IntegrityError:
            db.rollback()
            raise _name_taken() from None
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
        _announce_visibility(db, topic)
    db.commit()
    return _summary(db, topic.id)


def restore_topic(db: Session, topic_id: uuid.UUID) -> TopicSummary:
    """Idempotent: restoring an active topic changes nothing, not even its position.

    A restored topic goes to the end of the list rather than back to its old place, which
    other topics may have moved into since.
    """
    topic = _get(db, topic_id)
    if topic.archived_at is not None:
        topic.archived_at = None
        topic.position = next_topic_position(db)
        _announce_visibility(db, topic)
    db.commit()
    return _summary(db, topic.id)


def _announce_visibility(db: Session, topic: Topic) -> None:
    """Archive and restore change what learners see: the topic, each of its published
    lessons (`learner_visible`), and which topics the aptitude test covers."""
    events.topic_changed(db, topic)
    events.topic_lessons_changed(db, topic.id)
    events.bank_changed(db)


def delete_topic(db: Session, topic_id: uuid.UUID) -> None:
    """Only a topic with no lessons of any status that has never had an aptitude question
    (`assessed_at`, kept even after its questions move away). Otherwise the admin must
    archive it."""
    topic = _get(db, topic_id)
    if topic.assessed_at is not None or db.scalar(
        select(func.count(Lesson.id)).where(Lesson.topic_id == topic.id)
    ):
        db.rollback()
        raise _not_empty()
    events.topic_deleted(db, topic.id, topic.version)
    db.delete(topic)
    try:
        db.commit()
    except IntegrityError:
        # A lesson or question was linked after the check; both refer to the topic with
        # ON DELETE RESTRICT.
        db.rollback()
        raise _not_empty() from None


def reorder_topics(
    db: Session, ids: list[uuid.UUID], previous_ids: list[uuid.UUID]
) -> list[TopicSummary]:
    """Put the active topics in the order `ids`, replacing the order `previous_ids`.

    See check_reorder for what is refused. The active topics are locked first, so two
    reorders, or a reorder and an archive, run one after the other instead of interleaving.
    """
    rows = db.execute(
        select(Topic.id, Topic.position)
        .where(Topic.archived_at.is_(None))
        .order_by(Topic.position, Topic.created_at, Topic.id)
        .with_for_update()
    ).all()
    current = [row.id for row in rows]
    try:
        check_reorder(ids, previous_ids, current)
    except ContentProblem:
        db.rollback()
        raise
    if ids:
        db.execute(
            update(Topic)
            .where(Topic.id.in_(ids))
            # Setting updated_at to itself stops the ORM's onupdate from bumping it:
            # moving a topic is not editing it.
            .values(
                position=case({topic_id: n for n, topic_id in enumerate(ids)}, value=Topic.id),
                updated_at=Topic.updated_at,
            )
            .execution_options(synchronize_session=False)
        )
    was = {row.id: row.position for row in rows}
    moved = [topic_id for n, topic_id in enumerate(ids) if was[topic_id] != n]
    if moved:
        events.topics_moved(db, moved)
        events.bank_changed(db)
    db.commit()
    return list_topics(db)
