"""The administrators' lessons: the list and its order (SCRUM-66), and writing drafts
(SCRUM-64).

Routes stay thin: they call these functions and turn a ContentProblem into an HTTP error.

- the list has every lesson of every status, without its body, ordered as the admin
  portal shows it: by topic order, then by order within the topic. Lessons with no topic
  come last, and lessons in archived topics are included.
- lessons are ordered within their topic, and lessons with no topic among themselves.
  Moving a lesson to another topic belongs to the lesson editor, not to reordering.
- a reorder must list every lesson in that topic (or with no topic) exactly once, of any
  status, and say which order it replaces; a page that was out of date is refused rather
  than guessed at.
- reordering never changes a lesson's "last updated" time, which the list sorts by
  (SCRUM-66 AC3): moving a lesson is not editing it.
- a lesson is created as a draft at the end of its topic, and every field may be empty:
  required fields are checked only when publishing (SCRUM-56, SCRUM-70).
- only drafts are edited here; published lessons are edited or withdrawn (SCRUM-52).
- an edit or delete names the "last updated" time the editor loaded, and is refused if the
  lesson has changed since, so one save never silently overwrites another.
- only a lesson that has never been published can be deleted: deleting a lesson deletes
  everyone's completions of it, which published lessons must keep (SCRUM-52 AC4).
- a lesson can be moved into any active topic, but not into an archived one. A lesson that
  is already in an archived topic keeps saving there.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ColumnElement, case, func, select, update
from sqlalchemy.orm import Session

from app.models import Lesson, LessonStatus, Topic
from app.problems import (
    ContentProblem,
    check_reorder,
    lesson_not_deletable,
    lesson_not_draft,
    lesson_not_found,
    lesson_out_of_date,
    topic_archived,
    topic_not_found,
)


@dataclass(frozen=True)
class LessonSummary:
    id: uuid.UUID
    title: str
    topic_id: uuid.UUID | None
    status: LessonStatus
    updated_at: datetime
    position: int


@dataclass(frozen=True)
class LessonDetail:
    """One lesson as the editor needs it, body included."""

    id: uuid.UUID
    title: str
    content: str
    topic_id: uuid.UUID | None
    status: LessonStatus
    published_at: datetime | None
    withdrawn_at: datetime | None
    position: int
    created_at: datetime
    updated_at: datetime
    deletable: bool


def _deletable(lesson: Lesson) -> bool:
    """A draft that has never been published. Lives here so the page does not repeat it."""
    return lesson.status == LessonStatus.DRAFT and lesson.published_at is None


def _detail(lesson: Lesson) -> LessonDetail:
    return LessonDetail(
        id=lesson.id,
        title=lesson.title,
        content=lesson.content,
        topic_id=lesson.topic_id,
        status=lesson.status,
        published_at=lesson.published_at,
        withdrawn_at=lesson.withdrawn_at,
        position=lesson.position,
        created_at=lesson.created_at,
        updated_at=lesson.updated_at,
        deletable=_deletable(lesson),
    )


def _in_group(topic_id: uuid.UUID | None) -> ColumnElement[bool]:
    """The lessons ordered together: one topic's, or those with no topic."""
    return Lesson.topic_id.is_(None) if topic_id is None else Lesson.topic_id == topic_id


def list_lessons(db: Session) -> list[LessonSummary]:
    query = (
        select(
            Lesson.id,
            Lesson.title,
            Lesson.topic_id,
            Lesson.status,
            Lesson.updated_at,
            Lesson.position,
        )
        .outerjoin(Topic, Lesson.topic_id == Topic.id)
        .order_by(
            Topic.position.nulls_last(),
            Topic.created_at,
            Topic.id,
            Lesson.position,
            Lesson.created_at,
            Lesson.id,
        )
    )
    return [LessonSummary(*row) for row in db.execute(query).all()]


def next_lesson_position(db: Session, topic_id: uuid.UUID | None) -> int:
    """Where a new lesson goes in its topic (or among lessons with no topic): the end.

    For whoever creates lessons: the seed now, the lesson editor (SCRUM-64) later.
    """
    return db.scalar(
        select(func.coalesce(func.max(Lesson.position) + 1, 0)).where(_in_group(topic_id))
    )


