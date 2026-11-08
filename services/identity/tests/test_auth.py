"""SCRUM-73: sessions and guards, checked against the task's "Done when" list."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from app.models import AuthSession, UserRole

ADMIN = {"email": "admin@example.com", "password": "AdminPass123"}
USER = {"email": "user@example.com", "password": "Password123"}


def _admin(make_user):
    return make_user(ADMIN["email"], ADMIN["password"], role=UserRole.ADMIN)


# --- Main app -----------------------------------------------------------------------------


def test_signed_out_request_to_protected_route_is_refused(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "not_signed_in"


def test_user_can_sign_in_and_is_recognised(client, make_user):
    make_user(**USER)
    response = client.post("/api/auth/sign-in", json=USER)
    assert response.status_code == 200
    assert response.json()["user"]["email"] == USER["email"]
    assert client.get("/api/auth/me").json()["email"] == USER["email"]


def test_sign_in_ignores_email_case_and_spaces(client, make_user):
    make_user(**USER)
    response = client.post(
        "/api/auth/sign-in", json={"email": "  USER@Example.com ", "password": USER["password"]}
    )
    assert response.status_code == 200


def test_session_cookie_is_persistent_and_http_only(client, make_user):
    make_user(**USER)
    response = client.post("/api/auth/sign-in", json=USER)
    cookie = response.headers["set-cookie"]
    assert "sgjio_session=" in cookie
    assert "HttpOnly" in cookie
    assert "Max-Age=604800" in cookie  # 7 days, so closing the tab keeps you signed in
    assert "Path=/api" in cookie


def test_wrong_password_and_unknown_email_get_the_same_message(client, make_user):
    make_user(**USER)
    wrong_password = client.post(
        "/api/auth/sign-in", json={"email": USER["email"], "password": "Nope12345"}
    )
    unknown_email = client.post(
        "/api/auth/sign-in", json={"email": "nobody@example.com", "password": "Nope12345"}
    )
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


def test_empty_fields_are_rejected(client):
    response = client.post("/api/auth/sign-in", json={"email": "", "password": ""})
    assert response.status_code == 422


def test_sign_out_ends_the_session(client, make_user, db):
    make_user(**USER)
    client.post("/api/auth/sign-in", json=USER)
    token = client.cookies.get("sgjio_session")

    assert client.post("/api/auth/sign-out").status_code == 204
    assert db.scalar(select(AuthSession)) is None

    # Even if the old cookie is replayed, it no longer works (SCRUM-59 AC3).
    client.cookies.set("sgjio_session", token, path="/api")
    assert client.get("/api/auth/me").status_code == 401


def test_expired_session_is_refused(client, make_user, db):
    make_user(**USER)
    client.post("/api/auth/sign-in", json=USER)
    db.execute(update(AuthSession).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    db.commit()
    assert client.get("/api/auth/me").status_code == 401


def test_using_a_session_extends_it(client, make_user, db):
    make_user(**USER)
    client.post("/api/auth/sign-in", json=USER)
    two_days_ago = datetime.now(UTC) - timedelta(days=2)
    db.execute(
        update(AuthSession).values(
            last_seen_at=two_days_ago, expires_at=two_days_ago + timedelta(days=7)
        )
    )
    db.commit()

    assert client.get("/api/auth/me").status_code == 200
    db.expire_all()
    session = db.scalar(select(AuthSession))
    assert session.expires_at > datetime.now(UTC) + timedelta(days=6, hours=23)


# --- Admin portal -------------------------------------------------------------------------


def test_signed_out_request_to_admin_route_is_refused(client):
    assert client.get("/api/admin/ping").status_code == 401


def test_seeded_style_admin_can_sign_in_and_use_admin_routes(client, make_user):
    _admin(make_user)
    response = client.post("/api/admin/auth/sign-in", json=ADMIN)
    assert response.status_code == 200
    assert "sgjio_admin_session=" in response.headers["set-cookie"]
    assert "Path=/api/admin" in response.headers["set-cookie"]
    assert client.get("/api/admin/ping").json() == {"ok": True, "admin": ADMIN["email"]}


def test_ordinary_user_cannot_sign_in_to_admin_portal(client, make_user):
    make_user(**USER)
    response = client.post("/api/admin/auth/sign-in", json=USER)
    assert response.status_code == 401
    # Same message as a wrong password, so it does not reveal who is an admin.
    assert response.json()["detail"]["code"] == "invalid_credentials"


def test_main_app_session_does_not_open_admin_routes(client, make_user):
    # Even an administrator signed in to the main app is not signed in to the portal.
    _admin(make_user)
    assert client.post("/api/auth/sign-in", json=ADMIN).status_code == 200
    assert client.get("/api/admin/ping").status_code == 401


def test_admin_session_does_not_sign_in_to_main_app(client, make_user):
    _admin(make_user)
    client.post("/api/admin/auth/sign-in", json=ADMIN)
    assert client.get("/api/auth/me").status_code == 401


def test_admin_losing_role_is_refused_on_next_request(client, make_user, db):
    admin = _admin(make_user)
    client.post("/api/admin/auth/sign-in", json=ADMIN)
    admin.role = UserRole.USER
    db.commit()
    assert client.get("/api/admin/ping").status_code == 401


def test_admin_sessions_are_shorter(client, make_user):
    _admin(make_user)
    response = client.post("/api/admin/auth/sign-in", json=ADMIN)
    assert "Max-Age=28800" in response.headers["set-cookie"]  # 8 hours


def test_admin_sign_out(client, make_user):
    _admin(make_user)
    client.post("/api/admin/auth/sign-in", json=ADMIN)
    assert client.post("/api/admin/auth/sign-out").status_code == 204
    assert client.get("/api/admin/ping").status_code == 401
