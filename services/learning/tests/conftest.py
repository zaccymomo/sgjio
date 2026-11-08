"""Test setup. Tests run against TEST_DATABASE_URL (the compose learning-db's learning_test,
host port 5435), never the service's own database.

The schema is built by running the real Alembic migrations. Read models are only ever
filled through the real consumer, by the `content` and `identity` stand-ins
(tests/support), with envelopes checked against contracts/events. Learning's own tables
(completions, quizzes, exemptions) may be written directly, as the monolith's tests did.
"""

import os

from app.config import LOCAL_TEST_DATABASE

# Configure before anything imports app.db, which creates the engine on import.
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", LOCAL_TEST_DATABASE)
os.environ.setdefault("SERVICE_NAME", "learning")

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.platform.config import configure  # noqa: E402

configure(service_name="learning", gateway_key="test", run_relay=False, run_consumer=False)

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from tests.support.content import FakeContent  # noqa: E402
from tests.support.events import EventBus  # noqa: E402
from tests.support.identity import FakeIdentity, User  # noqa: E402

SERVICE_DIR = Path(__file__).resolve().parent.parent


def alembic_config() -> Config:
    config = Config(str(SERVICE_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(SERVICE_DIR / "alembic"))
    config.attributes["database_url"] = os.environ["DATABASE_URL"]
    return config


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    config = alembic_config()
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    yield


@pytest.fixture(autouse=True)
def clean_database():
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def content(bus) -> FakeContent:
    return FakeContent(bus)


@pytest.fixture
def identity(bus) -> FakeIdentity:
    return FakeIdentity(bus)


@pytest.fixture
def make_user(identity):
    """Register an account through identity.user.registered, as the monolith's make_user
    created one. Learners are Newcomers unless said otherwise."""

    def _make_user(
        email: str = "user@example.com",
        password: str = "unused",
        role: str = "user",
        name: str = "Test User",
        user_type: str = "newcomer",
        profile_completed: bool = True,
    ) -> User:
        del password  # sessions are Identity's; the gateway's headers stand in for them
        return identity.register(
            email, role=role, user_type=user_type, name=name, profile_completed=profile_completed
        )

    return _make_user


def sign_in(client: TestClient, user: User) -> TestClient:
    """What signing in amounts to here: the headers the gateway sends for this user."""
    client.headers.clear()
    client.headers.update(user.headers())
    return client


def sign_out(client: TestClient) -> TestClient:
    client.headers.clear()
    return client
