"""SCRUM-94: the introduction shown on first sign-in, and recording that it was seen."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.db import engine
from app.models import UserRole

URL = "/api/intro/finished"
API_DIR = Path(__file__).resolve().parent.parent
NEW = {
    "name": "Ana Rivera",
    "email": "ana@example.com",
    "password": "Password123",
    "password_confirmation": "Password123",
    "user_type": "newcomer",
    "privacy_consent": True,
    "privacy_notice_version": "2026-10-22",
}


def _sign_in(client, make_user, email="user@example.com"):
    make_user(email=email)
    response = client.post("/api/auth/sign-in", json={"email": email, "password": "Password123"})
    assert response.status_code == 200
    return response.json()["user"]


def test_needs_a_signed_in_user(client):
    assert client.post(URL).status_code == 401


def test_a_new_account_has_not_seen_the_introduction(client):
    """AC1: the app shows the introduction while this is empty."""
    response = client.post("/api/auth/register", json=NEW)
    assert response.status_code == 201
    assert response.json()["user"]["intro_finished_at"] is None
    assert client.get("/api/auth/me").json()["intro_finished_at"] is None


def test_finishing_or_skipping_is_recorded(client, make_user):
    """AC6: once finished or skipped, sign-in and /me say so."""
    assert _sign_in(client, make_user)["intro_finished_at"] is None
    response = client.post(URL)
    assert response.status_code == 200
    assert response.json()["email"] == "user@example.com"
    assert response.json()["intro_finished_at"] is not None
    assert client.get("/api/auth/me").json() == response.json()

    client.post("/api/auth/sign-out")
    signed_in = client.post(
        "/api/auth/sign-in", json={"email": "user@example.com", "password": "Password123"}
    ).json()
    assert signed_in["user"]["intro_finished_at"] is not None


def test_doing_it_again_keeps_the_first_time(client, make_user):
    _sign_in(client, make_user)
    client.post(URL)
    first = client.get("/api/auth/me").json()["intro_finished_at"]
    assert client.post(URL).json()["intro_finished_at"] == first
    assert client.get("/api/auth/me").json()["intro_finished_at"] == first


def test_an_admin_portal_session_cannot_use_it(client, make_user):
    make_user("admin@example.com", "AdminPass123", role=UserRole.ADMIN)
    signed_in = client.post(
        "/api/admin/auth/sign-in", json={"email": "admin@example.com", "password": "AdminPass123"}
    )
    assert signed_in.status_code == 200
    assert client.post(URL).status_code == 401


def test_users_only_mark_their_own(client, make_user, db):
    make_user(email="other@example.com")
    _sign_in(client, make_user)
    client.post(URL)
    seen = dict(db.execute(text("SELECT email, intro_finished_at FROM users")).all())
    assert seen["user@example.com"] is not None
    assert seen["other@example.com"] is None


def test_migration_0015_marks_existing_learners_as_having_seen_it():
    """People already using the app aren't sent through it; admins are left alone."""
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(API_DIR / "alembic"))
    command.downgrade(config, "0014")
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO users (id, name, email, password_hash, role, user_type) VALUES "
                    "(gen_random_uuid(), 'L', 'l@example.com', 'x', 'user', 'newcomer'), "
                    "(gen_random_uuid(), 'A', 'a@example.com', 'x', 'admin', NULL)"
                )
            )
        command.upgrade(config, "0015")
        with engine.connect() as conn:
            rows = dict(
                conn.execute(text("SELECT email, intro_finished_at = created_at FROM users")).all()
            )
        assert rows["l@example.com"] is True
        assert rows["a@example.com"] is None
    finally:
        command.upgrade(config, "head")
