"""Progress figures behind the landing page circles (SCRUM-16 AC7 and AC8). Moved from the
monolith's app/progress.py onto the read models; the rules are unchanged.

One query answers the whole landing page: for every topic that has at least one visible
lesson, how many of those lessons this user has completed, and how many there are.

Two rules from SCRUM-16 AC8 are enforced here rather than left to the caller:

- only *currently published* lessons count, in both figures
- because "completed" is counted over the same set of published lessons as "available",
  completed can never exceed available -- so a circle cannot read "13 / 12" after an
  administrator withdraws a lesson somebody had already finished (SCRUM-52)

Lessons are not hidden by level: every user sees every published lesson (SCRUM-104 AC4).
Users have no level of their own since SCRUM-113; the aptitude quiz gives each topic an
exemption level instead (`app/exemptions.py`).

Topics an administrator has archived (SCRUM-57) are left out entirely, so their circle
disappears and the overall figure shrinks with it; restoring brings both back.

Opening a circle lists that topic's lessons (SCRUM-53) by the same rules, so the figure on
the topic page always matches its circle.

Beside the circles sits one suggested lesson (SCRUM-6, SCRUM-106): the lowest-level lesson
neither completed nor exempted in the topic where progress is weakest, meaning the smallest
share of its lessons covered (completed or exempted, as the circles count). Topics tie in the
order administrators set, so someone with no activity at all is pointed at the first lesson of
the first topic. With everything covered there is no suggestion. The suggestion carries a
one-line reason (SCRUM-107), which never mentions a level.

Learners can also search every topic's lessons by a word or phrase (SCRUM-85), by the same
rules: published lessons only, as their latest version reads, in topics that aren't archived.

Each circle also carries the level the user has reached in its topic, which the Profile
tab's chart draws (SCRUM-100); `level_reached` explains the rule.

"Published and visible" is `catalog.lesson_visible()`: Content's `learner_visible`, with the
lesson's latest deck arrived and its topic visible here.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from app import catalog
from app.aptitude import has_taken_quiz
from app.catalog import visible_to_users
from app.exemptions import exemption_levels, is_exempted
from app.models import (
    MAX_LEVEL,
    PUBLISHED,
    LearnableLesson,
    LearnableTopic,
    LessonAttempt,
    LessonCompletion,
)
from app.problems import topic_unavailable


@dataclass(frozen=True)
class TopicProgress:
    id: uuid.UUID
    name: str
    # Covered lessons: completed by the learner or exempted by their aptitude result.
    completed: int
    # Exempted and not also completed, so the two parts never double count.
    exempted: int
    available: int
    # The level reached in this topic, 0 to 5 (SCRUM-100).
    level: int


@dataclass(frozen=True)
class Suggestion:
    """The lesson to start with next (SCRUM-6), as its latest version reads."""

    lesson_id: uuid.UUID
    title: str
    summary: str
    reading_seconds: int
    topic_id: uuid.UUID
    topic_name: str
    # Why this lesson, in one line and without a level (SCRUM-107).
    reason: str


@dataclass(frozen=True)
class Progress:
    topics: list[TopicProgress]
    completed: int
    exempted: int
    available: int
    # None once every lesson available has been completed (SCRUM-6 AC6).
    suggestion: Suggestion | None
    aptitude_taken: bool


def _topic_rows(user_id: uuid.UUID) -> Select:
    # Inner join to visible lessons: a topic with no visible lesson produces no row, and so
    # gets no circle (SCRUM-43 AC1).
    visible_lessons = and_(LearnableLesson.topic_id == LearnableTopic.id, catalog.lesson_visible())
    this_users_completions = and_(
        LessonCompletion.lesson_id == LearnableLesson.id,
        LessonCompletion.user_id == user_id,
    )
    query = (
        select(
            LearnableTopic.id,
            LearnableTopic.name,
            func.count(LearnableLesson.id)
            .filter(or_(LessonCompletion.id.is_not(None), is_exempted(user_id)))
            .label("completed"),
            func.count(LearnableLesson.id)
            .filter(and_(LessonCompletion.id.is_(None), is_exempted(user_id)))
            .label("exempted"),
            func.count(LearnableLesson.id).label("available"),
        )
        .select_from(LearnableTopic)
        .join(LearnableLesson, visible_lessons)
        .outerjoin(LessonCompletion, this_users_completions)
        .group_by(LearnableTopic.id, LearnableTopic.name)
        # In the order administrators set (SCRUM-66), so the circles stay put between
        # visits; the name breaks any tie.
        .order_by(LearnableTopic.position, LearnableTopic.name)
    )
    return visible_to_users(query)


def level_reached(quiz_level: int | None, lessons: list[tuple[int, bool]]) -> int:
    """The level a user has reached in one topic, 0 to 5 (SCRUM-100).

    `lessons` is each published lesson's level and whether it is covered (completed or
    exempted). The level is the highest one at which every lesson at that level and below
    is covered, counting only levels that have lessons, so a level with none neither holds
    the user back nor lifts them. It is never below what the aptitude test gave the topic.
    Covering every lesson reaches Level 5, so a finished topic fills its spoke on the chart.
    """
    reached = 0
    for level in sorted({level for level, _ in lessons}):
        if not all(covered for lesson_level, covered in lessons if lesson_level == level):
            break
        reached = level
    if lessons and all(covered for _, covered in lessons):
        reached = MAX_LEVEL
    return max(reached, quiz_level or 0)


def _levels(db: Session, user_id: uuid.UUID) -> dict[uuid.UUID, int]:
    """`level_reached` for every topic with a published lesson, by topic id."""
    covered = or_(
        select(LessonCompletion.id)
        .where(
            LessonCompletion.lesson_id == LearnableLesson.id, LessonCompletion.user_id == user_id
        )
        .exists(),
        is_exempted(user_id),
    )
    lessons: dict[uuid.UUID, list[tuple[int, bool]]] = {}
    for row in db.execute(
        select(LearnableLesson.topic_id, LearnableLesson.level, covered.label("covered")).where(
            LearnableLesson.publication_state == PUBLISHED
        )
    ):
        lessons.setdefault(row.topic_id, []).append((row.level, row.covered))
    quiz = exemption_levels(db, user_id)
    return {
        topic_id: level_reached(quiz.get(topic_id), topic_lessons)
        for topic_id, topic_lessons in lessons.items()
    }


def progress_for(db: Session, user_id: uuid.UUID) -> Progress:
    """Per-topic and overall figures for one user."""
    levels = _levels(db, user_id)
    topics = [
        TopicProgress(
            id=row.id,
            name=row.name,
            completed=row.completed,
            exempted=row.exempted,
            available=row.available,
            level=levels.get(row.id, 0),
        )
        for row in db.execute(_topic_rows(user_id)).all()
    ]
    # The overall figure is the sum of the circles, so the two always agree on screen
    # (SCRUM-43 AC6).
    return Progress(
        topics=topics,
        completed=sum(topic.completed for topic in topics),
        exempted=sum(topic.exempted for topic in topics),
        available=sum(topic.available for topic in topics),
        suggestion=_suggestion(db, user_id, topics),
        aptitude_taken=has_taken_quiz(db, user_id),
    )


def _suggestion(db: Session, user_id: uuid.UUID, topics: list[TopicProgress]) -> Suggestion | None:
    """The lowest-level lesson neither completed nor exempted in the weakest topic
    (SCRUM-106 AC1 and AC2, replacing SCRUM-6 AC2).

    `topics` are the circles, in order, and their `completed` already counts exempted
    lessons (SCRUM-104), so the weakest topic is chosen by the same figures the circles show.
    `sorted` is stable, so a tie goes to the order administrators set. A topic with nothing
    left is never the weakest, and the next topic is tried if a topic's lessons are all
    passed over (AC3); with everything covered there is no suggestion (AC4).
    """
    unfinished = [topic for topic in topics if topic.completed < topic.available]
    ranked = sorted(unfinished, key=lambda t: Fraction(t.completed, t.available))
    for rank, topic in enumerate(ranked):
        completed = select(LessonCompletion.id).where(
            LessonCompletion.lesson_id == LearnableLesson.id, LessonCompletion.user_id == user_id
        )
        lessons = db.scalars(
            select(LearnableLesson)
            .where(
                LearnableLesson.topic_id == topic.id,
                catalog.lesson_visible(),
                ~completed.exists(),
                ~is_exempted(user_id),
            )
            # Lowest level first, then the order administrators set within a level, as the
            # topic page lists them (SCRUM-104).
            .order_by(LearnableLesson.level, LearnableLesson.position, LearnableLesson.created_at)
        )
        for lesson in lessons:
            version = catalog.latest_deck(db, lesson)
            # A visible lesson always has its deck; one that somehow does not could not be
            # opened (app/learning.py), so it is passed over.
            if version is None:
                continue
            return Suggestion(
                lesson_id=lesson.id,
                title=version.title,
                summary=version.summary,
                reading_seconds=version.reading_seconds,
                topic_id=topic.id,
                topic_name=topic.name,
                reason=suggestion_reason(
                    topic.name,
                    weakest=rank == 0,
                    only_unfinished=len(unfinished) == 1 and len(topics) > 1,
                    nothing_covered=all(t.completed == 0 for t in topics),
                ),
            )
    return None


def suggestion_reason(
    topic_name: str, *, weakest: bool, only_unfinished: bool, nothing_covered: bool
) -> str:
    """One line on why a lesson is suggested (SCRUM-107 AC1). It names the topic and how
    the topic was chosen, and never a level, since levels are not shown to users (AC2)."""
    if nothing_covered:
        return f"The first lesson in {topic_name}, a good place to start."
    if only_unfinished:
        return f"The next lesson in {topic_name}, the only topic you haven't finished yet."
    if weakest:
        return f"The next lesson in {topic_name}, where you've done the least so far."
    # The weakest topic had nothing that could be opened, so this is the next one along.
    return f"The next lesson in {topic_name}, one of the topics with the most left to do."


@dataclass(frozen=True)
class TopicLesson:
    id: uuid.UUID
    title: str
    summary: str
    reading_seconds: int
    # Scored questions only: a one-option tap is not a quiz question.
    questions: int
    completed: bool
    exempted: bool
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
    exempted: int
    available: int
    lessons: list[TopicLesson]


def topic_lessons(db: Session, user_id: uuid.UUID, topic_id: uuid.UUID) -> TopicLessons:
    """One topic's visible lessons, in the order administrators set, with this user's
    completions (SCRUM-53). An archived or unknown topic is unavailable."""
    topic = db.scalar(visible_to_users(select(LearnableTopic).where(LearnableTopic.id == topic_id)))
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
        select(LearnableLesson, LessonCompletion, last_finished.c.at, is_exempted(user_id))
        .outerjoin(
            LessonCompletion,
            and_(
                LessonCompletion.lesson_id == LearnableLesson.id,
                LessonCompletion.user_id == user_id,
            ),
        )
        .outerjoin(last_finished, last_finished.c.lesson_id == LearnableLesson.id)
        .where(LearnableLesson.topic_id == topic.id, catalog.lesson_visible())
        .order_by(LearnableLesson.level, LearnableLesson.position, LearnableLesson.created_at)
    ).all()

    lessons = []
    for lesson, completion, last_finished_at, exempted in rows:
        version = catalog.latest_deck(db, lesson)
        # A visible lesson always has its deck; skip one that somehow does not, as opening
        # it would be refused (app/learning.py).
        if version is None:
            continue
        lessons.append(
            TopicLesson(
                id=lesson.id,
                title=version.title,
                summary=version.summary,
                # Worked out by Content as the lesson's cover does, so the two always agree.
                reading_seconds=version.reading_seconds,
                questions=version.scored_questions,
                completed=completion is not None,
                # A completed lesson takes precedence over its aptitude exemption:
                # it keeps the learner's score and no longer needs an Exempted label.
                exempted=bool(exempted and completion is None),
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
        completed=sum(1 for lesson in lessons if lesson.completed or lesson.exempted),
        exempted=sum(1 for lesson in lessons if lesson.exempted and not lesson.completed),
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
    """Visible lessons whose title or card text contains `query`, ignoring case and
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
            select(LearnableLesson, LearnableTopic, LessonCompletion.id)
            .join(LearnableTopic, LearnableTopic.id == LearnableLesson.topic_id)
            .outerjoin(
                LessonCompletion,
                and_(
                    LessonCompletion.lesson_id == LearnableLesson.id,
                    LessonCompletion.user_id == user_id,
                ),
            )
            .where(catalog.lesson_visible())
            .order_by(
                LearnableTopic.position,
                LearnableTopic.name,
                LearnableLesson.position,
                LearnableLesson.created_at,
            )
        )
    ).all()

    by_title: list[SearchResult] = []
    by_text: list[SearchResult] = []
    for lesson, topic, completion_id in rows:
        version = catalog.latest_deck(db, lesson)
        # A visible lesson always has its deck; one that somehow does not could not be
        # opened (app/learning.py), so it is passed over.
        if version is None:
            continue
        title_matches = needle in " ".join(version.title.split()).lower()
        snippet = _snippet(version.cards_plain_text, needle)
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


def _snippet(cards_plain_text: list[str], needle: str) -> str | None:
    """About SNIPPET_LENGTH characters of the first card whose text contains `needle`, cut
    so the match sits near the start, or None if no card's text does.

    `cards_plain_text` is each card's text as a reader sees it, one entry per card, as
    Content worked it out (lesson_doc.plain_text)."""
    for text in cards_plain_text:
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
