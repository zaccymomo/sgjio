"""End-to-end API checks for the admin portal's SCRUM-69 password-reset pages."""

from app.models import UserRole
from tests.helpers import emails, token_from_last_email

ADMIN = {"email": "admin@example.com", "password": "AdminPass123"}
REQUEST = "/api/admin/auth/forgot-password"
VALIDATE = "/api/admin/auth/reset-password/check"
CONFIRM = "/api/admin/auth/reset-password"


def _token_from_email() -> str:
    return token_from_last_email()


def test_admin_reset_request_always_has_the_same_response(client, make_user):
    make_user(**ADMIN, role=UserRole.ADMIN)
    ordinary = make_user("ordinary@example.com", role=UserRole.USER)

    admin_response = client.post(REQUEST, json={"email": ADMIN["email"]})
    ordinary_response = client.post(REQUEST, json={"email": ordinary.email})
    unknown_response = client.post(REQUEST, json={"email": "nobody@example.com"})

    responses = (admin_response, ordinary_response, unknown_response)
    assert [response.status_code for response in responses] == [
        204,
        204,
        204,
    ]
    assert len(emails()) == 1
    assert emails()[0]["data"]["expires_in_minutes"] == 15


def test_admin_reset_link_can_be_validated_and_resets_password(client, make_user):
    make_user(**ADMIN, role=UserRole.ADMIN)
    client.post(REQUEST, json={"email": ADMIN["email"]})
    token = _token_from_email()

    assert client.post(VALIDATE, json={"token": token}).status_code == 204
    response = client.post(
        CONFIRM,
        json={"token": token, "password": "NewAdmin456", "password_confirmation": "NewAdmin456"},
    )
    assert response.status_code == 204
    assert client.post(VALIDATE, json={"token": token}).status_code == 410
    assert client.post("/api/admin/auth/sign-in", json=ADMIN).status_code == 401
    assert (
        client.post(
            "/api/admin/auth/sign-in",
            json={"email": ADMIN["email"], "password": "NewAdmin456"},
        ).status_code
        == 200
    )


def test_invalid_or_reused_admin_reset_link_is_refused(client, make_user):
    make_user(**ADMIN, role=UserRole.ADMIN)
    body = {
        "token": "not-a-real-token",
        "password": "NewAdmin456",
        "password_confirmation": "NewAdmin456",
    }
    response = client.post(CONFIRM, json=body)

    assert response.status_code == 410
    assert response.json()["detail"]["code"] == "reset_link_invalid"


def test_bad_new_password_does_not_consume_admin_reset_link(client, make_user):
    make_user(**ADMIN, role=UserRole.ADMIN)
    client.post(REQUEST, json={"email": ADMIN["email"]})
    token = _token_from_email()

    mismatch = client.post(
        CONFIRM,
        json={"token": token, "password": "NewAdmin456", "password_confirmation": "OtherAdmin456"},
    )
    assert mismatch.status_code == 422
    assert mismatch.json()["detail"]["code"] == "password_mismatch"
    assert client.post(VALIDATE, json={"token": token}).status_code == 204

    weak = client.post(
        CONFIRM,
        json={"token": token, "password": "short", "password_confirmation": "short"},
    )
    assert weak.status_code == 422
    assert weak.json()["detail"]["code"] == "weak_password"
    assert client.post(VALIDATE, json={"token": token}).status_code == 204


def test_new_admin_reset_request_invalidates_the_previous_link(client, make_user):
    make_user(**ADMIN, role=UserRole.ADMIN)
    client.post(REQUEST, json={"email": ADMIN["email"]})
    first_token = _token_from_email()
    client.post(REQUEST, json={"email": ADMIN["email"]})
    second_token = _token_from_email()

    assert first_token != second_token
    assert client.post(VALIDATE, json={"token": first_token}).status_code == 410
    assert client.post(VALIDATE, json={"token": second_token}).status_code == 204
