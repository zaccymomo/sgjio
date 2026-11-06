"""Registration consent, password changes, and self-service account deletion.

Deleting an account removes Identity's rows in one transaction with an
identity.user.deleted event; Learning and Content erase their own data when it arrives
(their tests cover that side).
"""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.reset import issue_reset_token
from app.config import get_settings
from app.main import app
from app.models import (
    AuthScope,
    AuthSession,
    LoginAttempt,
    PasswordResetToken,
    Profile,
    User,
    UserRole,
)
from app.privacy import NOTICE_VERSION
from tests.helpers import outbox_events

PASSWORD = "Password123"
NEW_PASSWORD = "BetterPass456"


def _sign_in(client, email="member@example.com", password=PASSWORD):
    return client.post("/api/auth/sign-in", json={"email": email, "password": password})


def test_registration_requires_consent_and_records_version_and_time(client, db):
    body = {
        "name": "Member",
        "email": "member@example.com",
        "password": PASSWORD,
        "password_confirmation": PASSWORD,
        "user_type": "newcomer",
        "privacy_notice_version": NOTICE_VERSION,
    }
    assert client.post("/api/auth/register", json=body).status_code == 422
    assert (
        client.post("/api/auth/register", json={**body, "privacy_consent": False}).status_code
        == 422
    )
    assert db.scalar(select(User)) is None
    assert (
        client.post("/api/auth/register", json={**body, "privacy_consent": True}).status_code == 201
    )
    user = db.scalar(select(User))
    assert user.privacy_notice_version == NOTICE_VERSION
    assert user.privacy_agreed_at <= datetime.now(UTC)


def test_stale_privacy_notice_version_is_refused(client, db):
    response = client.post(
        "/api/auth/register",
        json={
            "name": "Member",
            "email": "member@example.com",
            "password": PASSWORD,
            "password_confirmation": PASSWORD,
            "user_type": "newcomer",
            "privacy_consent": True,
            "privacy_notice_version": "old-version",
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "privacy_notice_changed"
    assert db.scalar(select(User)) is None


def test_change_password_keeps_current_session_and_revokes_others_and_reset_links(
    client, db, make_user
):
    user = make_user(email="member@example.com")
    assert _sign_in(client).status_code == 200
    other = TestClient(app)
    try:
        assert _sign_in(other).status_code == 200
        token = issue_reset_token(db, user, AuthScope.APP)
        response = client.post(
            "/api/auth/change-password",
            json={
                "current_password": PASSWORD,
                "password": NEW_PASSWORD,
                "password_confirmation": NEW_PASSWORD,
            },
        )
        assert response.status_code == 204, response.json() if response.content else ""
        assert client.get("/api/auth/me").status_code == 200
        assert other.get("/api/auth/me").status_code == 401
        assert (
            client.post("/api/auth/reset-password/check", json={"token": token}).status_code == 410
        )
        assert len(db.scalars(select(AuthSession).where(AuthSession.user_id == user.id)).all()) == 1
        assert (
            db.scalar(select(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
            is None
        )
        client.post("/api/auth/sign-out")
        assert _sign_in(client).status_code == 401
        assert _sign_in(client, password=NEW_PASSWORD).status_code == 200
    finally:
        other.close()


def test_change_password_validates_old_password_and_new_rules(client, db, make_user):
    user = make_user(email="member@example.com")
    assert _sign_in(client).status_code == 200
    path = "/api/auth/change-password"
    bad_old = client.post(
        path,
        json={
            "current_password": "wrong",
            "password": NEW_PASSWORD,
            "password_confirmation": NEW_PASSWORD,
        },
    )
    assert bad_old.status_code == 401
    assert bad_old.json()["detail"]["code"] == "incorrect_current_password"
    mismatch = client.post(
        path,
        json={
            "current_password": PASSWORD,
            "password": NEW_PASSWORD,
            "password_confirmation": "Different456",
        },
    )
    assert mismatch.status_code == 422
    assert mismatch.json()["detail"]["field"] == "password_confirmation"
    weak = client.post(
        path,
        json={
            "current_password": PASSWORD,
            "password": "weak",
            "password_confirmation": "weak",
        },
    )
    assert weak.status_code == 422
    assert weak.json()["detail"]["failures"]
    for _ in range(get_settings().login_max_failures):
        client.post(
            path,
            json={
                "current_password": "wrong",
                "password": NEW_PASSWORD,
                "password_confirmation": NEW_PASSWORD,
            },
        )
    blocked = client.post(
        path,
        json={
            "current_password": PASSWORD,
            "password": NEW_PASSWORD,
            "password_confirmation": NEW_PASSWORD,
        },
    )
    assert blocked.status_code == 429
    assert blocked.json()["detail"]["blocked_until"]
    db.refresh(user)
    assert _sign_in(TestClient(app), password=NEW_PASSWORD).status_code == 429


def test_delete_account_removes_personal_data_and_frees_email(client, db, make_user):
    user = make_user(email="member@example.com")
    user_id = user.id
    email = user.email
    db.add(
        Profile(
            user_id=user.id, neighbourhood="Tampines", interests=["Food"], languages=["English"]
        )
    )
    db.commit()
    assert _sign_in(client).status_code == 200
    reset_token = issue_reset_token(db, user, AuthScope.APP)
    wrong = client.post("/api/auth/delete-account", json={"password": "wrong"})
    assert wrong.status_code == 401
    assert db.get(User, user_id) is not None
    assert outbox_events("identity.user.deleted") == []
    before = datetime.now(UTC)
    response = client.post("/api/auth/delete-account", json={"password": PASSWORD})
    assert response.status_code == 204
    db.expire_all()
    assert db.get(User, user_id) is None
    assert db.scalar(select(Profile).where(Profile.user_id == user_id)) is None
    # Learning (progress) and Content (reporter links) erase theirs from this event.
    [deleted] = outbox_events("identity.user.deleted")
    assert deleted["aggregate_id"] == deleted["data"]["user_id"] == str(user_id)
    assert deleted["aggregate_version"] == 2
    assert datetime.fromisoformat(deleted["data"]["deleted_at"]) >= before
    assert db.scalar(select(AuthSession).where(AuthSession.user_id == user_id)) is None
    assert (
        db.scalar(select(PasswordResetToken).where(PasswordResetToken.user_id == user_id)) is None
    )
    assert db.scalar(select(LoginAttempt).where(LoginAttempt.email == email)) is None
    assert client.get("/api/auth/me").status_code == 401
    assert _sign_in(client).status_code == 401
    assert (
        client.post("/api/auth/reset-password/check", json={"token": reset_token}).status_code
        == 410
    )
    assert (
        client.post(
            "/api/auth/register",
            json={
                "name": "New Member",
                "email": "member@example.com",
                "password": PASSWORD,
                "password_confirmation": PASSWORD,
                "user_type": "newcomer",
                "privacy_consent": True,
                "privacy_notice_version": NOTICE_VERSION,
            },
        ).status_code
        == 201
    )


def test_admin_cannot_self_delete_from_main_app(client, db, make_user):
    admin = make_user(email="admin@example.com", role=UserRole.ADMIN)
    assert _sign_in(client, email=admin.email).status_code == 200
    response = client.post("/api/auth/delete-account", json={"password": PASSWORD})
    assert response.status_code == 403
    assert db.get(User, admin.id) is not None
    assert outbox_events("identity.user.deleted") == []
