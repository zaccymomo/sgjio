"""Event consumer base (Content, Learning, Notification).

    consumer = Consumer(
        routing_keys=["identity.user.*", "content.#"],
        handlers={"identity.user.deleted": on_user_deleted, ...},
        session_factory=SessionLocal,
    )

It declares, in code, the service's own quorum queue `<service>.events` with its bindings
and dead-lettering. Each message runs its handler inside one database transaction, which
the consumer commits; then it is acknowledged. Types without a handler are acknowledged
and skipped.

When a handler raises, the consumer asks the database `SELECT 1`:
- The database answers: the handler itself failed (a bug, bad data). The message is
  requeued after a short pause (0.5 s, 1 s, 2 s, 4 s) and on its 5th failure
  (`max_attempts`) moves to `<service>.events.dlq`.
- The database is down: that is an outage, not the message's fault. The consumer waits,
  holding the message, until the database answers (or the service stops), then requeues
  it without counting an attempt. Nothing is dead-lettered because Postgres restarted.

Handlers are `handler(session, envelope)` and must be idempotent: a message can arrive
twice, and out of order (contracts/README.md). Handlers must not commit.
`dedupe(session, event_id) -> bool`, if given, is asked first; True skips the message
(Notification's inbox: emails are not idempotent).
"""

import hashlib
import json
import logging
import threading
import time
import uuid
from collections.abc import Callable, Iterable
from enum import Enum

from sqlalchemy import text
from sqlalchemy.orm import Session

from .broker import DLX, EXCHANGE, close_quietly, connect, declare_exchanges
from .config import get_config
from .logging import correlation_id

log = logging.getLogger("sgjio.consumer")
Handler = Callable[[Session, dict], None]

MAX_OUTAGE_WAIT = 10.0  # seconds between database checks during an outage


class Outcome(Enum):
    ACK = "ack"
    REQUEUE = "requeue"  # the handler failed: try again (counts as an attempt)
    RETRY = "retry"  # the database is down: wait for it, then try again (not counted)
    REJECT = "reject"  # can never succeed (not JSON): straight to the DLQ


