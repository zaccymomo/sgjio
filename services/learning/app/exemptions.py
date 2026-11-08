"""Per-topic exemptions from the aptitude quiz (SCRUM-113).

Each user has at most one `topic_exemptions` row per topic: the highest level they are
exempted up to there, 0 to 5. Exempted lessons are never stored. A lesson is exempted for a
user when its topic's exemption level is at least the lesson's level (SCRUM-104 AC1). Only
published lessons count, and a lesson's level is fixed from its first publish (SCRUM-103), so
this is worked out whenever it is needed (AC5).
That is also why a lesson published later at an exempted level is exempted too (SCRUM-104
AC3). A topic with no row, as for a user who skipped the quiz, exempts nothing.
"""

import uuid

from sqlalchemy import ColumnElement, Select, select
from sqlalchemy.orm import Session

from app.models import PUBLISHED, LearnableLesson, TopicExemption


def exemption_levels(db: Session, user_id: uuid.UUID) -> dict[uuid.UUID, int]:
    """The user's exemption level in each topic the quiz covered, by topic id."""
    rows = db.execute(
        select(TopicExemption.topic_id, TopicExemption.level).where(
            TopicExemption.user_id == user_id
        )
    )
    return {row.topic_id: row.level for row in rows}


def is_exempted(user_id: uuid.UUID) -> ColumnElement[bool]:
    """True for a `LearnableLesson` row the user is exempted from, for use in a query on
    lessons.

    Only the lesson's own topic counts, so an exemption in one topic never reaches another
    (SCRUM-104 AC2)."""
    return (
        select(TopicExemption.user_id)
        .where(
            TopicExemption.user_id == user_id,
            TopicExemption.topic_id == LearnableLesson.topic_id,
            TopicExemption.level >= LearnableLesson.level,
        )
        .exists()
    )


def exempted_lessons(user_id: uuid.UUID) -> Select[tuple[uuid.UUID]]:
    """The ids of the published lessons the user is exempted from, in every topic."""
    return select(LearnableLesson.id).where(
        LearnableLesson.publication_state == PUBLISHED, is_exempted(user_id)
    )
