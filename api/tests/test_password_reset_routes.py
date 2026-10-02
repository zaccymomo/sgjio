"""End-to-end API checks for the admin portal's SCRUM-69 password-reset pages."""

from urllib.parse import parse_qs, urlparse

from app import mailer
from app.models import UserRole

ADMIN = {"email": "admin@example.com", "password": "AdminPass123"}
REQUEST = "/api/admin/auth/password-reset/request"
VALIDATE = "/api/admin/auth/password-reset/validate"
CONFIRM = "/api/admin/auth/password-reset/confirm"


def _token_from_email() -> str:
    link = next(word for word in mailer.outbox[-1].text.split() if word.startswith("http"))
    return parse_qs(urlparse(link).query)["token"][0]


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
    assert len(mailer.outbox) == 1
    assert "valid for 5 minutes" in mailer.outbox[0].text


def test_admin_reset_link_can_be_validated_and_resets_password(client, make_user):
    make_user(**ADMIN, role=UserRole.ADMIN)
    client.post(REQUEST, json={"email": ADMIN["email"]})
    token = _token_from_email()

    assert client.get(VALIDATE, params={"token": token}).json() == {"valid": True}
    response = client.post(
        CONFIRM,
        json={"token": token, "password": "NewAdmin456", "password_confirmation": "NewAdmin456"},
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Your password has been reset."
    assert client.get(VALIDATE, params={"token": token}).json() == {"valid": False}
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

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_reset_token"


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
    assert client.get(VALIDATE, params={"token": token}).json() == {"valid": True}

    weak = client.post(
        CONFIRM,
        json={"token": token, "password": "short", "password_confirmation": "short"},
    )
    assert weak.status_code == 422
    assert weak.json()["detail"]["code"] == "weak_password"
    assert client.get(VALIDATE, params={"token": token}).json() == {"valid": True}


def test_new_admin_reset_request_invalidates_the_previous_link(client, make_user):
    make_user(**ADMIN, role=UserRole.ADMIN)
    client.post(REQUEST, json={"email": ADMIN["email"]})
    first_token = _token_from_email()
    client.post(REQUEST, json={"email": ADMIN["email"]})
    second_token = _token_from_email()

    assert first_token != second_token
    assert client.get(VALIDATE, params={"token": first_token}).json() == {"valid": False}
    assert client.get(VALIDATE, params={"token": second_token}).json() == {"valid": True}