class Consumer:
    def __init__(
        self,
        *,
        routing_keys: Iterable[str],
        handlers: dict[str, Handler],
        session_factory: Callable[[], Session],
        queue: str | None = None,
        dedupe: Callable[[Session, uuid.UUID], bool] | None = None,
        max_attempts: int = 5,
        queue_delivery_limit: int = 20,
        dlq_message_ttl_ms: int | None = None,
        prefetch: int = 10,
        broker_url: str | None = None,
    ):
        self.routing_keys = list(routing_keys)
        self.handlers = handlers
        self.session_factory = session_factory
        self.queue = queue or f"{get_config().service_name}.events"
        self.dedupe = dedupe
        self.max_attempts = max_attempts
        # The queue's own x-delivery-limit only catches consumers that die mid-message
        # (RabbitMQ 4 counts those returns, not nacks). It is a backstop, kept well above
        # max_attempts so reconnects during an outage don't reach it. Changing it later
        # means deleting the queue (a declare with other arguments is refused).
        self.queue_delivery_limit = queue_delivery_limit
        self.dlq_message_ttl_ms = dlq_message_ttl_ms
        self.prefetch = prefetch
        self.broker_url = broker_url
        # Handler failures per message, counted here: a restart forgets them, which only
        # means a few extra attempts.
        self._failures: dict[str, int] = {}

    # --- Broker topology ---------------------------------------------------------------

    def declare(self, channel) -> None:
        declare_exchanges(channel)
        dlq = f"{self.queue}.dlq"
        dlq_args = {"x-queue-type": "quorum"}
        if self.dlq_message_ttl_ms:
            dlq_args["x-message-ttl"] = self.dlq_message_ttl_ms
        channel.queue_declare(dlq, durable=True, arguments=dlq_args)
        channel.queue_bind(dlq, DLX, routing_key=self.queue)
        channel.queue_declare(
            self.queue,
            durable=True,
            arguments={
                "x-queue-type": "quorum",
                "x-dead-letter-exchange": DLX,
                "x-dead-letter-routing-key": self.queue,
                "x-delivery-limit": self.queue_delivery_limit,
            },
        )
        for key in self.routing_keys:
            channel.queue_bind(self.queue, EXCHANGE, routing_key=key)

    # --- One message (no broker needed, so tests can call it directly) -------------------

    def database_available(self) -> bool:
        try:
            with self.session_factory() as session:
                session.execute(text("SELECT 1"))
            return True
        except Exception:  # noqa: BLE001 - any failure means "not now"
            return False

    def handle(self, body: bytes) -> Outcome:
        try:
            envelope = json.loads(body)
            event_type = envelope["type"]
            event_id = uuid.UUID(envelope["event_id"])
        except (ValueError, KeyError, TypeError):
            log.error("rejecting a malformed message on %s", self.queue)
            return Outcome.REJECT
        handler = self.handlers.get(event_type)
        if handler is None:
            log.info("no handler for %s; skipped", event_type)
            return Outcome.ACK
        token = correlation_id.set(envelope.get("correlation_id"))
        try:
            with self.session_factory() as session, session.begin():
                if self.dedupe is not None and self.dedupe(session, event_id):
                    log.info("%s %s already processed; skipped", event_type, event_id)
                else:
                    handler(session, envelope)
            return Outcome.ACK
        except Exception:
            if not self.database_available():
                log.warning("database unavailable while handling %s %s", event_type, event_id)
                return Outcome.RETRY
            log.exception("handler for %s %s failed", event_type, event_id)
            return Outcome.REQUEUE
        finally:
            correlation_id.reset(token)

    # --- The loop ------------------------------------------------------------------------

    def run(self, stop: threading.Event) -> None:
        """Consume until `stop` is set, reconnecting with backoff."""
        backoff = 1.0
        while not stop.is_set():
            connection = None
            try:
                connection = connect("consumer", self.broker_url)
                channel = connection.channel()
                self.declare(channel)
                channel.basic_qos(prefetch_count=self.prefetch)
                channel.basic_consume(
                    self.queue,
                    lambda ch, method, props, body: self._on_message(ch, method, props, body, stop),
                )
                log.info("consuming %s", self.queue)
                backoff = 1.0
                while not stop.is_set():
                    connection.process_data_events(time_limit=0.5)
            except Exception as error:  # noqa: BLE001 - keep the consumer alive
                log.warning(
                    "consumer %s failed (%s); retrying in %.0fs", self.queue, error, backoff
                )
                stop.wait(backoff)
                backoff = min(backoff * 2, 30.0)
            finally:
                close_quietly(connection)

    @staticmethod
    def _pause(channel, seconds: float, stop: threading.Event) -> None:
        """Wait while keeping the connection's heartbeats going. Inside a callback pika
        does I/O here but does not dispatch further messages."""
        deadline = time.monotonic() + seconds
        while not stop.is_set() and (remaining := deadline - time.monotonic()) > 0:
            channel.connection.sleep(min(remaining, 0.5))

    def _on_message(self, channel, method, properties, body, stop) -> None:
        key = properties.message_id or hashlib.sha256(body).hexdigest()
        outcome = self.handle(body)
        if outcome is Outcome.ACK:
            self._failures.pop(key, None)
            channel.basic_ack(method.delivery_tag)
        elif outcome is Outcome.REJECT:
            self._failures.pop(key, None)
            channel.basic_nack(method.delivery_tag, requeue=False)
        elif outcome is Outcome.RETRY:
            # Hold the message (prefetch stops new ones being handled meanwhile) until the
            # database is back, then put it back without counting an attempt.
            wait = 0.5
            while not stop.is_set() and not self.database_available():
                self._pause(channel, wait, stop)
                wait = min(wait * 2, MAX_OUTAGE_WAIT)
            if not stop.is_set():
                log.info("database is back; retrying the held message")
            channel.basic_nack(method.delivery_tag, requeue=True)
        else:
            # RabbitMQ 4 does not count a nack-requeue towards x-delivery-limit, so the
            # attempts are counted here.
            attempt = self._failures.get(key, 0) + 1
            if attempt >= self.max_attempts:
                log.error("giving up after %d attempts; moving to %s.dlq", attempt, self.queue)
                self._failures.pop(key, None)
                channel.basic_nack(method.delivery_tag, requeue=False)
                return
            if len(self._failures) > 10_000:  # entries for messages another process took
                self._failures.clear()
            self._failures[key] = attempt
            # A short, growing pause so a failing handler doesn't spin through its
            # attempts in milliseconds (0.5 s, 1 s, 2 s, 4 s, then the DLQ).
            self._pause(channel, min(0.5 * 2 ** (attempt - 1), 5.0), stop)
            channel.basic_nack(method.delivery_tag, requeue=True)
