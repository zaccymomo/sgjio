"""Health checks, the error shapes the front ends read, and Identity's schema rules.

The monolith's GET /api/health is answered by the gateway now; each service has
/health/live and /health/ready (app/platform/health.py)."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models import User, UserRole


def test_live_and_ready(client):
    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/health/ready").json() == {"status": "ok"}


def test_every_answer_carries_a_request_id(client):
    assert client.get("/health/live").headers["x-request-id"]
    given = client.get("/health/live", headers={"X-Request-ID": "abc-123"})
    assert given.headers["x-request-id"] == "abc-123"


def test_signed_out_is_byte_for_byte_the_monoliths_answer(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.content == (
        b'{"detail":{"code":"not_signed_in","message":"Please sign in to continue."}}'
    )


def test_validation_errors_keep_fastapis_shape(client):
    response = client.post("/api/auth/sign-in", json={})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "email"]


def test_a_refused_admin_change_keeps_the_monoliths_field_order(client, make_user):
    make_user("yash@sgjio.example.com", "AdminPass123", role=UserRole.ADMIN, name="Yash")
    client.post(
        "/api/admin/auth/sign-in",
        json={"email": "yash@sgjio.example.com", "password": "AdminPass123"},
    )
    response = client.post("/api/admin/admins", json={"name": "A", "email": "a@gmail.com"})
    assert response.status_code == 422
    assert list(response.json()["detail"]) == ["code", "message", "domain", "field"]


def test_docs_are_served_by_the_service(client):
    assert client.get("/docs").status_code == 200
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/auth/sign-in" in paths
    assert "/internal/auth/app" not in paths


def test_emails_are_unique(db, make_user):
    make_user("a@example.com")
    db.add(User(name="B", email="a@example.com", password_hash="x", role=UserRole.USER))
    with pytest.raises(IntegrityError):
        db.commit()


def test_database_rejects_an_unknown_role(db, make_user):
    # Raw SQL on purpose: this checks the database's own CHECK constraint, not Python.
    user = make_user()
    with pytest.raises(IntegrityError):
        db.execute(text("UPDATE users SET role = 'owner' WHERE id = :id"), {"id": user.id})
        db.commit()
