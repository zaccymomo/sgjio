"""Test setup. Tests run against TEST_DATABASE_URL (the compose content-db's content_test
database, host port 5434), never the dev database.

The schema is built by running the real Alembic migrations, so the tests also prove that
migrations work from a clean database. No relay or consumer thread runs: events stay in the
outbox, where `outbox_events` reads them.

After every test, every event it wrote is checked against its JSON Schema in
contracts/events (the contract), and each aggregate's versions are checked to rise in the
order the events were written (contracts/README.md, "Ordering"). A test that writes the same
version again on purpose (republish-catalog) marks itself `@pytest.mark.repeats_versions`.
"""

import os

# Configure before anything imports app.db, which creates the engine on import.
os.environ["RUN_RELAY"] = "false"
os.environ["RUN_CONSUMER"] = "false"
os.environ["SERVICE_NAME"] = "content"
os.environ["GATEWAY_KEY"] = "test-gateway-key"
from app.config import Settings, get_settings  # noqa: E402

os.environ["DATABASE_URL"] = Settings().test_database_url
get_settings.cache_clear()

import json  # noqa: E402
import uuid  # noqa: E402
from collections import defaultdict  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from jsonschema import Draft202012Validator, FormatChecker  # noqa: E402
from referencing import Registry, Resource  # noqa: E402
from sqlalchemy import select, text  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import outbox  # noqa: E402
from app.platform.config import configure  # noqa: E402
from app.platform.outbox import envelope  # noqa: E402
from app.platform.testing import admin_headers, app_headers  # noqa: E402

SERVICE_DIR = Path(__file__).resolve().parent.parent
CONTRACTS = Path(
    os.environ.get("CONTRACTS_DIR", SERVICE_DIR.parent.parent / "contracts" / "events")
)
ADMIN_ID = uuid.UUID("0a0a0a0a-0000-4000-8000-000000000001")
LEARNER_ID = uuid.UUID("1e1e1e1e-0000-4000-8000-000000000002")

configure(
    service_name="content", gateway_key="test-gateway-key", run_relay=False, run_consumer=False
)


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "repeats_versions: the test republishes events at versions already sent"
    )


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
    """A client with no principal: what a request that bypassed the gateway, or a signed-out
    one, looks like."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def admin():
    """A client the gateway has let through as a signed-in administrator."""
    with TestClient(app, headers=admin_headers(ADMIN_ID)) as test_client:
        yield test_client


@pytest.fixture
def learner():
    """A client the gateway has let through as a signed-in main-app user."""
    with TestClient(app, headers=app_headers(LEARNER_ID)) as test_client:
        yield test_client


# --- Events ----------------------------------------------------------------------------------


def outbox_events(type_prefix: str = "", since: int = 0) -> list[dict]:
    """The events written so far (as the relay would send them), oldest first. `since` is
    how many there were at an earlier point (`len(outbox_events())`), to see only newer ones;
    `type_prefix` filters by type, e.g. "content.lesson."."""
    with SessionLocal() as session:
        rows = session.execute(select(outbox).order_by(outbox.c.id)).all()
    return [envelope(row) for row in rows[since:] if row.type.startswith(type_prefix)]


def event_types(since: int = 0) -> list[str]:
    return [event["type"] for event in outbox_events(since=since)]


@pytest.fixture(scope="session")
def contract_validators():
    if not CONTRACTS.is_dir():
        pytest.fail(f"contracts not found at {CONTRACTS}; set CONTRACTS_DIR")
    schemas = [json.loads(path.read_text()) for path in sorted(CONTRACTS.glob("*.schema.json"))]
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas
    )
    return {
        schema["title"]: Draft202012Validator(
            schema, registry=registry, format_checker=FormatChecker()
        )
        for schema in schemas
    }


def contract_problems(validators, event: dict) -> list[str]:
    validator = validators.get(event["type"])
    if validator is None:
        return [f"{event['type']}: no schema"]
    envelope_errors = list(validators["Event envelope"].iter_errors(event))
    return [
        f"{event['type']} {'/'.join(map(str, error.absolute_path))}: {error.message}"
        for error in [*envelope_errors, *validator.iter_errors(event)]
    ]


def ordering_problems(events: list[dict], *, strict: bool = True) -> list[str]:
    """Versions must rise per aggregate in outbox order (strictly, unless republishing);
    versions are written once each, at version 1; a lesson.changed naming a version this
    test published comes after that version's event."""
    problems = []
    last: dict[tuple[str, str], int] = {}
    versions_seen: set[str] = set()
    counts: defaultdict[str, int] = defaultdict(int)
    for event in events:
        key = (event["aggregate_type"], event["aggregate_id"])
        version = event["aggregate_version"]
        if event["type"] == "content.lesson_version.published":
            counts[event["aggregate_id"]] += 1
            versions_seen.add(event["aggregate_id"])
            if strict and counts[event["aggregate_id"]] > 1:
                problems.append(f"version {event['aggregate_id']} published twice")
            continue
        if key in last and (version <= last[key] if strict else version < last[key]):
            problems.append(f"{event['type']} {key}: version {version} after {last[key]}")
        last[key] = version
        if event["type"] == "content.lesson.changed":
            latest = event["data"]["latest_version_id"]
            published_here = any(
                e["aggregate_id"] == latest
                for e in events
                if e["type"] == "content.lesson_version.published"
            )
            if published_here and latest not in versions_seen:
                problems.append(f"lesson.changed names version {latest} before it was published")
    return problems


@pytest.fixture(autouse=True)
def events_follow_the_contract(request, contract_validators):
    """Checks every event each test wrote (see the module docstring)."""
    yield
    events = outbox_events()
    problems = [p for event in events for p in contract_problems(contract_validators, event)]
    strict = request.node.get_closest_marker("repeats_versions") is None
    problems += ordering_problems(events, strict=strict)
    assert not problems, "events break the contract:\n" + "\n".join(problems)
