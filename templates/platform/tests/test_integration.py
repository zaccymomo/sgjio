"""Outbox -> relay -> RabbitMQ -> consumer, against the compose broker and Postgres."""

import json
import threading
import time
import uuid

import pika
import pytest
from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    func,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import UUID, insert
from sqlalchemy.orm import sessionmaker

from app.platform.broker import EXCHANGE
from app.platform.consumer import Consumer
from app.platform.outbox import define_outbox_table, emit, run_relay
from app.platform.testing import make_envelope

pytestmark = pytest.mark.integration


def wait_for(condition, timeout=20.0, interval=0.1):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(interval)
    return False


@pytest.fixture
def tables(engine):
    metadata = MetaData()
    outbox = define_outbox_table(metadata)
    # What a consumer's read model looks like: one row per aggregate, version-guarded.
    seen = Table(
        "platformtest_seen",
        metadata,
        Column("aggregate_id", UUID(as_uuid=True), primary_key=True),
        Column("version", Integer, nullable=False),
        Column("name", String(50), nullable=False),
    )
    metadata.drop_all(engine)
    metadata.create_all(engine)
    yield outbox, seen
    metadata.drop_all(engine)


@pytest.fixture
def cleanup_queues(broker):
    names = []
    yield names
    channel = broker.channel()
    for name in names:
        channel.queue_delete(name)
        channel.queue_delete(f"{name}.dlq")
    channel.close()


def get_one(broker, queue, timeout=20.0):
    channel = broker.channel()
    found = []

    def poll():
        method, properties, body = channel.basic_get(queue, auto_ack=True)
        if method:
            found.append((properties, body))
        return bool(found)

    wait_for(poll, timeout)
    channel.close()
    return found[0] if found else None


