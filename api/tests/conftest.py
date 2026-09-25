"""Test setup. Tests run against TEST_DATABASE_URL (never your dev database).

The schema is built by running the real Alembic migrations, so the tests also prove that
migrations work from a clean database.
"""

import os

# Configure before anything imports app.db, which creates the engine on import.
os.environ["EMAIL_BACKEND"] = "memory"
from app.config import Settings, get_settings  # noqa: E402

os.environ["DATABASE_URL"] = Settings().test_database_url
get_settings.cache_clear()

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app import mailer  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User, UserRole, UserType  # noqa: E402
from app.security import hash_password  # noqa: E402

API_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(API_DIR / "alembic"))
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    yield


@pytest.fixture(autouse=True)
def clean_database():
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    mailer.outbox.clear()
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
def make_user(db):
    def _make_user(
        email: str = "user@example.com",
        password: str = "Password123",
        role: UserRole = UserRole.USER,
        name: str = "Test User",
    ) -> User:
        user = User(
            name=name,
            email=email,
            password_hash=hash_password(password),
            role=role,
            user_type=UserType.NEWCOMER if role == UserRole.USER else None,
        )
        db.add(user)
        db.commit()
        return user

    return _make_user
