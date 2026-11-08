"""Every identity.* event, as written to the outbox: when it is written, what it carries, and
that it matches contracts/events (also checked for every test by conftest's
`contract_check`). Events are written in the same transaction as the change, so a change
that is refused writes none."""

import contextlib
import json
import uuid
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import events
from app.auth.reset import check_reset_token
from app.main import app
from app.models import AuthScope, PasswordResetToken, User, UserRole
from app.platform.outbox import publish_pending
from app.privacy import NOTICE_VERSION
from tests import contracts
from tests.helpers import emails, outbox_events

NEW = {
    "name": "Ana Rivera",
    "email": "ana@example.com",
    "password": "Password123",
    "password_confirmation": "Password123",
    "user_type": "newcomer",
    "privacy_consent": True,
    "privacy_notice_version": NOTICE_VERSION,
}
ADMIN = {"email": "yash@sgjio.example.com", "password": "AdminPass123"}


@pytest.fixture(autouse=True)
def _contracts_present():
    if not contracts.available():
        pytest.skip(f"no contracts at {contracts.events_dir()}")


@pytest.fixture
def admin(client, make_user):
    make_user(ADMIN["email"], ADMIN["password"], role=UserRole.ADMIN, name="Yash")
    assert client.post("/api/admin/auth/sign-in", json=ADMIN).status_code == 200
    return client


def _only(type_: str) -> dict:
    found = outbox_events(type_)
    assert len(found) == 1, [event["type"] for event in outbox_events()]
    contracts.assert_valid(found[0])
    return found[0]


def _token(link: str) -> str:
    return parse_qs(urlparse(link).query)["token"][0]


# --- The envelope ---------------------------------------------------------------------------


def test_the_envelope_names_identity_and_carries_the_request_id(client):
    response = client.post("/api/auth/register", json=NEW, headers={"X-Request-ID": "req-123"})
    assert response.status_code == 201
    assert response.headers["x-request-id"] == "req-123"

    event = _only("identity.user.registered")
    assert event["producer"] == "identity"
    assert event["schema_version"] == 1
    assert event["aggregate_type"] == "user"
    assert event["correlation_id"] == "req-123"
    uuid.UUID(event["event_id"])
    assert event["occurred_at"].endswith("Z")


def test_the_contract_check_itself_catches_a_broken_event(client):
    client.post("/api/auth/register", json=NEW)
    event = _only("identity.user.registered")
    broken = json.loads(json.dumps(event))
    broken["data"]["user_type"] = None  # a learner must have one
    broken["data"]["extra"] = 1  # producers may not add fields
    broken["aggregate_version"] = 2
    assert len(contracts.errors(broken)) >= 3


# --- identity.user.registered -------------------------------------------------------------


def test_registering_writes_user_registered(client, db):
    client.post("/api/auth/register", json={**NEW, "user_type": "singaporean"})
    user = db.scalar(select(User))
    event = _only("identity.user.registered")
    assert event["aggregate_id"] == str(user.id)
    assert event["aggregate_version"] == 1
    assert event["data"] == {
        "user_id": str(user.id),
        "role": "user",
        "user_type": "singaporean",
        "registered_at": user.created_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
    }


def test_a_refused_registration_writes_nothing(client, make_user):
    make_user("ana@example.com")
    assert client.post("/api/auth/register", json=NEW).status_code == 409
    assert client.post("/api/auth/register", json={**NEW, "email": "x"}).status_code == 422
    weak = {**NEW, "email": "b@example.com", "password": "a", "password_confirmation": "a"}
    assert client.post("/api/auth/register", json=weak).status_code == 422
    assert outbox_events() == []


