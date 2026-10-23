"""SCRUM-81: administrators add, remove and restore other administrators from the portal."""

from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import admins, cli, mailer
from app.config import get_settings
from app.main import app
from app.models import AdminAction, AdminEvent, User, UserRole
from app.problems import ContentProblem

ADMIN = {"email": "yash@sgjio.example.com", "password": "AdminPass123"}
OTHER = {"email": "mei@sgjio.example.com", "password": "OtherPass123"}
URL = "/api/admin/admins"
SIGN_IN = "/api/admin/auth/sign-in"
CHECK = "/api/admin/auth/invite/check"
ACCEPT = "/api/admin/auth/invite/accept"


@pytest.fixture
def admin(client, make_user):
    """The test client, signed in to the admin portal as Yash."""
    make_user(ADMIN["email"], ADMIN["password"], role=UserRole.ADMIN, name="Yash")
    assert client.post(SIGN_IN, json=ADMIN).status_code == 200
    return client


@pytest.fixture
def other(make_user):
    """Mei, a second administrator, signed in to the portal in a browser of her own."""
    make_user(OTHER["email"], OTHER["password"], role=UserRole.ADMIN, name="Mei")
    with TestClient(app) as browser:
        assert browser.post(SIGN_IN, json=OTHER).status_code == 200
        yield browser


def _link() -> str:
    return next(word for word in mailer.outbox[-1].text.split() if word.startswith("http"))


def _token() -> str:
    return parse_qs(urlparse(_link()).query)["token"][0]


def _invite(client, name="Arjun", email="arjun@sgjio.example.com", **fields):
    return client.post(URL, json={"name": name, "email": email, **fields})


def _accept(browser, token, password="Joined12345"):
    return browser.post(
        ACCEPT, json={"token": token, "password": password, "password_confirmation": password}
    )


def _find(client, email, group="admins"):
    return next(a for a in client.get(URL).json()[group] if a["email"] == email)


def _actions(db) -> list[str]:
    return [e.action.value for e in db.scalars(select(AdminEvent).order_by(AdminEvent.created_at))]


# --- AC1: the list ------------------------------------------------------------------------


def test_the_list_shows_every_administrator_and_when_they_last_signed_in(admin, other, make_user):
    make_user("learner@example.com")

    body = admin.get(URL).json()

    assert [a["name"] for a in body["admins"]] == ["Mei", "Yash"]
    yash, mei = _find(admin, ADMIN["email"]), _find(admin, OTHER["email"])
    assert yash["is_you"] and not mei["is_you"]
    assert yash["status"] == mei["status"] == "active"
    assert yash["added_at"] and yash["last_sign_in_at"]
    assert body["removed"] == []
    assert body["email_domain"] == "sgjio.example.com"
    assert body["invite_hours"] == 72


def test_an_administrator_who_never_signed_in_has_no_last_sign_in(admin, make_user):
    make_user("quiet@sgjio.example.com", role=UserRole.ADMIN)
    assert _find(admin, "quiet@sgjio.example.com")["last_sign_in_at"] is None


def test_only_the_admin_portal_can_manage_administrators(client, make_user):
    make_user(ADMIN["email"], ADMIN["password"], role=UserRole.ADMIN)
    # Signed in to the main app, even as an administrator, is not signed in to the portal.
    assert client.post("/api/auth/sign-in", json=ADMIN).status_code == 200
    assert client.get(URL).status_code == 401
    assert _invite(client).status_code == 401


# --- AC2: inviting ------------------------------------------------------------------------


def test_inviting_creates_an_administrator_and_emails_a_link_that_works_once(admin, db):
    response = _invite(admin)

    assert response.status_code == 201
    invited = response.json()
    assert invited["status"] == "invited"
    assert invited["added_by"] == "Yash"
    assert invited["invite_expires_at"]
    email = mailer.outbox[-1]
    assert email.to == "arjun@sgjio.example.com"
    assert "Yash invited you" in email.subject
    assert "valid for 3 days" in email.text
    assert "/set-password?token=" in _link()

    token = _token()
    assert admin.post(CHECK, json={"token": token}).json() == {
        "name": "Arjun",
        "email": "arjun@sgjio.example.com",
        "invited_by": "Yash",
    }
    with TestClient(app) as browser:
        joined = _accept(browser, token)
        assert joined.status_code == 200
        # Choosing a password signs them straight in.
        assert browser.get("/api/admin/auth/me").json()["email"] == "arjun@sgjio.example.com"
        assert _accept(browser, token).status_code == 410
    assert admin.post(CHECK, json={"token": token}).status_code == 410

    arjun = _find(admin, "arjun@sgjio.example.com")
    assert arjun["status"] == "active"
    assert arjun["last_sign_in_at"]
    assert _actions(db) == ["invited", "joined"]
    signed_in = {"email": "arjun@sgjio.example.com", "password": "Joined12345"}
    assert admin.post(SIGN_IN, json=signed_in).status_code == 200


