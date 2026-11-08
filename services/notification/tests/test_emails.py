"""Each Identity event becomes the email the monolith sent for it (detailed-plan 2.4), sent
once per event (the processed_events inbox), retried when sending fails, and held (not
dead-lettered) while the mail server is down."""

import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app import consumer as app_consumer
from app import handlers, mailer
from app.consumer import DLQ_MESSAGE_TTL_MS, ROUTING_KEYS, consumer
from app.models import ProcessedEvent
from app.platform.consumer import Outcome
from app.platform.testing import make_envelope

EXAMPLES = Path(__file__).resolve().parents[3] / "contracts" / "events" / "examples"
LINK = "http://localhost:5173/reset-password?token=Zx8kP2qR7vN4mT1sY6wB3cH9"
ADMIN_LINK = "http://localhost:5174/reset-password?token=Ab1"
INVITE_LINK = "http://localhost:5174/set-password?token=Qw3eR5tY7uI9oP1aS2dF4gH6"


def _event(type_: str, data: dict, event_id: uuid.UUID | None = None) -> dict:
    subject = data.get("user_id") or data.get("admin_id")
    return make_envelope(
        type_, data, subject, 1, aggregate_type="user", producer="identity", event_id=event_id
    )


def reset(**changes) -> dict:
    data = {
        "user_id": str(uuid.uuid4()),
        "email": "newcomer@sgjio.example.com",
        "name": "Wei Ling",
        "audience": "app",
        "method": "password",
        "link": LINK,
        "expires_in_minutes": 15,
        **changes,
    }
    return _event("identity.password_reset.requested", data)


def google_reset() -> dict:
    return _event(
        "identity.password_reset.requested",
        {
            "user_id": str(uuid.uuid4()),
            "email": "mei@gmail.com",
            "name": "Mei",
            "audience": "app",
            "method": "google",
            "sign_in_url": "http://localhost:5173/sign-in",
        },
    )


def invitation(trigger: str = "invited", inviter: str | None = "Yash") -> dict:
    return _event(
        "identity.admin.invitation_issued",
        {
            "admin_id": str(uuid.uuid4()),
            "email": "arjun@sgjio.example.com",
            "name": "Arjun",
            "inviter_name": inviter,
            "link": INVITE_LINK,
            "expires_in_hours": 72,
            "trigger": trigger,
        },
    )


def removal() -> dict:
    return _event(
        "identity.admin.removed",
        {
            "admin_id": str(uuid.uuid4()),
            "email": "mei@sgjio.example.com",
            "name": "Mei",
            "remover_name": "Yash",
        },
    )


def _handle(envelope: dict) -> Outcome:
    return consumer.handle(json.dumps(envelope).encode())


def _sent_one(envelope: dict) -> mailer.EmailMessage:
    assert _handle(envelope) is Outcome.ACK
    assert len(mailer.outbox) == 1
    return mailer.outbox[0]


def _processed(db) -> list[tuple[uuid.UUID, str]]:
    return list(db.execute(select(ProcessedEvent.event_id, ProcessedEvent.type)).all())


# --- identity.password_reset.requested ------------------------------------------------------


def test_a_reset_link_for_the_main_app(db):
    event = reset()
    email = _sent_one(event)
    assert email.to == "newcomer@sgjio.example.com"
    assert email.subject == "Reset your SGJio password"
    assert "Hi Wei Ling," in email.text
    assert LINK in email.text
    assert f'href="{LINK}"' in email.html
    # SCRUM-63 AC3: the email says how long the link lasts (15 minutes).
    assert "valid for 15 minutes" in email.text
    assert "15 minutes" in email.html
    assert "the SGJio admin portal" not in email.text
    assert _processed(db) == [(uuid.UUID(event["event_id"]), event["type"])]


def test_a_reset_link_for_the_admin_portal():
    email = _sent_one(reset(audience="admin", link=ADMIN_LINK))
    assert email.subject == "Reset your SGJio admin password"
    assert "your password for the SGJio admin portal" in email.text
    assert ADMIN_LINK in email.text


def test_the_duration_is_the_one_in_the_event():
    assert "valid for 5 minutes" in _sent_one(reset(expires_in_minutes=5)).text


def test_a_google_only_account_is_told_how_it_signs_in():
    email = _sent_one(google_reset())
    assert email.to == "mei@gmail.com"
    assert email.subject == "How you sign in to SGJio"
    assert "Continue with Google" in email.text
    assert "http://localhost:5173/sign-in" in email.text
    assert "mei@gmail.com" in email.text


# --- identity.admin.invitation_issued -------------------------------------------------------