def reorder_lessons(
    db: Session,
    topic_id: uuid.UUID | None,
    ids: list[uuid.UUID],
    previous_ids: list[uuid.UUID],
) -> list[LessonSummary]:
    """Put one topic's lessons (or those with no topic) in the order `ids`, replacing the
    order `previous_ids`.

    See check_reorder for what is refused. The group's lessons are locked first, so two
    reorders of the same topic run one after the other instead of interleaving.
    """
    if topic_id is not None and db.get(Topic, topic_id) is None:
        raise topic_not_found()
    current = list(
        db.scalars(
            select(Lesson.id)
            .where(_in_group(topic_id))
            .order_by(Lesson.position, Lesson.created_at, Lesson.id)
            .with_for_update()
        )
    )
    try:
        check_reorder(ids, previous_ids, current)
    except ContentProblem:
        db.rollback()
        raise
    if ids:
        db.execute(
            update(Lesson)
            .where(Lesson.id.in_(ids))
            # Setting updated_at to itself stops the ORM's onupdate from bumping it.
            .values(
                position=case({lesson_id: n for n, lesson_id in enumerate(ids)}, value=Lesson.id),
                updated_at=Lesson.updated_at,
            )
            .execution_options(synchronize_session=False)
        )
    db.commit()
    return list_lessons(db)


# --- Writing drafts (SCRUM-64) ------------------------------------------------------------


def _check_topic(db: Session, topic_id: uuid.UUID) -> None:
    """A topic a lesson may be put in: one that exists and is not archived."""
    topic = db.get(Topic, topic_id)
    if topic is None:
        raise topic_not_found(field="topic_id")
    if topic.archived_at is not None:
        raise topic_archived(field="topic_id")


def get_lesson(db: Session, lesson_id: uuid.UUID) -> LessonDetail:
    lesson = db.get(Lesson, lesson_id)
    if lesson is None:
        raise lesson_not_found()
    return _detail(lesson)


def create_lesson(
    db: Session, title: str = "", content: str = "", topic_id: uuid.UUID | None = None
) -> LessonDetail:
    """A new draft, at the end of its topic (or of the lessons with no topic)."""
    if topic_id is not None:
        _check_topic(db, topic_id)
    lesson = Lesson(
        title=title,
        content=content,
        topic_id=topic_id,
        status=LessonStatus.DRAFT,
        position=next_lesson_position(db, topic_id),
    )
    db.add(lesson)
    db.commit()
    return _detail(lesson)


def update_lesson(
    db: Session, lesson_id: uuid.UUID, expected_updated_at: datetime, changes: dict
) -> LessonDetail:
    """Change a draft's `title`, `content` or `topic_id`: whichever `changes` holds.

    A save that changes nothing leaves "last updated" alone, since the ORM only writes
    (and only bumps updated_at) when a value differs. A new topic puts the lesson at the
    end of that topic; the lessons it leaves keep their positions, gap and all.
    """
    try:
        lesson = db.get(Lesson, lesson_id, with_for_update=True)
        if lesson is None:
            raise lesson_not_found()
        # Checked before the date, since a lesson published meanwhile has a new date too,
        # and "not a draft" is the more useful thing to say.
        if lesson.status != LessonStatus.DRAFT:
            raise lesson_not_draft()
        if lesson.updated_at != expected_updated_at:
            raise lesson_out_of_date()
        if "topic_id" in changes and changes["topic_id"] != lesson.topic_id:
            topic_id = changes["topic_id"]
            if topic_id is not None:
                _check_topic(db, topic_id)
            # Worked out before the move, so the lesson does not count itself.
            position = next_lesson_position(db, topic_id)
            lesson.topic_id = topic_id
            lesson.position = position
        for field in ("title", "content"):
            if field in changes and changes[field] != getattr(lesson, field):
                setattr(lesson, field, changes[field])
    except ContentProblem:
        db.rollback()
        raise
    db.commit()
    return _detail(lesson)


def delete_lesson(db: Session, lesson_id: uuid.UUID, expected_updated_at: datetime) -> None:
    """Delete a lesson that has never been published, with its quiz question."""
    try:
        lesson = db.get(Lesson, lesson_id, with_for_update=True)
        if lesson is None:
            raise lesson_not_found()
        if not _deletable(lesson):
            raise lesson_not_deletable()
        if lesson.updated_at != expected_updated_at:
            raise lesson_out_of_date()
    except ContentProblem:
        db.rollback()
        raise
    db.delete(lesson)
    db.commit()
