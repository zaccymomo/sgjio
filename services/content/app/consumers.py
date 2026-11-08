"""Events Content consumes: only identity.user.deleted (contracts/README.md).

Content keeps no copy of users. When an account is deleted it forgets which user reported a
problem, dealt with one, published a version or uploaded a file, by nulling those ids, and
tombstones the id (app/erasure.py). Running it twice has the same effect, so it needs no
inbox or version guard.
"""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.erasure import erase
from app.platform.consumer import Consumer

USER_DELETED = "identity.user.deleted"


def on_user_deleted(db: Session, envelope: dict) -> None:
    data = envelope["data"]
    erase(db, uuid.UUID(data["user_id"]), datetime.fromisoformat(data["deleted_at"]))


def build_consumer() -> Consumer:
    """Queue content.events, bound to identity.user.deleted. Named here rather than from
    SERVICE_NAME, so a host run without it still consumes the right queue."""
    return Consumer(
        queue="content.events",
        routing_keys=[USER_DELETED],
        handlers={USER_DELETED: on_user_deleted},
        session_factory=SessionLocal,
    )