def test_an_invite():
    email = _sent_one(invitation("invited"))
    assert email.to == "arjun@sgjio.example.com"
    assert email.subject == "Yash invited you to the SGJio admin portal"
    assert "valid for 3 days" in email.text
    assert INVITE_LINK in email.text
    assert "You will sign in with this email address: arjun@sgjio.example.com" in email.text


def test_a_resent_invite_reads_like_the_first():
    assert _sent_one(invitation("resent")).subject == "Yash invited you to the SGJio admin portal"


def test_an_invited_administrator_who_asked_for_a_new_link():
    email = _sent_one(invitation("forgot_password", inviter=None))
    assert email.subject == "Set up your SGJio admin account"
    assert "Here is a new link to set up your SGJio admin account." in email.text
    assert "valid for 3 days" in email.text


def test_access_given_back():
    email = _sent_one(invitation("restored"))
    assert email.subject == "Your SGJio admin access is back"
    assert "Yash has given you access to the SGJio admin portal again." in email.text


# --- identity.admin.removed -----------------------------------------------------------------


def test_a_removed_administrator_is_told_who_removed_them():
    email = _sent_one(removal())
    assert email.to == "mei@sgjio.example.com"
    assert email.subject == "Your SGJio admin access has been removed"
    assert "Yash has removed your access" in email.text
    assert "contact Yash or another administrator" in email.text


# --- The contract's own examples ------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "identity.password_reset.requested",
        "identity.admin.invitation_issued",
        "identity.admin.removed",
    ],
)
def test_each_contract_example_sends_one_email(name, db):
    path = EXAMPLES / f"{name}.json"
    if not path.is_file():
        pytest.skip(f"no contract example at {path}")
    example = json.loads(path.read_text())
    email = _sent_one(example)
    assert email.to == example["data"]["email"]
    assert _processed(db) == [(uuid.UUID(example["event_id"]), name)]


# --- Once per event -------------------------------------------------------------------------


def test_an_event_delivered_twice_sends_one_email(db):
    event = reset()
    assert _handle(event) is Outcome.ACK
    assert _handle(event) is Outcome.ACK
    assert len(mailer.outbox) == 1
    assert len(_processed(db)) == 1


def test_two_events_with_the_same_content_are_two_emails(db):
    """A second request is a second email: only the event id dedupes."""
    first, second = reset(), reset()
    second["data"] = first["data"]
    _handle(first)
    _handle(second)
    assert len(mailer.outbox) == 2
    assert len(_processed(db)) == 2


def test_an_event_already_in_the_inbox_is_skipped(db):
    event = removal()
    db.add(ProcessedEvent(event_id=uuid.UUID(event["event_id"]), type=event["type"]))
    db.commit()
    assert _handle(event) is Outcome.ACK
    assert mailer.outbox == []


# --- Failures -------------------------------------------------------------------------------


def test_a_send_failure_while_the_mail_server_answers_is_counted_and_records_nothing(
    db, monkeypatch
):
    event = invitation()
    calls = []

    def down(message):
        calls.append(message)
        raise ConnectionRefusedError("SMTP is down")

    monkeypatch.setattr(handlers, "send_email", down)
    assert _handle(event) is Outcome.REQUEUE
    assert _processed(db) == []

    monkeypatch.undo()
    assert _handle(event) is Outcome.ACK
    assert len(mailer.outbox) == 1
    assert len(calls) == 1


def _smtp_backend(monkeypatch, probe_answers: bool) -> list[str]:
    """Switch to the smtp backend with a fake server: sending is refused, and NOOP answers
    or not as asked. Returns the probes made."""
    from app.config import get_settings

    probes = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            probes.append(f"{host}:{port}")
            if not probe_answers:
                raise ConnectionRefusedError("connection refused")

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def noop(self):
            return (250, b"OK")

    monkeypatch.setattr(get_settings(), "email_backend", "smtp")
    monkeypatch.setattr(app_consumer.smtplib, "SMTP", FakeSMTP)
    return probes


def test_a_mail_server_outage_waits_instead_of_using_up_attempts(db, monkeypatch):
    """Mailpit or the provider down is an outage: RETRY holds the message until it answers,
    so nothing is dead-lettered and the email arrives when it recovers."""
    probes = _smtp_backend(monkeypatch, probe_answers=False)

    def refused(message):
        raise ConnectionRefusedError("SMTP is down")

    monkeypatch.setattr(handlers, "send_email", refused)
    assert _handle(invitation()) is Outcome.RETRY
    assert probes
    assert _processed(db) == []


