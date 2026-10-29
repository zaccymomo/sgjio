"""Signing in and registering with Google (SCRUM-92).

Google is never contacted: `_decode_token`, the one function that checks a token with
Google, is replaced by `google_token`, which makes a token for whatever claims a test needs.
"""

import pytest
from sqlalchemy import select

from app import mailer
from app.auth import google
from app.config import get_settings
from app.models import AuthScope, PasswordResetToken, User, UserRole
from app.privacy import NOTICE_VERSION

PROJECT = "sgjio-test"
PASSWORD = "Password123"


@pytest.fixture
def google_token(monkeypatch):
    """`google_token(sub=..., email=...)` returns a token the API accepts as that account."""
    monkeypatch.setattr(get_settings(), "firebase_project_id", PROJECT)
    tokens: dict[str, dict] = {}

    def decode(token: str, project_id: str) -> dict:
        assert project_id == PROJECT
        if token not in tokens:
            raise google.GoogleTokenInvalid("unknown test token")
        return tokens[token]

    monkeypatch.setattr(google, "_decode_token", decode)

    def make(
        sub: str = "google-1",
        email: str = "mei@gmail.com",
        verified: bool = True,
        name: str = "Mei Tan",
        **overrides,
    ) -> str:
        claims = {
            "iss": f"https://securetoken.google.com/{PROJECT}",
            "aud": PROJECT,
            "sub": f"firebase-{sub}",
            "email": email,
            "email_verified": verified,
            "name": name,
            "firebase": {
                "sign_in_provider": "google.com",
                "identities": {"google.com": [sub], "email": [email]},
            },
            **overrides,
        }
        token = f"token-{len(tokens)}"
        tokens[token] = claims
        return token

    return make


def _continue(client, token, **signup):
    body = {"id_token": token}
    if signup:
        body["signup"] = {
            "name": "Mei Tan",
            "user_type": "newcomer",
            "privacy_consent": True,
            "privacy_notice_version": NOTICE_VERSION,
            **signup,
        }
    return client.post("/api/auth/google", json=body)


def _sign_up(client, google_token, **claims):
    response = _continue(client, google_token(**claims), name="Mei Tan")
    assert response.status_code == 200, response.json()
    return response


# --- Configuration and tokens --------------------------------------------------------------


def test_switched_off_without_a_firebase_project(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "firebase_project_id", "")
    response = _continue(client, "anything")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "google_sign_in_unavailable"


def test_a_token_google_does_not_vouch_for_is_refused(client, db, google_token):
    response = _continue(client, "forged")
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "google_token_invalid"
    assert db.scalar(select(User)) is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"iss": "https://securetoken.google.com/another-project"},
        {"firebase": {"sign_in_provider": "password", "identities": {}}},
        {"firebase": {"sign_in_provider": "google.com", "identities": {}}},
        {"email": ""},
    ],
    ids=["other project", "not google", "no google id", "no email"],
)
def test_tokens_that_are_not_a_google_sign_in_for_this_project_are_refused(google_token, overrides):
    with pytest.raises(google.GoogleTokenInvalid):
        google.verify_google_token(google_token(**overrides))


def test_a_server_clock_a_little_off_from_googles_is_allowed(monkeypatch):
    """A token is used within a second of being issued; a slow clock must not refuse it."""
    from google.oauth2 import id_token

    seen = {}

    def verify(token, request, audience=None, clock_skew_in_seconds=0):
        seen.update(audience=audience, skew=clock_skew_in_seconds)
        return {}

    monkeypatch.setattr(id_token, "verify_firebase_token", verify)
    google._decode_token("token", PROJECT)
    assert seen == {"audience": PROJECT, "skew": 60}


def test_the_reason_a_token_was_refused_is_logged(client, google_token, caplog, monkeypatch):
    # Running the migrations applies alembic.ini's logging setup, which switches off loggers
    # that already exist, this one included. The API itself never runs migrations.
    monkeypatch.setattr(google.logger, "disabled", False)
    with caplog.at_level("WARNING", logger="sgjio.auth.google"):
        assert _continue(client, "forged").status_code == 401
    assert "Google sign-in token refused: unknown test token" in caplog.text


def test_identity_uses_googles_own_id_and_a_lower_case_email(google_token):
    identity = google.verify_google_token(google_token(sub="g-42", email=" Mei@Gmail.com "))
    assert identity.sub == "g-42"
    assert identity.email == "mei@gmail.com"
    assert identity.email_verified is True
    # Only a real true counts as verified.
    unverified = google.verify_google_token(google_token(verified="true"))
    assert unverified.email_verified is False


# --- New accounts ---------------------------------------------------------------------------


