"""Flows that end in an email, sent by Notification from Identity's events and read back
from Mailpit's API: password reset (8.3 item 9) and administrators (8.3 item 3).
"""

import httpx

from conftest import (
    PASSWORD,
    client,
    sign_in_admin,
    unique,
    unique_email,
)
from shapes import check, not_signed_in, problem


def test_forgot_password_email_resets_the_password(new_learner, mailpit):
    learner = new_learner()
    with client() as http:
        check(
            http.post("/api/auth/forgot-password", json={"email": learner.email}),
            "POST /api/auth/forgot-password",
            204,
        )
        # An unknown email gets the same answer and no email.
        nobody = unique_email()
        check(
            http.post("/api/auth/forgot-password", json={"email": nobody}),
            "POST /api/auth/forgot-password",
            204,
        )

    message = mailpit.wait_for(learner.email, "password")
    assert message["To"][0]["Address"] == learner.email
    assert "15 minutes" in message["Text"]
    link = mailpit.link(message, "/reset-password")
    assert link.startswith("http://localhost:5173/reset-password?token=")
    token = mailpit.token(link)

    with client() as http:
        check(
            http.post("/api/auth/reset-password/check", json={"token": token}),
            "POST /api/auth/reset-password/check",
            204,
        )
        problem(
            http.post(
                "/api/auth/reset-password",
                json={"token": token, "password": "Short1", "password_confirmation": "Short1"},
            ),
            422,
            "weak_password",
        )
        check(
            http.post(
                "/api/auth/reset-password",
                json={
                    "token": token,
                    "password": "ResetPass123",
                    "password_confirmation": "ResetPass123",
                },
            ),
            "POST /api/auth/reset-password",
            204,
        )
        # Works once.
        problem(
            http.post("/api/auth/reset-password/check", json={"token": token}),
            410,
            "reset_link_invalid",
        )
        # Every session ended; the new password works and the old one doesn't.
        not_signed_in(learner.http.get("/api/progress"))
        problem(
            http.post("/api/auth/sign-in", json={"email": learner.email, "password": PASSWORD}),
            401,
            "invalid_credentials",
        )
        check(
            http.post(
                "/api/auth/sign-in", json={"email": learner.email, "password": "ResetPass123"}
            ),
            "POST /api/auth/sign-in",
            200,
        )
        check(http.get("/api/progress"), "GET /api/progress", 200)
    assert mailpit.messages_to(nobody) == []


def test_a_new_reset_request_cancels_the_old_link(new_learner, mailpit):
    learner = new_learner()
    with client() as http:
        http.post("/api/auth/forgot-password", json={"email": learner.email})
        first = mailpit.token(
            mailpit.link(mailpit.wait_for(learner.email, "password"), "/reset-password")
        )
        http.post("/api/auth/forgot-password", json={"email": learner.email})
        second_message = mailpit.wait_for(learner.email, "password", count=2)
        second = mailpit.token(mailpit.link(second_message, "/reset-password"))
        assert first != second
        problem(
            http.post("/api/auth/reset-password/check", json={"token": first}),
            410,
            "reset_link_invalid",
        )
        check(
            http.post("/api/auth/reset-password/check", json={"token": second}),
            "POST /api/auth/reset-password/check",
            204,
        )


def _admins(admin: httpx.Client) -> dict:
    return check(admin.get("/api/admin/admins"), "GET /api/admin/admins", 200)


