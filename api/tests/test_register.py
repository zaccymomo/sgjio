"""SCRUM-61: registering an account, checked criterion by criterion."""

from sqlalchemy import select

from app.models import User, UserRole, UserType

NEW = {
    "name": "Ana Rivera",
    "email": "ana@example.com",
    "password": "Password123",
    "password_confirmation": "Password123",
    "user_type": "newcomer",
}


def _register(client, **overrides):
    return client.post("/api/auth/register", json={**NEW, **overrides})


# --- AC1: a valid form creates the account and signs the person in -----------------------


def test_registering_creates_the_account_with_the_chosen_user_type(client, db):
    response = _register(client)
    assert response.status_code == 201
    assert response.json()["user"]["email"] == NEW["email"]

    user = db.scalar(select(User).where(User.email == NEW["email"]))
    assert user.name == "Ana Rivera"
    assert user.user_type == UserType.NEWCOMER
    # Registration never makes administrators; those come from app.cli (SCRUM-68).
    assert user.role == UserRole.USER


def test_registering_signs_the_new_user_in(client):
    response = _register(client)
    assert "sgjio_session=" in response.headers["set-cookie"]
    assert client.get("/api/auth/me").json()["email"] == NEW["email"]


def test_singaporean_is_also_accepted(client, db):
    assert _register(client, user_type="singaporean").status_code == 201
    assert db.scalar(select(User)).user_type == UserType.SINGAPOREAN


def test_password_is_stored_hashed_and_works_for_sign_in(client, db):
    _register(client)
    user = db.scalar(select(User))
    assert NEW["password"] not in user.password_hash

    client.post("/api/auth/sign-out")
    response = client.post(
        "/api/auth/sign-in", json={"email": NEW["email"], "password": NEW["password"]}
    )
    assert response.status_code == 200


def test_email_is_stored_lower_case_and_trimmed(client, db):
    assert _register(client, email="  Ana@Example.COM ").status_code == 201
    assert db.scalar(select(User)).email == "ana@example.com"


# --- AC2: an email already in use --------------------------------------------------------


def test_second_registration_with_the_same_email_is_refused(client, db):
    _register(client)
    response = _register(client, name="Someone Else")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "email_taken"
    # The form highlights the email field and offers the sign-in page.
    assert response.json()["detail"]["field"] == "email"
    assert len(db.scalars(select(User)).all()) == 1


def test_an_email_in_use_is_recognised_whatever_the_case(client, make_user):
    make_user("taken@example.com")
    assert _register(client, email="TAKEN@example.com").status_code == 409


# --- AC3: invalid email format -----------------------------------------------------------


def test_an_invalid_email_is_refused_on_the_email_field(client, db):
    response = _register(client, email="not-an-email")
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] == "email"
    assert db.scalar(select(User)) is None


# --- AC4: password rules -----------------------------------------------------------------


def test_a_short_password_is_refused_and_names_the_rule(client, db):
    response = _register(client, password="Ab1", password_confirmation="Ab1")
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "weak_password"
    assert detail["field"] == "password"
    assert detail["failures"] == ["Use at least 8 characters."]
    assert db.scalar(select(User)) is None


def test_a_password_with_no_number_is_refused(client):
    response = _register(client, password="PasswordOnly", password_confirmation="PasswordOnly")
    assert response.json()["detail"]["failures"] == ["Include at least one number."]


def test_every_broken_rule_is_reported(client):
    response = _register(client, password="aaa", password_confirmation="aaa")
    assert response.json()["detail"]["failures"] == [
        "Use at least 8 characters.",
        "Include at least one number.",
    ]


# --- AC5: confirmation does not match ----------------------------------------------------


def test_a_mismatched_confirmation_is_refused(client, db):
    response = _register(client, password_confirmation="Password124")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "password_mismatch"
    assert response.json()["detail"]["field"] == "password_confirmation"
    assert db.scalar(select(User)) is None


# --- AC6: required fields ----------------------------------------------------------------


def test_missing_and_empty_fields_are_refused(client, db):
    assert client.post("/api/auth/register", json={}).status_code == 422
    assert _register(client, name="   ").status_code == 422
    assert _register(client, email="").status_code == 422
    assert _register(client, password="").status_code == 422
    assert db.scalar(select(User)) is None


def test_user_type_must_be_selected_and_must_be_one_of_the_two(client, db):
    without_type = {k: v for k, v in NEW.items() if k != "user_type"}
    assert client.post("/api/auth/register", json=without_type).status_code == 422
    assert _register(client, user_type="").status_code == 422
    assert _register(client, user_type="tourist").status_code == 422
    assert db.scalar(select(User)) is None


# --- The admin portal has no registration (SCRUM-68) -------------------------------------


def test_the_admin_portal_does_not_expose_registration(client, db):
    assert client.post("/api/admin/auth/register", json=NEW).status_code == 404
    assert db.scalar(select(User)) is None
