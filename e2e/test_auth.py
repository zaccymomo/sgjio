"""Sign-in, sessions and the gateway's auth (detailed plan 8.3 items 1, 2 and 4).

- an app cookie never opens admin routes, and the reverse
- client X-User-* headers are ignored; services refuse a request without the gateway key
- the sliding session cookie is relayed once on a Learning response
- lockout after 5 failures (429), change password, sign out
"""

import os

import httpx
import pytest

from conftest import (
    ADMIN,
    NEWCOMER,
    PASSWORD,
    client,
    progress,
    sign_in_admin,
    unique_email,
)
from shapes import check, not_signed_in, problem, validation_error

# The services' own host ports (127.0.0.1 only), used only to prove they refuse requests
# that did not come through the gateway.
SERVICE_PORTS = {
    "identity": os.environ.get("E2E_IDENTITY_URL", "http://localhost:8001"),
    "content": os.environ.get("E2E_CONTENT_URL", "http://localhost:8002"),
    "learning": os.environ.get("E2E_LEARNING_URL", "http://localhost:8003"),
}


def test_register_then_profile_then_aptitude_at_once(new_learner):
    """8.3.1: register, /me, intro, profile, progress, then the aptitude test straight after
    the profile save (the gateway asks Identity every time, so nothing is stale)."""
    learner = new_learner(onboarded=False)
    http = learner.http
    me = check(http.get("/api/auth/me"), "GET /api/auth/me", 200)
    assert me["email"] == learner.email
    assert me["intro_finished_at"] is None
    assert me["has_password"] is True and me["google_linked"] is False

    finished = check(http.post("/api/intro/finished"), "POST /api/intro/finished", 200)
    assert finished["intro_finished_at"] is not None

    options = check(http.get("/api/profile/options"), "GET /api/profile/options", 200)
    saved = check(
        http.put(
            "/api/profile",
            json={
                "neighbourhood": "Tampines",
                "interests": options["interests"][:2],
                "languages": options["languages"][:1],
            },
        ),
        "PUT /api/profile",
        200,
    )
    assert saved["interests"] == options["interests"][:2]
    assert check(http.get("/api/profile"), "GET /api/profile", 200) == saved

    body = progress(http)
    assert body["completed"] == 0 and body["aptitude_taken"] is False

    step = check(http.post("/api/aptitude/start"), "POST /api/aptitude/start", 200)
    assert step["done"] is False and step["question"]["level"] == 1
    assert "correct_option_id" not in step["question"]


def test_register_refuses_a_taken_email_and_bad_password():
    email = unique_email()
    with client() as http:
        version = http.get("/api/auth/privacy-notice-version").json()["version"]
        body = {
            "name": "E2E",
            "email": email,
            "password": PASSWORD,
            "password_confirmation": PASSWORD,
            "user_type": "singaporean",
            "privacy_consent": True,
            "privacy_notice_version": version,
        }
        check(http.post("/api/auth/register", json=body), "POST /api/auth/register", 201)
    with client() as other:
        problem(other.post("/api/auth/register", json=body), 409, "email_taken")
        weak = {
            **body,
            "email": unique_email(),
            "password": "short",
            "password_confirmation": "short",
        }
        response = other.post("/api/auth/register", json=weak)
        assert response.status_code == 422, response.text


def test_signed_out_requests_get_the_exact_401_everywhere():
    with client() as http:
        for path in [
            "/api/progress",
            "/api/review",
            "/api/search?q=kopi",
            "/api/admin/topics",
            "/api/admin/lessons",
            "/api/admin/reports",
            "/api/admin/aptitude-questions",
            "/api/auth/me",
            "/api/admin/auth/me",
            "/api/profile",
        ]:
            not_signed_in(http.get(path))
        not_signed_in(http.post("/api/aptitude/start"))
        not_signed_in(http.get("/api/admin/lessons/00000000-0000-0000-0000-000000000000/insights"))


def test_app_cookie_is_refused_on_admin_routes_and_admin_cookie_works(new_learner, admin):
    """8.3.2: scope separation."""
    learner = new_learner()
    for path in ["/api/admin/topics", "/api/admin/aptitude-questions", "/api/admin/reports"]:
        not_signed_in(learner.http.get(path))
    not_signed_in(learner.http.get("/api/admin/admins"))
    not_signed_in(learner.http.get("/api/admin/ping"))

    lessons = check(admin.get("/api/admin/lessons"), "GET /api/admin/lessons", 200)
    insights = admin.get(f"/api/admin/lessons/{lessons[0]['id']}/insights")
    check(insights, "GET /api/admin/lessons/{lesson_id}/insights", 200)
    # An admin's cookie is for /api/admin only: learner routes don't see it.
    not_signed_in(admin.get("/api/progress"))


