"""Generation's consumer: queue generation.events, bound to the two request types, with the
processed_events inbox as its dedupe hook (contracts/README.md, "Broker topology").

A request can take a minute or more (two model calls, maybe a retry). The platform
consumer runs handlers on the connection's own thread, so a long handler would stop pika
answering heartbeats and RabbitMQ would drop the connection (heartbeat 30 s). This
subclass runs each handler in a helper thread and keeps the connection serviced
(`connection.sleep`, which does I/O without dispatching new messages) until it is done.
`prefetch=1`: requests are taken one at a time.
"""

import threading

from app.db import SessionLocal
from app.handlers import REQUEST_TYPES, already_processed, make_handler
from app.platform.consumer import Consumer, Outcome

ROUTING_KEYS = list(REQUEST_TYPES)


class GenerationConsumer(Consumer):
    _channel = None

    def _on_message(self, channel, method, properties, body, stop) -> None:
        self._channel = channel
        try:
            super()._on_message(channel, method, properties, body, stop)
        finally:
            self._channel = None

    def handle(self, body: bytes) -> Outcome:
        channel = self._channel
        if channel is None:  # called directly (tests): no connection to keep alive
            return super().handle(body)
        outcome: list[Outcome] = []
        worker = threading.Thread(
            target=lambda: outcome.append(Consumer.handle(self, body)), daemon=True
        )
        worker.start()
        while worker.is_alive():
            channel.connection.sleep(0.5)
        return outcome[0] if outcome else Outcome.REQUEUE


def build_consumer(session_factory=SessionLocal, queue: str | None = None, llm_factory=None):
    """`queue` defaults to "<SERVICE_NAME>.events", i.e. generation.events."""
    handler = make_handler(session_factory, llm_factory)
    return GenerationConsumer(
        queue=queue,
        routing_keys=ROUTING_KEYS,
        handlers={event_type: handler for event_type in REQUEST_TYPES},
        session_factory=session_factory,
        dedupe=already_processed,
        prefetch=1,
    )


consumer = build_consumer()