def test_an_invited_administrator_cannot_sign_in_before_choosing_a_password(admin, db):
    _invite(admin)
    arjun = db.scalar(select(User).where(User.email == "arjun@sgjio.example.com"))
    assert arjun.role == UserRole.ADMIN and arjun.user_type is None
    for password in ("AdminPass123", "Joined12345"):
        response = admin.post(SIGN_IN, json={"email": arjun.email, "password": password})
        assert response.status_code == 401


def test_an_invite_checks_the_new_password_without_using_up_the_link(admin):
    _invite(admin)
    token = _token()
    response = _accept(admin, token, password="short")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "weak_password"
    assert admin.post(CHECK, json={"token": token}).status_code == 200


def test_an_email_outside_the_team_domain_needs_confirming(admin):
    response = _invite(admin, email="Arjun@Gmail.com")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "outside_domain"
    assert response.json()["detail"]["domain"] == "sgjio.example.com"
    assert mailer.outbox == []

    confirmed = _invite(admin, email="Arjun@Gmail.com", allow_other_domain=True)
    assert confirmed.status_code == 201
    assert confirmed.json()["email"] == "arjun@gmail.com"


def test_the_domain_check_can_be_switched_off(admin, monkeypatch):
    monkeypatch.setattr(get_settings(), "admin_email_domain", "")
    assert _invite(admin, email="arjun@gmail.com").status_code == 201
    assert admin.get(URL).json()["email_domain"] is None


@pytest.mark.parametrize(
    "fields",
    [{"name": "  ", "email": "a@sgjio.example.com"}, {"name": "Arjun", "email": "not-an-email"}],
)
def test_an_invite_needs_a_name_and_a_real_email(admin, fields):
    assert admin.post(URL, json=fields).status_code == 422


# --- AC3: emails that already have an account ---------------------------------------------


def test_a_learners_email_is_refused_and_their_account_is_unchanged(admin, make_user, db):
    learner = make_user("learner@sgjio.example.com", name="Learner")

    response = _invite(admin, email="Learner@sgjio.example.com")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "email_in_use"
    db.refresh(learner)
    assert learner.role == UserRole.USER and learner.name == "Learner"
    assert mailer.outbox == []


def test_an_existing_invited_or_removed_administrator_is_named(admin, other, db):
    assert _invite(admin, email=OTHER["email"]).json()["detail"]["code"] == "already_admin"

    arjun = _invite(admin).json()
    refused = _invite(admin).json()["detail"]
    assert refused["code"] == "already_invited"
    assert refused["admin_id"] == arjun["id"]

    admin.post(f"{URL}/{arjun['id']}/remove")
    assert _invite(admin).json()["detail"]["code"] == "admin_removed"


# --- Resending ----------------------------------------------------------------------------


def test_resending_an_invite_replaces_the_earlier_link(admin, db):
    arjun = _invite(admin).json()
    first = _token()

    response = admin.post(f"{URL}/{arjun['id']}/resend-invite")

    assert response.status_code == 200
    assert admin.post(CHECK, json={"token": first}).status_code == 410
    assert admin.post(CHECK, json={"token": _token()}).status_code == 200
    assert _actions(db) == ["invited", "invite_resent"]


def test_there_is_no_invite_to_resend_to_someone_already_set_up(admin, other):
    mei = _find(admin, OTHER["email"])
    response = admin.post(f"{URL}/{mei['id']}/resend-invite")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "not_invited"


def test_an_invited_administrator_who_forgets_is_sent_a_new_invite(admin, db):
    _invite(admin)
    first = _token()

    admin.post("/api/admin/auth/forgot-password", json={"email": "arjun@sgjio.example.com"})

    assert mailer.outbox[-1].subject == "Set up your SGJio admin account"
    assert "valid for 3 days" in mailer.outbox[-1].text
    assert admin.post(CHECK, json={"token": first}).status_code == 410
    assert admin.post(CHECK, json={"token": _token()}).json()["invited_by"] == "Yash"
    event = db.scalars(select(AdminEvent).order_by(AdminEvent.created_at.desc())).first()
    assert event.action == AdminAction.INVITE_RESENT and event.actor_id is None


# --- AC4: removing ------------------------------------------------------------------------


def test_removing_an_administrator_signs_them_out_and_stops_them_signing_in(admin, other, db):
    mei = _find(admin, OTHER["email"])
    with TestClient(app) as learner_browser:
        assert learner_browser.post("/api/auth/sign-in", json=OTHER).status_code == 200

        response = admin.post(f"{URL}/{mei['id']}/remove")

        assert response.status_code == 200
        assert response.json()["status"] == "removed"
        assert response.json()["removed_by"] == "Yash"
        assert other.get("/api/admin/auth/me").status_code == 401
        assert learner_browser.get("/api/auth/me").status_code == 401
    assert admin.post(SIGN_IN, json=OTHER).status_code == 401
    assert admin.post("/api/auth/sign-in", json=OTHER).status_code == 401

    email = mailer.outbox[-1]
    assert email.to == OTHER["email"]
    assert "Yash has removed your access" in email.text
    body = admin.get(URL).json()
    assert [a["email"] for a in body["admins"]] == [ADMIN["email"]]
    assert [a["email"] for a in body["removed"]] == [OTHER["email"]]
    assert body["activity"][0]["action"] == "removed"
    assert body["activity"][0]["actor_name"] == "Yash"
    assert body["activity"][0]["admin_name"] == "Mei"