def test_admin_signed_in_to_the_app_is_not_signed_in_to_the_portal():
    """As in the monolith: an administrator may use the main app, but that session never
    opens admin routes. A learner can't sign in to the portal at all."""
    with client() as http:
        check(http.post("/api/auth/sign-in", json=ADMIN), "POST /api/auth/sign-in", 200)
        not_signed_in(http.get("/api/admin/ping"))
        not_signed_in(http.get("/api/admin/topics"))
        not_signed_in(http.get("/api/admin/lessons/00000000-0000-0000-0000-000000000000/insights"))
        problem(http.post("/api/admin/auth/sign-in", json=NEWCOMER), 401, "invalid_credentials")


def test_forged_principal_headers_are_ignored(new_learner):
    learner = new_learner()
    with client() as seeded:
        check(seeded.post("/api/auth/sign-in", json=NEWCOMER), "POST /api/auth/sign-in", 200)
        newcomer = check(seeded.get("/api/auth/me"), "GET /api/auth/me", 200)
        assert progress(seeded)["completed"] > 0

    forged = {
        "X-User-Id": newcomer["id"],
        "X-User-Scope": "admin",
        "X-User-Role": "admin",
        "X-User-Type": "singaporean",
        "X-Profile-Completed": "true",
        "X-Gateway-Key": "guess",
    }
    # Signed out: still signed out.
    with client() as anonymous:
        not_signed_in(anonymous.get("/api/progress", headers=forged))
        not_signed_in(anonymous.get("/api/admin/topics", headers=forged))
        not_signed_in(anonymous.get("/api/auth/me", headers=forged))
    # Signed in as someone else: still that someone, with no admin rights.
    mine = check(learner.http.get("/api/progress", headers=forged), "GET /api/progress", 200)
    assert mine["completed"] == 0
    assert (
        check(learner.http.get("/api/auth/me", headers=forged), "GET /api/auth/me", 200)["id"]
        == learner.id
    )
    not_signed_in(learner.http.get("/api/admin/topics", headers=forged))
    review = check(learner.http.get("/api/review", headers=forged), "GET /api/review", 200)
    assert review == {"mistakes": []}


@pytest.mark.parametrize(
    ("service", "path"),
    [("content", "/api/admin/topics"), ("learning", "/api/progress"), ("learning", "/api/review")],
)
def test_services_refuse_requests_that_bypass_the_gateway(service, path, new_learner):
    learner = new_learner()
    headers = {
        "X-User-Id": learner.id,
        "X-User-Scope": "admin" if "/admin/" in path else "app",
        "X-User-Role": "admin" if "/admin/" in path else "user",
        "X-User-Type": "newcomer",
        "X-Profile-Completed": "true",
    }
    base = SERVICE_PORTS[service]
    cookie = f"sgjio_session={learner.http.cookies['sgjio_session']}"
    not_signed_in(httpx.get(base + path, headers={**headers, "Cookie": cookie}))
    not_signed_in(httpx.get(base + path, headers={**headers, "X-Gateway-Key": "wrong-key"}))


def test_identity_introspection_is_internal_only(new_learner):
    learner = new_learner()
    cookie = {"Cookie": f"sgjio_session={learner.http.cookies['sgjio_session']}"}
    # Not routed by the gateway at all.
    with client() as http:
        response = http.get("/internal/auth/app", headers=cookie)
        assert response.status_code == 404
        assert response.json() == {"detail": "Not Found"}
    # And Identity itself refuses it without the gateway key.
    direct = httpx.get(SERVICE_PORTS["identity"] + "/internal/auth/app", headers=cookie)
    assert direct.status_code == 401
    assert "x-user-id" not in direct.headers


def test_unknown_routes_get_fastapis_404():
    with client() as http:
        response = http.get("/api/nothing-here")
        assert response.status_code == 404
        assert response.json() == {"detail": "Not Found"}
        assert response.headers.get("x-request-id")


def test_request_id_is_echoed_once(new_learner):
    learner = new_learner()
    response = learner.http.get("/api/progress", headers={"X-Request-ID": "e2e-correlation-1"})
    assert response.headers.get_list("x-request-id") == ["e2e-correlation-1"]


