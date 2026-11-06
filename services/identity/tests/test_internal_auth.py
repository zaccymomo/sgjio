"""The gateway's session check, /internal/auth/{app,admin} (contracts/README.md, "Auth
contract"). It must apply exactly the rules Identity's own routes apply (SCRUM-73,
SCRUM-68 AC6, SCRUM-81 AC4), since every Content and Learning route depends on it."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.main import app
from app.models import AuthSession, UserRole

KEY = {"X-Gateway-Key": "test-gateway-key"}
USER = {"email": "user@example.com", "password": "Password123"}
ADMIN = {"email": "admin@example.com", "password": "AdminPass123"}
PROFILE = {"interests": ["Food"], "languages": ["English"], "neighbourhood": "Tampines"}


@pytest.fixture
def gateway():
    """A client with no cookie jar of its own: it forwards the Cookie header it is given,
    as nginx does."""
    with TestClient(app) as test_client:
        yield test_client


def _ask(gateway, scope: str, cookie: str | None, key: dict | None = None):
    headers = dict(KEY if key is None else key)
    if cookie is not None:
        headers["Cookie"] = cookie
    return gateway.get(f"/internal/auth/{scope}", headers=headers)


def _app_cookie(client, body=USER) -> str:
    assert client.post("/api/auth/sign-in", json=body).status_code == 200
    return f"sgjio_session={client.cookies.get('sgjio_session')}"


def _admin_cookie(client, body=ADMIN) -> str:
    assert client.post("/api/admin/auth/sign-in", json=body).status_code == 200
    return f"sgjio_admin_session={client.cookies.get('sgjio_admin_session')}"


def _assert_refused(response):
    assert response.status_code == 401
    assert response.content == b""
    assert "x-user-id" not in response.headers
    assert "set-cookie" not in response.headers


# --- Who it says the person is ------------------------------------------------------------


def test_a_signed_in_learner_is_described_in_headers(client, gateway, make_user):
    user = make_user(**USER)
    response = _ask(gateway, "app", _app_cookie(client))

    assert response.status_code == 200
    assert response.content == b""
    assert response.headers["x-user-id"] == str(user.id)
    assert response.headers["x-user-scope"] == "app"
    assert response.headers["x-user-role"] == "user"
    assert response.headers["x-user-type"] == "newcomer"
    assert response.headers["x-profile-completed"] == "false"
    assert response.headers["cache-control"] == "no-store"


def test_profile_completed_follows_the_profile(client, gateway, make_user):
    make_user(**USER)
    cookie = _app_cookie(client)
    assert client.put("/api/profile", json=PROFILE).status_code == 200
    assert _ask(gateway, "app", cookie).headers["x-profile-completed"] == "true"


def test_an_administrator_on_the_portal(client, gateway, make_user):
    admin = make_user(**ADMIN, role=UserRole.ADMIN)
    response = _ask(gateway, "admin", _admin_cookie(client))

    assert response.status_code == 200
    assert response.headers["x-user-id"] == str(admin.id)
    assert response.headers["x-user-scope"] == "admin"
    assert response.headers["x-user-role"] == "admin"
    # Administrators have no user type; nginx then sends no X-User-Type at all.
    assert response.headers["x-user-type"] == ""
    assert response.headers["cache-control"] == "no-store"


def test_an_administrator_signed_in_to_the_main_app_is_an_app_principal(client, gateway, make_user):
    make_user(**ADMIN, role=UserRole.ADMIN)
    response = _ask(gateway, "app", _app_cookie(client, ADMIN))
    assert response.status_code == 200
    assert response.headers["x-user-scope"] == "app"
    assert response.headers["x-user-role"] == "admin"


# --- The sliding session cookie -----------------------------------------------------------


def test_the_session_cookie_is_sent_again_like_every_signed_in_answer(client, gateway, make_user):
    make_user(**USER)
    cookie = _app_cookie(client)
    set_cookie = _ask(gateway, "app", cookie).headers["set-cookie"]
    assert set_cookie.startswith(cookie + ";")
    assert "HttpOnly" in set_cookie
    assert "Max-Age=604800" in set_cookie
    assert "Path=/api" in set_cookie
    assert "SameSite=lax" in set_cookie


def test_the_admin_cookie_keeps_its_own_path_and_lifetime(client, gateway, make_user):
    make_user(**ADMIN, role=UserRole.ADMIN)
    set_cookie = _ask(gateway, "admin", _admin_cookie(client)).headers["set-cookie"]
    assert "sgjio_admin_session=" in set_cookie
    assert "Max-Age=28800" in set_cookie
    assert "Path=/api/admin" in set_cookie


def test_using_a_session_through_the_gateway_extends_it(client, gateway, make_user, db):
    make_user(**USER)
    cookie = _app_cookie(client)
    two_days_ago = datetime.now(UTC) - timedelta(days=2)
    db.execute(
        update(AuthSession).values(
            last_seen_at=two_days_ago, expires_at=two_days_ago + timedelta(days=7)
        )
    )
    db.commit()

    assert _ask(gateway, "app", cookie).status_code == 200
    db.expire_all()
    session = db.scalar(select(AuthSession))
    assert session.expires_at > datetime.now(UTC) + timedelta(days=6, hours=23)


# --- Who it refuses -----------------------------------------------------------------------


def test_only_the_gateway_may_ask(client, gateway, make_user):
    make_user(**USER)
    cookie = _app_cookie(client)
    _assert_refused(_ask(gateway, "app", cookie, key={}))
    _assert_refused(_ask(gateway, "app", cookie, key={"X-Gateway-Key": "guess"}))
    assert _ask(gateway, "app", cookie).status_code == 200


def test_no_cookie_or_an_unknown_one_is_refused(gateway):
    _assert_refused(_ask(gateway, "app", None))
    _assert_refused(_ask(gateway, "app", "sgjio_session=made-up"))
    _assert_refused(_ask(gateway, "admin", "sgjio_admin_session=made-up"))


def test_scopes_never_mix(client, gateway, make_user):
    make_user(**ADMIN, role=UserRole.ADMIN)
    app_cookie = _app_cookie(client, ADMIN)
    admin_cookie = _admin_cookie(client)
    # The app cookie, even an administrator's, never opens the portal (SCRUM-68 AC6)...
    _assert_refused(_ask(gateway, "admin", app_cookie))
    # ...a portal token sent under the app cookie's name is not an app session...
    token = admin_cookie.split("=", 1)[1]
    _assert_refused(_ask(gateway, "app", f"sgjio_session={token}"))
    # ...and the admin cookie is not read for the app scope.
    _assert_refused(_ask(gateway, "app", admin_cookie))


def test_a_signed_out_session_is_refused_at_once(client, gateway, make_user):
    make_user(**USER)
    cookie = _app_cookie(client)
    assert client.post("/api/auth/sign-out").status_code == 204
    _assert_refused(_ask(gateway, "app", cookie))


def test_an_expired_session_is_refused_and_removed(client, gateway, make_user, db):
    make_user(**USER)
    cookie = _app_cookie(client)
    db.execute(update(AuthSession).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    db.commit()
    _assert_refused(_ask(gateway, "app", cookie))
    assert db.scalar(select(AuthSession)) is None


def test_a_removed_administrator_is_refused_on_both_scopes(client, gateway, make_user, db):
    """Removal deletes their sessions; a session that slipped through while the removal
    was being saved is refused too (SCRUM-81 AC4)."""
    admin = make_user(**ADMIN, role=UserRole.ADMIN)
    app_cookie = _app_cookie(client, ADMIN)
    admin_cookie = _admin_cookie(client)
    admin.removed_at = datetime.now(UTC)
    db.commit()

    assert db.scalar(select(AuthSession)) is not None
    _assert_refused(_ask(gateway, "admin", admin_cookie))
    _assert_refused(_ask(gateway, "app", app_cookie))


def test_an_administrator_who_lost_the_role_is_refused_on_the_portal(
    client, gateway, make_user, db
):
    admin = make_user(**ADMIN, role=UserRole.ADMIN)
    cookie = _admin_cookie(client)
    admin.role = UserRole.USER
    db.commit()
    _assert_refused(_ask(gateway, "admin", cookie))


def test_removing_an_administrator_from_the_portal_ends_their_access(client, gateway, make_user):
    make_user(**ADMIN, role=UserRole.ADMIN, name="Yash")
    other = {"email": "mei@example.com", "password": "OtherPass123"}
    mei = make_user(**other, role=UserRole.ADMIN, name="Mei")
    with TestClient(app) as mei_browser:
        mei_cookie = _admin_cookie(mei_browser, other)
    _admin_cookie(client)
    assert _ask(gateway, "admin", mei_cookie).status_code == 200

    assert client.post(f"/api/admin/admins/{mei.id}/remove").status_code == 200

    _assert_refused(_ask(gateway, "admin", mei_cookie))


def test_a_deleted_account_is_refused(client, gateway, make_user):
    make_user(**USER)
    cookie = _app_cookie(client)
    response = client.post("/api/auth/delete-account", json={"password": USER["password"]})
    assert response.status_code == 204
    _assert_refused(_ask(gateway, "app", cookie))


def test_unknown_scopes_do_not_exist(gateway):
    assert gateway.get("/internal/auth/other", headers=KEY).status_code == 404