def test_a_removed_administrator_gets_no_reset_links_and_old_ones_stop(admin, other):
    admin.post("/api/admin/auth/forgot-password", json={"email": OTHER["email"]})
    token = _token()
    mei = _find(admin, OTHER["email"])

    admin.post(f"{URL}/{mei['id']}/remove")
    mailer.outbox.clear()

    assert (
        admin.post("/api/admin/auth/reset-password/check", json={"token": token}).status_code == 410
    )
    admin.post("/api/admin/auth/forgot-password", json={"email": OTHER["email"]})
    admin.post("/api/auth/forgot-password", json={"email": OTHER["email"]})
    assert mailer.outbox == []


def test_removing_is_safe_to_repeat(admin, other, db):
    mei = _find(admin, OTHER["email"])
    admin.post(f"{URL}/{mei['id']}/remove")
    again = admin.post(f"{URL}/{mei['id']}/remove")
    assert again.status_code == 200
    assert _actions(db) == ["removed"]


def test_cancelling_an_invite_kills_the_link_without_an_email(admin, db):
    arjun = _invite(admin).json()
    token = _token()
    mailer.outbox.clear()

    admin.post(f"{URL}/{arjun['id']}/remove")

    assert admin.post(CHECK, json={"token": token}).status_code == 410
    assert mailer.outbox == []
    assert _find(admin, arjun["email"], "removed")["status"] == "removed"
    assert _actions(db) == ["invited", "invite_cancelled"]


def test_a_learner_cannot_be_removed_as_an_administrator(admin, make_user):
    learner = make_user("learner@example.com")
    assert admin.post(f"{URL}/{learner.id}/remove").status_code == 404


# --- AC5: yourself and the last administrator ---------------------------------------------


def test_you_cannot_remove_yourself(admin, other):
    yash = _find(admin, ADMIN["email"])
    response = admin.post(f"{URL}/{yash['id']}/remove")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "cannot_remove_self"
    assert admin.get("/api/admin/auth/me").status_code == 200


def test_the_last_administrator_cannot_be_removed(make_user, db):
    # Reachable only when two administrators remove each other at the same moment: the
    # second finds itself already removed and the other one the last left.
    yash = make_user(ADMIN["email"], role=UserRole.ADMIN)
    mei = make_user(OTHER["email"], role=UserRole.ADMIN)
    admins.remove_admin(db, yash, mei.id)

    with pytest.raises(ContentProblem) as refused:
        admins.remove_admin(db, mei, yash.id)

    assert refused.value.code == "last_admin"
    db.refresh(yash)
    assert not yash.is_removed


# --- Restoring ----------------------------------------------------------------------------


def test_restoring_sends_a_new_link_and_never_brings_back_the_old_password(admin, other, db):
    mei = _find(admin, OTHER["email"])
    admin.post(f"{URL}/{mei['id']}/remove")

    response = admin.post(f"{URL}/{mei['id']}/restore")

    assert response.status_code == 200
    assert response.json()["status"] == "invited"
    assert mailer.outbox[-1].subject == "Your SGJio admin access is back"
    assert admin.post(SIGN_IN, json=OTHER).status_code == 401
    assert admin.post(CHECK, json={"token": _token()}).json()["invited_by"] == "Yash"
    with TestClient(app) as browser:
        assert _accept(browser, _token(), "Restored123").status_code == 200
    assert _find(admin, OTHER["email"])["status"] == "active"
    assert _actions(db) == ["removed", "restored", "joined"]


def test_restoring_an_active_administrator_changes_nothing(admin, other, db):
    mei = _find(admin, OTHER["email"])
    assert admin.post(f"{URL}/{mei['id']}/restore").json()["status"] == "active"
    assert _actions(db) == []
    assert mailer.outbox == []


# --- The command line ---------------------------------------------------------------------


def test_create_admin_refuses_a_learners_email(make_user, db):
    learner = make_user("learner@example.com")
    assert cli.main(["create-admin", "--email", learner.email, "--password", "AdminPass123"]) == 1
    db.refresh(learner)
    assert learner.role == UserRole.USER


def test_create_admin_adds_one_and_restores_a_removed_one(client, make_user, db):
    email = "new@sgjio.example.com"
    assert cli.main(["create-admin", "--email", email, "--password", "AdminPass123"]) == 0
    new = db.scalar(select(User).where(User.email == email))
    actor = make_user(ADMIN["email"], role=UserRole.ADMIN)
    admins.remove_admin(db, actor, new.id)

    assert cli.main(["create-admin", "--email", email, "--password", "BackAgain123"]) == 0

    db.expire_all()
    assert not db.get(User, new.id).is_removed
    signed_in = client.post(SIGN_IN, json={"email": email, "password": "BackAgain123"})
    assert signed_in.status_code == 200
    assert _actions(db) == ["added", "removed", "restored"]