def test_relay_and_consumer_end_to_end(session_factory, tables, broker, unique, cleanup_queues):
    outbox, seen = tables
    calls = []

    def on_changed(session, envelope):
        calls.append(envelope["event_id"])
        # Version-guarded upsert: duplicates and stale versions change nothing.
        statement = insert(seen).values(
            aggregate_id=envelope["aggregate_id"],
            version=envelope["aggregate_version"],
            name=envelope["data"]["name"],
        )
        session.execute(
            statement.on_conflict_do_update(
                index_elements=[seen.c.aggregate_id],
                set_={"version": statement.excluded.version, "name": statement.excluded.name},
                where=seen.c.version < statement.excluded.version,
            )
        )

    def on_fails(session, envelope):
        raise RuntimeError("always fails")

    queue = f"{unique}.events"
    cleanup_queues.append(queue)
    consumer = Consumer(
        queue=queue,
        routing_keys=[f"{unique}.#"],
        handlers={f"{unique}.thing.changed": on_changed, f"{unique}.thing.fails": on_fails},
        session_factory=session_factory,
    )
    channel = broker.channel()
    consumer.declare(channel)  # before anything is published, as at service start-up
    channel.close()

    stop = threading.Event()
    threads = [
        threading.Thread(
            target=run_relay,
            args=(session_factory, stop),
            kwargs={"poll_interval": 0.05},
            daemon=True,
        ),
        threading.Thread(target=consumer.run, args=(stop,), daemon=True),
    ]
    for thread in threads:
        thread.start()
    try:
        first, second = uuid.uuid4(), uuid.uuid4()
        with session_factory() as session:
            for aggregate, version, name in [
                (first, 1, "one"),
                (first, 2, "two"),
                (second, 1, "only"),
            ]:
                emit(
                    session,
                    type=f"{unique}.thing.changed",
                    aggregate_type="thing",
                    aggregate_id=aggregate,
                    aggregate_version=version,
                    data={"name": name},
                )
            emit(
                session,
                type=f"{unique}.thing.unknown",
                aggregate_type="thing",
                aggregate_id=second,
                aggregate_version=1,
                data={},
            )
            session.commit()

        def rows():
            with session_factory() as session:
                return {r.aggregate_id: (r.version, r.name) for r in session.execute(select(seen))}

        assert wait_for(lambda: rows() == {first: (2, "two"), second: (1, "only")})
        assert wait_for(lambda: len(calls) == 3)
        with session_factory() as session:
            assert (
                session.scalar(
                    select(func.count()).select_from(outbox).where(outbox.c.published_at.is_(None))
                )
                == 0
            )

        # Redelivery: publish every row again. Handlers run again, state doesn't change.
        with session_factory() as session:
            session.execute(update(outbox).values(published_at=None))
            session.commit()
        assert wait_for(lambda: len(calls) == 6)
        assert rows() == {first: (2, "two"), second: (1, "only")}

        # Arriving out of order: an older version after a newer one is ignored.
        with session_factory() as session:
            emit(
                session,
                type=f"{unique}.thing.changed",
                aggregate_type="thing",
                aggregate_id=first,
                aggregate_version=1,
                data={"name": "stale"},
            )
            session.commit()
        assert wait_for(lambda: len(calls) == 7)
        assert rows()[first] == (2, "two")

        # The unknown type was acknowledged and dropped, not left in the queue.
        check = broker.channel()
        assert check.queue_declare(queue, passive=True).method.message_count == 0
        check.close()

        # A handler that always fails: 5 deliveries, then the dead-letter queue.
        with session_factory() as session:
            failing_id = emit(
                session,
                type=f"{unique}.thing.fails",
                aggregate_type="thing",
                aggregate_id=first,
                aggregate_version=3,
                data={},
            )
            session.commit()
        dead = get_one(broker, f"{queue}.dlq", timeout=30)
        assert dead is not None, "failing message never reached the DLQ"
        properties, body = dead
        assert properties.message_id == str(failing_id)
        assert json.loads(body)["type"] == f"{unique}.thing.fails"

        # A message that isn't JSON goes straight to the dead-letter queue.
        publish = broker.channel()
        publish.basic_publish(
            EXCHANGE, f"{unique}.thing.changed", b"not json", pika.BasicProperties(delivery_mode=2)
        )
        publish.close()
        dead = get_one(broker, f"{queue}.dlq", timeout=10)
        assert dead is not None and dead[1] == b"not json"
    finally:
        stop.set()
        for thread in threads:
            thread.join(timeout=10)
    assert not any(thread.is_alive() for thread in threads), "threads did not stop"


def test_message_properties_and_dedupe(session_factory, tables, broker, unique, cleanup_queues):
    outbox, _ = tables
    queue = f"{unique}.events"
    cleanup_queues.append(queue)
    processed: set[uuid.UUID] = set()
    calls = []

    def handler(session, envelope):
        calls.append(envelope["event_id"])
        processed.add(uuid.UUID(envelope["event_id"]))  # an inbox would insert a row here

    consumer = Consumer(
        queue=queue,
        routing_keys=[f"{unique}.#"],
        handlers={f"{unique}.mail.requested": handler},
        session_factory=session_factory,
        dedupe=lambda session, event_id: event_id in processed,
    )
    channel = broker.channel()
    consumer.declare(channel)
    channel.close()

    with session_factory() as session:
        event_id = emit(
            session,
            type=f"{unique}.mail.requested",
            aggregate_type="user",
            aggregate_id=uuid.uuid4(),
            aggregate_version=1,
            data={"to": "a@b.c"},
        )
        session.commit()

    stop = threading.Event()
    relay = threading.Thread(target=run_relay, args=(session_factory, stop), daemon=True)
    consumer_thread = threading.Thread(target=consumer.run, args=(stop,), daemon=True)
    relay.start()
    try:
        message = get_one(broker, queue)  # read it raw first: check the AMQP properties
        assert message is not None
        properties, body = message
        assert properties.message_id == str(event_id)
        assert properties.type == f"{unique}.mail.requested"
        assert properties.delivery_mode == 2
        assert properties.content_type == "application/json"
        assert properties.app_id == unique
        assert json.loads(body)["event_id"] == str(event_id)

        def unpublished():
            with session_factory() as session:
                return session.scalar(
                    select(func.count()).select_from(outbox).where(outbox.c.published_at.is_(None))
                )

        consumer_thread.start()
        for expected_calls in (1, 1):  # the same event twice: the handler runs once
            with session_factory() as session:
                session.execute(update(outbox).values(published_at=None))
                session.commit()
            assert wait_for(lambda: unpublished() == 0)
            assert wait_for(lambda n=expected_calls: len(calls) == n)
        check = broker.channel()
        assert wait_for(lambda: check.queue_declare(queue, passive=True).method.message_count == 0)
        check.close()
        time.sleep(0.5)
        assert calls == [str(event_id)]
    finally:
        stop.set()
        relay.join(timeout=10)
        if consumer_thread.ident:
            consumer_thread.join(timeout=10)


