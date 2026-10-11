"""Progress figures behind the landing page circles (SCRUM-16 AC7 and AC8).

One query answers the whole landing page: for every topic that has at least one published
lesson, how many of those lessons this user has completed, and how many there are.

Two rules from SCRUM-16 AC8 are enforced here rather than left to the caller:

- only *currently published* lessons count, in both figures
- because "completed" is counted over the same set of published lessons as "available",
  completed can never exceed available -- so a circle cannot read "13 / 12" after an
  administrator withdraws a lesson somebody had already finished (SCRUM-52)

Topics an administrator has archived (SCRUM-57) are left out entirely, so their circle
disappears and the overall figure shrinks with it; restoring brings both back.

Opening a circle lists that topic's lessons (SCRUM-53) by the same rules, so the figure on
the topic page always matches its circle.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import Session

from app import lesson_doc, media
from app.lesson_doc import LessonDoc
from app.lessons import latest_version
from app.models import Lesson, LessonAttempt, LessonCompletion, LessonStatus, Topic
from app.problems import topic_unavailable
from app.topics import visible_to_users


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
    query = (
        select(
            Topic.id,
            Topic.name,
            func.count(LessonCompletion.id).label("completed"),
            func.count(Lesson.id).label("available"),
        )
        .join(Lesson, published_lessons)
        .outerjoin(LessonCompletion, this_users_completions)
        .group_by(Topic.id, Topic.name)
        # In the order administrators set (SCRUM-66), so the circles stay put between
        # visits; the name breaks any tie.
        .order_by(Topic.position, Topic.name)
    )
    return visible_to_users(query)


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


@dataclass(frozen=True)
class TopicLesson:
    id: uuid.UUID
    title: str
    summary: str
    reading_seconds: int
    # Scored questions only: a one-option tap is not a quiz question.
    questions: int
    completed: bool
    # The best result so far (SCRUM-16), empty until the lesson is completed.
    best_correct: int | None
    best_scored: int | None
    # When this user last finished it (SCRUM-54), empty until the lesson is completed.
    last_attempted_at: datetime | None


@dataclass(frozen=True)
class TopicLessons:
    id: uuid.UUID
    name: str
    completed: int
    available: int
    lessons: list[TopicLesson]


def topic_lessons(db: Session, user_id: uuid.UUID, topic_id: uuid.UUID) -> TopicLessons:
    """One topic's published lessons, in the order administrators set, with this user's
    completions (SCRUM-53). An archived or unknown topic is unavailable."""
    topic = db.scalar(visible_to_users(select(Topic).where(Topic.id == topic_id)))
    if topic is None:
        raise topic_unavailable()

    # Only finished attempts count: one left half way is never recorded (SCRUM-15 AC4).
    last_finished = (
        select(
            LessonAttempt.lesson_id,
            func.max(LessonAttempt.finished_at).label("at"),
        )
        .where(LessonAttempt.user_id == user_id, LessonAttempt.finished_at.is_not(None))
        .group_by(LessonAttempt.lesson_id)
        .subquery()
    )
    rows = db.execute(
        select(Lesson, LessonCompletion, last_finished.c.at)
        .outerjoin(
            LessonCompletion,
            and_(LessonCompletion.lesson_id == Lesson.id, LessonCompletion.user_id == user_id),
        )
        .outerjoin(last_finished, last_finished.c.lesson_id == Lesson.id)
        .where(Lesson.topic_id == topic.id, Lesson.status == LessonStatus.PUBLISHED)
        .order_by(Lesson.position, Lesson.created_at)
    ).all()

    lessons = []
    for lesson, completion, last_finished_at in rows:
        version = latest_version(db, lesson.id)
        # A published lesson always has a version; skip one that somehow does not, as
        # opening it would be refused (app/learning.py).
        if version is None:
            continue
        doc = LessonDoc.model_validate(version.doc)
        stats = lesson_doc.stats(doc, media.facts_for(db, doc))
        lessons.append(
            TopicLesson(
                id=lesson.id,
                title=version.title,
                summary=version.summary,
                # Worked out as the lesson's cover does, so the two always agree.
                reading_seconds=stats.reading_seconds,
                questions=stats.scored_questions,
                completed=completion is not None,
                best_correct=completion.best_correct if completion else None,
                best_scored=completion.best_scored if completion else None,
                # A completion recorded before attempts were (or seeded) has no attempt;
                # its completion time stands in, so "attempted" always matches "completed".
                last_attempted_at=(
                    (last_finished_at or completion.completed_at) if completion else None
                ),
            )
        )

    return TopicLessons(
        id=topic.id,
        name=topic.name,
        completed=sum(1 for lesson in lessons if lesson.completed),
        available=len(lessons),
        lessons=lessons,
    )
