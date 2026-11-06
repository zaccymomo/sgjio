# Platform template

The plumbing every service needs, kept here once and **copied** into each service as `services/<name>/app/platform/`. Services never import it from here (each image builds from its own folder), so a service can't be broken by a change to the template: it takes a change by copying it again.

```bash
cp -r templates/platform/app/platform services/<name>/app/platform
```

Then add `pika==1.3.2` to the service's `requirements.txt` (the rest, FastAPI, SQLAlchemy and psycopg, it already has). Keep the copy identical to the template; if a service must differ, say so in its `app/platform/__init__.py`.

## What's in it

| Module | Gives you |
|---|---|
| `config.py` | `get_config()`: `SERVICE_NAME`, `GATEWAY_KEY`, `BROKER_URL`, `RUN_RELAY`, `RUN_CONSUMER` from the environment. `configure(...)` overrides them (e.g. from your own Settings, or in tests). |
| `errors.py` | `Problem(code, message, status_code, field=None, extra=None, headers=None)`, `not_signed_in()`, `install_error_handlers(app)`: the `{"detail": {...}}` shape, and FastAPI's own 422. |
| `logging.py` | `configure_logging(level=None)`: JSON lines with service and request id, at `LOG_LEVEL` unless a level is given. `CorrelationIdMiddleware`: reads or makes `X-Request-ID`, returns it, keeps it in the `correlation_id` context variable, logs one line per request, and answers an unhandled exception with a logged 500 that keeps the id. |
| `health.py` | `health_router(SessionLocal)`: `/health/live` and `/health/ready` (`SELECT 1`). |
| `principal.py` | `Principal` and `require_principal("app" \| "admin")`, the auth contract in `contracts/README.md`. |
| `outbox.py` | `define_outbox_table(Base.metadata)`, `emit(session, type=..., aggregate_type=..., aggregate_id=..., aggregate_version=..., data=...)`, `run_relay(...)` (also prunes rows published over 7 days ago, hourly), `prune_published(...)`. |
| `consumer.py` | `Consumer(routing_keys=..., handlers={type: handler(session, envelope)}, session_factory=..., dedupe=None, max_attempts=5, queue_delivery_limit=20, dlq_message_ttl_ms=None)`. |
| `broker.py` | Exchange names and `connect()`. |
| `lifespan.py` | `install_platform(app, SessionLocal)` (middleware, error handlers, health) and `background_workers(...)` for the FastAPI lifespan; `run_until_signalled(...)` for a worker with no API. |
| `testing.py` | `app_headers(user_id, user_type, profile_completed)`, `admin_headers(user_id)`, `headers_for(principal)`, `make_envelope(type, data, aggregate_id, aggregate_version)`. |

## Using it

**`app/main.py`** (Content shown; Identity passes `consumers=[]`, Learning `relay=False`):

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.db import SessionLocal
from app.consumers import consumer          # your Consumer(...)
from app.platform.config import get_config
from app.platform.lifespan import background_workers, install_platform
from app.platform.logging import configure_logging

configure_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    with background_workers(SessionLocal, relay=True, consumers=[consumer]):
        yield

app = FastAPI(title="SGJio content", lifespan=lifespan, docs_url="/docs")
install_platform(app, SessionLocal)
```

**Models.** Put the outbox on your own metadata, so Alembic autogenerates it into your baseline:

```python
from app.platform.outbox import define_outbox_table
outbox = define_outbox_table(Base.metadata)   # table "outbox"
```

**Emitting.** In the same session and transaction as the change, before the commit:

```python
topic.version += 1
emit(db, type="content.topic.changed", aggregate_type="topic", aggregate_id=topic.id,
     aggregate_version=topic.version, data={"topic_id": topic.id, "name": topic.name, ...})
db.commit()
```

`data` may hold UUIDs, enums and timezone-aware datetimes; they are turned into JSON strings. It must match `contracts/events/<type>.schema.json`.

**Consuming.** Handlers get the session (inside a transaction the consumer commits) and the envelope dict. They must not commit, and must be idempotent (version guards, insert-if-absent, tombstones: `contracts/README.md`). A handler that raises is retried with backoff and dead-lettered on its 5th failure. If the database is down when it raises, that is not counted: the consumer holds the message, checks `SELECT 1` with backoff (at most 10 s apart) until Postgres is back, then retries it, so a database restart never dead-letters events. `queue_delivery_limit` is only the queue's backstop for consumers that die mid-message; changing it on an existing queue means deleting the queue first.

```python
consumer = Consumer(
    routing_keys=["identity.user.deleted"],
    handlers={"identity.user.deleted": on_user_deleted},
    session_factory=SessionLocal,
)   # queue "content.events" (from SERVICE_NAME), DLQ "content.events.dlq"
```

Notification passes `dedupe=lambda session, event_id: session.get(ProcessedEvent, event_id) is not None`, has its handler insert the `processed_events` row after sending, and `dlq_message_ttl_ms=3_600_000`. Its `python -m app.worker` calls `run_until_signalled(SessionLocal, consumers=[consumer])`.

**Protecting routes** (Content and Learning; Identity keeps its own cookie checks):

```python
@router.get("/progress")
def progress(principal: Principal = Depends(require_principal("app")), db=Depends(get_db)): ...
```

**Tests.** Set `RUN_RELAY=false` and `RUN_CONSUMER=false` (or `configure(run_relay=False, run_consumer=False)`) so no threads start, and `configure(gateway_key="test")`. Call routes with `headers=app_headers(user_id)`; drive consumers without a broker through `consumer.handle(json.dumps(make_envelope(...)).encode())`, which returns `Outcome.ACK`, `REQUEUE`, `RETRY` (database unreachable) or `REJECT`.

## Environment

| Variable | Default | Used by |
|---|---|---|
| `SERVICE_NAME` | `unknown` | log lines, the `producer` field, the queue name `<service>.events`, connection names |
| `GATEWAY_KEY` | empty (refuses every request) | `require_principal` |
| `BROKER_URL` | `amqp://sgjio:sgjio@localhost:5672/%2F` | relay and consumer |
| `RUN_RELAY` | `true` | `background_workers(relay=True)` |
| `RUN_CONSUMER` | `true` | `background_workers(consumers=[...])` |
| `LOG_LEVEL` | `INFO` | `configure_logging()` |

`docker-compose.yml` sets all of them for every service.

## Template tests

Unit tests run anywhere; the integration tests (outbox, relay to RabbitMQ to consumer, redelivery, out-of-order versions, dead-lettering, dedupe, worker threads) need the compose Postgres and RabbitMQ, and skip with a message if they are down. They use their own `platform_test` database on the notification Postgres (created if missing) and random queue names, so they never touch a service's data.

```bash
docker compose up -d notification-db rabbitmq
cd templates/platform
uv venv -p 3.11 .venv && uv pip install -p .venv/bin/python -r requirements.txt
.venv/bin/python -m pytest          # 30 tests
.venv/bin/python -m ruff check . && .venv/bin/python -m ruff format --check .
```
