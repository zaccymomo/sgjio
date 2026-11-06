"""SCRUM-74: reset emails and the one-time links behind SCRUM-63 and SCRUM-69.

Identity no longer sends the email: it writes identity.password_reset.requested to the
outbox with the link, and Notification sends it (services/notification tests the wording).
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from app.auth.reset import (
    check_reset_token,
    consume_reset_token,
    issue_reset_token,
    request_password_reset,
    set_new_password,
)
from app.models import AuthScope, PasswordResetToken, UserRole
from tests.helpers import emails, link_from_last_email, recipients, token_from_last_email


def _token_from_last_email() -> tuple[str, str]:
    return link_from_last_email(), token_from_last_email()


def test_reset_email_is_sent_with_a_working_link(db, make_user):
    user = make_user()
    request_password_reset(db, "USER@example.com", AuthScope.APP)

    assert len(emails()) == 1
    email = emails()[0]["data"]
    assert email["email"] == user.email
    assert email["name"] == user.name
    assert email["audience"] == "app"
    assert email["method"] == "password"
    # 15 minutes on this branch (5 in the monolith): the email now goes out asynchronously.
    assert email["expires_in_minutes"] == 15
    link, token = _token_from_last_email()
    assert link.startswith("http://localhost:5173/reset-password?token=")
    assert check_reset_token(db, token, AuthScope.APP).id == user.id


def test_admin_reset_links_point_to_the_admin_portal(db, make_user):
    make_user(role=UserRole.ADMIN)
    request_password_reset(db, "user@example.com", AuthScope.ADMIN)
    link, _ = _token_from_last_email()
    assert link.startswith("http://localhost:5174/reset-password?token=")
    # Notification words it for the admin portal.
    assert emails()[-1]["data"]["audience"] == "admin"


def test_no_email_for_unknown_address(db):
    request_password_reset(db, "nobody@example.com", AuthScope.APP)
    assert emails() == []


def test_no_admin_reset_for_ordinary_user(db, make_user):
    make_user()
    request_password_reset(db, "user@example.com", AuthScope.ADMIN)
    assert emails() == []


def test_link_works_only_once(db, make_user):
    user = make_user()
    token = issue_reset_token(db, user, AuthScope.APP)
    assert consume_reset_token(db, token, AuthScope.APP).id == user.id
    assert consume_reset_token(db, token, AuthScope.APP) is None


def test_link_expires(db, make_user):
    user = make_user()
    token = issue_reset_token(db, user, AuthScope.APP)
    db.execute(
        update(PasswordResetToken).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    db.commit()
    assert consume_reset_token(db, token, AuthScope.APP) is None


def test_new_link_cancels_the_earlier_one(db, make_user):
    user = make_user()
    first = issue_reset_token(db, user, AuthScope.APP)
    second = issue_reset_token(db, user, AuthScope.APP)
    assert consume_reset_token(db, first, AuthScope.APP) is None
    assert consume_reset_token(db, second, AuthScope.APP) is not None


def test_app_link_does_not_work_on_admin_portal(db, make_user):
    user = make_user(role=UserRole.ADMIN)
    token = issue_reset_token(db, user, AuthScope.APP)
    assert consume_reset_token(db, token, AuthScope.ADMIN) is None


def test_new_password_replaces_old_and_signs_out_everywhere(client, db, make_user):
    user = make_user()
    client.post("/api/auth/sign-in", json={"email": user.email, "password": "Password123"})
    set_new_password(db, user, "BrandNew456")

    assert client.get("/api/auth/me").status_code == 401
    old = client.post("/api/auth/sign-in", json={"email": user.email, "password": "Password123"})
    new = client.post("/api/auth/sign-in", json={"email": user.email, "password": "BrandNew456"})
    assert old.status_code == 401
    assert new.status_code == 200


# --- SCRUM-63: the reset endpoints the main app's pages call -------------------------------


def _forgot(client, email="user@example.com"):
    return client.post("/api/auth/forgot-password", json={"email": email})


def _reset(client, token, password="NewPass456", confirmation=None):
    return client.post(
        "/api/auth/reset-password",
        json={
            "token": token,
            "password": password,
            "password_confirmation": password if confirmation is None else confirmation,
        },
    )


def test_forgot_password_answers_the_same_for_known_and_unknown_emails(client, make_user):
    # AC2: the response never reveals whether the email has an account.
    make_user()
    known = _forgot(client, "user@example.com")
    unknown = _forgot(client, "nobody@example.com")
    assert known.status_code == unknown.status_code == 204
    assert known.content == unknown.content == b""
    # AC3: only the registered email gets a link.
    assert recipients() == ["user@example.com"]


def test_reset_link_can_be_checked_before_use(client, make_user):
    make_user()
    _forgot(client)
    _, token = _token_from_last_email()
    assert client.post("/api/auth/reset-password/check", json={"token": token}).status_code == 204
    # Checking does not use the link up.
    assert client.post("/api/auth/reset-password/check", json={"token": token}).status_code == 204


def test_resetting_changes_the_password_and_signs_out_everywhere(client, make_user):
    # AC4-AC5
    make_user()
    client.post("/api/auth/sign-in", json={"email": "user@example.com", "password": "Password123"})
    assert client.get("/api/auth/me").status_code == 200

    _forgot(client)
    _, token = _token_from_last_email()
    assert _reset(client, token).status_code == 204

    assert client.get("/api/auth/me").status_code == 401
    old = client.post(
        "/api/auth/sign-in", json={"email": "user@example.com", "password": "Password123"}
    )
    assert old.status_code == 401
    new = client.post(
        "/api/auth/sign-in", json={"email": "user@example.com", "password": "NewPass456"}
    )
    assert new.status_code == 200


def test_a_weak_or_mismatched_password_is_refused_without_using_up_the_link(client, make_user):
    # AC4: the password rules from SCRUM-61 apply.
    make_user()
    _forgot(client)
    _, token = _token_from_last_email()

    weak = _reset(client, token, password="short")
    assert weak.status_code == 422
    assert weak.json()["detail"]["field"] == "password"
    assert "Include at least one number." in weak.json()["detail"]["failures"]

    mismatch = _reset(client, token, confirmation="Different789")
    assert mismatch.status_code == 422
    assert mismatch.json()["detail"]["code"] == "password_mismatch"

    assert _reset(client, token).status_code == 204


def test_used_expired_or_replaced_links_are_refused(client, db, make_user):
    # AC6-AC7
    make_user()
    _forgot(client)
    _, first = _token_from_last_email()
    _forgot(client)
    _, second = _token_from_last_email()

    replaced = _reset(client, first)
    assert replaced.status_code == 410
    assert replaced.json()["detail"]["code"] == "reset_link_invalid"

    assert _reset(client, second).status_code == 204
    assert _reset(client, second).status_code == 410
    check = client.post("/api/auth/reset-password/check", json={"token": second})
    assert check.status_code == 410

    _forgot(client)
    _, third = _token_from_last_email()
    db.execute(
        update(PasswordResetToken).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    db.commit()
    assert _reset(client, third).status_code == 410


def test_main_app_links_do_not_work_on_the_admin_portal(client, make_user):
    make_user(role=UserRole.ADMIN)
    _forgot(client)
    _, token = _token_from_last_email()
    response = client.post("/api/admin/auth/reset-password/check", json={"token": token})
    assert response.status_code == 410
