"""The consumer keeps the read models right however events arrive: twice, late, out of
order, or for things it has never seen (contracts/README.md, "Ordering and idempotency").
New tests: the monolith had no events."""

import copy
import json
import threading
import time
import uuid

import pika
import pytest
from sqlalchemy import func, select

from app.consumers import HANDLERS, ROUTING_KEYS, consumer
from app.db import SessionLocal
from app.models import (
    LearnableLesson,
    LearnableTopic,
    Learner,
    LessonDeck,
    QuizBank,
    TopicExemption,
)
from app.platform.consumer import Consumer, Outcome
from tests.support.records import quiz


def _topic_row(db, topic) -> LearnableTopic:
    db.expire_all()
    return db.get(LearnableTopic, topic.id)


def _lesson_row(db, lesson) -> LearnableLesson:
    db.expire_all()
    return db.get(LearnableLesson, lesson.id)


def _last(bus, type: str, aggregate_id=None) -> dict:
    return [
        e
        for e in bus.sent
        if e["type"] == type and (aggregate_id is None or e["aggregate_id"] == str(aggregate_id))
    ][-1]


def test_the_queue_binds_what_learning_consumes():
    assert consumer.queue == "learning.events"
    assert ROUTING_KEYS == ["identity.user.*", "content.#", "generation.lesson.*"]
    assert set(HANDLERS) == {
        "content.topic.changed",
        "content.topic.deleted",
        "content.lesson.changed",
        "content.lesson_version.published",
        "content.aptitude_question.changed",
        "content.aptitude_bank.changed",
        "identity.user.registered",
        "identity.user.deleted",
        "generation.lesson.progress",
        "generation.lesson.generated",
        "generation.lesson.failed",
    }


# --- Duplicates ------------------------------------------------------------------------------


def test_a_duplicate_event_changes_nothing(db, bus, content):
    topic = content.topic("Singlish")
    lesson = content.lesson(topic, "Lah")
    for envelope in list(bus.sent):
        bus.deliver(envelope)
        bus.deliver(copy.deepcopy(envelope) | {"event_id": str(uuid.uuid4())})

    assert db.scalar(select(func.count()).select_from(LearnableTopic)) == 1
    assert db.scalar(select(func.count()).select_from(LessonDeck)) == 1
    assert _lesson_row(db, lesson).version == 1
    assert _topic_row(db, topic).name == "Singlish"


def test_a_deck_is_inserted_once_and_never_changed(db, bus, content):
    lesson = content.lesson(content.topic(), "Lah")
    deck_event = _last(bus, "content.lesson_version.published")
    altered = copy.deepcopy(deck_event)
    altered["data"]["title"] = "Something else"
    bus.deliver(altered)

    db.expire_all()
    assert db.get(LessonDeck, lesson.versions[0].id).title == "Lah"


# --- Out of order ----------------------------------------------------------------------------


def test_a_stale_topic_event_is_ignored(db, bus, content):
    topic = content.topic("Singlish")
    first = _last(bus, "content.topic.changed")
    content.update_topic(topic, name="Singlish 101", position=4)
    bus.deliver(first)

    row = _topic_row(db, topic)
    assert (row.name, row.position, row.version) == ("Singlish 101", 4, 2)


def test_a_newer_event_arriving_first_wins(db, bus, content):
    topic = content.topic("Singlish")
    content.update_topic(topic, name="Renamed")
    # Replay history newest first into an empty read model.
    db.execute(LearnableTopic.__table__.delete())
    db.commit()
    for envelope in reversed([e for e in bus.sent if e["type"] == "content.topic.changed"]):
        bus.deliver(envelope)

    assert _topic_row(db, topic).name == "Renamed"


def test_a_stale_lesson_event_cannot_undo_a_withdrawal(client, db, bus, content, make_user):
    lesson = content.lesson(content.topic(), "Lah")
    published = _last(bus, "content.lesson.changed")
    content.withdraw(lesson)
    bus.deliver(published)

    row = _lesson_row(db, lesson)
    assert (row.publication_state, row.learner_visible, row.version) == ("withdrawn", False, 2)


def test_a_lesson_changed_before_its_topic_arrives_shows_once_the_topic_does(
    client, db, bus, content, make_user
):
    from tests.conftest import sign_in

    sign_in(client, make_user())
    topic = content.topic("Singlish")
    lesson = content.lesson(topic, "Lah")
    db.execute(LearnableTopic.__table__.delete())
    db.commit()
    assert client.get(f"/api/lessons/{lesson.id}").status_code == 404

    bus.deliver(_last(bus, "content.topic.changed"))
    assert client.get(f"/api/lessons/{lesson.id}").status_code == 200


# --- Tombstones ------------------------------------------------------------------------------


def test_a_deleted_topic_is_never_brought_back_by_a_stale_event(db, bus, content):
    topic = content.topic("Short-lived")
    changed = _last(bus, "content.topic.changed")
    content.delete_topic(topic)
    bus.deliver(changed)

    row = _topic_row(db, topic)
    assert (row.deleted, row.version) == (True, 2)


def test_a_delete_for_a_topic_never_seen_leaves_a_tombstone(db, bus, content):
    """The delete overtook the topic's own event: the late `changed` must not create it."""
    topic = content.topic("Short-lived")
    changed = _last(bus, "content.topic.changed")
    db.execute(LearnableTopic.__table__.delete())
    db.commit()
    content.delete_topic(topic)
    bus.deliver(changed)

    assert _topic_row(db, topic).deleted is True


