"""What learners may see of Content's catalogue, read from Learning's read models.

Content decides whether a lesson is visible to learners (published, in a topic that is not
archived) and sends the answer as `learner_visible`; Learning only filters on it. Two local
conditions are added, so a page never shows something it cannot open while events are
still arriving:

- the lesson's latest deck has arrived (`content.lesson_version.published` is written
  before `content.lesson.changed`, so this only matters if they arrive out of order), and
- its topic is known here and is neither archived nor deleted (the topic's own state).

`learner_lesson`, the circles, the topic page, the suggestion, search, review and the
aptitude result all use `lesson_visible()`, so they always agree.
"""

import uuid

from sqlalchemy import ColumnElement, Select, and_, select
from sqlalchemy.orm import Session, aliased

from app.models import LearnableLesson, LearnableTopic, LessonDeck


def visible_to_users(query: Select) -> Select:
    """Restrict a query on LearnableTopic to topics users may see."""
    return query.where(LearnableTopic.is_archived.is_(False), LearnableTopic.deleted.is_(False))


def topic_visible(topic: LearnableTopic | None) -> bool:
    return topic is not None and not topic.is_archived and not topic.deleted


def lesson_visible() -> ColumnElement[bool]:
    """True for a LearnableLesson row learners can open (see the module docstring)."""
    deck = aliased(LessonDeck)
    topic = aliased(LearnableTopic)
    return and_(
        LearnableLesson.learner_visible.is_(True),
        select(deck.id).where(deck.id == LearnableLesson.latest_version_id).exists(),
        select(topic.id)
        .where(
            topic.id == LearnableLesson.topic_id,
            topic.is_archived.is_(False),
            topic.deleted.is_(False),
        )
        .exists(),
    )


def latest_deck(db: Session, lesson: LearnableLesson) -> LessonDeck | None:
    """The lesson's latest published version, if it has arrived."""
    return db.get(LessonDeck, lesson.latest_version_id)


def is_open(db: Session, lesson: LearnableLesson | None) -> bool:
    """Whether learners may open this lesson, by the same rule as `lesson_visible()`."""
    return (
        lesson is not None
        and lesson.learner_visible
        and topic_visible(db.get(LearnableTopic, lesson.topic_id))
        and latest_deck(db, lesson) is not None
    )


def topic_name(db: Session, topic_id: uuid.UUID) -> str | None:
    topic = db.get(LearnableTopic, topic_id)
    return topic.name if topic is not None and not topic.deleted else None
