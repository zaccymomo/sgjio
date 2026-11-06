# Working on SGJio

## Branches

- `main` is always working. Nobody pushes to it directly.
- Work on a branch named after the Jira issue: `SCRUM-61-register`, `SCRUM-43-progress-circles`.
- Keep branches short-lived. Pull `main` into your branch often.

## Commits

Start each message with the Jira key, so Jira links the commit to the issue:

```
SCRUM-61: add registration form and validation
```

## Pull requests

1. Push your branch and open a pull request into `main`. The template asks for the Jira key and the acceptance criteria you checked.
2. CI (`.github/workflows/ci.yml`) must pass. Its jobs:

   | Job                                                           | What it runs                                                                                                                                                       |
   | ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
   | **Service (identity)**, (content), (learning), (notification) | per service: `ruff check`, `ruff format --check`, `alembic upgrade head` + `alembic check` and `pytest`, against its own Postgres, RabbitMQ and Mailpit containers |
   | **Platform template**                                         | `templates/platform`'s lint and tests, and a check that every service's `app/platform/` is an unchanged copy                                                       |
   | **Event contracts**                                           | `contracts/validate.py`: every event schema, example and negative case                                                                                             |
   | **Gateway**                                                   | `services/gateway/tests/run.sh`: builds the nginx image, `nginx -t`, every route against stub services                                                             |
   | **Front end**                                                 | `npm ci`, `npm run lint`, `npm run format:check`, `npm run build`                                                                                                  |
   | **End to end**                                                | `docker compose up --build --wait`, `scripts/seed-all.sh --demo`, then the e2e suite through the gateway (resilience drills excluded)                              |

3. Merge with "Squash and merge", then delete the branch.

## Branch protection (one-time, repository owner)

GitHub → repository → **Settings → Branches → Add branch ruleset** (or "Add rule") for `main`:

- Require a pull request before merging, with **0 required approvals**
- Require status checks to pass: select every job above (they appear after CI has run once). On `main` the old **API** check is replaced by the four **Service** checks once this branch is merged.
- Block force pushes

## Working on a service

Each service in `services/<name>/` is built, tested and migrated on its own. Its README lists its tables, API, events and commands. Use [uv](https://docs.astral.sh/uv/) and a `.venv` per service (Python 3.11; never conda or the system Python):

```bash
docker compose up -d <name>-db rabbitmq mailpit     # its test database (<name>_test) and the broker
cd services/<name>
uv venv -p 3.11 .venv && uv pip install -p .venv/bin/python -r requirements-dev.txt
.venv/bin/python -m pytest
```

Try your change in the running app with `docker compose up -d --build --wait <name>` (then the front ends as usual). Read a service's logs with `docker compose logs -f <name>`.

A change that crosses services (a new field learners need from Content, say) goes in this order: the event's schema in `contracts/`, the producer, then the consumer. Then run `scripts/e2e.sh`.

## Before you push

```bash
cd services/<name> && .venv/bin/python -m ruff check . && .venv/bin/python -m ruff format . \
  && .venv/bin/python -m pytest && cd ../..     # each service you changed
npm run lint && npm run format && npm run typecheck
scripts/e2e.sh                                  # when a flow crosses services
```

## Changing a service's database

Each service has its own models and its own Alembic history; never point one service at another's database.

1. Edit `services/<name>/app/models.py`.
2. `cd services/<name> && .venv/bin/python -m alembic revision --autogenerate -m "short description"` (against its dev database, which the running container keeps at head).
3. **Read the generated file** in `services/<name>/alembic/versions/` and fix anything Alembic guessed wrong.
4. `.venv/bin/python -m alembic upgrade head && .venv/bin/python -m alembic check`, then run the tests (they rebuild `<name>_test` from the migrations).
5. Commit the model change and the migration together. The container applies it when it next starts (`docker compose up -d --build <name>`).

Never edit a migration that is already on `main`; add a new one. Enums are stored as VARCHAR + CHECK (`_enum()` in `models.py`), not native Postgres enums. Ids from other services are plain UUIDs, never foreign keys.

## Changing an event

The events in `contracts/events/` are the only thing services share ([contracts/README.md](contracts/README.md)).

- **Adding a field** is safe: add it to the schema and the example, then to the producer. Consumers ignore fields they don't know.
- **Removing, renaming or changing the meaning of a field** is breaking: it needs a new `schema_version`. Allow the new version in the schemas (`envelope.schema.json` fixes it at 1 today), teach each consumer's handler to read it and list it in that consumer's `schema_versions`, deploy the consumers, and only then have the producer `emit(..., schema_version=2)`. A consumer that hasn't been updated sends the new version to its dead-letter queue instead of misreading it.
- **A new event** needs a schema, an example and an entry in `CATALOGUE` in `contracts/validate.py`.

Producers' tests validate every event they write against the schemas, so a drift fails there first.

## Changing the shared plumbing

`templates/platform/app/platform/` is copied, identically, into every service (`app/platform/`). Change the template, run its tests (`templates/platform/README.md`), copy it into each service, and run their tests. CI fails if a copy differs.

## Secrets

Settings come from each service's environment: `docker-compose.yml` for the stack, or `services/<name>/.env` (git ignores it) when running a service on your machine. Add a new setting to the service's `app/config.py`, its `docker-compose.yml` environment, and its `.env.example` if it has one. Real SMTP credentials and API keys never go in the repository.