def test_inviting_an_administrator_registers_them_and_sends_the_invite(admin, db):
    response = admin.post(
        "/api/admin/admins", json={"name": "Arjun", "email": "arjun@sgjio.example.com"}
    )
    assert response.status_code == 201
    arjun = db.scalar(select(User).where(User.email == "arjun@sgjio.example.com"))

    registered = _only("identity.user.registered")
    assert registered["data"]["user_id"] == str(arjun.id)
    assert registered["data"]["role"] == "admin"
    assert registered["data"]["user_type"] is None

    invite = _only("identity.admin.invitation_issued")
    assert invite["aggregate_id"] == str(arjun.id)
    assert invite["data"]["admin_id"] == str(arjun.id)
    assert invite["data"]["email"] == "arjun@sgjio.example.com"
    assert invite["data"]["name"] == "Arjun"
    assert invite["data"]["inviter_name"] == "Yash"
    assert invite["data"]["trigger"] == "invited"
    assert invite["data"]["expires_in_hours"] == 72
    assert invite["data"]["link"].startswith("http://localhost:5174/set-password?token=")
    # The link in the event is the one that works.
    assert check_reset_token(db, _token(invite["data"]["link"]), AuthScope.ADMIN).id == arjun.id
    # Registered first, then the email.
    assert [e["type"] for e in outbox_events()] == [
        "identity.user.registered",
        "identity.admin.invitation_issued",
    ]


def test_a_refused_invite_writes_nothing(admin, make_user):
    make_user("learner@sgjio.example.com")
    assert (
        admin.post(
            "/api/admin/admins", json={"name": "L", "email": "learner@sgjio.example.com"}
        ).status_code
        == 409
    )
    assert (
        admin.post("/api/admin/admins", json={"name": "G", "email": "g@gmail.com"}).status_code
        == 422
    )
    assert outbox_events() == []


# --- identity.user.deleted ----------------------------------------------------------------


def test_deleting_an_account_writes_user_deleted(client, db, make_user):
    user = make_user()
    client.post("/api/auth/sign-in", json={"email": user.email, "password": "Password123"})
    assert (
        client.post("/api/auth/delete-account", json={"password": "Password123"}).status_code == 204
    )

    event = _only("identity.user.deleted")
    assert event["aggregate_id"] == str(user.id)
    assert event["aggregate_version"] == 2
    assert event["data"]["user_id"] == str(user.id)


def test_a_refused_deletion_writes_nothing(client, make_user):
    user = make_user()
    client.post("/api/auth/sign-in", json={"email": user.email, "password": "Password123"})
    assert client.post("/api/auth/delete-account", json={"password": "Wrong123"}).status_code == 401
    assert client.post("/api/auth/delete-account", json={}).status_code == 422
    assert outbox_events() == []


# --- identity.password_reset.requested ------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "role", "audience", "base"),
    [
        ("/api/auth/forgot-password", UserRole.USER, "app", "http://localhost:5173"),
        ("/api/admin/auth/forgot-password", UserRole.ADMIN, "admin", "http://localhost:5174"),
    ],
)
def test_forgot_password_writes_a_reset_link(client, db, make_user, path, role, audience, base):
    user = make_user(role=role, name="Wei Ling")
    assert client.post(path, json={"email": "USER@example.com"}).status_code == 204

    event = _only("identity.password_reset.requested")
    assert event["aggregate_id"] == str(user.id)
    assert event["aggregate_version"] == 1
    data = event["data"]
    assert data["user_id"] == str(user.id)
    assert data["email"] == "user@example.com"
    assert data["name"] == "Wei Ling"
    assert data["audience"] == audience
    assert data["method"] == "password"
    assert data["expires_in_minutes"] == 15
    assert data["link"].startswith(f"{base}/reset-password?token=")
    assert "sign_in_url" not in data
    scope = AuthScope(audience)
    assert check_reset_token(db, _token(data["link"]), scope).id == user.id
    # The link and the token are stored together, or not at all.
    assert db.scalar(select(PasswordResetToken)).scope == scope


