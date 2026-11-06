"""RabbitMQ names and connections (pika, blocking: one connection per thread)."""

import contextlib

import pika

from .config import get_config

EXCHANGE = "sgjio.events"  # topic exchange; routing key = event type
DLX = "sgjio.dlx"  # direct exchange; routing key = the queue a message died in


def connect(purpose: str, broker_url: str | None = None) -> pika.BlockingConnection:
    """A new connection, named in the management UI as e.g. "content-relay"."""
    params = pika.URLParameters(broker_url or get_config().broker_url)
    params.client_properties = {"connection_name": f"{get_config().service_name}-{purpose}"}
    params.heartbeat = 30
    params.blocked_connection_timeout = 30
    params.socket_timeout = 5
    params.connection_attempts = 1
    return pika.BlockingConnection(params)


def declare_exchanges(channel) -> None:
    """Idempotent; infra/rabbitmq/definitions.json creates the same exchanges."""
    channel.exchange_declare(EXCHANGE, exchange_type="topic", durable=True)
    channel.exchange_declare(DLX, exchange_type="direct", durable=True)


def close_quietly(connection: pika.BlockingConnection | None) -> None:
    if connection is not None and connection.is_open:
        with contextlib.suppress(Exception):
            connection.close()
