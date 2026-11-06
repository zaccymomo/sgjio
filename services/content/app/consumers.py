"""Events Content consumes: only identity.user.deleted (contracts/README.md).

Content keeps no copy of users. When an account is deleted it forgets which user reported a
problem, dealt with one, published a version or uploaded a file, by nulling those ids.
Running it twice has the same effect, so it needs no inbox or version guard.
"""

import uuid

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import LessonReport, LessonVersion, MediaAsset
from app.platform.consumer import Consumer

USER_DELETED = "identity.user.deleted"


def on_user_deleted(db: Session, envelope: dict) -> None:
    user_id = uuid.UUID(envelope["data"]["user_id"])
    for column in (
        LessonReport.reporter_id,
        LessonReport.resolved_by,
        LessonVersion.published_by,
        MediaAsset.created_by,
    ):
        db.execute(
            update(column.class_)
            .where(column == user_id)
            .values({column.key: None})
            .execution_options(synchronize_session=False)
        )


def build_consumer() -> Consumer:
    """Queue content.events (from SERVICE_NAME), bound to identity.user.deleted."""
    return Consumer(
        routing_keys=[USER_DELETED],
        handlers={USER_DELETED: on_user_deleted},
        session_factory=SessionLocal,
    )
