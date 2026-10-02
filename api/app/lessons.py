"""The administrators' list of lessons and their order (SCRUM-66).

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
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ColumnElement, case, func, select, update
from sqlalchemy.orm import Session

from app.models import Lesson, LessonStatus, Topic
from app.problems import ContentProblem, check_reorder, topic_not_found


@dataclass(frozen=True)
class LessonSummary:
    id: uuid.UUID
    title: str
    topic_id: uuid.UUID | None
    status: LessonStatus
    updated_at: datetime
    position: int


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