def test_background_workers_follow_the_flags(
    session_factory, tables, broker, unique, cleanup_queues
):
    from app.platform.config import configure
    from app.platform.lifespan import background_workers

    queue = f"{unique}.events"
    cleanup_queues.append(queue)
    consumer = Consumer(
        queue=queue, routing_keys=[f"{unique}.#"], handlers={}, session_factory=session_factory
    )

    def ours():
        return [t for t in threading.enumerate() if t.name.endswith(("-relay", "-consumer"))]

    configure(run_relay=False, run_consumer=False)
    with background_workers(session_factory, relay=True, consumers=[consumer]):
        assert ours() == []

    configure(run_relay=True, run_consumer=True)
    with background_workers(session_factory, relay=True, consumers=[consumer]):
        assert {t.name for t in ours()} == {f"{queue}-consumer", f"{unique}-relay"}
        time.sleep(1)  # let them connect, so stopping is tested on live connections
    assert ours() == []


def test_database_outage_does_not_dead_letter(session_factory, broker, unique, cleanup_queues):
    """Postgres down for longer than all the retry pauses put together: the message is
    held, not dead-lettered, and is handled once the database is back."""
    queue = f"{unique}.events"
    cleanup_queues.append(queue)
    unreachable = sessionmaker(bind=create_engine("postgresql+psycopg://x:y@127.0.0.1:1/none"))
    current = {"factory": unreachable}
    calls = []

    def handler(session, envelope):
        session.execute(text("SELECT 1"))  # a real handler touches its database
        calls.append(1)

    consumer = Consumer(
        queue=queue,
        routing_keys=[f"{unique}.#"],
        handlers={f"{unique}.thing.changed": handler},
        session_factory=lambda: current["factory"](),
    )
    channel = broker.channel()
    consumer.declare(channel)
    body = json.dumps(make_envelope(f"{unique}.thing.changed", {})).encode()
    channel.basic_publish(EXCHANGE, f"{unique}.thing.changed", body)
    channel.close()

    stop = threading.Event()
    thread = threading.Thread(target=consumer.run, args=(stop,), daemon=True)
    thread.start()
    try:
        time.sleep(15)  # the old behaviour dead-lettered it after about 8 s
        check = broker.channel()
        assert check.queue_declare(f"{queue}.dlq", passive=True).method.message_count == 0
        check.close()
        assert calls == []

        current["factory"] = session_factory  # the database comes back
        assert wait_for(lambda: calls == [1], timeout=20)
        check = broker.channel()
        assert wait_for(lambda: check.queue_declare(queue, passive=True).method.message_count == 0)
        assert check.queue_declare(f"{queue}.dlq", passive=True).method.message_count == 0
        check.close()
    finally:
        stop.set()
        thread.join(timeout=15)
    assert not thread.is_alive()
