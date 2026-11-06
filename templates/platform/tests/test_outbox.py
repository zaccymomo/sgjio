import enum
import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import MetaData, create_engine, func, select, text, update
from sqlalchemy.orm import sessionmaker

from app.platform.consumer import Consumer, Outcome
from app.platform.logging import correlation_id
from app.platform.outbox import define_outbox_table, emit, envelope, run_relay, to_json
from app.platform.testing import make_envelope

pytestmark = pytest.mark.integration


@pytest.fixture
def outbox(engine):
    metadata = MetaData()
    table = define_outbox_table(metadata)
    metadata.drop_all(engine)
    metadata.create_all(engine)
    yield table
    metadata.drop_all(engine)


class Colour(enum.Enum):
    RED = "red"


def test_to_json():
    when = datetime(2026, 11, 10, 8, 0, tzinfo=UTC)
    some_id = uuid.uuid4()
    assert to_json({"id": some_id, "at": when, "c": Colour.RED, "n": [1, None]}) == {
        "id": str(some_id),
        "at": "2026-11-10T08:00:00Z",
        "c": "red",
        "n": [1, None],
    }
    with pytest.raises(ValueError):
        to_json({"at": datetime(2026, 1, 1)})


def test_emit_joins_the_callers_transaction(session_factory, outbox):
    topic_id = uuid.uuid4()
    with session_factory() as session:
        emit(
            session,
            type="content.topic.changed",
            aggregate_type="topic",
            aggregate_id=topic_id,
            aggregate_version=1,
            data={"topic_id": topic_id},
        )
        session.rollback()
        assert session.scalar(select(func.count()).select_from(outbox)) == 0

        token = correlation_id.set("req-42")
        try:
            event_id = emit(
                session,
                type="content.topic.changed",
                aggregate_type="topic",
                aggregate_id=topic_id,
                aggregate_version=2,
                data={"topic_id": topic_id},
            )
        finally:
            correlation_id.reset(token)
        session.commit()
        row = session.execute(select(outbox)).one()

    body = envelope(row)
    assert body == {
        "event_id": str(event_id),
        "type": "content.topic.changed",
        "schema_version": 1,
        "occurred_at": body["occurred_at"],
        "producer": "platformtest",
        "aggregate_type": "topic",
        "aggregate_id": str(topic_id),
        "aggregate_version": 2,
        "correlation_id": "req-42",
        "data": {"topic_id": str(topic_id)},
    }
    assert body["occurred_at"].endswith("Z")
    assert row.published_at is None


def test_handle_outcomes(session_factory):
    calls = []
    consumer = Consumer(
        routing_keys=[],
        session_factory=session_factory,
        handlers={
            "a.b.ok": lambda s, e: calls.append(e["event_id"]),
            "a.b.fails": lambda s, e: 1 / 0,
        },
    )
    ok = make_envelope("a.b.ok", {})
    assert consumer.handle(__import__("json").dumps(ok).encode()) is Outcome.ACK
    assert calls == [ok["event_id"]]
    assert (
        consumer.handle(b'{"type":"a.b.other","event_id":"' + str(uuid.uuid4()).encode() + b'"}')
        is Outcome.ACK
    )
    assert (
        consumer.handle(__import__("json").dumps(make_envelope("a.b.fails", {})).encode())
        is Outcome.REQUEUE
    )
    assert consumer.handle(b"not json") is Outcome.REJECT
    assert consumer.handle(b'{"type":"a.b.ok"}') is Outcome.REJECT


def test_handler_failure_while_the_database_is_down_is_a_retry():
    unreachable = sessionmaker(bind=create_engine("postgresql+psycopg://x:y@127.0.0.1:1/none"))
    consumer = Consumer(
        routing_keys=[],
        session_factory=unreachable,
        handlers={"a.b.ok": lambda s, e: s.execute(text("SELECT 1"))},
    )
    assert not consumer.database_available()
    body = __import__("json").dumps(make_envelope("a.b.ok", {})).encode()
    assert consumer.handle(body) is Outcome.RETRY


def test_relay_prunes_old_published_rows(session_factory, outbox, broker):
    with session_factory() as session:
        for _ in range(3):
            emit(
                session,
                type="platformtest.prune.x",
                aggregate_type="x",
                aggregate_id=uuid.uuid4(),
                aggregate_version=1,
                data={},
            )
        session.commit()
        old = session.scalars(select(outbox.c.id).order_by(outbox.c.id).limit(2)).all()
        session.execute(update(outbox).values(published_at=datetime.now(UTC)))
        session.execute(
            update(outbox)
            .where(outbox.c.id.in_(old))
            .values(published_at=datetime.now(UTC) - timedelta(days=8))
        )
        session.commit()
    stop = threading.Event()
    relay = threading.Thread(target=run_relay, args=(session_factory, stop), daemon=True)
    relay.start()

    def remaining():
        with session_factory() as session:
            return session.scalar(select(func.count()).select_from(outbox))

    try:
        deadline = datetime.now(UTC) + timedelta(seconds=10)
        while remaining() != 1 and datetime.now(UTC) < deadline:
            stop.wait(0.1)
        assert remaining() == 1  # the recent row is kept, the two old ones are gone
    finally:
        stop.set()
        relay.join(timeout=10)
