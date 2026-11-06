"""Which email each Identity event sends (detailed-plan 2.4). Identity decides what
happened; Notification decides how to tell the person.

    identity.password_reset.requested  method=password  password_reset_email
                                       method=google    google_account_email
    identity.admin.invitation_issued   any trigger      admin_invite_email
    identity.admin.removed                              admin_removed_email

Each event carries every argument its template takes (contracts/README.md, "Emails").
Handlers read only the fields they need and ignore any others, so a field added to an
event later breaks nothing.

Delivery is at least once (contracts/README.md, "Inbox"): the consumer skips an event
whose id is already in processed_events; otherwise the handler sends the email, then
records the id, and the consumer commits. A crash between the two sends a duplicate; it
never loses an email. A send that fails raises, so nothing is recorded. If the mail server
is down, the consumer waits for it and retries without counting (app/consumer.py); any
other failure is retried and, on its 5th, dead-lettered (notification.events.dlq keeps it
for an hour).

Inbox rows are kept for INBOX_RETENTION (30 days), far beyond any redelivery, then
`prune_inbox` deletes them: the worker runs it about hourly, and `python -m app.cli
prune-inbox` runs it by hand.
"""

import logging
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.mailer import EmailMessage, send_email
from app.mailer.templates import (
    admin_invite_email,
    admin_removed_email,
    google_account_email,
    password_reset_email,
)
from app.models import ProcessedEvent

PASSWORD_RESET_REQUESTED = "identity.password_reset.requested"
ADMIN_INVITATION_ISSUED = "identity.admin.invitation_issued"
ADMIN_REMOVED = "identity.admin.removed"

INBOX_RETENTION = timedelta(days=30)
PRUNE_EVERY_SECONDS = 3600.0

log = logging.getLogger("sgjio.notification")


def password_reset_message(data: dict) -> EmailMessage:
    if data["method"] == "google":
        return google_account_email(to=data["email"], name=data["name"], link=data["sign_in_url"])
    return password_reset_email(
        to=data["email"],
        name=data["name"],
        link=data["link"],
        minutes=data["expires_in_minutes"],
        for_admin=data["audience"] == "admin",
    )


def invitation_message(data: dict) -> EmailMessage:
    return admin_invite_email(
        to=data["email"],
        name=data["name"],
        inviter=data.get("inviter_name"),
        link=data["link"],
        hours=data["expires_in_hours"],
        restored=data["trigger"] == "restored",
    )


def removed_message(data: dict) -> EmailMessage:
    return admin_removed_email(to=data["email"], name=data["name"], remover=data["remover_name"])


MESSAGES: dict[str, Callable[[dict], EmailMessage]] = {
    PASSWORD_RESET_REQUESTED: password_reset_message,
    ADMIN_INVITATION_ISSUED: invitation_message,
    ADMIN_REMOVED: removed_message,
}


def already_processed(session: Session, event_id: uuid.UUID) -> bool:
    """The consumer's dedupe hook: True skips the event."""
    return session.get(ProcessedEvent, event_id) is not None


def send_and_record(session: Session, envelope: dict) -> None:
    """Send the event's email, then record the event as handled (the consumer commits)."""
    send_email(MESSAGES[envelope["type"]](envelope["data"]))
    session.add(ProcessedEvent(event_id=uuid.UUID(envelope["event_id"]), type=envelope["type"]))


def prune_inbox(session: Session, older_than: timedelta = INBOX_RETENTION) -> int:
    """Delete inbox rows recorded more than `older_than` ago; returns how many. The caller
    commits."""
    cutoff = datetime.now(UTC) - older_than
    return session.execute(
        delete(ProcessedEvent).where(ProcessedEvent.processed_at < cutoff)
    ).rowcount


def run_inbox_pruner(
    session_factory: Callable[[], Session],
    stop: threading.Event,
    *,
    every: float = PRUNE_EVERY_SECONDS,
    older_than: timedelta = INBOX_RETENTION,
) -> None:
    """Prune the inbox now and then every `every` seconds until `stop` is set. Pruning is
    housekeeping: a failure is logged and tried again next time."""
    while not stop.is_set():
        try:
            with session_factory() as session, session.begin():
                deleted = prune_inbox(session, older_than)
            if deleted:
                log.info("pruned %d processed_events rows", deleted)
        except Exception as error:  # noqa: BLE001 - try again next time
            log.warning("inbox prune failed (%s)", error)
        stop.wait(every)
