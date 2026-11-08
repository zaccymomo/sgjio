"""Notification's only table: the inbox of events it has already handled.

Sending email is not idempotent, so each handled event's id is recorded here, in the same
transaction the consumer commits after sending; an event seen again is skipped. No email
address or name is stored, so no personal data is kept at rest. Rows older than 30 days
are pruned (app/handlers.py, `prune_inbox`); processed_at is indexed for that.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ProcessedEvent(Base):
    __tablename__ = "processed_events"

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    type: Mapped[str] = mapped_column(String(100), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