def test_someone_new_is_asked_to_sign_up_and_nothing_is_created_yet(client, db, google_token):
    response = _continue(client, google_token(name="Mei Tan", email="Mei@gmail.com"))
    assert response.status_code == 200
    assert response.json() == {
        "status": "needs_signup",
        "user": None,
        "created": False,
        "name": "Mei Tan",
        "email": "mei@gmail.com",
    }
    assert db.scalar(select(User)) is None
    assert client.get("/api/auth/me").status_code == 401


def test_without_a_google_name_the_email_suggests_one(client, google_token):
    response = _continue(client, google_token(name="", email="mei.tan@gmail.com"))
    assert response.json()["name"] == "mei.tan"


def test_signing_up_creates_a_learner_with_no_password_and_signs_in(client, db, google_token):
    response = _continue(client, google_token(sub="g-7"), name="  Mei  ", user_type="singaporean")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "signed_in"
    assert body["created"] is True
    assert body["user"]["has_password"] is False
    assert body["user"]["google_linked"] is True

    user = db.scalar(select(User))
    assert user.name == "Mei"
    assert user.email == "mei@gmail.com"
    assert user.password_hash is None
    assert user.google_sub == "g-7"
    assert user.role == UserRole.USER
    assert user.user_type.value == "singaporean"
    assert user.privacy_notice_version == NOTICE_VERSION
    assert user.privacy_agreed_at is not None

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "mei@gmail.com"


@pytest.mark.parametrize(
    ("signup", "code"),
    [
        ({"privacy_notice_version": "old-version"}, "privacy_notice_changed"),
        ({"privacy_consent": False}, "validation_error"),
        ({"name": "   "}, "validation_error"),
        ({"user_type": None}, "validation_error"),
    ],
    ids=["old notice", "no consent", "blank name", "no user type"],
)
def test_sign_up_needs_a_name_a_user_type_and_the_current_notice(
    client, db, google_token, signup, code
):
    response = _continue(client, google_token(), **signup)
    assert response.status_code == 422
    if code != "validation_error":
        assert response.json()["detail"]["code"] == code
        assert response.json()["detail"]["field"] == "privacy_consent"
    assert db.scalar(select(User)) is None


def test_an_unverified_google_email_never_creates_or_links_an_account(
    client, db, google_token, make_user
):
    response = _continue(client, google_token(verified=False), name="Mei")
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "google_email_unverified"
    assert db.scalar(select(User)) is None

    user = make_user(email="mei@gmail.com")
    assert _continue(client, google_token(verified=False)).status_code == 403
    db.refresh(user)
    assert user.google_sub is None


# --- Returning and existing accounts --------------------------------------------------------


def test_a_returning_google_user_signs_in_without_signing_up_again(client, db, google_token):
    _sign_up(client, google_token, sub="g-1")
    client.cookies.clear()

    # Their Google email may have changed since; Google's id is what identifies them.
    response = _continue(client, google_token(sub="g-1", email="mei.new@gmail.com"))
    assert response.status_code == 200
    assert response.json()["status"] == "signed_in"
    assert response.json()["created"] is False
    assert len(db.scalars(select(User)).all()) == 1


def test_answers_sent_for_an_account_that_now_exists_just_sign_in(client, db, google_token):
    """Sign-up finished in another tab first: the second tab signs in to the same account."""
    token = google_token(sub="g-1")
    _continue(client, token, name="First tab")
    response = _continue(client, token, name="Second tab")
    assert response.json()["created"] is False
    assert [user.name for user in db.scalars(select(User))] == ["First tab"]


def test_an_existing_learner_with_that_email_is_linked_and_keeps_their_password(
    client, db, google_token, make_user
):
    user = make_user(email="mei@gmail.com", name="Mei from register")
    response = _continue(client, google_token(sub="g-9", email="MEI@gmail.com"))
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "signed_in"
    assert body["created"] is False
    assert body["user"]["id"] == str(user.id)
    assert body["user"]["has_password"] is True
    assert body["user"]["google_linked"] is True

    db.refresh(user)
    assert user.google_sub == "g-9"
    assert user.name == "Mei from register"
    client.cookies.clear()
    password = client.post(
        "/api/auth/sign-in", json={"email": "mei@gmail.com", "password": PASSWORD}
    )
    assert password.status_code == 200


