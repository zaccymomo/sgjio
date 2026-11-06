"""Notification's consumer: queue notification.events, bound to the Identity events that
send email (contracts/README.md, "Broker topology"), with the processed_events inbox as
its dedupe hook and a one-hour TTL on its dead-letter queue, so expired one-time links and
addresses don't sit in the broker.

A mail server that does not answer is an outage, like a database that does not answer:
the platform consumer then holds the message and waits for both to be back, without
counting an attempt, so nothing is dead-lettered because Mailpit or the SMTP provider was
down (the build plan's "the email arrives when it recovers"). A send that fails while the
mail server does answer is the message's fault and is counted (5 attempts, then the DLQ).
"""

import logging
import smtplib

from app.config import get_settings
from app.db import SessionLocal
from app.handlers import MESSAGES, already_processed, send_and_record
from app.platform.consumer import Consumer

log = logging.getLogger("sgjio.notification")

ROUTING_KEYS = ["identity.password_reset.requested", "identity.admin.*"]
DLQ_MESSAGE_TTL_MS = 3_600_000
SMTP_PROBE_TIMEOUT = 5.0


def smtp_available() -> bool:
    """True when email can go out: always for the memory and console backends; for smtp,
    when the server accepts a connection and answers NOOP."""
    settings = get_settings()
    if settings.email_backend != "smtp":
        return True
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=SMTP_PROBE_TIMEOUT) as s:
            s.noop()
        return True
    except (OSError, smtplib.SMTPException) as error:
        log.warning(
            "mail server %s:%s unavailable (%s)", settings.smtp_host, settings.smtp_port, error
        )
        return False


class NotificationConsumer(Consumer):
    """The platform consumer, with the mail server counted as a dependency next to the
    database: while either is down, a failed message waits instead of using up attempts."""

    def database_available(self) -> bool:
        return super().database_available() and smtp_available()


def build_consumer(session_factory=SessionLocal, queue: str | None = None) -> Consumer:
    """`queue` defaults to "<SERVICE_NAME>.events", i.e. notification.events."""
    return NotificationConsumer(
        queue=queue,
        routing_keys=ROUTING_KEYS,
        handlers={event_type: send_and_record for event_type in MESSAGES},
        session_factory=session_factory,
        dedupe=already_processed,
        dlq_message_ttl_ms=DLQ_MESSAGE_TTL_MS,
    )


consumer = build_consumer()
