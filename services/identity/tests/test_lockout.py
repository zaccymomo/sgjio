"""SCRUM-73: failed sign-in counting and temporary blocking (SCRUM-62 AC5, SCRUM-68 AC5)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from app.models import LoginAttempt, UserRole

USER = {"email": "user@example.com", "password": "Password123"}
WRONG = {"email": "user@example.com", "password": "WrongPass1"}


def _fail(client, times, path="/api/auth/sign-in", body=WRONG):
    return [client.post(path, json=body) for _ in range(times)]


def test_fifth_failure_blocks_and_says_when_to_try_again(client, make_user):
    make_user(**USER)
    responses = _fail(client, 5)
    assert [r.status_code for r in responses[:4]] == [401] * 4
    blocked = responses[4]
    assert blocked.status_code == 429
    detail = blocked.json()["detail"]
    assert detail["code"] == "too_many_attempts"
    assert 14 * 60 < detail["retry_after_seconds"] <= 15 * 60
    assert "blocked_until" in detail
    assert blocked.headers["Retry-After"] == str(detail["retry_after_seconds"])


def test_correct_password_is_refused_while_blocked(client, make_user):
    make_user(**USER)
    _fail(client, 5)
    assert client.post("/api/auth/sign-in", json=USER).status_code == 429


def test_block_lifts_after_the_lockout_period(client, make_user, db):
    make_user(**USER)
    _fail(client, 5)
    db.execute(update(LoginAttempt).values(attempted_at=datetime.now(UTC) - timedelta(minutes=16)))
    db.commit()
    assert client.post("/api/auth/sign-in", json=USER).status_code == 200


def test_success_resets_the_count(client, make_user):
    make_user(**USER)
    _fail(client, 4)
    assert client.post("/api/auth/sign-in", json=USER).status_code == 200
    assert [r.status_code for r in _fail(client, 4)] == [401] * 4


def test_unknown_emails_are_blocked_too(client):
    # Otherwise the block itself would reveal which emails are registered.
    body = {"email": "nobody@example.com", "password": "WrongPass1"}
    assert _fail(client, 5, body=body)[-1].status_code == 429


def test_main_app_and_admin_portal_count_separately(client, make_user):
    make_user(USER["email"], USER["password"], role=UserRole.ADMIN)
    _fail(client, 5)  # blocked on the main app
    admin_attempt = client.post("/api/admin/auth/sign-in", json=USER)
    assert admin_attempt.status_code == 200


def test_admin_portal_blocks_after_five_failures(client, make_user):
    make_user(USER["email"], USER["password"], role=UserRole.ADMIN)
    responses = _fail(client, 5, path="/api/admin/auth/sign-in")
    assert responses[-1].status_code == 429
