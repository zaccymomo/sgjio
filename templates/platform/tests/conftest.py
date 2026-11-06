import os
import uuid

import pika
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.platform.config import configure

# A database of its own on the notification Postgres, created if missing, so these tests
# never touch a service's tables. Override with PLATFORM_TEST_DATABASE_URL.
DATABASE_URL = os.environ.get(
    "PLATFORM_TEST_DATABASE_URL",
    "postgresql+psycopg://notification:notification@localhost:5436/platform_test",
)
BROKER_URL = os.environ.get("PLATFORM_TEST_BROKER_URL", "amqp://sgjio:sgjio@localhost:5672/%2F")
GATEWAY_KEY = "test-gateway-key"


@pytest.fixture(autouse=True)
def platform_config():
    configure(service_name="platformtest", gateway_key=GATEWAY_KEY, broker_url=BROKER_URL)


def _ensure_database(url: str) -> None:
    target = make_url(url)
    admin = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        exists = connection.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": target.database}
        )
        if not exists:
            connection.execute(text(f'CREATE DATABASE "{target.database}"'))
    admin.dispose()


@pytest.fixture(scope="session")
def engine():
    try:
        _ensure_database(DATABASE_URL)
        engine = create_engine(DATABASE_URL)
        with engine.connect():
            pass
    except Exception as error:  # noqa: BLE001
        pytest.skip(f"test Postgres unavailable ({error}); run `docker compose up -d`")
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture(scope="session")
def broker():
    try:
        connection = pika.BlockingConnection(pika.URLParameters(BROKER_URL))
    except Exception as error:  # noqa: BLE001
        pytest.skip(f"RabbitMQ unavailable ({error}); run `docker compose up -d`")
    yield connection
    if connection.is_open:
        connection.close()


@pytest.fixture
def unique() -> str:
    """A prefix for event types and queue names, so runs never see each other's messages."""
    return f"platformtest{uuid.uuid4().hex[:8]}"