def test_forgot_password_for_a_google_only_account_says_how_to_sign_in(client, db):
    db.add(
        User(
            name="Mei",
            email="mei@gmail.com",
            password_hash=None,
            google_sub="g-1",
            role=UserRole.USER,
            user_type="newcomer",
        )
    )
    db.commit()
    client.post("/api/auth/forgot-password", json={"email": "mei@gmail.com"})

    data = _only("identity.password_reset.requested")["data"]
    assert data["method"] == "google"
    assert data["audience"] == "app"
    assert data["sign_in_url"] == "http://localhost:5173/sign-in"
    assert "link" not in data and "expires_in_minutes" not in data


def test_no_event_for_an_unknown_email_or_a_learner_on_the_portal(client, make_user):
    make_user()
    client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})
    client.post("/api/admin/auth/forgot-password", json={"email": "user@example.com"})
    assert outbox_events() == []


# --- identity.admin.invitation_issued -------------------------------------------------------


def _invite(admin, db) -> User:
    admin.post("/api/admin/admins", json={"name": "Arjun", "email": "arjun@sgjio.example.com"})
    return db.scalar(select(User).where(User.email == "arjun@sgjio.example.com"))


def _invites() -> list[dict]:
    found = outbox_events("identity.admin.invitation_issued")
    for event in found:
        contracts.assert_valid(event)
    return [event["data"] for event in found]


def test_resending_an_invite(admin, db):
    arjun = _invite(admin, db)
    admin.post(f"/api/admin/admins/{arjun.id}/resend-invite")
    resent = _invites()[-1]
    assert resent["trigger"] == "resent"
    assert resent["inviter_name"] == "Yash"
    assert check_reset_token(db, _token(resent["link"]), AuthScope.ADMIN).id == arjun.id


def test_an_invited_administrator_asking_for_a_reset_gets_a_new_invite(admin, db):
    arjun = _invite(admin, db)
    admin.post("/api/admin/auth/forgot-password", json={"email": arjun.email})
    forgot = _invites()[-1]
    assert forgot["trigger"] == "forgot_password"
    assert forgot["inviter_name"] is None
    assert outbox_events("identity.password_reset.requested") == []


def test_restoring_an_administrator(admin, db, make_user):
    mei = make_user("mei@sgjio.example.com", role=UserRole.ADMIN, name="Mei")
    admin.post(f"/api/admin/admins/{mei.id}/remove")
    admin.post(f"/api/admin/admins/{mei.id}/restore")
    restored = _invites()[-1]
    assert restored["trigger"] == "restored"
    assert restored["inviter_name"] == "Yash"
    assert restored["admin_id"] == str(mei.id)


# --- identity.admin.removed -----------------------------------------------------------------


def test_removing_an_administrator_tells_them_who_did_it(admin, make_user):
    mei = make_user("mei@sgjio.example.com", role=UserRole.ADMIN, name="Mei")
    admin.post(f"/api/admin/admins/{mei.id}/remove")
    event = _only("identity.admin.removed")
    assert event["aggregate_id"] == str(mei.id)
    assert event["data"] == {
        "admin_id": str(mei.id),
        "email": "mei@sgjio.example.com",
        "name": "Mei",
        "remover_name": "Yash",
    }
    # Safe to repeat: no second email.
    admin.post(f"/api/admin/admins/{mei.id}/remove")
    assert len(outbox_events("identity.admin.removed")) == 1


def test_cancelling_an_invite_or_a_refused_removal_sends_nothing(admin, db, make_user):
    arjun = _invite(admin, db)
    yash = db.scalar(select(User).where(User.email == ADMIN["email"]))
    before = len(emails())
    admin.post(f"/api/admin/admins/{arjun.id}/remove")
    assert admin.post(f"/api/admin/admins/{yash.id}/remove").status_code == 409
    assert len(emails()) == before
    assert outbox_events("identity.admin.removed") == []


# --- The relay ------------------------------------------------------------------------------


