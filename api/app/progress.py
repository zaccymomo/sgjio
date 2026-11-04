"""Progress figures behind the landing page circles (SCRUM-16 AC7 and AC8).

One query answers the whole landing page: for every topic that has at least one published
lesson, how many of those lessons this user has completed, and how many there are.

Two rules from SCRUM-16 AC8 are enforced here rather than left to the caller:

- only *currently published* lessons count, in both figures
- because "completed" is counted over the same set of published lessons as "available",
  completed can never exceed available -- so a circle cannot read "13 / 12" after an
  administrator withdraws a lesson somebody had already finished (SCRUM-52)

Each user sees the lessons at their own level (SCRUM-104), plus every lesson they have
already completed at another level, so nothing they finished disappears when their level
changes (SCRUM-110 AC6). Both figures count that same set: lessons at other levels a user
hasn't completed are left out of "available" as well as "completed".

Topics an administrator has archived (SCRUM-57) are left out entirely, so their circle
disappears and the overall figure shrinks with it; restoring brings both back.

Opening a circle lists that topic's lessons (SCRUM-53) by the same rules, so the figure on
the topic page always matches its circle.

Beside the circles sits one suggested lesson (SCRUM-6): the next lesson not yet completed in
the topic where progress is weakest, meaning the smallest share of its lessons completed.
Topics tie in the order administrators set, so someone with no activity at all is pointed at
the first lesson of the first topic. With everything completed there is no suggestion.

Learners can also search every topic's lessons by a word or phrase (SCRUM-85), by the same
rules: published lessons only, as their latest version reads, in topics that aren't archived.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction

from sqlalchemy import ColumnElement, Select, and_, func, or_, select
from sqlalchemy.orm import Session

from app import lesson_doc, media
from app.lesson_doc import LessonDoc
from app.lessons import latest_version
from app.models import (
    MIN_LEVEL,
    Lesson,
    LessonAttempt,
    LessonCompletion,
    LessonStatus,
    Topic,
    User,
)
from app.problems import topic_unavailable
from app.topics import visible_to_users


@dataclass(frozen=True)
class TopicProgress:
    id: uuid.UUID
    name: str
    completed: int
    available: int


@dataclass(frozen=True)
class Suggestion:
    """The lesson to start with next (SCRUM-6), as its latest version reads."""

    lesson_id: uuid.UUID
    title: str
    summary: str
    reading_seconds: int
    topic_id: uuid.UUID
    topic_name: str


@dataclass(frozen=True)
class Progress:
    topics: list[TopicProgress]
    completed: int
    available: int
    # None once every lesson available has been completed (SCRUM-6 AC6).
    suggestion: Suggestion | None
    level: int
    aptitude_taken: bool


def _level_of(db: Session, user_id: uuid.UUID) -> int:
    user = db.get(User, user_id)
    return user.current_level if user is not None else MIN_LEVEL


def _for_this_user(level: int) -> ColumnElement[bool]:
    """A lesson at the user's level, or one they completed at any level (SCRUM-104).

    Needs `LessonCompletion` outer-joined to this user's completions."""
    return or_(Lesson.level == level, LessonCompletion.id.is_not(None))


def _topic_rows(user_id: uuid.UUID, level: int) -> Select:
    # Inner join to published lessons: a topic with no published lesson this user can see
    # produces no row, and so gets no circle (SCRUM-43 AC1, SCRUM-104 AC4).
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
        .where(_for_this_user(level))
        .group_by(Topic.id, Topic.name)
        # In the order administrators set (SCRUM-66), so the circles stay put between
        # visits; the name breaks any tie.
        .order_by(Topic.position, Topic.name)
    )
    return visible_to_users(query)


def progress_for(db: Session, user_id: uuid.UUID) -> Progress:
    """Per-topic and overall figures for one user."""
    level = _level_of(db, user_id)
    from app.aptitude import latest_attempt

    topics = [
        TopicProgress(id=row.id, name=row.name, completed=row.completed, available=row.available)
        for row in db.execute(_topic_rows(user_id, level)).all()
    ]
    # The overall figure is the sum of the circles, so the two always agree on screen
    # (SCRUM-43 AC6).
    return Progress(
        topics=topics,
        completed=sum(topic.completed for topic in topics),
        available=sum(topic.available for topic in topics),
        suggestion=_suggestion(db, user_id, level, topics),
        level=level,
        aptitude_taken=latest_attempt(db, user_id) is not None,
    )