def test_administrator_and_removed_accounts_are_never_reached_with_google(
    client, db, google_token, make_user
):
    from datetime import UTC, datetime

    admin = make_user(email="admin@gmail.com", role=UserRole.ADMIN)
    removed = make_user(email="gone@gmail.com")
    removed.removed_at = datetime.now(UTC)
    db.commit()

    for account, sub in [(admin, "g-admin"), (removed, "g-gone")]:
        response = _continue(client, google_token(sub=sub, email=account.email))
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "google_not_available"
        db.refresh(account)
        assert account.google_sub is None
    assert client.get("/api/auth/me").status_code == 401


def test_an_email_already_linked_to_another_google_account_is_refused(
    client, db, google_token, make_user
):
    user = make_user(email="mei@gmail.com")
    user.google_sub = "g-first"
    db.commit()

    response = _continue(client, google_token(sub="g-second", email="mei@gmail.com"))
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "google_account_mismatch"
    db.refresh(user)
    assert user.google_sub == "g-first"


# --- The session it starts -------------------------------------------------------------------


def test_the_admin_portal_has_no_google_sign_in(client, google_token):
    response = client.post("/api/admin/auth/google", json={"id_token": google_token()})
    assert response.status_code in (404, 405)


def test_google_starts_an_ordinary_main_app_session(client, db, google_token):
    _sign_up(client, google_token)
    assert client.get("/api/auth/me").status_code == 200
    assert client.get("/api/admin/auth/me").status_code == 401
    assert db.scalar(select(User)).email == "mei@gmail.com"

    assert client.post("/api/auth/sign-out").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_a_google_only_account_cannot_be_signed_in_to_with_a_password(client, google_token):
    _sign_up(client, google_token)
    client.cookies.clear()
    for password in ["x", "Password123", "None"]:
        response = client.post(
            "/api/auth/sign-in", json={"email": "mei@gmail.com", "password": password}
        )
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "invalid_credentials"


# --- Passwords and deleting the account ------------------------------------------------------


def test_forgot_password_tells_a_google_only_account_how_it_signs_in(client, db, google_token):
    _sign_up(client, google_token)
    client.cookies.clear()
    mailer.outbox.clear()

    assert (
        client.post("/api/auth/forgot-password", json={"email": "mei@gmail.com"}).status_code == 204
    )
    assert len(mailer.outbox) == 1
    email = mailer.outbox[0]
    assert email.subject == "How you sign in to SGJio"
    assert "Continue with Google" in email.text
    assert "http://localhost:5173/sign-in" in email.text
    assert db.scalar(select(PasswordResetToken)) is None


def test_forgot_password_still_resets_an_account_that_also_uses_google(
    client, db, google_token, make_user
):
    make_user(email="mei@gmail.com")
    _continue(client, google_token())
    mailer.outbox.clear()

    client.post("/api/auth/forgot-password", json={"email": "mei@gmail.com"})
    assert mailer.outbox[0].subject == "Reset your SGJio password"
    assert db.scalar(select(PasswordResetToken)).scope == AuthScope.APP


def test_a_google_only_account_has_no_password_to_change(client, google_token):
    _sign_up(client, google_token)
    response = client.post(
        "/api/auth/change-password",
        json={
            "current_password": "anything1",
            "password": "BetterPass456",
            "password_confirmation": "BetterPass456",
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "no_password"


def test_a_google_only_account_is_deleted_by_confirming_with_the_same_google_account(
    client, db, google_token
):
    _sign_up(client, google_token, sub="g-1")

    missing = client.post("/api/auth/delete-account", json={})
    assert missing.status_code == 422
    assert missing.json()["detail"]["code"] == "google_confirmation_required"

    other = client.post(
        "/api/auth/delete-account",
        json={"id_token": google_token(sub="g-2", email="someone@gmail.com")},
    )
    assert other.status_code == 403
    assert other.json()["detail"]["code"] == "google_account_mismatch"

    forged = client.post("/api/auth/delete-account", json={"id_token": "forged"})
    assert forged.status_code == 401
    assert db.scalar(select(User)) is not None

    same = client.post("/api/auth/delete-account", json={"id_token": google_token(sub="g-1")})
    assert same.status_code == 204
    assert db.scalar(select(User)) is None
    assert client.get("/api/auth/me").status_code == 401


def test_an_account_with_a_password_still_confirms_deletion_with_it(
    client, db, google_token, make_user
):
    make_user(email="mei@gmail.com")
    _continue(client, google_token(sub="g-1"))

    # Linked to Google, but it has a password, so that is what confirms.
    google_only = client.post(
        "/api/auth/delete-account", json={"id_token": google_token(sub="g-1")}
    )
    assert google_only.status_code == 422
    assert google_only.json()["detail"]["code"] == "password_required"

    assert client.post("/api/auth/delete-account", json={"password": PASSWORD}).status_code == 204
    assert db.scalar(select(User)) is None
