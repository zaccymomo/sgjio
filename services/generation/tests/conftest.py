"""Test setup. Tests run against TEST_DATABASE_URL (generation_test on the compose
generation-db, host port 5438) with the fake model. No consumer or relay thread starts:
tests hand messages to `consumer.handle(...)`, as the consumer loop does, and read the
events from the outbox."""

import os

# Configure before anything imports app.db (which creates the engine) or app.platform
# (which reads its settings on import).
os.environ["RUN_RELAY"] = "false"
os.environ["RUN_CONSUMER"] = "false"
os.environ["SERVICE_NAME"] = "generation"
os.environ["GENERATION_FAKE"] = "true"
os.environ["GENERATION_ENABLED"] = "true"
from app.config import Settings, get_settings  # noqa: E402

os.environ["DATABASE_URL"] = Settings().test_database_url
get_settings.cache_clear()

import json  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from jsonschema import Draft202012Validator, FormatChecker  # noqa: E402
from referencing import Registry, Resource  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402

SERVICE_DIR = Path(__file__).resolve().parent.parent
EVENTS = SERVICE_DIR.parent.parent / "contracts" / "events"


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
    yield
    get_settings.cache_clear()


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="session")
def contract():
    """validate(envelope) -> list of problems against the envelope and the event's schema,
    exactly as contracts/validate.py checks them."""
    schemas = [json.loads(p.read_text()) for p in sorted(EVENTS.glob("*.schema.json"))]
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas
    )
    by_title = {
        schema["title"]: Draft202012Validator(
            schema, registry=registry, format_checker=FormatChecker()
        )
        for schema in schemas
    }

    def validate(instance: dict) -> list[str]:
        found = []
        for validator in (by_title["Event envelope"], by_title[instance["type"]]):
            found += [
                f"{'/'.join(map(str, e.absolute_path))}: {e.message}"
                for e in validator.iter_errors(instance)
            ]
        return found

    return validate