def test_a_bad_event_with_the_mail_server_up_is_still_counted(db, monkeypatch):
    probes = _smtp_backend(monkeypatch, probe_answers=True)
    broken = invitation()
    del broken["data"]["link"]
    assert _handle(broken) is Outcome.REQUEUE
    assert probes
    assert _processed(db) == []


def test_the_mail_server_probe_is_skipped_for_the_memory_backend(monkeypatch):
    def never(*_args, **_kwargs):
        raise AssertionError("no SMTP connection expected")

    monkeypatch.setattr(app_consumer.smtplib, "SMTP", never)
    assert app_consumer.smtp_available() is True


def test_an_event_with_a_missing_field_is_retried_not_half_sent(db):
    broken = reset()
    del broken["data"]["link"]
    assert _handle(broken) is Outcome.REQUEUE
    assert mailer.outbox == []
    assert _processed(db) == []


def test_fields_it_does_not_know_are_ignored():
    event = reset(new_field="from a later version")
    assert _sent_one(event).subject == "Reset your SGJio password"


def test_events_with_no_email_are_acknowledged_and_skipped(db):
    registered = make_envelope(
        "identity.user.registered",
        {"user_id": str(uuid.uuid4()), "role": "user", "user_type": "newcomer"},
        aggregate_type="user",
    )
    assert _handle(registered) is Outcome.ACK
    assert mailer.outbox == []
    assert db.scalar(select(func.count()).select_from(ProcessedEvent)) == 0


def test_a_message_that_is_not_an_event_goes_to_the_dead_letter_queue():
    assert consumer.handle(b"not json") is Outcome.REJECT
    assert consumer.handle(b'{"type": "identity.admin.removed"}') is Outcome.REJECT
    assert mailer.outbox == []


# --- Topology -------------------------------------------------------------------------------


class _RecordingChannel:
    def __init__(self):
        self.queues: dict[str, dict] = {}
        self.bindings: list[tuple[str, str, str]] = []

    def exchange_declare(self, *args, **kwargs):
        pass

    def queue_declare(self, name, durable, arguments):
        self.queues[name] = arguments

    def queue_bind(self, queue, exchange, routing_key):
        self.bindings.append((queue, exchange, routing_key))


def test_the_queue_its_bindings_and_its_dead_letter_queue():
    channel = _RecordingChannel()
    consumer.declare(channel)

    assert consumer.queue == "notification.events"
    assert ROUTING_KEYS == ["identity.password_reset.requested", "identity.admin.*"]
    assert ("notification.events", "sgjio.events", "identity.password_reset.requested") in (
        channel.bindings
    )
    assert ("notification.events", "sgjio.events", "identity.admin.*") in channel.bindings
    assert ("notification.events.dlq", "sgjio.dlx", "notification.events") in channel.bindings
    assert channel.queues["notification.events"]["x-dead-letter-exchange"] == "sgjio.dlx"
    assert channel.queues["notification.events.dlq"]["x-message-ttl"] == DLQ_MESSAGE_TTL_MS
    assert DLQ_MESSAGE_TTL_MS == 3_600_000


# --- Inbox pruning --------------------------------------------------------------------------


def _record(db, days_ago: int) -> uuid.UUID:
    from datetime import UTC, datetime, timedelta

    event_id = uuid.uuid4()
    db.add(
        ProcessedEvent(
            event_id=event_id,
            type=handlers.ADMIN_REMOVED,
            processed_at=datetime.now(UTC) - timedelta(days=days_ago),
        )
    )
    db.commit()
    return event_id


def test_prune_inbox_deletes_only_rows_older_than_30_days(db):
    old = _record(db, 31)
    recent = _record(db, 29)
    assert handlers.prune_inbox(db) == 1
    db.commit()
    assert [row[0] for row in _processed(db)] == [recent]
    assert old not in [row[0] for row in _processed(db)]


def test_the_workers_pruner_prunes_and_survives_a_failure(db):
    import threading

    from app.db import SessionLocal

    _record(db, 40)
    stop = threading.Event()
    passes = []

    def factory():
        passes.append(1)
        if len(passes) == 1:
            raise ConnectionError("database down")  # logged; tried again next time
        if len(passes) == 2:
            stop.set()  # stop after this (real) pass
        return SessionLocal()

    handlers.run_inbox_pruner(factory, stop, every=0)
    assert len(passes) == 2
    db.expire_all()
    assert _processed(db) == []


def test_prune_inbox_command(db, capsys):
    from app import cli

    _record(db, 10)
    _record(db, 2)
    assert cli.main(["prune-inbox", "--days", "7"]) == 0
    assert "pruned 1 processed_events rows older than 7 days" in capsys.readouterr().out
    db.expire_all()
    assert len(_processed(db)) == 1