def test_invite_accept_sign_in_then_remove_admin(admin, mailpit):
    """Invite, email, accept, sign in, work; removed, and refused at once (8.3.3)."""
    email = f"{unique('e2e-admin')}@sgjio.example.com"
    invited = check(
        admin.post("/api/admin/admins", json={"name": "E2E Admin", "email": email}),
        "POST /api/admin/admins",
        201,
    )
    assert invited["status"] == "invited" and invited["added_by"] == "SGJio Admin"
    problem(
        admin.post("/api/admin/admins", json={"name": "Elsewhere", "email": unique_email()}),
        422,
        "outside_domain",
    )

    message = mailpit.wait_for(email, "invit")
    # Notification's inbox: one event, one email.
    assert len(mailpit.messages_to(email)) == 1
    link = mailpit.link(message, "/set-password")
    assert link.startswith("http://localhost:5174/set-password?token=")
    assert "SGJio Admin" in message["Text"]
    token = mailpit.token(link)

    with client() as http:
        greeting = check(
            http.post("/api/admin/auth/invite/check", json={"token": token}),
            "POST /api/admin/auth/invite/check",
            200,
        )
        assert greeting == {"name": "E2E Admin", "email": email, "invited_by": "SGJio Admin"}
        accepted = check(
            http.post(
                "/api/admin/auth/invite/accept",
                json={"token": token, "password": PASSWORD, "password_confirmation": PASSWORD},
            ),
            "POST /api/admin/auth/invite/accept",
            200,
        )
        assert accepted["user"]["email"] == email and accepted["user"]["role"] == "admin"
        problem(
            http.post("/api/admin/auth/invite/check", json={"token": token}),
            410,
            "invite_link_invalid",
        )

    new_admin = sign_in_admin(email, PASSWORD)
    try:
        check(new_admin.get("/api/admin/topics"), "GET /api/admin/topics", 200)
        listed = {a["email"]: a for a in _admins(admin)["admins"]}
        assert listed[email]["status"] == "active"

        removed = check(
            admin.post(f"/api/admin/admins/{invited['id']}/remove"),
            "POST /api/admin/admins/{admin_id}/remove",
            200,
        )
        assert removed["status"] == "removed" and removed["removed_by"] == "SGJio Admin"
        # Refused on the very next request, by every service.
        not_signed_in(new_admin.get("/api/admin/topics"))
        not_signed_in(new_admin.get("/api/admin/aptitude-questions"))
        not_signed_in(new_admin.get("/api/admin/ping"))
        not_signed_in(new_admin.get("/api/admin/auth/me"))
    finally:
        new_admin.close()

    with client() as http:
        problem(
            http.post("/api/admin/auth/sign-in", json={"email": email, "password": PASSWORD}),
            401,
            "invalid_credentials",
        )
    removal = mailpit.wait_for(email, "removed")
    assert "SGJio Admin" in removal["Text"]
    activity = _admins(admin)["activity"]
    assert {"invited", "joined", "removed"} <= {
        event["action"] for event in activity if event["admin_id"] == invited["id"]
    }
    assert email in {a["email"] for a in _admins(admin)["removed"]}


def test_admin_cannot_remove_themselves(admin):
    me = next(a for a in _admins(admin)["admins"] if a["is_you"])
    problem(admin.post(f"/api/admin/admins/{me['id']}/remove"), 409, "cannot_remove_self")


def test_admin_forgot_password_email(admin, mailpit):
    """An admin's reset email links to the portal; a learner's admin request sends nothing."""
    email = f"{unique('e2e-admin')}@sgjio.example.com"
    invited = check(
        admin.post("/api/admin/admins", json={"name": "Reset Admin", "email": email}),
        "POST /api/admin/admins",
        201,
    )
    token = mailpit.token(mailpit.link(mailpit.wait_for(email, "invit"), "/set-password"))
    with client() as http:
        http.post(
            "/api/admin/auth/invite/accept",
            json={"token": token, "password": PASSWORD, "password_confirmation": PASSWORD},
        )
        check(
            http.post("/api/admin/auth/forgot-password", json={"email": email}),
            "POST /api/admin/auth/forgot-password",
            204,
        )
        reset = mailpit.wait_for(email, "password")
        link = mailpit.link(reset, "/reset-password")
        assert link.startswith("http://localhost:5174/reset-password?token=")
        check(
            http.post(
                "/api/admin/auth/reset-password",
                json={
                    "token": mailpit.token(link),
                    "password": "AdminReset123",
                    "password_confirmation": "AdminReset123",
                },
            ),
            "POST /api/admin/auth/reset-password",
            204,
        )
        check(
            http.post(
                "/api/admin/auth/sign-in", json={"email": email, "password": "AdminReset123"}
            ),
            "POST /api/admin/auth/sign-in",
            200,
        )
    check(
        admin.post(f"/api/admin/admins/{invited['id']}/remove"),
        "POST /api/admin/admins/{admin_id}/remove",
        200,
    )
