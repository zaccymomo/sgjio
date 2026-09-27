"""Progress figures behind the landing page circles (SCRUM-16 AC7 and AC8).

One query answers the whole landing page: for every topic that has at least one published
lesson, how many of those lessons this user has completed, and how many there are.

Two rules from SCRUM-16 AC8 are enforced here rather than left to the caller:

- only *currently published* lessons count, in both figures
- because "completed" is counted over the same set of published lessons as "available",
  completed can never exceed available -- so a circle cannot read "13 / 12" after an
  administrator withdraws a lesson somebody had already finished (SCRUM-52)
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import Session

from app.models import Lesson, LessonCompletion, LessonStatus, Topic


@dataclass(frozen=True)
class TopicProgress:
    id: uuid.UUID
    name: str
    completed: int
    available: int


@dataclass(frozen=True)
class Progress:
    topics: list[TopicProgress]
    completed: int
    available: int


def _topic_rows(user_id: uuid.UUID) -> Select:
    # Inner join to published lessons: a topic with no published lesson produces no row,
    # and so gets no circle (SCRUM-43 AC1).
    published_lessons = and_(Lesson.topic_id == Topic.id, Lesson.status == LessonStatus.PUBLISHED)
    this_users_completions = and_(
        LessonCompletion.lesson_id == Lesson.id,
        LessonCompletion.user_id == user_id,
    )
    return (
        select(
            Topic.id,
            Topic.name,
            func.count(LessonCompletion.id).label("completed"),
            func.count(Lesson.id).label("available"),
        )
        .join(Lesson, published_lessons)
        .outerjoin(LessonCompletion, this_users_completions)
        .group_by(Topic.id, Topic.name)
        # Alphabetical, so the circles do not move around between visits.
        .order_by(Topic.name)
    )


def progress_for(db: Session, user_id: uuid.UUID) -> Progress:
    """Per-topic and overall figures for one user."""
    topics = [
        TopicProgress(id=row.id, name=row.name, completed=row.completed, available=row.available)
        for row in db.execute(_topic_rows(user_id)).all()
    ]
    # The overall figure is the sum of the circles, so the two always agree on screen
    # (SCRUM-43 AC6).
    return Progress(
        topics=topics,
        completed=sum(topic.completed for topic in topics),
        available=sum(topic.available for topic in topics),
    )
