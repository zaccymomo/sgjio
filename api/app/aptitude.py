"""Reading users' aptitude quizzes (Epic 6).

The quiz is taken once (SCRUM-113): a user has at most one completed attempt, saved with
their topic exemptions (`app/exemptions.py`). A user with no attempt has not taken it, which
after profile setup means they skipped it (SCRUM-98).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AptitudeAttempt


def quiz_attempt(db: Session, user_id: uuid.UUID) -> AptitudeAttempt | None:
    """The user's completed quiz, or None if they have not taken it (or skipped it)."""
    return db.scalar(select(AptitudeAttempt).where(AptitudeAttempt.user_id == user_id))


def has_taken_quiz(db: Session, user_id: uuid.UUID) -> bool:
    return quiz_attempt(db, user_id) is not None
