"""Identity's seed (SCRUM-72): the seed accounts, with the deterministic ids other services'
seeds rely on (contracts/README.md), each announced with identity.user.registered.

The monolith's seed tests about topics, lessons and the question bank are Content's; the
personas' placements and the Newcomer's completions are Learning's."""

import uuid

from sqlalchemy import func, select

from app.models import Profile, User, UserRole, UserType
from app.seed import TEST_USERS, seed, seed_user_id
from tests.helpers import outbox_events


def _expected_id(email: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, "sgjio:user:" + email)


def test_seed_creates_the_admin_the_newcomer_and_the_personas(db):
    created = seed(db)

    assert created[:2] == [
        "admin account admin@sgjio.example.com",
        "user account newcomer@sgjio.example.com",
    ]
    assert created[2:] == [f"test user {email}" for email in TEST_USERS]
    assert db.scalar(select(func.count()).select_from(User)) == 2 + len(TEST_USERS)

    admin = db.scalar(select(User).where(User.email == "admin@sgjio.example.com"))
    assert admin.role == UserRole.ADMIN and admin.user_type is None
    assert admin.intro_finished_at is None
    newcomer = db.scalar(select(User).where(User.email == "newcomer@sgjio.example.com"))
    assert newcomer.name == "Siddharth Sharma"
    assert newcomer.user_type == UserType.NEWCOMER
    assert newcomer.intro_finished_at is not None
    assert newcomer.profile.neighbourhood == "Tampines"
    for email, name in TEST_USERS.items():
        persona = db.scalar(select(User).where(User.email == email))
        assert persona.name == name
        assert persona.profile is not None
        assert persona.intro_finished_at is not None


def test_seed_logins_work(client, db):
    seed(db)
    assert (
        client.post(
            "/api/auth/sign-in",
            json={"email": "newcomer@sgjio.example.com", "password": "UserPass123"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/admin/auth/sign-in",
            json={"email": "admin@sgjio.example.com", "password": "AdminPass123"},
        ).status_code
        == 200
    )
    persona = {"email": "starter@sgjio.example.com", "password": "UserPass123"}
    assert client.post("/api/auth/sign-in", json=persona).status_code == 200


def test_seed_users_have_deterministic_ids(db):
    seed(db)
    for user in db.scalars(select(User)):
        assert user.id == _expected_id(user.email) == seed_user_id(user.email)


def test_every_seeded_account_is_registered_once(db):
    seed(db)
    registered = outbox_events("identity.user.registered")
    users = {user.id: user for user in db.scalars(select(User))}
    assert len(registered) == len(users)
    for event in registered:
        user = users[uuid.UUID(event["data"]["user_id"])]
        assert event["data"]["role"] == user.role.value
        assert event["data"]["user_type"] == (user.user_type.value if user.user_type else None)
        assert event["correlation_id"] is None  # from the command line, not a request


def test_seed_is_safe_to_run_twice(db):
    seed(db)
    before = len(outbox_events())
    assert seed(db) == []
    assert db.scalar(select(func.count()).select_from(User)) == 2 + len(TEST_USERS)
    assert len(outbox_events()) == before


def test_reseeding_keeps_an_edited_profile(db):
    seed(db)
    newcomer = db.scalar(select(User).where(User.email == "newcomer@sgjio.example.com"))
    newcomer.profile.neighbourhood = "Bedok"
    db.commit()
    seed(db)
    db.expire_all()
    assert db.scalar(select(Profile.neighbourhood).where(Profile.user_id == newcomer.id)) == (
        "Bedok"
    )
