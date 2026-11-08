"""Getting the email out: the SMTP backend, the consumer loop against the real broker and
Mailpit (including a mail server outage), the worker's wiring, and `python -m app.cli health`."""

import json
import threading
import time
import urllib.parse
import urllib.request
import uuid

import pika
import pytest

from app import cli, mailer
from app.config import get_settings
from app.consumer import build_consumer
from app.db import SessionLocal
from app.models import ProcessedEvent
from app.platform.broker import close_quietly, connect
from tests.test_emails import reset

MAILPIT = "http://localhost:8025"


def _broker_or_skip():
    try:
        close_quietly(connect("test"))
    except Exception as error:  # noqa: BLE001
        pytest.skip(f"RabbitMQ is not running ({error})")


def test_the_smtp_backend_sends_text_and_html_from_the_configured_sender(monkeypatch):
    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self):
            sent.append(("starttls",))

        def login(self, user, password):
            sent.append(("login", user))

        def send_message(self, mime):
            sent.append(("message", mime))

    settings = get_settings()
    monkeypatch.setattr(settings, "email_backend", "smtp")
    monkeypatch.setattr(settings, "smtp_host", "mail.example.com")
    monkeypatch.setattr(settings, "smtp_port", 2525)
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)

    mailer.send_email(
        mailer.EmailMessage(to="a@example.com", subject="Hi", text="T", html="<p>H</p>")
    )

    assert sent[0] == ("connect", "mail.example.com", 2525)
    mime = sent[-1][1]
    assert mime["From"] == "SGJio <no-reply@sgjio.example.com>"
    assert mime["To"] == "a@example.com"
    assert mime["Subject"] == "Hi"
    assert [part.get_content_type() for part in mime.iter_parts()] == ["text/plain", "text/html"]
    assert mailer.outbox == []


@pytest.mark.integration
def test_an_event_on_the_broker_arrives_in_mailpit(monkeypatch):
    """The whole path on the compose broker and Mailpit, on a queue of the test's own (so
    the running service's notification.events is never touched)."""
    _broker_or_skip()
    try:
        urllib.request.urlopen(f"{MAILPIT}/api/v1/info", timeout=3)
    except OSError as error:
        pytest.skip(f"Mailpit is not running ({error})")
    settings = get_settings()
    monkeypatch.setattr(settings, "email_backend", "smtp")
    monkeypatch.setattr(settings, "smtp_host", "localhost")
    monkeypatch.setattr(settings, "smtp_port", 1025)

    queue = f"notification-test-{uuid.uuid4().hex[:8]}"
    consumer = build_consumer(queue=queue)
    recipient = f"test-{uuid.uuid4().hex[:8]}@sgjio.example.com"
    event = reset(email=recipient)
    stop = threading.Event()
    thread = threading.Thread(target=consumer.run, args=(stop,), daemon=True)
    connection = connect("test")
    try:
        channel = connection.channel()
        consumer.declare(channel)  # before publishing, so the message has somewhere to go
        thread.start()
        channel.basic_publish(
            exchange="",
            routing_key=queue,
            body=json.dumps(event).encode(),
            properties=pika.BasicProperties(
                message_id=event["event_id"], type=event["type"], content_type="application/json"
            ),
        )
        query = urllib.parse.urlencode({"query": f"to:{recipient}"})
        messages = []
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and not messages:
            with urllib.request.urlopen(f"{MAILPIT}/api/v1/search?{query}", timeout=3) as answer:
                messages = json.loads(answer.read())["messages"]
            time.sleep(0.2)
        assert len(messages) == 1
        assert messages[0]["Subject"] == "Reset your SGJio password"
        with SessionLocal() as session:
            deadline = time.monotonic() + 5
            while session.get(ProcessedEvent, uuid.UUID(event["event_id"])) is None:
                assert time.monotonic() < deadline
                time.sleep(0.1)
                session.expire_all()
    finally:
        stop.set()
        thread.join(timeout=10)
        channel = connection.channel()
        channel.queue_delete(queue)
        channel.queue_delete(f"{queue}.dlq")
        close_quietly(connection)


@pytest.mark.integration
def test_a_mail_server_outage_holds_the_email_until_it_recovers(monkeypatch):
    """SMTP refused (nothing listens on port 1): the message is held, not dead-lettered,
    however long the outage, then sent once the mail server answers. max_attempts is cut to
    2 so a counted failure would have reached the DLQ within a second."""
    _broker_or_skip()
    try:
        urllib.request.urlopen(f"{MAILPIT}/api/v1/info", timeout=3)
    except OSError as error:
        pytest.skip(f"Mailpit is not running ({error})")
    settings = get_settings()
    monkeypatch.setattr(settings, "email_backend", "smtp")
    monkeypatch.setattr(settings, "smtp_host", "localhost")
    monkeypatch.setattr(settings, "smtp_port", 1)

    queue = f"notification-test-{uuid.uuid4().hex[:8]}"
    consumer = build_consumer(queue=queue)
    consumer.max_attempts = 2
    recipient = f"outage-{uuid.uuid4().hex[:8]}@sgjio.example.com"
    event = reset(email=recipient)
    stop = threading.Event()
    thread = threading.Thread(target=consumer.run, args=(stop,), daemon=True)
    connection = connect("test")
    try:
        channel = connection.channel()
        consumer.declare(channel)
        thread.start()
        channel.basic_publish(
            exchange="",
            routing_key=queue,
            body=json.dumps(event).encode(),
            properties=pika.BasicProperties(
                message_id=event["event_id"], type=event["type"], content_type="application/json"
            ),
        )
        time.sleep(3)
        dlq = channel.queue_declare(f"{queue}.dlq", passive=True).method.message_count
        assert dlq == 0
        with SessionLocal() as session:
            assert session.get(ProcessedEvent, uuid.UUID(event["event_id"])) is None

        monkeypatch.setattr(settings, "smtp_port", 1025)  # the mail server is back
        query = urllib.parse.urlencode({"query": f"to:{recipient}"})
        messages = []
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and not messages:
            with urllib.request.urlopen(f"{MAILPIT}/api/v1/search?{query}", timeout=3) as answer:
                messages = json.loads(answer.read())["messages"]
            time.sleep(0.2)
        assert len(messages) == 1
        assert channel.queue_declare(f"{queue}.dlq", passive=True).method.message_count == 0
    finally:
        stop.set()
        thread.join(timeout=15)
        channel = connection.channel()
        channel.queue_delete(queue)
        channel.queue_delete(f"{queue}.dlq")
        close_quietly(connection)


@pytest.mark.integration
def test_health_checks_the_database_and_the_broker(capsys):
    _broker_or_skip()
    assert cli.main(["health"]) == 0
    assert capsys.readouterr().out.strip() == "ok"


def test_health_fails_without_a_broker(monkeypatch):
    def refuse(*_args, **_kwargs):
        raise ConnectionError("refused")

    monkeypatch.setattr(cli, "connect", refuse)
    assert cli.main(["health"]) == 1


def test_the_worker_runs_the_consumer_until_stopped(monkeypatch):
    from app import worker

    seen = {}

    def run(session_factory, *, consumers):
        seen["consumers"] = consumers

    monkeypatch.setattr(worker, "run_until_signalled", run)
    worker.main()
    assert [c.queue for c in seen["consumers"]] == ["notification.events"]
