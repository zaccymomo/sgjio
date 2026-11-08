"""Test setup. Tests run against TEST_DATABASE_URL (notification_test on the compose
notification-db, host port 5436) with the memory email backend. No consumer thread starts:
tests hand messages to `consumer.handle(...)`, as the consumer loop does."""

import os

# Configure before anything imports app.db (which creates the engine) or app.platform
# (which reads its settings on import).
os.environ["EMAIL_BACKEND"] = "memory"
os.environ["RUN_RELAY"] = "false"
os.environ["RUN_CONSUMER"] = "false"
os.environ["SERVICE_NAME"] = "notification"
from app.config import Settings, get_settings  # noqa: E402

os.environ["DATABASE_URL"] = Settings().test_database_url
get_settings.cache_clear()

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app import mailer  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402

SERVICE_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    config = Config(str(SERVICE_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(SERVICE_DIR / "alembic"))
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    yield


@pytest.fixture(autouse=True)
def clean_database():
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables}"))
    mailer.outbox.clear()
    yield


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