def _suggestion(
    db: Session, user_id: uuid.UUID, level: int, topics: list[TopicProgress]
) -> Suggestion | None:
    """The first lesson not yet completed in the weakest topic (SCRUM-6 AC2). Lessons not
    yet completed only count at the user's level, so the suggestion is always at it.

    `topics` are the circles, in order, so `sorted` (which is stable) breaks a tie by the
    order administrators set. A topic with nothing left to do is never the weakest.
    """
    unfinished = [topic for topic in topics if topic.completed < topic.available]
    for topic in sorted(unfinished, key=lambda t: Fraction(t.completed, t.available)):
        completed = select(LessonCompletion.id).where(
            LessonCompletion.lesson_id == Lesson.id, LessonCompletion.user_id == user_id
        )
        lessons = db.scalars(
            select(Lesson)
            .where(
                Lesson.topic_id == topic.id,
                Lesson.status == LessonStatus.PUBLISHED,
                Lesson.level == level,
                ~completed.exists(),
            )
            .order_by(Lesson.position, Lesson.created_at)
        )
        for lesson in lessons:
            version = latest_version(db, lesson.id)
            # A published lesson always has a version; one that somehow does not could not
            # be opened (app/learning.py), so it is passed over.
            if version is None:
                continue
            doc = LessonDoc.model_validate(version.doc)
            return Suggestion(
                lesson_id=lesson.id,
                title=version.title,
                summary=version.summary,
                reading_seconds=lesson_doc.stats(doc, media.facts_for(db, doc)).reading_seconds,
                topic_id=topic.id,
                topic_name=topic.name,
            )
    return None


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
    level: int


@dataclass(frozen=True)
class TopicLessons:
    id: uuid.UUID
    name: str
    description: str
    completed: int
    available: int
    lessons: list[TopicLesson]


def topic_lessons(db: Session, user_id: uuid.UUID, topic_id: uuid.UUID) -> TopicLessons:
    """One topic's published lessons, in the order administrators set, with this user's
    completions (SCRUM-53): those at the user's level and those they completed at any level
    (SCRUM-104). An archived or unknown topic is unavailable."""
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
        .where(
            Lesson.topic_id == topic.id,
            Lesson.status == LessonStatus.PUBLISHED,
            _for_this_user(_level_of(db, user_id)),
        )
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
                level=lesson.level,
            )
        )

    return TopicLessons(
        id=topic.id,
        name=topic.name,
        description=topic.description,
        completed=sum(1 for lesson in lessons if lesson.completed),
        available=len(lessons),
        lessons=lessons,
    )


@dataclass(frozen=True)
class SearchResult:
    """One lesson found by learners' search (SCRUM-85), as its latest version reads."""

    lesson_id: uuid.UUID
    title: str
    topic_id: uuid.UUID
    topic_name: str
    completed: bool
    # Card text around the first match, or None when only the title matched.
    snippet: str | None


SNIPPET_LENGTH = 120
SNIPPET_LEAD = 40


def search_lessons(db: Session, user_id: uuid.UUID, query: str) -> list[SearchResult]:
    """Published lessons whose title or card text contains `query`, ignoring case and
    Markdown (SCRUM-85 AC2).

    Only the latest published version is read, never the draft, so an edit nobody has
    published yet can't be found. Lessons in archived topics are left out, as from the
    circles. Title matches come first; within each group, lessons keep the order of the
    circles and topic pages.
    """
    needle = " ".join(query.split()).lower()
    if not needle:
        return []

    rows = db.execute(
        visible_to_users(
            select(Lesson, Topic, LessonCompletion.id)
            .join(Topic, Topic.id == Lesson.topic_id)
            .outerjoin(
                LessonCompletion,
                and_(LessonCompletion.lesson_id == Lesson.id, LessonCompletion.user_id == user_id),
            )
            .where(Lesson.status == LessonStatus.PUBLISHED)
            .order_by(Topic.position, Topic.name, Lesson.position, Lesson.created_at)
        )
    ).all()

    by_title: list[SearchResult] = []
    by_text: list[SearchResult] = []
    for lesson, topic, completion_id in rows:
        version = latest_version(db, lesson.id)
        # A published lesson always has a version; one that somehow does not could not be
        # opened (app/learning.py), so it is passed over.
        if version is None:
            continue
        title_matches = needle in " ".join(version.title.split()).lower()
        snippet = _snippet(LessonDoc.model_validate(version.doc), needle)
        if not title_matches and snippet is None:
            continue
        result = SearchResult(
            lesson_id=lesson.id,
            title=version.title,
            topic_id=topic.id,
            topic_name=topic.name,
            completed=completion_id is not None,
            snippet=snippet,
        )
        (by_title if title_matches else by_text).append(result)
    return by_title + by_text


def _snippet(doc: LessonDoc, needle: str) -> str | None:
    """About SNIPPET_LENGTH characters of the first card whose text contains `needle`, cut
    so the match sits near the start, or None if no card's text does."""
    for card in doc.cards:
        text = lesson_doc.plain_text(card.text)
        at = text.lower().find(needle)
        if at < 0:
            continue
        start = max(0, at - SNIPPET_LEAD)
        end = min(len(text), start + max(SNIPPET_LENGTH, len(needle) + SNIPPET_LEAD))
        # Cut at spaces, so the snippet never starts or ends half way through a word.
        if start > 0:
            space = text.find(" ", start, at)
            start = space + 1 if space >= 0 else start
        if end < len(text):
            space = text.rfind(" ", at + len(needle), end)
            end = space if space >= 0 else end
        return ("…" if start > 0 else "") + text[start:end] + ("…" if end < len(text) else "")
    return None
