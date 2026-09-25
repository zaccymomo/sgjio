"""SCRUM-74: reset emails and the one-time links behind SCRUM-63 and SCRUM-69."""

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

from sqlalchemy import update

from app import mailer
from app.auth.reset import (
    check_reset_token,
    consume_reset_token,
    issue_reset_token,
    request_password_reset,
    set_new_password,
)
from app.models import AuthScope, PasswordResetToken, UserRole


def _token_from_last_email() -> tuple[str, str]:
    link = next(word for word in mailer.outbox[-1].text.split() if word.startswith("http"))
    return link, parse_qs(urlparse(link).query)["token"][0]


def test_reset_email_is_sent_with_a_working_link(db, make_user):
    user = make_user()
    request_password_reset(db, "USER@example.com", AuthScope.APP)

    assert len(mailer.outbox) == 1
    email = mailer.outbox[0]
    assert email.to == user.email
    assert "valid for 5 minutes" in email.text
    assert "5 minutes" in email.html
    link, token = _token_from_last_email()
    assert link.startswith("http://localhost:5173/reset-password?token=")
    assert check_reset_token(db, token, AuthScope.APP).id == user.id


def test_admin_reset_links_point_to_the_admin_portal(db, make_user):
    make_user(role=UserRole.ADMIN)
    request_password_reset(db, "user@example.com", AuthScope.ADMIN)
    link, _ = _token_from_last_email()
    assert link.startswith("http://localhost:5174/reset-password?token=")
    assert "admin" in mailer.outbox[-1].subject.lower()


def test_no_email_for_unknown_address(db):
    request_password_reset(db, "nobody@example.com", AuthScope.APP)
    assert mailer.outbox == []


def test_no_admin_reset_for_ordinary_user(db, make_user):
    make_user()
    request_password_reset(db, "user@example.com", AuthScope.ADMIN)
    assert mailer.outbox == []


def test_link_works_only_once(db, make_user):
    user = make_user()
    token = issue_reset_token(db, user, AuthScope.APP)
    assert consume_reset_token(db, token, AuthScope.APP).id == user.id
    assert consume_reset_token(db, token, AuthScope.APP) is None


def test_link_expires_after_five_minutes(db, make_user):
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