def test_deleting_a_topic_with_exemptions_is_refused_and_changes_nothing(
    db, bus, content, make_user
):
    """Impossible by Content's rule (topics.assessed_at); if it ever happens the event fails,
    so it ends in the DLQ for a person, and no learner's exemption is touched."""
    topic = content.topic("Assessed")
    quiz(db, make_user(), {topic: 2})
    content.delete_topic(topic, expect=Outcome.REQUEUE)

    assert _topic_row(db, topic).deleted is False
    assert db.scalar(select(func.count()).select_from(TopicExemption)) == 1


# --- Identity ------------------------------------------------------------------------------


def test_only_learners_are_kept(db, make_user):
    learner = make_user("learner@example.com", user_type="singaporean")
    make_user("admin@example.com", role="admin")

    rows = db.execute(select(Learner.user_id, Learner.user_type)).all()
    assert rows == [(learner.id, "singaporean")]


def test_a_repeated_registration_keeps_one_learner(db, bus, make_user):
    make_user()
    bus.deliver(_last(bus, "identity.user.registered"))
    assert db.scalar(select(func.count()).select_from(Learner)) == 1


# --- What the consumer is given ---------------------------------------------------------------


def test_unknown_fields_are_ignored(db, bus, content):
    """Tolerant reader: a field Content adds later is not a breaking change."""
    topic = content.topic("Singlish")
    newer = copy.deepcopy(_last(bus, "content.topic.changed"))
    newer["aggregate_version"] = 2
    newer["data"]["name"] = "Singlish, renamed"
    newer["data"]["colour"] = "#F43F5E"
    newer["envelope_extra"] = True
    bus.deliver(newer)

    assert _topic_row(db, topic).name == "Singlish, renamed"


def test_an_event_learning_has_no_handler_for_is_acknowledged(bus):
    envelope = bus.envelope(
        "identity.password_reset.requested",
        {
            "user_id": str(uuid.uuid4()),
            "email": "x@example.com",
            "name": "X",
            "audience": "app",
            "method": "password",
            "link": "http://localhost:5173/reset-password?token=abc",
            "expires_in_minutes": 15,
        },
        uuid.uuid4(),
        1,
        aggregate_type="user",
    )
    assert bus.deliver(envelope) is Outcome.ACK


def test_a_message_that_is_not_an_event_is_rejected():
    assert consumer.handle(b"not json") is Outcome.REJECT
    assert consumer.handle(json.dumps({"type": "content.topic.changed"}).encode()) is (
        Outcome.REJECT
    )


def test_a_broken_event_is_retried_not_half_applied(db, bus, content):
    topic = content.topic("Singlish")
    broken = copy.deepcopy(_last(bus, "content.topic.changed"))
    broken["aggregate_version"] = 2
    del broken["data"]["name"]
    assert bus.deliver(broken, Outcome.REQUEUE) is Outcome.REQUEUE
    assert _topic_row(db, topic).version == 1


def test_the_bank_keeps_its_single_row(db, content):
    topic = content.topic()
    content.question(topic, 1)
    content.question(topic, 2)
    assert db.scalar(select(func.count()).select_from(QuizBank)) == 1
    db.expire_all()
    assert db.scalar(select(QuizBank.revision)) == 2


# --- Through RabbitMQ -------------------------------------------------------------------------


def _broker_or_skip():
    try:
        return pika.BlockingConnection(pika.URLParameters("amqp://sgjio:sgjio@localhost:5672/%2F"))
    except Exception:  # noqa: BLE001
        pytest.skip("needs the compose RabbitMQ on localhost:5672")


@pytest.mark.integration
def test_an_event_published_on_the_exchange_reaches_the_read_model(db, bus):
    """The real path: sgjio.events -> a quorum queue declared by Consumer -> consumer thread.

    It stays off the shared stack: its throwaway queue is bound only to a private routing
    key that no real queue binds (the consumer dispatches on the envelope's type, not the
    key), so a running Learning never sees this event and nothing reaches sgjio.unrouted.
    The test declares the queue and its binding itself before publishing, so the message
    can't arrive before the consumer thread has bound it."""
    from app.platform.broker import EXCHANGE

    connection = _broker_or_skip()
    queue = f"learning-test-{uuid.uuid4().hex[:8]}"
    key = f"learning-test.{queue}"
    test_consumer = Consumer(
        routing_keys=[key],
        handlers=HANDLERS,
        session_factory=SessionLocal,
        queue=queue,
        broker_url="amqp://sgjio:sgjio@localhost:5672/%2F",
    )
    channel = connection.channel()
    stop = threading.Event()
    thread = threading.Thread(target=test_consumer.run, args=(stop,), daemon=True)
    try:
        test_consumer.declare(channel)  # idempotent; the thread declares the same again
        channel.confirm_delivery()
        thread.start()
        topic_id = uuid.uuid4()
        envelope = bus.envelope(
            "content.topic.changed",
            {
                "topic_id": str(topic_id),
                "name": "Over the wire",
                "description": "",
                "position": 0,
                "is_archived": False,
            },
            topic_id,
            1,
        )
        # mandatory + confirms: an unroutable publish raises here instead of timing out
        channel.basic_publish(
            EXCHANGE,
            key,
            json.dumps(envelope).encode(),
            pika.BasicProperties(message_id=envelope["event_id"], type=envelope["type"]),
            mandatory=True,
        )
        deadline = time.monotonic() + 10
        row = None
        while time.monotonic() < deadline and row is None:
            db.expire_all()
            row = db.get(LearnableTopic, topic_id)
            time.sleep(0.1)
        assert row is not None and row.name == "Over the wire"
    finally:
        stop.set()
        if thread.is_alive():
            thread.join(timeout=10)
        channel = connection.channel()
        channel.queue_delete(queue)
        channel.queue_delete(f"{queue}.dlq")
        connection.close()
