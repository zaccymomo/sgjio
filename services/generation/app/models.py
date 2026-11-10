"""Generation's tables: the outbox it publishes from, and the inbox of requests it has
already answered.

Generation keeps no lessons. Writing a lesson costs a model call, so each handled
request's event id is recorded in processed_events in the same transaction as the result
event; a redelivered request is skipped instead of paid for twice.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.platform.outbox import define_outbox_table

outbox = define_outbox_table(Base.metadata)


class ProcessedEvent(Base):
    __tablename__ = "processed_events"

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    type: Mapped[str] = mapped_column(String(100), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
