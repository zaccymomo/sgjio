"""Transactional outbox (producers: Identity, Content).

1. Define the table once on the service's own metadata, so it is in its models and its
   Alembic migrations:          outbox = define_outbox_table(Base.metadata)
2. Write events in the same transaction as the change they describe:
       emit(db, type="content.topic.changed", aggregate_type="topic",
            aggregate_id=topic.id, aggregate_version=topic.version, data={...})
       db.commit()
3. `run_relay` (a background thread, see lifespan.py) publishes unpublished rows in id
   order with publisher confirms, then marks them published. Delivery is at least once:
   a crash between publishing and marking publishes the row again, so consumers are
   idempotent (contracts/README.md). The relay also deletes rows published more than
   7 days ago, about once an hour (`prune_published`), so the table stays small.
"""

import json
import logging
import threading
import time
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from enum import Enum

import pika
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Index,
    MetaData,
    String,
    Table,
    delete,
    func,
    insert,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Session

from .broker import EXCHANGE, RECONNECT_BACKOFF_MAX, close_quietly, connect, declare_exchanges
from .config import get_config
from .logging import correlation_id

SCHEMA_VERSION = 1
log = logging.getLogger("sgjio.relay")
_table: Table | None = None


def define_outbox_table(metadata: MetaData, name: str = "outbox") -> Table:
    """The outbox table on the service's metadata. Call once, from the models module."""
    global _table
    _table = Table(
        name,
        metadata,
        # Only the relay's cursor: ordering for consumers comes from aggregate_version.
        Column("id", BigInteger, primary_key=True, autoincrement=True),
        Column("event_id", UUID(as_uuid=True), nullable=False, unique=True),
        Column("type", String(100), nullable=False),
        Column("aggregate_type", String(50), nullable=False),
        Column("aggregate_id", UUID(as_uuid=True), nullable=False),
        Column("aggregate_version", BigInteger, nullable=False),
        Column("payload", JSONB, nullable=False),  # the envelope's `data`
        Column("correlation_id", String(128)),
        Column("occurred_at", DateTime(timezone=True), nullable=False),
        Column("published_at", DateTime(timezone=True)),
        Index(f"ix_{name}_unpublished", "id", postgresql_where=text("published_at IS NULL")),
    )
    return _table


def _outbox(table: Table | None) -> Table:
    table = table if table is not None else _table
    if table is None:
        raise RuntimeError("define_outbox_table() has not been called")
    return table


def _json_default(value):
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("event datetimes must be timezone-aware")
        return _timestamp(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"{type(value).__name__} is not JSON serialisable")


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def to_json(data) -> object:
    """`data` as plain JSON values: UUIDs and enums become strings, datetimes ISO 8601 UTC."""
    return json.loads(json.dumps(data, default=_json_default))


def emit(
    session: Session,
    *,
    type: str,
    aggregate_type: str,
    aggregate_id: uuid.UUID | str,
    aggregate_version: int,
    data: dict,
    table: Table | None = None,
) -> uuid.UUID:
    """Add an event to the outbox in the caller's transaction. Returns its event_id."""
    event_id = uuid.uuid4()
    session.execute(
        insert(_outbox(table)).values(
            event_id=event_id,
            type=type,
            aggregate_type=aggregate_type,
            aggregate_id=uuid.UUID(str(aggregate_id)),
            aggregate_version=aggregate_version,
            payload=to_json(data),
            correlation_id=correlation_id.get(),
            occurred_at=datetime.now(UTC),
        )
    )
    return event_id


def envelope(row) -> dict:
    """The message body for an outbox row (contracts/events/envelope.schema.json)."""
    return {
        "event_id": str(row.event_id),
        "type": row.type,
        "schema_version": SCHEMA_VERSION,
        "occurred_at": _timestamp(row.occurred_at),
        "producer": get_config().service_name,
        "aggregate_type": row.aggregate_type,
        "aggregate_id": str(row.aggregate_id),
        "aggregate_version": row.aggregate_version,
        "correlation_id": row.correlation_id,
        "data": row.payload,
    }


def publish_pending(
    session_factory: Callable[[], Session], channel, batch_size: int = 100, table=None
) -> int:
    """Publish one batch of unpublished rows, in id order, and mark them published.

    FOR UPDATE SKIP LOCKED lets a second relay (if one is ever started) take other rows
    instead of waiting. Returns how many rows were published."""
    outbox = _outbox(table)
    with session_factory() as session, session.begin():
        rows = session.execute(
            select(outbox)
            .where(outbox.c.published_at.is_(None))
            .order_by(outbox.c.id)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        ).all()
        for row in rows:
            body = envelope(row)
            channel.basic_publish(
                exchange=EXCHANGE,
                routing_key=row.type,
                body=json.dumps(body).encode(),
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=pika.DeliveryMode.Persistent,
                    message_id=body["event_id"],
                    type=row.type,
                    app_id=body["producer"],
                    timestamp=int(row.occurred_at.timestamp()),
                    headers={"x-correlation-id": row.correlation_id or ""},
                ),
            )  # with confirms on, this returns once the broker has the message
        if rows:
            session.execute(
                update(outbox)
                .where(outbox.c.id.in_([row.id for row in rows]))
                .values(published_at=func.now())
            )
    return len(rows)


def prune_published(session: Session, older_than: timedelta = timedelta(days=7), table=None):
    """Delete rows published more than `older_than` ago. Safe: ordering never uses ids."""
    outbox = _outbox(table)
    cutoff = datetime.now(UTC) - older_than
    return session.execute(delete(outbox).where(outbox.c.published_at < cutoff)).rowcount


def _prune(session_factory, keep_published: timedelta, table) -> None:
    try:
        with session_factory() as session, session.begin():
            deleted = prune_published(session, keep_published, table)
        if deleted:
            log.info("pruned %d published outbox rows", deleted)
    except Exception as error:  # noqa: BLE001 - pruning is housekeeping; try next time
        log.warning("outbox prune failed (%s)", error)


def run_relay(
    session_factory: Callable[[], Session],
    stop: threading.Event,
    *,
    poll_interval: float = 0.25,
    batch_size: int = 100,
    table: Table | None = None,
    broker_url: str | None = None,
    prune_every: float = 3600.0,
    keep_published: timedelta = timedelta(days=7),
) -> None:
    """Publish the outbox until `stop` is set. Reconnects with backoff on any failure
    (broker or database down), so it never dies while the service runs. Every
    `prune_every` seconds it also deletes rows published more than `keep_published` ago."""
    backoff = 1.0
    next_prune = time.monotonic()
    while not stop.is_set():
        connection = None
        try:
            connection = connect("relay", broker_url)
            channel = connection.channel()
            declare_exchanges(channel)
            channel.confirm_delivery()
            log.info("outbox relay connected")
            backoff = 1.0
            while not stop.is_set():
                if publish_pending(session_factory, channel, batch_size, table) < batch_size:
                    connection.sleep(poll_interval)  # also keeps the heartbeat going
                if time.monotonic() >= next_prune:
                    next_prune = time.monotonic() + prune_every
                    _prune(session_factory, keep_published, table)
        except Exception as error:  # noqa: BLE001 - keep the relay alive whatever happens
            log.warning("outbox relay failed (%s); retrying in %.0fs", error, backoff)
            stop.wait(backoff)
            backoff = min(backoff * 2, RECONNECT_BACKOFF_MAX)
        finally:
            close_quietly(connection)
