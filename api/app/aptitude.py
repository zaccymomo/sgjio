"""Reading users' aptitude quizzes (Epic 6).

Every quiz a user takes is kept in `aptitude_attempts` (SCRUM-110 AC4). Users are shown
their latest (SCRUM-100, SCRUM-102 AC3); earlier ones are their history.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AptitudeAttempt


def latest_attempt(db: Session, user_id: uuid.UUID) -> AptitudeAttempt | None:
    """The user's most recent quiz, or None if they have never taken one (or skipped it)."""
    return db.scalar(
        select(AptitudeAttempt)
        .where(AptitudeAttempt.user_id == user_id)
        .order_by(AptitudeAttempt.taken_at.desc(), AptitudeAttempt.id.desc())
        .limit(1)
    )


def attempts(db: Session, user_id: uuid.UUID) -> list[AptitudeAttempt]:
    """Every quiz the user has taken, newest first."""
    return list(
        db.scalars(
            select(AptitudeAttempt)
            .where(AptitudeAttempt.user_id == user_id)
            .order_by(AptitudeAttempt.taken_at.desc(), AptitudeAttempt.id.desc())
        )
    )
