"""Erasing a learner (identity.user.deleted) and keeping them erased.

Identity deletes the account and, in the same transaction, writes `identity.user.deleted`.
Learning's consumer then, in one transaction:

1. takes the learner's advisory lock (exclusive),
2. records the id in `erased_learners` for good, so a replayed `user.registered` can never
   bring them back, and
3. deletes everything Learning holds about them: attempts (and their answers), completions,
   the aptitude quiz (and its exemptions), generated lessons (and their attempts, answers
   and reports) and the `learners` row.

Every step has the same effect if repeated, so a redelivered event is harmless.

The gateway already refuses a deleted user's session, so their requests stop at once. A
request already in flight when the event is handled is the one gap; the two writes that
create a learner's rows from nothing (starting a lesson attempt, submitting the quiz,
requesting a generated lesson or starting one)
take the same lock in shared mode and check the tombstone first, so they either commit
before the purge (and are purged) or are refused. Answering and finishing only ever touch
an attempt that already exists, which the purge removes.
"""

import uuid
from datetime import datetime

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import (
    AptitudeAttempt,
    ErasedLearner,
    GeneratedLesson,
    Learner,
    LessonAttempt,
    LessonCompletion,
)
from app.platform.errors import not_signed_in

_LOCK = "SELECT pg_advisory_xact_lock{mode}(hashtext(:key))"


def _lock(db: Session, user_id: uuid.UUID, shared: bool) -> None:
    db.execute(text(_LOCK.format(mode="_shared" if shared else "")), {"key": str(user_id)})


def refuse_if_erased(db: Session, user_id: uuid.UUID) -> None:
    """Call at the start of a write that creates a learner's rows (see the module docstring).
    The shared lock is held until the caller's transaction ends."""
    _lock(db, user_id, shared=True)
    if db.scalar(select(ErasedLearner.user_id).where(ErasedLearner.user_id == user_id)):
        raise not_signed_in()


def is_erased(db: Session, user_id: uuid.UUID) -> bool:
    return db.get(ErasedLearner, user_id) is not None


def erase(db: Session, user_id: uuid.UUID, erased_at: datetime) -> None:
    """Purge a learner and tombstone the id, inside the caller's transaction."""
    _lock(db, user_id, shared=False)
    db.execute(
        insert(ErasedLearner)
        .values(user_id=user_id, erased_at=erased_at)
        .on_conflict_do_nothing(index_elements=["user_id"])
    )
    # Attempts first: an in-flight finish holds its attempt's row lock, so this waits for it
    # and the completions delete below then sees the completion it wrote.
    db.execute(delete(LessonAttempt).where(LessonAttempt.user_id == user_id))
    db.execute(delete(LessonCompletion).where(LessonCompletion.user_id == user_id))
    # Exemptions go with the quiz (ON DELETE CASCADE).
    db.execute(delete(AptitudeAttempt).where(AptitudeAttempt.user_id == user_id))
    # Attempts, answers and reports go with their generated lesson (ON DELETE CASCADE).
    db.execute(delete(GeneratedLesson).where(GeneratedLesson.user_id == user_id))
    db.execute(delete(Learner).where(Learner.user_id == user_id))