def test_sliding_session_cookie_is_relayed_once_on_service_routes(new_learner, admin):
    """8.3.4: Identity re-sends the session cookie on every signed-in request (as the
    monolith did); the gateway relays it on Learning's and Content's answers, exactly once."""
    learner = new_learner()
    for path in ["/api/progress", "/api/review"]:
        cookies = learner.http.get(path).headers.get_list("set-cookie")
        assert len(cookies) == 1, cookies
        assert cookies[0].startswith("sgjio_session=")
        assert "Path=/api" in cookies[0] and "HttpOnly" in cookies[0]
        assert "Max-Age=604800" in cookies[0]
    cookies = admin.get("/api/admin/topics").headers.get_list("set-cookie")
    assert len(cookies) == 1 and cookies[0].startswith("sgjio_admin_session="), cookies
    assert "Path=/api/admin" in cookies[0] and "Max-Age=28800" in cookies[0]
    # Refused requests carry no cookie.
    with client() as anonymous:
        assert anonymous.get("/api/progress").headers.get_list("set-cookie") == []


def test_lockout_after_five_failures(new_learner):
    learner = new_learner()
    wrong = {"email": learner.email, "password": "WrongPass1"}
    with client() as http:
        for _ in range(4):
            problem(http.post("/api/auth/sign-in", json=wrong), 401, "invalid_credentials")
        blocked = problem(http.post("/api/auth/sign-in", json=wrong), 429, "too_many_attempts")
        assert 14 * 60 < blocked["retry_after_seconds"] <= 15 * 60
        assert "blocked_until" in blocked
        right = http.post("/api/auth/sign-in", json={"email": learner.email, "password": PASSWORD})
        detail = problem(right, 429, "too_many_attempts")
        assert right.headers["Retry-After"] == str(detail["retry_after_seconds"])
        # The admin portal counts separately (and never says the email isn't an admin).
        problem(http.post("/api/admin/auth/sign-in", json=wrong), 401, "invalid_credentials")
    # The learner's existing session is unaffected.
    progress(learner.http)


def test_change_password_signs_out_other_browsers(new_learner):
    learner = new_learner()
    with client() as other:
        check(
            other.post("/api/auth/sign-in", json={"email": learner.email, "password": PASSWORD}),
            "POST /api/auth/sign-in",
            200,
        )
        progress(other)

        problem(
            learner.http.post(
                "/api/auth/change-password",
                json={
                    "current_password": "WrongPass1",
                    "password": "NewPass1234",
                    "password_confirmation": "NewPass1234",
                },
            ),
            401,
            "incorrect_current_password",
        )
        changed = learner.http.post(
            "/api/auth/change-password",
            json={
                "current_password": PASSWORD,
                "password": "NewPass1234",
                "password_confirmation": "NewPass1234",
            },
        )
        check(changed, "POST /api/auth/change-password", 204)
        # This browser stays signed in; the other one is out at once, on every service.
        progress(learner.http)
        not_signed_in(other.get("/api/progress"))
        not_signed_in(other.get("/api/auth/me"))

    with client() as fresh:
        old = fresh.post("/api/auth/sign-in", json={"email": learner.email, "password": PASSWORD})
        problem(old, 401, "invalid_credentials")
        new = fresh.post(
            "/api/auth/sign-in", json={"email": learner.email, "password": "NewPass1234"}
        )
        check(new, "POST /api/auth/sign-in", 200)


def test_sign_out_takes_effect_everywhere_at_once(new_learner):
    learner = new_learner()
    cookie = learner.http.cookies["sgjio_session"]
    response = learner.http.post("/api/auth/sign-out")
    check(response, "POST /api/auth/sign-out", 204)
    assert "sgjio_session=" in response.headers["set-cookie"]
    # Replay the old cookie: refused by Identity and, through the gateway, by Learning.
    with client() as replay:
        replay.cookies.set("sgjio_session", cookie)
        not_signed_in(replay.get("/api/progress"))
        not_signed_in(replay.get("/api/auth/me"))


def test_admin_sign_out(admin):
    check(admin.get("/api/admin/ping"), "GET /api/admin/ping", 200)
    cookie = admin.cookies["sgjio_admin_session"]
    check(admin.post("/api/admin/auth/sign-out"), "POST /api/admin/auth/sign-out", 204)
    with client() as replay:
        replay.cookies.set("sgjio_admin_session", cookie, path="/api/admin")
        not_signed_in(replay.get("/api/admin/topics"))


def test_validation_errors_keep_fastapis_shape(new_learner):
    learner = new_learner()
    validation_error(learner.http.post("/api/aptitude/next", json={"answers": "nope"}))
    validation_error(learner.http.get("/api/lessons/not-a-uuid"))
    admin = sign_in_admin()
    try:
        validation_error(admin.post("/api/admin/topics", json={}))
    finally:
        admin.close()
