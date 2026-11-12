"""Forgetting a deleted account (identity.user.deleted) and keeping it forgotten.

Content keeps no copy of users, only their ids on what they did: the learner who reported
a problem, the administrator who dealt with it, published a version, uploaded a file,
asked for an AI draft or reviewed one before publishing it.
When Identity deletes an account, Content's consumer, in one transaction:

1. takes the user's advisory lock (exclusive),
2. records the id in `erased_users` for good, and
3. nulls every one of those ids.

Repeating it changes nothing, so a redelivered event is harmless.

The gateway refuses a deleted user's session at once. A report already past the gateway
when the event is handled is the one gap: `report_problem` takes the same lock in shared
mode and checks the tombstone first, so it either commits before the erasure (and is
anonymised by it) or is refused. Learning does the same (services/learning/app/erasure.py).
"""

import uuid
from datetime import datetime

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import (
    ErasedUser,
    GenerationJob,
    Lesson,
    LessonReport,
    LessonVersion,
    MediaAsset,
)
from app.platform.errors import not_signed_in

_LOCK = "SELECT pg_advisory_xact_lock{mode}(hashtext(:key))"
USER_COLUMNS = (
    LessonReport.reporter_id,
    LessonReport.resolved_by,
    LessonVersion.published_by,
    MediaAsset.created_by,
    GenerationJob.requested_by,
    Lesson.ai_reviewed_by,
)


def _lock(db: Session, user_id: uuid.UUID, shared: bool) -> None:
    db.execute(text(_LOCK.format(mode="_shared" if shared else "")), {"key": str(user_id)})


def refuse_if_erased(db: Session, user_id: uuid.UUID) -> None:
    """Call before a learner's write records their id. The shared lock is held until the
    caller's transaction ends."""
    _lock(db, user_id, shared=True)
    if db.scalar(select(ErasedUser.user_id).where(ErasedUser.user_id == user_id)):
        raise not_signed_in()


def erase(db: Session, user_id: uuid.UUID, erased_at: datetime) -> None:
    """Tombstone the id and null it everywhere, inside the caller's transaction."""
    _lock(db, user_id, shared=False)
    db.execute(
        insert(ErasedUser)
        .values(user_id=user_id, erased_at=erased_at)
        .on_conflict_do_nothing(index_elements=["user_id"])
    )
    for column in USER_COLUMNS:
        values = {column.key: None}
        if column.class_ is Lesson:
            values["updated_at"] = Lesson.updated_at  # not an edit: the editor's copy stays valid
        db.execute(
            update(column.class_)
            .where(column == user_id)
            .values(values)
            .execution_options(synchronize_session=False)
        )