@pytest.mark.integration
def test_the_relay_publishes_the_outbox_to_rabbitmq(client, monkeypatch):
    """The events reach the broker: one row through publish_pending to a queue of our own.

    It publishes to a private, auto-deleted exchange rather than sgjio.events, so a running
    Learning (bound to identity.user.*) never receives this test's learner."""
    from app.platform.broker import close_quietly, connect

    try:
        connection = connect("test")
    except Exception as error:  # noqa: BLE001
        pytest.skip(f"RabbitMQ is not running ({error})")
    exchange = f"identity-test-{uuid.uuid4().hex[:8]}"
    try:
        channel = connection.channel()
        channel.exchange_declare(exchange, exchange_type="topic", auto_delete=True)
        channel.confirm_delivery()
        queue = channel.queue_declare("", exclusive=True, auto_delete=True).method.queue
        channel.queue_bind(queue, exchange, routing_key="identity.user.registered")
        monkeypatch.setattr("app.platform.outbox.EXCHANGE", exchange)

        client.post("/api/auth/register", json=NEW)
        [written] = outbox_events()
        from app.db import SessionLocal

        assert publish_pending(SessionLocal, channel) == 1
        assert publish_pending(SessionLocal, channel) == 0

        method, properties, body = channel.basic_get(queue, auto_ack=True)
        assert method is not None
        assert method.exchange == exchange
        message = json.loads(body)
        assert message == written
        assert properties.message_id == written["event_id"]
        assert properties.type == "identity.user.registered"
        assert properties.app_id == "identity"
        contracts.assert_valid(message)
    finally:
        with contextlib.suppress(Exception):  # auto_delete removes it anyway
            connection.channel().exchange_delete(exchange)
        close_quietly(connection)


def test_every_event_with_an_address_or_link_is_discarded_after_publishing():
    """The relay deletes EMAIL_EVENTS rows once published (app/main.py), so one-time links
    and addresses don't stay in the outbox. Any identity event whose contract carries an
    email address or a link must be in that set."""
    if not contracts.available():
        pytest.skip("contracts/events not found (set CONTRACTS_DIR)")
    sensitive = set()
    for path in contracts.events_dir().glob("identity.*.schema.json"):
        schema = json.loads(path.read_text())
        data = json.dumps(schema["properties"]["data"])
        if any(f'"{field}"' in data for field in ("email", "link", "sign_in_url")):
            sensitive.add(schema["title"])
    assert sensitive == events.EMAIL_EVENTS


def test_the_service_passes_the_email_events_to_the_relay(monkeypatch):
    seen = {}

    def fake_workers(session_factory, **kwargs):
        seen.update(kwargs)
        return contextlib.nullcontext()

    monkeypatch.setattr("app.main.background_workers", fake_workers)
    with TestClient(app):
        pass
    assert seen["relay"] is True
    assert seen["discard_after_publish"] == events.EMAIL_EVENTS


# --- Direct use -----------------------------------------------------------------------------


def test_an_administrators_user_type_is_always_null(db, make_user):
    """The contract: user_type is null exactly for administrators."""
    admin = make_user("odd@example.com", role=UserRole.ADMIN)
    admin.user_type = "newcomer"
    events.user_registered(db, admin)
    db.commit()
    assert _only("identity.user.registered")["data"]["user_type"] is None


def test_user_deleted_takes_the_time_it_is_given(db):
    user_id = uuid.uuid4()
    when = datetime(2026, 11, 12, 9, 30, tzinfo=UTC)
    events.user_deleted(db, user_id, when)
    db.commit()
    assert _only("identity.user.deleted")["data"] == {
        "user_id": str(user_id),
        "deleted_at": "2026-11-12T09:30:00Z",
    }


def test_two_browsers_registering_the_same_email_write_one_event(client):
    with TestClient(app) as other:
        assert client.post("/api/auth/register", json=NEW).status_code == 201
        assert other.post("/api/auth/register", json=NEW).status_code == 409
    assert len(outbox_events("identity.user.registered")) == 1
